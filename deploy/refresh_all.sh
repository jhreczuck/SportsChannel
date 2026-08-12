#!/usr/bin/env bash
# Runs every refresh_*.py script in sequence, using the server venv.
# No `set -e` on purpose: each script already handles its own fetch
# failures gracefully (falls back to empty/best-effort data rather than
# crashing), and one script's unexpected failure shouldn't block the rest
# from running. Intended to be invoked by the sportschannel-refresh systemd
# service (see sportschannel-refresh.service / .timer in this directory).
set -uo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$DEPLOY_DIR/src"
PYTHON="$DEPLOY_DIR/venv/bin/python"

cd "$SRC_DIR"

echo "[refresh_all] Starting refresh at $(date -Iseconds)"

"$PYTHON" refresh_stories.py
"$PYTHON" refresh_ticker.py
"$PYTHON" refresh_probables.py
"$PYTHON" refresh_standings.py
"$PYTHON" refresh_nfl_standings.py
"$PYTHON" refresh_latest_line.py
"$PYTHON" refresh_history.py
"$PYTHON" refresh_birthdays.py
"$PYTHON" refresh_trivia.py
"$PYTHON" refresh_quotes.py
"$PYTHON" refresh_score_results.py

echo "[refresh_all] Finished at $(date -Iseconds)"
