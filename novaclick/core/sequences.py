"""Conditional multi-image sequences.

A sequence is a list of steps. Each step either scans for one target image and
performs an action when it appears, or performs a fixed action (wait / stop).
Missed targets can be skipped, retried or treated as a hard stop, which makes
simple visual workflows possible without writing a script.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import wininput
from .image_clicker import (
    IMAGE_DEPS,
    IMAGE_IMPORT_ERROR,
    _frame_from_shot,
    _select_monitor,
    load_template,
)
from .keys import vk_from_name

SEQUENCE_ACTIONS = ("click", "key", "wait", "stop")
MISS_POLICIES = ("skip", "retry", "abort")


@dataclass(frozen=True)
class SequenceConfig:
    threshold: float = 0.85
    interval: float = 0.4
    monitor: str = "all"
    grayscale: bool = False
    offset_x: int = 0
    offset_y: int = 0
    button: str = "left"


def normalize_steps(steps: list[dict]) -> list[dict]:
    """Validate persisted step dictionaries and fill safe defaults."""
    cleaned: list[dict] = []
    for raw in steps or []:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action", "click")).lower()
        if action not in SEQUENCE_ACTIONS:
            action = "click"
        policy = str(raw.get("on_miss", "skip")).lower()
        if policy not in MISS_POLICIES:
            policy = "skip"
        try:
            wait_ms = max(0, min(600_000, int(raw.get("wait_ms", 500))))
        except (TypeError, ValueError):
            wait_ms = 500
        try:
            timeout = max(0.2, min(600.0, float(raw.get("timeout_s", 10.0))))
        except (TypeError, ValueError):
            timeout = 10.0
        cleaned.append(
            {
                "image": str(raw.get("image", "") or ""),
                "action": action,
                "key": str(raw.get("key", "Space") or "Space"),
                "wait_ms": wait_ms,
                "timeout_s": round(timeout, 2),
                "on_miss": policy,
            }
        )
    return cleaned


def step_summary(step: dict, index: int = 0) -> str:
    """Readable row text for the sequence list."""
    action = str(step.get("action", "click"))
    image = Path(str(step.get("image", ""))).name or "—"
    prefix = f"{index + 1:02d}" if index >= 0 else "·"
    if action == "click":
        detail = f"click {image} when found"
    elif action == "key":
        detail = f"press {step.get('key', 'Space')} when {image} appears"
    elif action == "wait":
        detail = f"wait {int(step.get('wait_ms', 0)) / 1000:.2f}s"
    else:
        detail = "stop the sequence"
    if action in ("click", "key"):
        detail += f" · timeout {float(step.get('timeout_s', 0)):.1f}s · miss {step.get('on_miss', 'skip')}"
    return f"{prefix}  {detail}"


def best_match(frame, template):
    """Return ``(score, (x, y), (width, height))`` for one template."""
    import cv2

    height, width = template.shape[:2]
    frame_height, frame_width = frame.shape[:2]
    if height > frame_height or width > frame_width:
        return 0.0, (0, 0), (0, 0)
    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(result)
    return max(0.0, min(1.0, float(score))), (int(location[0]), int(location[1])), (
        int(width),
        int(height),
    )


class SequenceRunner:
    """Run conditional image steps on a worker thread."""

    label = "Sequence runner"

    def __init__(self, matcher=None, actor=None, grabber=None) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._active = False
        self._steps: list[dict] = []
        self._config = SequenceConfig()
        self._step_index = 0
        self._step_total = 0
        self._step_name = ""
        self._scans = 0
        self._matches = 0
        self._message = "Idle"
        self._error: str | None = None
        self._started_at = 0.0
        self._matcher = matcher or best_match
        self._actor = actor or self._default_actor
        self._grabber = grabber

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active": self._active,
                "step_index": self._step_index,
                "step_total": self._step_total,
                "step_name": self._step_name,
                "scans": self._scans,
                "matches": self._matches,
                "message": self._message,
                "error": self._error,
                "elapsed": time.perf_counter() - self._started_at if self._started_at else 0.0,
            }

    def start(self, steps: list[dict], config: SequenceConfig | None = None) -> bool:
        normalized = normalize_steps(steps)
        if not normalized:
            self._error = "Add at least one sequence step first."
            return False
        needs_screen = any(step["action"] in ("click", "key") for step in normalized)
        if needs_screen and not IMAGE_DEPS:
            self._error = IMAGE_IMPORT_ERROR or "Image dependencies are missing."
            return False
        for step in normalized:
            if step["action"] not in ("click", "key"):
                continue
            if not step["image"]:
                self._error = "A scan step has no target image."
                return False
            if not Path(step["image"]).is_file():
                self._error = f"Target image missing: {Path(step['image']).name}"
                return False
            if step["action"] == "key" and vk_from_name(step["key"]) is None:
                self._error = f"Unknown key name: {step['key']}"
                return False
        with self._lock:
            if self._active:
                return False
            self._active = True
            self._steps = normalized
            self._config = config or SequenceConfig()
            self._step_index = 0
            self._step_total = len(normalized)
            self._step_name = ""
            self._scans = 0
            self._matches = 0
            self._message = "Sequence armed"
            self._error = None
            self._started_at = time.perf_counter()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_guarded, daemon=True)
        self._thread.start()
        return True

    def stop(self, wait: float = 0.6) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=wait)

    # ------------------------------------------------------------------
    def _default_actor(self, action: str, step: dict, x: int | None, y: int | None) -> None:
        if action == "click":
            wininput.click(button=self._config.button, x=x, y=y)
        elif action == "key":
            vk = vk_from_name(step.get("key", "Space"))
            if vk:
                wininput.key_tap(vk)

    def _run_guarded(self) -> None:
        try:
            self._run()
        except Exception as exc:  # pragma: no cover - defensive
            with self._lock:
                self._error = f"Sequence fault: {exc}"
                self._message = self._error
        finally:
            with self._lock:
                self._active = False
            self._stop.set()

    def _run(self) -> None:
        steps = self._steps
        cfg = self._config
        templates: dict[str, object] = {}
        if self._grabber is None:
            import mss

            capture = mss.mss()
            monitor = _select_monitor(capture.monitors, cfg.monitor)
        else:
            capture = None
            monitor = {"left": 0, "top": 0, "width": 0, "height": 0}

        try:
            for position, step in enumerate(steps):
                if self._stop.is_set():
                    return
                action = step["action"]
                image = step["image"]
                name = Path(image).name if image else "Wait"
                with self._lock:
                    self._step_index = position + 1
                    self._step_name = name
                    self._message = f"Step {self._step_index}/{len(steps)}: {name}"

                if action == "wait":
                    with self._lock:
                        self._message = f"Waiting {step['wait_ms'] / 1000:.2f}s"
                    if self._stop.wait(step["wait_ms"] / 1000.0):
                        return
                    continue
                if action == "stop":
                    with self._lock:
                        self._message = "Sequence stop step reached"
                    return

                if image not in templates:
                    templates[image] = load_template(image, grayscale=cfg.grayscale)
                template = templates[image]
                deadline = time.perf_counter() + step["timeout_s"] if step["timeout_s"] > 0 else None

                while not self._stop.is_set():
                    started = time.perf_counter()
                    if self._grabber is not None:
                        frame, frame_monitor = self._grabber()
                        monitor = frame_monitor
                    else:
                        shot = capture.grab(monitor)
                        frame = _frame_from_shot(shot, cfg.grayscale)
                    score, location, (width, height) = self._matcher(frame, template)
                    with self._lock:
                        self._scans += 1

                    if score >= cfg.threshold:
                        x = int(monitor.get("left", 0)) + location[0] + width // 2 + cfg.offset_x
                        y = int(monitor.get("top", 0)) + location[1] + height // 2 + cfg.offset_y
                        self._actor(action, step, x, y)
                        with self._lock:
                            self._matches += 1
                            self._message = (
                                f"Step {self._step_index}/{len(steps)}: {name} matched "
                                f"({score * 100:.0f}%)"
                            )
                        break

                    if deadline is not None and time.perf_counter() >= deadline:
                        policy = step["on_miss"]
                        if policy == "abort":
                            with self._lock:
                                self._message = f"{name} not found — sequence aborted"
                            return
                        if policy == "retry":
                            deadline = time.perf_counter() + step["timeout_s"]
                            with self._lock:
                                self._message = f"{name} not found — retrying"
                            continue
                        with self._lock:
                            self._message = f"{name} not found — skipped"
                        break

                    remaining = cfg.interval - (time.perf_counter() - started)
                    if remaining > 0 and self._stop.wait(remaining):
                        return
                    if remaining <= 0:
                        time.sleep(0)
                else:
                    return
        finally:
            if capture is not None:
                try:
                    capture.close()
                except Exception:
                    pass


__all__ = [
    "MISS_POLICIES",
    "SEQUENCE_ACTIONS",
    "SequenceConfig",
    "SequenceRunner",
    "best_match",
    "normalize_steps",
    "step_summary",
]
