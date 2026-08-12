"""
Sportschannel – Retro Frame with Safe Wrapping, Music, Slide Rotation, and Multi-League Ticker

Features:
- 4:3 window (960x720)
- Retro dark background
- Header bar with channel name + clock
- Content panel with:
    - Title (hidden from display, body only)
    - Body text in a left column
    - Logo box area on the right
- Body text:
    - Wrapped safely by words (no characters deleted)
    - Revealed one line at a time (retro feel)
    - Wraps around an overlay logo region
- Bottom ticker bar:
    - Live scrolling ticker pulled from aggregated ESPN data via ticker.py
    - Pauses every 10 seconds for 3 seconds, then restarts from the right
- Background music:
    - Randomly picks one audio file from media/music
    - Loops it continuously
- Slide rotation:
    - Uses all slides from data/stories.json (or data/stories_cleaned.json if present)
    - Each slide is shown ~SLIDE_DURATION seconds then advances (wraps around)
- GPT cleaner:
    - If OPENAI_API_KEY is set, raw stories.json are cleaned with GPT
    - Cleaned stories are written to data/stories_cleaned.json
"""

import json
import random
import time
from pathlib import Path

import os
import math
import re

import pygame
import requests
import ticker as remote_ticker
import subprocess
import hashlib



# Music queue (shuffled, non-repeating) and end-event for pygame
MUSIC_QUEUE = []
MUSIC_INDEX = 0
MUSIC_END_EVENT = pygame.USEREVENT + 1
# Flag to track whether music was playing in the previous frame (polling fallback)
MUSIC_PLAYING = False

# ---------------------------
# Layout & Style
# ---------------------------
WIDTH, HEIGHT = 960, 720
HEADER_H = 64
TICKER_H = 56
PADDING = 18
PANEL_MARGIN = 20

# Logo tile size (fixed tile on right)
LOGO_BOX = (200, 200)

# Retro-ish color palette
BORDER_COLOR = (255, 0, 0)  # red
BG = (5, 5, 10)             # near-black
PANEL_BG = (50, 50, 50)     # panel pad
BODY_BG = (50, 50, 50)      # body box
INNER_FILL = (50, 50, 50)   # inner content fill

TEXT_PADDING = 14
FIRST_LINE_INDENT = 28
SEPARATOR_THICKNESS = 12
SEPARATOR_ALPHA = 128
TICKER_SEPARATOR_COLOR = (25, 25, 112)
TEXT = (235, 220, 190)
TICKER_BG = (10, 10, 16)
TICKER_TEXT = (245, 230, 200)

LINE_DELAY = 0.2       # seconds between each new line of body text
SLIDE_DURATION = 18.0  # seconds each story stays on screen before moving on

# Ticker behavior
TICKER_REFRESH_SECONDS = 120.0   # how often to refresh scores
TICKER_SCROLL_SPEED = 4          # pixels per frame

# Scroll/pause cycle: 10s scrolling, 3s pause
TICKER_SCROLL_ON_SECONDS = 10.0
TICKER_SCROLL_PAUSE_SECONDS = 3.0

# ESPN NFL endpoint (still used by ticker.py under-the-hood for NFL)
ESPN_NFL_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
)


# ---------------------------
# Data helpers
# ---------------------------

def load_stories(data_dir: Path):
    """
    Load slides for rotation.

    This app is read-only.
    It ONLY reads data/stories_cleaned.json.
    """
    cleaned_path = data_dir / "stories_cleaned.json"

    if not cleaned_path.exists():
        return [{
            "title": "No cleaned stories found",
            "body": "stories_cleaned.json not found. Run refresh_stories.py first.",
            "logo": None,
        }]

    try:
        data = json.loads(cleaned_path.read_text(encoding="utf-8"))
        slides = data.get("slides", [])
        if not slides:
            return [{
                "title": "No slides available",
                "body": "stories_cleaned.json contains no slides.",
                "logo": None,
            }]
        print(f"[STORIES] Loaded {len(slides)} slides from stories_cleaned.json")
        return slides
    except Exception as e:
        return [{
            "title": "Error reading stories_cleaned.json",
            "body": str(e),
            "logo": None,
        }]

def normalize_track_lufs(
    src: Path,
    out_dir: Path,
    target_i: float = -16.0,
    true_peak: float = -1.5,
    lra: float = 11.0,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    stat = src.stat()
    key = f"{src.name}|{stat.st_mtime_ns}|{stat.st_size}|I{target_i}|TP{true_peak}|LRA{lra}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

    dst = out_dir / f"{src.stem}__lufs_{int(abs(target_i))}_{digest}{src.suffix}"
    if dst.exists():
        return dst

    # ---------- PASS 1: MEASURE ----------
    cmd_pass1 = [
        "ffmpeg", "-i", str(src),
        "-af", f"loudnorm=I={target_i}:TP={true_peak}:LRA={lra}:print_format=json",
        "-f", "null", "-"
    ]

    try:
        p = subprocess.run(
            cmd_pass1,
            capture_output=True,
            text=True,
            check=True
        )
        match = re.search(r"\{[\s\S]*?\}", p.stderr)
        if not match:
            raise RuntimeError("loudnorm JSON not found")

        stats = json.loads(match.group(0))
    except Exception:
        return src  # fail safely

    # ---------- PASS 2: APPLY ----------
    # ffmpeg's loudnorm measure pass reports input_i/input_tp/input_lra/
    # input_thresh/target_offset, not measured_I/measured_TP/etc -- the old
    # key names here raised a KeyError every time this ran, silently caught
    # by the bare except below, which is why normalization always fell back
    # to the raw (un-normalized) file.
    cmd_pass2 = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-af",
        (
            f"loudnorm=I={target_i}:TP={true_peak}:LRA={lra}:"
            f"measured_I={stats['input_i']}:"
            f"measured_TP={stats['input_tp']}:"
            f"measured_LRA={stats['input_lra']}:"
            f"measured_thresh={stats['input_thresh']}:"
            f"offset={stats['target_offset']}:linear=true"
        ),
        str(dst)
    ]

    try:
        subprocess.run(cmd_pass2, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return dst
    except Exception:
        return src


def try_load_logo(media_logos: Path, file_name):
    if not file_name:
        return None
    p = media_logos / file_name
    if not p.exists():
        return None
    try:
        raw = pygame.image.load(str(p))

        has_alpha = False
        try:
            if raw.get_alpha() is not None or (raw.get_flags() & pygame.SRCALPHA):
                has_alpha = True
        except Exception:
            has_alpha = False

        try:
            if has_alpha:
                img = raw.convert_alpha()
            else:
                img = raw.convert()
                try:
                    top_left = img.get_at((0, 0))
                    colorkey = (top_left.r, top_left.g, top_left.b)
                    img.set_colorkey(colorkey)
                except Exception:
                    img.set_colorkey((255, 255, 255))
        except Exception:
            img = raw

        try:
            src_w, src_h = img.get_size()
            box_w, box_h = LOGO_BOX
            scale = min(box_w / src_w, box_h / src_h)
            new_w = max(1, int(src_w * scale))
            new_h = max(1, int(src_h * scale))
            img = pygame.transform.smoothscale(img, (new_w, new_h))
            print(f"[LOGO DEBUG] scaled to {new_w}x{new_h} within box {LOGO_BOX}")
        except Exception as e:
            try:
                img = pygame.transform.smoothscale(img, LOGO_BOX)
                print(
                    f"[LOGO DEBUG] aspect-ratio scale failed, forced to {LOGO_BOX}: {e}"
                )
            except Exception:
                print(f"[LOGO DEBUG] failed to scale image: {e}")

        try:
            canvas = pygame.Surface(LOGO_BOX, pygame.SRCALPHA, 32)
            canvas = canvas.convert_alpha()
            try:
                x = (LOGO_BOX[0] - img.get_width()) // 2
                y = (LOGO_BOX[1] - img.get_height()) // 2
            except Exception:
                x, y = 0, 0
            canvas.blit(img, (x, y))
            print(
                f"[LOGO DEBUG] loaded canvas (alpha preserved), image pos=({x},{y})"
            )
            return canvas
        except Exception:
            return img
    except Exception:
        return None


# ---------------------------
# Audio helper
# ---------------------------

def start_music(music_dir: Path, volume: float = 0.18):
    global MUSIC_QUEUE, MUSIC_INDEX, MUSIC_END_EVENT, MUSIC_PLAYING
    try:
        if not music_dir.exists():
            return

        files = []
        for ext in (".mp3", ".ogg", ".wav"):
            files.extend(music_dir.glob(f"*{ext}"))
        files = [f for f in files if f.is_file()]
        if not files:
            return

        # NEW: normalize into cache folder
        norm_dir = music_dir.parent / "music_normalized"
        normalized_files = [normalize_track_lufs(f, norm_dir) for f in files]

        MUSIC_QUEUE = list(normalized_files)
        random.shuffle(MUSIC_QUEUE)
        MUSIC_INDEX = 0

        pygame.mixer.init()
        pygame.mixer.music.set_endevent(MUSIC_END_EVENT)

        track = MUSIC_QUEUE[MUSIC_INDEX]
        pygame.mixer.music.load(str(track))
        pygame.mixer.music.set_volume(volume)  # overall gain (still useful)
        pygame.mixer.music.play(0)
        MUSIC_PLAYING = True
        print(f"[DEBUG] Playing music: {Path(track).name}")
    except Exception as e:
        print(f"[DEBUG] Music error: {e}")



# ---------------------------
# NFL ticker helpers (base ESPN utilities)
# ---------------------------

def fetch_nfl_scoreboard() -> dict | None:
    """Fetch raw NFL scoreboard JSON from ESPN. Return None on failure."""
    try:
        resp = requests.get(ESPN_NFL_SCOREBOARD_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[TICKER] Error fetching NFL scoreboard: {e}")
        return None


def parse_nfl_events_to_lines(data: dict) -> list[str]:
    """
    Parse ESPN scoreboard JSON into lines like:
        "BUF @ HOU 27-20 F"
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

            home = next(
                (c for c in competitors if c.get("homeAway") == "home"),
                competitors[0],
            )
            away = next(
                (c for c in competitors if c.get("homeAway") == "away"),
                competitors[1],
            )

            home_team = home.get("team", {}).get("abbreviation", "HOME")
            away_team = away.get("team", {}).get("abbreviation", "AWAY")

            home_score = home.get("score")
            away_score = away.get("score")

            status_type = comp.get("status", {}).get("type", {})
            short_detail = (
                status_type.get("shortDetail")
                or status_type.get("description")
                or ""
            )

            if home_score is not None and away_score is not None:
                score_part = f"{away_score}-{home_score}"
            else:
                score_part = ""

            parts = [f"{away_team} @ {home_team}"]
            if score_part:
                parts.append(score_part)
            if short_detail:
                parts.append(short_detail)

            line = " ".join(parts)
            lines.append(line)

        except Exception:
            continue

    return lines


def fetch_nfl_ticker_lines() -> list[str]:
    """
    Convenience wrapper:
    - Try to fetch NFL games and build lines
    - Fallback to static text if nothing is available
    """
    data = fetch_nfl_scoreboard()
    if not data:
        return [
            "NFL SCOREBOARD UNAVAILABLE",
        ]

    lines = parse_nfl_events_to_lines(data)
    if not lines:
        return [
            "NO NFL GAMES AVAILABLE",
        ]

    return lines


def build_ticker_surface(font_ticker: pygame.font.Font) -> pygame.Surface:
    """
    Build the ticker surface by pulling aggregated lines from src.ticker.
    Uses the configured leagues from the environment variable TICKER_LEAGUES
    (comma-separated, e.g. "nba,mlb,nhl"). If unset, uses ticker.default config.
    """
    env = os.getenv("TICKER_LEAGUES", "").strip()
    leagues = None
    if env:
        leagues = [s.strip().lower() for s in env.split(",") if s.strip()]

    try:
        lines = remote_ticker.fetch_ticker_lines(leagues)
    except Exception as e:
        print(f"[TICKER] Error fetching aggregated ticker lines: {e}")
        lines = ["No games available"]

    credits = "  LIVE SCORES BROUGHT TO YOU BY ESPN"
    if lines:
        full = "   |   ".join([credits] + lines)
    else:
        full = "   |   ".join([credits, "* SCORE SUMMARY *"])

    return font_ticker.render(full, True, TICKER_TEXT)


# ---------------------------
# Drawing helpers
# ---------------------------

def draw_header(surface, font_small, font_header, header_logo=None):
    content_w = WIDTH - PANEL_MARGIN * 2

    pygame.draw.rect(surface, BG, (PANEL_MARGIN, 0, content_w, HEADER_H))

    bottom_surf = pygame.Surface((content_w, SEPARATOR_THICKNESS), pygame.SRCALPHA)
    bottom_surf.fill((*BORDER_COLOR, SEPARATOR_ALPHA))
    surface.blit(bottom_surf, (PANEL_MARGIN, HEADER_H))

    label_x = PANEL_MARGIN + PADDING
    if header_logo:
        try:
            logo_rect = header_logo.get_rect()
            logo_y = HEADER_H // 2 - logo_rect.height // 2
            surface.blit(header_logo, (PANEL_MARGIN + 6, logo_y))
            label_x = PANEL_MARGIN + 6 + logo_rect.width + 8
        except Exception:
            label_x = PANEL_MARGIN + PADDING

    label = font_header.render("SportsChannel", True, TEXT)
    surface.blit(label, (label_x, HEADER_H // 2 - label.get_height() // 2))

    clock_text = time.strftime("%a %I:%M %p").upper()
    ts = font_small.render(clock_text, True, TEXT)
    surface.blit(
        ts,
        (
            PANEL_MARGIN + content_w - PADDING - ts.get_width(),
            HEADER_H // 2 - ts.get_height() // 2,
        ),
    )


def draw_ticker(surface, font_ticker, ticker_surface: pygame.Surface | None, ticker_x: int):
    """
    Draw the ticker bar at the bottom, with a scrolling ticker_surface if available.
    """
    content_w = WIDTH - PANEL_MARGIN * 2
    pygame.draw.rect(
        surface, TICKER_BG, (PANEL_MARGIN, HEIGHT - TICKER_H, content_w, TICKER_H)
    )

    tick_sep = pygame.Surface((content_w, SEPARATOR_THICKNESS), pygame.SRCALPHA)
    tick_sep.fill((*TICKER_SEPARATOR_COLOR, SEPARATOR_ALPHA))
    surface.blit(tick_sep, (PANEL_MARGIN, HEIGHT - TICKER_H))

    if ticker_surface is None:
        msg = "SPORTS PLUS NETWORK • AUTOMATED SPORTS NEWS FEED •"
        text = font_ticker.render(msg, True, TICKER_TEXT)
        surface.blit(
            text,
            (PADDING, HEIGHT - TICKER_H // 2 - text.get_height() // 2),
        )
        return

    y = HEIGHT - TICKER_H // 2 - ticker_surface.get_height() // 2
    w = ticker_surface.get_width()

    prev_clip = surface.get_clip()
    clip_rect = pygame.Rect(PANEL_MARGIN, HEIGHT - TICKER_H, content_w, TICKER_H)
    surface.set_clip(clip_rect)

    surface.blit(ticker_surface, (ticker_x, y))
    surface.blit(ticker_surface, (ticker_x + w, y))

    surface.set_clip(prev_clip)


# ---------------------------
# Text wrapping
# ---------------------------

def wrap_text_around_overlay(
    body_text: str,
    font: pygame.font.Font,
    left_rect: pygame.Rect,
    overlay_rect: pygame.Rect,
    padding: int,
    logo_surface: pygame.Surface | None,
) -> list[str]:
    """
    Wrap text word-by-word, preserving <<<INDENT>>> markers.
    Lines marked with <<<INDENT>>> will be indented when rendered.
    """
    lines = []
    line_height = font.get_height() + 4
    
    # Calculate widths
    full_width = max(40, left_rect.width - padding * 2)
    
    if logo_surface:
        overlay_top = max(0, overlay_rect.top - left_rect.top)
        overlay_start_line = int(overlay_top // line_height)
        overlay_line_count = int(math.ceil(overlay_rect.height / line_height))
        narrow_width = max(40, left_rect.width - overlay_rect.width - padding * 2 - 12)
    else:
        overlay_start_line = 999999
        overlay_line_count = 0
        narrow_width = full_width
    
    # Process each line (already split by \n in the data)
    for para in body_text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        
        # Check for indent marker
        has_indent = para.startswith("<<<INDENT>>>")
        text = para.replace("<<<INDENT>>>", "").strip()
        
        if not text:
            continue
        
        words = text.split()
        first_line = True
        
        while words:
            line_idx = len(lines)
            
            # Which width to use?
            if overlay_start_line <= line_idx < overlay_start_line + overlay_line_count:
                width = narrow_width
            else:
                width = full_width
            
            # Account for indent in width calculation
            if first_line and has_indent:
                # Reduce available width by indent amount
                available_width = width - FIRST_LINE_INDENT
            else:
                available_width = width
            
            # Build line word by word
            line = []
            while words:
                test = " ".join(line + [words[0]])
                
                if font.size(test)[0] <= available_width:
                    line.append(words.pop(0))
                else:
                    if not line:
                        # Word is too long, force it
                        line.append(words.pop(0))
                    break
            
            # Save line with marker on first line only
            result = " ".join(line)
            if first_line and has_indent:
                lines.append("<<<INDENT>>>" + result)
                first_line = False
            else:
                lines.append(result)
    
    return lines


# ---------------------------
# Main
# ---------------------------

def main():
    global MUSIC_INDEX, MUSIC_QUEUE, MUSIC_PLAYING

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(
        "Sportschannel – Retro Frame (Music + Rotation + Multi-League Ticker)"
    )
    clock = pygame.time.Clock()

    base = Path(__file__).resolve().parent.parent

    # Fonts
    def load_header_font(size, bold=False):
        candidates = [
            base / "media" / "fonts" / "EurostileCondensed.ttf",
            base / "media" / "fonts" / "Eurostile.ttf",
            base / "media" / "fonts" / "PxPlus_IBM_VGA8.ttf",
        ]
        for p in candidates:
            try:
                if p.exists():
                    return pygame.font.Font(str(p), size)
            except Exception:
                pass
        try:
            match = (
                pygame.font.match_font("Eurostile Condensed")
                or pygame.font.match_font("Eurostile")
            )
            if match:
                return pygame.font.Font(match, size)
        except Exception:
            pass
        try:
            return pygame.font.SysFont("Consolas", size, bold=bold)
        except Exception:
            return pygame.font.Font(None, size)

    def load_pxplus_font(size, bold=False):
        candidates = [base / "media" / "fonts" / "PxPlus_IBM_VGA8.ttf"]
        for p in candidates:
            try:
                if p.exists():
                    return pygame.font.Font(str(p), size)
            except Exception:
                pass
        try:
            match = pygame.font.match_font("PxPlus IBM VGA8") or pygame.font.match_font(
                "PxPlus"
            )
            if match:
                return pygame.font.Font(match, size)
        except Exception:
            pass
        try:
            return pygame.font.SysFont("Consolas", size, bold=bold)
        except Exception:
            return pygame.font.Font(None, size)

    font_header = load_header_font(38, bold=True)
    font_body = load_pxplus_font(39)
    font_ticker = load_pxplus_font(40)
    font_small = load_pxplus_font(30)

    try:
        font_body.size("test")
        font_header.size("T")
        font_ticker.size("test")
        font_small.size("test")
    except Exception:
        try:
            font_header = pygame.font.SysFont("Consolas", 24, bold=True)
            font_body = pygame.font.SysFont("Consolas", 21)
            font_ticker = pygame.font.SysFont("Consolas", 40)
            font_small = pygame.font.SysFont("Consolas", 26)
        except Exception:
            font_header = pygame.font.Font(None, 24)
            font_body = pygame.font.Font(None, 21)
            font_ticker = pygame.font.Font(None, 40)
            font_small = pygame.font.Font(None, 26)

    # Start music
    start_music(base / "media" / "music")

    # Header logo
    header_logo = None
    try:
        raw_logo = try_load_logo(base / "media" / "logos", "sportschannel.png")
        if raw_logo:
            try:
                src_w, src_h = raw_logo.get_size()
                target_h = max(8, HEADER_H - 18)
                scale = target_h / float(src_h) if src_h > 0 else 1.0
                scale *= 1.69  # bump up size ~69%
                new_w = max(1, int(src_w * scale))
                new_h = max(1, int(src_h * scale))
                header_logo = pygame.transform.smoothscale(raw_logo, (new_w, new_h))
            except Exception:
                header_logo = raw_logo
    except Exception:
        header_logo = None

    # Load slides (GPT-cleaned if available)
    slides = load_stories(base / "data")
    num_slides = len(slides)
    current_index = 0

    # Layout rects
    content_top = HEADER_H + SEPARATOR_THICKNESS
    content_bottom = HEIGHT - TICKER_H
    content_left = PANEL_MARGIN
    content_right = WIDTH - PANEL_MARGIN
    content_width = content_right - content_left
    content_rect = pygame.Rect(
        content_left, content_top, content_width, content_bottom - content_top
    )

    margin = TEXT_PADDING
    inner = content_rect.inflate(-margin * 2, -margin * 2)

    right_w = LOGO_BOX[0]
    right_rect = pygame.Rect(inner.right - right_w, inner.top, right_w, LOGO_BOX[1])

    gap = 12
    text_max_right = right_rect.left - gap
    left_width = max(80, text_max_right - inner.left)
    left_rect = pygame.Rect(inner.left, inner.top, left_width, inner.height)

    overlay_rect = pygame.Rect(
        inner.right - LOGO_BOX[0] - TEXT_PADDING,
        inner.top + TEXT_PADDING,
        LOGO_BOX[0],
        LOGO_BOX[1],
    )

    def prepare_slide(idx: int):
        slide = slides[idx]
        title = slide.get("title", "")
        body = slide.get("body", "")
        # Normalize escaped newline sequences if they appear as literal backslash escapes
        if isinstance(body, str):
            body = body.replace("\\r\\n", "\n").replace("\\n", "\n")
        logo_name = slide.get("logo") or slide.get("logo_recommended")
        logo = try_load_logo(base / "media" / "logos", logo_name)
        wrapped_lines = wrap_text_around_overlay(
            body, font_body, inner, overlay_rect, TEXT_PADDING, logo
        )
        print(f"[DEBUG] Slide {idx + 1}/{num_slides}: '{title}'")
        return title, body, logo, wrapped_lines

    title, body, logo, wrapped_lines = prepare_slide(current_index)
    slide_start_time = time.time()

    # Ticker state
    ticker_surface: pygame.Surface | None = None
    ticker_x = WIDTH
    last_ticker_refresh = 0.0
    ticker_cycle_start = time.time()

    try:
        ticker_surface = build_ticker_surface(font_ticker)
        last_ticker_refresh = time.time()
        ticker_x = PANEL_MARGIN + content_width
        ticker_cycle_start = time.time()
    except Exception as e:
        print(f"[TICKER] Initial ticker build failed: {e}")
        ticker_surface = None

    running = True
    while running:
        now = time.time()
        elapsed = now - slide_start_time

        # Refresh ticker periodically
        if now - last_ticker_refresh >= TICKER_REFRESH_SECONDS:
            try:
                ticker_surface = build_ticker_surface(font_ticker)
                last_ticker_refresh = now
                ticker_x = PANEL_MARGIN + content_width
                ticker_cycle_start = now
                print("[TICKER] Refreshed ticker.")
            except Exception as e:
                print(f"[TICKER] Refresh failed: {e}")

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == MUSIC_END_EVENT:
                try:
                    if MUSIC_QUEUE:
                        MUSIC_INDEX += 1
                        if MUSIC_INDEX >= len(MUSIC_QUEUE):
                            random.shuffle(MUSIC_QUEUE)
                            MUSIC_INDEX = 0
                        next_track = MUSIC_QUEUE[MUSIC_INDEX]
                        pygame.mixer.music.load(str(next_track))
                        pygame.mixer.music.play(0)
                        print(f"[DEBUG] Playing next music: {next_track.name}")
                except Exception as e:
                    print(f"[DEBUG] Music queue advance error: {e}")
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_RIGHT:
                    current_index = (current_index + 1) % num_slides
                    title, body, logo, wrapped_lines = prepare_slide(current_index)
                    slide_start_time = time.time()

        # Music polling fallback
        try:
            if pygame.mixer.get_init():
                busy = pygame.mixer.music.get_busy()
                if not busy and MUSIC_PLAYING:
                    try:
                        if MUSIC_QUEUE:
                            MUSIC_INDEX += 1
                            if MUSIC_INDEX >= len(MUSIC_QUEUE):
                                random.shuffle(MUSIC_QUEUE)
                                MUSIC_INDEX = 0
                            next_track = MUSIC_QUEUE[MUSIC_INDEX]
                            pygame.mixer.music.load(str(next_track))
                            pygame.mixer.music.play(0)
                            print(
                                f"[DEBUG] Playing next music (poll): {next_track.name}"
                            )
                            MUSIC_PLAYING = True
                        else:
                            MUSIC_PLAYING = False
                    except Exception as e:
                        print(f"[DEBUG] Music polling advance error: {e}")
                else:
                    MUSIC_PLAYING = busy
        except Exception:
            pass

        # Auto-advance slides
        if elapsed >= SLIDE_DURATION:
            current_index = (current_index + 1) % num_slides
            title, body, logo, wrapped_lines = prepare_slide(current_index)
            slide_start_time = time.time()
            elapsed = 0.0

        # Scroll ticker with pause cycle
        if ticker_surface is not None:
            cycle_elapsed = now - ticker_cycle_start
            w = ticker_surface.get_width()

            if cycle_elapsed <= TICKER_SCROLL_ON_SECONDS:
                ticker_x -= TICKER_SCROLL_SPEED
                if ticker_x <= (PANEL_MARGIN - w):
                    ticker_x = PANEL_MARGIN + content_width
            elif cycle_elapsed <= TICKER_SCROLL_ON_SECONDS + TICKER_SCROLL_PAUSE_SECONDS:
                pass
            else:
                ticker_cycle_start = now

        # Draw frame
        screen.fill(BG)
        draw_header(screen, font_small, font_header, header_logo)

        pygame.draw.rect(screen, PANEL_BG, content_rect)
        pygame.draw.rect(screen, BODY_BG, content_rect, 2)

        pygame.draw.rect(screen, INNER_FILL, inner)

        # Render text lines
        if wrapped_lines:
            lines_to_show = int(elapsed // LINE_DELAY)
            if lines_to_show > len(wrapped_lines):
                lines_to_show = len(wrapped_lines)
        else:
            lines_to_show = 0

        line_y = inner.top + TEXT_PADDING
        max_y = inner.bottom - TEXT_PADDING
        
        for i in range(lines_to_show):
            if line_y > max_y:
                break

            line = wrapped_lines[i]

            # Skip blank lines
            if not line.strip():
                line_y += font_body.get_height() + 4
                continue

            # Check for indent marker
            if line.startswith("<<<INDENT>>>"):
                # Remove marker and indent this line
                text = line.replace("<<<INDENT>>>", "")
                x_pos = inner.left + TEXT_PADDING + FIRST_LINE_INDENT
            else:
                # No indent - regular line
                text = line
                x_pos = inner.left + TEXT_PADDING

            # Render
            surf = font_body.render(text, True, TEXT)
            screen.blit(surf, (x_pos, line_y))
            line_y += font_body.get_height() + 4

        if logo:
            logo_rect = logo.get_rect()
            logo_rect.center = right_rect.center
            screen.blit(logo, logo_rect.topleft)

        draw_ticker(screen, font_ticker, ticker_surface, ticker_x)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()