"""The Fit Score model.

Every candidate (non-Illinois D-I player with remaining eligibility) gets a
0-100 Fit Score = weighted blend of four components, each 0-100 and each shown
separately so any number is explainable:

  1. production      — proven on-court value (BPM, porpag, minutes load)
  2. role_fit        — does their position fill a depleted Illinois spot?
  3. system_fit      — do their strengths match what Illinois needs (the
                       stat-priority weights from `needs`)?
  4. attainability   — realism of landing them, from their team's strength

Components are percentile-ranked *within the candidate pool*, so a score answers
"how does this player compare to other realistic targets," which is how a staff
actually reads a board.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import TEAM
from .needs import CATEGORY_LABEL, STAT_CATEGORIES

DEFAULT_WEIGHTS = {
    "production": 0.35,
    "role": 0.20,
    "system": 0.35,
    "attainability": 0.10,
}


def _pct(s: pd.Series, ascending: bool = True) -> pd.Series:
    """Percentile rank (0-100) within the pool; lower-is-better -> ascending=False."""
    return s.rank(pct=True, ascending=ascending) * 100.0


def attain_label(barthag: float) -> str:
    if barthag >= 0.85:
        return "High-major proven"
    if barthag >= 0.60:
        return "High-major rotation"
    if barthag >= 0.35:
        return "Mid-major riser"
    return "Low-major standout"


def candidate_pool(
    players: pd.DataFrame,
    teams: pd.DataFrame,
    min_gp: int = 20,
    min_min_pct: float = 40.0,
    include_seniors: bool = False,
    exclude_team: str = TEAM,
) -> pd.DataFrame:
    """Filter to realistic, proven transfer targets and attach team strength."""
    df = players[players["team"] != exclude_team].copy()
    df = df[(df["gp"] >= min_gp) & (df["min_pct"] >= min_min_pct)]
    if not include_seniors:
        df = df[df["yr"] != "Sr"]  # graduating seniors have no eligibility to transfer

    strength = teams[["team", "barthag"]].rename(columns={"barthag": "team_barthag"})
    df = df.merge(strength, on="team", how="left")
    df["team_barthag"] = df["team_barthag"].fillna(teams["barthag"].median())
    return df.reset_index(drop=True)


def _category_percentiles(pool: pd.DataFrame) -> dict[str, pd.Series]:
    """Map each need-category to a 0-100 'how good is this player at it' score."""
    gp = pool["gp"].clip(lower=1)
    return {
        "shooting": _pct(pool["three_pm"] / gp),                       # made-3 volume
        "playmaking": 0.6 * _pct(pool["ast_pct"]) + 0.4 * _pct(pool["to_pct"], ascending=False),
        "rim_protection": _pct(pool["blk_pct"]),
        "rebounding": _pct(pool["orb_pct"] + pool["drb_pct"]),
        "perimeter_defense": _pct(pool["stl_pct"]),
        "scoring": 0.6 * _pct(pool["pts_pg"]) + 0.4 * _pct(pool["ts"]),
    }


def _highlight(row: pd.Series, cat: str) -> str:
    g = max(row["gp"], 1)
    if cat == "shooting":
        return f"{row['three_pm'] / g:.1f} 3PM/g on {row['three_pct']:.0%}"
    if cat == "playmaking":
        return f"{row['ast_pg']:.1f} ast/g ({row['ast_pct']:.0f} AST%)"
    if cat == "rim_protection":
        return f"{row['blk_pct']:.1f}% block rate"
    if cat == "rebounding":
        return f"{row['trb_pg']:.1f} reb/g"
    if cat == "perimeter_defense":
        return f"{row['stl_pct']:.1f}% steal rate"
    if cat == "scoring":
        return f"{row['pts_pg']:.1f} pts/g on {row['ts']:.1f}% TS"
    return ""


def score_pool(pool: pd.DataFrame, needs: dict, weights: dict | None = None) -> pd.DataFrame:
    """Return the pool with the four components, the Fit Score, and a rationale."""
    weights = weights or DEFAULT_WEIGHTS
    out = pool.copy()

    # 1. Production -------------------------------------------------------
    production = 0.5 * _pct(out["bpm"]) + 0.3 * _pct(out["porpag"]) + 0.2 * _pct(out["min_pct"])

    # 2. Role fit (group-level positional need, normalized to the biggest hole) --
    pos = needs["position_need"]
    max_need = max(pos.values()) if pos else 0
    if max_need > 0:
        role = out["group"].map(lambda g: 100.0 * pos.get(g, 0.0) / max_need)
    else:
        role = pd.Series(50.0, index=out.index)  # no positional pressure -> neutral

    # 3. System fit (weighted by the stat priorities we need to replace) ---
    cat_pct = _category_percentiles(out)
    sp = needs["stat_priority"]
    tot = sum(sp.values()) or 1.0
    system = sum(sp[c] * cat_pct[c] for c in cat_pct) / tot

    # 4. Attainability ----------------------------------------------------
    attain = (100.0 * (1.0 - out["team_barthag"] * 0.6)).clip(0, 100)

    out["production"] = production.round(1)
    out["role_fit"] = role.round(1)
    out["system_fit"] = system.round(1)
    out["attainability"] = attain.round(1)
    out["fit_score"] = (
        weights["production"] * production
        + weights["role"] * role
        + weights["system"] * system
        + weights["attainability"] * attain
    ).round(1)
    out["attain_label"] = out["team_barthag"].map(attain_label)

    # Per-player rationale: lead with the two needs they best address.
    relevance = pd.DataFrame({c: sp[c] * cat_pct[c] for c in cat_pct}, index=out.index)
    cats = list(relevance.columns)

    def _rationale(i: int) -> str:
        row = out.loc[i]
        order = np.argsort(relevance.loc[i].values)[::-1]
        picks = [cats[j] for j in order[:2] if relevance.loc[i].values[j] > 0]
        hi = "; ".join(_highlight(row, c) for c in picks) if picks else "rotation contributor"
        fills = " + ".join(CATEGORY_LABEL[c] for c in picks[:2]) if picks else "depth"
        return (f"{row['role']} ({row['team']}). {hi}; +{row['bpm']:.1f} BPM. "
                f"Helps {fills}. {row['attain_label']}.")

    out["rationale"] = [_rationale(i) for i in out.index]
    return out.sort_values("fit_score", ascending=False).reset_index(drop=True)


def build_board(
    players: pd.DataFrame,
    teams: pd.DataFrame,
    needs: dict,
    weights: dict | None = None,
    **pool_kwargs,
) -> pd.DataFrame:
    """Convenience: filter pool then score it."""
    pool = candidate_pool(players, teams, **pool_kwargs)
    return score_pool(pool, needs, weights)


if __name__ == "__main__":
    # End-to-end sanity check on the live Illinois pipeline.
    from .fetch import get_players, get_teams
    from .profile import default_departures, get_roster
    from .needs import detect_needs

    players, teams = get_players(), get_teams()
    roster = get_roster(players)
    nd = detect_needs(roster, default_departures(roster))
    board = build_board(players, teams, nd)

    cols = ["player", "team", "conf", "role", "yr", "fit_score",
            "production", "role_fit", "system_fit", "attainability", "attain_label"]
    print(f"Pool size: {len(board)}  |  Needs: {nd['headline']}\n")
    print(board[cols].head(15).to_string(index=False))

    # --- assertions: the model must behave sensibly --------------------------
    # A high-need shooting profile should reward a high-volume, efficient shooter.
    shoot_needs = {
        "departures": [],
        "position_need": {"Guard": 1.0, "Wing": 0.5, "Big": 0.0},
        "stat_priority": {"shooting": 1.0, "playmaking": 0.6, "scoring": 0.4,
                          "rim_protection": 0.0, "rebounding": 0.0, "perimeter_defense": 0.0},
        "headline": "test",
    }
    b2 = build_board(players, teams, shoot_needs)
    top = b2.head(50)
    assert top["three_pm"].mean() > board.head(50)["three_pm"].mean(), \
        "shooting-weighted board should surface more shooters"
    assert (b2["fit_score"].between(0, 100)).all(), "fit scores must be 0-100"
    assert b2["group"].iloc[0] in ("Guard", "Wing"), "guard/wing need should top the board"
    print("\nSanity checks passed.")
