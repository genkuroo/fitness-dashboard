"""Populate fitness.db with synthetic-but-realistic demo data.

Why this exists:
  * The public repo must never contain real personal health data, so the
    dashboard needs *something* to render. This generates a plausible ~12 weeks
    of cardio, strength, weight, and nutrition that all overlap on the same
    calendar — so the cross-source view (Phase 5) has real overlap to show.
  * It's deterministic (fixed seed) so screenshots and demos are reproducible.

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


def daterange(days):
    for i in range(days):
        yield START + timedelta(days=i)


def seed_activities(conn):
    """Runs/rides a few days a week, with a gentle upward volume trend."""
    rows = 0
    aid = 1000
    for i, d in enumerate(daterange(WEEKS * 7)):
        # ~3-4 sessions/week, more likely later in the block.
        if random.random() > 0.5:
            continue
        base_km = 5 + (i / (WEEKS * 7)) * 4  # 5km ramping toward ~9km
        distance_m = (base_km + random.uniform(-1.5, 1.5)) * 1000
        pace = random.uniform(5.2, 6.4)  # min/km
        moving_s = int(distance_m / 1000 * pace * 60)
        conn.execute(
            """INSERT OR REPLACE INTO activities
               (id, date, sport_type, name, distance_m, moving_time_s, avg_hr, elevation_m)
               VALUES (?,?,?,?,?,?,?,?)""",
            (aid, d.isoformat(), "Run", "Morning Run", round(distance_m),
             moving_s, round(random.uniform(140, 165), 1), round(random.uniform(10, 90), 1)),
        )
        aid += 1
        rows += 1
    return rows


LIFTS = ["Squat", "Bench Press", "Deadlift", "Overhead Press", "Barbell Row"]


def seed_strength(conn):
    """3 lifting days/week, slow progressive overload."""
    rows = 0
    for week in range(WEEKS):
        for offset in (0, 2, 4):  # Mon/Wed/Fri-ish
            d = START + timedelta(weeks=week, days=offset)
            for lift in random.sample(LIFTS, 3):
                base = {"Squat": 185, "Bench Press": 135, "Deadlift": 225,
                        "Overhead Press": 95, "Barbell Row": 115}[lift]
                weight = base + week * 5  # +5 lb/week
                for set_no in range(1, 4):
                    conn.execute(
                        """INSERT OR IGNORE INTO strength_sets
                           (date, exercise, set_no, weight, reps)
                           VALUES (?,?,?,?,?)""",
                        (d.isoformat(), lift, set_no, weight, random.randint(5, 8)),
                    )
                    rows += 1
    return rows


def seed_body_metrics(conn):
    """Weight with a slow downward trend plus daily noise."""
    rows = 0
    start_w = 190.0
    for i, d in enumerate(daterange(WEEKS * 7)):
        trend = start_w - (i / (WEEKS * 7)) * 8  # lose ~8 lb over the block
        noise = math.sin(i / 3) * 0.6 + random.uniform(-0.5, 0.5)
        conn.execute(
            "INSERT OR REPLACE INTO body_metrics (date, weight) VALUES (?,?)",
            (d.isoformat(), round(trend + noise, 1)),
        )
        rows += 1
    return rows


def seed_nutrition(conn):
    """Daily calories in a modest deficit, protein-forward."""
    rows = 0
    for d in daterange(WEEKS * 7):
        cals = random.uniform(2100, 2500)
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


def main():
    conn = db.connect()
    db.init_db(conn)
    counts = {
        "activities": seed_activities(conn),
        "strength_sets": seed_strength(conn),
        "body_metrics": seed_body_metrics(conn),
        "nutrition": seed_nutrition(conn),
    }
    conn.commit()
    conn.close()
    print("Seeded demo data:")
    for table, n in counts.items():
        print(f"  {table:16} {n} rows")


if __name__ == "__main__":
    main()
