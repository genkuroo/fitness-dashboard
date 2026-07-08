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


def weekly_running_miles(conn) -> dict:
    """Running distance summed per calendar week (bars), in miles."""
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
    activities = _read(conn, "SELECT date, distance_m FROM activities")
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

    # Total running distance (miles) and run count.
    if not activities.empty:
        out["running"] = {"miles": round(activities["distance_m"].sum() / METERS_PER_MILE, 1),
                          "runs": int(len(activities))}
    else:
        out["running"] = {"miles": 0, "runs": 0}

    # Workouts logged = runs + distinct lifting days.
    out["workouts"] = {"value": int(len(activities)) + int(len(strength))}

    return out


def _days_before(date_str, days):
    """Return the YYYY-MM-DD string `days` before a YYYY-MM-DD string."""
    return (pd.to_datetime(date_str) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def dashboard_data(conn) -> dict:
    """Everything the dashboard template needs, in one call."""
    return {
        "kpis": kpis(conn),
        "weight": weight_series(conn),
        "calories": calories_series(conn),
        "running": weekly_running_miles(conn),
        "strength": weekly_strength_volume(conn),
    }
