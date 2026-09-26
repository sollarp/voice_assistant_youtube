from google.genai import types

from jarvis.config import JSON_MODEL
from jarvis.domain.intent import SessionMemory
from jarvis.llm.prompts import RESPONSE_SCHEMA, SYSTEM_INSTRUCTION
from jarvis.log import log


def _instruction(memory: SessionMemory) -> str:
    last_song = memory.last_song_query or "none"
    last_offset = memory.last_version_offset
    return (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"Session memory:\n"
        f"- last_song_query: {last_song}\n"
        f"- last_version_offset: {last_offset}\n"
        f"If the user asks for another version, set action to search_alternate "
        f"and version_offset to {last_offset + 1}."
    )


class TextRouter:
    def __init__(self, client) -> None:
        self._client = client

    async def route(self, transcript: str, memory: SessionMemory) -> str:
        instruction = _instruction(memory)
        configs = [
            types.GenerateContentConfig(
                system_instruction=instruction,
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
            ),
            types.GenerateContentConfig(
                system_instruction=instruction,
                response_mime_type="application/json",
            ),
            types.GenerateContentConfig(system_instruction=instruction),
        ]
        last_error = None
        for config in configs:
            try:
                response = await self._client.aio.models.generate_content(
                    model=JSON_MODEL,
                    contents=transcript,
                    config=config,
                )
                return (response.text or "").strip()
            except Exception as exc:
                last_error = exc
                log(f"json route failed: {exc}")
        raise RuntimeError(f"unable to route transcript: {last_error}")
