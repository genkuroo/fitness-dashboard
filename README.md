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
| **Liftoff** | Strength (gym) | Unofficial private-API route | Opt-in, off by default |

Each source is a **connector** (`connectors/`) implementing one small interface,
so the pipeline doesn't care how the data was obtained — it just syncs each
enabled connector into a shared SQLite database, isolating failures so one broken
source never takes down the rest.

### A note on Liftoff

Liftoff has no official API or export, so its connector uses the same private API
the phone app does. That's a Terms-of-Service gray area (it's *my own* data, so
not a legal issue — worst case is account closure), so it's **disabled by
default**, ships **no credentials**, and only runs when you explicitly pass
`--enable-liftoff`. Everything else uses official channels.

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

Then, as the phases land:

```bash
cp .env.example .env          # add your Strava OAuth credentials
python pipeline.py --source strava     # Phase 1: pull real activities
# drop a MyNetDiary CSV export into imports/, then:
python pipeline.py --source mynetdiary # Phase 2: import weight + nutrition
python app.py                          # Phase 3: dashboard on http://localhost:5001
```

## Data flow

```
Strava API ─────┐
MyNetDiary CSV ─┼─► connectors/ ─► pipeline.py ─► fitness.db ─► app.py ─► browser
Liftoff (opt-in)┘                                   (SQLite)     (Flask, charts)
```

## Status

Phase 0 (scaffold) complete. See `CLAUDE.md` for the phase checklist.

## What it's not

Not deployed, not real-time, not medical advice. Just my own data, in one place,
so I can look at it properly.
