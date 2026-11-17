"""Macro recording, playback, storage and formatting helpers."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import wininput
from .keys import is_extended, pynput_key_to_vk, vk_name
from .paths import MACRO_DIR

HOTKEY_VKS = {0x75, 0x76, 0x77, 0x78, 0x79}
VALID_EVENT_TYPES = {"move", "down", "up", "scroll", "keydown", "keyup"}
VALID_BUTTONS = {"left", "right", "middle"}


def format_duration(ms: float) -> str:
    ms = max(0.0, float(ms))
    seconds = ms / 1000.0
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    if minutes < 60:
        return f"{minutes}m {rest:04.1f}s"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h {minutes:02d}m"


def format_clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _event_counts(events: list[dict]) -> dict[str, int]:
    counts = {"moves": 0, "clicks": 0, "keys": 0, "scrolls": 0}
    for event in events:
        kind = event.get("type")
        if kind == "move":
            counts["moves"] += 1
        elif kind in ("down", "up"):
            counts["clicks"] += 1
        elif kind in ("keydown", "keyup"):
            counts["keys"] += 1
        elif kind == "scroll":
            counts["scrolls"] += 1
    return counts


class MacroStore:
    """JSON-backed macro library stored beside the app."""

    def __init__(self, folder: Path = MACRO_DIR) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._macros: dict[str, dict] = {}
        self.load_errors: list[str] = []

    @staticmethod
    def _validate(macro: dict) -> dict:
        if not isinstance(macro, dict):
            raise ValueError("Macro file is not an object.")
        events = macro.get("events")
        if not isinstance(events, list):
            raise ValueError("Macro has no event list.")
        clean_events: list[dict] = []
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                raise ValueError(f"Event {index} is invalid.")
            kind = event.get("type")
            if kind not in VALID_EVENT_TYPES:
                raise ValueError(f"Event {index} has unknown type.")
            try:
                when = float(event.get("t", 0))
            except (TypeError, ValueError):
                raise ValueError(f"Event {index} has an invalid time.") from None
            cleaned = {"t": round(max(0.0, when), 2), "type": kind}
            if kind in ("move", "down", "up", "scroll"):
                cleaned["x"] = int(event.get("x", 0))
                cleaned["y"] = int(event.get("y", 0))
            if kind in ("down", "up"):
                button = str(event.get("button", "left")).lower()
                cleaned["button"] = button if button in VALID_BUTTONS else "left"
            if kind == "scroll":
                cleaned["dx"] = int(event.get("dx", 0))
                cleaned["dy"] = int(event.get("dy", 0))
            if kind in ("keydown", "keyup"):
                vk = int(event.get("vk", 0))
                if not 0 < vk <= 0xFE:
                    continue
                cleaned["vk"] = vk
                cleaned["name"] = vk_name(vk)
            clean_events.append(cleaned)

        clean_events.sort(key=lambda item: item["t"])
        duration = float(macro.get("duration", 0.0))
        if clean_events:
            duration = max(duration, float(clean_events[-1]["t"]))
        macro_id = str(macro.get("id") or uuid.uuid4().hex)
        return {
            "id": macro_id,
            "name": str(macro.get("name") or "Untitled macro")[:80],
            "created": str(macro.get("created") or datetime.now().isoformat(timespec="seconds")),
            "duration": round(duration, 2),
            "events": clean_events,
        }

    def load(self) -> None:
        self._macros.clear()
        self.load_errors.clear()
        for path in sorted(self.folder.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    macro = self._validate(json.load(handle))
                self._macros[macro["id"]] = macro
            except Exception as exc:
                self.load_errors.append(f"{path.name}: {exc}")

    def all(self) -> list[dict]:
        return sorted(self._macros.values(), key=lambda item: item.get("created", ""), reverse=True)

    def get(self, macro_id: str) -> dict | None:
        return self._macros.get(macro_id)

    def save(self, macro: dict) -> dict:
        macro = self._validate(macro)
        path = self.folder / f"{macro['id']}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(macro, handle, ensure_ascii=False, indent=2)
        self._macros[macro["id"]] = macro
        return macro

    def create(self, name: str, events: list[dict], duration: float) -> dict:
        macro = {
            "id": uuid.uuid4().hex,
            "name": name,
            "created": datetime.now().isoformat(timespec="seconds"),
            "duration": duration,
            "events": events,
        }
        return self.save(macro)

    def next_name(self) -> str:
        used = {macro["name"] for macro in self._macros.values()}
        index = 1
        while f"Macro {index:02d}" in used:
            index += 1
        return f"Macro {index:02d}"

    def rename(self, macro_id: str, name: str) -> dict | None:
        macro = self._macros.get(macro_id)
        if not macro:
            return None
        macro = dict(macro)
        macro["name"] = name.strip()[:80] or macro["name"]
        return self.save(macro)

    def delete(self, macro_id: str) -> bool:
        self._macros.pop(macro_id, None)
        path = self.folder / f"{macro_id}.json"
        try:
            if path.exists():
                path.unlink()
            return True
        except OSError:
            return False

    def export(self, macro: dict, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8") as handle:
            json.dump(self._validate(macro), handle, ensure_ascii=False, indent=2)

    def import_file(self, path: str | Path) -> dict:
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            raise ValueError("Multi-macro files are not supported yet.")
        macro = self._validate(payload)
        macro["id"] = uuid.uuid4().hex
        macro["name"] = macro["name"][:70] + " (imported)"
        return self.save(macro)


class MacroRecorder:
    """Global mouse & keyboard recorder with no duration limit."""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self._active = False
        self._t0 = 0.0
        self._last_move_t = -999.0
        self._last_move_pos: tuple[int, int] | None = None
        self._held_keys: set[int] = set()
        self._mouse_listener = None
        self._key_listener = None
        self._started_at = 0.0
        self.error: str | None = None

    @property
    def is_active(self) -> bool:
        return self._active

    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    def elapsed(self) -> float:
        if not self._started_at:
            return 0.0
        return time.perf_counter() - self._started_at

    @staticmethod
    def _now(t0: float) -> float:
        return round((time.perf_counter() - t0) * 1000.0, 2)

    def _add(self, event: dict) -> None:
        with self._lock:
            self._events.append(event)

    def start(self) -> bool:
        if self._active:
            return False
        self._events = []
        self._held_keys.clear()
        self._last_move_t = -999.0
        self._last_move_pos = None
        self.error = None
        try:
            from pynput import keyboard, mouse

            self._mouse_listener = mouse.Listener(
                on_move=self._on_move,
                on_click=self._on_click,
                on_scroll=self._on_scroll,
            )
            self._key_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._mouse_listener.daemon = True
            self._key_listener.daemon = True
            self._mouse_listener.start()
            self._key_listener.start()
        except Exception as exc:
            self.error = str(exc)
            self._stop_listeners()
            return False

        self._t0 = time.perf_counter()
        self._started_at = self._t0
        self._active = True
        return True

    def stop(self) -> dict | None:
        if not self._active:
            return None
        self._active = False
        self._stop_listeners()
        with self._lock:
            events = list(self._events)
        if not events:
            return None
        events.sort(key=lambda item: item["t"])
        duration = events[-1]["t"]
        return {
            "events": events,
            "duration": duration,
            "counts": _event_counts(events),
        }

    def _stop_listeners(self) -> None:
        for listener in (self._mouse_listener, self._key_listener):
            if listener:
                try:
                    listener.stop()
                except Exception:
                    pass
        self._mouse_listener = None
        self._key_listener = None

    # -- listener callbacks -------------------------------------------------
    def _on_move(self, x, y) -> None:
        if not self._active:
            return
        now = self._now(self._t0)
        pos = (int(x), int(y))
        if now - self._last_move_t < 10.0:
            return
        if self._last_move_pos == pos:
            return
        self._last_move_t = now
        self._last_move_pos = pos
        self._add({"t": now, "type": "move", "x": pos[0], "y": pos[1]})

    def _on_click(self, x, y, button, pressed) -> None:
        if not self._active:
            return
        name = getattr(button, "name", "left")
        self._add({
            "t": self._now(self._t0),
            "type": "down" if pressed else "up",
            "x": int(x),
            "y": int(y),
            "button": name if name in VALID_BUTTONS else "left",
        })

    def _on_scroll(self, x, y, dx, dy) -> None:
        if not self._active:
            return
        self._add({
            "t": self._now(self._t0),
            "type": "scroll",
            "x": int(x),
            "y": int(y),
            "dx": int(dx),
            "dy": int(dy),
        })

    def _on_key_press(self, key) -> None:
        if not self._active:
            return
        vk = pynput_key_to_vk(key)
        if not vk or vk in HOTKEY_VKS or vk in self._held_keys:
            return
        self._held_keys.add(vk)
        self._add({"t": self._now(self._t0), "type": "keydown", "vk": vk, "name": vk_name(vk)})

    def _on_key_release(self, key) -> None:
        if not self._active:
            return
        vk = pynput_key_to_vk(key)
        if not vk or vk in HOTKEY_VKS:
            return
        self._held_keys.discard(vk)
        self._add({"t": self._now(self._t0), "type": "keyup", "vk": vk, "name": vk_name(vk)})


class MacroPlayer:
    """Replay a recorded macro with speed control and optional infinite looping."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._active = False
        self._error: str | None = None
        self._loop = 0
        self._loops_total: int | None = 1
        self._event_index = 0
        self._event_total = 0
        self._started_at = 0.0
        self.error_callback: Callable[[str], None] | None = None
        self.finished_callback: Callable[[bool], None] | None = None

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active": self._active,
                "loop": self._loop,
                "loops_total": self._loops_total,
                "event_index": self._event_index,
                "event_total": self._event_total,
                "elapsed": time.perf_counter() - self._started_at if self._started_at else 0.0,
                "error": self._error,
            }

    def start(self, macro: dict, speed: float = 1.0, loops: int | None = 1) -> bool:
        events = macro.get("events", [])
        if not events:
            return False
        with self._lock:
            if self._active:
                return False
            self._active = True
            self._loop = 0
            self._loops_total = loops
            self._event_index = 0
            self._event_total = len(events)
            self._error = None
            self._started_at = time.perf_counter()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_guarded,
            args=(list(events), max(0.1, speed), loops),
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, wait: float = 0.4) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=wait)

    def _run_guarded(self, events: list[dict], speed: float, loops: int | None) -> None:
        finished = False
        try:
            self._run(events, speed, loops)
            finished = not self._stop.is_set()
        except Exception as exc:  # pragma: no cover - defensive
            self._error = f"Playback fault: {exc}"
            if self.error_callback:
                try:
                    self.error_callback(self._error)
                except Exception:
                    pass
        finally:
            with self._lock:
                self._active = False
            self._stop.set()
            if self.finished_callback:
                try:
                    self.finished_callback(finished)
                except Exception:
                    pass

    def _run(self, events: list[dict], speed: float, loops: int | None) -> None:
        pressed_keys: set[int] = set()
        pressed_buttons: set[str] = set()
        last_pos: tuple[int, int] | None = None
        loop_index = 0
        try:
            while not self._stop.is_set():
                loop_index += 1
                with self._lock:
                    self._loop = loop_index
                    self._started_at = time.perf_counter()
                base = time.perf_counter()
                for index, event in enumerate(events):
                    target = base + max(0.0, float(event.get("t", 0))) / 1000.0 / speed
                    while True:
                        if self._stop.is_set():
                            return
                        remaining = target - time.perf_counter()
                        if remaining <= 0:
                            break
                        if remaining > 0.0015:
                            if self._stop.wait(min(remaining - 0.0007, 0.05)):
                                return
                        else:
                            time.sleep(0)
                    if self._stop.is_set():
                        return
                    self._apply(event, last_pos, pressed_keys, pressed_buttons)
                    with self._lock:
                        self._event_index = index + 1
                    last_pos = self._last_pos(event, last_pos)
                if loops is not None and loop_index >= max(1, loops):
                    return
                if self._stop.wait(0.08):
                    return
        finally:
            for vk in list(pressed_keys):
                wininput.key_up(vk)
            for button in list(pressed_buttons):
                wininput.mouse_up(button)

    def _last_pos(self, event: dict, last_pos: tuple[int, int] | None) -> tuple[int, int] | None:
        if "x" in event and "y" in event:
            return int(event["x"]), int(event["y"])
        return last_pos

    def _apply(
        self,
        event: dict,
        last_pos: tuple[int, int] | None,
        pressed_keys: set[int],
        pressed_buttons: set[str],
    ) -> None:
        kind = event.get("type")
        if "x" in event and "y" in event:
            x, y = int(event["x"]), int(event["y"])
            should_move = kind == "move" or last_pos is None or abs(last_pos[0] - x) > 0 or abs(last_pos[1] - y) > 0
            if should_move:
                wininput.move_to(x, y)

        if kind == "down":
            wininput.mouse_down(event.get("button", "left"))
            pressed_buttons.add(event.get("button", "left"))
        elif kind == "up":
            wininput.mouse_up(event.get("button", "left"))
            pressed_buttons.discard(event.get("button", "left"))
        elif kind == "scroll":
            dx = int(event.get("dx", 0))
            dy = int(event.get("dy", 0))
            if dy:
                wininput.scroll(dy * 120)
            if dx:
                wininput.scroll(dx * 120, horizontal=True)
        elif kind == "keydown":
            vk = int(event.get("vk", 0))
            if vk:
                wininput.key_down(vk)
                pressed_keys.add(vk)
        elif kind == "keyup":
            vk = int(event.get("vk", 0))
            if vk:
                wininput.key_up(vk)
                pressed_keys.discard(vk)


def macro_summary(macro: dict) -> str:
    counts = _event_counts(macro.get("events", []))
    date = str(macro.get("created", ""))[:10]
    return (
        f"{format_duration(macro.get('duration', 0))}  ·  "
        f"{len(macro.get('events', [])):,} events  ·  {date}"
    )


def event_breakdown(macro: dict) -> dict[str, int]:
    return _event_counts(macro.get("events", []))


__all__ = [
    "MacroStore",
    "MacroRecorder",
    "MacroPlayer",
    "macro_summary",
    "event_breakdown",
    "format_duration",
    "format_clock",
    "is_extended",
]
