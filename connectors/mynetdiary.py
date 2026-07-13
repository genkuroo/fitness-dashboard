"""MyNetDiary connector — the manual-export source.

MyNetDiary has no personal-data API, but it lets you export your data. Drop the
export into imports/ as `mynetdiary_*` and this reads it. Two shapes are handled:

  * The **yearly workbook** (Analysis -> Data Export -> "MyNetDiary_Year_YYYY.xls").
    A multi-sheet Excel file: a `Food` sheet with one row per logged food item
    (summed per day into calories + macros) and a `Measurements` sheet in tall
    `Measurement`/`Value` form (the "Body Weight" rows become bodyweight). This is
    the real, complete export and the recommended one.
  * A **flat CSV report** (one row per day, columns like date/weight/calories).
    Kept as a tolerant fallback for the older Chart/Report CSV exports.

Because MyNetDiary's exact headers vary by report and locale, columns are matched
tolerantly by keyword (case-insensitive substring) rather than by exact name.
If a file matches nothing recognizable, it's skipped with a clear message instead
of guessing.
"""

import glob
import os

import pandas as pd

from connectors.base import Connector

IMPORTS_DIR = "imports"
# The yearly export is .xls; older report exports are .csv. Accept both (+ .xlsx).
FILE_GLOBS = ["mynetdiary_*.csv", "mynetdiary_*.xls", "mynetdiary_*.xlsx"]

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
    lowered = {c: str(c).lower() for c in columns}
    for kw in keywords:
        for original, low in lowered.items():
            if kw in low:
                return original
    return None


def _find_sheet(sheet_names, keywords):
    """Return the first sheet whose lowercased name contains any keyword."""
    for kw in keywords:
        for name in sheet_names:
            if kw in str(name).lower():
                return name
    return None


def _opt(v):
    """A nullable numeric cell -> float or None (for optional macro columns)."""
    return None if v is None or pd.isna(v) else float(v)


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
        paths = []
        for pattern in FILE_GLOBS:
            paths.extend(glob.glob(os.path.join(IMPORTS_DIR, pattern)))
        paths = sorted(set(paths))
        if not paths:
            print(f"[mynetdiary] no files matching {IMPORTS_DIR}/mynetdiary_* — "
                  f"export your data (Analysis -> Data Export) and drop it there.")
            return 0

        total = 0
        for path in paths:
            if path.lower().endswith((".xls", ".xlsx")):
                total += self._import_workbook(conn, path)
            else:
                total += self._import_file(conn, path)
        return total

    # --- Yearly workbook export (the real, complete export) ------------------

    def _import_workbook(self, conn, path) -> int:
        name = os.path.basename(path)
        try:
            book = pd.ExcelFile(path)
        except Exception as e:
            print(f"[mynetdiary] {name}: could not open Excel file ({e}). "
                  f"Install xlrd (for .xls) / openpyxl (for .xlsx).")
            return 0

        rows = 0
        food_sheet = _find_sheet(book.sheet_names, ["food"])
        meas_sheet = _find_sheet(book.sheet_names, ["measure"])
        if food_sheet:
            rows += self._load_food_sheet(conn, book, food_sheet)
        if meas_sheet:
            rows += self._load_measurements_sheet(conn, book, meas_sheet)

        if rows == 0:
            print(f"[mynetdiary] {name}: no Food/Measurements data recognized, skipping")
        else:
            print(f"[mynetdiary] {name}: {rows} rows")
        return rows

    @staticmethod
    def _load_food_sheet(conn, book, sheet) -> int:
        """Food sheet = one row per logged item; sum per day into nutrition."""
        df = pd.read_excel(book, sheet_name=sheet)
        date_col = _find_column(df.columns, ["date"])
        cal_col = _find_column(df.columns, ["calorie", "energy", "kcal"])
        if not date_col or not cal_col:
            return 0
        prot_col = _find_column(df.columns, ["protein"])
        carb_col = _find_column(df.columns, ["total carb", "carb"])
        fat_col = _find_column(df.columns, ["total fat", "fat"])

        agg = pd.DataFrame({"day": pd.to_datetime(df[date_col], errors="coerce").dt.date})
        agg["calories"] = _to_number(df[cal_col])
        agg["protein"] = _to_number(df[prot_col]) if prot_col else pd.NA
        agg["carbs"] = _to_number(df[carb_col]) if carb_col else pd.NA
        agg["fat"] = _to_number(df[fat_col]) if fat_col else pd.NA
        agg = agg.dropna(subset=["day"])
        daily = agg.groupby("day", as_index=True).sum(min_count=1)

        rows = 0
        for day, r in daily.iterrows():
            if pd.isna(r["calories"]):
                continue
            conn.execute(
                """INSERT OR REPLACE INTO nutrition
                   (date, calories, protein_g, carbs_g, fat_g) VALUES (?,?,?,?,?)""",
                (day.strftime("%Y-%m-%d"), float(r["calories"]),
                 _opt(r["protein"]), _opt(r["carbs"]), _opt(r["fat"])),
            )
            rows += 1
        return rows

    @staticmethod
    def _load_measurements_sheet(conn, book, sheet) -> int:
        """Measurements sheet = tall Measurement/Value rows; pull Body Weight."""
        df = pd.read_excel(book, sheet_name=sheet)
        date_col = _find_column(df.columns, ["date"])
        meas_col = _find_column(df.columns, ["measurement", "metric", "type"])
        val_col = _find_column(df.columns, ["value"])
        if not (date_col and meas_col and val_col):
            return 0

        is_weight = df[meas_col].astype(str).str.contains("weight", case=False, na=False)
        w = df[is_weight]
        unit_col = _find_column(df.columns, ["unit"])
        dates = pd.to_datetime(w[date_col], errors="coerce")
        values = _to_number(w[val_col])

        rows = 0
        for i in range(len(w)):
            d, v = dates.iloc[i], values.iloc[i]
            if pd.isna(d) or pd.isna(v):
                continue
            # MyNetDiary exports kg or lbs per the account; body_metrics is lbs.
            if unit_col and "kg" in str(w[unit_col].iloc[i]).lower():
                v = v * 2.2046226218
            conn.execute(
                "INSERT OR REPLACE INTO body_metrics (date, weight) VALUES (?,?)",
                (d.strftime("%Y-%m-%d"), float(v)),
            )
            rows += 1
        return rows

    # --- Flat CSV report (older export shape) --------------------------------

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
