"""Precedent engine — outcome-backed projections from real comparable transfers.

The Big Ten Translation model gives a *formula* answer ("~78% of scoring
survives a jump this size"). This module backs that number with **named, real
precedent**: for any target it finds the historical transfers who made the most
similar level-jump from the most similar starting profile, then reports what
*actually* happened to their box line the next season. The staff gets a
**confidence band** ("5 players like him kept 71-88% of scoring, median 80%")
instead of one false-precision number.

It reuses exactly the public, cross-season BartTorvik data the translation model
is calibrated on — the same player matched across seasons by stable ``pid`` —
so nothing here is synthetic or assumed.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .config import DEFAULT_SEASON
from .fetch import players_snapshot, teams_snapshot
from .similarity import _REF_DIST, _with_features, _zmatrix  # noqa: F401
from .translation import transfer_pairs

# Only learn retention from players who actually scored, so a 1.5 -> 1.0 ppg
# blip can't masquerade as a meaningful "kept 67%" data point.
_PTS_FLOOR = 6.0
# How hard we insist the precedent's jump SIZE matches the target's jump size.
_GAP_WEIGHT = 1.5


def _snapshots_present(year: int) -> bool:
    return os.path.exists(players_snapshot(year)) and os.path.exists(teams_snapshot(year))


def up_transfer_cohort(illinois_season: int = DEFAULT_SEASON,
                       transitions: list[tuple[int, int]] | None = None) -> pd.DataFrame:
    """Real players who moved UP in competition, with before/after box lines.

    Each row is one player's season-pair (origin ``_0`` -> destination ``_1``)
    plus the Barthag ``gap`` he jumped and the share of scoring he kept.
    """
    transitions = transitions or [(illinois_season - 2, illinois_season - 1),
                                  (illinois_season - 1, illinois_season)]
    frames = [transfer_pairs(a, b) for a, b in transitions
              if _snapshots_present(a) and _snapshots_present(b)]
    if not frames:
        return pd.DataFrame()
    pairs = pd.concat(frames, ignore_index=True)
    pairs = pairs[(pairs["gap"] > 0.02) & (pairs["pts_pg_0"] >= _PTS_FLOOR)].copy()
    pairs["kept_pct"] = (pairs["pts_pg_1"] / pairs["pts_pg_0"]).clip(0.1, 2.0) * 100.0
    return pairs.reset_index(drop=True)


def _origin_frame(cohort: pd.DataFrame) -> pd.DataFrame:
    """The cohort's PRE-jump (origin) profiles, with un-suffixed column names."""
    base = {c[:-2]: cohort[c].values for c in cohort.columns if c.endswith("_0")}
    return pd.DataFrame(base)


def precedents(target: pd.Series, cohort: pd.DataFrame, mu: pd.Series, sigma: pd.Series,
               illinois_barthag: float, n: int = 6,
               gap_weight: float = _GAP_WEIGHT) -> pd.DataFrame:
    """The ``n`` real up-transfers most like ``target`` (profile + jump size).

    Matches the target's *current* style to each precedent's *origin* style
    (z-scored, Euclidean) and penalises a mismatch in how big a level jump the
    two are making, so the comps are players who started where this target is
    and then leapt about as far as he would to reach Illinois.
    """
    if not len(cohort):
        return pd.DataFrame()
    coh = cohort[cohort["pid"] != target.get("pid")].copy()
    if not len(coh):
        return pd.DataFrame()

    omat = _zmatrix(_with_features(_origin_frame(coh)), mu, sigma)
    q = _zmatrix(_with_features(pd.DataFrame([target])), mu, sigma)[0]
    style_dist = np.linalg.norm(omat - q, axis=1)

    target_gap = max(float(illinois_barthag) - float(target["team_barthag"]), 0.0)
    gaps = coh["gap"].to_numpy()
    gap_sigma = float(gaps.std()) or 0.1
    gap_pen = gap_weight * np.abs(gaps - target_gap) / gap_sigma
    dist = np.sqrt(style_dist ** 2 + gap_pen ** 2)

    coh["match"] = np.round(100.0 * np.exp(-dist / _REF_DIST), 1)
    sel = coh.sort_values("match", ascending=False).head(n)
    return pd.DataFrame({
        "player": sel["player_1"].values,
        "from": sel["team_0"].values,
        "to": sel["team_1"].values,
        "from_conf": sel["conf_0"].values,
        "to_conf": sel["conf_1"].values,
        "gap": np.round(sel["gap"].values, 3),
        "from_pts": np.round(sel["pts_pg_0"].values, 1),
        "to_pts": np.round(sel["pts_pg_1"].values, 1),
        "kept_pct": np.round(sel["kept_pct"].values, 0),
        "match": sel["match"].values,
    }).reset_index(drop=True)


def precedent_band(prec: pd.DataFrame, target_pts: float) -> dict | None:
    """Turn the matched precedents into a kept-% band + projected scoring band."""
    if prec is None or not len(prec):
        return None
    kept = prec["kept_pct"].to_numpy(dtype=float)
    p25, p50, p75 = (float(x) for x in np.percentile(kept, [25, 50, 75]))
    tp = float(target_pts)
    return {
        "n": int(len(prec)),
        "kept_p25": round(p25), "kept_med": round(p50), "kept_p75": round(p75),
        "pts_low": round(tp * p25 / 100, 1),
        "pts_med": round(tp * p50 / 100, 1),
        "pts_high": round(tp * p75 / 100, 1),
    }


def band_sentence(band: dict | None) -> str:
    """One-line, staff-ready summary of the precedent band."""
    if not band:
        return "No close historical precedent in the cross-season sample."
    return (f"{band['n']} comparable real transfers kept "
            f"{band['kept_p25']:.0f}–{band['kept_p75']:.0f}% of their scoring "
            f"(median {band['kept_med']:.0f}%) → ~{band['pts_low']:.1f}–"
            f"{band['pts_high']:.1f} pts at Illinois's level.")


if __name__ == "__main__":
    from .fetch import get_players, get_teams
    from .fit_score import candidate_pool
    from .similarity import build_reference
    from .translation import calibrate

    players, teams = get_players(), get_teams()
    pool = candidate_pool(players, teams)
    mu, sigma = build_reference(players)
    model = calibrate()
    cohort = up_transfer_cohort()

    # A high-scoring player making a real level jump is the interesting case.
    big = pool[pool["team_barthag"] < model.illinois_barthag - 0.30]
    tgt = big.sort_values("pts_pg", ascending=False).iloc[0]
    prec = precedents(tgt, cohort, mu, sigma, model.illinois_barthag, n=6)
    band = precedent_band(prec, tgt["pts_pg"])

    print(f"Cohort of real up-transfers: {len(cohort)}\n")
    print(f"{tgt['player']} ({tgt['team']}, {tgt['conf']}) — {tgt['pts_pg']:.1f} ppg, "
          f"jumping ~{model.illinois_barthag - tgt['team_barthag']:.2f} Barthag to Illinois\n")
    print("Most comparable real transfers (started similar, jumped similar):")
    print(prec.to_string(index=False))
    print("\n" + band_sentence(band))

    # --- assertions --------------------------------------------------------
    assert len(cohort) > 200, f"too few precedents in cohort: {len(cohort)}"
    assert len(prec) == 6, "should return the requested number of precedents"
    assert prec["match"].is_monotonic_decreasing, "precedents must be sorted by match"
    assert prec["kept_pct"].between(10, 200).all(), "kept% out of sane range"
    assert band["kept_p25"] <= band["kept_med"] <= band["kept_p75"], "band must be ordered"
    print("\nSanity checks passed.")
