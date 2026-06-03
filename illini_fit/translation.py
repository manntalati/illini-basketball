"""Big Ten Translation model: what a player's box line becomes at Illinois's level.

Box-score counting stats (points, made threes, assists, rebounds) are *not*
opponent-adjusted: a 20-and-8 line against low-major defenses does not survive
contact with Big Ten competition. This module learns, from real history, how
much of each box stat a player keeps when he moves UP in competition, then
projects every candidate's production "as if he played Illinois's schedule."

Calibration is fully data-driven and transparent:

  * We match the SAME player across consecutive seasons via BartTorvik's stable
    player id (``pid``).
  * A player who changed teams is a transfer; the Barthag gap between his
    destination and origin measures how big a level jump he made.
  * For each box stat we fit a one-parameter retention line, anchored so a
    zero-gap move means no change:  ``ratio = 1 + slope * gap``.  ``slope`` is the
    least-squares fit through that anchor across the whole transfer cohort, so
    every multiplier is an empirical estimate, not an assumption.

Efficiency stats (TS%, usage) come out with a near-zero slope, proof that
efficiency travels while counting volume deflates. That's exactly the scouting
lesson the tool exists to surface.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import DEFAULT_SEASON, TEAM

# Per-game / rate stats we translate. Each maps to a function returning the
# player's per-game value, so totals (three_pm) and per-game columns are uniform.
STAT_ACCESSORS: dict[str, callable] = {
    "pts_pg": lambda d: d["pts_pg"],
    "three_pm_pg": lambda d: d["three_pm"] / d["gp"].clip(lower=1),
    "ast_pg": lambda d: d["ast_pg"],
    "trb_pg": lambda d: d["trb_pg"],
    "usg": lambda d: d["usg"],
    "ts": lambda d: d["ts"],
}

# A counting stat can only deflate when moving up; efficiency/usage may drift
# either way, so they are not capped at 1.0.
COUNTING_STATS = {"pts_pg", "three_pm_pg", "ast_pg", "trb_pg"}

# Minimum origin value before a ratio is trustworthy (kills divide-by-tiny noise).
_STAT_FLOOR = {
    "pts_pg": 4.0, "three_pm_pg": 0.4, "ast_pg": 0.7, "trb_pg": 1.5,
    "usg": 12.0, "ts": 40.0,
}

STAT_LABEL = {
    "pts_pg": "Points/g", "three_pm_pg": "Made 3s/g", "ast_pg": "Assists/g",
    "trb_pg": "Rebounds/g", "usg": "Usage%", "ts": "TS%",
}


# --------------------------------------------------------------------------- #
# Cohort construction
# --------------------------------------------------------------------------- #
def _season_table(year: int) -> pd.DataFrame:
    """Players for a season with their team's Barthag attached (lazy import)."""
    from .fetch import get_players, get_teams

    players = get_players(year).copy()
    bt = get_teams(year).set_index("team")["barthag"]
    players["team_barthag"] = players["team"].map(bt)
    return players


def transfer_pairs(year_from: int, year_to: int,
                   min_gp: int = 15, min_min_pct: float = 40.0) -> pd.DataFrame:
    """Match rotation players across two seasons who changed teams (transfers)."""
    a = _season_table(year_from)
    b = _season_table(year_to)
    rot = lambda d: d[(d["gp"] >= min_gp) & (d["min_pct"] >= min_min_pct)]
    m = rot(a).merge(rot(b), on="pid", suffixes=("_0", "_1"))
    m = m[(m["team_0"] != m["team_1"])
          & m["team_barthag_0"].notna() & m["team_barthag_1"].notna()].copy()
    m["gap"] = m["team_barthag_1"] - m["team_barthag_0"]
    return m


def _ratio_frame(pairs: pd.DataFrame, stat: str) -> pd.DataFrame:
    """(gap, ratio) rows for one stat, with origin floor + outlier clipping."""
    acc = STAT_ACCESSORS[stat]
    orig = acc(pairs.rename(columns=lambda c: c[:-2] if c.endswith("_0") else c))
    dest = acc(pairs.rename(columns=lambda c: c[:-2] if c.endswith("_1") else c))
    df = pd.DataFrame({"gap": pairs["gap"].values,
                       "orig": orig.values, "dest": dest.values})
    df = df[df["orig"] >= _STAT_FLOOR[stat]]
    df["ratio"] = (df["dest"] / df["orig"]).clip(0.2, 3.0)
    return df.dropna()


def _fit_slope(df: pd.DataFrame) -> float:
    """Least-squares slope of (ratio-1) on gap, forced through (gap=0, ratio=1)."""
    g = df["gap"].values
    denom = float(np.sum(g * g))
    if denom == 0:
        return 0.0
    return float(np.sum(g * (df["ratio"].values - 1.0)) / denom)


# --------------------------------------------------------------------------- #
# The model
# --------------------------------------------------------------------------- #
@dataclass
class TranslationModel:
    slopes: dict[str, float]
    illinois_barthag: float
    n_pairs: int
    n_used: dict[str, int] = field(default_factory=dict)

    def multiplier(self, gap: float | pd.Series, stat: str):
        """Retention multiplier for a level jump of size ``gap`` (Barthag)."""
        mult = 1.0 + self.slopes[stat] * gap
        if stat in COUNTING_STATS:  # moving up can't inflate a counting stat
            mult = np.minimum(mult, 1.0)
        return np.clip(mult, 0.2, 1.5)

    def gap_to_illinois(self, team_barthag: float | pd.Series):
        """How far below Illinois the player's current level is (>=0)."""
        return np.clip(self.illinois_barthag - team_barthag, 0.0, None)

    def project(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add projected box line + retention + level-jump label to a player frame."""
        out = df.copy()
        gap = self.gap_to_illinois(out["team_barthag"])
        out["level_gap"] = np.round(gap, 3)
        for stat, acc in STAT_ACCESSORS.items():
            raw = acc(out)
            out[f"raw_{stat}"] = raw.round(2)
            out[f"proj_{stat}"] = (raw * self.multiplier(gap, stat)).round(2)
        # Overall counting-production retention (scoring is the headline).
        out["retention"] = (self.multiplier(gap, "pts_pg") * 100).round(0)
        out["level_jump"] = [level_jump_label(g) for g in gap]
        return out


def level_jump_label(gap: float) -> str:
    if gap <= 0.05:
        return "Big Ten-ready"
    if gap <= 0.20:
        return "Modest jump"
    if gap <= 0.40:
        return "Sizable jump"
    return "Major jump (high variance)"


def calibrate(transitions: list[tuple[int, int]] | None = None,
              illinois_season: int = DEFAULT_SEASON) -> TranslationModel:
    """Fit retention slopes from real transfers across one or more season jumps."""
    transitions = transitions or [(illinois_season - 2, illinois_season - 1),
                                   (illinois_season - 1, illinois_season)]
    pairs = pd.concat([transfer_pairs(a, b) for a, b in transitions],
                      ignore_index=True)
    slopes, n_used = {}, {}
    for stat in STAT_ACCESSORS:
        rf = _ratio_frame(pairs, stat)
        slopes[stat] = _fit_slope(rf)
        n_used[stat] = len(rf)

    teams = _season_table(illinois_season)
    ill = teams.loc[teams["team"] == TEAM, "team_barthag"]
    ill_bt = float(ill.iloc[0]) if not ill.empty else 0.9
    return TranslationModel(slopes=slopes, illinois_barthag=ill_bt,
                            n_pairs=len(pairs), n_used=n_used)


def projected_line(model: TranslationModel, row: pd.Series) -> str:
    """One-line 'as a Big Ten player' projection for a single candidate."""
    return (f"{model.illinois_barthag:.2f} Barthag target · "
            f"{row['proj_pts_pg']:.1f} pts, {row['proj_three_pm_pg']:.1f} 3PM, "
            f"{row['proj_ast_pg']:.1f} ast, {row['proj_trb_pg']:.1f} reb "
            f"(~{row['retention']:.0f}% of raw scoring) · {row['level_jump']}")


if __name__ == "__main__":
    model = calibrate()
    print(f"Calibrated on {model.n_pairs} cross-season transfers · "
          f"Illinois Barthag = {model.illinois_barthag:.3f}\n")
    print(f"{'stat':<14}{'slope':>9}{'n':>7}   retention at gap=0.30")
    for s in STAT_ACCESSORS:
        ret = float(model.multiplier(0.30, s))
        print(f"{STAT_LABEL[s]:<14}{model.slopes[s]:>9.3f}{model.n_used[s]:>7}"
              f"        {ret*100:>5.0f}%")

    # Project the live candidate pool and eyeball a few big level jumps.
    from .fetch import get_players, get_teams
    from .fit_score import candidate_pool

    players, teams = get_players(), get_teams()
    pool = candidate_pool(players, teams)
    proj = model.project(pool).sort_values("raw_pts_pg", ascending=False)
    cols = ["player", "team", "conf", "team_barthag", "level_gap",
            "raw_pts_pg", "proj_pts_pg", "retention", "level_jump"]
    print("\nHighest raw scorers, translated to Illinois's level:")
    print(proj[cols].head(12).to_string(index=False))

    # --- assertions --------------------------------------------------------
    assert model.n_pairs > 300, f"too few transfers calibrated: {model.n_pairs}"
    assert model.slopes["pts_pg"] < 0, "scoring should deflate when moving up"
    assert abs(model.slopes["ts"]) < abs(model.slopes["pts_pg"]), \
        "efficiency should travel better than counting volume"
    big = proj[proj["level_gap"] > 0.3]
    assert (big["proj_pts_pg"] <= big["raw_pts_pg"] + 1e-9).all(), \
        "counting production must not inflate on a level-up"
    print("\nSanity checks passed.")
