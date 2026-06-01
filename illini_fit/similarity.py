"""Player comp / similarity engine — "who plays like this guy?"

Two questions a staff asks constantly during portal season:

  1. *Stylistic replacement* — a rotation piece is leaving; which available
     transfers play the same role the same way?
  2. *Comp* — we like this target; who does he remind us of (ideally a name we
     already know) so we can frame him quickly?

Both reduce to nearest-neighbours in a normalised **style space**: each player
is a vector of role/skill rates (usage, shot diet, playmaking, rebounding,
defense, size, efficiency), z-scored against a Division-I rotation baseline so
every axis is on the same scale. Distance is plain Euclidean — fully
transparent, no learned weights — and reported as a 0-100 similarity.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Style axes. These describe HOW a player plays, not just how good he is, so the
# nearest neighbour is a stylistic match rather than merely a similar-rated guy.
STYLE_FEATURES = [
    "usg",          # how much of the offense runs through him
    "three_rate",   # share of his shots from three (derived below)
    "three_pct",    # outside touch
    "ast_pct",      # playmaking load
    "to_pct",       # ball security
    "orb_pct",      # offensive glass
    "drb_pct",      # defensive glass
    "blk_pct",      # rim protection
    "stl_pct",      # perimeter disruption
    "ftr",          # rim pressure / physicality
    "ts",           # scoring efficiency
    "height_in",    # size
]

# Distance at which two players are deemed "average-unrelated" — used to map a
# raw Euclidean distance onto a friendly 0-100 similarity. sqrt(2*k) is the
# expected distance between two independent standard-normal k-vectors.
_REF_DIST = float(np.sqrt(2 * len(STYLE_FEATURES)))


def _with_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    fga = (out["two_pa"] + out["three_pa"]).clip(lower=1)
    out["three_rate"] = (out["three_pa"] / fga).astype(float)
    return out


def build_reference(players: pd.DataFrame, min_gp: int = 15,
                    min_min_pct: float = 40.0) -> tuple[pd.Series, pd.Series]:
    """Mean/std of each style axis over the D-I rotation baseline."""
    ref = _with_features(players)
    ref = ref[(ref["gp"] >= min_gp) & (ref["min_pct"] >= min_min_pct)]
    mu = ref[STYLE_FEATURES].mean()
    sigma = ref[STYLE_FEATURES].std(ddof=0).replace(0, 1.0)
    return mu, sigma


def _zmatrix(df: pd.DataFrame, mu: pd.Series, sigma: pd.Series) -> np.ndarray:
    """Z-scored style matrix; missing values fall back to the mean (z=0)."""
    feats = _with_features(df)[STYLE_FEATURES]
    z = (feats - mu) / sigma
    return z.fillna(0.0).to_numpy()


def _similarity(dist: np.ndarray) -> np.ndarray:
    return np.round(100.0 * np.exp(-dist / _REF_DIST), 1)


def comps(query: pd.Series, search: pd.DataFrame, mu: pd.Series, sigma: pd.Series,
          n: int = 5, exclude_pid=None) -> pd.DataFrame:
    """The ``n`` players in ``search`` whose style is closest to ``query``."""
    q = _zmatrix(pd.DataFrame([query]), mu, sigma)[0]
    pool = search
    if exclude_pid is not None:
        pool = pool[pool["pid"] != exclude_pid]
    mat = _zmatrix(pool, mu, sigma)
    dist = np.linalg.norm(mat - q, axis=1)
    out = pool.copy()
    out["similarity"] = _similarity(dist)
    out["style_distance"] = np.round(dist, 2)
    return out.sort_values("similarity", ascending=False).head(n).reset_index(drop=True)


def replacements_for(departed: pd.Series, candidate_pool: pd.DataFrame,
                     mu: pd.Series, sigma: pd.Series, n: int = 8,
                     same_group: bool = True) -> pd.DataFrame:
    """Transfer-eligible candidates who most resemble a departing player's style."""
    search = candidate_pool
    if same_group and pd.notna(departed.get("group")):
        same = candidate_pool[candidate_pool["group"] == departed["group"]]
        if len(same) >= n:
            search = same
    return comps(departed, search, mu, sigma, n=n, exclude_pid=departed.get("pid"))


def comp_names(query: pd.Series, search: pd.DataFrame, mu: pd.Series,
               sigma: pd.Series, n: int = 3) -> str:
    """Short 'plays like X, Y, Z' string for a scouting note."""
    c = comps(query, search, mu, sigma, n=n, exclude_pid=query.get("pid"))
    return ", ".join(f"{r['player']} ({r['team']})" for _, r in c.iterrows())


if __name__ == "__main__":
    from .fetch import get_players, get_teams
    from .fit_score import candidate_pool
    from .profile import get_roster

    players, teams = get_players(), get_teams()
    mu, sigma = build_reference(players)
    pool = candidate_pool(players, teams)
    roster = get_roster(players)

    # 1) Stylistic replacements for Illinois's top minutes-getter.
    leader = roster.iloc[0]
    print(f"Style replacements for {leader['player']} "
          f"({leader['role']}, {leader['min_pct']:.0f}% min):\n")
    rep = replacements_for(leader, pool, mu, sigma, n=6)
    print(rep[["player", "team", "conf", "role", "similarity",
               "pts_pg", "three_pm", "ast_pg", "bpm"]].to_string(index=False))

    # 2) Comps for a candidate, drawn from high-major rotation names.
    hi = _with_features(players)
    hi = hi[(hi["gp"] >= 15) & (hi["min_pct"] >= 40)]
    strength = teams.set_index("team")["barthag"]
    hi = hi[hi["team"].map(strength).fillna(0) >= 0.80]
    tgt = pool.sort_values("bpm", ascending=False).iloc[0]
    print(f"\n{tgt['player']} ({tgt['team']}) plays like: "
          f"{comp_names(tgt, hi, mu, sigma, n=3)}")

    # --- assertions --------------------------------------------------------
    self_match = comps(leader, roster, mu, sigma, n=1, exclude_pid=None)
    assert self_match.iloc[0]["player"] == leader["player"], \
        "a player must be his own closest comp"
    assert rep["similarity"].is_monotonic_decreasing, "comps must be sorted"
    assert rep["similarity"].between(0, 100).all(), "similarity must be 0-100"
    print("\nSanity checks passed.")
