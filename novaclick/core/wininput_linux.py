"""Linux input backend built on pynput (X11, with Wayland limitations).

pynput talks to the X server; on a Wayland session it can work through
XWayland for X11 clients, but synthetic input may be restricted by the
compositor. Every function is defensive: callers get False or an empty result
instead of an exception when the display server refuses input.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time

try:
    from pynput import keyboard as _keyboard
    from pynput import mouse as _mouse
except Exception:  # pragma: no cover - headless environments
    _keyboard = None
    _mouse = None

_SCAN_CODE_MODE = False
_INPUT_LOCK = threading.RLock()
_MOUSE = None
_KEYBOARD = None
_VK_MAP: dict[int, object] | None = None
_BUTTONS: dict[str, object] | None = None


def _mouse_controller():
    global _MOUSE
    if _mouse is None:
        return None
    if _MOUSE is None:
        try:
            _MOUSE = _mouse.Controller()
        except Exception:
            return None
    return _MOUSE


def _key_controller():
    global _KEYBOARD
    if _keyboard is None:
        return None
    if _KEYBOARD is None:
        try:
            _KEYBOARD = _keyboard.Controller()
        except Exception:
            return None
    return _KEYBOARD


def _char_key(char: str):
    if _keyboard is None:
        return None
    try:
        return _keyboard.KeyCode.from_char(char)
    except Exception:
        return None


def _build_maps() -> tuple[dict[int, object], dict[str, object]]:
    global _VK_MAP, _BUTTONS
    if _VK_MAP is not None and _BUTTONS is not None:
        return _VK_MAP, _BUTTONS
    mapping: dict[int, object] = {}
    buttons: dict[str, object] = {}
    if _keyboard is None:
        _VK_MAP, _BUTTONS = mapping, buttons
        return mapping, buttons

    Key = _keyboard.Key
    named = {
        0x08: "backspace",
        0x09: "tab",
        0x0D: "enter",
        0x10: "shift",
        0x11: "ctrl",
        0x12: "alt",
        0x13: "pause",
        0x14: "caps_lock",
        0x1B: "esc",
        0x20: "space",
        0x21: "page_up",
        0x22: "page_down",
        0x23: "end",
        0x24: "home",
        0x25: "left",
        0x26: "up",
        0x27: "right",
        0x28: "down",
        0x2C: "print_screen",
        0x2D: "insert",
        0x2E: "delete",
        0x5B: "cmd",
        0x5C: "cmd_r",
        0x5D: "menu",
        0x6A: "multiply",
        0x6B: "add",
        0x6D: "subtract",
        0x6E: "decimal",
        0x6F: "divide",
        0x90: "num_lock",
        0x91: "scroll_lock",
        0xA0: "shift_l",
        0xA1: "shift_r",
        0xA2: "ctrl_l",
        0xA3: "ctrl_r",
        0xA4: "alt_l",
        0xA5: "alt_gr",
    }
    for vk, name in named.items():
        key = getattr(Key, name, None)
        if key is not None:
            mapping[vk] = key
    for number in range(1, 25):
        key = getattr(Key, f"f{number}", None)
        if key is not None:
            mapping[0x6F + number] = key
    for digit in range(10):
        key = _char_key(str(digit))
        if key is not None:
            mapping[0x30 + digit] = key
            mapping[0x60 + digit] = key
    for code in range(0x41, 0x5B):
        key = _char_key(chr(code).lower())
        if key is not None:
            mapping[code] = key
    punctuation = {
        0xBA: ";",
        0xBB: "=",
        0xBC: ",",
        0xBD: "-",
        0xBE: ".",
        0xBF: "/",
        0xC0: "`",
        0xDB: "[",
        0xDC: "\\",
        0xDD: "]",
        0xDE: "'",
    }
    for vk, char in punctuation.items():
        key = _char_key(char)
        if key is not None:
            mapping[vk] = key

    if _mouse is not None:
        Button = _mouse.Button
        for name in ("left", "right", "middle"):
            button = getattr(Button, name, None)
            if button is not None:
                buttons[name] = button
        for name in ("x1", "x2"):
            button = getattr(Button, name, None)
            if button is not None:
                buttons[name] = button
    _VK_MAP, _BUTTONS = mapping, buttons
    return mapping, buttons


def _key_for_vk(vk: int):
    mapping, _ = _build_maps()
    return mapping.get(int(vk))


def _button_for(name: str):
    _, buttons = _build_maps()
    return buttons.get(str(name).lower(), buttons.get("left"))


# ---------------------------------------------------------------------------
# Lifecycle and platform capabilities
# ---------------------------------------------------------------------------

def set_scan_code_mode(enabled: bool) -> bool:
    """Scan-code injection is Windows-only; report it as unavailable."""
    return False


def scan_code_mode() -> bool:
    return False


def set_high_priority(enabled: bool) -> bool:
    """No process-priority tweak is needed on Linux."""
    return False


def is_admin() -> bool:
    try:
        return bool(os.geteuid() == 0)
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    return False


def enable_dpi_awareness() -> None:
    return None


def begin_timer_resolution() -> None:
    return None


def end_timer_resolution() -> None:
    return None


# ---------------------------------------------------------------------------
# Pointer
# ---------------------------------------------------------------------------

def virtual_screen_rect() -> tuple[int, int, int, int]:
    try:
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            return (
                int(monitor.get("left", 0)),
                int(monitor.get("top", 0)),
                int(monitor.get("width", 0)),
                int(monitor.get("height", 0)),
            )
    except Exception:
        return (0, 0, 0, 0)


def cursor_position() -> tuple[int, int]:
    controller = _mouse_controller()
    if controller is None:
        return (0, 0)
    try:
        x, y = controller.position
        return int(x), int(y)
    except Exception:
        return (0, 0)


def move_to(x: int, y: int) -> bool:
    controller = _mouse_controller()
    if controller is None:
        return False
    try:
        with _INPUT_LOCK:
            controller.position = (int(x), int(y))
        return True
    except Exception:
        return False


def mouse_down(button: str = "left") -> bool:
    controller = _mouse_controller()
    target = _button_for(button)
    if controller is None or target is None:
        return False
    try:
        with _INPUT_LOCK:
            controller.press(target)
        return True
    except Exception:
        return False


def mouse_up(button: str = "left") -> bool:
    controller = _mouse_controller()
    target = _button_for(button)
    if controller is None or target is None:
        return False
    try:
        with _INPUT_LOCK:
            controller.release(target)
        return True
    except Exception:
        return False


def click(
    button: str = "left",
    x: int | None = None,
    y: int | None = None,
    double: bool = False,
    hold_ms: int = 0,
) -> bool:
    if x is not None and y is not None and cursor_position() != (int(x), int(y)):
        move_to(int(x), int(y))
    controller = _mouse_controller()
    target = _button_for(button)
    if controller is None or target is None:
        return False
    try:
        with _INPUT_LOCK:
            if hold_ms > 0:
                controller.press(target)
                time.sleep(min(hold_ms, 2000) / 1000.0)
                controller.release(target)
                return True
            controller.click(target, 2 if double else 1)
        return True
    except Exception:
        try:
            controller.release(target)
        except Exception:
            pass
        return False


def scroll(
    delta: int,
    horizontal: bool = False,
    x: int | None = None,
    y: int | None = None,
) -> bool:
    if x is not None and y is not None:
        move_to(int(x), int(y))
    controller = _mouse_controller()
    if controller is None:
        return False
    try:
        with _INPUT_LOCK:
            if horizontal:
                controller.scroll(int(delta), 0)
            else:
                controller.scroll(0, int(delta))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

def key_down(vk: int) -> bool:
    key = _key_for_vk(int(vk))
    controller = _key_controller()
    if key is None or controller is None:
        return False
    try:
        with _INPUT_LOCK:
            controller.press(key)
        return True
    except Exception:
        return False


def key_up(vk: int) -> bool:
    key = _key_for_vk(int(vk))
    controller = _key_controller()
    if key is None or controller is None:
        return False
    try:
        with _INPUT_LOCK:
            controller.release(key)
        return True
    except Exception:
        return False


def key_tap(vk: int, hold_ms: int = 0) -> bool:
    if hold_ms > 0:
        if not key_down(vk):
            return False
        try:
            time.sleep(min(hold_ms, 5000) / 1000.0)
        finally:
            key_up(vk)
        return True
    key = _key_for_vk(int(vk))
    controller = _key_controller()
    if key is None or controller is None:
        return False
    try:
        with _INPUT_LOCK:
            controller.press(key)
            controller.release(key)
        return True
    except Exception:
        return False


def release_all() -> None:
    """Release common mouse buttons and modifier keys to prevent stuck input."""
    controller = _mouse_controller()
    if controller is not None:
        _, buttons = _build_maps()
        for button in buttons.values():
            try:
                controller.release(button)
            except Exception:
                pass
    keyboard_controller = _key_controller()
    if keyboard_controller is not None:
        mapping, _ = _build_maps()
        for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
            key = mapping.get(vk)
            if key is None:
                continue
            try:
                keyboard_controller.release(key)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def beep(frequency: int = 800, duration: int = 10) -> None:
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass


def get_foreground_title() -> str:
    """Return the active window title via xdotool when available."""
    if shutil.which("xdotool") is None:
        return ""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=0.4,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def list_window_titles(limit: int = 250) -> list[str]:
    """List visible window titles via wmctrl, if installed."""
    if shutil.which("wmctrl") is None:
        return []
    try:
        result = subprocess.run(
            ["wmctrl", "-l"], capture_output=True, text=True, timeout=1.0
        )
        if result.returncode != 0:
            return []
        titles: list[str] = []
        for line in result.stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) == 4 and parts[3].strip():
                titles.append(parts[3].strip())
            if len(titles) >= limit:
                break
        return titles
    except Exception:
        return []


__all__ = [
    "begin_timer_resolution",
    "beep",
    "click",
    "cursor_position",
    "enable_dpi_awareness",
    "end_timer_resolution",
    "get_foreground_title",
    "is_admin",
    "key_down",
    "key_tap",
    "key_up",
    "list_window_titles",
    "mouse_down",
    "mouse_up",
    "move_to",
    "relaunch_as_admin",
    "release_all",
    "scan_code_mode",
    "scroll",
    "set_high_priority",
    "set_scan_code_mode",
    "virtual_screen_rect",
]
