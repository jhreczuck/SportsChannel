"""
sportsdata_test.py
Simple SportsDataIO test script for Sportschannel project.

What it does:
- Loads SPORTSDATAIO_API_KEY and SPORTSDATAIO_LEAGUE from .env
- Calls one SportsDataIO endpoint for today's games for that league
- Prints a few cleaned-up lines suitable for a ticker

This script does NOT use pygame. It's just a feed test you run in the terminal.

Usage (from project root, with venv active):
    python src\sportsdata_test.py
"""

import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# ------------------------
# Config
# ------------------------

BASE_URLS = {
    "nba": "https://api.sportsdata.io/v3/nba/scores/json/ScoresBasicFinal/{date}",
    "mlb": "https://api.sportsdata.io/v3/mlb/scores/json/ScoresBasicFinal/{date}",
    "nhl": "https://api.sportsdata.io/v3/nhl/scores/json/GamesByDate/2025-DEC-05",
    "nfl": "https://api.sportsdata.io/v3/nfl/scores/json/ScoresBasicFinal/2025/12"
    # NOTE: NFL uses different patterns (season/week) – we'll handle that later.
}

def load_config():
    """Load API key and league from .env"""
    base = Path(__file__).resolve().parent.parent
    env_path = base / ".env"
    load_dotenv(env_path)

    api_key = os.getenv("SPORTSDATAIO_API_KEY")
    league = os.getenv("SPORTSDATAIO_LEAGUE", "nba").lower()

    if not api_key:
        raise RuntimeError("SPORTSDATAIO_API_KEY not set in .env")
    if league not in BASE_URLS:
        raise RuntimeError(f"Unsupported league '{league}'. Supported: {', '.join(BASE_URLS.keys())}")

    return api_key, league


def build_url(league: str) -> str:
    """Build a URL for 'today' for date-based leagues."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    template = BASE_URLS[league]
    return template.format(date=today)


def fetch_games(api_key: str, league: str):
    """Fetch games from SportsDataIO for the given league."""
    url = build_url(league)
    headers = {
        "Ocp-Apim-Subscription-Key": api_key
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data


def format_game_line(league: str, game: dict) -> str:
    """Turn a single game JSON object into a ticker-style line."""
    lg = league.upper()

    home = game.get("HomeTeam") or game.get("HomeTeamName") or "HOME"
    away = game.get("AwayTeam") or game.get("AwayTeamName") or "AWAY"

    home_score = game.get("HomeTeamScore")
    away_score = game.get("AwayTeamScore")

    status = (game.get("Status") or "").upper()
    quarter = game.get("Quarter") or ""
    time_rem = game.get("TimeRemaining") or game.get("TimeRemainingMinutes") or ""

    # Normalize status
    if status == "FINAL":
        status_str = "F"
    elif status == "INPROGRESS":
        status_str = "LIVE"
    else:
        status_str = status

    # Build core score part
    if home_score is not None and away_score is not None:
        score_part = f"{away} {away_score} – {home} {home_score}"
    else:
        score_part = f"{away} @ {home}"

    # Append clock/period if available
    extra = ""
    if quarter and time_rem:
        extra = f" {quarter} {time_rem}"
    elif quarter:
        extra = f" {quarter}"
    elif status_str and status_str not in ("F", ""):
        extra = f" {status_str}"

    # Final format
    if status_str == "F":
        return f"{lg}: {score_part} F"
    elif status_str:
        return f"{lg}: {score_part}{extra}"
    else:
        return f"{lg}: {score_part}"


def main():
    try:
        api_key, league = load_config()
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        print("Make sure you have a .env file with SPORTSDATAIO_API_KEY and SPORTSDATAIO_LEAGUE set.")
        return

    print(f"[INFO] Using league='{league.upper()}'")
    try:
        games = fetch_games(api_key, league)
    except Exception as e:
        print(f"[ERROR] Failed to fetch games: {e}")
        return

    if not games:
        print("[INFO] No games returned for today.")
        return

    print(f"[INFO] Received {len(games)} games")
    print("--- Sample ticker lines ---")
    count = 0
    for g in games:
        line = format_game_line(league, g)
        print(" ", line)
        count += 1
        if count >= 10:
            break


if __name__ == "__main__":
    main()
