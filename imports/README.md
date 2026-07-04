# imports/

Drop manual data exports here. Files in this folder are **gitignored** — they
contain real personal health data and never get committed.

## MyNetDiary (Phase 2)

In MyNetDiary, open a Chart or Report, export it to CSV/Excel, and save the file
here as `mynetdiary_*.csv` (e.g. `mynetdiary_2026-07.csv`). Then run:

```bash
python pipeline.py --source mynetdiary
```
