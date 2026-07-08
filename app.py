"""fitness-dashboard web UI — read-only view of fitness.db.

DB-only by design: this app never calls Strava/MyNetDiary/Liftoff or the AI. It
only reads the database and renders computed analytics. The "Sync now" button
shells out to pipeline.py (the one place data ever gets fetched).

Run:  python app.py   ->  http://localhost:5002
"""

import socket
import subprocess
import sys

from flask import Flask, flash, redirect, render_template, url_for

import analytics
import db

app = Flask(__name__)
app.secret_key = "fitness-dashboard-local"  # local-only, just for flash messages

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
    has_data = bool(data["weight"]["labels"] or data["running"]["labels"])
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


if __name__ == "__main__":
    db.init_db()
    port = find_free_port(PORT)
    if port != PORT:
        print(f"Port {PORT} is busy — using {port} instead.")
    print(f"Dashboard: http://localhost:{port}")
    app.run(debug=True, port=port)
