#!/usr/bin/env python3
"""
ticker.py

Fetches scoreboard data from ESPN's public endpoint and shows a scrolling
ticker in the terminal.

You can also import this file and use:
- fetch_ticker_lines()
- build_ticker_text(lines)
- ticker_frame(text, width, offset)

inside your own rendering loop (e.g., PIL image overlay).
"""

import time
import shutil
import requests
import sys
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


# Base URLs for different sports (ESPN scoreboard endpoints)
BASE_URLS = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
}


# ---------------------------------------------------------------------------
# ESPN API helpers
# ---------------------------------------------------------------------------

def fetch_scoreboard_json(league: str = "nfl") -> dict:
    """Fetch raw scoreboard JSON from ESPN for the specified league with debug output (prints up to 5000 chars of body)."""
    url = BASE_URLS.get(league.lower())
    if not url:
        raise RuntimeError(f"No BASE_URL configured for league '{league}'")

    #print(f"[TICKER DEBUG] HTTP GET {league.upper()} -> {url}")
    try:
        resp = requests.get(url, timeout=10)
    except Exception as e:
        print(f"[TICKER DEBUG] {league.upper()} request failed: {e}")
        raise

    #print(f"[TICKER DEBUG] {league.upper()} HTTP {resp.status_code}")
    # Always print a truncated portion of the response body for debugging (up to 5000 chars)
    try:
        body_snippet = resp.text[:5000].replace("\n", " ")
        #print(f"[TICKER DEBUG] {league.upper()} response body (truncated to 5000 chars): {body_snippet}")
    except Exception as e:
        print(f"[TICKER DEBUG] Failed to read response body for {league.upper()}: {e}")

    try:
        resp.raise_for_status()
    except Exception as e:
        # Status non-200; re-raise after printing above
        raise

    try:
        return resp.json()
    except Exception as e:
        print(f"[TICKER DEBUG] {league.upper()} failed to parse JSON: {e}")
        # Print raw text for debugging (already printed snippet above)
        raise


def parse_events_to_lines(data: dict, league: str = "NFL") -> list[str]:
    """
    Parse ESPN scoreboard JSON into a list of ticker lines with league-aware formatting.

    Desired behaviors:
    - NFL (example): "DAL @ DET 30-44 Final"
    - NBA/MLB/NHL upcoming (no score): "MIA @ ORL 0-0 12/9 - 6:00 PM ET"
    - When scores exist for other leagues display scores and short detail, similar to NFL.
    """
    lines: list[str] = []
    events = data.get("events", [])

    for event in events:
        try:
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            # Identify home/away by "homeAway" flag
            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

            home_team = home.get("team", {}).get("abbreviation", "HOME")
            away_team = away.get("team", {}).get("abbreviation", "AWAY")

            # Scores may be strings or numbers; normalize to int where possible
            def norm_score(x):
                try:
                    return int(x)
                except Exception:
                    return None

            home_score = norm_score(home.get("score"))
            away_score = norm_score(away.get("score"))

            status_type = comp.get("status", {}).get("type", {})
            short_detail = (status_type.get("shortDetail") or status_type.get("description") or "").strip()

            # Helper: format datetime to "M/D - H:MM AM/PM TZ"
            def fmt_event_date(dt_str):
                if not dt_str:
                    return ""
                try:
                    # Some ESPN datetimes include timezone offset, parse with fromisoformat where supported
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                except Exception:
                    try:
                        # fallback parse naive
                        dt = datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S")
                    except Exception:
                        return ""
                # Convert to Eastern time display if available, else local
                tz = None
                if ZoneInfo:
                    try:
                        tz = ZoneInfo("America/New_York")
                        dt = dt.astimezone(tz)
                        tz_abbr = dt.tzname() or "ET"
                    except Exception:
                        tz_abbr = "ET"
                else:
                    tz_abbr = "ET"
                # Use %I:%M %p and strip leading zero for cross-platform compatibility
                try:
                    time_str = dt.strftime("%I:%M %p").lstrip("0")
                except Exception:
                    time_str = ""
                return f"{dt.month}/{dt.day} - {time_str} {tz_abbr}" if time_str else f"{dt.month}/{dt.day}"

            # If scores exist, show score_part
            if home_score is not None and away_score is not None:
                score_part = f"{away_score}-{home_score}"
            else:
                score_part = ""

            # League-specific formatting
            lg = league.lower()
            if lg == "nfl":
                # Prefer "Final" instead of "F"
                status_out = ""
                if short_detail:
                    # If short_detail signals final (contains 'FINAL' or 'F'), normalize to 'Final'
                    s_up = short_detail.upper()
                    if "FINAL" in s_up or s_up == "F":
                        status_out = "Final"
                    else:
                        status_out = short_detail
                parts = [f"{away_team} @ {home_team}"]
                if score_part:
                    parts.append(score_part)
                if status_out:
                    parts.append(status_out)
                line = " ".join(parts)
                lines.append(line)
                continue

            # For NBA/MLB/NHL: if no score, prefer to show scheduled date/time
            if lg in ("nba", "mlb", "nhl"):
                if score_part:
                    # show score + short detail if available
                    parts = [f"{away_team} @ {home_team}", score_part]
                    if short_detail:
                        parts.append(short_detail)
                    line = " ".join(parts)
                    lines.append(line)
                else:
                    # Try to find event/competition date
                    dt_str = comp.get("date") or event.get("date") or comp.get("season") or ""
                    pretty = fmt_event_date(dt_str)
                    if not pretty:
                        # fallback to generic placeholder
                        pretty = ""
                    # If no time available, still show date placeholder
                    if pretty:
                        line = f"{away_team} @ {home_team} 0-0 {pretty}"
                    else:
                        line = f"{away_team} @ {home_team} 0-0"
                    lines.append(line)
                continue

            # Generic fallback for unknown leagues: similar to NFL but without normalization
            parts = [f"{away_team} @ {home_team}"]
            if score_part:
                parts.append(score_part)
            if short_detail:
                parts.append(short_detail)
            line = " ".join(parts)
            lines.append(line)

        except Exception:
            # Skip malformed events
            continue

    if not lines:
        lines.append("No games available")
    return lines


def fetch_ticker_lines(leagues: list[str] | None = None) -> list[str]:
    """Fetch and combine ticker lines from specified leagues or all configured leagues if None."""
    lines: list[str] = []
    chosen = leagues if leagues is not None else list(BASE_URLS.keys())
    #print(f"[TICKER DEBUG] Fetching leagues: {', '.join(ch.upper() for ch in chosen)}")
    for lg in chosen:
        url = BASE_URLS.get(lg)
        if not url:
            print(f"[TICKER DEBUG] Skipping unknown league: {lg}")
            continue
       #print(f"[TICKER DEBUG] Attempting fetch for {lg.upper()} -> {url}")
        try:
            data = fetch_scoreboard_json(lg)
            event_count = len(data.get("events", [])) if isinstance(data, dict) else 0
            parsed = parse_events_to_lines(data, league=lg)
            #print(f"[TICKER DEBUG] {lg.upper()} fetch OK: events={event_count}, parsed_lines={len(parsed)}")
            # Insert a league header before that league's lines so the scroll shows
            # "* NBA SCORE SUMMARY *" (or other league) immediately before its scores.
            league_header = f"* {lg.upper()} SCORE SUMMARY *"
            # Avoid duplicating the same league header (defensive check).
            # If the previous appended item is already this header, skip appending again.
            if not lines or lines[-1] != league_header:
                lines.append(league_header)
            lines.extend(parsed)
        except Exception as e:
            print(f"[TICKER DEBUG] {lg.upper()} fetch failed: {e}")
            # continue to next league
            continue

    if not lines:
        lines.append("No games available")
    return lines


# ---------------------------------------------------------------------------
# Ticker text helpers
# ---------------------------------------------------------------------------

def build_ticker_text(lines: list[str], separator: str = "   |   ") -> str:
    """
    Join multiple ticker lines into one long scrolling string.
    """
    base = separator.join(lines)
    return base + separator  # add separator at end for smooth looping


def ticker_frame(text: str, width: int, offset: int) -> str:
    """
    Return a single 'frame' of the ticker, of fixed width, based on an offset.

    - text:   full ticker text (usually from build_ticker_text)
    - width:  number of characters to display in one frame
    - offset: scroll position (int; usually incremented each frame)
    """
    if width <= 0:
        return ""

    padded = text + " " * width  # padding to avoid abrupt cutoff
    length = len(padded)

    if length == 0:
        return " " * width

    start = offset % length
    end = start + width

    if end <= length:
        return padded[start:end]
    else:
        # Wrap-around
        return padded[start:] + padded[:end - length]


# ---------------------------------------------------------------------------
# Terminal scrolling implementation
# ---------------------------------------------------------------------------

def scroll_ticker_terminal(
    ticker_text: str,
    speed_seconds: float = 0.08,
) -> None:
    """
    Continuously scroll ticker_text across the terminal.
    Ctrl+C to exit.
    """
    # Terminal width; default to 80 if detection
