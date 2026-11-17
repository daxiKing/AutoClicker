"""Platform input facade.

Windows uses the native SendInput backend; Linux uses pynput (X11/Wayland).
Callers import this module and use the same function names on both platforms.
Windows-only capabilities (scan-code mode, elevation, window-title filtering)
degrade to safe no-ops on Linux.
"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform.startswith("win")
PLATFORM = "windows" if IS_WINDOWS else "linux"

if IS_WINDOWS:
    from .wininput_win import *  # noqa: F401,F403
    from .wininput_win import __all__ as _backend_all
else:
    from .wininput_linux import *  # noqa: F401,F403
    from .wininput_linux import __all__ as _backend_all

__all__ = [*_backend_all, "IS_WINDOWS", "PLATFORM"]
