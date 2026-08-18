r"""
refresh_league_leaders.py

Fetches MLB batting/pitching stat leaders (Triple Crown categories, matching
the on-air standard for this project's 1988-93 retro broadcast era) split
into AL/NL, and writes data/league_leaders.json -- shown right after the
Standings board.

ESPN's site.api "statistics" endpoint looked like the obvious source but
turned out to be a rolling recent-games window, not season totals (verified
live: its HR "leader" had 7 HR in mid-August). Real season leaders live on
the core API instead: .../seasons/{year}/types/2/leaders, one call for all
categories at once. That endpoint returns athlete/team as $ref links rather
than embedded objects, so:
  - team abbreviation is resolved via a single upfront team-list fetch
    (_team_abbrevs), not a fetch per leader
  - athlete short names are resolved only for the ~10 leaders (5 AL + 5 NL)
    that actually make each category's final cut, cached by athlete id
    across categories (the same player often leads more than one category)

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_league_leaders.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from mlb_divisions import league_for
from mlb_season import is_mlb_season

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LEADERS_PATH = DATA_DIR / "league_leaders.json"

TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams"
LEADERS_URL_TMPL = (
    "https://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb/seasons/{year}/types/2/leaders"
)

# (ESPN category key, display name, short stat label)
CATEGORIES = [
    ("avg", "Batting Average", "AVG"),
    ("homeRuns", "Home Runs", "HR"),
    ("RBIs", "RBIs", "RBI"),
    ("wins", "Wins", "W"),
    ("ERA", "ERA", "ERA"),
    ("strikeouts", "Strikeouts", "SO"),
]

LEADERS_PER_LEAGUE = 5

_REF_ID_RE = re.compile(r"/(\d+)(?:\?|$)")


def _ref_id(ref_url: str) -> Optional[str]:
    match = _REF_ID_RE.search(ref_url.split("?")[0] + "?")
    return match.group(1) if match else None


def _team_abbrevs() -> Dict[str, str]:
    """One request for the full team list -- avoids resolving each leader's
    team $ref individually."""
    resp = requests.get(TEAMS_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    abbrevs: Dict[str, str] = {}
    for entry in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
        team = entry.get("team", {})
        if team.get("id"):
            abbrevs[team["id"]] = team.get("abbreviation", "")
    return abbrevs


def _athlete_short_name(ref_url: str, cache: Dict[str, str]) -> str:
    athlete_id = _ref_id(ref_url)
    if athlete_id and athlete_id in cache:
        return cache[athlete_id]
    try:
        resp = requests.get(ref_url, timeout=10)
        resp.raise_for_status()
        name = resp.json().get("shortName", "")
    except Exception:
        name = ""
    if athlete_id:
        cache[athlete_id] = name
    return name


def _format_value(category_key: str, value: float) -> str:
    if category_key in ("avg",):
        return f"{value:.3f}".lstrip("0")
    if category_key in ("ERA",):
        return f"{value:.2f}"
    return str(int(value))


def fetch_leaders() -> Dict[str, List[Dict[str, Any]]]:
    """Returns {"AL": [category dicts...], "NL": [category dicts...]}."""
    team_abbrevs = _team_abbrevs()

    year = datetime.now().year
    resp = requests.get(
        LEADERS_URL_TMPL.format(year=year),
        params={"limit": 30, "lang": "en", "region": "us"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    categories_by_key = {c.get("name"): c for c in data.get("categories", [])}

    athlete_name_cache: Dict[str, str] = {}
    leagues: Dict[str, List[Dict[str, Any]]] = {"AL": [], "NL": []}

    for key, display_name, short_label in CATEGORIES:
        category = categories_by_key.get(key)
        if not category:
            continue

        by_league: Dict[str, List[Dict[str, Any]]] = {"AL": [], "NL": []}
        for leader in category.get("leaders", []):
            if len(by_league["AL"]) >= LEADERS_PER_LEAGUE and len(by_league["NL"]) >= LEADERS_PER_LEAGUE:
                break
            team_ref = leader.get("team", {}).get("$ref", "")
            team_id = _ref_id(team_ref)
            abbr = team_abbrevs.get(team_id, "") if team_id else ""
            league = league_for(abbr) if abbr else None
            if league not in ("AL", "NL") or len(by_league[league]) >= LEADERS_PER_LEAGUE:
                continue
            by_league[league].append({
                "team": abbr,
                "value": leader.get("value"),
                "athlete_ref": leader.get("athlete", {}).get("$ref", ""),
            })

        for league_name, entries in by_league.items():
            rows = []
            for i, entry in enumerate(entries, start=1):
                name = _athlete_short_name(entry["athlete_ref"], athlete_name_cache) if entry["athlete_ref"] else ""
                rows.append({
                    "rank": i,
                    "name": name,
                    "team": entry["team"],
                    "display": _format_value(key, entry["value"]),
                })
            leagues[league_name].append({
                "key": key,
                "displayName": display_name,
                "label": short_label,
                "leaders": rows,
            })

    return leagues


def main() -> None:
    in_season = is_mlb_season()

    leagues_data: Dict[str, List[Dict[str, Any]]] = {"AL": [], "NL": []}
    if in_season:
        try:
            leagues_data = fetch_leaders()
        except Exception as e:
            print(f"[refresh_league_leaders] Fetch failed: {e}")

    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "in_season": in_season,
        "sport": "mlb",
        "leagues": [
            {"name": name, "categories": categories}
            for name, categories in leagues_data.items()
        ],
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LEADERS_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(len(c["leaders"]) for l in wrapper["leagues"] for c in l["categories"])
    print(f"[refresh_league_leaders] in_season={in_season}, wrote {total} leader rows to {LEADERS_PATH}")


if __name__ == "__main__":
    main()
