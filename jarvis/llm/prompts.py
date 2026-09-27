SYSTEM_INSTRUCTION = (
    "You are Jarvis, a bilingual AI voice assistant. "
    "You can understand and speak both English and Hungarian fluently. "
    "Respond in the same language the user speaks to you. "
    "Use the 'control_music_player' tool for playback commands in either language, "
    "including stop, stopp, and állj, which must use action stop to end the current song. "
    "Use create_playlist, add_to_playlist, and play_playlist for saved music. "
    "Add this song to my playlist NAME means add_to_playlist with that name and no query. "
    "Play my playlist NAME, when normal or random was not said, means ask which order they want "
    "and do not call the tool yet. "
    "Play my playlist NAME in random means play_playlist with order random. "
    "Play my playlist NAME in order means play_playlist with order normal. "
    "Volume is a scale from 1 to 10, and 10 is the loudest. "
    "Volume up means volume_up. Volume down means volume_down. "
    "A number from 1 to 10 means set_volume with that level. "
    "Delete this song means delete_song with no query. "
    "Delete the playlist called NAME means delete_playlist with that name. "
    "What playlists do you have means list_playlists, then say every returned name. "
    "Use Google Search for factual queries. Keep all spoken responses under 20 seconds."
)

MUSIC_TOOL = {
    "name": "control_music_player",
    "description": (
        "Control playback and saved music. play starts a song and reuses a saved playlist or "
        "history match before searching YouTube. pause holds the song, resume continues it, "
        "stop ends it and clears a queued playlist, and next_version plays another official recording. "
        "create_playlist stores an empty named list. "
        "add_to_playlist adds a song. For 'add this song to my playlist NAME', "
        "pass name and omit query so the current song is saved. "
        "play_playlist plays every song in the named list. "
        "For 'play my playlist NAME' with no order, do not call the tool; ask normal or random. "
        "For 'play my playlist NAME in random', call it with order random. "
        "For 'play my playlist NAME in order', call it with order normal. "
        "volume_up raises the level by 2. volume_down lowers it by 2. "
        "set_volume uses level 1 to 10. "
        "delete_song removes the current song from the library when query is omitted. "
        "delete_playlist removes the named list. "
        "list_playlists returns the playlist names; say those names to the user. "
        "The same commands work in Hungarian, including lejátszási lista, sorban, and keverve. "
        "query is the song and artist. name is the playlist name. "
        "offset is the 1-based official match and defaults to 1."
    ),
    "behavior": "NON_BLOCKING",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "play",
                    "pause",
                    "resume",
                    "stop",
                    "next_version",
                    "create_playlist",
                    "add_to_playlist",
                    "play_playlist",
                    "volume_up",
                    "volume_down",
                    "set_volume",
                    "delete_song",
                    "delete_playlist",
                    "list_playlists",
                ],
            },
            "query": {"type": "STRING"},
            "name": {"type": "STRING"},
            "level": {"type": "INTEGER"},
            "order": {"type": "STRING", "enum": ["normal", "random"]},
            "offset": {"type": "INTEGER"},
        },
        "required": ["action"],
    },
}
