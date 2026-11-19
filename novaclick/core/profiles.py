"""App profiles and timed-run helpers for the automation page.

Profiles map a foreground window title to a saved clicker preset. Schedules
describe one macro run on selected weekdays at a fixed local time. Everything
is plain dictionaries so it round-trips through the settings JSON untouched.
"""

from __future__ import annotations

from datetime import datetime, time as clock_time, timedelta

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

DAY_PRESETS: dict[str, tuple[int, ...]] = {
    "every_day": (0, 1, 2, 3, 4, 5, 6),
    "weekdays": (0, 1, 2, 3, 4),
    "weekends": (5, 6),
}


def normalize_days(days) -> tuple[int, ...]:
    """Convert a day preset, iterable or comma string into weekday numbers."""
    if days is None:
        return DAY_PRESETS["every_day"]
    if isinstance(days, str):
        preset = DAY_PRESETS.get(days)
        if preset:
            return preset
        parts = [part.strip() for part in days.replace(";", ",").split(",") if part.strip()]
        values = []
        for part in parts:
            if part.isdigit() and 0 <= int(part) <= 6:
                values.append(int(part))
        return tuple(sorted(set(values))) or DAY_PRESETS["every_day"]
    try:
        values = sorted({int(day) for day in days if 0 <= int(day) <= 6})
    except (TypeError, ValueError):
        return DAY_PRESETS["every_day"]
    return tuple(values) or DAY_PRESETS["every_day"]


def days_label(days) -> str:
    normalized = normalize_days(days)
    if normalized == DAY_PRESETS["every_day"]:
        return "Every day"
    if normalized == DAY_PRESETS["weekdays"]:
        return "Weekdays"
    if normalized == DAY_PRESETS["weekends"]:
        return "Weekends"
    return ", ".join(DAY_NAMES[day] for day in normalized)


def parse_clock(text: str) -> tuple[int, int] | None:
    """Parse ``HH:MM`` (24h) and return ``(hour, minute)`` or ``None``."""
    raw = str(text or "").strip().replace(".", ":")
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def format_clock_text(hour: int, minute: int) -> str:
    return f"{int(hour):02d}:{int(minute):02d}"


def window_matches(query: str, title: str) -> bool:
    """True when the non-empty query appears in the window title."""
    needle = str(query or "").strip().lower()
    return bool(needle) and needle in str(title or "").lower()


def best_profile(profiles: list[dict], title: str) -> dict | None:
    """Pick the enabled profile with the longest matching title fragment."""
    winner: dict | None = None
    winner_length = -1
    for profile in profiles or []:
        if not isinstance(profile, dict) or not profile.get("enabled", True):
            continue
        match = str(profile.get("match", "")).strip()
        if not window_matches(match, title):
            continue
        if len(match) > winner_length:
            winner = profile
            winner_length = len(match)
    return winner


def next_occurrence(clock: str, days, now: datetime | None = None) -> datetime | None:
    """Return the next scheduled datetime strictly after ``now``."""
    parsed = parse_clock(clock)
    if not parsed:
        return None
    hour, minute = parsed
    normalized = normalize_days(days)
    moment = now or datetime.now()
    for offset in range(0, 8):
        day = (moment + timedelta(days=offset)).date()
        if day.weekday() not in normalized:
            continue
        candidate = datetime.combine(day, clock_time(hour, minute))
        if candidate > moment:
            return candidate
    return None


def due_schedules(
    schedules: list[dict],
    now: datetime | None = None,
    last_fired: dict[str, str] | None = None,
    window_seconds: int = 120,
) -> list[tuple[dict, datetime]]:
    """Return schedules whose moment fell within the last ``window_seconds``.

    The window tolerates timer jitter and short sleeps. ``last_fired`` maps a
    schedule id to the ISO timestamp of the occurrence already handled, so a
    run never fires twice for the same day.
    """
    moment = now or datetime.now()
    fired = last_fired or {}
    due: list[tuple[dict, datetime]] = []
    for schedule in schedules or []:
        if not isinstance(schedule, dict) or not schedule.get("enabled", True):
            continue
        parsed = parse_clock(str(schedule.get("time", "")))
        if not parsed:
            continue
        hour, minute = parsed
        days = normalize_days(schedule.get("days"))
        for offset in (0, 1):
            day = (moment - timedelta(days=offset)).date()
            if day.weekday() not in days:
                continue
            occurrence = datetime.combine(day, clock_time(hour, minute))
            elapsed = (moment - occurrence).total_seconds()
            if 0 <= elapsed < max(5, int(window_seconds)):
                key = str(schedule.get("id") or schedule.get("time") or "")
                if fired.get(key) != occurrence.isoformat(timespec="minutes"):
                    due.append((schedule, occurrence))
                break
    return due


def schedule_summary(schedule: dict, now: datetime | None = None) -> str:
    """Readable one-liner used by the schedule list and next-run label."""
    name = str(schedule.get("macro_name") or "Macro")
    clock = str(schedule.get("time") or "—")
    days = days_label(schedule.get("days"))
    text = f"{clock}  ·  {days}  ·  {name}"
    if schedule.get("enabled", True):
        upcoming = next_occurrence(clock, schedule.get("days"), now)
        if upcoming:
            text += f"  ·  next {upcoming.strftime('%a %H:%M')}"
    else:
        text += "  ·  paused"
    return text


__all__ = [
    "DAY_NAMES",
    "DAY_PRESETS",
    "best_profile",
    "days_label",
    "due_schedules",
    "format_clock_text",
    "next_occurrence",
    "normalize_days",
    "parse_clock",
    "schedule_summary",
    "window_matches",
]
