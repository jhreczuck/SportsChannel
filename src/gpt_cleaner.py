from __future__ import annotations

import os
import re
import time
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

# Load .env automatically (so OPENAI_API_KEY works without you doing anything else)
load_dotenv()

# ----------------------------
# Config
# ----------------------------
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
DEFAULT_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "2"))

_SYSTEM_PROMPT = """
You rewrite sports news articles into clean, readable blurbs for a slideshow card.

Rules:
- Remove ALL URLs, links, and HTML.
- Remove ads, social prompts, author bios, photo captions/credits, and copyright notices.
- Keep only the core sports news details.
- Write in plain sentences, no bullet points.
- Do not mention that text was shortened or summarized.
- Do not add opinions or invent details that aren't in the source.
- Use standard punctuation.
- Use as much of the character limit as the source material actually supports --
  do not artificially cut the piece down to one or two sentences just because
  it could technically be shorter. Only fall short of the limit if the source
  article genuinely doesn't have more relevant content to include.
- Break into a new paragraph only at a natural topic shift, not a fixed count
  -- most short articles are fine as a single paragraph. Separate paragraphs
  with exactly one "\\n" and nothing else (no indentation markers, no tabs,
  no blank line -- the display layer handles indentation on its own).
- Stay under the character limit provided.
- End on a full sentence (do not cut off mid-sentence).
- Output ONLY the cleaned text. No labels, no prefixes, no quotes.

Numeric and abbreviation integrity (critical):
- Do NOT change numeric formatting (e.g. .500, 3.14, 46.5).
- Do NOT insert spaces inside numbers or decimals (e.g., 46.5, .500, 3.14).
- Do NOT change abbreviations like a.m./p.m. (keep as a.m., p.m.).
""".strip()

# ----------------------------
# Text utilities
# ----------------------------
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def _strip_urls(text: str) -> str:
    return _URL_RE.sub("", text)


def _strip_edge_spaces_only(text: str) -> str:
    """
    Trim ONLY normal spaces from the very start/end.
    Do NOT strip tabs/newlines at the edges.
    """
    if text is None:
        return ""
    return re.sub(r"^[ ]+|[ ]+$", "", text)


def _safe_preclean(text: str) -> str:
    """
    Minimal cleanup before sending to GPT.
    MUST NOT touch newlines/tabs/decimals/abbreviations.
    """
    t = _strip_urls(text or "")

    # Remove trailing spaces/tabs BEFORE a newline: "word.  \n" -> "word.\n"
    t = re.sub(r"[ \t]+\n", "\n", t)

    # Collapse ONLY runs of spaces (do NOT touch \n or \t)
    t = re.sub(r"[ ]{2,}", " ", t)

    # Strip plain spaces at the very edges (not tabs/newlines)
    return _strip_edge_spaces_only(t)



def _trim_to_sentence_preserve_layout(text: str, max_chars: int) -> str:
    """
    Enforce max_chars and end on a sentence boundary if possible.
    Does NOT collapse whitespace or reflow text.
    """
    if max_chars <= 0:
        return ""

    t = text or ""
    if len(t) <= max_chars:
        return t

    window = t[:max_chars]

    # Prefer ending at a period.
    cut = window.rfind(".")
    if cut != -1:
        return window[: cut + 1]

    # Otherwise allow exclamation or question.
    cut = max(window.rfind("!"), window.rfind("?"))
    if cut != -1:
        return window[: cut + 1]

    # Nothing usable, hard cut.
    return window


def _build_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Put it in .env and make sure python-dotenv is installed."
        )
    return OpenAI(api_key=api_key, timeout=DEFAULT_TIMEOUT_SECONDS)


# Lazily created client so importing this module never crashes your app
_client: Optional[OpenAI] = None

# ----------------------------
# Public API
# ----------------------------
def clean_article(raw: str, max_chars: int = 500, model: Optional[str] = None) -> str:
    """
    Cleans and compresses a single article body.

    Guarantees (best effort):
    - No URLs
    - Output <= max_chars (enforced locally)
    - Ends on a sentence boundary when possible (enforced locally)

    Important:
    - Does NOT run any period/spacing normalization that could break decimals or a.m./p.m.
    - Paragraph breaks in the output are GPT's own choice (single "\\n" at natural topic
      shifts), not a preservation of the raw source's newlines -- those are mostly RSS/HTML
      formatting artifacts, not meaningful paragraph structure.
    """
    if not raw:
        return ""

    raw = _safe_preclean(raw)
    if not raw:
        return ""

    global _client
    if _client is None:
        _client = _build_client()

    use_model = (model or DEFAULT_MODEL).strip()

    last_err: Optional[Exception] = None
    for attempt in range(DEFAULT_MAX_RETRIES + 1):
        try:
            resp = _client.chat.completions.create(
                model=use_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Character limit: {max_chars}.\n\n{raw}",
                    },
                ],
                temperature=0.0,
                max_tokens=1200,
            )

            # Do NOT strip tabs/newlines.
            text = resp.choices[0].message.content or ""

            # Post-clean safety (non-destructive)
            text = _strip_urls(text)

            # Only strip plain spaces at edges (not tabs/newlines)
            text = _strip_edge_spaces_only(text)

            # Enforce hard limit + sentence ending (preserves layout)
            text = _trim_to_sentence_preserve_layout(text, max_chars)

            return text

        except Exception as e:
            last_err = e
            if attempt < DEFAULT_MAX_RETRIES:
                time.sleep(0.8 * (attempt + 1))
                continue
            break

    # If GPT fails, fall back to minimal local cleaning + hard trim
    fallback = _trim_to_sentence_preserve_layout(_strip_urls(_safe_preclean(raw)), max_chars)
    if fallback:
        return fallback

    raise RuntimeError(f"GPT cleaning failed: {last_err}") from last_err
