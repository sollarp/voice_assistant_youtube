SYSTEM_INSTRUCTION = (
    "You are Jarvis, a bilingual AI voice assistant. "
    "You can understand and speak both English and Hungarian fluently. "
    "Respond in the same language the user speaks to you. "
    "Use the 'control_music_player' tool for playback commands in either language, "
    "including stop to end the current song. "
    "Use Google Search for factual queries. Keep all spoken responses under 20 seconds."
)

MUSIC_TOOL = {
    "name": "control_music_player",
    "description": (
        "Control playback. action play starts a song, pause holds it, resume continues it, "
        "stop ends it, and next_version plays another official recording. "
        "query is the song and artist. offset is the 1-based official match and defaults to 1."
    ),
    "behavior": "NON_BLOCKING",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["play", "pause", "resume", "stop", "next_version"],
            },
            "query": {"type": "STRING"},
            "offset": {"type": "INTEGER"},
        },
        "required": ["action"],
    },
}
