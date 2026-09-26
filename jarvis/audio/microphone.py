from __future__ import annotations

import inspect

import numpy as np
import openwakeword
import pyaudio
from openwakeword.model import Model

from jarvis.audio.devices import open_input, resample
from jarvis.config import CHUNK, RATE, WAKE_MODEL, WAKE_THRESHOLD
from jarvis.log import log


class Microphone:
    def __init__(self) -> None:
        self._pa = pyaudio.PyAudio()
        self.stream, self._rate, self._native_chunk, self.device_name = open_input(self._pa)
        self.stream.start_stream()

    def read(self) -> bytes:
        try:
            native = self.stream.read(self._native_chunk, exception_on_overflow=False)
        except OSError as exc:
            log(f"mic read error: {exc}")
            return b"\x00" * (CHUNK * 2)
        return resample(native, self._rate, RATE, CHUNK)

    def close(self) -> None:
        self.stream.stop_stream()
        self.stream.close()
        self._pa.terminate()


class WakeWord:
    def __init__(self) -> None:
        try:
            from openwakeword.utils import download_models
            download_models()
        except ImportError:
            pass

        catalog = getattr(openwakeword, "models", None) or getattr(openwakeword, "MODELS", {})
        entry = catalog.get(WAKE_MODEL, {})
        model_path = entry.get("model_path") if isinstance(entry, dict) else None
        params = inspect.signature(Model.__init__).parameters

        if "wakeword_model_paths" in params:
            if not model_path:
                raise RuntimeError("hey_jarvis model not found")
            self._model = Model(wakeword_model_paths=[model_path])
            return

        kwargs = {"wakeword_models": [model_path] if model_path else [WAKE_MODEL]}
        if "inference_framework" in params:
            kwargs["inference_framework"] = "onnx"
        self._model = Model(**kwargs)

    def score(self, pcm: bytes) -> float:
        samples = np.frombuffer(pcm, dtype=np.int16)
        prediction = self._model.predict(samples)
        best = 0.0
        for name, value in prediction.items():
            if "jarvis" in str(name).lower():
                best = max(best, float(value))
        return best

    def triggered(self, pcm: bytes) -> bool:
        return self.score(pcm) > WAKE_THRESHOLD

    def reset(self) -> None:
        self._model.reset()
