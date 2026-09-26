import os
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
from gtts import gTTS

from jarvis.log import log


def speak(text: str) -> None:
    print(text, flush=True)
    cleaned = (text or "").strip()
    if not cleaned:
        return

    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        gTTS(text=cleaned, lang="en").save(path)
        pygame.mixer.init()
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.delay(40)
        finally:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
    except Exception as exc:
        log(f"speech playback failed: {exc}")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
