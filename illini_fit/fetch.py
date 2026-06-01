"""Fetch + cache public BartTorvik data.

Design goal: the app must work for a reviewer with zero setup. So we ship a
committed snapshot under ``data/raw/`` and only hit the network when a snapshot
is missing or an explicit refresh is requested. Either way the data is real
BartTorvik data — nothing is synthetic.
"""
from __future__ import annotations

import os

import pandas as pd
import requests

from .config import DEFAULT_SEASON, PLAYERS_URL, RAW_DIR, TEAMS_URL
from .schema import load_players, load_teams

_HEADERS = {"User-Agent": "illini-portal-fit/1.0 (analytics take-home)"}
_TIMEOUT = 30


def players_snapshot(year: int) -> str:
    return os.path.join(RAW_DIR, f"players_{year}.csv")


def teams_snapshot(year: int) -> str:
    return os.path.join(RAW_DIR, f"teams_{year}.json")


def _download(url: str, dest: str) -> str:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(resp.text)
    return dest


def refresh(year: int = DEFAULT_SEASON) -> tuple[str, str]:
    """Force a fresh download of both datasets for ``year``."""
    p = _download(PLAYERS_URL.format(year=year), players_snapshot(year))
    t = _download(TEAMS_URL.format(year=year), teams_snapshot(year))
    return p, t


def get_players(year: int = DEFAULT_SEASON, force: bool = False) -> pd.DataFrame:
    path = players_snapshot(year)
    if force or not os.path.exists(path):
        _download(PLAYERS_URL.format(year=year), path)
    return load_players(path)


def get_teams(year: int = DEFAULT_SEASON, force: bool = False) -> pd.DataFrame:
    path = teams_snapshot(year)
    if force or not os.path.exists(path):
        _download(TEAMS_URL.format(year=year), path)
    return load_teams(path)


if __name__ == "__main__":
    # Smoke test: refresh the default season and validate the load.
    from .config import TEAM

    refresh(DEFAULT_SEASON)
    players = get_players(DEFAULT_SEASON)
    teams = get_teams(DEFAULT_SEASON)

    assert len(players) > 4000, f"too few players: {len(players)}"
    assert len(teams) > 300, f"too few teams: {len(teams)}"
    illini = players[players["team"] == TEAM]
    assert not illini.empty, "no Illinois players parsed"
    assert players["bpm"].notna().mean() > 0.95, "BPM column looks wrong"

    print(f"OK  players={len(players)}  teams={len(teams)}  "
          f"Illinois players={len(illini)}")
    print("Illinois sample:",
          ", ".join(illini.sort_values("min_pct", ascending=False)["player"].head(5)))
