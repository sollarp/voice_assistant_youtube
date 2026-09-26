from __future__ import annotations

import asyncio
import json
import signal
import sys

from jarvis.audio.microphone import Microphone, WakeWord
from jarvis.audio.player import Player
from jarvis.audio.tts import speak
from jarvis.domain.intent import SessionMemory
from jarvis.intent.handler import IntentHandler
from jarvis.intent.parse import extract_json, normalize
from jarvis.llm.client import build_client
from jarvis.llm.live import LiveGateway
from jarvis.llm.router import TextRouter
from jarvis.log import log
from jarvis.media.playlists import PlaylistStore


class Assistant:
    def __init__(self) -> None:
        self._client = build_client()
        self._live = LiveGateway(self._client)
        self._router = TextRouter(self._client)
        self._player = Player()
        self._handler = IntentHandler(self._player, PlaylistStore())
        self._memory = SessionMemory()
        self._shutdown = asyncio.Event()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown.set)
            except NotImplementedError:
                signal.signal(sig, lambda *_: self._shutdown.set())

        log("starting")
        mic = Microphone()
        wake = WakeWord()
        log("listening")
        try:
            while not self._shutdown.is_set():
                pcm = await asyncio.to_thread(mic.read)
                if not wake.triggered(pcm):
                    continue
                wake.reset()
                self._player.duck()
                await asyncio.sleep(0.2)
                try:
                    await self._handle_wake(mic)
                except Exception as exc:
                    log(f"wake handling failed: {exc}")
                    speak("I had trouble reaching the assistant. Please try again.")
                finally:
                    self._player.restore_volume()
                for _ in range(8):
                    await asyncio.to_thread(mic.read)
                wake.reset()
                log("listening")
        finally:
            self._player.stop()
            mic.close()
            log("stopped")

    async def _handle_wake(self, mic: Microphone) -> None:
        log("wake word")
        transcript = await self._live.transcribe(mic)
        if not transcript:
            speak("I didn't catch that. Please say Hey Jarvis and try again.")
            return
        log(f"heard: {transcript}")
        try:
            raw = await self._router.route(transcript, self._memory)
            intent = normalize(extract_json(raw), self._memory)
            self._handler.run(intent)
        except json.JSONDecodeError as exc:
            log(f"json parse failed: {exc}")
            speak("I heard you, but I could not parse the response.")
        except Exception as exc:
            log(f"request failed: {exc}")
            speak("Something went wrong while handling that request.")


async def _run() -> None:
    await Assistant().run()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        sys.exit(0)
