"""One-time helper to get a Strava refresh token.

Strava's refresh token is long-lived — you generate it once and the connector
uses it forever (until you revoke access). This script walks the OAuth flow:

  1. You register a personal app at https://www.strava.com/settings/api
     (Authorization Callback Domain can just be `localhost`).
  2. Put the Client ID and Client Secret in .env (or you'll be prompted).
  3. Run this script. It opens an authorize URL; you approve in the browser.
  4. Strava redirects to http://localhost/?code=...  — the page won't load,
     that's fine. Copy the `code` value out of the address bar and paste it here.
  5. It prints your STRAVA_REFRESH_TOKEN. Paste that into .env.

Usage:  python strava_auth.py
"""

import os
import sys
import urllib.parse
import webbrowser

import requests

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
REDIRECT_URI = "http://localhost"
# activity:read_all also covers private/manual activities.
SCOPE = "activity:read_all"


def prompt(name, env_key):
    val = os.environ.get(env_key)
    if val:
        return val
    return input(f"Enter your Strava {name} ({env_key}): ").strip()


def main():
    client_id = prompt("Client ID", "STRAVA_CLIENT_ID")
    client_secret = prompt("Client Secret", "STRAVA_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Client ID and Client Secret are required.", file=sys.stderr)
        return 1

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPE,
    }
    auth_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    print("\n1) Opening this URL in your browser (approve access):\n")
    print("   " + auth_url + "\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass
    print("2) After approving, your browser goes to a http://localhost/?...&code=XXXX&...")
    print("   page that fails to load — that's expected. Copy the `code` value.\n")

    code = input("Paste the code here: ").strip()
    if not code:
        print("No code provided.", file=sys.stderr)
        return 1

    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    }, timeout=30)
    if resp.status_code != 200:
        print(f"\nToken exchange failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    refresh = data.get("refresh_token")
    athlete = data.get("athlete", {})
    name = f"{athlete.get('firstname','')} {athlete.get('lastname','')}".strip()

    print("\n" + "=" * 60)
    print(f"Success! Authorized as: {name or 'your account'}")
    print("Add this line to your .env file:\n")
    print(f"    STRAVA_REFRESH_TOKEN={refresh}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
