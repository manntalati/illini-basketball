"""Illini Portal Fit Engine — interactive transfer-portal target board.

Run locally:  streamlit run streamlit_app.py
"""
from __future__ import annotations

import os

# Force matplotlib's headless raster backend BEFORE anything imports it, so the
# server never tries to load a macOS GUI or cairo backend (which needs native
# libcairo). We only rasterize PNGs for the scouting radar — Agg is sufficient.
os.environ["MPLBACKEND"] = "Agg"

import base64
import io

import pandas as pd
import streamlit as st

from illini_fit.config import DEFAULT_SEASON, NAVY, ORANGE, POSITION_GROUPS, TEAM_LABEL
from illini_fit.fetch import get_players, get_teams
from illini_fit.fit_score import DEFAULT_WEIGHTS, candidate_pool, score_pool
from illini_fit.needs import (
    CATEGORY_LABEL,
    STAT_CATEGORIES,
    TARGET_ROTATION,
    detect_needs,
)
from illini_fit.precedent import (
    band_sentence,
    precedent_band,
    precedents,
    up_transfer_cohort,
)
from illini_fit.profile import (
    ROTATION_MIN_PCT,
    default_departures,
    get_roster,
    returning_core,
    roster_identity,
    team_profile,
)
from illini_fit.scouting import (
    bigten_baseline,
    build_projection,
    card_html,
    card_to_pdf,
    compare_radar,
    radar_figure,
)
from illini_fit.similarity import build_reference, comps as style_comps, replacements_for
from illini_fit.trajectory import attach_trajectory, player_trajectories, trajectory_line
from illini_fit.translation import calibrate

st.set_page_config(page_title="Illini Portal Fit Engine", page_icon="🟧", layout="wide")


# --------------------------------------------------------------------------- #
# Data loading (cached)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Loading BartTorvik data…")
def load_data(season: int, _nonce: int = 0):
    return get_players(season), get_teams(season)


@st.cache_data(show_spinner="Calibrating Big Ten translation model…")
def load_model(season: int, _nonce: int = 0):
    return calibrate(illinois_season=season)


@st.cache_data(show_spinner="Building style reference…")
def load_reference(season: int, _nonce: int = 0):
    players, _ = load_data(season, _nonce)
    mu, sigma = build_reference(players)
    return mu, sigma


@st.cache_data(show_spinner="Computing multi-year trajectories…")
def load_trajectories(season: int, _nonce: int = 0):
    return player_trajectories(season)


@st.cache_data(show_spinner="Assembling historical transfer precedents…")
def load_cohort(season: int, _nonce: int = 0):
    return up_transfer_cohort(illinois_season=season)


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

tab_needs, tab_board, tab_depth, tab_compare, tab_detail = st.tabs(
    ["🟧 Program & Needs", "📋 Target Board", "🧱 Depth Chart",
     "⚔️ Compare", "🔍 Player Detail"]
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

    st.markdown("#### 🔁 Stylistic replacements for a departing player")
    if departures:
        dep_pick = st.selectbox("Find transfers who play like…", departures)
        dep_row = roster[roster["player"] == dep_pick].iloc[0]
        mu_r, sigma_r = load_reference(season, st.session_state.nonce)
        rep_pool = candidate_pool(players, teams, min_gp=min_gp,
                                  min_min_pct=min_min, include_seniors=include_sr)
        rep = replacements_for(dep_row, rep_pool, mu_r, sigma_r, n=8)
        st.caption(f"Closest stylistic matches to **{dep_pick}** "
                   f"({dep_row['role']}) in the transfer-eligible pool")
        st.dataframe(
            rep[["player", "team", "conf", "role", "yr", "similarity",
                 "pts_pg", "three_pm", "ast_pg", "bpm"]]
            .rename(columns={"similarity": "style match", "three_pm": "3PM"}),
            width="stretch", hide_index=True,
            column_config={"style match": st.column_config.ProgressColumn(
                "Style match", min_value=0, max_value=100, format="%.0f")},
        )
    else:
        st.caption("Mark a departure above to see who best replaces his style.")

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

model = load_model(season, st.session_state.nonce)
traj = load_trajectories(season, st.session_state.nonce)
board = score_pool(pool, needs, weights) if len(pool) else pool
if len(board):
    board = model.project(board)        # raw_/proj_ box line, retention, level_jump
    board = attach_trajectory(board, traj)  # d_bpm, traj_index, traj_label, *_prev

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
        st.caption(f"**Proj pts** = raw scoring translated to Illinois's level via "
                   f"{model.n_pairs} real cross-season transfers; **Keep%** is the "
                   f"share of raw scoring that survives the jump.")
        st.dataframe(
            show[["rank", "player", "team", "conf", "role", "yr", "fit_score",
                  "production", "role_fit", "system_fit", "attainability",
                  "raw_pts_pg", "proj_pts_pg", "retention", "level_jump",
                  "d_bpm", "traj_label", "attain_label", "rationale"]],
            width="stretch", hide_index=True,
            column_config={
                "fit_score": st.column_config.ProgressColumn(
                    "Fit", min_value=0, max_value=100, format="%.1f"),
                "production": st.column_config.NumberColumn("Prod", format="%.0f"),
                "role_fit": st.column_config.NumberColumn("Role", format="%.0f"),
                "system_fit": st.column_config.NumberColumn("System", format="%.0f"),
                "attainability": st.column_config.NumberColumn("Attain", format="%.0f"),
                "raw_pts_pg": st.column_config.NumberColumn("Raw pts", format="%.1f"),
                "proj_pts_pg": st.column_config.NumberColumn("Proj pts", format="%.1f"),
                "retention": st.column_config.NumberColumn("Keep%", format="%.0f"),
                "level_jump": st.column_config.TextColumn("Level jump"),
                "d_bpm": st.column_config.NumberColumn("ΔBPM", format="%+.1f",
                    help="Year-over-year BPM change vs last season (rotation players)"),
                "traj_label": st.column_config.TextColumn("Trend"),
                "rationale": st.column_config.TextColumn("Scouting note", width="large"),
            },
        )
        st.download_button("⬇️ Download board (CSV)",
                           board.to_csv(index=False).encode(),
                           file_name=f"illini_targets_{season}.csv", mime="text/csv")

        # ---- Risers: who in this pool is on the way up -------------------
        risers = board[board["traj_label"].isin(["Breakout", "Ascending"])]
        risers = risers.sort_values("traj_index", ascending=False)
        st.markdown("#### 📈 Biggest risers in the pool")
        if len(risers):
            st.caption("Candidates whose game took a real year-over-year leap "
                       "(rotation role both seasons) — value a single-season "
                       "snapshot understates. **Breakout** = bigger role *and* "
                       "held efficiency, still underclass-eligible.")
            st.dataframe(
                risers.head(15)[["player", "team", "conf", "role", "yr",
                                 "bpm_prev", "bpm", "d_bpm", "d_usg", "d_ts",
                                 "traj_label", "fit_score"]],
                width="stretch", hide_index=True,
                column_config={
                    "bpm_prev": st.column_config.NumberColumn("BPM last yr", format="%.1f"),
                    "bpm": st.column_config.NumberColumn("BPM now", format="%.1f"),
                    "d_bpm": st.column_config.NumberColumn("ΔBPM", format="%+.1f"),
                    "d_usg": st.column_config.NumberColumn("ΔUsg", format="%+.1f"),
                    "d_ts": st.column_config.NumberColumn("ΔTS%", format="%+.1f"),
                    "traj_label": st.column_config.TextColumn("Trend"),
                    "fit_score": st.column_config.NumberColumn("Fit", format="%.1f"),
                },
            )
        else:
            st.caption("No prior-season data available to compute risers for "
                       "this season (need the previous year's snapshot).")

# --------------------------------------------------------------------------- #
# Depth chart — project the post-portal roster and slot targets into holes
# --------------------------------------------------------------------------- #
with tab_depth:
    st.subheader("Projected post-portal depth chart")
    st.caption(f"Assumes the **{len(departures)}** player(s) marked leaving on the "
               f"Program & Needs tab are gone. Target rotation: "
               f"{TARGET_ROTATION['Guard']} guards · {TARGET_ROTATION['Wing']} wings "
               f"· {TARGET_ROTATION['Big']} bigs. Slot board targets into the holes.")
    ret = returning_core(roster, departures)
    gcols = st.columns(3)
    open_by, picks_by = {}, {}
    for i, g in enumerate(POSITION_GROUPS):
        with gcols[i]:
            grp = ret[ret["group"] == g].sort_values("min_pct", ascending=False)
            rot = grp[grp["min_pct"] >= ROTATION_MIN_PCT]
            open_slots = max(0, TARGET_ROTATION[g] - len(rot))
            open_by[g] = open_slots
            head = (f"**{g}** · {len(rot)}/{TARGET_ROTATION[g]} rotation "
                    + ("✅ set" if open_slots == 0 else f"🟧 {open_slots} open"))
            st.markdown(head)
            if len(grp):
                for _, p in grp.iterrows():
                    tag = "🟧" if p["min_pct"] >= ROTATION_MIN_PCT else "•"
                    st.write(f"{tag} {p['player']} · {p['yr']} · {p['min_pct']:.0f}% min")
            else:
                st.write("— no returners")
            opts = board[board["group"] == g]["player"].head(40).tolist() if len(board) else []
            picks = st.multiselect(f"Add {g} target(s)", opts, key=f"slot_{g}")
            picks_by[g] = picks
            for name in picks:
                pr = board[board["player"] == name].iloc[0]
                st.success(f"➕ {name} · {pr['team']} · Fit {pr['fit_score']:.0f} "
                           f"· proj {pr['proj_pts_pg']:.1f} pts")
    total_open = sum(open_by.values())
    filled = sum(len(v) for v in picks_by.values())
    st.divider()
    mcol = st.columns(3)
    mcol[0].metric("Open rotation spots", total_open)
    mcol[1].metric("Targets slotted", filled)
    mcol[2].metric("Holes remaining", max(0, total_open - filled),
                   delta=None if total_open == filled else f"-{max(0, total_open - filled)}")

# --------------------------------------------------------------------------- #
# Compare — head-to-head on radar shape, fit components, projected production
# --------------------------------------------------------------------------- #
with tab_compare:
    st.subheader("Head-to-head target comparison")
    st.caption("Pick 2–3 players to compare percentile shape (vs the Big Ten), "
               "Fit components, and Big Ten-projected production side by side.")
    if not len(board):
        st.info("Adjust filters to populate the board, then compare players here.")
    else:
        cmp_picks = st.multiselect("Players", board["player"].tolist(),
                                   max_selections=3, key="cmp_picks")
        if len(cmp_picks) < 2:
            st.info("Select at least two players to compare.")
        else:
            rows = [board[board["player"] == p].iloc[0] for p in cmp_picks]
            base_cmp = bigten_baseline(players)
            cc1, cc2 = st.columns([1.1, 1])
            with cc1:
                st.pyplot(compare_radar(rows, base_cmp, labels=cmp_picks))
            with cc2:
                idx = ["Fit Score", "Production", "Role fit", "System fit",
                       "Attainability", "Class", "Height", "Pts/g (raw)",
                       "Proj pts", "Keep%", "3PM/g", "3P%", "AST%", "Stl%",
                       "Blk%", "BPM"]

                def _col(r):
                    return [f"{r['fit_score']:.1f}", f"{r['production']:.0f}",
                            f"{r['role_fit']:.0f}", f"{r['system_fit']:.0f}",
                            f"{r['attainability']:.0f}", str(r["yr"]), str(r["height"]),
                            f"{r['pts_pg']:.1f}", f"{r['proj_pts_pg']:.1f}",
                            f"{r['retention']:.0f}%",
                            f"{r['three_pm'] / max(r['gp'], 1):.1f}",
                            f"{r['three_pct']:.0%}", f"{r['ast_pct']:.0f}",
                            f"{r['stl_pct']:.1f}", f"{r['blk_pct']:.1f}",
                            f"{r['bpm']:.1f}"]

                table = pd.DataFrame({p: _col(r) for p, r in zip(cmp_picks, rows)},
                                     index=idx)
                st.dataframe(table, width="stretch")
            for p, r in zip(cmp_picks, rows):
                st.markdown(f"**{p}** — {r['rationale']}")

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

        # ---- Development trajectory (multi-year, via stable pid) ----------
        tline = trajectory_line(r)
        if tline is not None:
            st.divider()
            st.markdown(f"#### 📈 Development trajectory · **{r['traj_label']}**")
            prev_team = r.get("team_prev")
            move = (f"{prev_team} → {r['team']}"
                    if pd.notna(prev_team) and prev_team != r["team"]
                    else "same program, year over year")
            st.caption(f"How his game moved last season → this season ({move}).")
            st.dataframe(tline, width="stretch", hide_index=True,
                         column_config={"Δ": st.column_config.NumberColumn(
                             "Δ", format="%+.1f")})

        # ---- Comparable past transfers (real, outcome-backed precedent) ----
        cohort = load_cohort(season, st.session_state.nonce)
        mu_p, sigma_p = load_reference(season, st.session_state.nonce)
        prec = precedents(r, cohort, mu_p, sigma_p, model.illinois_barthag, n=6)
        if len(prec):
            band = precedent_band(prec, r["pts_pg"])
            st.divider()
            st.markdown("#### 📜 Comparable past transfers — what actually happened")
            st.caption("Real players who started from a similar profile and made a "
                       "similar-size level jump. Their realized outcomes are the "
                       "empirical band behind this target's projection.")
            st.success(band_sentence(band))
            st.dataframe(
                prec.rename(columns={"from": "From", "to": "To",
                                     "from_conf": "From conf", "to_conf": "To conf",
                                     "from_pts": "Pts before", "to_pts": "Pts after",
                                     "kept_pct": "Kept%", "match": "Match"}),
                width="stretch", hide_index=True,
                column_config={
                    "gap": st.column_config.NumberColumn("Jump", format="%.2f",
                        help="Barthag distance jumped (bigger = larger level-up)"),
                    "Kept%": st.column_config.NumberColumn("Kept%", format="%.0f"),
                    "Match": st.column_config.ProgressColumn(
                        "Match", min_value=0, max_value=100, format="%.0f"),
                })

        # ---- Scouting card: radar + translation + comps + printable PDF ----
        st.divider()
        st.markdown("#### 🃏 Scouting card")
        base = bigten_baseline(players)
        mu, sigma = load_reference(season, st.session_state.nonce)

        card_l, card_r = st.columns([1, 1])
        with card_l:
            fig = radar_figure(r, base)
            st.pyplot(fig)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
            radar_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        with card_r:
            proj = build_projection(model, r)
            st.markdown(f"**Big Ten projection** · {proj['level_jump']} · "
                        f"~{proj['retention']:.0f}% of raw scoring survives")
            st.dataframe(pd.DataFrame(proj["lines"],
                                      columns=["Stat", "Raw", "At Illinois"]),
                         width="stretch", hide_index=True)

            strength = teams.set_index("team")["barthag"]
            hi = players[(players["gp"] >= 15) & (players["min_pct"] >= 40)].copy()
            hi = hi[hi["team"].map(strength).fillna(0) >= 0.80]
            cmp = style_comps(r, hi, mu, sigma, n=5, exclude_pid=r.get("pid"))
            st.caption("Plays like (high-major comps)")
            st.dataframe(cmp[["player", "team", "conf", "similarity"]]
                         .rename(columns={"similarity": "sim"}),
                         width="stretch", hide_index=True)

        card = card_html(r, base, radar_b64=radar_b64, projection=proj,
                         comps=cmp, rationale=r["rationale"])
        safe_name = pick.replace(" ", "_")
        try:
            st.download_button(
                "⬇️ Download 1-page scouting card (PDF)", card_to_pdf(card),
                file_name=f"{safe_name}_scouting_card.pdf",
                mime="application/pdf")
        except Exception:
            # Some environments lack a working reportlab raster backend
            # (e.g. a python.org build whose reportlab pulls in libcairo).
            # Fall back to a self-contained HTML card the staff can open
            # in any browser and print to PDF — the app never crashes.
            st.download_button(
                "⬇️ Download 1-page scouting card (HTML)", card.encode("utf-8"),
                file_name=f"{safe_name}_scouting_card.html",
                mime="text/html")
            st.caption("PDF export is unavailable in this environment — "
                       "open the HTML card in a browser and print to PDF.")

st.caption("Data: BartTorvik (public). Fit Score is a transparent weighted blend of "
           "production, positional fit, system fit, and attainability — all tunable above.")
