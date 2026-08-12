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

For MLB only, also fetches the winning/losing/save pitcher per game from
ESPN's per-event summary endpoint (not available on the scoreboard endpoint
itself) -- verified live: boxscore.players[team].statistics[pitching group]
.athletes[i].notes carries a {"type": "pitchingDecision", "text": "W, 6-8"}
style entry per pitcher who factored in the decision. This is one extra
HTTP request per game (summary?event=<id>), so it's skipped for NFL, which
has no equivalent pitcher-decision concept.

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

MLB_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary"

SEARCH_DAYS_BACK = 10


def _fetch_pitching_decisions(event_id: str) -> Dict[str, str]:
    """Returns {"win": "Z. Matthews, 6-8", "loss": "S. Baz, 4-12",
    "save": "Y. Gomez, 17"} for whichever decisions are present -- a game
    can lack a save (no reliever finished it out)."""
    decisions: Dict[str, str] = {}
    try:
        resp = requests.get(MLB_SUMMARY_URL, params={"event": event_id}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return decisions

    label_by_code = {"W": "win", "L": "loss", "S": "save"}
    for team in data.get("boxscore", {}).get("players", []):
        for stat_group in team.get("statistics", []):
            if (stat_group.get("labels") or [None])[0] != "IP":
                continue
            for athlete_entry in stat_group.get("athletes", []):
                for note in athlete_entry.get("notes") or []:
                    if note.get("type") != "pitchingDecision":
                        continue
                    text = note.get("text") or ""
                    code = text.split(",")[0].strip()
                    key = label_by_code.get(code)
                    if not key or key in decisions:
                        continue
                    name = athlete_entry.get("athlete", {}).get("shortName", "")
                    record = text.split(",", 1)[1].strip() if "," in text else ""
                    decisions[key] = f"{name}, {record}" if record else name
    return decisions


def _final_games(url: str, date_str: str, league: str) -> List[Dict[str, Any]]:
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
            game = {
                "away": away.get("team", {}).get("location", ""),
                "away_score": away.get("score", ""),
                "home": home.get("team", {}).get("location", ""),
                "home_score": home.get("score", ""),
            }
            if league == "mlb":
                decisions = _fetch_pitching_decisions(event["id"])
                if decisions.get("win"):
                    game["winning_pitcher"] = decisions["win"]
                if decisions.get("loss"):
                    game["losing_pitcher"] = decisions["loss"]
                if decisions.get("save"):
                    game["save_pitcher"] = decisions["save"]
            games.append(game)
        except Exception:
            continue
    return games


def fetch_recent_results(url: str, league: str) -> Optional[Dict[str, Any]]:
    """Walks backward from today until a day with at least one final game is
    found. Returns {"day_label": "Monday's", "games": [...]}, or None if
    nothing found within SEARCH_DAYS_BACK."""
    today = datetime.now()
    for days_back in range(SEARCH_DAYS_BACK):
        day = today - timedelta(days=days_back)
        games = _final_games(url, day.strftime("%Y%m%d"), league)
        if games:
            return {"day_label": f"{day.strftime('%A')}'s", "games": games}
    return None


def main() -> None:
    results: Dict[str, Any] = {}
    for league, url in SCOREBOARD_URLS.items():
        try:
            result = fetch_recent_results(url, league)
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
