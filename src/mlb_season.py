"""
mlb_season.py

Shared "is it MLB season" gate for the Probables and Standings boards. Both
features should only appear roughly April-October; off-season they're skipped
entirely rather than showing stale/empty tables. Both refresh scripts write
their own "in_season" flag into their output JSON so the frontend doesn't need
to duplicate this date logic in JS.

Override with MLB_SEASON_OVERRIDE=1 / MLB_SEASON_OVERRIDE=0 for testing
in/out of season without waiting for the calendar.
"""
from __future__ import annotations

import os
from datetime import date

SEASON_START_MONTH = 4   # April
SEASON_END_MONTH = 10    # October (inclusive)


def is_mlb_season(today: date | None = None) -> bool:
    override = os.getenv("MLB_SEASON_OVERRIDE", "").strip()
    if override == "1":
        return True
    if override == "0":
        return False

    d = today or date.today()
    return SEASON_START_MONTH <= d.month <= SEASON_END_MONTH
