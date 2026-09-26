class PlaylistStore:
    def __init__(self) -> None:
        self._items: dict[str, list[dict[str, str]]] = {}

    def add(self, name: str, title: str, link: str) -> dict[str, list[dict[str, str]]]:
        self._items.setdefault(name, []).append({"title": title, "link": link})
        return self._items

    def as_dict(self) -> dict[str, list[dict[str, str]]]:
        return self._items
