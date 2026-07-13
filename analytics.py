"""Read-only analytics computed from fitness.db.

All numbers and series shown on the dashboard are computed here, deterministically,
with pandas. The dashboard (app.py) only ever renders what these functions return —
no external calls, and no AI anywhere near a chart.

Kept separate from app.py so Phase 5's cross-source view can build on the same
primitives.
"""

import pandas as pd

METERS_PER_MILE = 1609.344


def _read(conn, sql, **kw):
    return pd.read_sql_query(sql, conn, **kw)


def weight_series(conn) -> dict:
    """Daily bodyweight over time (single line)."""
    df = _read(conn, "SELECT date, weight FROM body_metrics ORDER BY date")
    return {"labels": df["date"].tolist(),
            "values": [round(v, 1) for v in df["weight"].tolist()]}


def calories_series(conn) -> dict:
    """Daily calorie intake over time (single line)."""
    df = _read(conn, "SELECT date, calories FROM nutrition ORDER BY date")
    return {"labels": df["date"].tolist(),
            "values": [round(v) for v in df["calories"].tolist()]}


def weekly_cardio_miles(conn) -> dict:
    """Cardio distance summed per calendar week (bars), in miles.

    Strength sessions are excluded upstream (the Strava connector skips them),
    so every activity row here is genuine cardio; walks/hikes logged without GPS
    simply contribute no distance.
    """
    df = _read(conn, "SELECT date, distance_m FROM activities",
               parse_dates=["date"])
    if df.empty:
        return {"labels": [], "values": []}
    weekly = (df.set_index("date")
                .resample("W-MON", label="left", closed="left")["distance_m"]
                .sum() / METERS_PER_MILE)
    return {"labels": [d.strftime("%Y-%m-%d") for d in weekly.index],
            "values": [round(v, 1) for v in weekly.tolist()]}


def weekly_strength_volume(conn) -> dict:
    """Strength volume (sum of weight x reps) per week (bars), in thousands of lbs."""
    df = _read(conn, "SELECT date, weight, reps FROM strength_sets",
               parse_dates=["date"])
    if df.empty:
        return {"labels": [], "values": []}
    df["volume"] = df["weight"] * df["reps"]
    weekly = (df.set_index("date")
                .resample("W-MON", label="left", closed="left")["volume"]
                .sum() / 1000.0)
    return {"labels": [d.strftime("%Y-%m-%d") for d in weekly.index],
            "values": [round(v, 1) for v in weekly.tolist()]}


def kpis(conn) -> dict:
    """Headline stat-tile numbers. Each value is paired with context where useful."""
    weight = _read(conn, "SELECT date, weight FROM body_metrics ORDER BY date")
    nutrition = _read(conn, "SELECT date, calories FROM nutrition ORDER BY date",
                      parse_dates=["date"])
    activities = _read(conn, "SELECT date, sport_type, distance_m FROM activities")
    strength = _read(conn, "SELECT DISTINCT date FROM strength_sets")

    out = {}

    # Current weight + 30-day change (down is good for a cut).
    if not weight.empty:
        current = round(weight["weight"].iloc[-1], 1)
        prior = weight[weight["date"] <= _days_before(weight["date"].iloc[-1], 30)]
        delta = round(current - prior["weight"].iloc[-1], 1) if not prior.empty else None
        out["weight"] = {"value": current, "delta": delta, "unit": "lb"}
    else:
        out["weight"] = {"value": None, "delta": None, "unit": "lb"}

    # Average daily calories over the last 14 logged days.
    if not nutrition.empty:
        recent = nutrition.sort_values("date").tail(14)
        out["avg_calories"] = {"value": round(recent["calories"].mean())}
    else:
        out["avg_calories"] = {"value": None}

    # Total cardio distance (miles) + a per-type session breakdown, so the tile
    # says "11 runs · 8 walks · 1 hike" instead of miscounting everything as runs.
    if not activities.empty:
        miles = round(activities["distance_m"].fillna(0).sum() / METERS_PER_MILE, 1)
        counts = activities["sport_type"].fillna("Other").value_counts()
        by_type = [(str(t), int(n)) for t, n in counts.items()]
        out["cardio"] = {"miles": miles, "sessions": int(len(activities)),
                         "breakdown": _breakdown_phrase(by_type)}
    else:
        out["cardio"] = {"miles": 0, "sessions": 0, "breakdown": ""}

    # Workouts logged = cardio sessions + distinct lifting days.
    out["workouts"] = {"value": int(len(activities)) + int(len(strength))}

    return out


def _breakdown_phrase(by_type) -> str:
    """Turn [('Run', 11), ('Walk', 8), ('Hike', 1)] into '11 runs · 8 walks · 1 hike'."""
    parts = [f"{n} {t.lower()}{'s' if n != 1 else ''}" for t, n in by_type]
    return " · ".join(parts)


def _days_before(date_str, days):
    """Return the YYYY-MM-DD string `days` before a YYYY-MM-DD string."""
    return (pd.to_datetime(date_str) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")


# --- Phase 5: cross-source analytics ----------------------------------------
#
# The payoff. Everything above summarizes one source at a time. These functions
# put all four sources on a single weekly timeline and ask whether they actually
# move together — the one question no single app (Strava / MyNetDiary / Liftoff)
# can answer, because none of them can see the other two.

def _weekly_sum(conn, sql, value_col):
    """Resample a dated value column into a weekly (Mon-anchored) sum series."""
    df = _read(conn, sql, parse_dates=["date"])
    if df.empty:
        return pd.Series(dtype=float)
    return (df.set_index("date")
              .resample("W-MON", label="left", closed="left")[value_col]
              .sum())


def _weekly_mean(conn, sql, value_col):
    """Resample a dated value column into a weekly (Mon-anchored) mean series."""
    df = _read(conn, sql, parse_dates=["date"])
    if df.empty:
        return pd.Series(dtype=float)
    return (df.set_index("date")
              .resample("W-MON", label="left", closed="left")[value_col]
              .mean())


def _normalize(s: pd.Series) -> pd.Series:
    """Min-max scale a series into 0..1. Flat series -> all zeros (no signal)."""
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or hi == lo:
        return pd.Series(0.0, index=s.index)
    return (s - lo) / (hi - lo)


def weekly_frame(conn) -> pd.DataFrame:
    """One row per calendar week, every source aligned on the same index.

    This is the join that the whole project exists for. Cardio and strength come
    in as weekly sums; calories and weight as weekly averages (a daily reading is
    noisy, the week's average is the real trend). Weeks with no training are a
    genuine 0; weeks with no weigh-in / no food log stay NaN (missing != zero).

    'training_load' is a synthetic 0-100 index: cardio miles and strength volume
    live in different units and can't just be added, so each is min-max normalized
    across the block and averaged. It's a relative "how hard was this week" number,
    not an absolute one — documented here and in the chart tooltip so it's honest.
    """
    strength_sql = "SELECT date, weight * reps AS volume FROM strength_sets"
    frame = pd.DataFrame({
        "run_mi": _weekly_sum(conn, "SELECT date, distance_m FROM activities",
                              "distance_m") / METERS_PER_MILE,
        "str_vol": _weekly_sum(conn, strength_sql, "volume") / 1000.0,
        "avg_cal": _weekly_mean(conn, "SELECT date, calories FROM nutrition",
                                "calories"),
        "weight": _weekly_mean(conn, "SELECT date, weight FROM body_metrics",
                               "weight"),
    })
    if frame.empty:
        return frame

    frame = frame.sort_index()
    # Training happened or it didn't — absence is a real zero for load.
    frame["run_mi"] = frame["run_mi"].fillna(0.0)
    frame["str_vol"] = frame["str_vol"].fillna(0.0)
    frame["training_load"] = (
        (_normalize(frame["run_mi"]) + _normalize(frame["str_vol"])) / 2 * 100
    )
    # Week-over-week weight change: the thing calories/training should predict.
    frame["weight_delta"] = frame["weight"].diff()
    return frame


def cross_source(conn) -> dict:
    """Series for the combined weekly timeline chart (dual-axis: weight, cal, load)."""
    frame = weekly_frame(conn)
    if frame.empty:
        return {"labels": [], "weight": [], "calories": [], "load": []}

    def col(name, nd):
        return [None if pd.isna(v) else round(v, nd) for v in frame[name].tolist()]

    return {
        "labels": [d.strftime("%Y-%m-%d") for d in frame.index],
        "weight": col("weight", 1),
        "calories": [None if pd.isna(v) else round(v) for v in frame["avg_cal"].tolist()],
        "load": col("training_load", 0),
    }


def _pearson(a: pd.Series, b: pd.Series):
    """Pearson r over the weeks where BOTH series are present. (r, n)."""
    paired = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(paired) < 3 or paired["a"].nunique() < 2 or paired["b"].nunique() < 2:
        return None, len(paired)
    return float(paired["a"].corr(paired["b"])), len(paired)


def _strength_word(r: float) -> str:
    a = abs(r)
    if a < 0.2:
        return "no clear"
    if a < 0.4:
        return "a weak"
    if a < 0.7:
        return "a moderate"
    return "a strong"


def correlations(conn) -> list:
    """Do the sources actually move together? Pearson r on the weekly frame.

    Each entry pairs the raw number with a plain-English reading, so the dashboard
    states what it found instead of making the viewer decode a coefficient.
    """
    frame = weekly_frame(conn)

    # (key, label, series a, series b, phrase when r is positive, when negative)
    specs = [
        ("cal_weight", "Calories vs weight change",
         "avg_cal", "weight_delta",
         "weeks you ate more, your weight trended up",
         "weeks you ate more, your weight still trended down"),
        ("load_weight", "Training vs weight change",
         "training_load", "weight_delta",
         "harder-training weeks came with weight ticking up",
         "harder-training weeks came with weight trending down"),
        ("load_cal", "Training vs calories",
         "training_load", "avg_cal",
         "you ate more on your harder-training weeks",
         "you ate less on your harder-training weeks"),
    ]

    out = []
    for key, label, a, b, pos, neg in specs:
        if frame.empty:
            r, n = None, 0
        else:
            r, n = _pearson(frame[a], frame[b])
        if r is None:
            out.append({"key": key, "label": label, "r": None, "n": n,
                        "sentence": "Not enough overlapping weeks yet.", "sign": "flat"})
            continue
        word = _strength_word(r)
        reading = pos if r >= 0 else neg
        sentence = (f"{word.capitalize()} link — {reading}."
                    if word != "no clear" else "No clear link in this window.")
        out.append({"key": key, "label": label, "r": round(r, 2), "n": n,
                    "sentence": sentence,
                    "sign": "flat" if word == "no clear" else ("up" if r >= 0 else "down")})
    return out


def dashboard_data(conn) -> dict:
    """Everything the dashboard template needs, in one call."""
    return {
        "kpis": kpis(conn),
        "weight": weight_series(conn),
        "calories": calories_series(conn),
        "cardio": weekly_cardio_miles(conn),
        "strength": weekly_strength_volume(conn),
        "cross": cross_source(conn),
        "correlations": correlations(conn),
    }
