r"""
refresh_quotes.py

Fetches a real sports quote per league (MLB, NFL) from Goodreads' quote-tag
pages (e.g. goodreads.com/quotes/tag/baseball) and writes data/quotes.json.
Shown once after each league's block in the rotation.

Goodreads' tag pages mix genuine athlete/coach quotes (Babe Ruth, Vince
Lombardi) with loosely-tagged literary/commentary quotes (a humor columnist
riffing on football, etc.) that happen to share the tag. A curated list of
recognizable coaches/players per league (FAMOUS_BY_LEAGUE) is used to prefer
an actual sports-figure quote when one is available in the fetched batch,
same approach as refresh_history.py's FAMOUS_ATHLETES. Falls back to a
random pick from the batch if no famous-name match is found -- "related to
the league if possible", not guaranteed.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_quotes.py
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
QUOTES_PATH = DATA_DIR / "quotes.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Goodreads tag per league. "football" on Goodreads is dominated by American
# football (Lombardi, Manning, Rice) rather than soccer, which is what we
# want here.
TAG_BY_LEAGUE = {"mlb": "baseball", "nfl": "football"}

# Recognizable enough that a quote from them beats a generic
# loosely-tagged one, even though it's not exhaustive.
FAMOUS_BY_LEAGUE = {
    "mlb": [
        "babe ruth", "yogi berra", "jackie robinson", "hank aaron", "willie mays",
        "ted williams", "lou gehrig", "joe dimaggio", "derek jeter", "cal ripken",
        "mickey mantle", "satchel paige", "reggie jackson", "pete rose",
    ],
    "nfl": [
        "vince lombardi", "joe montana", "tom brady", "peyton manning", "jerry rice",
        "walter payton", "john madden", "bill belichick", "brett favre",
        "lawrence taylor", "jim brown", "troy aikman", "lou holtz",
    ],
}

_QUOTE_BLOCK_RE = re.compile(
    r'<div class="quote mediumText ">.*?</div>\s*</div>\s*<div class="action">', re.S
)
_AUTHOR_RE = re.compile(r'authorOrTitle">\s*([^<]+)')
_QUOTE_TEXT_RE = re.compile(r'quoteText">\s*&ldquo;(.*?)&rdquo;', re.S)

MAX_QUOTE_LEN = 200  # skip long literary passages; keep it broadcast-card sized


def _strip_tags(html_fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", html_fragment)
    text = text.replace("&#039;", "'").replace("&amp;", "&").replace("&quot;", '"')
    text = text.replace("&ldquo;", '"').replace("&rdquo;", '"').replace("&#8213;", "-")
    return re.sub(r"\s{2,}", " ", text).strip()


def fetch_candidates(tag: str) -> List[Dict[str, str]]:
    resp = requests.get(f"https://www.goodreads.com/quotes/tag/{tag}", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    html = resp.text

    candidates: List[Dict[str, str]] = []
    for block in _QUOTE_BLOCK_RE.findall(html):
        author_m = _AUTHOR_RE.search(block)
        quote_m = _QUOTE_TEXT_RE.search(block)
        if not author_m or not quote_m:
            continue
        author = _strip_tags(author_m.group(1))
        quote = _strip_tags(quote_m.group(1))
        if not author or not quote or len(quote) > MAX_QUOTE_LEN:
            continue
        candidates.append({"author": author, "quote": quote})
    return candidates


def pick_quote(candidates: List[Dict[str, str]], league: str) -> Optional[Dict[str, str]]:
    if not candidates:
        return None
    famous = FAMOUS_BY_LEAGUE.get(league, [])
    famous_matches = [c for c in candidates if c["author"].lower() in famous]
    pool = famous_matches if famous_matches else candidates
    return random.choice(pool)


def main() -> None:
    quotes: Dict[str, Any] = {}
    for league, tag in TAG_BY_LEAGUE.items():
        try:
            candidates = fetch_candidates(tag)
            quote = pick_quote(candidates, league)
        except Exception as e:
            print(f"[refresh_quotes] Fetch failed for {league}: {e}")
            quote = None
        quotes[league] = quote
        if quote:
            print(f"[refresh_quotes] {league.upper()}: {quote['author']} - {quote['quote'][:60]}")
        else:
            print(f"[refresh_quotes] {league.upper()}: no quote available")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quotes": quotes,
    }
    QUOTES_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
