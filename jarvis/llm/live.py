from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from google.genai import types

from jarvis.audio.microphone import Microphone
from jarvis.audio.vad import VoiceActivity
from jarvis.config import (
    LIVE_MODELS,
    MAX_UTTERANCE_CHUNKS,
    PCM_MIME,
    TRANSCRIPT_TIMEOUT,
)
from jarvis.llm.prompts import LIVE_INSTRUCTION
from jarvis.log import log


def _live_config() -> dict:
    return {
        "response_modalities": ["AUDIO"],
        "system_instruction": LIVE_INSTRUCTION,
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "realtime_input_config": {
            "automatic_activity_detection": {"disabled": True},
        },
    }


@asynccontextmanager
async def _connect(client):
    last_error = None
    session = None
    session_cm = None
    tried = set()
    for model_name in LIVE_MODELS:
        if model_name in tried:
            continue
        tried.add(model_name)
        candidate = client.aio.live.connect(model=model_name, config=_live_config())
        try:
            session = await candidate.__aenter__()
            session_cm = candidate
            log(f"live session {model_name}")
            break
        except Exception as exc:
            last_error = exc
            log(f"live connect failed ({model_name}): {exc}")
            try:
                await candidate.__aexit__(type(exc), exc, exc.__traceback__)
            except Exception:
                pass
    if session is None or session_cm is None:
        raise RuntimeError(f"unable to open live session: {last_error}")
    try:
        yield session
    finally:
        await session_cm.__aexit__(None, None, None)


async def _send_activity(session, kind: str) -> None:
    try:
        if kind == "start":
            await session.send_realtime_input(activity_start=types.ActivityStart())
        else:
            await session.send_realtime_input(activity_end=types.ActivityEnd())
    except Exception:
        if kind == "end":
            try:
                await session.send_realtime_input(audio_stream_end=True)
            except Exception:
                pass


async def _buffer_until(mic: Microphone, stop_event: asyncio.Event, chunks: list[bytes]) -> None:
    while not stop_event.is_set():
        chunks.append(await asyncio.to_thread(mic.read))


async def _stream(session, mic: Microphone, preroll: list[bytes]) -> None:
    await _send_activity(session, "start")
    vad = VoiceActivity()
    done = False
    for pcm in preroll:
        await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type=PCM_MIME))
        if vad.update(pcm):
            done = True
            break
    if not done:
        for _ in range(MAX_UTTERANCE_CHUNKS):
            pcm = await asyncio.to_thread(mic.read)
            await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type=PCM_MIME))
            if vad.update(pcm):
                break
    await _send_activity(session, "end")


async def _collect(session, collected: dict[str, str]) -> None:
    input_parts: list[str] = []
    output_parts: list[str] = []
    text_parts: list[str] = []
    try:
        async for response in session.receive():
            text = getattr(response, "text", None)
            if text:
                text_parts.append(text)
            server_content = getattr(response, "server_content", None)
            if server_content is not None:
                input_transcription = getattr(server_content, "input_transcription", None)
                if input_transcription is not None and getattr(input_transcription, "text", None):
                    input_parts.append(input_transcription.text)
                output_transcription = getattr(server_content, "output_transcription", None)
                if output_transcription is not None and getattr(output_transcription, "text", None):
                    output_parts.append(output_transcription.text)
            collected["text"] = "".join(text_parts).strip()
            collected["input"] = "".join(input_parts).strip()
            collected["output"] = "".join(output_parts).strip()
            if server_content is not None and getattr(server_content, "turn_complete", False):
                break
    except asyncio.CancelledError:
        raise
    finally:
        collected["text"] = "".join(text_parts).strip()
        collected["input"] = "".join(input_parts).strip()
        collected["output"] = "".join(output_parts).strip()


class LiveGateway:
    def __init__(self, client) -> None:
        self._client = client

    async def transcribe(self, mic: Microphone) -> str:
        preroll: list[bytes] = []
        stop_buffer = asyncio.Event()
        buffer_task = asyncio.create_task(_buffer_until(mic, stop_buffer, preroll))
        turn = {"text": "", "input": "", "output": ""}
        try:
            async with _connect(self._client) as session:
                stop_buffer.set()
                await buffer_task
                sender = asyncio.create_task(_stream(session, mic, preroll))
                collector = asyncio.create_task(_collect(session, turn))
                try:
                    await sender
                    await asyncio.wait_for(collector, timeout=TRANSCRIPT_TIMEOUT)
                except asyncio.TimeoutError:
                    log("transcript wait ended")
                finally:
                    for task in (collector, sender):
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except (asyncio.CancelledError, Exception):
                                pass
        finally:
            if not buffer_task.done():
                stop_buffer.set()
                try:
                    await buffer_task
                except Exception:
                    pass
        return turn.get("input") or turn.get("text") or ""
