"""Liftoff connector — the opt-in, file-import source.

Liftoff (getgymbros.com) has no official API or export. There's a community tool,
`liftoff-export` (github.com/DTTerastar/liftoff-export-cli), that can dump your
workouts as JSON — but rather than have *this* project shell out to it or touch
your Liftoff password, this connector is a plain file reader:

    You produce a workout JSON export however you trust (e.g.
    `liftoff-export workouts list --format json > imports/liftoff_workouts.json`)
    and drop it in imports/. We only ever read that file.

That keeps every credential decision outside this project entirely. This is also
why Liftoff is opt-in and off by default (`--enable-liftoff`): it relies on an
unofficial export path, and reaching your data is a Terms-of-Service gray area
(it's your own data, so not a legal issue).

Expected file: imports/liftoff_*.json — a JSON array of workout "Post" objects
(the shape `liftoff-export` emits). Each Post has exerciseData[]; we keep only
weight/reps exercises (exerciseTypes == "WR"), where setsData[].inputOne is
weight in kg and inputTwo is reps. Weight is converted to lb to match the app.
"""

import glob
import json
import os

from connectors.base import Connector

KG_TO_LB = 2.2046226218
IMPORTS_DIR = "imports"
FILE_GLOB = "liftoff_*.json"


class LiftoffConnector(Connector):
    name = "liftoff"

    def sync(self, conn) -> int:
        paths = sorted(glob.glob(os.path.join(IMPORTS_DIR, FILE_GLOB)))
        if not paths:
            print(f"[liftoff] no files matching {IMPORTS_DIR}/{FILE_GLOB} — export "
                  f"your workouts to JSON and drop the file there.")
            return 0

        total = 0
        for path in paths:
            total += self._import_file(conn, path)
        return total

    def _import_file(self, conn, path) -> int:
        with open(path) as f:
            posts = json.load(f)
        if not isinstance(posts, list):
            print(f"[liftoff] {os.path.basename(path)}: expected a JSON array of "
                  f"workouts, skipping")
            return 0

        rows = 0
        # Number sets per (date, exercise) so two sessions of the same lift on one
        # day get sequential set numbers instead of colliding on the UNIQUE key.
        set_counter = {}

        for post in posts:
            date = (post.get("startedAt") or "")[:10]  # local calendar day
            if not date:
                continue
            for ex in post.get("exerciseData", []):
                # Only weight/reps exercises become strength sets; skip
                # distance/duration (DD) and no-data (ND).
                if ex.get("exerciseTypes") != "WR":
                    continue
                name = ex.get("exerciseName") or "Unknown"
                for s in ex.get("setsData", []):
                    weight_kg = _num(s.get("inputOne"))
                    reps = _num(s.get("inputTwo"))
                    if weight_kg is None or reps is None:
                        continue
                    key = (date, name)
                    set_counter[key] = set_counter.get(key, 0) + 1
                    conn.execute(
                        """INSERT OR IGNORE INTO strength_sets
                           (date, exercise, set_no, weight, reps) VALUES (?,?,?,?,?)""",
                        (date, name, set_counter[key],
                         round(weight_kg * KG_TO_LB, 1), int(round(reps))),
                    )
                    rows += 1

        print(f"[liftoff] {os.path.basename(path)}: {rows} sets")
        return rows


def _num(v):
    """Coerce a JSON value (possibly a string) to float, or None."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
