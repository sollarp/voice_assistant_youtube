import numpy as np

from jarvis.config import (
    CHUNK,
    MAX_UTTERANCE_SECONDS,
    RATE,
    SILENCE_RMS_THRESHOLD,
    SILENCE_SECONDS,
    SPEECH_CONFIRM_CHUNKS,
)

_FRAME = CHUNK / RATE


def pcm_rms(pcm_bytes: bytes) -> float:
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))))


class VoiceActivity:
    def __init__(self) -> None:
        self.heard_speech = False
        self.silence = 0.0
        self.elapsed = 0.0
        self._hot = 0

    def update(self, pcm: bytes, *, stop_on_idle: bool = True) -> bool:
        self.elapsed += _FRAME
        if pcm_rms(pcm) >= SILENCE_RMS_THRESHOLD:
            self._hot += 1
            self.silence = 0.0
            if self._hot >= SPEECH_CONFIRM_CHUNKS:
                self.heard_speech = True
        else:
            self._hot = 0
            self.silence += _FRAME
        if self.heard_speech and self.silence >= SILENCE_SECONDS:
            return True
        if stop_on_idle and not self.heard_speech and self.silence >= SILENCE_SECONDS:
            return True
        return self.elapsed >= MAX_UTTERANCE_SECONDS

    def forgive_leading_silence(self) -> None:
        if not self.heard_speech:
            self.silence = 0.0
