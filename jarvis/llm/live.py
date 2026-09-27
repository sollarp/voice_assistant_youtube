from __future__ import annotations

import asyncio
import base64
import os
import re
import wave
from collections.abc import Awaitable, Callable

from google.genai import types

from jarvis.audio.microphone import Microphone
from jarvis.audio.speaker import Speaker
from jarvis.audio.vad import VoiceActivity
from jarvis.config import (
    LIVE_MODEL,
    MAX_UTTERANCE_SECONDS,
    OUTPUT_RATE,
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
                        speaker.drop()
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
    vad = VoiceActivity()
    held: list[bytes] = []
    streaming = False

    async def push(pcm: bytes, *, stop_on_idle: bool) -> bool:
        nonlocal streaming
        done = vad.update(pcm, stop_on_idle=stop_on_idle or streaming)
        if not vad.heard_speech:
            held.append(pcm)
            if len(held) > 6:
                del held[:-6]
            return done
        if not streaming:
            streaming = True
            held.append(pcm)
            await _send_activity(session, "start")
            for item in held:
                await session.send_realtime_input(audio=types.Blob(data=item, mime_type=PCM_MIME))
            held.clear()
            return False
        await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type=PCM_MIME))
        return done

    finished = False
    for pcm in preroll:
        if await push(pcm, stop_on_idle=False):
            finished = True
            break
    if not finished:
        vad.forgive_leading_silence()
        while vad.elapsed < MAX_UTTERANCE_SECONDS:
            pcm = await asyncio.to_thread(mic.read)
            if await push(pcm, stop_on_idle=True):
                break
    log(f"microphone stream ended (speech={vad.heard_speech}, {vad.elapsed:.1f}s)")
    if not streaming:
        return False
    await _send_activity(session, "end")
    return True


async def _receive(session, speaker: Speaker, tasks: list[asyncio.Task], on_tool: ToolHandler) -> None:
    heard: list[str] = []
    spoken: list[str] = []
    shapes: list[str] = []
    audio = bytearray()
    audio_rate = OUTPUT_RATE
    chunks = 0
    try:
        async for response in session.receive():
            tool_call = getattr(response, "tool_call", None)
            if tool_call:
                for call in tool_call.function_calls or []:
                    tasks.append(asyncio.create_task(_run_tool(session, call, on_tool)))
            shape = _shape(response)
            if shape and shape not in shapes:
                shapes.append(shape)
            for mime, pcm in _audio_parts(response):
                rate = _pcm_rate(mime)
                if chunks == 0:
                    audio_rate = rate
                    log(f"gemini audio {mime}, {len(pcm)} bytes, rms={_rms(pcm):.0f}")
                chunks += 1
                audio.extend(pcm)
                speaker.write(pcm, rate)
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
        if chunks == 0:
            detail = " | ".join(shapes[:6]) or "no server messages"
            log(f"wav not written, no audio bytes from gemini: {detail}")
        else:
            log(f"gemini audio {chunks} chunks, {len(audio)} bytes, {audio_rate} Hz")
            _save_wav(bytes(audio), audio_rate)


def _audio_parts(response) -> list[tuple[str, bytes]]:
    content = getattr(response, "server_content", None)
    turn = getattr(content, "model_turn", None) if content is not None else None
    found: list[tuple[str, bytes]] = []
    for part in getattr(turn, "parts", None) or []:
        inline = getattr(part, "inline_data", None)
        if inline is None:
            continue
        pcm = _as_pcm(getattr(inline, "data", None))
        if pcm is None:
            continue
        mime = str(getattr(inline, "mime_type", None) or "audio/pcm")
        if "audio" in mime or "pcm" in mime or "l16" in mime:
            found.append((mime, pcm))
    if found:
        return found
    pcm = _as_pcm(getattr(response, "data", None))
    if pcm is not None:
        return [("audio/pcm", pcm)]
    return []


def _as_pcm(raw) -> bytes | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = base64.b64decode(raw)
        except Exception:
            return None
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    elif isinstance(raw, bytearray):
        raw = bytes(raw)
    if not isinstance(raw, bytes) or len(raw) < 2:
        return None
    return raw[: len(raw) // 2 * 2]


def _pcm_rate(mime: str) -> int:
    match = re.search(r"rate=(\d+)", mime)
    return int(match.group(1)) if match else OUTPUT_RATE


def _rms(pcm: bytes) -> float:
    count = min(len(pcm) // 2, 2400)
    if count == 0:
        return 0.0
    total = 0
    for index in range(count):
        sample = int.from_bytes(pcm[index * 2 : index * 2 + 2], "little", signed=True)
        total += sample * sample
    return (total / count) ** 0.5


def _shape(response) -> str:
    bits: list[str] = []
    if getattr(response, "tool_call", None):
        bits.append("tool_call")
    content = getattr(response, "server_content", None)
    if content is None:
        return ",".join(bits)
    if getattr(content, "input_transcription", None):
        bits.append("input_transcription")
    if getattr(content, "output_transcription", None):
        bits.append("output_transcription")
    if getattr(content, "interrupted", False):
        bits.append("interrupted")
    if getattr(content, "turn_complete", False):
        bits.append("turn_complete")
    turn = getattr(content, "model_turn", None)
    for part in getattr(turn, "parts", None) or []:
        inline = getattr(part, "inline_data", None)
        if inline is not None:
            data = getattr(inline, "data", None)
            mime = getattr(inline, "mime_type", None) or "?"
            size = len(data) if hasattr(data, "__len__") else 0
            bits.append(f"inline:{mime}:{type(data).__name__}:{size}")
        elif getattr(part, "text", None):
            bits.append("text")
    return ",".join(bits)


def _save_wav(pcm: bytes, rate: int) -> None:
    paths = (
        "/tmp/jarvis-reply.wav",
        os.path.join(os.getcwd(), "jarvis-reply.wav"),
    )
    for path in paths:
        try:
            with wave.open(path, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(rate)
                handle.writeframes(pcm)
        except OSError as exc:
            log(f"could not save {path}: {exc}")
            continue
        log(f"saved {path}")


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
