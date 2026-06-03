"""Visual scouting cards: a one-page, printable read on any target.

A coach does not read a 60-column CSV; he reads a card. Each card answers, at a
glance:

  * Shape: a percentile radar vs the Big Ten rotation baseline, so every spoke
    is "how would this skill rank in our league?"
  * Translation: the raw box line next to its projection at Illinois's level
    (from :mod:`illini_fit.translation`), so gaudy low-major numbers are honest.
  * Shot diet: where his shots come from (rim / mid / three) and how they fall.
  * Comps: the players he most resembles (from :mod:`illini_fit.similarity`).

The radar is matplotlib (shown in the app) and the whole card renders to a
self-contained one-page PDF via xhtml2pdf, so coaches can print the board.
"""
from __future__ import annotations

import base64
import io
import os

# Pin the headless raster backend before matplotlib is imported anywhere. The
# default on macOS is the GUI "macosx" backend (unsafe off the main thread) and
# some setups default to a cairo backend that needs native libcairo. We only
# need to rasterize a PNG, so Agg is correct and dependency-free.
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import pandas as pd

from .config import NAVY, ORANGE

# (column, label) for the radar spokes. Percentile is rank within the baseline,
# so the differing column scales (rates vs per-game) do not matter.
RADAR_METRICS = [
    ("usg", "Usage"),
    ("pts_pg", "Scoring"),
    ("three_rate", "3PT volume"),
    ("three_pct", "3PT touch"),
    ("ast_pct", "Playmaking"),
    ("trb_pg", "Rebounding"),
    ("blk_pct", "Rim protect"),
    ("stl_pct", "Perimeter D"),
]


def _with_three_rate(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    fga = (out["two_pa"] + out["three_pa"]).clip(lower=1)
    out["three_rate"] = out["three_pa"] / fga
    return out


def bigten_baseline(players: pd.DataFrame, conf: str = "B10",
                    min_gp: int = 10, min_min_pct: float = 25.0) -> pd.DataFrame:
    b = _with_three_rate(players)
    return b[(b["conf"] == conf) & (b["gp"] >= min_gp) & (b["min_pct"] >= min_min_pct)]


def percentiles_vs_baseline(player: pd.Series, baseline: pd.DataFrame) -> dict[str, float]:
    p = _with_three_rate(pd.DataFrame([player])).iloc[0]
    out = {}
    for col, _ in RADAR_METRICS:
        vals = baseline[col].dropna()
        v = p.get(col)
        out[col] = float((vals < v).mean() * 100) if len(vals) and pd.notna(v) else 0.0
    return out


def shot_profile(player: pd.Series) -> dict:
    rim, mid, three = (float(player.get("rim_att", 0) or 0),
                       float(player.get("mid_att", 0) or 0),
                       float(player.get("three_pa", 0) or 0))
    tot = rim + mid + three or 1.0
    return {
        "rim_share": rim / tot, "mid_share": mid / tot, "three_share": three / tot,
        "rim_pct": float(player.get("rim_pct", np.nan)),
        "mid_pct": float(player.get("mid_pct", np.nan)),
        "three_pct": float(player.get("three_pct", np.nan)),
    }


# --------------------------------------------------------------------------- #
# Radar figure
# --------------------------------------------------------------------------- #
def radar_figure(player: pd.Series, baseline: pd.DataFrame):
    """Percentile radar (vs Big Ten baseline) as a matplotlib Figure."""
    import matplotlib
    matplotlib.use("Agg", force=True)  # belt-and-suspenders: never touch GUI/cairo
    import matplotlib.pyplot as plt

    pcts = percentiles_vs_baseline(player, baseline)
    labels = [lab for _, lab in RADAR_METRICS]
    vals = [pcts[col] for col, _ in RADAR_METRICS]

    ang = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    vals_c, ang_c = vals + vals[:1], ang + ang[:1]

    fig, ax = plt.subplots(figsize=(4.6, 4.6), subplot_kw={"polar": True})
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(ang)
    ax.set_xticklabels(labels, fontsize=9, color=NAVY)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75])
    ax.set_yticklabels(["25", "50", "75"], fontsize=7, color="#9aa3b2")
    ax.plot(ang_c, vals_c, color=ORANGE, linewidth=2)
    ax.fill(ang_c, vals_c, color=ORANGE, alpha=0.25)
    ax.spines["polar"].set_color("#d6dbe4")
    ax.set_title(f"{player['player']}: percentile vs Big Ten",
                 color=NAVY, fontsize=11, fontweight="bold", pad=16)
    fig.tight_layout()
    return fig


def compare_radar(players: list, baseline: pd.DataFrame, labels: list | None = None):
    """Overlay 2-3 players' percentile radars on one axis for head-to-head."""
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    colors = [ORANGE, NAVY, "#2E8B57"]
    labels = labels or [p["player"] for p in players]
    spoke_labels = [lab for _, lab in RADAR_METRICS]
    ang = np.linspace(0, 2 * np.pi, len(spoke_labels), endpoint=False).tolist()
    ang_c = ang + ang[:1]

    fig, ax = plt.subplots(figsize=(5.2, 5.2), subplot_kw={"polar": True})
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(ang)
    ax.set_xticklabels(spoke_labels, fontsize=9, color=NAVY)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75])
    ax.set_yticklabels(["25", "50", "75"], fontsize=7, color="#9aa3b2")
    for p, c, lab in zip(players, colors, labels):
        pcts = percentiles_vs_baseline(p, baseline)
        vals = [pcts[col] for col, _ in RADAR_METRICS]
        vals_c = vals + vals[:1]
        ax.plot(ang_c, vals_c, color=c, linewidth=2, label=lab)
        ax.fill(ang_c, vals_c, color=c, alpha=0.12)
    ax.spines["polar"].set_color("#d6dbe4")
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.12), fontsize=8, frameon=False)
    ax.set_title("Percentile vs Big Ten", color=NAVY, fontsize=11,
                 fontweight="bold", pad=16)
    fig.tight_layout()
    return fig


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


# --------------------------------------------------------------------------- #
# HTML / PDF card
# --------------------------------------------------------------------------- #
def _fmt(v, spec="{:.1f}"):
    return spec.format(v) if pd.notna(v) else "-"


def card_html(player: pd.Series, baseline: pd.DataFrame, *,
              radar_b64: str | None = None, projection: dict | None = None,
              comps: pd.DataFrame | None = None, rationale: str | None = None) -> str:
    """Self-contained HTML for a one-page scouting card."""
    sp = shot_profile(player)
    radar_b64 = radar_b64 if radar_b64 is not None else _fig_to_b64(
        radar_figure(player, baseline))

    proj_rows = ""
    if projection:
        for raw, prj, lab in projection["lines"]:
            proj_rows += (f"<tr><td>{lab}</td><td style='text-align:right'>{raw}</td>"
                          f"<td style='text-align:right;color:{ORANGE};font-weight:700'>"
                          f"{prj}</td></tr>")
    comp_rows = ""
    if comps is not None and len(comps):
        for _, c in comps.iterrows():
            comp_rows += (f"<tr><td>{c['player']}</td><td>{c['team']}</td>"
                          f"<td style='text-align:right'>{c['similarity']:.0f}</td></tr>")

    age = _fmt(player.get("age"))
    return f"""
<html><head><meta charset="utf-8"><style>
  @page {{ size: letter; margin: 1.4cm; }}
  body {{ font-family: Helvetica, Arial, sans-serif; color:#1c2533; font-size:10.5pt; }}
  .hdr {{ background:{NAVY}; color:#fff; padding:12px 16px; border-left:9px solid {ORANGE};
          border-radius:6px; }}
  .hdr .n {{ font-size:19pt; font-weight:800; }}
  .hdr .s {{ color:#cfd6e4; font-size:10pt; }}
  h3 {{ color:{NAVY}; border-bottom:2px solid {ORANGE}; padding-bottom:3px;
        margin:14px 0 6px; font-size:11.5pt; }}
  table {{ border-collapse:collapse; width:100%; font-size:9.5pt; }}
  td, th {{ border-bottom:1px solid #e2e6ee; padding:3px 6px; }}
  th {{ background:#f1f4f9; color:{NAVY}; text-align:left; }}
  .note {{ background:#f4f6fa; border-left:4px solid {ORANGE}; padding:8px 10px;
           font-style:italic; color:#41506a; }}
  .two td {{ border:none; vertical-align:top; }}
</style></head><body>
  <div class="hdr">
    <div class="n">{player['player']}</div>
    <div class="s">{player.get('role','')} · {player['team']} ({player.get('conf','')})
      · {player.get('yr','')} · {player.get('height','?')} · age {age}</div>
  </div>
  {f'<div class="note" style="margin-top:10px">{rationale}</div>' if rationale else ''}

  <table class="two"><tr>
    <td style="width:290pt">
      <img src="data:image/png;base64,{radar_b64}" style="width:280pt;height:280pt"/>
    </td>
    <td style="width:250pt">
      <h3>Big Ten projection</h3>
      <table><tr><th>Stat</th><th style="text-align:right">Raw</th>
        <th style="text-align:right">At Illinois</th></tr>{proj_rows}</table>
      <h3>Shot diet</h3>
      <table>
        <tr><th>Zone</th><th style="text-align:right">Share</th><th style="text-align:right">FG%</th></tr>
        <tr><td>Rim</td><td style="text-align:right">{sp['rim_share']:.0%}</td>
            <td style="text-align:right">{_fmt(sp['rim_pct']*100,'{:.0f}%') if pd.notna(sp['rim_pct']) else '-'}</td></tr>
        <tr><td>Mid</td><td style="text-align:right">{sp['mid_share']:.0%}</td>
            <td style="text-align:right">{_fmt(sp['mid_pct']*100,'{:.0f}%') if pd.notna(sp['mid_pct']) else '-'}</td></tr>
        <tr><td>Three</td><td style="text-align:right">{sp['three_share']:.0%}</td>
            <td style="text-align:right">{_fmt(sp['three_pct']*100,'{:.0f}%') if pd.notna(sp['three_pct']) else '-'}</td></tr>
      </table>
    </td>
  </tr></table>

  <h3>Plays like</h3>
  <table><tr><th>Comp</th><th>Team</th><th style="text-align:right">Similarity</th></tr>
    {comp_rows or '<tr><td colspan="3">-</td></tr>'}</table>

  <p style="color:#9aa3b2;font-size:8pt;margin-top:14px">
    Illini Portal Fit Engine · data: BartTorvik (public) · radar = percentile vs Big Ten
    rotation · projection from {projection['n_pairs'] if projection else 0} real transfers.</p>
</body></html>"""


def card_to_pdf(html: str) -> bytes:
    """Render card HTML to PDF bytes (xhtml2pdf)."""
    from xhtml2pdf import pisa

    buf = io.BytesIO()
    pisa.CreatePDF(html, dest=buf)
    return buf.getvalue()


def build_projection(model, player: pd.Series) -> dict:
    """Assemble the raw->projected lines for the card from a TranslationModel."""
    from .translation import STAT_LABEL

    proj = model.project(pd.DataFrame([player])).iloc[0]
    lines = []
    for stat in ("pts_pg", "three_pm_pg", "ast_pg", "trb_pg"):
        lines.append((STAT_LABEL[stat],
                      f"{proj[f'raw_{stat}']:.1f}", f"{proj[f'proj_{stat}']:.1f}"))
    return {"lines": lines, "n_pairs": model.n_pairs,
            "level_jump": proj["level_jump"], "retention": proj["retention"]}


if __name__ == "__main__":
    from .fetch import get_players, get_teams
    from .fit_score import candidate_pool
    from .similarity import build_reference, comps as comp_fn
    from .translation import calibrate

    players, teams = get_players(), get_teams()
    pool = candidate_pool(players, teams)
    base = bigten_baseline(players)
    mu, sigma = build_reference(players)
    model = calibrate()

    tgt = pool.sort_values("bpm", ascending=False).iloc[0]
    proj = build_projection(model, tgt)
    cmp = comp_fn(tgt, bigten_baseline(players, min_min_pct=40), mu, sigma, n=4,
                  exclude_pid=tgt.get("pid"))
    html = card_html(tgt, base, projection=proj, comps=cmp,
                     rationale=f"{tgt['role']} · {tgt['team']} · {proj['level_jump']}.")
    pdf = card_to_pdf(html)

    out = "report/sample_scouting_card.pdf"
    with open(out, "wb") as fh:
        fh.write(pdf)
    print(f"Sample card: {tgt['player']} ({tgt['team']})")
    print(f"  raw {tgt['pts_pg']:.1f} pts -> proj {proj['lines'][0][2]} "
          f"({proj['retention']:.0f}% retention, {proj['level_jump']})")
    print(f"  comps: {', '.join(cmp['player'].tolist())}")

    # --- assertions --------------------------------------------------------
    assert len(pdf) > 5000, f"PDF looks empty ({len(pdf)} bytes)"
    pcts = percentiles_vs_baseline(tgt, base)
    assert all(0 <= v <= 100 for v in pcts.values()), "percentiles must be 0-100"
    print(f"\nWrote {out} ({len(pdf)//1024} KB). Sanity checks passed.")
