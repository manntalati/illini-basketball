"""Illini Portal Fit Engine — interactive transfer-portal target board.

Run locally:  streamlit run streamlit_app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from illini_fit.config import DEFAULT_SEASON, NAVY, ORANGE, POSITION_GROUPS, TEAM_LABEL
from illini_fit.fetch import get_players, get_teams
from illini_fit.fit_score import DEFAULT_WEIGHTS, candidate_pool, score_pool
from illini_fit.needs import CATEGORY_LABEL, STAT_CATEGORIES, detect_needs
from illini_fit.profile import (
    default_departures,
    get_roster,
    roster_identity,
    team_profile,
)

st.set_page_config(page_title="Illini Portal Fit Engine", page_icon="🟧", layout="wide")


# --------------------------------------------------------------------------- #
# Data loading (cached)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Loading BartTorvik data…")
def load_data(season: int, _nonce: int = 0):
    return get_players(season), get_teams(season)


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.markdown(
    f"""
    <div style="background:{NAVY};padding:18px 24px;border-radius:10px;
                border-left:10px solid {ORANGE};margin-bottom:8px;">
      <span style="color:white;font-size:30px;font-weight:800;">Illini Portal Fit Engine</span><br>
      <span style="color:#cfd6e4;font-size:15px;">
        A data-driven transfer-portal target board for {TEAM_LABEL} · powered by public BartTorvik data
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Sidebar — data + filters + weights
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Controls")
    season = st.selectbox("Season (ending year)", [2026, 2025, 2024], index=0)
    if "nonce" not in st.session_state:
        st.session_state.nonce = 0
    if st.button("🔄 Refresh from BartTorvik"):
        st.session_state.nonce += 1
        st.cache_data.clear()

    players, teams = load_data(season, st.session_state.nonce)

    st.subheader("Candidate pool")
    min_gp = st.slider("Min games played", 5, 35, 20)
    min_min = st.slider("Min % of team minutes", 10, 80, 40)
    include_sr = st.checkbox("Include seniors (extra eligibility)", value=False)
    groups_sel = st.multiselect("Positions", POSITION_GROUPS, default=POSITION_GROUPS)
    classes_sel = st.multiselect("Classes", ["Fr", "So", "Jr", "Sr"],
                                 default=["Fr", "So", "Jr"])
    conf_options = sorted(players["conf"].dropna().unique().tolist())
    conf_sel = st.multiselect("Conferences (blank = all)", conf_options, default=[])

    st.subheader("Fit Score weights")
    w_prod = st.slider("Production", 0.0, 1.0, DEFAULT_WEIGHTS["production"], 0.05)
    w_role = st.slider("Role fit", 0.0, 1.0, DEFAULT_WEIGHTS["role"], 0.05)
    w_sys = st.slider("System fit", 0.0, 1.0, DEFAULT_WEIGHTS["system"], 0.05)
    w_att = st.slider("Attainability", 0.0, 1.0, DEFAULT_WEIGHTS["attainability"], 0.05)
    _wt = (w_prod + w_role + w_sys + w_att) or 1.0
    weights = {"production": w_prod / _wt, "role": w_role / _wt,
               "system": w_sys / _wt, "attainability": w_att / _wt}

# --------------------------------------------------------------------------- #
# Program + needs
# --------------------------------------------------------------------------- #
tp = team_profile(teams)
roster = get_roster(players)
ident = roster_identity(roster)

tab_needs, tab_board, tab_detail = st.tabs(
    ["🟧 Program & Needs", "📋 Target Board", "🔍 Player Detail"]
)

with tab_needs:
    st.subheader(f"{tp['team']} — {tp['conf']} · {tp['record']}")
    c = st.columns(5)
    c[0].metric("Barthag", f"#{tp['barthag_rank']}", f"{tp['barthag']:.3f}")
    c[1].metric("Adj. Offense", f"#{tp['adj_oe_rank']}", f"{tp['adj_oe']:.1f}")
    c[2].metric("Adj. Defense", f"#{tp['adj_de_rank']}", f"{tp['adj_de']:.1f}")
    c[3].metric("Tempo", f"#{tp['tempo_rank']}", f"{tp['tempo']:.1f} poss")
    c[4].metric("3PA share of FGA", f"{ident['three_pa_share']:.0%}",
                f"{ident['made_threes_pg']:.1f} 3PM/g")

    st.markdown("#### Roster — mark who is **leaving** (default: seniors graduate)")
    departures = st.multiselect(
        "Departures",
        roster["player"].tolist(),
        default=default_departures(roster),
        help="Add known portal entries / NBA declarations; remove anyone with an extra year.",
    )
    roster_view = roster.assign(leaving=roster["player"].isin(departures))
    st.dataframe(
        roster_view[["player", "role", "group", "yr", "min_pct", "usg",
                     "three_pm", "three_pct", "ast_pg", "blk_pct", "bpm", "leaving"]]
        .rename(columns={"min_pct": "min%", "three_pm": "3PM", "three_pct": "3P%",
                         "ast_pg": "ast/g", "blk_pct": "blk%"}),
        width="stretch", hide_index=True,
    )

    needs = detect_needs(roster, departures)
    st.markdown(f"#### Detected needs · **{needs['headline']}**")
    nc = st.columns(2)
    nc[0].caption("Positional need (share of rotation spots open)")
    nc[0].bar_chart(pd.Series(needs["position_need"]), color=ORANGE, horizontal=True)
    nc[1].caption("Production walking out the door (share of last year's total)")
    sp_named = {CATEGORY_LABEL[k]: v for k, v in needs["stat_priority"].items()}
    nc[1].bar_chart(pd.Series(sp_named), color=ORANGE, horizontal=True)

    with st.expander("✏️ Fine-tune needs (optional — overrides the auto-detected values)"):
        pn = {}
        st.caption("Positional need weights")
        pcols = st.columns(len(POSITION_GROUPS))
        for i, g in enumerate(POSITION_GROUPS):
            pn[g] = pcols[i].slider(g, 0.0, 1.0, float(needs["position_need"][g]), 0.05,
                                    key=f"pn_{g}")
        sp = {}
        st.caption("Stat-priority weights")
        scols = st.columns(3)
        for i, cat in enumerate(STAT_CATEGORIES):
            sp[cat] = scols[i % 3].slider(
                CATEGORY_LABEL[cat], 0.0, 1.0, float(needs["stat_priority"][cat]), 0.05,
                key=f"sp_{cat}")
        needs = {**needs, "position_need": pn, "stat_priority": sp}

# --------------------------------------------------------------------------- #
# Build + score board
# --------------------------------------------------------------------------- #
pool = candidate_pool(players, teams, min_gp=min_gp, min_min_pct=min_min,
                      include_seniors=include_sr)
if groups_sel:
    pool = pool[pool["group"].isin(groups_sel)]
if classes_sel:
    pool = pool[pool["yr"].isin(classes_sel)]
if conf_sel:
    pool = pool[pool["conf"].isin(conf_sel)]
pool = pool.reset_index(drop=True)

board = score_pool(pool, needs, weights) if len(pool) else pool

with tab_board:
    if not len(board):
        st.warning("No candidates match the current filters.")
    else:
        st.subheader(f"Top transfer targets for {tp['team']}  ·  {len(board)} in pool")
        st.caption(f"Needs: **{needs['headline']}**  ·  weights — "
                   f"production {weights['production']:.0%}, role {weights['role']:.0%}, "
                   f"system {weights['system']:.0%}, attainability {weights['attainability']:.0%}")
        top_n = st.slider("Show top N", 10, 100, 25)
        show = board.head(top_n).copy()
        show.insert(0, "rank", range(1, len(show) + 1))
        st.dataframe(
            show[["rank", "player", "team", "conf", "role", "yr", "fit_score",
                  "production", "role_fit", "system_fit", "attainability",
                  "attain_label", "rationale"]],
            width="stretch", hide_index=True,
            column_config={
                "fit_score": st.column_config.ProgressColumn(
                    "Fit", min_value=0, max_value=100, format="%.1f"),
                "production": st.column_config.NumberColumn("Prod", format="%.0f"),
                "role_fit": st.column_config.NumberColumn("Role", format="%.0f"),
                "system_fit": st.column_config.NumberColumn("System", format="%.0f"),
                "attainability": st.column_config.NumberColumn("Attain", format="%.0f"),
                "rationale": st.column_config.TextColumn("Scouting note", width="large"),
            },
        )
        st.download_button("⬇️ Download board (CSV)",
                           board.to_csv(index=False).encode(),
                           file_name=f"illini_targets_{season}.csv", mime="text/csv")

with tab_detail:
    if not len(board):
        st.info("Adjust filters to populate the board, then inspect a player here.")
    else:
        pick = st.selectbox("Player", board["player"].tolist())
        r = board[board["player"] == pick].iloc[0]
        st.subheader(f"{r['player']} — {r['role']} · {r['team']} ({r['conf']})")
        st.markdown(f"> {r['rationale']}")
        m = st.columns(5)
        m[0].metric("Fit Score", f"{r['fit_score']:.1f}")
        m[1].metric("Production", f"{r['production']:.0f}")
        m[2].metric("Role fit", f"{r['role_fit']:.0f}")
        m[3].metric("System fit", f"{r['system_fit']:.0f}")
        m[4].metric("Attainability", f"{r['attainability']:.0f}", r["attain_label"])

        left, right = st.columns(2)
        left.caption("Fit Score components")
        left.bar_chart(
            pd.Series({"Production": r["production"], "Role fit": r["role_fit"],
                       "System fit": r["system_fit"], "Attainability": r["attainability"]}),
            color=ORANGE, horizontal=True,
        )
        right.caption("Profile")
        age_str = f"{r['age']:.1f}" if pd.notna(r.get("age")) else "—"
        right.dataframe(pd.DataFrame({
            "stat": ["Class", "Height", "Age", "Min%", "Usage", "BPM", "porpag",
                     "3PM/g", "3P%", "AST%", "TO%", "Blk%", "Stl%", "TS%", "Pts/g"],
            "value": [str(r["yr"]), str(r["height"]), age_str, f"{r['min_pct']:.1f}",
                      f"{r['usg']:.1f}", f"{r['bpm']:.1f}", f"{r['porpag']:.2f}",
                      f"{r['three_pm'] / max(r['gp'], 1):.1f}", f"{r['three_pct']:.0%}",
                      f"{r['ast_pct']:.0f}", f"{r['to_pct']:.0f}", f"{r['blk_pct']:.1f}",
                      f"{r['stl_pct']:.1f}", f"{r['ts']:.1f}%", f"{r['pts_pg']:.1f}"],
        }), width="stretch", hide_index=True)

st.caption("Data: BartTorvik (public). Fit Score is a transparent weighted blend of "
           "production, positional fit, system fit, and attainability — all tunable above.")
