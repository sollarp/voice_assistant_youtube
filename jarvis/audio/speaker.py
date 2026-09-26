import os
import tempfile
import threading
import wave

import numpy as np

from jarvis.audio.player import MPVController
from jarvis.config import OUTPUT_RATE
from jarvis.log import log


def _tone(frequency: float, seconds: float) -> bytes:
    count = int(OUTPUT_RATE * seconds)
    ramp = min(int(OUTPUT_RATE * 0.01), max(count // 2, 1))
    timeline = np.arange(count, dtype=np.float32) / OUTPUT_RATE
    wave = 0.25 * np.sin(2 * np.pi * frequency * timeline)
    envelope = np.ones(count, dtype=np.float32)
    envelope[:ramp] = np.linspace(0, 1, ramp, dtype=np.float32)
    envelope[-ramp:] = np.linspace(1, 0, ramp, dtype=np.float32)
    return (wave * envelope * 32767).astype(np.int16).tobytes()


class Speaker:
    """Plays Gemini's voice on the same mpv that plays the song."""

    def __init__(self, player: MPVController) -> None:
        self._player = player
        self._chunks: list[bytes] = []
        self._lock = threading.Lock()
        self._skip = False

    def write(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._skip = False
        with self._lock:
            self._chunks.append(pcm)

    def drop(self) -> None:
        self._skip = True
        with self._lock:
            self._chunks.clear()

    def beep(self) -> None:
        self.write(_tone(880, 0.18))
        self.drain()

    def drain(self) -> None:
        with self._lock:
            if self._skip:
                self._chunks.clear()
                self._skip = False
                return
            pcm = b"".join(self._chunks)
            self._chunks.clear()
        if not pcm:
            return
        seconds = len(pcm) / 2 / OUTPUT_RATE
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            with wave.open(path, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(OUTPUT_RATE)
                handle.writeframes(pcm)
            log(f"speaking {seconds:.1f}s")
            if not self._player.play_clip(path, seconds):
                log("voice playback failed")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def close(self) -> None:
        return
