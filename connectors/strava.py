"""Strava connector — the official, sanctioned source.

Strava gives every user a free API app. Auth is OAuth2 with a long-lived refresh
token: we exchange it for a short-lived access token on each run (no browser,
no re-login), then page through the athlete's activities.

Credentials come from the environment (loaded from .env by run.sh):
    STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN

Get a refresh token once with:  python strava_auth.py
"""

import os

import requests

from connectors.base import Connector

TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
PER_PAGE = 200  # Strava's max page size


class StravaConnector(Connector):
    name = "strava"

    def _refresh_access_token(self):
        """Trade the long-lived refresh token for a short-lived access token."""
        client_id = os.environ.get("STRAVA_CLIENT_ID")
        client_secret = os.environ.get("STRAVA_CLIENT_SECRET")
        refresh_token = os.environ.get("STRAVA_REFRESH_TOKEN")
        missing = [k for k, v in {
            "STRAVA_CLIENT_ID": client_id,
            "STRAVA_CLIENT_SECRET": client_secret,
            "STRAVA_REFRESH_TOKEN": refresh_token,
        }.items() if not v]
        if missing:
            raise RuntimeError(
                "Missing Strava credentials in environment: " + ", ".join(missing) +
                ". Run `python strava_auth.py` to get a refresh token, then add it to .env."
            )

        resp = requests.post(TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        # Strava can rotate the refresh token; surface it so the user can update .env.
        new_refresh = payload.get("refresh_token")
        if new_refresh and new_refresh != refresh_token:
            print(f"[strava] NOTE: refresh token rotated. Update .env:\n"
                  f"         STRAVA_REFRESH_TOKEN={new_refresh}")
        return payload["access_token"]

    def _fetch_activities(self, access_token):
        """Page through /athlete/activities until Strava returns an empty page."""
        headers = {"Authorization": f"Bearer {access_token}"}
        page = 1
        while True:
            resp = requests.get(ACTIVITIES_URL, headers=headers, params={
                "per_page": PER_PAGE, "page": page,
            }, timeout=30)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            yield from batch
            page += 1

    @staticmethod
    def normalize(activity: dict) -> tuple:
        """Map a raw Strava activity into our `activities` table columns.

        Kept pure and static so it can be unit-tested against a sample payload
        without any network or credentials.
        """
        # start_date_local looks like "2026-06-30T06:12:34Z"; we only want the day.
        start = activity.get("start_date_local") or activity.get("start_date") or ""
        day = start[:10]
        return (
            activity["id"],
            day,
            activity.get("sport_type") or activity.get("type"),
            activity.get("name"),
            activity.get("distance"),               # metres
            activity.get("moving_time"),            # seconds
            activity.get("average_heartrate"),
            activity.get("total_elevation_gain"),   # metres
        )

    def sync(self, conn) -> int:
        access_token = self._refresh_access_token()
        rows = 0
        for activity in self._fetch_activities(access_token):
            conn.execute(
                """INSERT OR REPLACE INTO activities
                   (id, date, sport_type, name, distance_m, moving_time_s, avg_hr, elevation_m)
                   VALUES (?,?,?,?,?,?,?,?)""",
                self.normalize(activity),
            )
            rows += 1
        return rows
