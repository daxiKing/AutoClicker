"""High-throughput click and auto-key engines."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable

from . import wininput
from .hotkeys import Binding, DEFAULT_BINDINGS, modifier_for_vk
from .keys import current_modifiers, is_extended


@dataclass(frozen=True)
class ClickConfig:
    cps: float = 100.0
    uncapped: bool = False
    button: str = "left"
    click_type: str = "single"  # single | double | hold
    hold_ms: int = 80
    x: int | None = None
    y: int | None = None
    jitter_px: int = 0
    chaos_pct: int = 0
    start_delay: float = 0.0
    stop_after_clicks: int = 0   # 0 = disabled
    stop_after_seconds: float = 0.0  # 0 = disabled
    click_sound: bool = False
    target_window: str = ""      # empty = any window


@dataclass(frozen=True)
class KeyConfig:
    vk: int = 0x20
    key_name: str = "Space"
    rate: float = 20.0
    hold_ms: int = 0
    start_delay: float = 0.0
    stop_after_presses: int = 0   # 0 = disabled
    stop_after_seconds: float = 0.0  # 0 = disabled


def _wait_until(stop: threading.Event, deadline: float) -> bool:
    """Sleep until a monotonic deadline. Returns False if stopped."""
    while True:
        if stop.is_set():
            return False
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return True
        if remaining > 0.0015:
            if stop.wait(min(remaining - 0.0007, 0.05)):
                return False
        else:
            # A very short yield is more accurate than sleeping on Windows.
            time.sleep(0)


class _AutomationBase:
    label = "engine"

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._count = 0
        self._started_at = 0.0
        self._active = False
        self._error: str | None = None
        self._on_error: Callable[[str], None] | None = None

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def set_error_callback(self, callback: Callable[[str], None] | None) -> None:
        self._on_error = callback

    def snapshot(self) -> dict:
        with self._lock:
            elapsed = (time.perf_counter() - self._started_at) if self._started_at else 0.0
            return {
                "active": self._active,
                "count": self._count,
                "elapsed": elapsed,
                "error": self._error,
            }

    def _publish(self, count: int | None = None, active: bool | None = None) -> None:
        with self._lock:
            if count is not None:
                self._count = count
            if active is not None:
                self._active = active

    def _fail(self, message: str, callback_enabled: bool = True) -> None:
        with self._lock:
            self._error = message
        if callback_enabled and self._on_error:
            try:
                self._on_error(message)
            except Exception:
                pass

    def stop(self, wait: float = 0.35) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=wait)

    def _launch(self) -> bool:
        with self._lock:
            if self._active:
                return False
            self._count = 0
            self._started_at = 0.0
            self._error = None
            self._active = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_guarded, daemon=True)
        self._thread.start()
        return True

    def _run_guarded(self) -> None:
        try:
            self._run()
        except Exception as exc:  # pragma: no cover - defensive
            self._fail(f"{self.label} fault: {exc}")
        finally:
            with self._lock:
                self._active = False
            self._stop.set()


class AutoClicker(_AutomationBase):
    label = "Click engine"

    def __init__(self) -> None:
        super().__init__()
        self._config = ClickConfig()

    def start(self, config: ClickConfig) -> bool:
        self._config = replace(config)
        return self._launch()

    def _run(self) -> None:
        cfg = self._config
        if cfg.start_delay > 0 and self._stop.wait(cfg.start_delay):
            return

        self._publish(active=True)
        with self._lock:
            self._started_at = time.perf_counter()

        interval = 1.0 / max(cfg.cps, 0.1)
        next_due = time.perf_counter()
        count = 0
        last_publish = next_due
        deadline = (
            time.perf_counter() + cfg.stop_after_seconds
            if cfg.stop_after_seconds > 0
            else None
        )

        while not self._stop.is_set():
            now = time.perf_counter()
            if cfg.stop_after_clicks > 0 and count >= cfg.stop_after_clicks:
                break
            if deadline is not None and now >= deadline:
                break
            if not cfg.uncapped:
                if now < next_due:
                    if not _wait_until(self._stop, next_due):
                        break
                    continue

            self._click_once(cfg)
            count += 1

            if cfg.uncapped:
                # Keep the UI thread responsive without meaningfully slowing input.
                if count % 64 == 0:
                    time.sleep(0)
            else:
                step = interval
                if cfg.chaos_pct > 0:
                    spread = min(cfg.chaos_pct, 95) / 100.0
                    step *= random.uniform(1.0 - spread, 1.0 + spread)
                next_due += step
                if next_due < now - max(0.25, step * 60):
                    next_due = now + step

            now = time.perf_counter()
            if now - last_publish >= 0.02:
                self._publish(count=count)
                last_publish = now

        self._publish(count=count)

    def _click_once(self, cfg: ClickConfig) -> None:
        if cfg.target_window:
            title = wininput.get_foreground_title()
            if cfg.target_window.lower() not in title.lower():
                return
        if cfg.click_sound:
            wininput.beep(800, 8)

        x = y = None
        if cfg.x is not None and cfg.y is not None:
            x, y = cfg.x, cfg.y
            if cfg.jitter_px > 0:
                x += random.randint(-cfg.jitter_px, cfg.jitter_px)
                y += random.randint(-cfg.jitter_px, cfg.jitter_px)

        if cfg.click_type == "hold":
            if x is not None and y is not None:
                wininput.move_to(x, y)
            if not wininput.mouse_down(cfg.button):
                return
            try:
                self._stop.wait(max(1, cfg.hold_ms) / 1000.0)
            finally:
                wininput.mouse_up(cfg.button)
        else:
            wininput.click(
                button=cfg.button,
                x=x,
                y=y,
                double=cfg.click_type == "double",
            )


class AutoKey(_AutomationBase):
    label = "Auto-key engine"

    def __init__(self) -> None:
        super().__init__()
        self._config = KeyConfig()

    def start(self, config: KeyConfig) -> bool:
        if not config.vk:
            return False
        self._config = replace(config)
        return self._launch()

    def _run(self) -> None:
        cfg = self._config
        if cfg.start_delay > 0 and self._stop.wait(cfg.start_delay):
            return

        self._publish(active=True)
        with self._lock:
            self._started_at = time.perf_counter()

        interval = 1.0 / max(cfg.rate, 0.1)
        next_due = time.perf_counter()
        count = 0
        last_publish = next_due
        deadline = (
            time.perf_counter() + cfg.stop_after_seconds
            if cfg.stop_after_seconds > 0
            else None
        )

        while not self._stop.is_set():
            now = time.perf_counter()
            if cfg.stop_after_presses > 0 and count >= cfg.stop_after_presses:
                break
            if deadline is not None and now >= deadline:
                break
            if now < next_due:
                if not _wait_until(self._stop, next_due):
                    break
                continue

            if cfg.hold_ms > 0:
                wininput.key_down(cfg.vk)
                try:
                    self._stop.wait(cfg.hold_ms / 1000.0)
                finally:
                    wininput.key_up(cfg.vk)
            else:
                wininput.key_tap(cfg.vk)

            count += 1
            next_due += interval
            if next_due < now - max(0.25, interval * 60):
                next_due = now + interval

            now = time.perf_counter()
            if now - last_publish >= 0.02:
                self._publish(count=count)
                last_publish = now

        # Defensive cleanup in case the loop is interrupted mid-hold.
        wininput.key_up(cfg.vk)
        self._publish(count=count)


class HotkeyManager:
    """Global shortcut listener that never swallows keystrokes.

    Bindings can be remapped live; matching is exact on both the virtual key
    and the held modifier set. The listener itself is intentionally 1:1 with
    ``pynput`` so synthetic input from the engines is ignored by the OS.
    """

    DEFAULT_MAP = {
        "clicker": 0x75,   # F6
        "autokey": 0x76,   # F7
        "record": 0x77,    # F8
        "play": 0x78,      # F9
        "panic": 0x79,     # F10
    }

    def __init__(
        self,
        dispatch: Callable[[str], None],
        bindings: dict[str, Binding] | None = None,
    ) -> None:
        self._dispatch = dispatch
        self._listener = None
        self._pressed: set[int] = set()
        self._suspended = False
        self._lock = threading.RLock()
        self._bindings: dict[str, Binding] = dict(bindings or DEFAULT_BINDINGS)
        self._actions: dict[tuple[frozenset[str], int], str] = {}
        self._rebuild_lookup()
        self.error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._listener is not None

    @property
    def bindings(self) -> dict[str, Binding]:
        with self._lock:
            return dict(self._bindings)

    def _rebuild_lookup(self) -> None:
        self._actions = {
            (binding.mods, int(binding.vk)): action
            for action, binding in self._bindings.items()
            if binding.vk != 0
        }

    def set_bindings(self, bindings: dict[str, Binding]) -> None:
        """Swap the live key map without restarting the listener."""
        clean = {
            str(action): binding
            for action, binding in bindings.items()
            if isinstance(binding, Binding)
        }
        with self._lock:
            self._bindings = clean
            self._rebuild_lookup()
            self._pressed.clear()

    def start(self) -> bool:
        try:
            from pynput import keyboard

            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._listener.daemon = True
            self._listener.start()
            self.error = None
            return True
        except Exception as exc:
            self.error = str(exc)
            self._listener = None
            return False

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        if listener:
            try:
                listener.stop()
            except Exception:
                pass

    def set_suspended(self, suspended: bool) -> None:
        self._suspended = suspended
        if suspended:
            self._pressed.clear()

    def _on_press(self, key) -> None:
        from .keys import pynput_key_to_vk

        vk = pynput_key_to_vk(key)
        if vk is None or self._suspended:
            return
        if modifier_for_vk(vk) is not None:
            return
        mods = current_modifiers()
        with self._lock:
            action = self._actions.get((mods, vk))
        if action and vk not in self._pressed:
            self._pressed.add(vk)
            try:
                self._dispatch(action)
            except Exception:
                pass

    def _on_release(self, key) -> None:
        from .keys import pynput_key_to_vk

        vk = pynput_key_to_vk(key)
        if vk is not None:
            self._pressed.discard(vk)
