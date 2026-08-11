r"""
refresh_nfl_standings.py

Fetches current NFL division standings from ESPN's standings API (level=3
returns all 8 divisions directly) and writes data/nfl_standings.json.
Mirrors refresh_standings.py (MLB), but NFL has 8 divisions (not 6) and a
ties column MLB doesn't have.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_nfl_standings.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

from league_seasons import active_leagues

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STANDINGS_PATH = DATA_DIR / "nfl_standings.json"

STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/football/nfl/standings?level=3"


def _team_row(entry: Dict[str, Any]) -> Dict[str, str]:
    stats = {s.get("name"): s.get("displayValue") for s in entry.get("stats", [])}
    return {
        "name": entry.get("team", {}).get("shortDisplayName", ""),
        "w": stats.get("wins", ""),
        "l": stats.get("losses", ""),
        "t": stats.get("ties", ""),
        "pct": stats.get("winPercent", ""),
        "gb": stats.get("gamesBehind", ""),
    }


def fetch_standings() -> List[Dict[str, Any]]:
    """Returns all 8 division standings blocks, AFC then NFC, East/North/South/West order."""
    resp = requests.get(STANDINGS_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    divisions: List[Dict[str, Any]] = []
    for conference in data.get("children", []):
        for division in conference.get("children", []):
            entries = division.get("standings", {}).get("entries", [])
            divisions.append({
                "name": division.get("name", ""),
                "teams": [_team_row(e) for e in entries],
            })
    return divisions


def main() -> None:
    in_season = "nfl" in active_leagues()

    divisions: List[Dict[str, Any]] = []
    if in_season:
        try:
            divisions = fetch_standings()
        except Exception as e:
            print(f"[refresh_nfl_standings] Fetch failed: {e}")

    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "in_season": in_season,
        "sport": "nfl",
        "divisions": divisions,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STANDINGS_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[refresh_nfl_standings] in_season={in_season}, wrote {len(divisions)} divisions to {STANDINGS_PATH}")


if __name__ == "__main__":
    main()
