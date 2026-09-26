from dataclasses import dataclass


@dataclass
class SessionMemory:
    last_song_query: str | None = None
    last_version_offset: int = 1


@dataclass
class Intent:
    action: str
    spoken_response: str
    song_query: str | None = None
    playlist_name: str | None = None
    version_offset: int = 1
    seek_seconds: int | None = None
