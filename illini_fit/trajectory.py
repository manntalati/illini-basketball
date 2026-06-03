"""Player development trajectories: who is rising, who is plateauing.

The Fit Score reads a single season, which underrates ascending young players
and overrates one-year spikes on bad teams. This module tracks the same player
across seasons (stable ``pid``) and measures how his game moved year over year.
That lets the board flag genuine risers and breakout candidates a single
box-score season hides, and lets Player Detail show a real development line
instead of one static number.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .config import DEFAULT_SEASON
from .fetch import get_players, players_snapshot

# Metric -> the name of its year-over-year delta column.
_DELTAS = {"bpm": "d_bpm", "usg": "d_usg", "ts": "d_ts",
           "pts_pg": "d_pts", "min_pct": "d_min", "ast_pct": "d_ast"}

# Stats we carry from the prior season for the multi-year line in Player Detail.
_CARRY = ["bpm", "usg", "ts", "pts_pg", "min_pct", "ast_pct"]

_PREV_COLS = ["pid", "team", "yr"] + _CARRY


def _rotation(df: pd.DataFrame, min_gp: int, min_min_pct: float) -> pd.DataFrame:
    """Real rotation players only, so prior-season BPM isn't tiny-sample noise.

    Requiring a genuine role in BOTH seasons is what keeps the riser board
    honest: a +20 BPM 'jump' off a 5-minute freshman year is noise, not growth.
    """
    d = df[df["pid"].notna()].copy()
    d = d[(d["pid"] != 0) & (d["gp"] >= min_gp) & (d["min_pct"] >= min_min_pct)]
    return d.sort_values("min_pct", ascending=False).drop_duplicates("pid")


def _traj_index(m: pd.DataFrame) -> pd.Series:
    """0-100 development index: BPM growth weighted most, efficiency-aware."""
    w = {"d_bpm": 1.4, "d_pts": 0.7, "d_min": 0.6, "d_usg": 0.5, "d_ts": 0.4}
    num = sum(wt * m[c].rank(pct=True) for c, wt in w.items())
    return (num / sum(w.values()) * 100.0).round(1)


def _label(r: pd.Series) -> str:
    young = str(r.get("yr")) in ("Fr", "So", "Jr")
    if young and r["d_bpm"] >= 2.0 and r["d_usg"] >= 1.5 and r["d_ts"] >= -1.5:
        return "Breakout"          # bigger role AND held efficiency, still young
    if r["d_bpm"] >= 1.5:
        return "Ascending"
    if r["d_bpm"] <= -1.5:
        return "Declining"
    return "Steady"


def player_trajectories(season: int = DEFAULT_SEASON, lookback: int = 1,
                        min_gp: int = 12, min_min_pct: float = 25.0) -> pd.DataFrame:
    """Year-over-year change per returning rotation player, with a riser label."""
    prev_year = season - lookback
    if not (os.path.exists(players_snapshot(season))
            and os.path.exists(players_snapshot(prev_year))):
        return pd.DataFrame()

    now = _rotation(get_players(season), min_gp, min_min_pct)[
        ["pid", "player", "team", "yr"] + _CARRY]
    prev = _rotation(get_players(prev_year), min_gp, min_min_pct)[_PREV_COLS]
    m = now.merge(prev, on="pid", suffixes=("", "_prev"))
    if not len(m):
        return pd.DataFrame()

    for col, d in _DELTAS.items():
        m[d] = (m[col] - m[f"{col}_prev"]).round(2)
    m["traj_index"] = _traj_index(m)
    m["traj_label"] = m.apply(_label, axis=1)
    return m.reset_index(drop=True)


_TRAJ_COLS = (["pid", "traj_index", "traj_label", "team_prev"]
              + list(_DELTAS.values()) + [f"{c}_prev" for c in _CARRY])


def attach_trajectory(board: pd.DataFrame, traj: pd.DataFrame) -> pd.DataFrame:
    """Left-join trajectory onto a scored board; non-matches = first D-I season."""
    out = board.copy()
    if traj is None or not len(traj):
        out["traj_label"] = "n/a"
        out["traj_index"] = np.nan
        for c in list(_DELTAS.values()) + [f"{c}_prev" for c in _CARRY] + ["team_prev"]:
            out[c] = np.nan
        return out
    out = out.merge(traj[_TRAJ_COLS].drop_duplicates("pid"), on="pid", how="left")
    out["traj_label"] = out["traj_label"].fillna("First D-I season")
    return out


def trajectory_line(row: pd.Series) -> pd.DataFrame | None:
    """Prev-season -> this-season table for the metrics we track (Player Detail)."""
    if pd.isna(row.get("traj_index")):
        return None
    label = {"bpm": "BPM", "usg": "Usage%", "ts": "TS%", "pts_pg": "Pts/g",
             "min_pct": "Min%", "ast_pct": "AST%"}
    rows = []
    for c in _CARRY:
        prev, now = row.get(f"{c}_prev"), row.get(c)
        if pd.isna(prev) or pd.isna(now):
            continue
        rows.append((label[c], round(float(prev), 1), round(float(now), 1),
                     round(float(now) - float(prev), 1)))
    return pd.DataFrame(rows, columns=["Metric", "Last yr", "This yr", "Δ"])


if __name__ == "__main__":
    from .fetch import get_teams
    from .fit_score import build_board, candidate_pool  # noqa: F401
    from .needs import detect_needs
    from .profile import default_departures, get_roster

    players, teams = get_players(), get_teams()
    traj = player_trajectories()
    print(f"Matched {len(traj)} returning players across seasons\n")

    risers = traj[traj["traj_label"].isin(["Breakout", "Ascending"])]
    risers = risers.sort_values("traj_index", ascending=False)
    cols = ["player", "team", "yr", "bpm_prev", "bpm", "d_bpm", "d_usg",
            "d_ts", "traj_index", "traj_label"]
    print("Top risers in Division I:")
    print(risers[cols].head(12).to_string(index=False))

    # Attach to a real board and confirm it merges cleanly.
    roster = get_roster(players)
    nd = detect_needs(roster, default_departures(roster))
    board = build_board(players, teams, nd)
    board = attach_trajectory(board, traj)

    # --- assertions --------------------------------------------------------
    assert len(traj) > 500, f"too few cross-season matches: {len(traj)}"
    assert traj["traj_index"].between(0, 100).all(), "traj_index must be 0-100"
    assert set(traj["traj_label"]).issubset(
        {"Breakout", "Ascending", "Steady", "Declining"}), "unexpected label"
    assert "traj_label" in board.columns and len(board), "attach failed"
    # A pure BPM jump must read as Ascending-or-better.
    hot = traj[traj["d_bpm"] >= 3.0]
    assert (hot["traj_label"].isin(["Ascending", "Breakout"])).all(), \
        "a big BPM jump should be flagged as rising"
    print("\nSanity checks passed.")
