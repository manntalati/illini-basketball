"""Project-wide constants: team identity, data locations, role taxonomy.

Single source of truth so the data layer, model, and Streamlit app stay in sync.
"""
from __future__ import annotations

import os

# --- Paths -----------------------------------------------------------------
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(PKG_DIR)
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")

# --- Target program --------------------------------------------------------
TEAM = "Illinois"            # BartTorvik team name for the Fighting Illini
TEAM_LABEL = "Illinois Fighting Illini"
DEFAULT_SEASON = 2026        # BartTorvik labels seasons by their ending year (2025-26 -> 2026)

# Illini brand colors (for the UI).
ORANGE = "#E84A27"
NAVY = "#13294B"

# --- BartTorvik endpoints (public, no auth) --------------------------------
PLAYERS_URL = "https://barttorvik.com/getadvstats.php?year={year}&csv=1"
TEAMS_URL = "https://barttorvik.com/{year}_team_results.json"

# --- Role taxonomy ---------------------------------------------------------
# BartTorvik assigns each player one of eight archetype "roles". We group them
# into three position buckets for roster-construction logic.
GUARD_ROLES = ["Pure PG", "Scoring PG", "Combo G", "Wing G"]
WING_ROLES = ["Wing F"]
BIG_ROLES = ["Stretch 4", "PF/C", "C"]

ROLE_TO_GROUP = {r: "Guard" for r in GUARD_ROLES}
ROLE_TO_GROUP.update({r: "Wing" for r in WING_ROLES})
ROLE_TO_GROUP.update({r: "Big" for r in BIG_ROLES})

POSITION_GROUPS = ["Guard", "Wing", "Big"]

# Roles that primarily handle the ball / create offense (used for need logic).
PRIMARY_HANDLER_ROLES = ["Pure PG", "Scoring PG", "Combo G"]
