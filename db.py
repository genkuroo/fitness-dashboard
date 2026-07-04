"""SQLite schema and shared query helpers for fitness-dashboard.

One local database file (fitness.db) holds normalized data from every source.
Each domain gets its own table, all keyed by date so they can be joined on a
shared timeline — that join is the whole point of the project.

Schema is created idempotently (CREATE TABLE IF NOT EXISTS) with a try/except
ALTER migration pattern, so re-running is always safe.
"""

import sqlite3

DB_PATH = "fitness.db"


def connect():
    """Open a connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn=None):
    """Create all tables if they don't exist. Safe to call on every run."""
    own = conn is None
    if own:
        conn = connect()

    # Strava — one row per cardio activity (run, ride, etc.).
    conn.execute(
        """CREATE TABLE IF NOT EXISTS activities (
            id            INTEGER PRIMARY KEY,   -- Strava's own activity id
            date          TEXT NOT NULL,          -- YYYY-MM-DD (local start date)
            sport_type    TEXT,
            name          TEXT,
            distance_m    REAL,
            moving_time_s INTEGER,
            avg_hr        REAL,
            elevation_m   REAL
        )"""
    )

    # Liftoff — one row per set performed (opt-in source).
    conn.execute(
        """CREATE TABLE IF NOT EXISTS strength_sets (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            date     TEXT NOT NULL,   -- YYYY-MM-DD
            exercise TEXT NOT NULL,
            set_no   INTEGER,
            weight   REAL,            -- lbs
            reps     INTEGER,
            UNIQUE (date, exercise, set_no)
        )"""
    )

    # MyNetDiary — bodyweight, one reading per day.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS body_metrics (
            date   TEXT PRIMARY KEY,   -- YYYY-MM-DD
            weight REAL                -- lbs
        )"""
    )

    # MyNetDiary — daily nutrition totals.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS nutrition (
            date      TEXT PRIMARY KEY,   -- YYYY-MM-DD
            calories  REAL,
            protein_g REAL,
            carbs_g   REAL,
            fat_g     REAL
        )"""
    )

    # Optional Phase-6 prose summaries. Populated only on manual request.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS weekly_tldr (
            week_start TEXT PRIMARY KEY,   -- Monday, YYYY-MM-DD
            summary    TEXT,
            trend      TEXT,               -- e.g. up / flat / down
            generated  TEXT                -- ISO timestamp
        )"""
    )

    conn.commit()
    if own:
        conn.close()


def _add_column(conn, table, coldef):
    """Poor-man's migration: add a column, ignore if it already exists."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
    except sqlite3.OperationalError:
        pass


if __name__ == "__main__":
    init_db()
    print(f"Initialized {DB_PATH}")
