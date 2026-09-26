import json
import os
import socket
import subprocess

from jarvis.config import (
    MPV_IPC_PATH,
    MUSIC_VOLUME_DUCKED,
    MUSIC_VOLUME_NORMAL,
)
from jarvis.log import log


class Player:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def play(self, url: str) -> None:
        self.stop()
        self._proc = subprocess.Popen(
            [
                "mpv",
                "--no-video",
                "--no-terminal",
                "--really-quiet",
                f"--volume={MUSIC_VOLUME_NORMAL}",
                f"--input-ipc-server={MPV_IPC_PATH}",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        log("playback started")

    def stop(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
        try:
            os.remove(MPV_IPC_PATH)
        except OSError:
            pass

    def pause(self) -> bool:
        ok = self._command(["set_property", "pause", True])
        if ok:
            log("paused")
        return ok

    def resume(self) -> bool:
        ok = self._command(["set_property", "pause", False])
        if ok:
            log("resumed")
        return ok

    def seek(self, seconds: int) -> bool:
        ok = self._command(["seek", seconds, "relative"])
        if ok:
            log(f"seek {seconds}s")
        return ok

    def duck(self) -> None:
        if not self.is_playing():
            return
        self._command(["set_property", "volume", MUSIC_VOLUME_DUCKED])

    def restore_volume(self) -> None:
        if not self.is_playing():
            return
        self._command(["set_property", "volume", MUSIC_VOLUME_NORMAL])

    def _command(self, command: list) -> bool:
        if not self.is_playing() or not os.path.exists(MPV_IPC_PATH):
            return False
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.4)
            sock.connect(MPV_IPC_PATH)
            sock.sendall((json.dumps({"command": command}) + "\n").encode("utf-8"))
            sock.close()
            return True
        except OSError as exc:
            log(f"player ipc failed: {exc}")
            return False
