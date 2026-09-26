from __future__ import annotations

import os
from contextlib import contextmanager

import numpy as np
import pyaudio

from jarvis.config import CHANNELS, CHUNK, FORMAT, OUTPUT_RATE, RATE
from jarvis.log import log

_INPUT_RATES = (RATE, 48000, 44100, 32000, 22050)
_OUTPUT_RATES = (OUTPUT_RATE, 48000, 44100, 16000)


@contextmanager
def _quiet_alsa():
    """ALSA logs every rejected device to stderr. Hide that while probing."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(2)
    try:
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull)


def resample(pcm: bytes, src_rate: int, dst_rate: int, dst_samples: int | None = None) -> bytes:
    if not pcm:
        return pcm
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if dst_samples is None:
        if src_rate == dst_rate:
            return pcm
        dst_samples = max(1, int(round(samples.size * dst_rate / src_rate)))
    if src_rate == dst_rate and samples.size == dst_samples:
        return pcm
    if samples.size == 1:
        return np.full(dst_samples, samples[0], dtype=np.int16).tobytes()
    src_pos = np.linspace(0.0, 1.0, samples.size, endpoint=False)
    dst_pos = np.linspace(0.0, 1.0, dst_samples, endpoint=False)
    return np.interp(dst_pos, src_pos, samples).astype(np.int16).tobytes()


def _candidate_rates(info: dict, preferred: tuple[int, ...]) -> list[int]:
    default = int(info.get("defaultSampleRate") or 0)
    rates: list[int] = []
    for rate in (default, *preferred):
        if rate > 0 and rate not in rates:
            rates.append(rate)
    return rates


def _devices(pa: pyaudio.PyAudio, *, input_device: bool) -> list[dict]:
    found: list[dict] = []
    seen: set[int] = set()
    try:
        default = (
            pa.get_default_input_device_info()
            if input_device
            else pa.get_default_output_device_info()
        )
        found.append(default)
        seen.add(int(default["index"]))
    except OSError:
        pass
    channel_key = "maxInputChannels" if input_device else "maxOutputChannels"
    for index in range(pa.get_device_count()):
        if index in seen:
            continue
        info = pa.get_device_info_by_index(index)
        if int(info.get(channel_key) or 0) < 1:
            continue
        found.append(info)
        seen.add(index)
    return found


def _supports(pa: pyaudio.PyAudio, info: dict, rate: int, *, input_device: bool) -> bool:
    index = int(info["index"])
    try:
        if input_device:
            return bool(
                pa.is_format_supported(
                    rate,
                    input_device=index,
                    input_channels=CHANNELS,
                    input_format=FORMAT,
                )
            )
        return bool(
            pa.is_format_supported(
                rate,
                output_device=index,
                output_channels=CHANNELS,
                output_format=FORMAT,
            )
        )
    except ValueError:
        return False


def open_input(pa: pyaudio.PyAudio) -> tuple[pyaudio.Stream, int, int]:
    errors: list[str] = []
    with _quiet_alsa():
        for info in _devices(pa, input_device=True):
            name = str(info.get("name") or info["index"])
            index = int(info["index"])
            for rate in _candidate_rates(info, _INPUT_RATES):
                if not _supports(pa, info, rate, input_device=True):
                    continue
                frames = max(1, int(round(CHUNK * rate / RATE)))
                try:
                    stream = pa.open(
                        format=FORMAT,
                        channels=CHANNELS,
                        rate=rate,
                        input=True,
                        input_device_index=index,
                        frames_per_buffer=frames,
                    )
                except OSError as exc:
                    errors.append(f"{name} @ {rate} Hz: {exc}")
                    continue
                log(f"microphone {name} @ {rate} Hz")
                if rate != RATE:
                    log(f"resampling microphone {rate} Hz -> {RATE} Hz")
                return stream, rate, frames
    detail = "; ".join(errors[-3:]) if errors else "no capture device accepted a supported rate"
    raise OSError(f"Could not open a microphone. {detail}")


def open_output(pa: pyaudio.PyAudio) -> tuple[pyaudio.Stream, int]:
    errors: list[str] = []
    with _quiet_alsa():
        for info in _devices(pa, input_device=False):
            name = str(info.get("name") or info["index"])
            index = int(info["index"])
            for rate in _candidate_rates(info, _OUTPUT_RATES):
                if not _supports(pa, info, rate, input_device=False):
                    continue
                try:
                    stream = pa.open(
                        format=FORMAT,
                        channels=CHANNELS,
                        rate=rate,
                        output=True,
                        output_device_index=index,
                    )
                except OSError as exc:
                    errors.append(f"{name} @ {rate} Hz: {exc}")
                    continue
                log(f"speaker {name} @ {rate} Hz")
                if rate != OUTPUT_RATE:
                    log(f"resampling speaker {OUTPUT_RATE} Hz -> {rate} Hz")
                return stream, rate
    detail = "; ".join(errors[-3:]) if errors else "no playback device accepted a supported rate"
    raise OSError(f"Could not open a speaker. {detail}")
