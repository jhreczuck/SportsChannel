"""
Sportschannel Smoke Test
- Opens a 960x720 window titled "Sportschannel – Smoke Test"
- Renders a simple message
- If an MP3 exists in media/music, plays it quietly
- Quits on ESC or window close; auto-exits after ~8 seconds
"""
import sys
import time
import pygame
from pathlib import Path

WIDTH, HEIGHT = 960, 720

def find_first_audio(music_dir: Path):
    if not music_dir.exists():
        return None
    for ext in (".mp3", ".ogg", ".wav"):
        files = list(music_dir.glob(f"*{ext}"))
        if files:
            return files[0]
    return None

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Sportschannel – Smoke Test")
    clock = pygame.time.Clock()

    # Background + text
    bg = (24, 24, 24)
    accent = (255, 165, 0)
    text_color = (230, 230, 230)

    # Font fallback
    try:
        font = pygame.font.SysFont("Consolas", 28)
    except Exception:
        font = pygame.font.Font(None, 28)

    # Try audio
    audio_started = False
    try:
        pygame.mixer.init()
        music_path = find_first_audio(Path(__file__).resolve().parent.parent / "media" / "music")
        if music_path:
            pygame.mixer.music.load(str(music_path))
            pygame.mixer.music.set_volume(0.2)
            pygame.mixer.music.play(-1)
            audio_started = True
    except Exception as e:
        # Audio is optional; continue anyway
        audio_started = False

    start = time.time()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        screen.fill(bg)

        # Frame
        pygame.draw.rect(screen, accent, (20, 20, WIDTH-40, HEIGHT-40), 2)

        # Text
        lines = [
            "Sportschannel – Smoke Test",
            "If you can see this window, pygame rendering works.",
            "Press ESC to exit, or wait ~8 seconds.",
            "Audio: {}".format("playing (looped)" if audio_started else "not detected"),
        ]
        y = 120
        for line in lines:
            surf = font.render(line, True, text_color)
            rect = surf.get_rect(center=(WIDTH//2, y))
            screen.blit(surf, rect)
            y += 40

        pygame.display.flip()
        clock.tick(60)

        if time.time() - start > 8:
            running = False

    try:
        pygame.mixer.music.stop()
        pygame.mixer.quit()
    except Exception:
        pass
    pygame.quit()

if __name__ == "__main__":
    main()
