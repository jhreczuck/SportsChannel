r"""
refresh_standings.py

Fetches current MLB division standings from ESPN's standings API (level=3
returns all 6 divisions directly) and writes data/standings.json.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_standings.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

from mlb_season import is_mlb_season

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STANDINGS_PATH = DATA_DIR / "standings.json"

STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings?level=3"


def _team_row(entry: Dict[str, Any]) -> Dict[str, str]:
    stats = {s.get("name"): s.get("displayValue") for s in entry.get("stats", [])}
    return {
        "name": entry.get("team", {}).get("shortDisplayName", ""),
        "w": stats.get("wins", ""),
        "l": stats.get("losses", ""),
        "pct": stats.get("winPercent", ""),
        "gb": stats.get("gamesBehind", ""),
    }


def fetch_standings() -> List[Dict[str, Any]]:
    """Returns a flat list of the 6 division standings blocks, in AL East,
    AL Central, AL West, NL East, NL Central, NL West order."""
    resp = requests.get(STANDINGS_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    divisions: List[Dict[str, Any]] = []
    for league in data.get("children", []):
        for division in league.get("children", []):
            entries = division.get("standings", {}).get("entries", [])
            divisions.append({
                "name": division.get("name", ""),
                "teams": [_team_row(e) for e in entries],
            })
    return divisions


def main() -> None:
    in_season = is_mlb_season()

    divisions: List[Dict[str, Any]] = []
    if in_season:
        try:
            divisions = fetch_standings()
        except Exception as e:
            print(f"[refresh_standings] Fetch failed: {e}")

    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "in_season": in_season,
        "divisions": divisions,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STANDINGS_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[refresh_standings] in_season={in_season}, wrote {len(divisions)} divisions to {STANDINGS_PATH}")


if __name__ == "__main__":
    main()
