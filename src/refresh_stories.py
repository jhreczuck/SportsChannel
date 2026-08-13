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
import league_seasons


# Base directory is the project root, one level up from src/
# e.g. ...\Sportschannel\Sportschannel\
BASE_DIR = Path(__file__).resolve().parent.parent

# data directory lives alongside src/
DATA_DIR = BASE_DIR / "data"
STORIES_PATH = DATA_DIR / "stories.json"
CLEANED_STORIES_PATH = DATA_DIR / "stories_cleaned.json"
HEADLINES_PATH = DATA_DIR / "headlines.json"

# Which league's content shows first in the web rotation (stories, headlines).
LEAGUE_PRIORITY = ["mlb", "nfl", "nba", "nhl"]

# Logos live here (used to validate inferred logo filenames)
MEDIA_LOGOS_DIR = BASE_DIR / "media" / "logos"

# True display capacity of one card: measured empirically in-browser at the
# real 36px body font against the actual panel width/height (13 lines fit;
# the first ~5 sit beside the logo column at the narrower width, the rest use
# the full panel width) -- came out to ~477 chars for realistic article
# prose. This replaced the previous MAX_LEN=480, which wasn't actually wrong
# as a capacity number, but was being applied at the wrong pipeline stage
# (see clean_slides_with_gpt). split_at_natural_break's small forward
# tolerance (see below) can land a few characters past this, so it's kept
# just under the true measured max rather than exactly at it.
PANEL_CHAR_CAPACITY = 475

# Budget handed to GPT for the *initial* cleaning pass -- generous enough to
# cover a two-card story (primary + one continuation) so GPT compresses the
# source article to how much substance it actually has, rather than being
# capped at a single card's worth before we've even decided whether the
# story needs two cards. Split into primary/continuation happens *after*
# cleaning, based on the cleaned length -- see clean_slides_with_gpt.
#
# Also used in build_slides_from_news as the raw-text pull cap: since output
# can never exceed this regardless of how much raw text GPT is given, there's
# no reason to send more than this much raw input either -- it would just
# burn extra input tokens on content that gets discarded either way.
CLEAN_MAX_CHARS = PANEL_CHAR_CAPACITY * 2

# If splitting a cleaned story leaves only a modest bit of leftover text, a
# whole separate "(cont)" card for it would sit mostly empty -- not worth a
# full second card. Only split into a continuation when the leftover is
# substantial enough to reasonably fill a chunk of the panel on its own;
# otherwise just drop the excess and let the primary card end at capacity.
MIN_CONTINUATION_LEN = 200

# Off-season story cap: a league that's out of season (per league_seasons.py's
# ACTIVE_MONTHS windows) still gets *some* news coverage rather than being cut
# off entirely, but far fewer slides than an in-season league gets.
OFFSEASON_MAX_PER_SPORT = 10

# Categories to exclude entirely from generated slides (normalized form).
# Example: "fantasyfootball" will exclude categories like "Fantasy Football",
# "fantasy-football", "fantasy_football", etc.
EXCLUDED_CATEGORIES = {"fantasyfootball"}


def _logo_for_word(word: str, league: str | None) -> str | None:
    if league and (MEDIA_LOGOS_DIR / f"{league}_{word}.png").exists():
        return f"{league}_{word}.png"
    logo_name = f"{word}.png"
    if (MEDIA_LOGOS_DIR / logo_name).exists():
        return logo_name
    return None


def infer_logo_from_text(text: str, league: str | None = None) -> str | None:
    """
    Infer a team logo filename from the first team name that actually
    appears in the text (by position, not by which regex found it), e.g.
    'Cowboys' -> 'cowboys.png'. Also matches digit-prefixed nicknames like
    '49ers', which have no uppercase letter at all ("49ers", not "49Ers")
    and would otherwise never match the capitalized-word pattern.

    Two-word nicknames (e.g. "Red Sox" -> redsox.png, "Blue Jays" ->
    bluejays.png, "Trail Blazers", "Maple Leafs", "Golden Knights", "Blue
    Jackets") are checked as a pair, not word-by-word -- checking only
    single words would never match "Red" or "Sox" individually against
    "redsox.png", silently skipping straight past the team actually being
    written about to whatever single-word team name happened to appear
    later in the text (confirmed live: a Red Sox story's first sentence
    named the Red Sox, but since neither "Red" nor "Sox" alone matched a
    logo file, it fell through to "Yankees" -- mentioned second -- instead).

    A few nicknames exist in both NFL and MLB (currently "Giants" and
    "Cardinals" -- see fetch_team_logos.py), so if `league` is known, the
    league-prefixed filename ("mlb_giants.png") is checked before the bare
    one, to avoid an MLB story showing the NFL team's logo or vice versa.

    Returns None if no matching logo file exists.
    """
    if not text:
        return None

    candidates: list[tuple[int, str]] = []  # (start_pos, logo_filename)

    # Two-word candidates first so a tie at the same start position (the
    # two-word match's first word also matching alone, e.g. "Blue" vs "Blue
    # Jays") prefers the more specific full name -- stable sort keeps
    # insertion order for ties. Uses a lookahead for the second word so
    # matches can overlap -- a plain "word word" pattern consumes both words
    # per match, so in "The Blue Jays swept...", "The Blue" would consume
    # "Blue" and "Blue Jays" itself would never be tried at all.
    for m in re.finditer(r"\b([A-Z][a-z]+)\s+(?=([A-Z][a-z]+)\b)", text):
        logo = _logo_for_word((m.group(1) + m.group(2)).lower(), league)
        if logo:
            candidates.append((m.start(), logo))

    for m in re.finditer(r"\b[A-Z][a-z]+\b", text):
        logo = _logo_for_word(m.group().lower(), league)
        if logo:
            candidates.append((m.start(), logo))

    for m in re.finditer(r"\b\d+[a-z]+\b", text):
        logo = _logo_for_word(m.group().lower(), league)
        if logo:
            candidates.append((m.start(), logo))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


def infer_logo(title: str, body: str, league: str | None = None) -> str | None:
    """
    Prefer the article's title for logo inference -- Yahoo's RSS feed has no
    team-specific metadata (categories are generic: "sports", "nfl"; source
    is just the publisher, e.g. "SB Nation"), but titles reliably name the
    team explicitly ("Dallas Cowboys release..."), while the body text can
    mention several teams in passing (opponents, comparisons) and pick the
    wrong one. Falls back to scanning the body if the title has no match.
    """
    return infer_logo_from_text(title, league) or infer_logo_from_text(body, league)

def style_body_text(text: str) -> str:
    """
    Apply minimal styling to raw source text before it's sent to GPT.
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

def split_at_natural_break(text: str, max_len: int) -> tuple[str, str]:
    """
    Split text into (first_part, rest) at a sentence/clause break (., ,, or
    -) near max_len, so a card doesn't cut off mid-word or mid-sentence.

    Prefers a break slightly *past* max_len over settling for one well
    before it: e.g. if the last sentence ending at or before max_len is at
    character 365, but the next sentence only overruns max_len by ~20 chars,
    using that next break fits a whole extra sentence instead of leaving a
    card with ~100 unused characters just because the runner-up sentence
    happened to cross the cap by a little. Bounded by FORWARD_TOLERANCE, not
    unbounded -- text with no punctuation at all nearby hard-cuts at max_len
    rather than searching arbitrarily far ahead.
    """
    if len(text) <= max_len:
        return text, ""

    FORWARD_TOLERANCE = 60
    candidates = [".", ",", "-"]

    split_idx = -1
    for ch in candidates:
        i = text.rfind(ch, 0, max_len)
        if i > split_idx:
            split_idx = i

    # Look for the next break shortly after wherever we landed (or after
    # max_len itself, if nothing was found before it) -- if it's within
    # tolerance, prefer it over the earlier (possibly much shorter) split.
    search_from = split_idx + 1 if split_idx != -1 else max_len
    forward_limit = max_len + FORWARD_TOLERANCE
    earliest_forward = None
    for ch in candidates:
        i = text.find(ch, search_from, forward_limit)
        if i != -1 and (earliest_forward is None or i < earliest_forward):
            earliest_forward = i
    if earliest_forward is not None:
        split_idx = earliest_forward

    if split_idx == -1:
        split_idx = max_len - 1

    split_idx += 1
    return text[:split_idx].strip(), text[split_idx:].strip()


def build_slides_from_news(max_per_sport: int = 40) -> Dict[str, Any]:
    """
    Fetch latest news via news_feed.fetch_sport_news() and convert to the
    stories.json structure your main app expects, with extra metadata.

    One slide per fetched item at this stage -- splitting into a primary
    card plus an optional "(cont)" card happens later, in
    clean_slides_with_gpt, based on the actual *cleaned* length rather than
    the raw source length (see that function's docstring for why).
    """
    slides: List[Dict[str, Any]] = []
    per_sport_order = ["nfl", "mlb", "nba", "nhl"]
    items: List[Any] = []

    active = set(league_seasons.active_leagues())
    for s in per_sport_order:
        sport_max = max_per_sport if s in active else OFFSEASON_MAX_PER_SPORT
        try:
            fetched = news_feed.fetch_sport_news(s, max_items=sport_max)
            items.extend(fetched)
        except Exception as e:
            print(f"[refresh_stories] Warning: failed to fetch {s}: {e}")
            continue

    for item in items:
        raw_text = (getattr(item, "text", None) or "")
        # Convert literal escaped sequences (e.g. "\\n", "\\r\\n", "\\t") into actual characters
        # so subsequent newline normalization/collapse works on real newlines.
        raw_text = raw_text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
        text = style_body_text(raw_text)  # Apply styling once
        # Collapse multiple consecutive newlines into a single newline so slide bodies only have one blank line.
        text = collapse_newlines(text)

        # Trim at the source, before GPT ever sees it, to at most two cards'
        # worth of characters (CLEAN_MAX_CHARS) -- output is already capped
        # there regardless (see clean_slides_with_gpt), so sending GPT more
        # raw input than that just burns extra input tokens for content that
        # would only get discarded anyway. Trimmed at a natural sentence
        # break via split_at_natural_break, not a mid-sentence hard cut.
        text, _ = split_at_natural_break(text, CLEAN_MAX_CHARS)

        if not text:
            continue

        league = (getattr(item, "sport", None) or "").lower() or None
        logo_recommended = f"{league}.png" if league else None
        item_title = getattr(item, "title", "") or ""
        inferred_logo = infer_logo(item_title, text, league)
        category = getattr(item, "category", None) or None

        # Normalize category for exclusion checks
        norm_cat = re.sub(r"\W+", "", category.lower()) if category else None
        if norm_cat and norm_cat in EXCLUDED_CATEGORIES:
            continue

        slides.append({
            "title": item_title,
            "body": text,
            "logo": inferred_logo,
            "league": league,
            "logo_recommended": logo_recommended,
            "category": category,
        })

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

    GPT is given CLEAN_MAX_CHARS (two cards' worth) up front, so it compresses
    each article down to how much substance it actually has rather than being
    pre-capped at one card's budget before we know whether it needs a second
    card. The cleaned result is then split into a primary card (up to
    PANEL_CHAR_CAPACITY) plus an optional "(cont)" card for real leftover
    content -- deciding the split on the cleaned text, not the raw source,
    is what actually fixes two problems: cards that used to look emptier than
    they needed to (GPT was never given room to fill them), and "(cont)"
    cards that used to appear even when GPT's own compression would have
    fit everything on one card if only it had been allowed to try.
    """
    slides = wrapper.get("slides", [])
    cleaned_slides: List[Dict[str, Any]] = []

    for idx, slide in enumerate(slides):
        body = (slide.get("body") or "")
        raw_len = len(body)

        if not body.strip():
            cleaned_slides.append(slide)
            continue

        try:
            cleaned_body = clean_article(body, max_chars=CLEAN_MAX_CHARS)
            cleaned_body = collapse_newlines(cleaned_body)
        except Exception as e:
            print(f"[refresh_stories] GPT failed on slide {idx + 1}: {e}")
            cleaned_body = collapse_newlines(body)[:CLEAN_MAX_CHARS]

        title = slide.get("title", "")
        league = slide.get("league")

        primary_body, rest = split_at_natural_break(cleaned_body, PANEL_CHAR_CAPACITY)
        # The continuation card has the same capacity as the primary one --
        # if there's enough leftover to need a third card's worth, trim it
        # to fit rather than overflowing the (single) continuation card.
        # CLEAN_MAX_CHARS is 2x PANEL_CHAR_CAPACITY, so this is rare (only
        # when the primary split landed well under capacity).
        if len(rest) > PANEL_CHAR_CAPACITY:
            rest, _ = split_at_natural_break(rest, PANEL_CHAR_CAPACITY)
        make_continuation = len(rest) >= MIN_CONTINUATION_LEN

        # Re-infer the logo from the text that will actually be displayed on
        # the primary card, not the raw pre-GPT body: GPT can drop sentences
        # that only mentioned a team in passing (e.g. a source article's
        # closing line naming "the Bruins' offensive staff" for a UCLA
        # football story), so inferring from the raw body risks picking a
        # team logo for a team that never appears in what's shown.
        recomputed_logo = infer_logo(title, primary_body, league)

        cleaned_slides.append({**slide, "body": primary_body, "logo": recomputed_logo})
        print(
            f"[refresh_stories] GPT cleaned slide {idx + 1}: "
            f"{raw_len} -> {len(cleaned_body)} (limit {CLEAN_MAX_CHARS}), "
            f"primary {len(primary_body)} chars"
            + (f", +continuation {len(rest)} chars" if make_continuation else
               (f", dropped {len(rest)} leftover chars (below {MIN_CONTINUATION_LEN})" if rest else ""))
        )

        if make_continuation:
            cleaned_slides.append({
                **slide,
                "title": "",  # continuation of the slide above; headline already shown there
                "body": "(cont) " + rest,
                # Shares the primary card's logo rather than being independently
                # re-inferred from its own fragment -- both split from the same
                # source article, and re-inferring per-fragment would let a
                # two-part story's logo flip between its own two cards.
                "logo": recomputed_logo,
            })

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
