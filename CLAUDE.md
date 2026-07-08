# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

A personal health-analytics pipeline that pulls three fitness feeds into one
local SQLite database so they can be viewed — and cross-referenced — in one
place:

- **Strava** (cardio) — official OAuth REST API.
- **MyNetDiary** (diet + weight) — manual CSV export dropped into `imports/`.
- **Liftoff** (strength) — unofficial private-API route; **opt-in, off by default**.

The point isn't just consolidation, it's the *join*: line up training load
against weight trend against calories on one timeline — something no single app
does.

## Hard rules

- **Code owns the visuals.** Every chart/infographic is computed deterministically
  from the data (`pandas` → Chart.js). **No AI-generated imagery, ever.**
- **AI is optional, text-only, manual (Phase 6).** Claude only writes a prose
  summary of already-computed trends, only when explicitly asked
  (`pipeline.py --summarize`). The app is fully functional with `anthropic` not
  installed. It never produces or influences a chart.
- **Never commit real health data.** `fitness.db`, `imports/*`, and `.env` are
  gitignored. The public repo shows code + synthetic demo data only.
- **Liftoff is opt-in.** `enabled: false` in `config.json`; only runs with
  `--enable-liftoff`. No credentials committed. Personal use only.
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
- [ ] **Phase 4 — Liftoff connector.** Opt-in, `--enable-liftoff` → `strength_sets`.
- [ ] **Phase 5 — Cross-source analytics.** pandas join → Chart.js (training load
      vs weight vs calories). The payoff.
- [ ] **Phase 6 — (optional) Claude trend summary.** Manual, text-only prose caption.

## Running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/seed_demo.py     # populate synthetic demo data
python pipeline.py --source strava   # (after Phase 1) real Strava pull
python app.py                   # (after Phase 3) dashboard on :5002
```

## Note on Claude specifics

Before writing `tldr.py` (Phase 6), re-verify the current model id and
structured-output syntax via the `claude-api` skill rather than copying blind
from `stock-tracker`.
