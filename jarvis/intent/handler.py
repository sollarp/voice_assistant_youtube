import json

from jarvis.audio.player import Player
from jarvis.audio.tts import speak
from jarvis.config import MUSIC_CONTROL_ACTIONS, SEEK_SECONDS_DEFAULT
from jarvis.domain.intent import Intent
from jarvis.log import log
from jarvis.media.playlists import PlaylistStore
from jarvis.media.youtube import search_audio


class IntentHandler:
    def __init__(self, player: Player, playlists: PlaylistStore) -> None:
        self._player = player
        self._playlists = playlists

    def run(self, intent: Intent) -> None:
        speak(intent.spoken_response)

        if intent.action in {"play_music", "search_alternate"}:
            self._play(intent)
            return
        if intent.action == "add_to_playlist":
            self._add_to_playlist(intent)
            return
        if intent.action in MUSIC_CONTROL_ACTIONS:
            self._control(intent)

    def _play(self, intent: Intent) -> None:
        if not intent.song_query:
            speak("I need a song name before I can search YouTube.")
            return
        offset = intent.version_offset or 1
        log(f"searching youtube for {intent.song_query!r} #{offset}")
        result = search_audio(intent.song_query, offset=offset)
        print(result["webpage_url"], flush=True)
        log(f"streaming {result['title']}")
        self._player.play(result["stream_url"])

    def _add_to_playlist(self, intent: Intent) -> None:
        if not intent.song_query or not intent.playlist_name:
            speak("I need both a song and a playlist name to save that.")
            return
        offset = intent.version_offset or 1
        result = search_audio(intent.song_query, offset=offset)
        store = self._playlists.add(
            intent.playlist_name, result["title"], result["webpage_url"]
        )
        print(json.dumps(store, indent=2), flush=True)

    def _control(self, intent: Intent) -> None:
        if not self._player.is_playing():
            speak("Nothing is playing right now.")
            return
        if intent.action == "pause_music" and not self._player.pause():
            speak("I could not pause the music.")
        elif intent.action == "resume_music" and not self._player.resume():
            speak("I could not resume the music.")
        elif intent.action == "stop_music":
            self._player.stop()
            log("stopped")
        elif intent.action == "seek_music":
            seconds = intent.seek_seconds or SEEK_SECONDS_DEFAULT
            if not self._player.seek(int(seconds)):
                speak("I could not jump in the track.")
