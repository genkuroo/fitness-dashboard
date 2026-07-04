"""fitness-dashboard CLI — pull/import data from each source into fitness.db.

Usage:
    python pipeline.py                     # sync every enabled source
    python pipeline.py --source strava     # sync just one source
    python pipeline.py --enable-liftoff    # also run the opt-in Liftoff source
    python pipeline.py --summarize         # (Phase 6) manual, text-only trend summary

The dashboard (app.py) never calls this directly except via its refresh button;
it only ever reads fitness.db.
"""

import argparse
import json
import sys

import db


def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)


def build_connectors(config, enable_liftoff=False):
    """Instantiate the connector for each configured source.

    Connectors are imported lazily so a missing optional dependency (or a
    half-built connector during development) doesn't break the whole CLI.
    """
    sources = config.get("sources", {})
    connectors = []

    # Registered as each phase lands. Phase 0 ships the registry; the
    # connector modules themselves arrive in Phases 1, 2, and 4.
    registry = {}
    try:
        from connectors.strava import StravaConnector
        registry["strava"] = StravaConnector
    except ImportError:
        pass
    try:
        from connectors.mynetdiary import MyNetDiaryConnector
        registry["mynetdiary"] = MyNetDiaryConnector
    except ImportError:
        pass
    try:
        from connectors.liftoff import LiftoffConnector
        registry["liftoff"] = LiftoffConnector
    except ImportError:
        pass

    for name, cls in registry.items():
        source_cfg = dict(sources.get(name, {}))
        # --enable-liftoff is an explicit, per-run opt-in for the gray source.
        if name == "liftoff" and enable_liftoff:
            source_cfg["enabled"] = True
        connectors.append(cls(source_cfg))

    return connectors


def run_sync(only=None, enable_liftoff=False):
    config = load_config()
    conn = db.connect()
    db.init_db(conn)

    connectors = build_connectors(config, enable_liftoff=enable_liftoff)
    if only:
        connectors = [c for c in connectors if c.name == only]
        if not connectors:
            print(f"[skip] no connector named '{only}' is available yet")
            return

    total = 0
    failed = []
    for c in connectors:
        if not c.enabled:
            print(f"[skip] {c.name} is disabled in config")
            continue
        try:
            rows = c.sync(conn)
            conn.commit()
            total += rows
            print(f"[ok]   {c.name}: {rows} rows")
        except Exception as e:  # one broken source must not abort the rest
            failed.append(c.name)
            print(f"[FAIL] {c.name} — {type(e).__name__}: {e}")

    conn.close()
    print(f"\nDone. {total} rows written." + (f" Failed: {', '.join(failed)}" if failed else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sync fitness data into fitness.db")
    parser.add_argument("--source", help="only sync this source (strava, mynetdiary, liftoff)")
    parser.add_argument("--enable-liftoff", action="store_true",
                        help="opt in to the unofficial Liftoff source for this run")
    parser.add_argument("--summarize", action="store_true",
                        help="(Phase 6) generate a manual, text-only trend summary — never auto-runs")
    args = parser.parse_args(argv)

    if args.summarize:
        try:
            import tldr
        except ImportError:
            print("Trend summaries (Phase 6) aren't set up yet.")
            return 1
        tldr.summarize()
        return 0

    run_sync(only=args.source, enable_liftoff=args.enable_liftoff)
    return 0


if __name__ == "__main__":
    sys.exit(main())
