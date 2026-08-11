r"""
refresh_birthdays.py

Fetches real sports birthdays for today's date from onthisday.com/sport and
picks a couple, writing data/birthdays.json. Same site/scraping approach as
refresh_history.py.

Critical filter: onthisday.com's birthday list includes people regardless of
whether they're still alive -- entries for the deceased are marked "(d.
YYYY)". Those are excluded entirely, since a birthday board can't say a dead
person "turns 56".

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_birthdays.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BIRTHDAYS_PATH = DATA_DIR / "birthdays.json"

BASE_URL = "https://www.onthisday.com/sport/birthdays"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

MAX_PEOPLE = 2  # matches the reference broadcast's density (2 per screen)

# Only consider people born in/after this year -- keeps the board to
# current-ish athletes rather than, say, a 90-year-old former cricketer.
MIN_BIRTH_YEAR = 1980

# Prefer the major US sports this app already covers; a person matching one
# of these is more likely to be recognizable to a viewer than an obscure
# cricket/rugby figure the source site also carries.
MAJOR_SPORT_KEYWORDS = ["nfl", "football", "mlb", "baseball", "nba", "basketball", "nhl", "hockey"]

_LI_RE = re.compile(
    r'<li class="person">(?:<a[^>]*class="birthDate">(\d{4})</a>|<b>(\d{4})</b>)\s*'
    r'([^<]+(?:<[^>]+>[^<]*</[^>]+>[^<]*)*)</li>'
)


def _strip_tags(html_fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", html_fragment)
    text = text.replace("&#039;", "'").replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r"\s{2,}", " ", text).strip()


def _split_name_and_desc(text: str) -> tuple[str, str]:
    """
    Raw format: "Name, description (extra detail), born in City".
    Pull the name (before the first comma) and a short description (between
    the first comma and the first '(' or the next comma, whichever is
    first).
    """
    if "," not in text:
        return text.strip(), ""
    name, rest = text.split(",", 1)
    rest = rest.strip()
    cut = min([i for i in (rest.find("("), rest.find(",")) if i != -1] or [len(rest)])
    return name.strip(), rest[:cut].strip()


def fetch_candidates(month: str, day: int) -> List[Dict[str, Any]]:
    resp = requests.get(f"{BASE_URL}/{month}/{day}", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    html = resp.text

    candidates: List[Dict[str, Any]] = []
    for y1, y2, fragment in _LI_RE.findall(html):
        text = _strip_tags(fragment)
        if "(d." in text:
            continue  # deceased -- can't have a birthday
        year = int(y1 or y2)
        name, desc = _split_name_and_desc(text)
        if not name:
            continue
        candidates.append({"year": year, "name": name, "desc": desc})
    return candidates


def score(candidate: Dict[str, Any]) -> int:
    desc_lower = candidate["desc"].lower()
    return 1 if any(k in desc_lower for k in MAJOR_SPORT_KEYWORDS) else 0


def pick_people(candidates: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
    candidates = [c for c in candidates if c["year"] >= MIN_BIRTH_YEAR]
    ranked = sorted(candidates, key=score, reverse=True)
    return ranked[:count]


def main() -> None:
    today = datetime.now()
    month = MONTH_NAMES[today.month - 1]
    current_year = today.year

    people: List[Dict[str, Any]] = []
    try:
        candidates = fetch_candidates(month, today.day)
        picked = pick_people(candidates, MAX_PEOPLE)
        for c in picked:
            people.append({
                "name": c["name"].upper(),
                "desc": c["desc"],
                "age": current_year - c["year"],
            })
    except Exception as e:
        print(f"[refresh_birthdays] Fetch failed: {e}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date_label": f"{today.strftime('%A, %b')} {today.day}",
        "people": people,
    }
    BIRTHDAYS_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[refresh_birthdays] Wrote {len(people)} people to {BIRTHDAYS_PATH}")


if __name__ == "__main__":
    main()
