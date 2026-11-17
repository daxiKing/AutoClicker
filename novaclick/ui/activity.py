"""Thread-safe in-app activity feed."""

from __future__ import annotations

import threading
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from ..core.paths import LOG_FILE

MAX_ENTRIES = 800


class ActivityLog(QObject):
    entry = Signal(str, str, str)  # time, level, message
    cleared = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._entries: list[tuple[str, str, str]] = []

    def log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self._entries.append((timestamp, level, message))
            if len(self._entries) > MAX_ENTRIES:
                self._entries = self._entries[-MAX_ENTRIES:]
            try:
                with LOG_FILE.open("a", encoding="utf-8") as handle:
                    handle.write(f"{datetime.now().isoformat(timespec='seconds')} [{level.upper()}] {message}\n")
            except OSError:
                pass
        self.entry.emit(timestamp, level, message)

    def entries(self) -> list[tuple[str, str, str]]:
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            try:
                LOG_FILE.write_text("", encoding="utf-8")
            except OSError:
                pass
        self.cleared.emit()
