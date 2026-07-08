# fitness-dashboard

A personal health-analytics pipeline. It pulls my fitness data out of three apps
that don't talk to each other and puts it in one place — so I can not only see it
together but *cross-reference* it (does my weight actually track my training
volume? do heavy lifting weeks line up with eating more?).

This is a learning / portfolio project, not a deployable product.

## The three sources (and why they're handled differently)

The interesting part is that each app lets its data out in a different way, and
the code treats each one accordingly:

| Source | Domain | How the data comes out | Legitimacy |
|---|---|---|---|
| **Strava** | Cardio (runs, rides) | Official OAuth REST API | Fully sanctioned |
| **MyNetDiary** | Diet + weight | Built-in CSV/Excel export | Sanctioned |
| **Liftoff** | Strength (gym) | Manual JSON export you drop in `imports/` | Opt-in, off by default |

Each source is a **connector** (`connectors/`) implementing one small interface,
so the pipeline doesn't care how the data was obtained — it just syncs each
enabled connector into a shared SQLite database, isolating failures so one broken
source never takes down the rest.

### A note on Liftoff

Liftoff has no official API or export. Reaching your data is a Terms-of-Service
gray area (it's *my own* data, so not a legal issue — worst case is account
closure), so this connector is deliberately hands-off about credentials: **it
never touches your Liftoff login.** Instead, *you* produce a workout JSON export
however you trust — e.g. with the community tool
[`liftoff-export`](https://github.com/DTTerastar/liftoff-export-cli),
`liftoff-export workouts list --format json > imports/liftoff_workouts.json` —
and this connector just reads that file. It's **off by default**, ships **no
credentials**, and only runs when you explicitly pass `--enable-liftoff`.
Whatever you decide to trust for the login step stays entirely outside this
project's code. Everything else uses official channels.

## Design principles

- **Code owns the visuals.** Every chart is computed deterministically from the
  data with `pandas` + Chart.js. There is **no AI-generated imagery**.
- **AI is optional and text-only.** An optional, manually-triggered feature
  (Phase 6) can write a short *prose* summary of the computed trends. The app is
  fully functional without it, and it never touches a chart.
- **Real health data never gets committed** — the database, manual exports, and
  secrets are all gitignored. The repo ships synthetic demo data instead.

## Getting it running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# See it immediately with synthetic data (no accounts or keys needed):
python scripts/seed_demo.py
```

### Connecting Strava (one-time)

1. Register a personal API app at [strava.com/settings/api](https://www.strava.com/settings/api).
   Any name works; set **Authorization Callback Domain** to `localhost`.
2. Copy `.env.example` to `.env` and paste in the **Client ID** and **Client Secret** it gives you.
3. Get a long-lived refresh token (opens a browser, you approve once):
   ```bash
   python strava_auth.py     # prints STRAVA_REFRESH_TOKEN — paste it into .env
   ```
4. You're set. `python pipeline.py --source strava` now pulls your activities.

Then, as the phases land:

```bash
python pipeline.py --source strava     # Phase 1: pull real activities
# drop a MyNetDiary CSV export into imports/, then:
python pipeline.py --source mynetdiary # Phase 2: import weight + nutrition
python app.py                          # Phase 3: dashboard on http://localhost:5002
```

## Data flow

```
Strava API ─────┐
MyNetDiary CSV ─┼─► connectors/ ─► pipeline.py ─► fitness.db ─► app.py ─► browser
Liftoff (opt-in)┘                                   (SQLite)     (Flask, charts)
```

## Status

Phases 0–5 complete — the pipeline, all three connectors, the dashboard, and the
**cross-source view** are in. That last one is the payoff: alongside the per-source
charts, the dashboard now aligns every feed on a single weekly timeline (weight and
calories as lines, a training-load index as bars) and computes the correlations
between them — reporting, in plain English, whether eating more actually tracked
with gaining and training harder tracked with losing. Phase 6 (an optional,
text-only Claude trend summary) is the only piece left. See `CLAUDE.md` for the
full phase checklist.

## What it's not

Not deployed, not real-time, not medical advice. Just my own data, in one place,
so I can look at it properly.
