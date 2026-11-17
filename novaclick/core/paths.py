"""Filesystem locations used by AutoClicker."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    # Portable installs keep macros/settings beside the executable rather than
    # inside PyInstaller's temporary extraction directory.
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = PACKAGE_DIR.parent
DATA_DIR = BASE_DIR / "data"
MACRO_DIR = DATA_DIR / "macros"
LOG_FILE = DATA_DIR / "activity.log"
SETTINGS_FILE = DATA_DIR / "settings.json"


def ensure_dirs() -> None:
    for folder in (DATA_DIR, MACRO_DIR):
        folder.mkdir(parents=True, exist_ok=True)


ensure_dirs()
