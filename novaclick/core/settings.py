"""Small JSON settings store for preferences."""

from __future__ import annotations

import json
from typing import Any

from .paths import SETTINGS_FILE

DEFAULTS: dict[str, Any] = {
    "start_delay_ms": 0,
    "always_on_top": False,
    "confirm_delete": True,
    "show_toasts": True,
    "game_mode": False,
    "hotkeys": {},
}


class SettingsStore:
    def __init__(self) -> None:
        self._data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                # Accept every stored key so features added after 2.0.0
                # (click sound, window filter, presets) survive restarts.
                for key, value in payload.items():
                    self._data[key] = value
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def save(self) -> None:
        try:
            with SETTINGS_FILE.open("w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2)
        except OSError:
            pass

    def reset(self) -> None:
        self._data = dict(DEFAULTS)
        self.save()
