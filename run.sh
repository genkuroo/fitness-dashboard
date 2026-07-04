#!/usr/bin/env bash
# Env-loading wrapper so scheduled/launchd runs get the .env secrets.
# Mirrors the stock-tracker pattern.
set -e
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; source .env; set +a; fi
exec ./.venv/bin/python pipeline.py "$@"
