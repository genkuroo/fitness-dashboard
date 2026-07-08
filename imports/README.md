# imports/

Drop manual data exports here. Files in this folder are **gitignored** — they
contain real personal health data and never get committed.

## MyNetDiary (Phase 2)

In MyNetDiary, open a Chart or Report, export it to CSV/Excel, and save the file
here as `mynetdiary_*.csv` (e.g. `mynetdiary_2026-07.csv`). Then run:

```bash
python pipeline.py --source mynetdiary
```

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
