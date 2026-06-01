"""Build Illinois's system profile and current-roster snapshot.

These feed two things downstream: the roster-need detector (what's walking out
the door) and the Streamlit "who are we / what do we need" page.
"""
from __future__ import annotations

import pandas as pd

from .config import TEAM
from .schema import TEAM_COL  # noqa: F401  (kept for reference/readers)

# A player counts as a real rotation piece at/above this share of team minutes.
ROTATION_MIN_PCT = 25.0


def team_profile(teams: pd.DataFrame, team: str = TEAM) -> dict:
    """High-level identity card for the program (offense/defense/tempo + ranks)."""
    row = teams[teams["team"] == team]
    if row.empty:
        raise ValueError(f"{team!r} not found in team data")
    row = row.iloc[0]

    # National ranks computed within the loaded team set.
    oe_rank = int((teams["adj_oe"] > row["adj_oe"]).sum() + 1)
    de_rank = int((teams["adj_de"] < row["adj_de"]).sum() + 1)  # lower adjDE is better
    tempo_rank = int((teams["tempo"] > row["tempo"]).sum() + 1)

    return {
        "team": team,
        "conf": row["conf"],
        "record": row["record"],
        "barthag": float(row["barthag"]),
        "barthag_rank": int(row["rank"]),
        "adj_oe": float(row["adj_oe"]),
        "adj_oe_rank": oe_rank,
        "adj_de": float(row["adj_de"]),
        "adj_de_rank": de_rank,
        "tempo": float(row["tempo"]),
        "tempo_rank": tempo_rank,
        "n_teams": len(teams),
    }


def get_roster(players: pd.DataFrame, team: str = TEAM) -> pd.DataFrame:
    """Illinois players this season, sorted by minutes, with a rotation flag."""
    r = players[players["team"] == team].copy()
    r["rotation"] = r["min_pct"] >= ROTATION_MIN_PCT
    return r.sort_values("min_pct", ascending=False).reset_index(drop=True)


def default_departures(roster: pd.DataFrame) -> list[str]:
    """Default assumption: seniors graduate and leave the roster.

    Underclassmen are assumed to return; the app lets staff override this to
    reflect known portal entries, NBA declarations, or extra-eligibility cases.
    """
    return roster.loc[roster["yr"] == "Sr", "player"].tolist()


def returning_core(roster: pd.DataFrame, departures: list[str]) -> pd.DataFrame:
    return roster[~roster["player"].isin(departures)].copy()


def roster_identity(roster: pd.DataFrame) -> dict:
    """A few descriptive team rates for the profile page (rotation players only)."""
    rot = roster[roster["rotation"]]
    fga = (rot["two_pa"] + rot["three_pa"]).sum()
    three_rate = float(rot["three_pa"].sum() / fga) if fga else 0.0
    return {
        "rotation_size": int(rot.shape[0]),
        "three_pa_share": three_rate,                       # share of FGA from three
        "avg_height_in": float(rot["height_in"].mean()),
        "made_threes_pg": float((rot["three_pm"] / rot["gp"]).sum()),
    }
