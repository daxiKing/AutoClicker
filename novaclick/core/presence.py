"""Discord Rich Presence over the local Discord IPC socket.

The service is intentionally dependency-free: Discord exposes a length-prefixed
JSON protocol on a local named pipe (Windows) or Unix socket (Linux). AutoClicker
connects as the application's own client ID, publishes what the engines are
doing, and reconnects automatically while Rich Presence is enabled.

Only the public application client ID is stored here. User tokens are never
read, stored or transmitted by this module.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import struct
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

# Public Discord application client ID used for AutoClicker's Rich Presence.
DISCORD_CLIENT_ID = os.environ.get(
    "AUTOCLICKER_DISCORD_CLIENT_ID", "1571907035258167377"
)
GITHUB_URL = "https://github.com/daxiKing/AutoClicker"

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

_MAX_FRAME = 1 << 20
_RECONNECT_SECONDS = 8.0
_HANDSHAKE_SECONDS = 5.0


class PresenceError(RuntimeError):
    """Raised when the Discord IPC transport cannot be used."""


def encode_frame(opcode: int, payload: dict[str, Any]) -> bytes:
    """Serialize one Discord IPC frame (little-endian opcode + length)."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(body) > _MAX_FRAME:
        raise PresenceError("Discord IPC frame is too large")
    return struct.pack("<ii", int(opcode), len(body)) + body


def decode_header(header: bytes) -> tuple[int, int]:
    if len(header) != 8:
        raise PresenceError("Incomplete Discord IPC header")
    opcode, length = struct.unpack("<ii", header)
    if length < 0 or length > _MAX_FRAME:
        raise PresenceError(f"Invalid Discord IPC frame length: {length}")
    return int(opcode), int(length)


def pipe_candidates() -> list[str]:
    """Return likely Discord IPC endpoints for the current platform."""
    if sys.platform.startswith("win"):
        return [rf"\\?\pipe\discord-ipc-{index}" for index in range(10)]

    bases: list[Path] = []
    for raw in (
        os.environ.get("XDG_RUNTIME_DIR"),
        os.environ.get("TMPDIR"),
        "/tmp",
    ):
        if raw:
            path = Path(raw)
            if path not in bases:
                bases.append(path)
    # Flatpak and Snap sandboxes use nested runtime directories.
    for suffix in (
        "app/com.discordapp.Discord",
        "app/com.discordapp.DiscordCanary",
        "snap.discord",
        "snap.discord-canary",
    ):
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime:
            bases.append(Path(runtime) / suffix)
    home = Path.home()
    bases.extend(
        [
            home / ".var/app/com.discordapp.Discord",
            home / ".var/app/com.discordapp.DiscordCanary",
        ]
    )

    endpoints: list[str] = []
    for base in bases:
        for index in range(10):
            candidate = str(base / f"discord-ipc-{index}")
            if candidate not in endpoints:
                endpoints.append(candidate)
    return endpoints


def _loop_main(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


async def _open_stream(path: str, loop: asyncio.AbstractEventLoop):
    """Open one Discord IPC endpoint with the native asyncio transport."""
    if sys.platform.startswith("win"):
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        transport, _ = await loop.create_pipe_connection(lambda: protocol, path)
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        return reader, writer
    return await asyncio.open_unix_connection(path)


class _IPC:
    """A single IPC connection with a background asyncio reader task."""

    def __init__(self, reader, writer, loop, thread: threading.Thread) -> None:
        self._reader = reader
        self._writer = writer
        self._loop = loop
        self._thread = thread
        self._frames: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue()
        self._write_lock = threading.Lock()
        self._closed = threading.Event()
        self._read_task: asyncio.Task | None = None
        loop.call_soon_threadsafe(self._start_reader)

    def _start_reader(self) -> None:
        self._read_task = self._loop.create_task(self._read_loop())

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def send(self, opcode: int, payload: dict[str, Any]) -> bool:
        if self.closed:
            return False
        data = encode_frame(opcode, payload)

        async def _write() -> None:
            self._writer.write(data)
            await self._writer.drain()

        try:
            with self._write_lock:
                asyncio.run_coroutine_threadsafe(_write(), self._loop).result(3.0)
            return True
        except Exception:
            self._closed.set()
            return False

    async def _read_loop(self) -> None:
        try:
            while not self._closed.is_set():
                header = await self._reader.readexactly(8)
                opcode, length = decode_header(header)
                body = await self._reader.readexactly(length) if length else b"{}"
                try:
                    payload = json.loads(body.decode("utf-8"))
                except Exception:
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                self._frames.put((opcode, payload))
        except Exception:
            pass
        finally:
            self._closed.set()

    def recv(self, timeout: float = 1.0) -> tuple[int, dict[str, Any]] | None:
        try:
            return self._frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()

        async def _close() -> None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass

        try:
            asyncio.run_coroutine_threadsafe(_close(), self._loop).result(2.0)
        except Exception:
            pass

    def shutdown(self) -> None:
        self.close()
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except RuntimeError:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)


def _truncate(text: str, limit: int = 128) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_activity(
    state_text: str,
    version: str,
    *,
    active: bool = False,
    session_start: int | None = None,
    repo_url: str = GITHUB_URL,
) -> dict[str, Any]:
    """Build the SET_ACTIVITY payload published to Discord.

    Kept pure so the payload can be tested without a running Discord client.
    """
    state = _truncate(state_text or "SYSTEM READY", 128)
    details = _truncate(
        f"AutoClicker v{version} · {'running' if active else 'ready'}", 128
    )
    activity: dict[str, Any] = {
        "details": details,
        "state": state,
        "timestamps": {"start": int(session_start or time.time())},
        "assets": {
            "large_image": "logo",
            "large_text": f"AutoClicker v{version}",
            "small_image": "status",
            "small_text": "Automation running" if active else "Idle",
        },
        "instance": True,
    }
    if repo_url:
        activity["buttons"] = [{"label": "GitHub repository", "url": repo_url}]
    return activity


def _handshake(
    ipc: _IPC, client_id: str
) -> tuple[bool, str, str]:
    """Perform the IPC handshake; return (ok, username, error)."""
    ipc.send(
        OP_HANDSHAKE,
        {"v": 1, "client_id": str(client_id)},
    )
    deadline = time.monotonic() + _HANDSHAKE_SECONDS
    while time.monotonic() < deadline:
        frame = ipc.recv(max(0.05, deadline - time.monotonic()))
        if frame is None:
            continue
        opcode, payload = frame
        if opcode == OP_PING:
            ipc.send(OP_PONG, payload)
            continue
        if opcode == OP_CLOSE:
            message = str(payload.get("message") or "Discord closed the connection")
            return False, "", message
        event = str(payload.get("evt") or "")
        if event == "READY":
            user = payload.get("data", {}).get("user", {})
            username = str(user.get("username") or "")
            return True, username, ""
        if event == "ERROR":
            message = str(
                payload.get("data", {}).get("message")
                or payload.get("message")
                or "Discord rejected the handshake"
            )
            return False, "", message
    return False, "", "Discord did not answer the handshake"


def connect(client_id: str = DISCORD_CLIENT_ID) -> tuple[_IPC | None, str, str]:
    """Open and handshake the first usable Discord IPC endpoint."""
    errors: list[str] = []
    loop = asyncio.new_event_loop()
    thread = threading.Thread(
        target=_loop_main, args=(loop,), name="discord-ipc-loop", daemon=True
    )
    thread.start()
    for candidate in pipe_candidates():
        try:
            reader, writer = asyncio.run_coroutine_threadsafe(
                _open_stream(candidate, loop), loop
            ).result(3.0)
        except Exception:
            continue
        ipc = _IPC(reader, writer, loop, thread)
        ok, username, error = _handshake(ipc, client_id)
        if ok:
            return ipc, username, ""
        errors.append(error)
        ipc.close()
    try:
        loop.call_soon_threadsafe(loop.stop)
    except RuntimeError:
        pass
    if thread.is_alive():
        thread.join(timeout=2.0)
    return None, "", errors[-1] if errors else "Discord desktop app is not running"


class PresenceService:
    """Background Rich Presence publisher with automatic reconnects."""

    def __init__(self, client_id: str = DISCORD_CLIENT_ID, version: str = "") -> None:
        self.client_id = str(client_id)
        self.version = str(version)
        self._lock = threading.RLock()
        self._enabled = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ipc: _IPC | None = None
        self._status = "Rich Presence off"
        self._state_text = "SYSTEM READY"
        self._active = False
        self._session_start = int(time.time())
        self._last_signature: tuple[str, bool] | None = None
        self._username = ""

    # -- lifecycle ---------------------------------------------------------
    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._ipc is not None and not self._ipc.closed

    def status_text(self) -> str:
        with self._lock:
            return self._status

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._enabled = True
                return
            self._enabled = True
            self._stop.clear()
            self._last_signature = None
            self._set_status_locked("Looking for the Discord desktop app…")
            self._thread = threading.Thread(
                target=self._run, name="discord-presence", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._enabled = False
            self._stop.set()
            ipc, self._ipc = self._ipc, None
            self._set_status_locked("Rich Presence off")
        if ipc is not None:
            ipc.shutdown()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.2)
        with self._lock:
            self._thread = None
            self._last_signature = None

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.start()
        else:
            self.stop()

    # -- activity ----------------------------------------------------------
    def set_state(self, text: str, active: bool = False) -> None:
        """Publish a new engine state; ignored when Presence is stopped."""
        with self._lock:
            changed = (text, bool(active)) != (self._state_text, self._active)
            self._state_text = text or "SYSTEM READY"
            self._active = bool(active)
            ipc = self._ipc
            enabled = self._enabled
            if not changed or not enabled or ipc is None:
                return
            self._last_signature = (self._state_text, self._active)
        self._publish(ipc)

    def _activity(self) -> dict[str, Any]:
        return build_activity(
            self._state_text,
            self.version or "2.5.0",
            active=self._active,
            session_start=self._session_start,
        )

    def _publish(self, ipc: _IPC) -> None:
        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {"pid": os.getpid(), "activity": self._activity()},
            "nonce": str(uuid.uuid4()),
        }
        if not ipc.send(OP_FRAME, payload):
            self._set_status("Discord connection lost — reconnecting…")

    def _set_status(self, text: str) -> None:
        with self._lock:
            self._set_status_locked(text)

    def _set_status_locked(self, text: str) -> None:
        self._status = text

    # -- worker ------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ipc, username, error = connect(self.client_id)
            except Exception as exc:  # defensive: never kill the app
                ipc, username, error = None, "", str(exc)
            if ipc is None:
                self._set_status(f"Waiting for Discord — {error}")
                if self._stop.wait(_RECONNECT_SECONDS):
                    break
                continue

            with self._lock:
                self._ipc = ipc
                self._username = username
                self._last_signature = (self._state_text, self._active)
                self._set_status_locked(
                    f"Connected as {username}" if username else "Connected to Discord"
                )
            self._publish(ipc)

            while not self._stop.is_set():
                frame = ipc.recv(1.0)
                if frame is None:
                    if ipc.closed:
                        break
                    continue
                opcode, payload = frame
                if opcode == OP_PING:
                    ipc.send(OP_PONG, payload)
                elif opcode == OP_CLOSE:
                    break
                elif opcode == OP_FRAME:
                    event = str(payload.get("evt") or "")
                    if event == "ERROR":
                        message = str(
                            payload.get("data", {}).get("message")
                            or "Discord reported an activity error"
                        )
                        self._set_status(f"Discord: {message}")
                # Ignore normal SET_ACTIVITY responses.

            with self._lock:
                if self._ipc is ipc:
                    self._ipc = None
            ipc.shutdown()
            if self._stop.is_set():
                break
            self._set_status("Discord connection closed — reconnecting…")
            if self._stop.wait(2.0):
                break

        with self._lock:
            self._ipc = None
            if not self._enabled:
                self._set_status_locked("Rich Presence off")


__all__ = [
    "DISCORD_CLIENT_ID",
    "GITHUB_URL",
    "PresenceError",
    "PresenceService",
    "build_activity",
    "connect",
    "decode_header",
    "encode_frame",
    "pipe_candidates",
]
