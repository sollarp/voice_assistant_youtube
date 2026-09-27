import queue
import threading
import time

import numpy as np
import pyaudio

from jarvis.audio.devices import open_output, resample
from jarvis.config import OUTPUT_RATE
from jarvis.log import log

_ECHO_TAIL = 1.5


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
    """Plays Gemini's voice on the Pi 3.5 mm headphone jack."""

    def __init__(self, prefer_name: str | None = None) -> None:
        self._pa = pyaudio.PyAudio()
        self._stream, self._rate = open_output(self._pa, prefer_name)
        if self._stream.is_stopped():
            self._stream.start_stream()
        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._skip = False
        self._audible_until = 0.0
        self._queued = 0
        self._played = 0
        self._dropped = 0
        self._errors = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def arm(self) -> None:
        self._skip = False

    def audible(self) -> bool:
        return time.monotonic() < self._audible_until

    def write(self, pcm: bytes, rate: int = OUTPUT_RATE) -> None:
        if not pcm:
            return
        if self._skip:
            self._dropped += len(pcm)
            return
        try:
            if rate != self._rate:
                pcm = resample(pcm, rate, self._rate)
        except Exception as exc:
            self._errors += 1
            log(f"speaker resample failed: {exc}")
            return
        self._queued += len(pcm)
        self._queue.put(pcm)

    def drop(self) -> None:
        self._skip = True
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            else:
                if item:
                    self._dropped += len(item)
                self._queue.task_done()

    def beep(self) -> None:
        self.arm()
        self.write(_tone(880, 0.18))
        self.drain()

    def drain(self) -> None:
        self._queue.join()
        if self._queued or self._played or self._dropped or self._errors:
            log(
                f"speaker queued {self._queued} bytes, played {self._played}, "
                f"dropped {self._dropped}, errors {self._errors}"
            )
            self._queued = 0
            self._played = 0
            self._dropped = 0
            self._errors = 0

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=2)
        self._stream.stop_stream()
        self._stream.close()
        self._pa.terminate()

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                if self._skip:
                    self._dropped += len(item)
                    continue
                try:
                    if self._stream.is_stopped():
                        self._stream.start_stream()
                    self._stream.write(item)
                except Exception as exc:
                    self._errors += 1
                    log(f"speaker write failed: {exc}")
                    continue
                self._played += len(item)
                seconds = len(item) / 2 / self._rate
                now = time.monotonic()
                start = max(self._audible_until - _ECHO_TAIL, now)
                self._audible_until = start + seconds + _ECHO_TAIL
            finally:
                self._queue.task_done()
