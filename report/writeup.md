# Illini Portal Fit Engine
### A transfer-portal recruiting target board for Illinois Men's Basketball

**Author:** Mannat Talati · **Built for:** Illinois Men's Basketball Analytics Internship
**Live app:** _(Streamlit link — see README)_ · **Code:** _(GitHub link — see README)_

---

## 1. The problem

Roster construction in college basketball now runs through the transfer portal. Every
spring, 1,500+ Division I players enter, and a staff has a few weeks to decide who to
pursue. Illinois under Brad Underwood has been one of the most aggressive portal and
international programs in the country, so this is not a side project for the staff — it
*is* the roster.

The hard part is not finding *good* players; it is finding good players who **(a)** fill a
**specific hole** the roster just opened, **(b)** fit how Illinois actually plays, and
**(c)** are **realistic** to land. Doing that by eye across all of Division I is slow and
biased toward the names you already know.

**This tool turns that triage into a ranked, explainable board.** It profiles Illinois's
roster, detects what's leaving, and scores every eligible D-I player on a transparent
**Fit Score** so the staff can start the portal window with a shortlist instead of a blank
page.

## 2. The data — and how I sourced it

Everything is **public BartTorvik data**, pulled live over plain HTTP (no scraping tricks,
no paywalled sources like KenPom):

| Source | Endpoint | What it gives |
|---|---|---|
| Player advanced stats | `getadvstats.php?year=YYYY&csv=1` | ~5,000 players/season, 67 columns: archetype role, usage, efficiency, shooting splits, BPM/OBPM/DBPM, rebounding, steals/blocks, class, height, hometown |
| Team ratings | `YYYY_team_results.json` | 365 teams: adjusted offense/defense, Barthag power rating, tempo |

The player feed ships with **no header row**, so I reverse-engineered the column layout and
then **validated it against the data itself** before trusting a single number:

- shooting splits reconcile (FTM ÷ FTA = FT%, etc.),
- `BPM == OBPM + DBPM` holds for **100%** of rows,
- `total rebounds == offensive + defensive` per game holds for **100%** of rows.

Columns I could not verify are named `extra_NN` and are **deliberately unused**, so every
figure the tool reports is one I can explain on a whiteboard.

A real snapshot is committed to the repo, so the app loads instantly for a reviewer and the
results are reproducible; a "Refresh from BartTorvik" button re-pulls live data on demand.

## 3. How the Fit Score works

For the current (2025-26) season, the engine reads Illinois as: **28-9, Barthag #6, the
#2 offense in the country (adjOE 131.8), #20 defense, and — notably — the #289 tempo.**
That last number matters: Illinois is an *elite half-court* team, **not** a run-and-gun
team, so the model rewards skill and shot-making over raw transition athleticism. The
profile is *derived from data*, not assumed.

It then assumes seniors graduate (editable in the app) — for 2025-26 that's lead guard
**Kylan Boswell**, stretch big **Ben Humrichous**, and **AJ Redd** — and measures what
walks out the door: a chunk of the team's **playmaking, perimeter defense, and outside
shooting**.

Each eligible candidate (non-Illinois, has remaining eligibility, cleared minimum
minutes/games) gets a **0-100 Fit Score**, a weighted blend of four parts that are each
shown separately:

1. **Production** — proven value: BPM, porpag, minutes load.
2. **Role fit** — does their position fill a *depleted* Illinois spot (guard / wing / big)?
3. **System fit** — do their strengths match the **specific** skills Illinois must replace?
   The weights here come straight from the departure analysis (e.g. "we lost 24% of our
   made threes" → shooting is weighted up).
4. **Attainability** — a realism lens from the player's current team strength, surfaced as a
   plain label: *High-major proven*, *Mid-major riser*, *Low-major standout*.

Every component is percentile-ranked **within the candidate pool**, so a score answers the
question a coach actually asks: *"compared to the other realistic options, how good is
this?"* All four weights, the departure list, and the need weights are **tunable live** in
the app.

**Example output (default Illinois needs, 2025-26):**

| Fit | Player | Team | Role | Why |
|---|---|---|---|---|
| 86.8 | Jason Rivera-Torres | Monmouth | Wing F | 3.3% steal rate; 1.5 3PM/g; +5.5 BPM — perimeter D + shooting; mid-major riser |
| 85.3 | Tyler Tanner | Vanderbilt | Scoring PG | 5.1 ast/g (29 AST%); +10.2 BPM — playmaking; high-major proven |
| 85.1 | Mason Falslev | Utah St. | Combo G | 3.6% steal rate; 3.1 ast/g; +8.8 BPM — perimeter D + playmaking |

Each row carries an auto-generated scouting note, and the **Player Detail** view breaks the
score into its four bars next to the player's full statistical profile.

## 4. How I built it

- **Language:** Python 3.
- **Data / model:** `pandas`, `numpy` — a small, readable package (`illini_fit/`) split into
  `schema` (validated column map), `fetch` (cache + live refresh), `profile` (team + roster),
  `needs` (departure-driven gap detection), and `fit_score` (the scoring model).
- **App:** `streamlit` — an interactive, Illini-themed web app (filters, weight sliders,
  ranked board, player detail, CSV export).
- **Quality:** the data layer and the model each ship with self-checks (row-count and
  Illinois-parse assertions; a test that a shooting-weighted board really does surface more
  shooters and that scores stay in 0-100). The app is verified headlessly with Streamlit's
  `AppTest`.
- **Deploy:** GitHub + Streamlit Community Cloud (one-click, free) for a shareable live link.

## 5. Why it's useful to a GM / coaching staff

- **It starts the portal window with a shortlist, not a spreadsheet.** Day one of the portal,
  the staff has a ranked, position-aware board instead of 1,500 names.
- **It's tied to *this* roster's needs.** The board re-ranks the moment you mark a player as
  leaving — so the night a starter enters the portal, you instantly see who replaces *his*
  production, not just "good players."
- **It's explainable to non-analysts.** Every score decomposes into production / role /
  system / attainability with a one-line rationale. That's defensible in a staff meeting and
  to a head coach who wants the *why*, not a black box.
- **It encodes Illinois's identity from data.** Because system fit is derived from Illinois's
  actual profile (elite half-court offense, slow tempo, shooting), it won't recommend a
  player who is good in the abstract but wrong for how Illinois plays.
- **It's tunable on the fly.** A coach who wants to prioritize a defensive guard over a
  scoring one just moves a slider; the board updates in real time.

In practice the staff intersects this board with the live portal list (which they have and
which is not a clean public feed): the engine ranks the full pool by fit, and the staff
filters to who's actually available. That mirrors how an analytics staffer already works —
this just does the heavy ranking in seconds.

## 6. Honest limitations & next steps

- **Portal availability isn't a clean public dataset**, so the engine ranks the full pool and
  is meant to be filtered to the live portal list. A natural v2 is to ingest a portal feed and
  auto-filter.
- **One season of box-score data** underrates injured/young players and can overrate
  high-usage players on bad teams; attainability and minutes filters mitigate this but don't
  eliminate it. Multi-year trends and play-type data (Synergy/Hudl, if licensed) would sharpen it.
- **Fit weights are a reasonable default, not gospel** — which is exactly why they're exposed
  as sliders for the staff to own.
- **No NIL/cost modeling.** A real GM board would layer in budget; that data isn't public.

---

*All data is publicly sourced from BartTorvik. Built as an independent analytics project for
the Illinois Men's Basketball Analytics Internship.*
