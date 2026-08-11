"""
mlb_divisions.py

Static team -> league/division lookup for MLB. ESPN's scoreboard endpoint
doesn't label individual games with AL/NL, so refresh_probables.py needs this
to sort games onto the right board. Keyed by ESPN's team abbreviation.
"""
from __future__ import annotations

from typing import Dict, Tuple

# abbreviation -> (league, division)
TEAM_DIVISIONS: Dict[str, Tuple[str, str]] = {
    # AL East
    "BAL": ("AL", "East"),
    "BOS": ("AL", "East"),
    "NYY": ("AL", "East"),
    "TB": ("AL", "East"),
    "TOR": ("AL", "East"),
    # AL Central
    "CWS": ("AL", "Central"),
    "CLE": ("AL", "Central"),
    "DET": ("AL", "Central"),
    "KC": ("AL", "Central"),
    "MIN": ("AL", "Central"),
    # AL West
    "HOU": ("AL", "West"),
    "LAA": ("AL", "West"),
    "ATH": ("AL", "West"),
    "SEA": ("AL", "West"),
    "TEX": ("AL", "West"),
    # NL East
    "ATL": ("NL", "East"),
    "MIA": ("NL", "East"),
    "NYM": ("NL", "East"),
    "PHI": ("NL", "East"),
    "WSH": ("NL", "East"),
    # NL Central
    "CHC": ("NL", "Central"),
    "CIN": ("NL", "Central"),
    "MIL": ("NL", "Central"),
    "PIT": ("NL", "Central"),
    "STL": ("NL", "Central"),
    # NL West
    "ARI": ("NL", "West"),
    "COL": ("NL", "West"),
    "LAD": ("NL", "West"),
    "SD": ("NL", "West"),
    "SF": ("NL", "West"),
}


def league_for(abbreviation: str) -> str | None:
    entry = TEAM_DIVISIONS.get(abbreviation.upper())
    return entry[0] if entry else None
