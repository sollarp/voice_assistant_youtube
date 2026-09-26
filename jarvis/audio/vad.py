import numpy as np

from jarvis.config import (
    MAX_UTTERANCE_CHUNKS,
    MIN_SPEECH_CHUNKS,
    NO_SPEECH_CHUNKS,
    SILENCE_CHUNKS,
    SILENCE_RMS_THRESHOLD,
)


def pcm_rms(pcm_bytes: bytes) -> float:
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))))


class VoiceActivity:
    def __init__(self) -> None:
        self.heard_speech = False
        self.speech_chunks = 0
        self.silence_chunks = 0
        self.idle_chunks = 0
        self.total_chunks = 0

    def update(self, pcm: bytes) -> bool:
        rms = pcm_rms(pcm)
        if rms >= SILENCE_RMS_THRESHOLD:
            self.heard_speech = True
            self.speech_chunks += 1
            self.silence_chunks = 0
            self.idle_chunks = 0
        elif self.heard_speech:
            self.silence_chunks += 1
        else:
            self.idle_chunks += 1
        self.total_chunks += 1

        if (
            self.heard_speech
            and self.speech_chunks >= MIN_SPEECH_CHUNKS
            and self.silence_chunks >= SILENCE_CHUNKS
        ):
            return True
        if not self.heard_speech and self.idle_chunks >= NO_SPEECH_CHUNKS:
            return True
        return self.total_chunks >= MAX_UTTERANCE_CHUNKS
