from __future__ import annotations

import asyncio
import random
import threading

from jarvis.audio.player import MPVController
from jarvis.log import log
from jarvis.media.library import Library
from jarvis.media.youtube import YouTubeResolver, studio_query

_CURRENT_SONG = {
    "this",
    "this song",
    "this track",
    "the song",
    "current song",
    "the current song",
    "current track",
    "ez",
    "ezt",
    "ez a dal",
    "ezt a dalt",
    "ez a szám",
    "ezt a számot",
    "a mostani",
    "mostani dal",
}


class MusicControl:
    def __init__(self, player: MPVController, resolver: YouTubeResolver) -> None:
        self._player = player
        self._resolver = resolver
        self._library = Library()
        self._player.remember_level(self._library.volume_level())
        self._query: str | None = None
        self._current: dict | None = None
        self._offset = 1
        self._queue_token = 0

    async def handle(self, args: dict) -> dict:
        return await asyncio.to_thread(self._run, args)

    def _run(self, args: dict) -> dict:
        action = str(args.get("action") or "").strip().lower()
        query = args.get("query")
        query = query.strip() if isinstance(query, str) else ""
        query = query or None
        try:
            offset = int(args.get("offset") or 1)
        except (TypeError, ValueError):
            offset = 1
        offset = max(offset, 1)
        log(f"music {action} query={query!r} offset={offset}")

        name = args.get("name")
        name = name.strip() if isinstance(name, str) else ""
        order = _playback_order(str(args.get("order") or ""))

        if action == "pause":
            return {"ok": self._player.pause(), "action": action}
        if action == "resume":
            return {"ok": self._player.resume(), "action": action}
        if action == "stop":
            self._cancel_queue()
            return {"ok": self._player.stop(), "action": action}
        if action == "next_version":
            return self._next(query, offset)
        if action == "play":
            if not query:
                return {"ok": False, "error": "missing song query"}
            return self._play(query, offset)
        if action == "create_playlist":
            return self._create_playlist(name)
        if action == "add_to_playlist":
            return self._add_to_playlist(name, query)
        if action == "play_playlist":
            return self._play_playlist(name, order)
        if action == "volume_up":
            return self._volume(self._player.change_user_level(2))
        if action == "volume_down":
            return self._volume(self._player.change_user_level(-2))
        if action == "set_volume":
            return self._set_volume(args.get("level"))
        if action == "delete_song":
            return self._delete_song(query)
        if action == "delete_playlist":
            return self._delete_playlist(name)
        if action == "list_playlists":
            return self._list_playlists()
        return {"ok": False, "error": f"unsupported action {action}"}

    def _next(self, query: str | None, offset: int) -> dict:
        song = studio_query(query) if query else None
        same = bool(song and self._query and song == self._query)
        query = query or self._query
        if not query:
            return {"ok": False, "error": "no song to switch"}
        if same or not song:
            offset = max(offset, self._offset + 1, 2)
        else:
            offset = max(offset, 2)
        return self._play(query, offset)

    def _play(self, query: str, offset: int) -> dict:
        if offset == 1:
            found = self._library.find(query)
            if found is not None:
                source, saved = found
                saved = dict(saved)
                saved["query"] = saved.get("query") or query
                return self._start(saved, source=source)
        track = self._resolver.resolve(query, offset=offset)
        track["query"] = query
        result = self._start(track, source="youtube")
        self._offset = offset
        result["offset"] = offset
        return result

    def _create_playlist(self, name: str) -> dict:
        if not name:
            return {"ok": False, "error": "missing playlist name"}
        title = self._library.create(name)
        log(f"playlist {title}")
        return {"ok": True, "action": "create_playlist", "name": title}

    def _add_to_playlist(self, name: str, query: str | None) -> dict:
        if not name:
            return {"ok": False, "error": "missing playlist name"}
        if _mentions_current(query):
            if not self._current:
                return {"ok": False, "error": "nothing is playing"}
            track = dict(self._current)
            title = self._library.add(name, track)
            log(f"added {track['title']} to {title}")
            return {
                "ok": True,
                "action": "add_to_playlist",
                "name": title,
                "title": track["title"],
            }
        song = query or self._query
        if not song:
            return {"ok": False, "error": "missing song"}
        found = self._library.find(song)
        if found is not None:
            track = dict(found[1])
        else:
            track = self._resolver.resolve(song, offset=1)
            track["query"] = song
            self._library.remember(track)
        title = self._library.add(name, track)
        log(f"added {track['title']} to {title}")
        return {
            "ok": True,
            "action": "add_to_playlist",
            "name": title,
            "title": track["title"],
        }

    def _play_playlist(self, name: str, order: str) -> dict:
        if order not in {"normal", "random"}:
            return {
                "ok": False,
                "error": "ask the user whether to play the playlist in normal order or random",
            }
        try:
            tracks = self._library.tracks(name)
        except KeyError:
            return {"ok": False, "error": f"no playlist named {name}"}
        if not tracks:
            return {"ok": False, "error": f"playlist {name} is empty"}
        if order == "random":
            random.shuffle(tracks)
        result = self._start(tracks[0], source=f"playlist {name}")
        if not result.get("ok"):
            return result
        self._queue_rest(tracks[1:])
        result["action"] = "play_playlist"
        result["order"] = order
        result["count"] = len(tracks)
        return result

    def _start(self, track: dict, *, source: str) -> dict:
        self._cancel_queue()
        page = str(track.get("webpage_url") or "")
        stream = track.get("stream_url")
        if not stream:
            fresh = self._resolver.resolve_page(page)
            stream = fresh["stream_url"]
            track = {**track, **fresh, "query": track.get("query") or fresh["title"]}
        if not self._player.play(str(stream)):
            return {"ok": False, "error": "mpv rejected the stream"}
        self._player.restore()
        self._library.remember(track)
        self._current = {
            "title": str(track.get("title") or ""),
            "query": str(track.get("query") or track.get("title") or ""),
            "webpage_url": str(track.get("webpage_url") or ""),
            "video_id": str(track.get("video_id") or ""),
        }
        self._query = studio_query(self._current["query"])
        self._offset = 1
        print(track["webpage_url"], flush=True)
        log(f"streaming {track['title']} from {source}")
        return {
            "ok": True,
            "action": "play",
            "title": track["title"],
            "url": track["webpage_url"],
            "source": source,
        }

    def _queue_rest(self, tracks: list[dict]) -> None:
        token = self._queue_token

        def work() -> None:
            for track in tracks:
                if token != self._queue_token:
                    return
                try:
                    fresh = self._resolver.resolve_page(str(track.get("webpage_url") or ""))
                except Exception as exc:
                    log(f"could not queue {track.get('title')}: {exc}")
                    continue
                if token != self._queue_token:
                    return
                if self._player.append(fresh["stream_url"]):
                    log(f"queued {fresh['title']}")

        threading.Thread(target=work, daemon=True).start()

    def _volume(self, level: int) -> dict:
        stored = self._library.set_volume_level(level)
        log(f"volume {stored}")
        return {"ok": True, "action": "volume", "level": stored, "speak": True}

    def _set_volume(self, level) -> dict:
        try:
            requested = int(level)
        except (TypeError, ValueError):
            return {"ok": False, "error": "ask for a volume from 1 to 10"}
        if requested < 1 or requested > 10:
            return {"ok": False, "error": "volume must be from 1 to 10"}
        self._player.set_user_level(requested)
        return self._volume(requested)

    def _delete_song(self, query: str | None) -> dict:
        if _mentions_current(query):
            track = self._current
        else:
            found = self._library.find(query or "")
            track = found[1] if found is not None else None
        if not track:
            return {"ok": False, "error": "that song is not in the library"}
        title = self._library.remove_track(track)
        if self._current and title == self._current.get("title"):
            self._current = None
        log(f"deleted song {title}")
        return {"ok": True, "action": "delete_song", "title": title, "speak": True}

    def _delete_playlist(self, name: str) -> dict:
        if not name:
            return {"ok": False, "error": "missing playlist name"}
        try:
            title = self._library.delete_playlist(name)
        except KeyError:
            return {"ok": False, "error": f"no playlist named {name}"}
        log(f"deleted playlist {title}")
        return {"ok": True, "action": "delete_playlist", "name": title, "speak": True}

    def _list_playlists(self) -> dict:
        names = self._library.names()
        log(f"playlists {names}")
        return {"ok": True, "action": "list_playlists", "playlists": names, "speak": True}

    def _cancel_queue(self) -> None:
        self._queue_token += 1


def _mentions_current(query: str | None) -> bool:
    if not query:
        return True
    return query.casefold().strip(" .") in _CURRENT_SONG


def _playback_order(value: str) -> str:
    text = value.casefold().strip()
    if not text:
        return ""
    if any(word in text for word in ("random", "shuffle", "kever", "véletlen", "veletlen")):
        return "random"
    if any(word in text for word in ("normal", "order", "sorban", "sequence")):
        return "normal"
    return text
