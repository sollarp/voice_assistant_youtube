import json
import os
import socket
import subprocess
import time

from jarvis.config import MPV_IPC_PATH
from jarvis.log import log


class MPVController:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._started = False
        self._busy_until = 0.0

    def ensure(self) -> None:
        if self._alive():
            return
        if os.path.exists(MPV_IPC_PATH):
            try:
                os.remove(MPV_IPC_PATH)
            except OSError:
                pass
        self._proc = subprocess.Popen(
            [
                "mpv",
                "--no-video",
                "--idle",
                "--really-quiet",
                "--audio-exclusive=no",
                f"--input-ipc-server={MPV_IPC_PATH}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._started = True
        for _ in range(40):
            if self._alive():
                log("mpv ready")
                return
            time.sleep(0.05)
        raise RuntimeError("mpv ipc socket did not open")

    def play(self, url: str) -> bool:
        self.ensure()
        ok = self._command(["loadfile", url, "replace"])
        if ok:
            self._busy_until = time.monotonic() + 20
        return ok

    def pause(self) -> bool:
        self.ensure()
        ok = self._command(["set_property", "pause", True])
        if ok:
            log("paused")
        return ok

    def resume(self) -> bool:
        self.ensure()
        ok = self._command(["set_property", "pause", False])
        if ok:
            log("resumed")
        return ok

    def stop(self) -> bool:
        self._busy_until = 0.0
        if not self._alive():
            return False
        ok = self._command(["stop"])
        if ok:
            log("stopped")
        return ok

    def set_volume(self, level: int) -> bool:
        try:
            self.ensure()
        except Exception as exc:
            log(f"mpv unavailable: {exc}")
            return False
        return self._command(["set_property", "volume", int(level)])

    def close(self) -> None:
        if not self._started:
            return
        if self._alive():
            self._command(["quit"])
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)

    def _alive(self) -> bool:
        if not os.path.exists(MPV_IPC_PATH):
            return False
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.2)
            sock.connect(MPV_IPC_PATH)
            sock.close()
            return True
        except OSError:
            return False

    def has_media(self) -> bool:
        if not os.path.exists(MPV_IPC_PATH):
            return False
        payload = self._request(["get_property", "idle-active"])
        if not payload or payload.get("error") != "success":
            return False
        return payload.get("data") is False

    def making_sound(self) -> bool:
        if time.monotonic() < self._busy_until:
            return True
        if not self.has_media():
            return False
        payload = self._request(["get_property", "pause"])
        if not payload or payload.get("error") != "success":
            return True
        return payload.get("data") is not True

    def _command(self, command: list) -> bool:
        payload = self._request(command)
        if payload and payload.get("error") == "success":
            return True
        if payload:
            log(f"mpv command failed: {payload.get('error')}")
        else:
            log(f"mpv ipc failed: {command[0]}")
        return False

    def _request(self, command: list) -> dict | None:
        if not os.path.exists(MPV_IPC_PATH):
            return None
        for _ in range(3):
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(0.4)
                sock.connect(MPV_IPC_PATH)
                sock.sendall((json.dumps({"command": command}) + "\n").encode())
                raw = b""
                while b"\n" not in raw:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
                sock.close()
                if not raw:
                    return None
                payload = json.loads(raw.decode().split("\n", 1)[0])
                return payload if isinstance(payload, dict) else None
            except (OSError, json.JSONDecodeError):
                time.sleep(0.1)
        return None
