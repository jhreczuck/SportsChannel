r"""
refresh_score_results.py

Fetches the most recent day's final scores per league (NFL, MLB) from
ESPN's scoreboard and writes data/score_results.json -- "Monday's NFL
Result(s)" style board, shown right after each league's Section Intro card.

Searches backward day-by-day (up to SEARCH_DAYS_BACK) for the most recent
date with at least one STATUS_FINAL game, since during gaps between
game days (e.g. the week-plus gap between NFL preseason openers) "yesterday"
may have nothing -- confirmed live: NFL's most recent finals were a full
week back during this preseason window, while MLB had 15 the very next day.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_score_results.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SCORE_RESULTS_PATH = DATA_DIR / "score_results.json"

SCOREBOARD_URLS = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
}

SEARCH_DAYS_BACK = 10


def _final_games(url: str, date_str: str) -> List[Dict[str, Any]]:
    resp = requests.get(url, params={"dates": date_str}, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    games: List[Dict[str, Any]] = []
    for event in data.get("events", []):
        try:
            comp = event["competitions"][0]
            if comp["status"]["type"]["name"] != "STATUS_FINAL":
                continue
            competitors = comp["competitors"]
            home = next(c for c in competitors if c.get("homeAway") == "home")
            away = next(c for c in competitors if c.get("homeAway") == "away")
            games.append({
                "away": away.get("team", {}).get("location", ""),
                "away_score": away.get("score", ""),
                "home": home.get("team", {}).get("location", ""),
                "home_score": home.get("score", ""),
            })
        except Exception:
            continue
    return games


def fetch_recent_results(url: str) -> Optional[Dict[str, Any]]:
    """Walks backward from today until a day with at least one final game is
    found. Returns {"day_label": "Monday's", "games": [...]}, or None if
    nothing found within SEARCH_DAYS_BACK."""
    today = datetime.now()
    for days_back in range(SEARCH_DAYS_BACK):
        day = today - timedelta(days=days_back)
        games = _final_games(url, day.strftime("%Y%m%d"))
        if games:
            return {"day_label": f"{day.strftime('%A')}'s", "games": games}
    return None


def main() -> None:
    results: Dict[str, Any] = {}
    for league, url in SCOREBOARD_URLS.items():
        try:
            result = fetch_recent_results(url)
        except Exception as e:
            print(f"[refresh_score_results] Fetch failed for {league}: {e}")
            result = None
        results[league] = result
        if result:
            print(f"[refresh_score_results] {league.upper()}: {result['day_label']} -- {len(result['games'])} games")
        else:
            print(f"[refresh_score_results] {league.upper()}: no results found in the last {SEARCH_DAYS_BACK} days")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    SCORE_RESULTS_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
