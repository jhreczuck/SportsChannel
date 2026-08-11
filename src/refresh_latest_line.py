r"""
refresh_latest_line.py

Fetches upcoming NFL betting lines (favorite/spread/underdog) from ESPN's
scoreboard endpoint and writes data/latest_line.json, grouped by game day --
mirrors the "LATEST LINE" board from the original broadcast. No byline or
copyright line, per request.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_latest_line.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LATEST_LINE_PATH = DATA_DIR / "latest_line.json"

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
LOOKAHEAD_DAYS = 7


def _team_label(team: Dict[str, Any]) -> str:
    location = team.get("location", "")
    name = team.get("name", "")
    # Two NY teams share a city name; disambiguate like the reference board
    # ("NY Giants" / "NY Jets") instead of a bare, ambiguous "New York".
    if location == "New York":
        return f"NY {name}"
    return location or name


def fetch_latest_line() -> List[Dict[str, Any]]:
    today = datetime.now(timezone.utc)
    end = today + timedelta(days=LOOKAHEAD_DAYS)
    date_range = f"{today:%Y%m%d}-{end:%Y%m%d}"

    resp = requests.get(SCOREBOARD_URL, params={"dates": date_range}, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    games_by_day: Dict[str, List[Dict[str, Any]]] = {}

    for event in data.get("events", []):
        try:
            comp = event["competitions"][0]
            if comp["status"]["type"]["name"] != "STATUS_SCHEDULED":
                continue

            odds_list = comp.get("odds") or []
            if not odds_list:
                continue
            odds = odds_list[0]
            spread = odds.get("spread")
            if spread is None:
                continue

            competitors = comp["competitors"]
            home = next(c for c in competitors if c.get("homeAway") == "home")
            away = next(c for c in competitors if c.get("homeAway") == "away")

            home_is_favorite = bool(odds.get("homeTeamOdds", {}).get("favorite"))

            game = {
                "home": _team_label(home["team"]),
                "away": _team_label(away["team"]),
                "favorite": "home" if home_is_favorite else "away",
                "points": abs(spread),
            }

            game_date = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
            day_name = game_date.strftime("%A")
            games_by_day.setdefault(day_name, []).append(game)
        except Exception:
            continue

    # Preserve chronological day order rather than dict insertion order.
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    ordered_days = sorted(games_by_day.keys(), key=lambda d: day_order.index(d) if d in day_order else 99)

    return [{"day": d, "games": games_by_day[d]} for d in ordered_days]


def main() -> None:
    try:
        days = fetch_latest_line()
    except Exception as e:
        print(f"[refresh_latest_line] Fetch failed: {e}")
        days = []

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
    }
    LATEST_LINE_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    total_games = sum(len(d["games"]) for d in days)
    print(f"[refresh_latest_line] Wrote {total_games} games across {len(days)} days to {LATEST_LINE_PATH}")


if __name__ == "__main__":
    main()
