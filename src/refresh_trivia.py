r"""
refresh_trivia.py

Fetches a sports trivia question from Open Trivia DB (opentdb.com), a free
public trivia API with a dedicated Sports category -- no API key, no
scraping, real curated Q&A pairs. Writes data/trivia.json.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\refresh_trivia.py
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TRIVIA_PATH = DATA_DIR / "trivia.json"

TRIVIA_URL = "https://opentdb.com/api.php?amount=1&category=21"  # 21 = Sports


def fetch_trivia() -> Optional[Dict[str, Any]]:
    resp = requests.get(TRIVIA_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("response_code") != 0 or not data.get("results"):
        return None

    result = data["results"][0]
    return {
        "question": html.unescape(result["question"]),
        "answer": html.unescape(result["correct_answer"]),
        "type": result.get("type", "multiple"),  # "multiple" or "boolean"
    }


def main() -> None:
    trivia = None
    try:
        trivia = fetch_trivia()
    except Exception as e:
        print(f"[refresh_trivia] Fetch failed: {e}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trivia": trivia,
    }
    TRIVIA_PATH.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    if trivia:
        print(f"[refresh_trivia] Q: {trivia['question'][:70]}")
    else:
        print("[refresh_trivia] No trivia available")


if __name__ == "__main__":
    main()
