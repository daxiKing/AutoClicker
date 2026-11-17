"""Global hotkey metadata, bindings and persistence helpers.

Bindings are stored as ``{action: {"vk": int, "mods": [str, ...]}}`` so the
JSON settings file stays readable while the runtime uses immutable objects.
Every action can be rebound to any non-modifier key, optionally with
Ctrl / Alt / Shift / Win held. Matching is exact: a bare ``F6`` binding will
not fire while Ctrl is held, which keeps the user's typing predictable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .keys import current_modifiers, vk_name

ACTION_ORDER = ("clicker", "autokey", "record", "play", "panic")

# action -> (title, description, tone)
ACTION_INFO: dict[str, tuple[str, str, str]] = {
    "clicker": ("Click engine", "Start or stop native clicking.", "accent"),
    "autokey": ("Auto keys", "Start or stop the auto-key stream.", "accent"),
    "record": ("Record macro", "Arm, capture and save a sequence.", "violet"),
    "play": ("Playback", "Play or stop the selected macro.", "violet"),
    "panic": ("Panic stop", "Stop every engine and release held input.", "red"),
}

MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")
MODIFIER_LABELS = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "win": "Win",
}

# Virtual keys that represent a modifier. The generic variants are reported
# by some keyboard layouts, the left/right variants by others.
MODIFIER_VKS: dict[int, str] = {
    0x10: "shift",
    0xA0: "shift",
    0xA1: "shift",
    0x11: "ctrl",
    0xA2: "ctrl",
    0xA3: "ctrl",
    0x12: "alt",
    0xA4: "alt",
    0xA5: "alt",
    0x5B: "win",
    0x5C: "win",
}

@dataclass(frozen=True)
class Binding:
    """A single global shortcut: one key plus optional held modifiers."""

    vk: int
    mods: frozenset[str] = frozenset()

    @property
    def key_name(self) -> str:
        return vk_name(self.vk)

    def label(self) -> str:
        parts = [MODIFIER_LABELS[name] for name in MODIFIER_ORDER if name in self.mods]
        parts.append(self.key_name)
        return "+".join(parts)

    def compact_label(self) -> str:
        parts = [MODIFIER_LABELS[name] for name in MODIFIER_ORDER if name in self.mods]
        parts.append(self.key_name)
        return "+".join(parts)

    def payload(self) -> dict[str, Any]:
        return {
            "vk": int(self.vk),
            "mods": [name for name in MODIFIER_ORDER if name in self.mods],
        }

    @classmethod
    def from_payload(cls, payload: Any) -> "Binding | None":
        if isinstance(payload, Binding):
            return payload
        if isinstance(payload, int):
            return cls(payload)
        if not isinstance(payload, dict):
            return None
        try:
            vk = int(payload.get("vk", 0))
        except (TypeError, ValueError):
            return None
        if not 0 <= vk <= 0xFF:
            return None
        if vk == 0:
            # vk 0 means "unbound" — Escape-cleared actions persist this way.
            return cls(0)
        if modifier_for_vk(vk) is not None:
            return None
        raw_mods = payload.get("mods", [])
        if isinstance(raw_mods, str):
            raw_mods = [raw_mods]
        if not isinstance(raw_mods, (list, tuple, set)):
            return None
        mods = frozenset(
            str(item).strip().lower()
            for item in raw_mods
            if str(item).strip().lower() in MODIFIER_LABELS
        )
        return cls(vk, mods)


DEFAULT_BINDINGS: dict[str, Binding] = {
    "clicker": Binding(0x75),  # F6
    "autokey": Binding(0x76),  # F7
    "record": Binding(0x77),   # F8
    "play": Binding(0x78),     # F9
    "panic": Binding(0x79),    # F10
}


def modifier_for_vk(vk: int) -> str | None:
    return MODIFIER_VKS.get(int(vk))


def _first_free(used: set[Binding]) -> Binding:
    for number in range(1, 25):
        candidate = Binding(0x70 + number - 1)
        if candidate not in used:
            return candidate
    return Binding(0x71)


def load_bindings(raw: Any) -> dict[str, Binding]:
    """Merge persisted bindings with defaults, rejecting duplicates.

    A binding with ``vk == 0`` is a deliberate "unbound" state and is kept
    as-is; duplicate detection only applies to real key bindings.
    """
    payload = raw if isinstance(raw, dict) else {}
    resolved: dict[str, Binding] = {}
    used: set[Binding] = set()
    for action in ACTION_ORDER:
        binding = Binding.from_payload(payload.get(action))
        if binding is not None and binding.vk != 0 and binding in used:
            binding = None
        if binding is None:
            binding = DEFAULT_BINDINGS[action]
            if binding in used:
                binding = _first_free(used)
        resolved[action] = binding
        if binding.vk != 0:
            used.add(binding)
    return resolved


def serialize_bindings(bindings: dict[str, Binding]) -> dict[str, dict[str, Any]]:
    return {
        action: bindings[action].payload()
        for action in ACTION_ORDER
        if action in bindings
    }


def conflict_for(
    bindings: dict[str, Binding], action: str, binding: Binding
) -> str | None:
    """Return the other action already using *binding*, if any."""
    if binding.vk == 0:
        return None
    for other, candidate in bindings.items():
        if other != action and candidate.vk != 0 and candidate == binding:
            return other
    return None


def action_title(action: str) -> str:
    return ACTION_INFO.get(action, (action.title(), "", "accent"))[0]


__all__ = [
    "ACTION_INFO",
    "ACTION_ORDER",
    "Binding",
    "DEFAULT_BINDINGS",
    "MODIFIER_LABELS",
    "MODIFIER_ORDER",
    "action_title",
    "conflict_for",
    "current_modifiers",
    "load_bindings",
    "modifier_for_vk",
    "serialize_bindings",
]
