"""Strava CSV connector — the free, no-API, no-subscription cardio source.

As of 2026-06-30 Strava's live REST API requires a paid Strava subscription,
even for a personal self-hosted app pulling your own data. This connector
sidesteps that entirely by reading Strava's **free bulk data export** instead:

    Strava → Settings → "My Account" → "Download or Delete Your Account"
           → "Download Request (optional)" → Request Your Archive

Strava emails you a zip; inside is `activities.csv` — every activity you've ever
logged. Drop it in imports/ as `strava_*.csv` (or leave it named activities.csv)
and this imports it into the same `activities` table the live API connector fed.

Like the MyNetDiary connector, this is a tolerant file importer: the export's
headers vary by account and locale, and it even carries **duplicate** column
names — a localized summary block (Distance in km/mi, Elapsed Time in the app's
units) followed by a detailed SI block (Distance in metres). Rather than trust a
header name for units, we detect the metres column by magnitude. Idempotent:
rows are keyed by Strava's own Activity ID (the same id the API uses), so
re-importing a fresh export just refreshes existing rows instead of duplicating.
"""

import glob
import os

import pandas as pd

from connectors.base import Connector

IMPORTS_DIR = "imports"
# The export unzips to activities.csv; accept that name or a strava_*.csv rename.
FILE_GLOBS = ["strava_*.csv", "activities*.csv"]

# Strength sessions (including Liftoff workouts auto-posted to Strava) carry no
# distance/reps in this export — just a duration — and strength is owned by the
# Liftoff connector. Keep these out of the cardio `activities` table so they
# don't inflate run/workout counts or double-count against Liftoff. Compared
# after lowercasing and removing spaces (so "Weight Training" -> "weighttraining").
EXCLUDED_TYPES = {"weighttraining", "workout"}


def _norm_type(value) -> str:
    return "".join(str(value).lower().split())


def _find_columns(columns, keywords, avoid=()):
    """All columns whose lowercased name contains any keyword (in file order).

    `avoid` keywords veto a column even if a wanted keyword also matched — e.g.
    "heart rate" should not pick up "Max Heart Rate" when we want the average.
    """
    out = []
    for col in columns:
        low = str(col).lower()
        if any(a in low for a in avoid):
            continue
        if any(kw in low for kw in keywords):
            out.append(col)
    return out


def _first(columns, keywords, avoid=()):
    matches = _find_columns(columns, keywords, avoid)
    return matches[0] if matches else None


def _to_number(series):
    """Coerce a column to numeric, stripping stray units/commas (e.g. '5,000 m')."""
    cleaned = (
        series.astype(str)
        .str.replace(r"[^0-9.\-]", "", regex=True)
        .replace("", None)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _pick_metres_distance(df, candidates):
    """From the distance column(s), return a metres series.

    The export can carry both a localized summary distance (km or miles) and a
    detailed distance in metres. We pick the largest-magnitude column (metres)
    and, if only a small-valued one exists, treat it as km and convert.
    """
    best_col, best_median, best_vals = None, -1.0, None
    for col in candidates:
        vals = _to_number(df[col])
        median = vals.dropna().median()
        if pd.isna(median):
            continue
        if median > best_median:
            best_col, best_median, best_vals = col, median, vals
    if best_vals is None:
        return None
    # A single run/ride is rarely >1000 in km/mi but always is in metres.
    if best_median < 1000:
        best_vals = best_vals * 1000.0  # km -> m
    return best_vals


class StravaCsvConnector(Connector):
    name = "strava_csv"

    def sync(self, conn) -> int:
        paths = []
        for pattern in FILE_GLOBS:
            paths.extend(glob.glob(os.path.join(IMPORTS_DIR, pattern)))
        paths = sorted(set(paths))
        if not paths:
            print(f"[strava_csv] no files matching {IMPORTS_DIR}/"
                  f"{{{', '.join(FILE_GLOBS)}}} — request your Strava data export "
                  f"and drop activities.csv there.")
            return 0

        total = 0
        for path in paths:
            total += self._import_file(conn, path)
        return total

    def _import_file(self, conn, path) -> int:
        df = pd.read_csv(path)
        name = os.path.basename(path)

        id_col = _first(df.columns, ["activity id", "id"])
        date_col = _first(df.columns, ["activity date", "date"])
        type_col = _first(df.columns, ["activity type", "sport", "type"])
        name_col = _first(df.columns, ["activity name", "name"], avoid=["file"])
        dist_cols = _find_columns(df.columns, ["distance"])
        move_col = _first(df.columns, ["moving time"])
        hr_col = _first(df.columns, ["average heart rate", "average heartrate"]) \
            or _first(df.columns, ["heart rate", "heartrate"], avoid=["max"])
        elev_col = _first(df.columns, ["elevation gain", "elev gain", "total elevation"]) \
            or _first(df.columns, ["elevation"], avoid=["loss", "low", "high"])

        if not id_col or not date_col:
            print(f"[strava_csv] {name}: no Activity ID / Date column found, skipping")
            return 0

        ids = _to_number(df[id_col])
        dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
        types = df[type_col] if type_col else None
        names = df[name_col] if name_col else None
        dist = _pick_metres_distance(df, dist_cols) if dist_cols else None
        move = _to_number(df[move_col]) if move_col else None
        hr = _to_number(df[hr_col]) if hr_col else None
        elev = _to_number(df[elev_col]) if elev_col else None

        def at(series, i):
            if series is None:
                return None
            v = series.iloc[i]
            if isinstance(v, float) and pd.isna(v):
                return None
            return v if not pd.isna(v) else None

        rows = 0
        skipped = 0
        for i in range(len(df)):
            aid, day = ids.iloc[i], dates.iloc[i]
            if pd.isna(aid) or pd.isna(day):
                continue
            stype = at(types, i)
            if stype is not None and _norm_type(stype) in EXCLUDED_TYPES:
                skipped += 1  # strength session — owned by the Liftoff connector
                continue
            conn.execute(
                """INSERT OR REPLACE INTO activities
                   (id, date, sport_type, name, distance_m, moving_time_s, avg_hr, elevation_m)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    int(aid),
                    day.strftime("%Y-%m-%d"),
                    (str(at(types, i)) if at(types, i) is not None else None),
                    (str(at(names, i)) if at(names, i) is not None else None),
                    (float(dist.iloc[i]) if dist is not None and not pd.isna(dist.iloc[i]) else None),
                    (int(move.iloc[i]) if move is not None and not pd.isna(move.iloc[i]) else None),
                    (float(hr.iloc[i]) if hr is not None and not pd.isna(hr.iloc[i]) else None),
                    (float(elev.iloc[i]) if elev is not None and not pd.isna(elev.iloc[i]) else None),
                ),
            )
            rows += 1

        note = f" ({skipped} strength sessions skipped — owned by Liftoff)" if skipped else ""
        print(f"[strava_csv] {name}: {rows} activities{note}")
        return rows
