from yt_dlp import YoutubeDL


def search_audio(song_query: str, offset: int = 1) -> dict[str, str]:
    query = f"ytsearch{offset}:{song_query}"
    opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "extract_flat": False,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=False)

    entries = info.get("entries") if isinstance(info, dict) else None
    if entries:
        usable = [entry for entry in entries if entry]
        entry = usable[-1] if usable else None
    else:
        entry = info

    if not entry:
        raise RuntimeError(f"no youtube results for {song_query!r}")

    title = entry.get("title") or song_query
    webpage_url = entry.get("webpage_url") or entry.get("original_url")
    stream_url = entry.get("url")
    if not webpage_url or not stream_url:
        raise RuntimeError(f"incomplete youtube metadata for {song_query!r}")

    return {"title": title, "webpage_url": webpage_url, "stream_url": stream_url}
