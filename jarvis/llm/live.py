from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from google.genai import types

from jarvis.audio.microphone import Microphone
from jarvis.audio.speaker import Speaker
from jarvis.audio.vad import VoiceActivity
from jarvis.config import (
    LIVE_MODEL,
    MAX_UTTERANCE_SECONDS,
    PCM_MIME,
    RESPONSE_TIMEOUT,
)
from jarvis.llm.prompts import MUSIC_TOOL, SYSTEM_INSTRUCTION
from jarvis.log import log

ToolHandler = Callable[[dict], Awaitable[dict]]


def _live_config() -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=SYSTEM_INSTRUCTION,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        tools=[
            types.Tool(function_declarations=[MUSIC_TOOL]),
            types.Tool(google_search=types.GoogleSearch()),
        ],
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
        ),
    )


async def _send_activity(session, kind: str) -> None:
    try:
        if kind == "start":
            await session.send_realtime_input(activity_start=types.ActivityStart())
        else:
            await session.send_realtime_input(activity_end=types.ActivityEnd())
    except Exception as exc:
        log(f"activity {kind} not accepted: {exc}")
        if kind == "end":
            try:
                await session.send_realtime_input(audio_stream_end=True)
            except Exception as end_exc:
                log(f"audio_stream_end not accepted: {end_exc}")


async def _buffer(mic: Microphone, stop: asyncio.Event, chunks: list[bytes]) -> None:
    while not stop.is_set():
        chunks.append(await asyncio.to_thread(mic.read))


class LiveGateway:
    def __init__(self, client, on_tool: ToolHandler) -> None:
        self._client = client
        self._on_tool = on_tool

    async def run(self, mic: Microphone, speaker: Speaker) -> bool:
        preroll: list[bytes] = []
        stop = asyncio.Event()
        buffer_task = asyncio.create_task(_buffer(mic, stop, preroll))
        try:
            async with self._client.aio.live.connect(
                model=LIVE_MODEL,
                config=_live_config(),
            ) as session:
                stop.set()
                await buffer_task
                log(f"live session {LIVE_MODEL} ({len(preroll)} buffered chunks)")
                tasks: list[asyncio.Task] = []
                sender = asyncio.create_task(_stream(session, mic, preroll))
                receiver = asyncio.create_task(_receive(session, speaker, tasks, self._on_tool))
                heard_speech = True
                try:
                    heard_speech = await sender
                    if not heard_speech:
                        log("no speech after wake, ignoring")
                    else:
                        await asyncio.wait_for(receiver, timeout=RESPONSE_TIMEOUT)
                except asyncio.TimeoutError:
                    log("gemini response wait ended")
                finally:
                    for task in (receiver, sender):
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except (asyncio.CancelledError, Exception):
                                pass
                    if not heard_speech:
                        for task in tasks:
                            task.cancel()
                        speaker.drop()
                if not heard_speech:
                    return False
                if tasks:
                    try:
                        await asyncio.wait_for(asyncio.gather(*tasks), timeout=45)
                    except asyncio.TimeoutError:
                        log("music tool timed out")
                        for task in tasks:
                            task.cancel()
        finally:
            if not buffer_task.done():
                stop.set()
                try:
                    await buffer_task
                except Exception:
                    pass
        return True


async def _stream(session, mic: Microphone, preroll: list[bytes]) -> bool:
    await _send_activity(session, "start")
    vad = VoiceActivity()
    finished = False
    for pcm in preroll:
        await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type=PCM_MIME))
        if vad.update(pcm, stop_on_idle=False):
            finished = True
            break
    if not finished:
        vad.forgive_leading_silence()
        while vad.elapsed < MAX_UTTERANCE_SECONDS:
            pcm = await asyncio.to_thread(mic.read)
            await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type=PCM_MIME))
            if vad.update(pcm):
                break
    log(f"microphone stream ended (speech={vad.heard_speech}, {vad.elapsed:.1f}s)")
    if vad.heard_speech:
        await _send_activity(session, "end")
    return vad.heard_speech


async def _receive(session, speaker: Speaker, tasks: list[asyncio.Task], on_tool: ToolHandler) -> None:
    heard: list[str] = []
    spoken: list[str] = []
    try:
        async for response in session.receive():
            tool_call = getattr(response, "tool_call", None)
            if tool_call:
                for call in tool_call.function_calls or []:
                    tasks.append(asyncio.create_task(_run_tool(session, call, on_tool)))
            audio = getattr(response, "data", None)
            if audio:
                speaker.write(audio)
            content = getattr(response, "server_content", None)
            if content is not None:
                _collect(content, "input_transcription", heard)
                _collect(content, "output_transcription", spoken)
                if getattr(content, "turn_complete", False):
                    break
    finally:
        heard_text = "".join(heard).strip()
        spoken_text = "".join(spoken).strip()
        if heard_text:
            log(f"heard: {heard_text}")
        if spoken_text:
            log(f"jarvis: {spoken_text}")


def _collect(content, name: str, parts: list[str]) -> None:
    transcription = getattr(content, name, None)
    text = getattr(transcription, "text", None) if transcription is not None else None
    if text:
        parts.append(text)


async def _run_tool(session, call, on_tool: ToolHandler) -> None:
    name = getattr(call, "name", None)
    args = dict(getattr(call, "args", None) or {})
    try:
        if name != "control_music_player":
            result = {"ok": False, "error": f"unknown tool {name}"}
        else:
            result = await on_tool(args)
    except Exception as exc:
        log(f"tool failed: {exc}")
        result = {"ok": False, "error": str(exc)}
    body = {"output": result} if result.get("ok") else {"error": result.get("error") or "failed"}
    try:
        await session.send_tool_response(
            function_responses=[
                types.FunctionResponse(
                    id=getattr(call, "id", None),
                    name=name,
                    scheduling="SILENT",
                    response=body,
                )
            ]
        )
    except Exception as exc:
        log(f"tool response failed: {exc}")
