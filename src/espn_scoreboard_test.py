"""
espn_scoreboard_test.py
Simple ESPN scoreboard test script for Sportschannel.

What it does:
- Calls ESPN's public scoreboard API (no API key required)
- Currently default: NFL
- Prints cleaned-up ticker-style lines

Usage (from project root, with venv active):
    python src\espn_scoreboard_test.py
"""

import requests

# You can change this to "basketball", "baseball", "hockey"
SPORT = "football"
LEAGUE = "nfl"
#            https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
BASE_URL = f"https://site.api.espn.com/apis/site/v2/sports/{SPORT}/{LEAGUE}/scoreboard"


def fetch_scoreboard():
    resp = requests.get(BASE_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


def format_event(event: dict) -> str:
    """
    Turn one ESPN event into a ticker line, e.g.:
      NFL: BUF 24 – HOU 20 F
    """
    competitions = event.get("competitions", [])
    if not competitions:
        return ""

    comp = competitions[0]
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return ""

    # Identify home/away
    home = None
    away = None
    for team in competitors:
        if team.get("homeAway") == "home":
            home = team
        elif team.get("homeAway") == "away":
            away = team

    if not home or not away:
        return ""

    def team_str(team):
        abbr = team.get("team", {}).get("abbreviation") or "TEAM"
        score = team.get("score") or ""
        return abbr, score

    away_abbr, away_score = team_str(away)
    home_abbr, home_score = team_str(home)

    # Status handling
    status_info = comp.get("status", {}).get("type", {})
    state = status_info.get("state", "").lower()   # in, pre, post
    short_detail = status_info.get("shortDetail", "")  # e.g. "FINAL", "Q4 5:23", etc.

    if state == "post":
        status_tag = "F"
    elif state == "in":
        status_tag = "LIVE"
    else:
        status_tag = ""

    # Build score presentation
    if away_score and home_score:
        score_part = f"{away_abbr} {away_score} – {home_abbr} {home_score}"
    else:
        score_part = f"{away_abbr} @ {home_abbr}"

    # Use ESPN's shortDetail when available
    extra = ""
    if short_detail:
        extra = f" {short_detail.upper()}"
    elif status_tag:
        extra = f" {status_tag}"

    return f"{LEAGUE.upper()}: {score_part}{extra}"


def main():
    print(f"[INFO] Fetching ESPN scoreboard: {BASE_URL}")
    try:
        data = fetch_scoreboard()
    except Exception as e:
        print(f"[ERROR] Failed to fetch scoreboard: {e}")
        return

    events = data.get("events", [])
    if not events:
        print("[INFO] No events found.")
        return

    print(f"[INFO] Found {len(events)} events")
    print("--- Sample ticker lines ---")
    count = 0
    for event in events:
        line = format_event(event)
        if not line:
            continue
        print(" ", line)
        count += 1
        if count >= 15:
            break


if __name__ == "__main__":
    main()
