r"""
normalize_music.py

Batch loudness-normalizes every track in media/music/ into
media/music_normalized/ using ffmpeg's two-pass loudnorm filter, then writes
web/music_manifest.json pointing at the normalized filenames -- fixes
variable playback volume on the web player (it was just playing the raw
files directly, unlike the pygame app which already normalized on the fly).

Reuses the same two-pass loudnorm approach as main.py's
normalize_track_lufs(), just run once as a batch step instead of per-track
at pygame-app startup. Skips files that are already normalized (content-hash
keyed filename), so re-running only processes new/changed tracks.

Requires ffmpeg on PATH.

Usage:

    python C:\Users\Admin\Documents\APIs\Sportschannel\Sportschannel\src\normalize_music.py
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
MUSIC_DIR = BASE_DIR / "media" / "music"
NORMALIZED_DIR = BASE_DIR / "media" / "music_normalized"
MANIFEST_PATH = BASE_DIR / "web" / "music_manifest.json"

TARGET_I = -16.0
TRUE_PEAK = -1.5
LRA = 11.0


def normalize_track(src: Path) -> Optional[Path]:
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)

    stat = src.stat()
    key = f"{src.name}|{stat.st_mtime_ns}|{stat.st_size}|I{TARGET_I}|TP{TRUE_PEAK}|LRA{LRA}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    dst = NORMALIZED_DIR / f"{src.stem}__lufs_{int(abs(TARGET_I))}_{digest}{src.suffix}"

    if dst.exists():
        return dst

    # ---------- PASS 1: MEASURE ----------
    cmd_pass1 = [
        "ffmpeg", "-i", str(src),
        "-af", f"loudnorm=I={TARGET_I}:TP={TRUE_PEAK}:LRA={LRA}:print_format=json",
        "-f", "null", "-",
    ]
    try:
        p = subprocess.run(cmd_pass1, capture_output=True, text=True, check=True)
        match = re.search(r"\{[\s\S]*?\}", p.stderr)
        if not match:
            raise RuntimeError("loudnorm JSON not found in ffmpeg output")
        stats = json.loads(match.group(0))
    except Exception as e:
        print(f"[normalize_music] Measure pass failed for {src.name}: {e}")
        return None

    # ---------- PASS 2: APPLY ----------
    # ffmpeg's loudnorm measure pass actually reports input_i/input_tp/
    # input_lra/input_thresh/target_offset (this ffmpeg build is 9.0) --
    # main.py's original normalize_track_lufs() used measured_I/measured_TP/
    # etc., which don't exist in the output and raised a KeyError as soon as
    # it actually ran (silently swallowed there by a bare except, which is
    # why the pygame app's normalization always failed and this bug was
    # never noticed until running it standalone here).
    cmd_pass2 = [
        "ffmpeg", "-y", "-i", str(src),
        "-af", (
            f"loudnorm=I={TARGET_I}:TP={TRUE_PEAK}:LRA={LRA}:"
            f"measured_I={stats['input_i']}:"
            f"measured_TP={stats['input_tp']}:"
            f"measured_LRA={stats['input_lra']}:"
            f"measured_thresh={stats['input_thresh']}:"
            f"offset={stats['target_offset']}:linear=true"
        ),
        str(dst),
    ]
    try:
        subprocess.run(cmd_pass2, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return dst
    except Exception as e:
        print(f"[normalize_music] Apply pass failed for {src.name}: {e}")
        return None


def main() -> None:
    files = sorted(
        f for ext in (".mp3", ".ogg", ".wav") for f in MUSIC_DIR.glob(f"*{ext}")
    )
    if not files:
        print(f"[normalize_music] No music files found in {MUSIC_DIR}")
        return

    normalized_names = []
    ok, failed = 0, 0
    for f in files:
        dst = normalize_track(f)
        if dst:
            normalized_names.append(dst.name)
            ok += 1
            print(f"[normalize_music] OK: {f.name} -> {dst.name}")
        else:
            failed += 1

    MANIFEST_PATH.write_text(
        json.dumps({"files": normalized_names}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[normalize_music] Done. normalized={ok} failed={failed} -> {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
