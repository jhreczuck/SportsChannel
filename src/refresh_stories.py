r"""
refresh_stories.py

Fetches fresh sports news from Yahoo (via news_feed.py) and writes them into:
- data/stories.json (raw)
- data/stories_cleaned.json (GPT-cleaned)

Project layout assumed:

    C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\
        data\
            stories.json
            stories_cleaned.json
        src\
            main.py
            news_feed.py
            refresh_stories.py

Usage (run from anywhere):

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_stories.py

Optional env:

    MAX_PER_SPORT=5  python ...\refresh_stories.py

What we store per slide:

    {
      "title": "<original article headline, empty for (cont) continuation slides>",
      "body": "<multi-sentence text>",
      "logo": "cowboys.png" | null,
      "league": "nfl" | "nba" | ...,
      "logo_recommended": "nfl.png" | null
    }
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime
import re
import unicodedata

from gpt_cleaner import clean_article
import news_feed  # must live in the same src/ folder as this script


# Base directory is the project root, one level up from src/
# e.g. ...\Sportschannel\Sportschannel\
BASE_DIR = Path(__file__).resolve().parent.parent

# data directory lives alongside src/
DATA_DIR = BASE_DIR / "data"
STORIES_PATH = DATA_DIR / "stories.json"
CLEANED_STORIES_PATH = DATA_DIR / "stories_cleaned.json"
HEADLINES_PATH = DATA_DIR / "headlines.json"

# Which league's content shows first in the web rotation (stories, headlines).
LEAGUE_PRIORITY = ["mlb", "nfl"]

# Logos live here (used to validate inferred logo filenames)
MEDIA_LOGOS_DIR = BASE_DIR / "media" / "logos"

# If a story "item" is very short and looks like a continuation, merge it into the previous slide.
MERGE_CONTINUATION_MAX_LEN = 200

# Categories to exclude entirely from generated slides (normalized form).
# Example: "fantasyfootball" will exclude categories like "Fantasy Football",
# "fantasy-football", "fantasy_football", etc.
EXCLUDED_CATEGORIES = {"fantasyfootball"}


def infer_logo_from_text(text: str) -> str | None:
    """
    Infer a team logo filename from capitalized words in the text.
    Example: 'Cowboys' -> 'cowboys.png'
    Returns None if no matching logo file exists.
    """
    if not text:
        return None

    candidates = re.findall(r"\b[A-Z][a-z]+\b", text)
    for word in candidates:
        logo_name = f"{word.lower()}.png"
        if (MEDIA_LOGOS_DIR / logo_name).exists():
            return logo_name
    return None

def indent_paragraphs(text: str) -> str:
    """
    No-op: preserve original paragraph boundaries and do NOT insert tabs/newlines.
    Previously this function prefixed tabs to paragraphs; per request we must
    preserve only original newlines from the source. Return the input unchanged.
    """
    return text


def pick_trim_length(raw_len: int) -> int:
    """
    Cleaning length rules (target sized to the web panel's ~550-char capacity
    at the current 32px body font):
    - >1000 chars -> 1000
    - 550-750 chars -> 550
    - otherwise -> keep as-is (GPT still cleans)
    """
    if raw_len > 1000:
        return 1000
    if 550 <= raw_len <= 750:
        return 550
    return raw_len


def add_paragraph_breaks(text: str) -> str:
    """
    No-op: do not insert paragraph breaks. Preserve original newlines from source.
    """
    return text


def linefeed_and_indent_after_first_sentence(text: str) -> str:
    """
    No-op: do not insert a linefeed after the first sentence. Preserve original text.
    """
    return text

def style_body_text(text: str) -> str:
    """
    Apply final body styling rules and return cleaned text WITHOUT <<<INDENT>>> markers.
    """
    if not text:
        return ""

    # Insert a space after any '.' not followed by whitespace/end-of-string (but allow numeric decimals)
    t = re.sub(r"\.(?!\s|$|\d)", ". ", text)

    # Remove symbol characters (e.g., bullets) and control chars
    t = "".join(ch for ch in t if unicodedata.category(ch)[0] not in ("S", "C"))

    # Collapse multiple spaces and strip
    t = re.sub(r"\s{2,}", " ", t).strip()

    return t


def collapse_newlines(s: str) -> str:
    """
    Collapse multiple consecutive newlines into a single newline.
    Preserve original CRLF -> LF normalization.
    """
    if not s:
        return s
    t = s.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{2,}", "\n", t)

def mark_first_line(s: str) -> str:
    """
    Prefix the first non-blank line of s with the <<<INDENT>>> marker (if not already).
    Preserves blank lines and other content.
    """
    if not s:
        return s
    lines = s.splitlines()
    for i, l in enumerate(lines):
        if l.strip():
            if not l.startswith("<<<INDENT>>>"):
                lines[i] = "<<<INDENT>>>" + l
            break
    return "\n".join(lines)




def _maybe_merge_or_append(slides: List[Dict[str, Any]], slide: Dict[str, Any]) -> None:
    """
    Merge short "continuation fragments" into the previous slide when:
    - same league
    - same inferred logo
    - current body is short (<= MERGE_CONTINUATION_MAX_LEN)
    - neither body starts with "(cont)"
    """
    if not slides:
        slides.append(slide)
        return

    cur_body = (slide.get("body") or "").strip()
    prev_body = (slides[-1].get("body") or "").strip()

    if (
        cur_body
        and len(cur_body) <= MERGE_CONTINUATION_MAX_LEN
        and slides[-1].get("league") == slide.get("league")
        and slides[-1].get("logo") == slide.get("logo")
        and not prev_body.lstrip().startswith("(cont)")
        and not cur_body.lstrip().startswith("(cont)")
    ):
        # Merge with a single space separator; strip leading whitespace/tabs from current.
        merged = (prev_body.rstrip() + " " + cur_body.lstrip()).strip()
        # Collapse accidental double spaces
        merged = re.sub(r"\s{2,}", " ", merged)
        slides[-1]["body"] = merged
    else:
        slides.append(slide)


def build_slides_from_news(max_per_sport: int = 40) -> Dict[str, Any]:
    """
    Fetch latest news via news_feed.fetch_sport_news() and convert to the
    stories.json structure your main app expects, with extra metadata.
    """
    slides: List[Dict[str, Any]] = []
    per_sport_order = ["nfl", "mlb"]
    items: List[Any] = []

    for s in per_sport_order:
        try:
            fetched = news_feed.fetch_sport_news(s, max_items=max_per_sport)
            items.extend(fetched)
        except Exception as e:
            print(f"[refresh_stories] Warning: failed to fetch {s}: {e}")
            continue

    MAX_LEN = 550  # matches the web panel's ~550-char capacity at the current 32px body font
    MAX_EXCLUDE_LEN = 1000

    for item in items:
        raw_text = (getattr(item, "text", None) or "")
        # Convert literal escaped sequences (e.g. "\\n", "\\r\\n", "\\t") into actual characters
        # so subsequent newline normalization/collapse works on real newlines.
        raw_text = raw_text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
        text = style_body_text(raw_text)  # Apply styling once
        # Collapse multiple consecutive newlines into a single newline so slide bodies only have one blank line.
        text = collapse_newlines(text)

        if not text:
            continue

        league = (getattr(item, "sport", None) or "").lower() or None
        logo_recommended = f"{league}.png" if league else None
        inferred_logo = infer_logo_from_text(text)
        item_title = getattr(item, "title", "") or ""
        category = getattr(item, "category", None) or None

        # Normalize category for exclusion checks
        norm_cat = re.sub(r"\W+", "", category.lower()) if category else None
        if norm_cat and norm_cat in EXCLUDED_CATEGORIES:
            continue

        if len(text) > MAX_EXCLUDE_LEN:
            print(
                f"[refresh_stories] Skipping story (length {len(text)} > {MAX_EXCLUDE_LEN})"
            )
            continue

        if len(text) > MAX_LEN:
            # Split at the last natural break before MAX_LEN
            candidates = [".", ",", "-"]
            split_idx = -1
            for ch in candidates:
                i = text.rfind(ch, 0, MAX_LEN)
                if i > split_idx:
                    split_idx = i

            if split_idx == -1:
                # try earliest break after MAX_LEN
                earliest = None
                for ch in candidates:
                    i = text.find(ch, MAX_LEN)
                    if i != -1 and (earliest is None or i < earliest):
                        earliest = i
                if earliest is not None:
                    split_idx = earliest

            if split_idx == -1:
                split_idx = MAX_LEN
            else:
                split_idx += 1

            first_part = text[:split_idx].strip()
            rest = text[split_idx:].strip()

            # Normalize consecutive newlines so there is only one blank line between paragraphs.
            first_part = collapse_newlines(first_part)
            rest = collapse_newlines(rest)

            # DON'T call style_body_text again - it's already styled!
            # Mark only the first visible line with <<<INDENT>>> and append slides.
            first_slide = {
                "title": item_title,
                "body": mark_first_line(first_part),
                "logo": inferred_logo,
                "league": league,
                "logo_recommended": logo_recommended,
                "category": category,
            }
            _maybe_merge_or_append(slides, first_slide)

            if rest:
                cont_body = mark_first_line("(cont) " + rest)
                second_slide = {
                    "title": "",  # continuation of the slide above; headline already shown there
                    "body": cont_body,
                    "logo": inferred_logo,
                    "league": league,
                    "logo_recommended": logo_recommended,
                    "category": category,
                }
                _maybe_merge_or_append(slides, second_slide)
        else:
            # Collapse multiple consecutive newlines to a single newline
            text = collapse_newlines(text)
            slide = {
                "title": item_title,
                "body": mark_first_line(text),
                "logo": inferred_logo,
                "league": league,
                "logo_recommended": logo_recommended,
                "category": category,
            }
            _maybe_merge_or_append(slides, slide)

    return {"slides": slides}


def build_headlines(wrapper: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Pull one-line headlines straight from the RSS article titles already
    captured on each slide (see news_feed.NewsItem.title) -- no separate
    fetch or GPT cleaning needed, since these are already short. Ordered by
    LEAGUE_PRIORITY, de-duplicated (continuation slides have an empty title).
    """
    seen = set()
    headlines: List[Dict[str, str]] = []
    for league in LEAGUE_PRIORITY:
        for slide in wrapper.get("slides", []):
            title = (slide.get("title") or "").strip()
            if not title or slide.get("league") != league or title in seen:
                continue
            seen.add(title)
            headlines.append({"title": title, "league": league})
    return headlines


def clean_slides_with_gpt(wrapper: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reads the full stories.json-style wrapper, cleans slide bodies with GPT,
    and returns a new wrapper suitable for stories_cleaned.json.
    """
    slides = wrapper.get("slides", [])
    cleaned_slides: List[Dict[str, Any]] = []

    for idx, slide in enumerate(slides):
        body = (slide.get("body") or "")
        raw_len = len(body)
        target_len = pick_trim_length(raw_len)

        if not body.strip():
            cleaned_slides.append(slide)
            continue

        try:
            cleaned_body = clean_article(body, max_chars=target_len)
            # Collapse any consecutive newlines that may have been introduced by the cleaner
            cleaned_body = collapse_newlines(cleaned_body)
            print(
                f"[refresh_stories] GPT cleaned slide {idx + 1}: "
                f"{raw_len} -> {len(cleaned_body)} (limit {target_len})"
            )
        except Exception as e:
            print(f"[refresh_stories] GPT failed on slide {idx + 1}: {e}")
            # Ensure fallback also has normalized newlines
            cleaned_body = collapse_newlines(body)

        cleaned_slides.append({**slide, "body": cleaned_body})

    return {**wrapper, "slides": cleaned_slides}


def main() -> None:
    max_per_sport_env = os.getenv("MAX_PER_SPORT", "").strip()
    try:
        max_per_sport = int(max_per_sport_env) if max_per_sport_env else 40
    except ValueError:
        max_per_sport = 40

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    payload = build_slides_from_news(max_per_sport=max_per_sport)
    wrapper = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "yahoo_news_via_news_feed",
        "max_per_sport": max_per_sport,
        "slides": payload.get("slides", []),
    }

    STORIES_PATH.write_text(
        json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[refresh_stories] Wrote {len(wrapper['slides'])} slides to {STORIES_PATH}")

    headlines = build_headlines(wrapper)
    headlines_wrapper = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "headlines": headlines,
    }
    HEADLINES_PATH.write_text(
        json.dumps(headlines_wrapper, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[refresh_stories] Wrote {len(headlines)} headlines to {HEADLINES_PATH}")

    cleaned_wrapper = clean_slides_with_gpt(wrapper)
    CLEANED_STORIES_PATH.write_text(
        json.dumps(cleaned_wrapper, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"[refresh_stories] Wrote {len(cleaned_wrapper['slides'])} slides to {CLEANED_STORIES_PATH}"
    )


if __name__ == "__main__":
    main()
