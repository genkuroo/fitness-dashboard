"""fitness-dashboard web UI — read-only view of fitness.db.

DB-only by design: this app never calls Strava/MyNetDiary/Liftoff or the AI. It
only reads the database and renders computed analytics. The "Sync now" button
shells out to pipeline.py (the one place data ever gets fetched).

Run:  python app.py   ->  http://localhost:5002
"""

import os
import socket
import subprocess
import sys

from flask import Flask, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

import analytics
import db

app = Flask(__name__)
app.secret_key = "fitness-dashboard-local"  # local-only, just for flash messages

IMPORTS_DIR = "imports"

# Each uploadable source -> (filename prefix, allowed extensions) the connector
# globs for. The upload drops the file into imports/ with the source's prefix,
# preserving the original extension, and runs that importer — the same file-drop
# the CLI reads, done from the browser. MyNetDiary's real export is .xls.
UPLOAD_SOURCES = {
    "strava_csv": ("strava_", {".csv"}),
    "mynetdiary": ("mynetdiary_", {".csv", ".xls", ".xlsx"}),
    "liftoff": ("liftoff_", {".json"}),
}

# Preferred port. macOS AirPlay squats on 5000 and stock-tracker owns 5001, so we
# start at 5002 — but if it's already taken, find_free_port() walks up to the next
# open one rather than failing. (Standing rule: never fight over a busy port.)
PORT = 5002


def find_free_port(preferred, limit=20):
    """Return `preferred` if it's free, else the next open port above it."""
    for port in range(preferred, preferred + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # connect_ex == 0 means something is already listening there.
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"No free port in range {preferred}–{preferred + limit - 1}")


@app.route("/")
def index():
    conn = db.connect()
    db.init_db(conn)
    data = analytics.dashboard_data(conn)
    conn.close()
    has_data = bool(data["weight"]["labels"] or data["cardio"]["labels"])
    return render_template("index.html", data=data, has_data=has_data)


@app.route("/refresh", methods=["POST"])
def refresh():
    """Kick off a data sync in the background, then return to the dashboard."""
    try:
        subprocess.Popen([sys.executable, "pipeline.py"])
        flash("Sync started — refresh the page in a moment to see new data.")
    except Exception as e:
        flash(f"Could not start sync: {e}")
    return redirect(url_for("index"))


@app.route("/upload", methods=["POST"])
def upload():
    """Accept an exported file from the browser, save it into imports/ with the
    name its connector expects, and run that one importer so we can report the
    result immediately (no terminal, no manual file copying)."""
    source = request.form.get("source")
    file = request.files.get("file")
    if source not in UPLOAD_SOURCES:
        flash("Pick a source for the upload.")
        return redirect(url_for("index"))
    if not file or not file.filename:
        flash("No file selected.")
        return redirect(url_for("index"))

    prefix, allowed_exts = UPLOAD_SOURCES[source]
    stem, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if ext not in allowed_exts:
        flash(f"{source} expects {', '.join(sorted(allowed_exts))} — got '{ext or 'no extension'}'.")
        return redirect(url_for("index"))
    stem = secure_filename(stem) or "upload"
    os.makedirs(IMPORTS_DIR, exist_ok=True)
    dest = os.path.join(IMPORTS_DIR, f"{prefix}{stem}{ext}")
    file.save(dest)

    # Run just this source's importer synchronously for immediate feedback.
    args = [sys.executable, "pipeline.py", "--source", source]
    if source == "liftoff":
        args.append("--enable-liftoff")  # Liftoff is opt-in / disabled by default
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        lines = (result.stdout or "").strip().splitlines()
        summary = lines[-1] if lines else "import finished"
        flash(f"Imported {file.filename} — {summary}")
    except Exception as e:
        flash(f"Saved {os.path.basename(dest)} but the import failed: {e}")
    return redirect(url_for("index"))


if __name__ == "__main__":
    db.init_db()
    port = find_free_port(PORT)
    if port != PORT:
        print(f"Port {PORT} is busy — using {port} instead.")
    print(f"Dashboard: http://localhost:{port}")
    app.run(debug=True, port=port)
