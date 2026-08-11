"""
league_seasons.py

Rough month-based "is this league in season" windows, used to keep the
ticker from showing NBA/NHL games in the middle of summer or MLB games in
January. These are deliberately approximate (calendar-month granularity, not
exact start/end dates) -- good enough for "should this league's scores be on
the ticker right now."

Override with TICKER_LEAGUES_OVERRIDE=nfl,mlb (comma-separated) to force a
specific set, e.g. for testing.
"""
from __future__ import annotations

import os
from datetime import date
from typing import List

# Month numbers (1-12) each league is considered "in season," including
# preseason/playoffs. MLB matches mlb_season.py's April-October window.
ACTIVE_MONTHS = {
    "nfl": {8, 9, 10, 11, 12, 1, 2},
    "mlb": {4, 5, 6, 7, 8, 9, 10},
    "nba": {10, 11, 12, 1, 2, 3, 4, 5, 6},
    "nhl": {10, 11, 12, 1, 2, 3, 4, 5, 6},
}


def active_leagues(today: date | None = None) -> List[str]:
    override = os.getenv("TICKER_LEAGUES_OVERRIDE", "").strip()
    if override:
        return [s.strip().lower() for s in override.split(",") if s.strip()]

    month = (today or date.today()).month
    return [league for league, months in ACTIVE_MONTHS.items() if month in months]
