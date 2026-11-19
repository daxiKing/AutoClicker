"""Timeline editing helpers for recorded macros.

The recorder stores a flat list of timestamped input events. This module keeps
that format but adds non-destructive operations the visual editor uses:
trimming a time range, deleting events, nudging timestamps and reordering
events while keeping a valid, sorted timeline.
"""

from __future__ import annotations

from .keys import vk_name

EVENT_TYPES = ("move", "down", "up", "scroll", "keydown", "keyup")


def _time_of(event: dict) -> float:
    try:
        return max(0.0, float(event.get("t", 0.0)))
    except (TypeError, ValueError):
        return 0.0


def normalize_events(events: list[dict]) -> list[dict]:
    """Return copies sorted by time with normalized, rounded timestamps."""
    cleaned: list[dict] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        kind = str(event.get("type", ""))
        if kind not in EVENT_TYPES:
            continue
        copy = dict(event)
        copy["t"] = round(_time_of(event), 2)
        cleaned.append(copy)
    cleaned.sort(key=lambda item: item["t"])
    return cleaned


def event_duration(events: list[dict]) -> float:
    """Longest timestamp in the list, in milliseconds."""
    return round(max((_time_of(event) for event in events), default=0.0), 2)


def trim_events(events: list[dict], start_ms: float, end_ms: float) -> list[dict]:
    """Keep events inside ``[start_ms, end_ms]`` and rebase them to zero."""
    start_ms = max(0.0, float(start_ms))
    end_ms = max(0.0, float(end_ms))
    if end_ms <= start_ms:
        raise ValueError("Trim end must be after trim start.")
    kept: list[dict] = []
    for event in normalize_events(events):
        when = _time_of(event)
        if start_ms <= when <= end_ms:
            copy = dict(event)
            copy["t"] = round(when - start_ms, 2)
            kept.append(copy)
    return kept


def delete_events(events: list[dict], indices: set[int] | list[int]) -> list[dict]:
    """Drop the events at the given list positions."""
    ordered = normalize_events(events)
    drop = {int(index) for index in indices}
    return [event for index, event in enumerate(ordered) if index not in drop]


def nudge_events(events: list[dict], indices: set[int] | list[int], delta_ms: float) -> list[dict]:
    """Shift selected events by ``delta_ms`` without going below zero."""
    ordered = normalize_events(events)
    shift = float(delta_ms)
    targets = {int(index) for index in indices}
    for index, event in enumerate(ordered):
        if index in targets:
            event["t"] = round(max(0.0, _time_of(event) + shift), 2)
    ordered.sort(key=lambda item: item["t"])
    return ordered


def move_event(events: list[dict], index: int, offset: int) -> tuple[list[dict], int]:
    """Move one event up or down the timeline.

    Events keep their original timestamp slots, so moving a row swaps it with
    its neighbour in time while the rest of the sequence stays intact. Returns
    ``(events, new_index)``.
    """
    ordered = normalize_events(events)
    if not ordered:
        return ordered, 0
    index = max(0, min(len(ordered) - 1, int(index)))
    target = max(0, min(len(ordered) - 1, index + int(offset)))
    if target == index:
        return ordered, index
    slots = sorted(_time_of(event) for event in ordered)
    item = ordered.pop(index)
    ordered.insert(target, item)
    for event, timestamp in zip(ordered, slots):
        event["t"] = timestamp
    return ordered, target


def describe_event(event: dict) -> str:
    """One-line human description used by the editor table."""
    kind = str(event.get("type", ""))
    x = event.get("x")
    y = event.get("y")
    where = f"{x}, {y}" if x is not None and y is not None else "—"
    if kind == "move":
        return f"Move cursor to {where}"
    if kind in ("down", "up"):
        button = str(event.get("button", "left")).capitalize()
        state = "down" if kind == "down" else "up"
        return f"Mouse {button} {state} at {where}"
    if kind == "scroll":
        return f"Scroll {event.get('dx', 0)}, {event.get('dy', 0)} at {where}"
    if kind in ("keydown", "keyup"):
        name = event.get("name") or vk_name(int(event.get("vk", 0) or 0))
        state = "down" if kind == "keydown" else "up"
        return f"Key {name} {state}"
    return kind.title() or "Event"


def rebuild_macro(macro: dict, events: list[dict]) -> dict:
    """Return a macro copy with a fresh duration and the edited events."""
    updated = dict(macro)
    updated["events"] = normalize_events(events)
    updated["duration"] = event_duration(updated["events"])
    return updated


__all__ = [
    "delete_events",
    "describe_event",
    "event_duration",
    "move_event",
    "nudge_events",
    "normalize_events",
    "rebuild_macro",
    "trim_events",
]
