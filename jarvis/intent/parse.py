import json
import re

from jarvis.config import MUSIC_CONTROL_ACTIONS, SEEK_SECONDS_DEFAULT
from jarvis.domain.intent import Intent, SessionMemory


def extract_json(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("empty model response")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("model json was not an object")
    return parsed


def _blank_to_none(value):
    if value in ("", "null"):
        return None
    if isinstance(value, str):
        return value.strip() or None
    return value


def normalize(payload: dict, memory: SessionMemory) -> Intent:
    action = str(payload.get("action") or "conversation").strip().lower()
    spoken = str(payload.get("spoken_response") or "I did not catch that.").strip()
    song_query = _blank_to_none(payload.get("song_query"))
    playlist_name = _blank_to_none(payload.get("playlist_name"))
    try:
        version_offset = int(payload.get("version_offset") or 1)
    except (TypeError, ValueError):
        version_offset = 1
    try:
        seek_seconds = payload.get("seek_seconds")
        seek_seconds = None if seek_seconds in ("", "null", None) else int(seek_seconds)
    except (TypeError, ValueError):
        seek_seconds = None

    if action == "search_alternate":
        song_query = song_query or memory.last_song_query
        version_offset = max(version_offset, memory.last_version_offset + 1, 2)
        if song_query:
            memory.last_song_query = song_query
            memory.last_version_offset = version_offset
    elif action in {"play_music", "add_to_playlist"}:
        version_offset = max(version_offset, 1)
        if song_query:
            memory.last_song_query = song_query
            memory.last_version_offset = version_offset
    elif action == "seek_music":
        if seek_seconds is None:
            seek_seconds = SEEK_SECONDS_DEFAULT
    elif action not in MUSIC_CONTROL_ACTIONS:
        action = "conversation"
        version_offset = 1
        seek_seconds = None

    return Intent(
        action=action,
        spoken_response=spoken,
        song_query=song_query,
        playlist_name=playlist_name,
        version_offset=version_offset,
        seek_seconds=seek_seconds,
    )
