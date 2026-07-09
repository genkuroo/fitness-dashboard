# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

A personal health-analytics pipeline that pulls three fitness feeds into one
local SQLite database so they can be viewed — and cross-referenced — in one
place:

- **Strava** (cardio) — official OAuth REST API.
- **MyNetDiary** (diet + weight) — manual CSV export dropped into `imports/`.
- **Liftoff** (strength) — manual JSON export dropped in `imports/`; **opt-in, off by default**.

The point isn't just consolidation, it's the *join*: line up training load
against weight trend against calories on one timeline — something no single app
does.

## Hard rules

- **Code owns everything.** Every number, chart, and insight is computed
  deterministically from the data (`pandas` → Chart.js). **This project contains no
  AI**: no generated imagery, no generated text, no API calls to a model. The
  correlations say what the data says. Don't add an AI dependency — a "just a text
  caption" summary was scoped as Phase 6 and deliberately **cancelled**.
- **Never commit real health data.** `fitness.db`, `imports/*`, and `.env` are
  gitignored. The public repo shows code + synthetic demo data only.
- **Liftoff is opt-in and credential-free.** `enabled: false` in `config.json`;
  only runs with `--enable-liftoff`. The connector reads a JSON export the user
  drops in `imports/liftoff_*.json` — it never handles the Liftoff login. Personal
  use only.
- **Commits/PRs: no AI attribution** (workspace convention).

## Architecture

- Flat root modules + a `connectors/` package (one connector per source behind a
  common `Connector` base — the ETL story).
- `sqlite3` (stdlib, no ORM). Idempotent `CREATE TABLE IF NOT EXISTS`; re-runs
  are safe. `INSERT OR IGNORE` for backfill, `INSERT OR REPLACE` for daily rows.
- `pipeline.py` (argparse CLI) loops enabled connectors inside per-source
  try/except so one broken source never aborts the run.
- `app.py` (Flask, port 5002) is **DB-only** — it never calls an external API;
  its refresh button shells out to `pipeline.py`.
- Secrets in `.env` (loaded by `run.sh`); hand-edited `config.json` for source flags.

## Phases (each phase = one shippable commit)

- [x] **Phase 0 — Scaffold.** Repo, schema (`db.py`), config, connector base,
      `pipeline.py` dispatch, `seed_demo.py`, docs.
- [x] **Phase 1 — Strava connector.** OAuth refresh-token flow → `activities`.
      `strava_auth.py` is the one-time login helper.
- [x] **Phase 2 — MyNetDiary importer.** CSV in `imports/` → `body_metrics` + `nutrition`.
      Tolerant keyword-based column matching; auto-routes weight vs nutrition files.
- [x] **Phase 3 — Flask dashboard.** DB-only, port 5002 (auto-shifts if busy),
      KPI tiles + 4 charts (analytics.py → Chart.js), data tables, Sync button.
- [x] **Phase 4 — Liftoff connector.** Opt-in file importer (`imports/liftoff_*.json`,
      `--enable-liftoff`) → `strength_sets`. Keeps only WR sets; kg→lb. No creds.
- [x] **Phase 5 — Cross-source analytics.** `weekly_frame()` aligns all four sources
      on one weekly index; a dual-axis Chart.js panel shows weight + calories (lines)
      over a training-load index (bars), and an insights strip reports Pearson `r`
      for calories↔weight-change, training↔weight-change, training↔calories in plain
      English. Demo seeder simulates weight from energy balance so the signal is real.
- ~~**Phase 6 — Claude trend summary.**~~ **Cancelled.** The dashboard's job is to
      compute and state what the data shows; the correlation insights already do that
      in plain English, deterministically. An AI prose caption would add a dependency,
      an API key, and a non-reproducible surface for zero analytical gain. The project
      is complete at Phase 5.

## Running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/seed_demo.py     # populate synthetic demo data
python pipeline.py --source strava   # real Strava pull
python app.py                   # dashboard on :5002
```
