# 🟧 Illini Portal Fit Engine

**A data-driven transfer-portal recruiting target board for Illinois Men's Basketball.**

Built for the Illinois Men's Basketball Analytics Internship. It profiles Illinois's roster,
detects what's leaving, and ranks every eligible Division I player by a transparent **Fit
Score** so the staff can walk into the portal window with a shortlist instead of a blank page.

- **Live app:** _add your Streamlit Community Cloud URL here_
- **Write-up:** [`report/writeup.md`](report/writeup.md)
- **Data:** 100% public — [BartTorvik](https://barttorvik.com)

---

## What it does

1. **Reads Illinois's identity from data** — record, Barthag, adjusted offense/defense, tempo
   (2025-26: 28-9, #6 Barthag, **#2 offense**, slow #289 tempo → an *elite half-court* team).
2. **Detects roster needs** — assumes seniors graduate (editable), then measures the share of
   last year's shooting / playmaking / defense / rebounding that's walking out the door.
3. **Scores every eligible D-I player** on a 0-100 **Fit Score** = a weighted, fully visible
   blend of **Production + Role fit + System fit + Attainability**, each percentile-ranked
   within the realistic candidate pool.
4. **Lets the staff drive** — tune weights, edit departures, re-weight needs, filter by
   conference/position/class, and export the board to CSV — all live.

## Quickstart

```bash
git clone <your-repo-url>
cd illini-portal-fit
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The app loads instantly from the committed data snapshot in `data/raw/`. Click
**🔄 Refresh from BartTorvik** in the sidebar to pull fresh data.

### Run the pipeline / tests without the UI

```bash
python -m illini_fit.fetch        # download + validate data (asserts Illinois parses)
python -m illini_fit.fit_score    # print the default Illinois board + run sanity checks
```

## How the Fit Score is built

| Component | Weight (default) | Measures |
|---|---|---|
| **Production** | 35% | BPM, porpag, minutes load — proven value |
| **Role fit** | 20% | Does the player's position fill a *depleted* Illinois spot? |
| **System fit** | 35% | Strengths matched to the *specific* skills Illinois must replace |
| **Attainability** | 10% | Realism, from current team strength (`High-major proven` → `Low-major standout`) |

Weights, departures, and need priorities are all adjustable in the app.

## Project structure

```
illini-portal-fit/
├── streamlit_app.py          # interactive web app (entry point)
├── illini_fit/
│   ├── config.py             # team identity, endpoints, role taxonomy
│   ├── schema.py             # validated 67-column BartTorvik map + loaders
│   ├── fetch.py              # download / cache / refresh (with snapshot fallback)
│   ├── profile.py            # Illinois team + roster profile
│   ├── needs.py              # departure-driven roster-need detection
│   └── fit_score.py          # the Fit Score model (+ self-tests)
├── data/raw/                 # committed BartTorvik snapshot (reproducible runs)
├── report/
│   ├── writeup.md            # the project write-up
│   └── sample_board_2026.csv # example output
├── requirements.txt
└── .streamlit/config.toml    # Illini orange/navy theme
```

## Data sources

| Source | Endpoint |
|---|---|
| Player advanced stats | `https://barttorvik.com/getadvstats.php?year=YYYY&csv=1` |
| Team ratings | `https://barttorvik.com/YYYY_team_results.json` |

The column layout of the headerless player feed was reverse-engineered and **validated**
(shooting splits reconcile; `BPM == OBPM + DBPM` and `TRB == ORB + DRB` hold for 100% of
rows). Unverified columns are unused.

## Deploy a live link (Streamlit Community Cloud — free)

1. Push this repo to GitHub (public).
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Pick the repo, branch `main`, main file `streamlit_app.py`.
4. Deploy. Paste the resulting URL into the **Live app** field above.

## Notes & limitations

Portal availability isn't a clean public feed, so the engine ranks the full eligible pool and
is meant to be filtered to the live portal list. It uses one season of box-score data (no
NIL/cost, no play-type data). Defaults are a sensible starting point — the sliders exist so
the staff owns the final weighting. See [`report/writeup.md`](report/writeup.md) for the full
discussion.

---

*Independent analytics project · all data publicly sourced from BartTorvik.*
