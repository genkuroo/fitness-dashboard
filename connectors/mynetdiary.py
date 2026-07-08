"""MyNetDiary connector — the manual-export source.

MyNetDiary has no personal-data API, but it lets you export Charts/Reports to
CSV. You drop those files into imports/ as `mynetdiary_*.csv` and this reads them.

Two kinds of export are supported, auto-detected by their columns:
  * a weight/measurements export  -> body_metrics (date, weight)
  * a nutrition/food export       -> nutrition (date, calories, macros)

Because MyNetDiary's exact headers vary by report and locale, columns are matched
tolerantly by keyword (case-insensitive substring) rather than by exact name.
If a file matches neither shape, it's skipped with a clear message instead of
guessing.
"""

import glob
import os

import pandas as pd

from connectors.base import Connector

IMPORTS_DIR = "imports"
FILE_GLOB = "mynetdiary_*.csv"

# Keyword -> the normalized field it feeds. First matching column wins.
# Order matters: more specific keywords are listed first.
COLUMN_KEYWORDS = {
    "date": ["date", "day"],
    "weight": ["weight"],
    "calories": ["calorie", "energy", "kcal", "cals"],
    "protein_g": ["protein"],
    "carbs_g": ["net carb", "carb"],
    "fat_g": ["fat"],
}


def _find_column(columns, keywords):
    """Return the first column whose lowercased name contains any keyword."""
    lowered = {c: c.lower() for c in columns}
    for kw in keywords:
        for original, low in lowered.items():
            if kw in low:
                return original
    return None


def _to_number(series):
    """Coerce a column to numeric, stripping stray units/commas."""
    cleaned = (
        series.astype(str)
        .str.replace(r"[^0-9.\-]", "", regex=True)
        .replace("", None)
    )
    return pd.to_numeric(cleaned, errors="coerce")


class MyNetDiaryConnector(Connector):
    name = "mynetdiary"

    def sync(self, conn) -> int:
        paths = sorted(glob.glob(os.path.join(IMPORTS_DIR, FILE_GLOB)))
        if not paths:
            print(f"[mynetdiary] no files matching {IMPORTS_DIR}/{FILE_GLOB} — "
                  f"export a Chart/Report to CSV and drop it there.")
            return 0

        total = 0
        for path in paths:
            total += self._import_file(conn, path)
        return total

    def _import_file(self, conn, path) -> int:
        df = pd.read_csv(path)
        cols = {field: _find_column(df.columns, kws)
                for field, kws in COLUMN_KEYWORDS.items()}

        if not cols["date"]:
            print(f"[mynetdiary] {os.path.basename(path)}: no date column found, skipping")
            return 0

        # Normalize the date column to YYYY-MM-DD strings.
        dates = pd.to_datetime(df[cols["date"]], errors="coerce")

        rows = 0
        if cols["weight"]:
            rows += self._load_weight(conn, dates, _to_number(df[cols["weight"]]))
        if cols["calories"]:
            rows += self._load_nutrition(conn, dates, df, cols)

        if rows == 0:
            print(f"[mynetdiary] {os.path.basename(path)}: no weight or nutrition "
                  f"columns recognized, skipping")
        else:
            print(f"[mynetdiary] {os.path.basename(path)}: {rows} rows")
        return rows

    @staticmethod
    def _load_weight(conn, dates, weights) -> int:
        rows = 0
        for d, w in zip(dates, weights):
            if pd.isna(d) or pd.isna(w):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO body_metrics (date, weight) VALUES (?,?)",
                (d.strftime("%Y-%m-%d"), float(w)),
            )
            rows += 1
        return rows

    @staticmethod
    def _load_nutrition(conn, dates, df, cols) -> int:
        cal = _to_number(df[cols["calories"]])
        protein = _to_number(df[cols["protein_g"]]) if cols["protein_g"] else None
        carbs = _to_number(df[cols["carbs_g"]]) if cols["carbs_g"] else None
        fat = _to_number(df[cols["fat_g"]]) if cols["fat_g"] else None

        def at(series, i):
            if series is None:
                return None
            v = series.iloc[i]
            return None if pd.isna(v) else float(v)

        rows = 0
        for i, d in enumerate(dates):
            if pd.isna(d) or pd.isna(cal.iloc[i]):
                continue
            conn.execute(
                """INSERT OR REPLACE INTO nutrition
                   (date, calories, protein_g, carbs_g, fat_g) VALUES (?,?,?,?,?)""",
                (d.strftime("%Y-%m-%d"), float(cal.iloc[i]),
                 at(protein, i), at(carbs, i), at(fat, i)),
            )
            rows += 1
        return rows
