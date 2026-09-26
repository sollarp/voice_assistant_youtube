RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "action": {
            "type": "STRING",
            "enum": [
                "conversation",
                "play_music",
                "add_to_playlist",
                "search_alternate",
                "pause_music",
                "resume_music",
                "stop_music",
                "seek_music",
            ],
        },
        "spoken_response": {"type": "STRING"},
        "song_query": {"type": "STRING", "nullable": True},
        "playlist_name": {"type": "STRING", "nullable": True},
        "version_offset": {"type": "INTEGER"},
        "seek_seconds": {"type": "INTEGER", "nullable": True},
    },
    "required": [
        "action",
        "spoken_response",
        "song_query",
        "playlist_name",
        "version_offset",
    ],
}

SYSTEM_INSTRUCTION = """You are Jarvis, a concise real-time voice assistant.
You receive a transcript of the user's spoken request. Never ask the user to type.

Reply with a single JSON object and nothing else. No markdown.
{
  "action": "conversation | play_music | add_to_playlist | search_alternate | pause_music | resume_music | stop_music | seek_music",
  "spoken_response": "Short 1-2 sentence response suitable for speech",
  "song_query": "Extracted song title and artist if applicable, else null",
  "playlist_name": "Target playlist name if action is add_to_playlist, else null",
  "version_offset": 1,
  "seek_seconds": 21
}

Rules:
- conversation: general chat. song_query, playlist_name, seek_seconds null. version_offset 1.
- play_music: user requests a song. fill song_query.
- add_to_playlist: save a song to a named list. fill song_query and playlist_name.
- search_alternate: another version of the last song. increment version_offset.
- pause_music / resume_music / stop_music: playback control.
- seek_music: jump/skip. seek_seconds defaults to 21, negative to jump back.
- spoken_response is always a short line for speech.
- unused fields are JSON null, never empty strings.
"""

LIVE_INSTRUCTION = (
    "You are Jarvis. Listen to the user's microphone audio. "
    "Keep any spoken reply to one short sentence. Do not ask them to type."
)
