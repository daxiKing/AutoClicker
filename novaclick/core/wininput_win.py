"""Native Windows input injection built on SendInput."""

from __future__ import annotations

import base64
import ctypes
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

try:
    import winsound
except Exception:  # pragma: no cover - Windows-only
    winsound = None

user32 = ctypes.WinDLL("user32", use_last_error=True)
winmm = ctypes.WinDLL("winmm")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# ---------------------------------------------------------------------------
# Windows API structures
# ---------------------------------------------------------------------------

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE = 0x0004

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

_MOUSE_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

# Game input mode sends keyboard events as hardware scan codes instead of
# virtual-key messages. DirectInput-era games and some engines only sample the
# raw keyboard state, so scan-code injection is much more reliable there while
# remaining normal SendInput (no driver, no injection into another process).
_scan_code_mode = False
_scan_code_lock = threading.Lock()

_IDLE_PRIORITY_CLASS = 0x00000040
_NORMAL_PRIORITY_CLASS = 0x00000020
_HIGH_PRIORITY_CLASS = 0x00000080


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUTUNION),
    ]


_SendInput = user32.SendInput
_SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_SendInput.restype = wintypes.UINT

_GetCursorPos = user32.GetCursorPos
_GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
_GetCursorPos.restype = wintypes.BOOL

_GetSystemMetrics = user32.GetSystemMetrics
_GetSystemMetrics.argtypes = (ctypes.c_int,)
_GetSystemMetrics.restype = ctypes.c_int

_MapVirtualKeyW = user32.MapVirtualKeyW
_MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
_MapVirtualKeyW.restype = wintypes.UINT

SetProcessDpiAwarenessContext = getattr(user32, "SetProcessDpiAwarenessContext", None)
if SetProcessDpiAwarenessContext:
    SetProcessDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
    SetProcessDpiAwarenessContext.restype = wintypes.BOOL


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------

def set_scan_code_mode(enabled: bool) -> bool:
    """Toggle hardware scan-code keyboard injection (game input mode)."""
    global _scan_code_mode
    with _scan_code_lock:
        _scan_code_mode = bool(enabled)
        return _scan_code_mode


def scan_code_mode() -> bool:
    with _scan_code_lock:
        return _scan_code_mode


def set_high_priority(enabled: bool) -> bool:
    """Raise the process priority while game mode is active."""
    try:
        handle = kernel32.GetCurrentProcess()
        priority = _HIGH_PRIORITY_CLASS if enabled else _NORMAL_PRIORITY_CLASS
        return bool(kernel32.SetPriorityClass(handle, priority))
    except Exception:
        return False


def is_admin() -> bool:
    """Return True when the current process is elevated."""
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.IsUserAnAdmin.argtypes = ()
        shell32.IsUserAnAdmin.restype = wintypes.BOOL
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Relaunch AutoClicker elevated after the current instance exits.

    A short-lived hidden PowerShell helper waits for this process to release the
    single-instance mutex, then triggers the normal Windows UAC prompt. The new
    copy inherits the working directory so its portable data folder is reused.
    """
    try:
        exe = Path(sys.executable).resolve()
        if getattr(sys, "frozen", False):
            arguments = list(sys.argv[1:])
        else:
            script = Path(sys.argv[0]).resolve()
            arguments = [str(script), *sys.argv[1:]]

        def quote(value: str) -> str:
            return "'" + str(value).replace("'", "''") + "'"

        args_literal = "@(" + ", ".join(quote(item) for item in arguments) + ")"
        script = (
            "Start-Sleep -Milliseconds 1400; "
            f"Start-Process -FilePath {quote(str(exe))} "
            f"-ArgumentList {args_literal} "
            f"-WorkingDirectory {quote(str(Path.cwd()))} "
            "-Verb RunAs"
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        creation_flags = 0x08000000  # CREATE_NO_WINDOW
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                encoded,
            ],
            creationflags=creation_flags,
            close_fds=True,
        )
        return True
    except Exception:
        return False


def enable_dpi_awareness() -> None:
    """Match Windows coordinates to physical pixels before Qt starts."""
    try:
        if SetProcessDpiAwarenessContext and SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


_timer_lock = threading.Lock()
_timer_owners = 0


def begin_timer_resolution() -> None:
    """Ask Windows for 1 ms timer granularity while the app is running."""
    global _timer_owners
    with _timer_lock:
        if _timer_owners == 0:
            try:
                winmm.timeBeginPeriod(1)
            except Exception:
                pass
        _timer_owners += 1


def end_timer_resolution() -> None:
    global _timer_owners
    with _timer_lock:
        if _timer_owners > 0:
            _timer_owners -= 1
            if _timer_owners == 0:
                try:
                    winmm.timeEndPeriod(1)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _mouse_input(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> INPUT:
    item = INPUT(type=INPUT_MOUSE)
    item.mi = MOUSEINPUT(dx, dy, data, flags, 0, 0)
    return item


def _key_input(vk: int, up: bool = False) -> INPUT:
    from .keys import is_extended

    item = INPUT(type=INPUT_KEYBOARD)
    scan = _MapVirtualKeyW(vk, 0) & 0xFF
    flags = KEYEVENTF_KEYUP if up else 0
    if is_extended(vk):
        flags |= KEYEVENTF_EXTENDEDKEY
    virtual_key = vk & 0xFFFF
    if scan_code_mode() and scan:
        flags |= KEYEVENTF_SCANCODE
        virtual_key = 0
    item.ki = KEYBDINPUT(virtual_key, scan, flags, 0, 0)
    return item


def _send(items: list[INPUT]) -> bool:
    if not items:
        return False
    array = (INPUT * len(items))(*items)
    sent = _SendInput(len(items), array, ctypes.sizeof(INPUT))
    return sent == len(items)


def _absolute(x: int, y: int) -> tuple[int, int]:
    left = _GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = _GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = max(_GetSystemMetrics(SM_CXVIRTUALSCREEN), 2)
    height = max(_GetSystemMetrics(SM_CYVIRTUALSCREEN), 2)
    nx = round((x - left) * 65535 / (width - 1))
    ny = round((y - top) * 65535 / (height - 1))
    return min(max(nx, 0), 65535), min(max(ny, 0), 65535)


def virtual_screen_rect() -> tuple[int, int, int, int]:
    return (
        _GetSystemMetrics(SM_XVIRTUALSCREEN),
        _GetSystemMetrics(SM_YVIRTUALSCREEN),
        _GetSystemMetrics(SM_CXVIRTUALSCREEN),
        _GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def cursor_position() -> tuple[int, int]:
    point = wintypes.POINT()
    _GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


_mouse_move_lock = threading.Lock()


def move_to(x: int, y: int) -> bool:
    nx, ny = _absolute(int(x), int(y))
    with _mouse_move_lock:
        return _send([
            _mouse_input(
                MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                nx,
                ny,
            )
        ])


def mouse_down(button: str = "left") -> bool:
    down_flag, _ = _MOUSE_BUTTONS.get(button, _MOUSE_BUTTONS["left"])
    return _send([_mouse_input(down_flag)])


def mouse_up(button: str = "left") -> bool:
    _, up_flag = _MOUSE_BUTTONS.get(button, _MOUSE_BUTTONS["left"])
    return _send([_mouse_input(up_flag)])


def click(
    button: str = "left",
    x: int | None = None,
    y: int | None = None,
    double: bool = False,
    hold_ms: int = 0,
) -> bool:
    """Send one click, optionally at a specific screen coordinate."""
    if x is not None and y is not None:
        current = cursor_position()
        if abs(current[0] - x) > 0 or abs(current[1] - y) > 0:
            move_to(x, y)

    down_flag, up_flag = _MOUSE_BUTTONS.get(button, _MOUSE_BUTTONS["left"])

    if hold_ms > 0:
        if not mouse_down(button):
            return False
        try:
            time.sleep(min(hold_ms, 2000) / 1000.0)
        finally:
            mouse_up(button)
        return True

    items = [_mouse_input(down_flag), _mouse_input(up_flag)]
    if double:
        items += [_mouse_input(down_flag), _mouse_input(up_flag)]
    return _send(items)


def scroll(delta: int, horizontal: bool = False, x: int | None = None, y: int | None = None) -> bool:
    """Send one wheel notch. Positive scrolls up / right."""
    if x is not None and y is not None:
        move_to(x, y)
    flags = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
    return _send([_mouse_input(flags, data=ctypes.c_uint32(int(delta) & 0xFFFFFFFF).value)])


def key_down(vk: int) -> bool:
    if not vk:
        return False
    return _send([_key_input(vk, up=False)])


def key_up(vk: int) -> bool:
    if not vk:
        return False
    return _send([_key_input(vk, up=True)])


def key_tap(vk: int, hold_ms: int = 0) -> bool:
    if not vk:
        return False
    if hold_ms > 0:
        if not key_down(vk):
            return False
        try:
            time.sleep(min(hold_ms, 5000) / 1000.0)
        finally:
            key_up(vk)
        return True
    return _send([_key_input(vk, up=False), _key_input(vk, up=True)])


def release_all() -> None:
    """Release common mouse buttons and modifiers to prevent stuck input."""
    items: list[INPUT] = []
    for _, (_, up_flag) in _MOUSE_BUTTONS.items():
        items.append(_mouse_input(up_flag))
    for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
        items.append(_key_input(vk, up=True))
    if items:
        _send(items)


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

_foreground_title_cache: tuple[float, str] = (0.0, "")


def beep(frequency: int = 800, duration: int = 10) -> None:
    """Play a short system beep for click-audible feedback."""
    if winsound is None:
        return
    try:
        winsound.Beep(max(37, min(frequency, 32767)), max(1, min(duration, 5000)))
    except Exception:
        pass


def get_foreground_title() -> str:
    """Return the title of the foreground window, cached for 100 ms.

    The cache keeps window-title checks cheap during high-CPS clicking.
    """
    now = time.perf_counter()
    if now - _foreground_title_cache[0] < 0.1:
        return _foreground_title_cache[1]
    try:
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            length = user32.GetWindowTextLengthW(hwnd) + 1
            buffer = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, buffer, length)
            title = buffer.value
        else:
            title = ""
    except Exception:
        title = ""
    _foreground_title_cache = (now, title)
    return title


def list_window_titles(limit: int = 250) -> list[str]:
    """Return the titles of visible top-level windows, de-duplicated in Z-order."""
    titles: list[str] = []
    try:
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        def _on_window(hwnd, _lparam):
            try:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buffer, length + 1)
                        titles.append(buffer.value)
            except Exception:
                pass
            return True

        user32.EnumWindows(WNDENUMPROC(_on_window), 0)
    except Exception:
        pass
    unique: list[str] = []
    seen: set[str] = set()
    for title in titles:
        if title and title not in seen:
            seen.add(title)
            unique.append(title)
        if len(unique) >= limit:
            break
    return unique


# Sanity check for developers.
assert ctypes.sizeof(INPUT) in (28, 40), ctypes.sizeof(INPUT)

__all__ = [
    'begin_timer_resolution',
    'beep',
    'click',
    'cursor_position',
    'enable_dpi_awareness',
    'end_timer_resolution',
    'get_foreground_title',
    'is_admin',
    'key_down',
    'key_tap',
    'key_up',
    'list_window_titles',
    'mouse_down',
    'mouse_up',
    'move_to',
    'relaunch_as_admin',
    'release_all',
    'scan_code_mode',
    'scroll',
    'set_high_priority',
    'set_scan_code_mode',
    'virtual_screen_rect',
]

