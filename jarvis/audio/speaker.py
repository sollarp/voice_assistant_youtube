import os
import queue
import subprocess
import threading
import time

import numpy as np

from jarvis.config import OUTPUT_RATE
from jarvis.log import log

_VOICE_FIFO = "/tmp/jarvis-voice.pcm"


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
    """Plays Gemini's voice through mpv, on the same output as the song."""

    def __init__(self) -> None:
        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._skip = False
        self._pending = 0.0
        self._lock = threading.Lock()
        self._pipe = None
        self._proc: subprocess.Popen | None = None
        self._start()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _start(self) -> None:
        if os.path.exists(_VOICE_FIFO):
            os.remove(_VOICE_FIFO)
        os.mkfifo(_VOICE_FIFO)
        self._proc = subprocess.Popen(
            [
                "mpv",
                "--no-video",
                "--really-quiet",
                "--no-terminal",
                "--demuxer=rawaudio",
                f"--demuxer-rawaudio-rate={OUTPUT_RATE}",
                "--demuxer-rawaudio-channels=1",
                "--demuxer-rawaudio-format=s16le",
                _VOICE_FIFO,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        opened: list = []

        def _open() -> None:
            opened.append(open(_VOICE_FIFO, "wb", buffering=0))

        opener = threading.Thread(target=_open, daemon=True)
        opener.start()
        opener.join(3)
        if not opened:
            raise RuntimeError("voice player did not start")
        self._pipe = opened[0]
        log("voice player ready")

    def write(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._skip = False
        self._queue.put(pcm)

    def drop(self) -> None:
        self._skip = True
        with self._lock:
            self._pending = 0.0
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return
            else:
                self._queue.task_done()

    def beep(self) -> None:
        self.write(_tone(880, 0.09))
        self.drain()

    def drain(self) -> None:
        self._queue.join()
        with self._lock:
            wait = self._pending
            self._pending = 0.0
        if wait > 0:
            time.sleep(min(wait, 20))

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=2)
        if self._pipe is not None:
            self._pipe.close()
            self._pipe = None
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            os.remove(_VOICE_FIFO)
        except OSError:
            pass

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                if self._skip or not item or self._pipe is None:
                    continue
                self._pipe.write(item)
                self._pipe.flush()
                with self._lock:
                    self._pending += len(item) / 2 / OUTPUT_RATE
            except Exception as exc:
                log(f"voice playback failed: {exc}")
            finally:
                self._queue.task_done()
