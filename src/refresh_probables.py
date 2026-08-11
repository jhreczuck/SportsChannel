r"""
refresh_probables.py

Fetches today's MLB probable starting pitchers from ESPN's scoreboard endpoint
(the same one ticker.py uses for scores) and writes data/probables.json,
grouped by league (AL/NL) per mlb_divisions.py.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_probables.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from mlb_divisions import league_for
from mlb_season import is_mlb_season

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROBABLES_PATH = DATA_DIR / "probables.json"

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"


def _probable_str(competitor: Dict[str, Any]) -> str:
    probs = competitor.get("probables") or []
    if not probs:
        return "TBD"
    p = probs[0]
    name = p.get("athlete", {}).get("shortName") or p.get("athlete", {}).get("displayName") or "TBD"
    stats = {s.get("name"): s.get("displayValue") for s in p.get("statistics", [])}
    wins = stats.get("wins")
    losses = stats.get("losses")
    if wins is not None and losses is not None:
        return f"{name} {wins}-{losses}"
    return name


def fetch_probables() -> Dict[str, List[Dict[str, Any]]]:
    """Returns {"AL": [games...], "NL": [games...]}, each game a dict of
    away/home team + probable pitcher strings."""
    leagues: Dict[str, List[Dict[str, Any]]] = {"AL": [], "NL": []}

    resp = requests.get(SCOREBOARD_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    for event in data.get("events", []):
        try:
            comp = event["competitions"][0]
            competitors = comp["competitors"]
            home = next(c for c in competitors if c.get("homeAway") == "home")
            away = next(c for c in competitors if c.get("homeAway") == "away")

            home_abbr = home.get("team", {}).get("abbreviation", "")
            away_abbr = away.get("team", {}).get("abbreviation", "")

            # Games are cross-league (interleague) sometimes; file under the
            # home team's league, matching how the original broadcast would
            # have listed "at [home city]" under that team's league board.
            league = league_for(home_abbr)
            if league is None:
                continue

            game = {
                "away": away.get("team", {}).get("location", away_abbr),
                "away_pitcher": _probable_str(away),
                "home": home.get("team", {}).get("location", home_abbr),
                "home_pitcher": _probable_str(home),
            }
            leagues[league].append(game)
        except Exception:
            continue

    return leagues


def main() -> None:
    in_season = is_mlb_season()

    leagues_data: Dict[str, List[Dict[str, Any]]] = {"AL": [], "NL": []}
    if in_season:
        try:
            leagues_data = fetch_probables()
        except Exception as e:
            print(f"[refresh_probables] Fetch failed: {e}")

    today_label = datetime.now().strftime("%A") + "'s"

    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "in_season": in_season,
        "date_label": today_label,
        "leagues": [
            {"name": name, "games": games}
            for name, games in leagues_data.items()
        ],
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROBABLES_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    total_games = sum(len(l["games"]) for l in wrapper["leagues"])
    print(f"[refresh_probables] in_season={in_season}, wrote {total_games} games to {PROBABLES_PATH}")


if __name__ == "__main__":
    main()
