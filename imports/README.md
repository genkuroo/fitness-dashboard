# imports/

Drop manual data exports here. Files in this folder are **gitignored** — they
contain real personal health data and never get committed.

**Easiest way in:** you don't have to touch this folder by hand. On the dashboard
(`python app.py`), use the **Import file** control in the header — pick the source,
choose your exported file, and it lands here with the right name and imports itself.
The steps below are the equivalent CLI path.

## Strava (free, no API/subscription)

Since 2026-06-30 Strava's live API requires a paid subscription, so this project
reads Strava's **free bulk data export** instead. In Strava: **Settings → My Account
→ "Download or Delete Your Account" → "Download Request (optional)" → Request Your
Archive.** Strava emails you a zip; unzip it and drop the `activities.csv` here
(any name starting with `strava_`, or leave it as `activities.csv`). Then run:

```bash
python pipeline.py --source strava_csv
```

Rows are keyed by Strava's own Activity ID, so re-importing a newer export just
refreshes existing activities instead of duplicating them.

## MyNetDiary (Phase 2)

Use the website (mynetdiary.com), **Analysis → Data Export**: pick a year and
click **Download**. You get a multi-sheet Excel file named like
`MyNetDiary_Year_2026.xls`. Drop it here as `mynetdiary_*.xls` (any name starting
with `mynetdiary_`) — **upload the .xls directly, don't convert it to CSV**, since
converting a multi-sheet workbook loses all but one sheet. Then run:

```bash
python pipeline.py --source mynetdiary
```

The importer reads the `Food` sheet (one row per logged item, summed per day into
calories + macros) and the `Measurements` sheet (the "Body Weight" rows). An older
flat one-row-per-day CSV report is still accepted as `mynetdiary_*.csv`.

## Liftoff (Phase 4, opt-in)

Liftoff has no official export, and this project never touches your Liftoff
login. Produce a workout JSON export however you trust — e.g. with the community
tool [`liftoff-export`](https://github.com/DTTerastar/liftoff-export-cli):

```bash
liftoff-export workouts list --format json > imports/liftoff_workouts.json
```

Save it here as `liftoff_*.json`, then run:

```bash
python pipeline.py --source liftoff --enable-liftoff
```
