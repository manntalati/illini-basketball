"""BartTorvik data schemas + typed loaders.

The player CSV (getadvstats.php) ships with NO header row, so we assign column
names by position. The mapping below was reverse-engineered and *validated*
against the data itself:

  * shooting splits reconcile (e.g. FTM / FTA == FT%),
  * BPM == OBPM + DBPM holds for 100% of rows (cols 50/51/52),
  * total rebounds == off + def per game (cols 59 == 57 + 58).

Columns we could not verify are named ``extra_NN`` and are intentionally unused
by the model, so every number the tool reports is one we can explain.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd

from .config import ROLE_TO_GROUP

# 67 columns, index-aligned to getadvstats.php?csv=1 output.
PLAYER_COLUMNS = [
    "player",       # 0
    "team",         # 1
    "conf",         # 2
    "gp",           # 3  games played
    "min_pct",      # 4  % of team minutes played
    "ortg",         # 5  offensive rating
    "usg",          # 6  usage %
    "efg",          # 7  effective FG %
    "ts",           # 8  true shooting %
    "orb_pct",      # 9
    "drb_pct",      # 10
    "ast_pct",      # 11
    "to_pct",       # 12 turnover %
    "ftm",          # 13
    "fta",          # 14
    "ft_pct",       # 15
    "two_pm",       # 16
    "two_pa",       # 17
    "two_pct",      # 18
    "three_pm",     # 19
    "three_pa",     # 20
    "three_pct",    # 21
    "blk_pct",      # 22
    "stl_pct",      # 23
    "ftr",          # 24 free throw rate (FTA/FGA, %)
    "yr",           # 25 class (Fr/So/Jr/Sr)
    "height",       # 26 e.g. "6-2"
    "num",          # 27 jersey number
    "porpag",       # 28 points over replacement per adjusted game
    "extra_29",     # 29 (unverified)
    "extra_30",     # 30 (unverified)
    "season",       # 31 ending year of the season
    "pid",          # 32 BartTorvik player id
    "hometown",     # 33
    "rec_rank",     # 34 recruiting rank/rating (sparse)
    "extra_35",     # 35 (unverified)
    "rim_made",     # 36 shots at the rim made
    "rim_att",      # 37 shots at the rim attempted
    "mid_made",     # 38 mid-range made
    "mid_att",      # 39 mid-range attempted
    "rim_pct",      # 40
    "mid_pct",      # 41
    "dunk_made",    # 42
    "dunk_att",     # 43
    "dunk_pct",     # 44
    "extra_45",     # 45 (unverified)
    "adj_oe",       # 46 player adjusted offensive rating
    "adj_de",       # 47 player adjusted defensive rating (lower = better)
    "extra_48",     # 48 (unverified)
    "extra_49",     # 49 (unverified)
    "bpm",          # 50 box plus/minus  (== obpm + dbpm)
    "obpm",         # 51 offensive BPM
    "dbpm",         # 52 defensive BPM
    "gbpm",         # 53 Torvik BPM variant (== ogbpm + dgbpm)
    "extra_54",     # 54 (unverified)
    "ogbpm",        # 55
    "dgbpm",        # 56
    "orb_pg",       # 57 offensive rebounds per game
    "drb_pg",       # 58 defensive rebounds per game
    "trb_pg",       # 59 total rebounds per game
    "ast_pg",       # 60 assists per game
    "stl_pg",       # 61 steals per game
    "blk_pg",       # 62 blocks per game
    "pts_pg",       # 63 points per game
    "role",         # 64 archetype label
    "extra_65",     # 65 (unverified)
    "birthdate",    # 66 YYYY-MM-DD
]

# Team results JSON (2026_team_results.json) is a list of lists; we only need
# a handful of columns, indexed below.
TEAM_COL = {
    "rank": 0,
    "team": 1,
    "conf": 2,
    "record": 3,
    "adj_oe": 4,
    "adj_de": 6,
    "barthag": 8,      # 0-1 power rating
    "wins": 10,
    "losses": 11,
    "tempo": 44,       # adjusted possessions / game
}


def _height_to_inches(h) -> float:
    if not isinstance(h, str) or "-" not in h:
        return np.nan
    feet, _, inches = h.partition("-")
    try:
        return int(feet) * 12 + int(inches)
    except ValueError:
        return np.nan


def _age_on(birthdate, ref: _dt.date) -> float:
    if not isinstance(birthdate, str):
        return np.nan
    try:
        b = _dt.date.fromisoformat(birthdate)
    except ValueError:
        return np.nan
    return round((ref - b).days / 365.25, 1)


def load_players(path: str, ref_date: _dt.date | None = None) -> pd.DataFrame:
    """Load a getadvstats CSV into a typed DataFrame with a few derived columns."""
    df = pd.read_csv(path, header=None, names=PLAYER_COLUMNS)
    df = df[df["player"].notna()].copy()

    # Derived, model-friendly columns.
    df["group"] = df["role"].map(ROLE_TO_GROUP)
    df["height_in"] = df["height"].map(_height_to_inches)
    ref = ref_date or _dt.date.today()
    df["age"] = df["birthdate"].map(lambda b: _age_on(b, ref))

    # Three-point volume per game (a system-fit signal Illinois cares about).
    df["three_pa_pg"] = np.where(df["gp"] > 0, df["three_pa"] / df["gp"], 0.0)
    return df


def load_teams(path: str) -> pd.DataFrame:
    """Load team_results JSON into a tidy per-team DataFrame."""
    raw = pd.read_json(path)
    out = pd.DataFrame({name: raw[idx] for name, idx in TEAM_COL.items()})
    return out
