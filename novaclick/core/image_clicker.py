"""Screen-image targeting built on OpenCV template matching.

v2.2.0 remaster: a library of target images is scanned as a set, optionally
matching full colour instead of greyscale, with a one-shot probe so the user
can test a target without clicking, and a click limit for finite runs.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import wininput

IMAGE_IMPORT_ERROR: str | None = None
try:
    import cv2
    import mss
    import numpy as np
    IMAGE_DEPS = True
except Exception as exc:  # pragma: no cover - depends on installation
    cv2 = None
    mss = None
    np = None
    IMAGE_DEPS = False
    IMAGE_IMPORT_ERROR = str(exc)

# Formats offered in the file dialog and drag-and-drop. OpenCV handles the
# common raster formats; Qt's readers cover SVG, ICO, TIFF and friends.
SUPPORTED_IMAGE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".bmp", ".dib", ".webp",
    ".gif", ".tif", ".tiff", ".ico", ".svg", ".ppm", ".pgm", ".pbm",
    ".tga", ".jp2", ".j2k", ".avif",
)

IMAGE_FILE_FILTER = (
    "All supported images ("
    + " ".join(f"*{ext}" for ext in SUPPORTED_IMAGE_EXTENSIONS)
    + ");;PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp);;GIF (*.gif);;"
    "TIFF (*.tif *.tiff);;Bitmap (*.bmp);;Icon (*.ico);;SVG (*.svg);;"
    "All files (*.*)"
)


@dataclass(frozen=True)
class ImageConfig:
    image_paths: tuple[str, ...] = ()
    threshold: float = 0.85
    interval: float = 0.5
    offset_x: int = 0
    offset_y: int = 0
    one_shot: bool = False
    monitor: str = "all"  # all | primary
    button: str = "left"
    start_delay: float = 0.0
    grayscale: bool = False
    stop_after_clicks: int = 0  # 0 = unlimited

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(path for path in self.image_paths if path)


def _decode_with_qt(path: str, grayscale: bool):
    """Decode through Qt's image plugins when OpenCV cannot read the file.

    This is what makes SVG, ICO, TIFF and other Qt-only formats usable as
    templates. Returns a grayscale or BGR numpy array, or ``None``.
    """
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QImage, QImageReader
    except Exception:
        return None
    try:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull() and not reader.size().isValid():
            # Vector sources sometimes carry no intrinsic size; rasterise
            # them at a sane default so they can still be matched.
            reader.setScaledSize(QSize(512, 512))
            image = reader.read()
        if image.isNull():
            return None
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        width = image.width()
        height = image.height()
        if width <= 0 or height <= 0:
            return None
        stride = image.bytesPerLine()
        raw = bytes(image.constBits())
        if len(raw) < stride * height:
            return None
        array = np.frombuffer(raw[: stride * height], dtype=np.uint8)
        array = array.reshape(height, stride)[:, : width * 4].reshape(height, width, 4)
        code = cv2.COLOR_RGBA2GRAY if grayscale else cv2.COLOR_RGBA2BGR
        return cv2.cvtColor(array, code)
    except Exception:
        return None


def load_template(path: str, grayscale: bool = True):
    if not IMAGE_DEPS:
        raise RuntimeError(IMAGE_IMPORT_ERROR or "Image dependencies are missing.")
    flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
    image = None
    try:
        raw = np.fromfile(path, dtype=np.uint8)
    except Exception:
        raw = None
    if raw is not None and raw.size:
        image = cv2.imdecode(raw, flag)
    if image is None:
        # OpenCV could not decode it — fall back to Qt's readers so SVG,
        # TIFF, ICO and similar formats still work.
        image = _decode_with_qt(path, grayscale)
    if image is None:
        raise ValueError(
            "The selected file is not a readable image. Try PNG, JPG, WebP, "
            "GIF, TIFF, BMP, ICO or SVG."
        )
    if image.size == 0:
        raise ValueError("The selected image is empty.")
    if float(image.std()) < 0.5:
        raise ValueError("That image has almost no visual detail — choose a more distinct crop.")
    return image


def _select_monitor(monitors, which: str) -> dict:
    """Pick the bounded mss monitor dict for ``all`` or ``primary``."""
    if which == "primary" and len(monitors) > 1:
        return monitors[1]
    return monitors[0]


def _frame_from_shot(shot, grayscale: bool):
    """Convert an mss BGRA grab into a grayscale or BGR frame."""
    bgra = np.asarray(shot)
    code = cv2.COLOR_BGRA2GRAY if grayscale else cv2.COLOR_BGRA2BGR
    return cv2.cvtColor(bgra, code)


def match_best(frame, templates):
    """Return ``(score, (x, y), index, (width, height))`` for the best match.

    Templates of different sizes are each scanned over the whole frame and
    the highest confidence wins. Raises ``ValueError`` when no template can
    fit the frame at all.
    """
    best_score = -1.0
    best_location = (0, 0)
    best_index = 0
    best_size = (0, 0)
    frame_height, frame_width = frame.shape[:2]
    for index, template in enumerate(templates):
        height, width = template.shape[:2]
        if height > frame_height or width > frame_width:
            continue
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        if score > best_score:
            best_score = float(score)
            best_location = (int(location[0]), int(location[1]))
            best_index = index
            best_size = (int(width), int(height))
    if best_score < -0.5:
        raise ValueError("The reference image is larger than the selected screen.")
    return (
        max(0.0, min(1.0, best_score)),
        best_location,
        best_index,
        best_size,
    )


class ImageClicker:
    label = "Image targeting"

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._active = False
        self._config = ImageConfig()
        self._scans = 0
        self._matches = 0
        self._score = 0.0
        self._pos: tuple[int, int] | None = None
        self._matched = ""
        self._template_count = 0
        self._error: str | None = None
        self._started_at = 0.0

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active": self._active,
                "scans": self._scans,
                "matches": self._matches,
                "score": self._score,
                "pos": self._pos,
                "matched": self._matched,
                "templates": self._template_count,
                "error": self._error,
                "elapsed": time.perf_counter() - self._started_at if self._started_at else 0.0,
            }

    def start(self, config: ImageConfig) -> bool:
        if not IMAGE_DEPS:
            self._error = IMAGE_IMPORT_ERROR or "Image dependencies are missing."
            return False
        paths = config.paths
        if not paths:
            self._error = "Add at least one enabled target image first."
            return False
        for path in paths:
            if not Path(path).is_file():
                self._error = f"Target image missing: {Path(path).name}"
                return False
        with self._lock:
            if self._active:
                return False
            self._active = True
            self._config = config
            self._scans = 0
            self._matches = 0
            self._score = 0.0
            self._pos = None
            self._matched = ""
            self._template_count = len(paths)
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

    def probe(self, config: ImageConfig) -> dict:
        """Scan one frame and report the best match without clicking.

        Returns score, position, target index/name and whether the score
        clears the configured threshold.
        """
        if not IMAGE_DEPS:
            raise RuntimeError(IMAGE_IMPORT_ERROR or "Image dependencies are missing.")
        paths = config.paths
        if not paths:
            raise ValueError("Add at least one enabled target image first.")
        templates = []
        for path in paths:
            if not Path(path).is_file():
                raise ValueError(f"Target image missing: {Path(path).name}")
            try:
                templates.append(load_template(path, grayscale=config.grayscale))
            except Exception as exc:
                raise ValueError(f"{Path(path).name}: {exc}") from exc
        with mss.mss() as sct:
            monitor = _select_monitor(sct.monitors, config.monitor)
            shot = sct.grab(monitor)
        frame = _frame_from_shot(shot, config.grayscale)
        score, location, index, (width, height) = match_best(frame, templates)
        x = int(monitor["left"]) + location[0] + width // 2 + config.offset_x
        y = int(monitor["top"]) + location[1] + height // 2 + config.offset_y
        return {
            "score": score,
            "pos": (x, y),
            "index": index,
            "name": Path(paths[index]).name,
            "threshold": config.threshold,
            "found": score >= config.threshold,
            "templates": len(templates),
        }

    def _run_guarded(self) -> None:
        try:
            self._run()
        except Exception as exc:  # pragma: no cover - defensive
            with self._lock:
                self._error = f"Image engine fault: {exc}"
        finally:
            with self._lock:
                self._active = False
            self._stop.set()

    def _run(self) -> None:
        cfg = self._config
        paths = cfg.paths
        templates = []
        for path in paths:
            try:
                templates.append(load_template(path, grayscale=cfg.grayscale))
            except Exception as exc:
                raise ValueError(f"{Path(path).name}: {exc}") from exc

        clicks = 0
        with mss.mss() as sct:
            monitor = _select_monitor(sct.monitors, cfg.monitor)

            if cfg.start_delay > 0 and self._stop.wait(cfg.start_delay):
                return

            while not self._stop.is_set():
                started = time.perf_counter()
                shot = sct.grab(monitor)
                frame = _frame_from_shot(shot, cfg.grayscale)
                score, location, index, (width, height) = match_best(frame, templates)

                with self._lock:
                    self._scans += 1
                    self._score = score
                    self._template_count = len(templates)

                if score >= cfg.threshold:
                    x = int(monitor["left"]) + location[0] + width // 2 + cfg.offset_x
                    y = int(monitor["top"]) + location[1] + height // 2 + cfg.offset_y
                    clicks += 1
                    with self._lock:
                        self._matches += 1
                        self._pos = (x, y)
                        self._matched = Path(paths[index]).name
                    wininput.click(button=cfg.button, x=x, y=y)
                    if cfg.one_shot:
                        return
                    if cfg.stop_after_clicks > 0 and clicks >= cfg.stop_after_clicks:
                        return

                remaining = cfg.interval - (time.perf_counter() - started)
                if remaining > 0 and self._stop.wait(remaining):
                    return
                if remaining <= 0:
                    time.sleep(0)

    def probe_targets(self, config: ImageConfig) -> dict:
        """Backwards-friendly alias for :meth:`probe`."""
        return self.probe(config)


__all__ = [
    "ImageClicker",
    "ImageConfig",
    "IMAGE_DEPS",
    "IMAGE_IMPORT_ERROR",
    "IMAGE_FILE_FILTER",
    "SUPPORTED_IMAGE_EXTENSIONS",
    "load_template",
    "match_best",
]
