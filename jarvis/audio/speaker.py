import queue
import threading

import numpy as np
import pyaudio

from jarvis.audio.devices import open_output, resample
from jarvis.config import OUTPUT_RATE


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
        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._skip = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def write(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._skip = False
        if self._rate != OUTPUT_RATE:
            pcm = resample(pcm, OUTPUT_RATE, self._rate)
        self._queue.put(pcm)

    def drop(self) -> None:
        self._skip = True
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return
            else:
                self._queue.task_done()

    def beep(self) -> None:
        self.write(_tone(880, 0.18))
        self.drain()

    def drain(self) -> None:
        self._queue.join()

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
                    continue
                self._stream.write(item)
            finally:
                self._queue.task_done()
