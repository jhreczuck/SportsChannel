r"""
fetch_team_logos.py

Downloads team logos from ESPN's team-list API for NFL and MLB, saving them
into media/logos/ using the same {nickname}.png naming convention that
infer_logo_from_text() (in refresh_stories.py) already looks for -- e.g.
"49ers.png", "cowboys.png", "redsox.png".

Won't overwrite a file that already exists, so any hand-picked/custom art
you've already dropped in media/logos/ is left alone. Re-run any time to
fill in gaps.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\fetch_team_logos.py
"""
from __future__ import annotations

from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
LOGOS_DIR = BASE_DIR / "media" / "logos"

TEAMS_ENDPOINTS = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams",
    "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams",
}


def fetch_teams(league: str) -> list[dict]:
    resp = requests.get(TEAMS_ENDPOINTS[league], timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return [t["team"] for t in data["sports"][0]["leagues"][0]["teams"]]


def main() -> None:
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)

    downloaded, skipped, failed = 0, 0, 0

    for league in TEAMS_ENDPOINTS:
        try:
            teams = fetch_teams(league)
        except Exception as e:
            print(f"[fetch_team_logos] Failed to list {league.upper()} teams: {e}")
            continue

        for team in teams:
            nickname = (team.get("shortDisplayName") or "").strip()
            if not nickname:
                continue
            filename = nickname.lower().replace(" ", "") + ".png"
            dest = LOGOS_DIR / filename

            if dest.exists():
                skipped += 1
                continue

            logos = team.get("logos") or []
            if not logos:
                print(f"[fetch_team_logos] No logo available for {league.upper()} {nickname}")
                failed += 1
                continue

            url = logos[0]["href"]
            try:
                img_resp = requests.get(url, timeout=10)
                img_resp.raise_for_status()
                dest.write_bytes(img_resp.content)
                downloaded += 1
                print(f"[fetch_team_logos] Saved {filename} ({league.upper()})")
            except Exception as e:
                print(f"[fetch_team_logos] Failed to download {filename}: {e}")
                failed += 1

    print(f"[fetch_team_logos] Done. downloaded={downloaded} skipped(existing)={skipped} failed={failed}")


if __name__ == "__main__":
    main()
