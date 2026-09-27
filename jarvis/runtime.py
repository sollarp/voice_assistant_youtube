from __future__ import annotations

import asyncio
import signal
import sys
import time

from jarvis.audio.microphone import Microphone, WakeWord
from jarvis.audio.player import MPVController
from jarvis.audio.speaker import Speaker
from jarvis.config import (
    CHUNK,
    MUSIC_VOLUME_DUCKED,
    MUSIC_VOLUME_NORMAL,
    RATE,
    WAKE_CONFIRM_CHUNKS,
    WAKE_CONFIRM_CHUNKS_MUSIC,
    WAKE_COOLDOWN_SECONDS,
    WAKE_FALSE_COOLDOWN_SECONDS,
    WAKE_PLAYBACK_COOLDOWN_SECONDS,
    WAKE_QUIET,
    WAKE_QUIET_CHUNKS,
    WAKE_THRESHOLD,
    WAKE_THRESHOLD_MUSIC,
)
from jarvis.intent.handler import MusicControl
from jarvis.llm.client import build_client
from jarvis.llm.live import LiveGateway
from jarvis.log import log
from jarvis.media.youtube import YouTubeResolver


class Assistant:
    def __init__(self) -> None:
        client = build_client()
        self._player = MPVController()
        self._controls = MusicControl(self._player, YouTubeResolver())
        self._live = LiveGateway(client, self._controls.handle)
        self._shutdown = asyncio.Event()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown.set)
            except NotImplementedError:
                signal.signal(sig, lambda *_: self._shutdown.set())

        log("starting")
        try:
            await asyncio.to_thread(self._player.ensure)
        except Exception as exc:
            log(f"mpv unavailable: {exc}")
        mic = Microphone()
        wake = WakeWord()
        speaker = Speaker(mic.device_name)
        log("listening")
        streak = 0
        calm = 0
        media_on = False
        media_until = 0.0
        speaker_guard = False
        try:
            while not self._shutdown.is_set():
                pcm = await asyncio.to_thread(mic.read)
                if speaker.audible():
                    if not speaker_guard:
                        log("ignoring the microphone until the speaker finishes")
                        speaker_guard = True
                    streak = 0
                    calm = 0
                    continue
                if speaker_guard:
                    wake.reset()
                    speaker_guard = False
                    streak = 0
                    calm = 0
                now = time.monotonic()
                if now >= media_until:
                    media_on = self._player.making_sound()
                    media_until = now + 1.0
                score = wake.score(pcm)
                if score < WAKE_QUIET:
                    calm = WAKE_QUIET_CHUNKS
                    streak = 0
                    continue
                if calm <= 0:
                    streak = 0
                    continue
                calm -= 1
                needed = WAKE_THRESHOLD_MUSIC if media_on else WAKE_THRESHOLD
                if score <= needed:
                    streak = 0
                    continue
                streak += 1
                needed_chunks = WAKE_CONFIRM_CHUNKS_MUSIC if media_on else WAKE_CONFIRM_CHUNKS
                if streak < needed_chunks:
                    continue
                streak = 0
                calm = 0
                wake.reset()
                heard_speech = True
                try:
                    self._player.set_volume(MUSIC_VOLUME_DUCKED)
                    log(f"Hey Jarvis ({score:.2f})")
                    await asyncio.to_thread(speaker.beep)
                    for _ in range(4):
                        await asyncio.to_thread(mic.read)
                    heard_speech = await self._live.run(mic, speaker)
                except Exception as exc:
                    log(f"wake handling failed: {exc}")
                finally:
                    await asyncio.to_thread(speaker.drain)
                    self._player.set_volume(MUSIC_VOLUME_NORMAL)
                playing = self._player.making_sound()
                if not heard_speech:
                    pause = WAKE_FALSE_COOLDOWN_SECONDS
                elif playing:
                    pause = WAKE_PLAYBACK_COOLDOWN_SECONDS
                    log("ignoring wake word while the song starts")
                else:
                    pause = WAKE_COOLDOWN_SECONDS
                for _ in range(int(pause * RATE / CHUNK)):
                    await asyncio.to_thread(mic.read)
                wake.reset()
                streak = 0
                log("listening")
        finally:
            self._player.close()
            speaker.close()
            mic.close()
            log("stopped")


async def _run() -> None:
    await Assistant().run()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        sys.exit(0)
