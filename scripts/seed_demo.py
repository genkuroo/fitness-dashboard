"""Populate fitness.db with synthetic-but-realistic demo data.

Why this exists:
  * The public repo must never contain real personal health data, so the
    dashboard needs *something* to render. This generates a plausible ~12 weeks
    of cardio, strength, weight, and nutrition that all overlap on the same
    calendar — so the cross-source view (Phase 5) has real overlap to show.
  * It's deterministic (fixed seed) so screenshots and demos are reproducible.

The Phase 5 payoff only means anything if the four feeds are actually *coupled*:
if weight fell on its own regardless of eating and training, the correlation
panel would show pure noise and the "join" would look broken. So the data is
generated in dependency order — training and calories first, then bodyweight is
simulated day-by-day from a simple energy balance (calories in − maintenance −
exercise burn), plus measurement noise. The result is a demo where eating more
genuinely tracks with gaining and training harder genuinely tracks with losing.

Run from the repo root:  python scripts/seed_demo.py
"""

import math
import os
import random
import sys
from datetime import date, timedelta

# Allow running as `python scripts/seed_demo.py` from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402

random.seed(42)

WEEKS = 12
START = date.today() - timedelta(weeks=WEEKS)

# Rough energy-balance constants for the weight simulation. These are demo-grade
# approximations, not medical claims — they just make the sources move together.
MAINTENANCE_KCAL = 2450     # daily intake that would hold weight steady, at rest
KCAL_PER_LB = 3500          # textbook "one pound of fat ≈ 3500 kcal"
KCAL_PER_RUN_MILE = 100     # ballpark running expenditure
KCAL_PER_LIFT_DAY = 180     # flat estimate for a strength session

LIFTS = ["Squat", "Bench Press", "Deadlift", "Overhead Press", "Barbell Row"]
LIFT_BASE = {"Squat": 185, "Bench Press": 135, "Deadlift": 225,
             "Overhead Press": 95, "Barbell Row": 115}


def daterange(days):
    for i in range(days):
        yield START + timedelta(days=i)


def build_schedule():
    """Decide, up front, what training and eating happens on every day.

    Returned per-day dict carries the raw activity plus its calorie burn, so the
    weight simulation can react to the exact same numbers the other tables store.
    Calories carry a per-week mood (a 'loose' vs 'tight' week) and a mild pull
    toward eating more on higher-mileage weeks, which is what makes the three
    cross-source correlations show a real — but not cartoonish — signal.
    """
    days = list(daterange(WEEKS * 7))

    # Per-week eating "mood": some weeks you're looser, some tighter.
    week_cal_offset = [random.uniform(-260, 260) for _ in range(WEEKS)]

    # --- runs: ~3-4/week, distance ramping up across the block --------------
    runs = {}
    for i, d in enumerate(days):
        if random.random() > 0.5:
            continue
        base_km = 5 + (i / (WEEKS * 7)) * 4  # 5km ramping toward ~9km
        distance_m = max(1000.0, (base_km + random.uniform(-1.5, 1.5)) * 1000)
        pace = random.uniform(5.2, 6.4)  # min/km
        runs[d] = {
            "distance_m": round(distance_m),
            "moving_s": int(distance_m / 1000 * pace * 60),
            "avg_hr": round(random.uniform(140, 165), 1),
            "elevation_m": round(random.uniform(10, 90), 1),
        }

    # --- lifts: 3 days/week, slow progressive overload ---------------------
    lifts = {}
    for week in range(WEEKS):
        for offset in (0, 2, 4):  # Mon/Wed/Fri-ish
            d = START + timedelta(weeks=week, days=offset)
            chosen = random.sample(LIFTS, 3)
            sets = []
            for lift in chosen:
                weight = LIFT_BASE[lift] + week * 5  # +5 lb/week
                for set_no in range(1, 4):
                    sets.append((lift, set_no, weight, random.randint(5, 8)))
            lifts[d] = sets

    # Weekly running mileage, used to nudge that week's appetite up a touch.
    week_miles = [0.0] * WEEKS
    for d, r in runs.items():
        week_miles[(d - START).days // 7] += r["distance_m"] / 1609.344

    # --- daily calories, aware of the week's mood + training ---------------
    schedule = {}
    for i, d in enumerate(days):
        week = i // 7
        run = runs.get(d)
        run_kcal = (run["distance_m"] / 1609.344) * KCAL_PER_RUN_MILE if run else 0.0
        lift_kcal = KCAL_PER_LIFT_DAY if d in lifts else 0.0

        cals = (2300
                + week_cal_offset[week]           # this week's loose/tight mood
                + 6.0 * week_miles[week]          # eat a bit more on big weeks
                + random.uniform(-110, 110))      # day-to-day noise
        cals = max(1700, cals)

        schedule[d] = {
            "run": run,
            "lifts": lifts.get(d),
            "calories": cals,
            "burn_kcal": run_kcal + lift_kcal,
        }
    return days, schedule


def seed_activities(conn, days, schedule):
    rows = 0
    aid = 1000
    for d in days:
        run = schedule[d]["run"]
        if not run:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO activities
               (id, date, sport_type, name, distance_m, moving_time_s, avg_hr, elevation_m)
               VALUES (?,?,?,?,?,?,?,?)""",
            (aid, d.isoformat(), "Run", "Morning Run", run["distance_m"],
             run["moving_s"], run["avg_hr"], run["elevation_m"]),
        )
        aid += 1
        rows += 1
    return rows


def seed_strength(conn, days, schedule):
    rows = 0
    for d in days:
        sets = schedule[d]["lifts"]
        if not sets:
            continue
        for lift, set_no, weight, reps in sets:
            conn.execute(
                """INSERT OR IGNORE INTO strength_sets
                   (date, exercise, set_no, weight, reps)
                   VALUES (?,?,?,?,?)""",
                (d.isoformat(), lift, set_no, weight, reps),
            )
            rows += 1
    return rows


def seed_nutrition(conn, days, schedule):
    """Store the daily calories decided in the schedule, split into macros."""
    rows = 0
    for d in days:
        cals = schedule[d]["calories"]
        protein = random.uniform(150, 190)
        fat = random.uniform(60, 85)
        carbs = max(0, (cals - protein * 4 - fat * 9) / 4)
        conn.execute(
            """INSERT OR REPLACE INTO nutrition (date, calories, protein_g, carbs_g, fat_g)
               VALUES (?,?,?,?,?)""",
            (d.isoformat(), round(cals), round(protein), round(carbs), round(fat)),
        )
        rows += 1
    return rows


def seed_body_metrics(conn, days, schedule):
    """Simulate bodyweight day-by-day from the schedule's energy balance.

    weight change (lb) each day = (intake − maintenance − exercise) / 3500, with
    a little measurement noise on top. Because intake and training come straight
    from the schedule, the resulting weight genuinely responds to them — which is
    the whole point of the cross-source view.
    """
    rows = 0
    weight = 191.0  # starting bodyweight
    for i, d in enumerate(days):
        s = schedule[d]
        net_kcal = s["calories"] - MAINTENANCE_KCAL - s["burn_kcal"]
        weight += net_kcal / KCAL_PER_LB
        # Water-weight / scale noise so the line isn't unrealistically smooth.
        noise = math.sin(i / 3) * 0.4 + random.uniform(-0.4, 0.4)
        conn.execute(
            "INSERT OR REPLACE INTO body_metrics (date, weight) VALUES (?,?)",
            (d.isoformat(), round(weight + noise, 1)),
        )
        rows += 1
    return rows


def main():
    conn = db.connect()
    db.init_db(conn)
    days, schedule = build_schedule()
    counts = {
        "activities": seed_activities(conn, days, schedule),
        "strength_sets": seed_strength(conn, days, schedule),
        "nutrition": seed_nutrition(conn, days, schedule),
        "body_metrics": seed_body_metrics(conn, days, schedule),
    }
    conn.commit()
    conn.close()
    print("Seeded demo data:")
    for table, n in counts.items():
        print(f"  {table:16} {n} rows")


if __name__ == "__main__":
    main()
