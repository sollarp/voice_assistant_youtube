from __future__ import annotations

import asyncio
import signal
import sys

from jarvis.audio.microphone import Microphone, WakeWord
from jarvis.audio.player import MPVController
from jarvis.audio.speaker import Speaker
from jarvis.config import MUSIC_VOLUME_DUCKED, MUSIC_VOLUME_NORMAL
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
        speaker = Speaker()
        log("listening")
        try:
            while not self._shutdown.is_set():
                pcm = await asyncio.to_thread(mic.read)
                if not wake.triggered(pcm):
                    continue
                wake.reset()
                try:
                    self._player.set_volume(MUSIC_VOLUME_DUCKED)
                    log("Hey Jarvis")
                    await asyncio.to_thread(speaker.beep)
                    for _ in range(4):
                        await asyncio.to_thread(mic.read)
                    await self._live.run(mic, speaker)
                except Exception as exc:
                    log(f"wake handling failed: {exc}")
                finally:
                    await asyncio.to_thread(speaker.drain)
                    self._player.set_volume(MUSIC_VOLUME_NORMAL)
                for _ in range(8):
                    await asyncio.to_thread(mic.read)
                wake.reset()
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
