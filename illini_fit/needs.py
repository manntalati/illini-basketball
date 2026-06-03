"""Detect Illinois's roster needs from who is leaving.

Two kinds of need are produced, both in an easy-to-explain 0-1 scale:

  * ``position_need``: are we short bodies at Guard / Wing / Big in the rotation?
  * ``stat_priority``: what *share of last year's production* (threes, assists,
    blocks, rebounds, steals, points) is walking out the door?

Everything is derived from the data; the app lets staff override any weight or
the list of departures before scoring.
"""
from __future__ import annotations

import pandas as pd

from .config import POSITION_GROUPS
from .profile import ROTATION_MIN_PCT, returning_core

# Target rotation composition for an Illinois-style 9-man rotation.
TARGET_ROTATION = {"Guard": 4, "Wing": 2, "Big": 3}

# Category -> a function giving each player's SEASON-TOTAL contribution.
# Counting totals make "fraction leaving" interpretable as plain English.
STAT_CATEGORIES: dict[str, callable] = {
    "shooting": lambda d: d["three_pm"],
    "playmaking": lambda d: d["ast_pg"] * d["gp"],
    "rim_protection": lambda d: d["blk_pg"] * d["gp"],
    "rebounding": lambda d: d["trb_pg"] * d["gp"],
    "perimeter_defense": lambda d: d["stl_pg"] * d["gp"],
    "scoring": lambda d: d["pts_pg"] * d["gp"],
}

CATEGORY_LABEL = {
    "shooting": "outside shooting",
    "playmaking": "playmaking",
    "rim_protection": "rim protection",
    "rebounding": "rebounding",
    "perimeter_defense": "perimeter defense",
    "scoring": "scoring",
}


def _position_need(roster: pd.DataFrame, departures: list[str]) -> dict[str, float]:
    ret = returning_core(roster, departures)
    rot = ret[ret["min_pct"] >= ROTATION_MIN_PCT]
    counts = rot["group"].value_counts().to_dict()
    need = {}
    for g in POSITION_GROUPS:
        gap = max(0, TARGET_ROTATION[g] - int(counts.get(g, 0)))
        need[g] = round(gap / TARGET_ROTATION[g], 3)
    return need


def _stat_priority(roster: pd.DataFrame, departures: list[str]) -> dict[str, float]:
    leaving = roster["player"].isin(departures)
    priority = {}
    for cat, fn in STAT_CATEGORIES.items():
        totals = fn(roster)
        whole = float(totals.sum())
        gone = float(totals[leaving].sum())
        priority[cat] = round(gone / whole, 3) if whole > 0 else 0.0
    return priority


def detect_needs(roster: pd.DataFrame, departures: list[str]) -> dict:
    position_need = _position_need(roster, departures)
    stat_priority = _stat_priority(roster, departures)

    # Human-readable headline: most depleted position + top two stat gaps.
    top_pos = max(position_need, key=position_need.get)
    top_stats = sorted(stat_priority, key=stat_priority.get, reverse=True)[:2]
    headline_parts = []
    if position_need[top_pos] > 0:
        headline_parts.append(f"another {top_pos.lower()}")
    headline_parts += [CATEGORY_LABEL[c] for c in top_stats if stat_priority[c] > 0.15]

    return {
        "departures": list(departures),
        "position_need": position_need,
        "stat_priority": stat_priority,
        "headline": "Replace " + ", ".join(headline_parts) if headline_parts else
                    "Roster is largely intact",
    }
