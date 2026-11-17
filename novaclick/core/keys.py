"""Keyboard helpers shared by the input engine and the UI."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform.startswith("win")

_MAPVK_VK_TO_VSC = 0
if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    _GetKeyNameTextW = user32.GetKeyNameTextW
    _GetKeyNameTextW.argtypes = (wintypes.LONG, wintypes.LPWSTR, ctypes.c_int)
    _GetKeyNameTextW.restype = ctypes.c_int
    _MapVirtualKeyW = user32.MapVirtualKeyW
    _MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    _MapVirtualKeyW.restype = wintypes.UINT
    _GetAsyncKeyState = user32.GetAsyncKeyState
    _GetAsyncKeyState.argtypes = (ctypes.c_int,)
    _GetAsyncKeyState.restype = ctypes.c_short
else:  # pragma: no cover - exercised on Linux
    user32 = None
    _GetKeyNameTextW = None
    _MapVirtualKeyW = None
    _GetAsyncKeyState = None

# Virtual-key codes that Windows treats as "extended" keys.
EXTENDED_VKS = {
    0x21,  # page up
    0x22,  # page down
    0x23,  # end
    0x24,  # home
    0x25,  # left
    0x26,  # up
    0x27,  # right
    0x28,  # down
    0x2D,  # insert
    0x2E,  # delete
    0x5B,  # left windows
    0x5C,  # right windows
    0x5D,  # applications
    0x6F,  # numpad divide
    0x90,  # num lock
    0xA3,  # right control
    0xA5,  # right alt
}

_NAMES = {
    0x08: "Backspace",
    0x09: "Tab",
    0x0D: "Enter",
    0x13: "Pause",
    0x14: "Caps Lock",
    0x1B: "Esc",
    0x20: "Space",
    0x21: "Page Up",
    0x22: "Page Down",
    0x23: "End",
    0x24: "Home",
    0x25: "Left",
    0x26: "Up",
    0x27: "Right",
    0x28: "Down",
    0x2C: "Print Screen",
    0x2D: "Insert",
    0x2E: "Delete",
    0x5B: "Left Win",
    0x5C: "Right Win",
    0x5D: "Menu",
    0x6A: "Numpad *",
    0x6B: "Numpad +",
    0x6D: "Numpad -",
    0x6E: "Numpad .",
    0x6F: "Numpad /",
    0x90: "Num Lock",
    0x91: "Scroll Lock",
    0xA0: "Left Shift",
    0xA1: "Right Shift",
    0xA2: "Left Ctrl",
    0xA3: "Right Ctrl",
    0xA4: "Left Alt",
    0xA5: "Right Alt",
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


def vk_name(vk: int) -> str:
    """Return a human-friendly name for a virtual key."""
    if not vk:
        return "Unbound"
    if vk in _NAMES:
        return _NAMES[vk]
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Numpad {vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"

    if _MapVirtualKeyW is None:
        return f"VK {vk:02X}"
    scan = _MapVirtualKeyW(vk, _MAPVK_VK_TO_VSC)
    if scan:
        flags = 1 << 24 if vk in EXTENDED_VKS else 0
        lparam = (scan << 16) | flags
        buffer = ctypes.create_unicode_buffer(64)
        if _GetKeyNameTextW(lparam, buffer, 64):
            name = buffer.value.strip()
            if name:
                return name
    return f"VK {vk:02X}"


def is_extended(vk: int) -> bool:
    return vk in EXTENDED_VKS


_MODIFIER_STATE_VKS = {
    "ctrl": (0x11, 0xA2, 0xA3),
    "alt": (0x12, 0xA4, 0xA5),
    "shift": (0x10, 0xA0, 0xA1),
    "win": (0x5B, 0x5C),
}


def key_is_down(vk: int) -> bool:
    """Return True while a virtual key is physically held."""
    if _GetAsyncKeyState is None:
        return False
    try:
        return bool(_GetAsyncKeyState(int(vk)) & 0x8000)
    except Exception:
        return False


def current_modifiers() -> frozenset[str]:
    """Read the live Ctrl / Alt / Shift / Win state.

    This is called from listener threads before matching a hotkey. Querying
    the OS is more reliable than tracking press/release pairs, which can get
    stuck when focus changes or a chord starts before the listener is ready.
    """
    held: set[str] = set()
    for name, codes in _MODIFIER_STATE_VKS.items():
        for code in codes:
            if key_is_down(code):
                held.add(name)
                break
    return frozenset(held)


def pynput_key_to_vk(key) -> int | None:
    """Normalize a pynput key object into a Windows virtual-key code."""
    if key is None:
        return None

    vk = getattr(key, "vk", None)
    if IS_WINDOWS and isinstance(vk, int) and vk > 0:
        return vk

    value = getattr(key, "value", None)
    if IS_WINDOWS and isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and len(value) == 1:
        try:
            return ord(value.upper())
        except (TypeError, ValueError):
            pass

    name = getattr(key, "name", None)
    if name:
        alias = {
            "space": 0x20,
            "enter": 0x0D,
            "return": 0x0D,
            "tab": 0x09,
            "esc": 0x1B,
            "escape": 0x1B,
            "backspace": 0x08,
            "delete": 0x2E,
            "insert": 0x2D,
            "home": 0x24,
            "end": 0x23,
            "page_up": 0x21,
            "page_down": 0x22,
            "up": 0x26,
            "down": 0x28,
            "left": 0x25,
            "right": 0x27,
            "shift": 0x10,
            "shift_l": 0xA0,
            "shift_r": 0xA1,
            "ctrl": 0x11,
            "ctrl_l": 0xA2,
            "ctrl_r": 0xA3,
            "alt": 0x12,
            "alt_l": 0xA4,
            "alt_gr": 0xA5,
            "caps_lock": 0x14,
            "num_lock": 0x90,
            "scroll_lock": 0x91,
            "cmd": 0x5B,
            "cmd_l": 0x5B,
            "cmd_r": 0x5C,
            "menu": 0x5D,
        }
        if name.startswith("f") and name[1:].isdigit():
            number = int(name[1:])
            if 1 <= number <= 24:
                return 0x70 + number - 1
        if name in alias:
            return alias[name]

    char = getattr(key, "char", None)
    if isinstance(char, str) and len(char) == 1:
        try:
            return ord(char.upper())
        except (TypeError, ValueError):
            pass
    return None
