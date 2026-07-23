"""
news_feed.py

Fetch short sports news snippets from Yahoo Sports RSS feeds for the
four major US leagues: NFL, NBA, MLB, NHL.

Changes vs previous version:
- Removed title and link from public data structure
- Now returns richer multi-sentence text snippets
- Uses <content:encoded> when available for more context
- Still optionally attaches a league logo path if a matching PNG exists
  under ./media/logos/{sport}.png (e.g., nfl.png, nba.png, ...)
- If the logo file does NOT exist, it simply sets logo_path=None and
  continues without breaking.

Public usage:

    from news_feed import get_latest_news

    items = get_latest_news(max_per_sport=5)
    for item in items:
        print(item.sport, item.text, item.logo_path)

Later, you can extend this to per-team logos instead of league logos.
"""
from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List, Optional, Dict

import requests
import xml.etree.ElementTree as ET


# ---------------------------
# Config
# ---------------------------

# Yahoo Sports RSS feeds for the four major US leagues
SPORT_FEEDS: Dict[str, str] = {
    "nfl": "https://sports.yahoo.com/nfl/rss.xml",
    #"nba": "https://sports.yahoo.com/nba/rss.xml",
    #"mlb": "https://sports.yahoo.com/mlb/rss.xml",
    #"nhl": "https://sports.yahoo.com/nhl/rss.xml",
}

# Base directory for league logos.
# Expected optional files (not required to exist):
#   media/logos/nfl.png
#   media/logos/nba.png
#   media/logos/mlb.png
#   media/logos/nhl.png
BASE_DIR = Path(__file__).resolve().parent
LOGO_DIR = BASE_DIR / "media" / "logos"


@dataclass
class NewsItem:
    sport: str                 # "nfl", "nba", "mlb", "nhl"
    category: Optional[str]    # optional category parsed from <category>
    text: str                  # multi-sentence snippet
    published: Optional[datetime]
    logo_path: Optional[Path]  # Optional local logo file; None if not found


# ---------------------------
# Helpers
# ---------------------------

def _clean_html(raw: str) -> str:
    """
    Strip basic HTML tags and unescape entities.

    This is intentionally simple; for Yahoo's RSS descriptions / content,
    it is more than enough.
    """
    if not raw:
        return ""
    # unescape HTML entities (&amp;, &quot;, etc.)
    text = html.unescape(raw)
    # remove tags
    text = re.sub(r"<.*?>", "", text)
    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_pubdate(pubdate: Optional[str]) -> Optional[datetime]:
    if not pubdate:
        return None
    try:
        dt = parsedate_to_datetime(pubdate)
        # Normalize to aware UTC if it's naive
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _fetch_rss(url: str, timeout: float = 10.0) -> str:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _get_logo_for_sport(sport: str) -> Optional[Path]:
    """
    Try to find a league logo file for the given sport.
    If it doesn't exist, return None and do NOT raise.

    Expected path: ./media/logos/{sport}.png
    Example: ./media/logos/nfl.png
    """
    candidate = LOGO_DIR / f"{sport.lower()}.png"
    if candidate.exists():
        return candidate
    return None


def _extract_snippet_from_item(item: ET.Element) -> str:
    """
    Build a multi-sentence text snippet from an <item> element:

    1) Prefer <content:encoded> (fuller HTML article teaser)
    2) Fallback to <description>
    3) Strip HTML, unescape entities
    4) Take the first 2–3 sentences for a concise summary
    """
    description_raw = item.findtext("description") or ""

    # Try to get <content:encoded> for longer text
    content_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
    if content_el is not None and content_el.text:
        raw_text = content_el.text
    else:
        raw_text = description_raw  # fallback

    cleaned = _clean_html(raw_text)

    # Split into sentences; this is heuristic but fine for display
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    # Choose up to 3 sentences
    snippet = " ".join(s for s in sentences[:3] if s).strip()

    return snippet


def _parse_rss_items(sport: str, xml_text: str) -> List[NewsItem]:
    """
    Parse an RSS XML string for a given sport into NewsItem objects.
    """
    items: List[NewsItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"[news_feed] XML parse error for {sport}: {e}", file=sys.stderr)
        return items

    # RSS structure: <rss><channel><item>...</item></channel></rss>
    channel = root.find("channel")
    if channel is None:
        return items

    logo_path = _get_logo_for_sport(sport)

    for item in channel.findall("item"):
        pubdate_raw = item.findtext("pubDate")
        published = _parse_pubdate(pubdate_raw)

        # Parse category if present
        category_raw = item.findtext("category")
        category = _clean_html(category_raw).strip() if category_raw else None

        # Title-based exclusion: skip items whose title contains "fantasy" (case-insensitive)
        title_raw = item.findtext("title") or ""
        title_clean = _clean_html(title_raw).lower()
        if "fantasy" in title_clean:
            # quietly skip fantasy-related posts
            #print(f"[news_feed] Skipping item with fantasy in title: {title_raw}", file=sys.stderr)
            continue

        text = _extract_snippet_from_item(item)
        if not text:
            # skip completely empty items
            continue

        ni = NewsItem(
            sport=sport,
            category=category,
            text=text,
            published=published,
            logo_path=logo_path,
        )
        items.append(ni)

    return items


# ---------------------------
# Public API
# ---------------------------

def fetch_sport_news(sport: str, max_items: int | None = None) -> List[NewsItem]:
    """
    Fetch news items for a single sport key ("nfl", "nba", "mlb", "nhl").

    - max_items: optional cap per feed.
    """
    sport_lower = sport.lower()
    if sport_lower not in SPORT_FEEDS:
        raise ValueError(f"Unknown sport key: {sport} (expected one of {list(SPORT_FEEDS)})")

    url = SPORT_FEEDS[sport_lower]
    try:
        xml_text = _fetch_rss(url)
    except Exception as e:
        print(f"[news_feed] Error fetching RSS for {sport_lower}: {e}", file=sys.stderr)
        return []

    items = _parse_rss_items(sport_lower, xml_text)
    if max_items is not None:
        items = items[:max_items]
    return items


def get_latest_news(max_per_sport: int = 10) -> List[NewsItem]:
    """
    Fetch latest news from all configured sports.

    - max_per_sport: maximum items per sport feed.
    - Returns a single combined list, sorted by published datetime (desc).
      Items without a publish date are pushed to the end.
    """
    all_items: List[NewsItem] = []

    for sport in SPORT_FEEDS.keys():
        items = fetch_sport_news(sport, max_items=max_per_sport)
        all_items.extend(items)

    # Sort by published timestamp (most recent first).
    # Items with None published date go last.
    def sort_key(item: NewsItem):
        return item.published or datetime.min.replace(tzinfo=timezone.utc)

    all_items.sort(key=sort_key, reverse=True)
    return all_items


# ---------------------------
# CLI test
# ---------------------------

def _demo_print(max_per_sport: int = 3) -> None:
    """
    Simple CLI test: fetch a few items per sport and print them.
    """
    print(f"Fetching up to {max_per_sport} items per sport from Yahoo Sports RSS...\n")
    items = get_latest_news(max_per_sport=max_per_sport)
    for item in items:
        ts = item.published.isoformat() if item.published else "Unknown time"
        logo_str = str(item.logo_path) if item.logo_path else "None"
        print(f"[{item.sport.upper()}] {ts}")
        print(f"   {item.text}")
        print(f"   logo: {logo_str}")
        print("-" * 80)


if __name__ == "__main__":
    _demo_print(max_per_sport=3)
