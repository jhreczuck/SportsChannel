#!/usr/bin/env bash
# Pulls the latest code, reinstalls deps if requirements-server.txt changed,
# then runs every refresh_*.py script in sequence. One atomic step rather
# than a separately-timed "pull" job ahead of a separately-timed "refresh"
# job -- avoids a race if the pull ever runs long enough to still be in
# progress when a second timer fires. No `set -e` on the refresh scripts
# themselves: each already handles its own fetch failures gracefully
# (falls back to empty/best-effort data rather than crashing), and one
# script's unexpected failure shouldn't block the rest from running.
# Intended to be invoked by the sportschannel-refresh systemd service (see
# sportschannel-refresh.service / .timer in this directory).
set -uo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$DEPLOY_DIR/src"
PYTHON="$DEPLOY_DIR/venv/bin/python"
PIP="$DEPLOY_DIR/venv/bin/pip"

echo "[refresh_all] Starting at $(date -Iseconds)"

cd "$DEPLOY_DIR"
echo "[refresh_all] Pulling latest code..."
git pull --ff-only || echo "[refresh_all] git pull failed, continuing with existing code"

echo "[refresh_all] Syncing dependencies..."
"$PIP" install -q -r requirements-server.txt || echo "[refresh_all] pip install failed, continuing"

cd "$SRC_DIR"

echo "[refresh_all] Starting data refresh at $(date -Iseconds)"

"$PYTHON" refresh_stories.py
"$PYTHON" refresh_ticker.py
"$PYTHON" refresh_probables.py
"$PYTHON" refresh_standings.py
"$PYTHON" refresh_league_leaders.py
"$PYTHON" refresh_nfl_standings.py
"$PYTHON" refresh_nba_standings.py
"$PYTHON" refresh_nhl_standings.py
"$PYTHON" refresh_latest_line.py
"$PYTHON" refresh_nba_line.py
"$PYTHON" refresh_nhl_line.py
"$PYTHON" refresh_history.py
"$PYTHON" refresh_birthdays.py
"$PYTHON" refresh_trivia.py
"$PYTHON" refresh_quotes.py
"$PYTHON" refresh_score_results.py

echo "[refresh_all] Finished at $(date -Iseconds)"
