from __future__ import annotations

import json
import os
import re

from jarvis.media.youtube import studio_query

_PATH = os.path.join(os.getcwd(), "jarvis-library.json")
_HISTORY_LIMIT = 200


def _key(text: str) -> str:
    cleaned = studio_query(text).casefold().replace("&", " and ")
    cleaned = re.sub(r"[^0-9a-z\u00c0-\u024f]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _contains(haystack: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {haystack} "


def match_score(query: str, track: dict) -> int:
    want = _key(query)
    if not want:
        return 0
    title = _key(str(track.get("title") or ""))
    stored = _key(str(track.get("query") or ""))
    if want in {title, stored}:
        return 3
    if _contains(title, want) or _contains(stored, want) or _contains(want, title):
        return 2
    want_tokens = set(want.split())
    have = set(f"{title} {stored}".split())
    if want_tokens and len(want_tokens & have) / len(want_tokens) >= 0.75:
        return 1
    return 0


class Library:
    def __init__(self, path: str = _PATH) -> None:
        self._path = path
        self._data = {"history": [], "playlists": {}}
        self._load()

    def find(self, query: str) -> tuple[str, dict] | None:
        best: tuple[int, str, dict] | None = None
        for track in reversed(self._data["history"]):
            score = match_score(query, track)
            if score == 3:
                return "history", track
            if score and (best is None or score > best[0]):
                best = (score, "history", track)
        for name, tracks in self._data["playlists"].items():
            for track in tracks:
                score = match_score(query, track)
                if score == 3:
                    return f"playlist {name}", track
                if score and (best is None or score > best[0]):
                    best = (score, f"playlist {name}", track)
        if best is None:
            return None
        return best[1], best[2]

    def remember(self, track: dict) -> None:
        saved = _record(track)
        history = [
            item
            for item in self._data["history"]
            if not _same(item, saved)
        ]
        history.append(saved)
        self._data["history"] = history[-_HISTORY_LIMIT:]
        self._save()

    def create(self, name: str) -> str:
        title = name.strip()
        if not title:
            raise ValueError("missing playlist name")
        existing = self._playlist_name(title)
        if existing is None:
            self._data["playlists"][title] = []
            self._save()
            return title
        return existing

    def add(self, name: str, track: dict) -> str:
        title = self.create(name)
        tracks = self._data["playlists"][title]
        saved = _record(track)
        if any(_same(item, saved) for item in tracks):
            return title
        tracks.append(saved)
        self._save()
        return title

    def tracks(self, name: str) -> list[dict]:
        title = self._playlist_name(name)
        if title is None:
            raise KeyError(name.strip())
        return [dict(item) for item in self._data["playlists"][title]]

    def _playlist_name(self, name: str) -> str | None:
        want = name.strip().casefold()
        if not want:
            return None
        for existing in self._data["playlists"]:
            if existing.casefold() == want:
                return existing
        return None

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        history = payload.get("history")
        playlists = payload.get("playlists")
        if isinstance(history, list):
            self._data["history"] = [item for item in history if isinstance(item, dict)]
        if isinstance(playlists, dict):
            self._data["playlists"] = {
                str(name): [item for item in tracks if isinstance(item, dict)]
                for name, tracks in playlists.items()
                if isinstance(tracks, list)
            }

    def _save(self) -> None:
        temporary = f"{self._path}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self._data, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, self._path)


def _record(track: dict) -> dict:
    return {
        "title": str(track.get("title") or "").strip(),
        "query": str(track.get("query") or track.get("title") or "").strip(),
        "webpage_url": str(track.get("webpage_url") or "").strip(),
        "video_id": str(track.get("video_id") or "").strip(),
    }


def _same(left: dict, right: dict) -> bool:
    if left.get("video_id") and left.get("video_id") == right.get("video_id"):
        return True
    if left.get("webpage_url") and left.get("webpage_url") == right.get("webpage_url"):
        return True
    return _key(str(left.get("title") or "")) == _key(str(right.get("title") or "")) and bool(
        left.get("title")
    )
