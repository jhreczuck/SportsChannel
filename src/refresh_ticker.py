r"""
refresh_ticker.py

Fetches live scoreboard lines via ticker.py (ESPN) and writes them to
data/ticker.json as a flat "items" list, matching the shape the web
frontend (web/app.js) already reads.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_ticker.py

Optional env:

    TICKER_LEAGUES=nfl,nba  python ...\refresh_ticker.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import ticker as remote_ticker
from league_seasons import active_leagues

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TICKER_PATH = DATA_DIR / "ticker.json"

CREDITS_LINE = "LIVE SCORES BROUGHT TO YOU BY ESPN"


def main() -> None:
    env = os.getenv("TICKER_LEAGUES", "").strip()
    if env:
        leagues = [s.strip().lower() for s in env.split(",") if s.strip()]
    else:
        # Default to whichever leagues are actually in season, rather than
        # showing e.g. NHL/NBA scores in the middle of summer.
        leagues = active_leagues()
        print(f"[refresh_ticker] In-season leagues: {leagues}")

    try:
        lines = remote_ticker.fetch_ticker_lines(leagues)
    except Exception as e:
        print(f"[refresh_ticker] Fetch failed: {e}")
        lines = []

    items = [CREDITS_LINE] + lines

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
    TICKER_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[refresh_ticker] Wrote {len(items)} items to {TICKER_PATH}")


if __name__ == "__main__":
    main()
