from __future__ import annotations

import asyncio

from jarvis.audio.player import MPVController
from jarvis.config import MUSIC_VOLUME_DUCKED
from jarvis.log import log
from jarvis.media.youtube import YouTubeResolver, studio_query


class MusicControl:
    def __init__(self, player: MPVController, resolver: YouTubeResolver) -> None:
        self._player = player
        self._resolver = resolver
        self._query: str | None = None
        self._offset = 1

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

        if action == "pause":
            return {"ok": self._player.pause(), "action": action}
        if action == "resume":
            return {"ok": self._player.resume(), "action": action}
        if action == "stop":
            return {"ok": self._player.stop(), "action": action}
        if action == "next_version":
            return self._next(query, offset)
        if action == "play":
            if not query:
                return {"ok": False, "error": "missing song query"}
            return self._play(query, offset)
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
        track = self._resolver.resolve(query, offset=offset)
        if not self._player.play(track["stream_url"]):
            return {"ok": False, "error": "mpv rejected the stream"}
        self._player.set_volume(MUSIC_VOLUME_DUCKED)
        self._query = studio_query(query)
        self._offset = offset
        print(track["webpage_url"], flush=True)
        log(f"streaming {track['title']}")
        return {
            "ok": True,
            "action": "play",
            "title": track["title"],
            "url": track["webpage_url"],
            "offset": offset,
        }
