r"""
refresh_history.py

Fetches real "on this day in sports history" facts from onthisday.com/sport
for today's date and picks one, writing data/history.json.

Two sources are scraped from the page:
- "Highlighted" entries (onthisday.com's own featured picks for the date,
  each with a photo) -- a real editorial notability signal.
- Plain list entries (everything else for the date).

Picks the best candidate by score: highlighted entries start ahead of plain
ones, and any entry naming an unmistakably famous athlete (Ruth, Ali,
Jordan, etc. -- see FAMOUS_ATHLETES) gets a further boost, so a slam-dunk
pick like "Babe Ruth hits his 600th home run" wins over a more obscure
plain-list item, matching how a person would actually choose.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_history.py
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
HISTORY_PATH = DATA_DIR / "history.json"

BASE_URL = "https://www.onthisday.com/sport/events"
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

# Skip anything older than this -- pre-1929 sports trivia (Victorian cricket
# stumping records, etc.) doesn't fit the vibe.
MIN_YEAR = 1929

# Athletes famous enough that a fact mentioning them should win over a more
# obscure one, even if the obscure one happens to be a plain (non-highlighted)
# list entry. Deliberately short and top-tier only -- this is a tie-breaker,
# not an attempt at a comprehensive database.
FAMOUS_ATHLETES = [
    "babe ruth", "muhammad ali", "michael jordan", "wayne gretzky",
    "jackie robinson", "jesse owens", "tiger woods", "serena williams",
    "hank aaron", "joe dimaggio", "willie mays", "lou gehrig",
    "tom brady", "michael phelps", "usain bolt", "lebron james",
    "mickey mantle", "pele", "magic johnson", "larry bird",
    "wilt chamberlain", "jim brown", "walter payton", "joe montana",
]

_LI_RE = re.compile(
    r'<li class="event"><a href="/sport/events/date/(\d{4})" class="date">\d{4}</a>\s*'
    r'([^<]+(?:<a[^>]*>[^<]*</a>[^<]*)*)</li>'
)
_POI_RE = re.compile(
    r'section--poi.*?<p><a href="/sport/events/date/(\d{4})" class="date">\d{4}</a>\s*'
    r'([^<]+(?:<a[^>]*>[^<]*</a>[^<]*)*)</p>',
    re.S,
)


def _strip_tags(html_fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", html_fragment)
    text = text.replace("&#039;", "'").replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r"\s{2,}", " ", text).strip()


def fetch_candidates(month: str, day: int) -> List[Dict[str, Any]]:
    resp = requests.get(f"{BASE_URL}/{month}/{day}", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    html = resp.text

    candidates: List[Dict[str, Any]] = []
    for year, fragment in _POI_RE.findall(html):
        candidates.append({"year": year, "text": _strip_tags(fragment), "highlighted": True})
    for year, fragment in _LI_RE.findall(html):
        candidates.append({"year": year, "text": _strip_tags(fragment), "highlighted": False})
    return candidates


def score(candidate: Dict[str, Any]) -> int:
    s = 1 if candidate["highlighted"] else 0
    text_lower = candidate["text"].lower()
    if any(name in text_lower for name in FAMOUS_ATHLETES):
        s += 5
    return s


def pick_best(candidates: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    candidates = [c for c in candidates if int(c["year"]) >= MIN_YEAR]
    if not candidates:
        return None
    best_score = max(score(c) for c in candidates)
    top = [c for c in candidates if score(c) == best_score]
    return random.choice(top)


def main() -> None:
    today = datetime.now()
    month = MONTH_NAMES[today.month - 1]

    fact = None
    try:
        candidates = fetch_candidates(month, today.day)
        fact = pick_best(candidates)
    except Exception as e:
        print(f"[refresh_history] Fetch failed: {e}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date_label": f"{today.strftime('%A, %b')} {today.day}",  # avoid %-d (not portable to Windows)
        "fact": fact,
    }
    HISTORY_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    if fact:
        print(f"[refresh_history] Picked {fact['year']}: {fact['text'][:80]}")
    else:
        print("[refresh_history] No fact found/available for today")


if __name__ == "__main__":
    main()
