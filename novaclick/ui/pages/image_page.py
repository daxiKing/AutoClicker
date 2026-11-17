"""Image-targeted clicking page — v2.2.0 remaster."""

from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.image_clicker import (
    IMAGE_DEPS,
    IMAGE_FILE_FILTER,
    IMAGE_IMPORT_ERROR,
    SUPPORTED_IMAGE_EXTENSIONS,
    ImageClicker,
    ImageConfig,
    load_template,
)
from ...core.macros import format_clock
from ...core.paths import DATA_DIR
from ..theme import COLORS, FONT_MONO, FONT_UI
from ..widgets import (
    Card,
    EnergyLine,
    GlowPulse,
    HeroCard,
    PulseDot,
    SegmentedControl,
    StatTile,
    ThresholdBar,
    ToggleSwitch,
    hline,
    label,
    make_button,
)
from .base import Page


class ImageDrop(QWidget):
    files_dropped = Signal(list)
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(132)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self._pixmap: QPixmap | None = None
        self._path = ""
        self._drag = False

    def set_image(self, path: str) -> bool:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            # Qt could not preview it (rare); OpenCV may still decode it.
            try:
                array = load_template(path, grayscale=False)
            except Exception:
                return False
            height, width = array.shape[:2]
            rgb = array[:, :, ::-1].copy()
            image = QImage(
                rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888
            ).copy()
            pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return False
        self._pixmap = pixmap
        self._path = path
        self.update()
        return True

    def clear(self) -> None:
        self._pixmap = None
        self._path = ""
        self.update()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                suffix = Path(url.toLocalFile()).suffix.lower()
                if suffix in SUPPORTED_IMAGE_EXTENSIONS:
                    event.acceptProposedAction()
                    self._drag = True
                    self.update()
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._drag = False
        self.update()

    def dropEvent(self, event) -> None:
        self._drag = False
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if Path(url.toLocalFile()).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
        ]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        outer = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(outer, QColor("#c0c0c0"))
        painter.fillRect(outer.left(), outer.top(), outer.width(), 2, QColor("#404040"))
        painter.fillRect(outer.left(), outer.top(), 2, outer.height(), QColor("#404040"))
        painter.fillRect(outer.left(), outer.bottom() - 2, outer.width(), 2, QColor("#ffffff"))
        painter.fillRect(outer.right() - 2, outer.top(), 2, outer.height(), QColor("#ffffff"))

        rect = outer.adjusted(4, 4, -4, -4)
        painter.fillRect(rect, QColor("#ffffe1" if self._drag else "#ffffff"))
        if self._pixmap:
            # Classic checkerboard so transparent captures stay readable.
            tile = 10
            for ty in range(int(rect.top()), int(rect.bottom()), tile):
                for tx in range(int(rect.left()), int(rect.right()), tile):
                    if ((tx - int(rect.left())) // tile + (ty - int(rect.top())) // tile) % 2:
                        painter.fillRect(
                            QRectF(tx, ty, min(tile, rect.right() - tx), min(tile, rect.bottom() - ty)),
                            QColor("#e8e8e8"),
                        )
            target = rect.adjusted(8, 8, -8, -28)
            scaled = self._pixmap.scaled(
                target.size().toSize(),
                Qt.KeepAspectRatio,
                Qt.FastTransformation,
            )
            x = target.center().x() - scaled.width() / 2
            y = target.center().y() - scaled.height() / 2
            painter.drawPixmap(int(x), int(y), scaled)
            overlay = QRectF(rect.left(), rect.bottom() - 22, rect.width(), 22)
            painter.fillRect(overlay, QColor("#000080"))
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont(FONT_MONO, 8))
            painter.drawText(
                overlay.adjusted(8, 0, -8, 0),
                Qt.AlignVCenter | Qt.AlignLeft,
                f"{self._pixmap.width()} × {self._pixmap.height()} px",
            )
        else:
            painter.setPen(QPen(QColor("#808080"), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(7, 7, -7, -7))
            painter.setPen(QColor("#404040"))
            painter.setFont(QFont(FONT_MONO, 9))
            painter.drawText(
                rect,
                Qt.AlignCenter,
                "Drop one or more images here\nPNG · JPG · WebP · GIF · TIFF · BMP · SVG · ICO\nor click to browse · or Paste from clipboard",
            )
        if self._drag:
            painter.setPen(QPen(QColor("#000080"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(outer.adjusted(2, 2, -2, -2))


class ImageRadar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(156)
        self._active = False
        self._phase = 0.0
        self._score = 0.0
        self._threshold = 0.85
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def set_active(self, active: bool) -> None:
        self._active = active
        if active and not self._timer.isActive():
            self._timer.start()
        elif not active:
            self._timer.stop()
        self.update()

    def set_state(self, score: float, threshold: float) -> None:
        self._score = max(0.0, min(1.0, score))
        self._threshold = max(0.0, min(1.0, threshold))
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.035) % (math.pi * 2)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        center = QPointF(self.width() / 2, self.height() / 2)
        max_radius = min(self.width(), self.height()) * 0.38

        painter.setPen(QPen(QColor("#c0c0c0"), 1, Qt.DotLine))
        painter.setBrush(Qt.NoBrush)
        for fraction in (0.45, 0.72, 1.0):
            radius = max_radius * fraction
            painter.drawEllipse(center, radius, radius)
        painter.setPen(QPen(QColor("#808080"), 1, Qt.DashLine))
        painter.drawLine(
            QPointF(center.x() - max_radius, center.y()),
            QPointF(center.x() + max_radius, center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - max_radius),
            QPointF(center.x(), center.y() + max_radius),
        )

        if self._active:
            # Chunky sweeping arc drawn as consecutive segments.
            for step in range(9):
                angle = self._phase + step * 0.075
                x = center.x() + math.cos(angle) * max_radius * 0.86
                y = center.y() + math.sin(angle) * max_radius * 0.86
                shade = QColor("#000080")
                shade.setAlpha(190 - step * 18)
                painter.fillRect(QRectF(x - 2, y - 2, 5, 5), shade)

        found = self._score >= self._threshold
        color = QColor("#008000") if found else QColor("#404040")
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(center.x() - 11, center.y() - 11, 22, 22))
        painter.drawLine(QPointF(center.x() - 22, center.y()), QPointF(center.x() - 8, center.y()))
        painter.drawLine(QPointF(center.x() + 8, center.y()), QPointF(center.x() + 22, center.y()))
        painter.drawLine(QPointF(center.x(), center.y() - 22), QPointF(center.x(), center.y() - 8))
        painter.drawLine(QPointF(center.x(), center.y() + 8), QPointF(center.x(), center.y() + 22))
        if found:
            painter.fillRect(QRectF(center.x() - 2, center.y() - 2, 5, 5), QColor("#008000"))
        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(QFont(FONT_MONO, 7))
        text = "TARGET LOCKED" if found else ("SCANNING" if self._active else "STANDBY")
        painter.drawText(QRectF(0, self.height() - 21, self.width(), 14), Qt.AlignCenter, text)


class ImagePage(Page):
    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self.engine = ImageClicker()
        self._active_ui = False
        self._manual_stop = False
        self._path = ""
        self._targets: list[dict] = []
        self._last_error = None
        self._last_match_count = 0
        self._started_at = 0.0
        self._last_score = 0.0

        self._build_hero()
        columns = QHBoxLayout()
        columns.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(self._build_library_card())
        left.addWidget(self._build_settings_card())
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self._build_telemetry_card())
        right.addWidget(self._build_tips_card())
        right.addStretch(1)
        columns.addLayout(left, 5)
        columns.addLayout(right, 4)
        self.layout.addLayout(columns)

        if not IMAGE_DEPS:
            self.main.log("error", f"Image targeting unavailable: {IMAGE_IMPORT_ERROR}")
            self.main.toast("error", "Image targeting dependencies are missing.")
            self.start_btn.setEnabled(False)
            self.browse_btn.setEnabled(False)
            self.paste_btn.setEnabled(False)
            self.test_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)

        self._timer = QTimer(self)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._load_targets()
        self._update_summary()

    # ------------------------------------------------------------------
    def _build_hero(self) -> None:
        hero = HeroCard()
        outer = QVBoxLayout(hero)
        outer.setContentsMargins(22, 17, 22, 14)
        outer.setSpacing(10)
        row = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(4)
        eyebrow = QHBoxLayout()
        eyebrow.setSpacing(4)
        self.hero_dot = PulseDot(COLORS["faint"], 8)
        eyebrow.addWidget(self.hero_dot)
        eyebrow.addWidget(label("VISUAL TARGETING MK II", "Eyebrow"))
        eyebrow.addStretch(1)
        left.addLayout(eyebrow)
        self.hero_status = label("Vision engine standby", "HeroTitle")
        left.addWidget(self.hero_status)
        self.hero_sub = label("Add target images to begin.", "HeroSub")
        left.addWidget(self.hero_sub)
        row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(5)
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.start_btn = make_button("Start scanning", "StartButton")
        self.start_btn.setMinimumWidth(190)
        self.start_btn.setMinimumHeight(54)
        self.start_btn.setToolTip("Toggle image scanning and clicking")
        self.start_btn.clicked.connect(self.toggle)
        self._glow = GlowPulse(self.start_btn)
        right.addWidget(self.start_btn, 0, Qt.AlignRight)
        note = label("Multi-target template matching · local only", "Tiny")
        note.setAlignment(Qt.AlignRight)
        right.addWidget(note)
        row.addLayout(right)
        outer.addLayout(row)
        self.energy = EnergyLine()
        outer.addWidget(self.energy)
        self.layout.addWidget(hero)

    def _build_library_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Target library", "CardTitle"))
        header.addStretch(1)
        self.res_badge = label("NO TARGETS", "VersionBadge")
        header.addWidget(self.res_badge)
        card.body.addLayout(header)

        self.preview = ImageDrop()
        self.preview.files_dropped.connect(self._add_paths)
        self.preview.clicked.connect(self._browse_images)
        card.body.addWidget(self.preview)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.browse_btn = make_button("Add images", "GhostButton")
        self.browse_btn.setToolTip("Add one or more images: PNG, JPG, WebP, GIF, TIFF, BMP, ICO, SVG")
        self.browse_btn.clicked.connect(self._browse_images)
        action_row.addWidget(self.browse_btn)
        self.paste_btn = make_button("Paste", "GhostButton")
        self.paste_btn.setToolTip("Paste an image from the clipboard and add it to the library")
        self.paste_btn.clicked.connect(self._paste_image)
        action_row.addWidget(self.paste_btn)
        self.test_btn = make_button("Test match", "GhostButton")
        self.test_btn.setToolTip("Scan once and report the best target without clicking")
        self.test_btn.clicked.connect(self._test_match)
        action_row.addWidget(self.test_btn)
        action_row.addStretch(1)
        self.remove_btn = make_button("Remove", "GhostButton")
        self.remove_btn.setToolTip("Remove the selected target from the library (file stays on disk)")
        self.remove_btn.clicked.connect(self._remove_selected)
        action_row.addWidget(self.remove_btn)
        card.body.addLayout(action_row)

        self.target_list = QListWidget()
        self.target_list.setFixedHeight(112)
        self.target_list.setToolTip(
            "Check a target to include it in scans; click one to preview"
        )
        self.target_list.itemChanged.connect(self._on_target_item_changed)
        self.target_list.currentItemChanged.connect(lambda cur, prev: self._preview_current())
        card.body.addWidget(self.target_list)

        self.path_label = label("No targets yet — add an image or paste one.", "Tiny")
        self.path_label.setStyleSheet("color: #404040;")
        card.body.addWidget(self.path_label)
        card.body.addWidget(hline())

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(label("Match confidence", "SectionTitle"))
        threshold_row.addStretch(1)
        self.threshold_label = label("85%", "Value")
        self.threshold_label.setStyleSheet("font-family: 'Courier New'; font-size: 14px; color: #000080;")
        threshold_row.addWidget(self.threshold_label)
        card.body.addLayout(threshold_row)
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(50, 99)
        self.confidence_slider.setValue(85)
        self.confidence_slider.setPageStep(5)
        self.confidence_slider.valueChanged.connect(self._on_threshold_changed)
        card.body.addWidget(self.confidence_slider)
        hint = label(
            "The best-scoring target wins each scan. A tight crop with sharp edges "
            "improves matching; Win + Shift + S is perfect for grabbing a target.",
            "Tiny",
            wrap=True,
        )
        card.body.addWidget(hint)
        return card

    def _build_settings_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Scan settings", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("TEMPO + ACTION", "Tiny"))
        card.body.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(3, 1)
        grid.addWidget(label("Scan interval", "SectionTitle"), 0, 0)
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.1, 10.0)
        self.interval_spin.setSingleStep(0.1)
        self.interval_spin.setDecimals(1)
        self.interval_spin.setValue(0.5)
        self.interval_spin.setSuffix(" s")
        self.interval_spin.setFixedWidth(90)
        self.interval_spin.valueChanged.connect(lambda _v: self._update_summary())
        grid.addWidget(self.interval_spin, 0, 1)
        grid.addWidget(label("Minimum time between screen scans", "Tiny"), 0, 2, 1, 3)

        grid.addWidget(label("Monitor", "SectionTitle"), 1, 0)
        self.monitor_combo = QComboBox()
        self.monitor_combo.addItems(["Entire desktop", "Primary monitor"])
        self.monitor_combo.setFixedWidth(164)
        self.monitor_combo.currentIndexChanged.connect(lambda _i: self._update_summary())
        grid.addWidget(self.monitor_combo, 1, 1)
        grid.addWidget(label("All screens are captured locally", "Tiny"), 1, 2, 1, 3)

        grid.addWidget(label("Click offset", "SectionTitle"), 2, 0)
        offset_row = QHBoxLayout()
        offset_row.setSpacing(6)
        self.offset_x = QSpinBox()
        self.offset_x.setRange(-2000, 2000)
        self.offset_x.setPrefix("X ")
        self.offset_x.setFixedWidth(86)
        self.offset_y = QSpinBox()
        self.offset_y.setRange(-2000, 2000)
        self.offset_y.setPrefix("Y ")
        self.offset_y.setFixedWidth(86)
        offset_row.addWidget(self.offset_x)
        offset_row.addWidget(self.offset_y)
        offset_row.addStretch(1)
        grid.addLayout(offset_row, 2, 1, 1, 4)

        grid.addWidget(label("Mouse button", "SectionTitle"), 3, 0)
        self.button_segment = SegmentedControl(
            [("left", "Left"), ("right", "Right"), ("middle", "Middle")]
        )
        self.button_segment.changed.connect(lambda _key: self._update_summary())
        grid.addWidget(self.button_segment, 3, 1, 1, 4)
        card.body.addLayout(grid)
        card.body.addWidget(hline())

        color_row = QHBoxLayout()
        color_text = QVBoxLayout()
        color_text.setSpacing(2)
        color_text.addWidget(label("Match exact colors", "SectionTitle"))
        color_text.addWidget(
            label("Off = grayscale matching: faster and tolerant of recolors", "Tiny")
        )
        color_row.addLayout(color_text, 1)
        self.color_toggle = ToggleSwitch(True)
        self.color_toggle.setToolTip("Compare full color instead of brightness only")
        self.color_toggle.toggled.connect(lambda _checked: self._update_summary())
        color_row.addWidget(self.color_toggle)
        card.body.addLayout(color_row)

        stop_row = QHBoxLayout()
        stop_text = QVBoxLayout()
        stop_text.setSpacing(2)
        stop_text.addWidget(label("Stop after", "SectionTitle"))
        stop_text.addWidget(label("End the scan after a number of clicks; 0 = unlimited", "Tiny"))
        stop_row.addLayout(stop_text, 1)
        self.stop_clicks_spin = QSpinBox()
        self.stop_clicks_spin.setRange(0, 999999)
        self.stop_clicks_spin.setSuffix(" clicks")
        self.stop_clicks_spin.setValue(0)
        self.stop_clicks_spin.setFixedWidth(120)
        self.stop_clicks_spin.setToolTip("0 = scan until stopped manually")
        self.stop_clicks_spin.valueChanged.connect(lambda _v: self._update_summary())
        stop_row.addWidget(self.stop_clicks_spin)
        card.body.addLayout(stop_row)

        one_shot_row = QHBoxLayout()
        one_shot_text = QVBoxLayout()
        one_shot_text.setSpacing(2)
        one_shot_text.addWidget(label("Click once, then stop", "SectionTitle"))
        one_shot_text.addWidget(label("Useful for one-shot targets and confirmations", "Tiny"))
        one_shot_row.addLayout(one_shot_text, 1)
        self.oneshot_toggle = ToggleSwitch(False)
        one_shot_row.addWidget(self.oneshot_toggle)
        card.body.addLayout(one_shot_row)
        return card

    def _build_telemetry_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Vision telemetry", "CardTitle"))
        header.addStretch(1)
        self.telemetry_badge = label("IDLE", "VersionBadge")
        self.telemetry_badge.setStyleSheet(
            "background: #c0c0c0; border: 2px solid; border-top-color: #ffffff; "
            "border-left-color: #ffffff; border-right-color: #404040; "
            "border-bottom-color: #404040; color: #404040; "
            "padding: 3px 7px; font-size: 9px; font-weight: 700;"
        )
        header.addWidget(self.telemetry_badge)
        card.body.addLayout(header)

        self.radar = ImageRadar()
        card.body.addWidget(self.radar)

        score_header = QHBoxLayout()
        score_header.addWidget(label("BEST MATCH", "Tiny"))
        score_header.addStretch(1)
        self.score_label = label("0.0%", "Value")
        self.score_label.setStyleSheet("font-family: 'Courier New'; font-size: 18px; color: #404040;")
        score_header.addWidget(self.score_label)
        card.body.addLayout(score_header)
        self.score_bar = ThresholdBar()
        self.score_bar.set_threshold(0.85)
        card.body.addWidget(self.score_bar)

        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        self.scans_tile = StatTile("Scans", "0")
        self.matches_tile = StatTile("Clicked", "0")
        self.time_tile = StatTile("Session", "00:00")
        tiles.addWidget(self.scans_tile)
        tiles.addWidget(self.matches_tile)
        tiles.addWidget(self.time_tile)
        card.body.addLayout(tiles)

        pos_row = QHBoxLayout()
        pos_row.addWidget(label("Last match", "Tiny"))
        pos_row.addStretch(1)
        self.pos_label = label("—", "Muted")
        self.pos_label.setStyleSheet("font-family: 'Courier New'; font-size: 10px; color: #404040;")
        pos_row.addWidget(self.pos_label)
        card.body.addLayout(pos_row)

        matched_row = QHBoxLayout()
        matched_row.addWidget(label("Matched target", "Tiny"))
        matched_row.addStretch(1)
        self.matched_label = label("—", "Muted")
        self.matched_label.setStyleSheet("font-family: 'Courier New'; font-size: 10px; color: #404040;")
        matched_row.addWidget(self.matched_label)
        card.body.addLayout(matched_row)
        return card

    def _build_tips_card(self) -> Card:
        card = Card()
        card.body.addWidget(label("Field notes", "CardTitle"))
        for title, text in (
            ("LIBRARY", "Add several crops of the same target; the best score wins each scan."),
            ("TIGHT CROP", "Capture only the unique part of the target, not its background."),
            ("COLORS", "Exact color is stricter; turn it off when themes or lighting shift."),
            ("ONE SHOT", "Enable it for buttons that move or disappear after clicking."),
        ):
            row = QHBoxLayout()
            row.setSpacing(9)
            badge = label(title, "VersionBadge")
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedWidth(72)
            row.addWidget(badge, 0, Qt.AlignTop)
            row.addWidget(label(text, "Muted", wrap=True), 1)
            card.body.addLayout(row)
        return card

    # ------------------------------------------------------------------
    # Target library
    # ------------------------------------------------------------------
    def _load_targets(self) -> None:
        raw = self.main.settings.get("image_targets", [])
        targets: list[dict] = []
        missing = 0
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, str):
                    path, enabled = entry, True
                elif isinstance(entry, dict):
                    path = str(entry.get("path", ""))
                    enabled = bool(entry.get("enabled", True))
                else:
                    continue
                if not path:
                    continue
                if not Path(path).is_file():
                    missing += 1
                    continue
                targets.append({"path": path, "enabled": enabled})
        self._targets = targets
        self._refresh_target_list()
        if missing:
            self.main.log("info", f"{missing} saved target image(s) were missing and skipped.")

    def _save_targets(self) -> None:
        self.main.settings.set("image_targets", self._targets)

    def _enabled_paths(self) -> list[str]:
        return [
            target["path"]
            for target in self._targets
            if target.get("enabled", True) and Path(target["path"]).is_file()
        ]

    def _current_target_path(self) -> str:
        if not hasattr(self, "target_list"):
            return ""
        item = self.target_list.currentItem()
        return str(item.data(Qt.UserRole)) if item is not None else ""

    def _refresh_target_list(self, select: str | None = None) -> None:
        if not hasattr(self, "target_list"):
            return
        current = select or self._current_target_path()
        self.target_list.blockSignals(True)
        self.target_list.clear()
        for target in self._targets:
            path = str(target["path"])
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if target.get("enabled", True) else Qt.Unchecked
            )
            if not Path(path).is_file():
                item.setText(f"{Path(path).name} (missing)")
                item.setForeground(QColor("#804000"))
            self.target_list.addItem(item)
        selected_row = -1
        for row in range(self.target_list.count()):
            if self.target_list.item(row).data(Qt.UserRole) == current:
                selected_row = row
                break
        if selected_row < 0 and self.target_list.count():
            selected_row = 0
        if selected_row >= 0:
            self.target_list.setCurrentRow(selected_row)
        self.target_list.blockSignals(False)
        self._preview_current()
        self._update_summary()

    def _on_target_item_changed(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if not path:
            return
        for target in self._targets:
            if target["path"] == path:
                target["enabled"] = item.checkState() == Qt.Checked
                break
        self._save_targets()
        self._update_summary()

    def _preview_current(self) -> None:
        path = self._current_target_path()
        self._path = path
        if not path:
            self.preview.clear()
            self.path_label.setText(
                "No targets yet — add an image or paste one."
                if not self._targets
                else "Select a target to preview."
            )
            self.path_label.setToolTip("")
            return
        if not self.preview.set_image(path):
            self.preview.clear()
            self.path_label.setText(f"{Path(path).name} — cannot preview")
            self.path_label.setToolTip(path)
            return
        meta = ""
        try:
            reader = QImageReader(path)
            size = reader.size()
            if size.isValid():
                meta = f"  ·  {size.width()} × {size.height()}"
        except Exception:
            pass
        self.path_label.setText(f"{Path(path).name}{meta}")
        self.path_label.setToolTip(path)

    def _browse_images(self) -> None:
        if not IMAGE_DEPS:
            return
        if self.engine.is_active:
            self.main.toast("warning", "Stop scanning before changing the target library.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add target images",
            "",
            IMAGE_FILE_FILTER,
        )
        if paths:
            self._add_paths(paths)

    def _add_paths(self, paths: list[str], select: str | None = None) -> None:
        if not IMAGE_DEPS:
            return
        if self.engine.is_active:
            self.main.toast("warning", "Stop scanning before changing the target library.")
            return
        added: list[str] = []
        skipped: list[str] = []
        for raw in paths:
            path = str(Path(raw))
            if any(target["path"] == path for target in self._targets):
                skipped.append(f"{Path(path).name} (already in library)")
                continue
            if not Path(path).is_file():
                skipped.append(f"{Path(path).name} (missing)")
                continue
            try:
                load_template(path, grayscale=False)
            except Exception:
                skipped.append(f"{Path(path).name} (unreadable)")
                continue
            self._targets.append({"path": path, "enabled": True})
            added.append(path)
        if added:
            self._save_targets()
            self._refresh_target_list(select=select or added[0])
            self.main.log("info", f"Added {len(added)} target image(s) to the library.")
            self.main.toast("success", f"Added {len(added)} target image(s).")
        if skipped:
            more = "…" if len(skipped) > 3 else ""
            self.main.toast("warning", "Skipped: " + ", ".join(skipped[:3]) + more)

    def _paste_image(self) -> None:
        """Save the clipboard image as a PNG target and add it to the library."""
        if not IMAGE_DEPS:
            return
        if self.engine.is_active:
            self.main.toast("warning", "Stop scanning before changing the target library.")
            return
        image = QApplication.clipboard().image()
        if image is None or image.isNull():
            self.main.toast(
                "warning",
                "The clipboard has no image. Copy one first — Win + Shift + S is perfect.",
            )
            return
        folder = DATA_DIR / "targets"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.main.toast("error", f"Could not create the targets folder: {exc}")
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = folder / f"paste-{stamp}.png"
        counter = 2
        while path.exists():
            path = folder / f"paste-{stamp}-{counter}.png"
            counter += 1
        if not image.save(str(path), "PNG"):
            self.main.toast("error", "The clipboard image could not be saved.")
            return
        self.main.log("info", f"Clipboard image saved as a target — {path.name}.")
        self._add_paths([str(path)], select=str(path))

    def _remove_selected(self) -> None:
        if self.engine.is_active:
            self.main.toast("warning", "Stop scanning before changing the target library.")
            return
        path = self._current_target_path()
        if not path:
            self.main.toast("warning", "Select a target to remove first.")
            return
        self._targets = [target for target in self._targets if target["path"] != path]
        self._save_targets()
        self._refresh_target_list()
        self.main.log("info", f"Removed target {Path(path).name} from the library.")
        self.main.toast("info", "Target removed from the library; the file was kept.")

    def _test_match(self) -> None:
        if not IMAGE_DEPS:
            return
        if self.engine.is_active:
            self.main.toast("warning", "Stop scanning before testing a match.")
            return
        if not self._enabled_paths():
            self.main.toast("warning", "Add or enable at least one target image first.")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            result = self.engine.probe(self.config())
        except Exception as exc:
            self.main.toast("error", str(exc))
            self.main.log("error", f"Test match failed — {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.test_btn.setText("Test match")
            self.test_btn.setEnabled(not self.engine.is_active)
        score = float(result["score"])
        threshold = self._threshold_value()
        self._last_score = score
        self.score_label.setText(f"{score * 100:.1f}%")
        color = "#008000" if score >= threshold else "#808000" if score > max(0.55, threshold - 0.2) else "#404040"
        self.score_label.setStyleSheet(
            f"font-family: 'Courier New'; font-size: 18px; color: {color};"
        )
        self.score_bar.set_value(score)
        self.radar.set_state(score, threshold)
        self.pos_label.setText(f"{result['pos'][0]:,} {result['pos'][1]:,}")
        self.matched_label.setText(str(result["name"]))
        if result["found"]:
            self.main.log("success", f"Test match — {result['name']} at {score * 100:.1f}%.")
            self.main.toast("success", f"{result['name']} matched at {score * 100:.1f}%.")
        else:
            self.main.log(
                "info",
                f"Test match — best was {result['name']} at {score * 100:.1f}% "
                f"(below {threshold * 100:.0f}%).",
            )
            self.main.toast(
                "warning",
                f"Best match {score * 100:.1f}% — below the {threshold * 100:.0f}% threshold.",
            )

    # ------------------------------------------------------------------
    def _update_summary(self) -> None:
        if not hasattr(self, "hero_sub"):
            return
        total = len(self._targets)
        enabled = len(self._enabled_paths())
        if hasattr(self, "res_badge"):
            if total == 0:
                self.res_badge.setText("NO TARGETS")
            else:
                self.res_badge.setText(f"{total} TARGET{'S' if total != 1 else ''}")
        if not hasattr(self, "color_toggle") or not hasattr(self, "monitor_combo"):
            return
        threshold = self._threshold_value()
        mode = "all monitors" if self.monitor_combo.currentIndex() == 0 else "primary monitor"
        color = "exact color" if self.color_toggle.isChecked() else "grayscale"
        if enabled:
            targets = f"{enabled} of {total} target{'s' if total != 1 else ''} armed"
            self.hero_sub.setText(
                f"{targets}  ·  {threshold * 100:.0f}% confidence  ·  {color}  ·  scanning {mode}"
            )
        else:
            self.hero_sub.setText("Add or enable a target image to begin.")

    def _threshold_value(self) -> float:
        return self.confidence_slider.value() / 100.0

    def _on_threshold_changed(self, value: int) -> None:
        self.threshold_label.setText(f"{value}%")
        self.score_bar.set_threshold(value / 100.0)
        self.radar.set_state(self._last_score, value / 100.0)
        self._update_summary()

    # ------------------------------------------------------------------
    def config(self) -> ImageConfig:
        return ImageConfig(
            image_paths=tuple(self._enabled_paths()),
            threshold=self._threshold_value(),
            interval=self.interval_spin.value(),
            offset_x=self.offset_x.value(),
            offset_y=self.offset_y.value(),
            one_shot=self.oneshot_toggle.isChecked(),
            monitor="all" if self.monitor_combo.currentIndex() == 0 else "primary",
            button=self.button_segment.current_key(),
            start_delay=self.main.start_delay_s(),
            grayscale=not self.color_toggle.isChecked(),
            stop_after_clicks=self.stop_clicks_spin.value(),
        )

    def toggle(self) -> None:
        if self.engine.is_active:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.engine.is_active:
            return
        if not IMAGE_DEPS:
            self.main.toast("error", f"Image dependencies missing: {IMAGE_IMPORT_ERROR}")
            return
        paths = self._enabled_paths()
        if not paths:
            self.main.toast("warning", "Add or enable at least one target image first.")
            return
        cfg = self.config()
        self.main.acquire("image")
        if not self.engine.start(cfg):
            self.main.release("image")
            error = self.engine.snapshot().get("error") or "Image engine could not start."
            self.main.toast("error", error)
            return
        self._active_ui = True
        self._manual_stop = False
        self._last_error = None
        self._last_match_count = 0
        self._started_at = time.perf_counter()
        self._last_score = 0.0
        self.score_label.setText("0.0%")
        self.score_label.setStyleSheet("font-family: 'Courier New'; font-size: 18px; color: #404040;")
        self.score_bar.set_value(0)
        self.scans_tile.set_value("0")
        self.matches_tile.set_value("0")
        self.time_tile.set_value("00:00")
        self.pos_label.setText("—")
        self.matched_label.setText("—")
        self._set_running_ui(True)
        self.main.log("hotkey", f"Image targeting engaged — {len(paths)} target(s).")
        self.main.toast("success", "Image targeting engaged.")

    def stop(self, quiet: bool = False) -> None:
        if not self.engine.is_active and not self._active_ui:
            return
        self._manual_stop = True
        self.engine.stop()
        snapshot = self.engine.snapshot()
        self._active_ui = False
        self._set_running_ui(False)
        self._apply_snapshot(snapshot)
        self.main.release("image")
        if not quiet:
            self.main.log("info", f"Image targeting stopped — {snapshot.get('matches', 0)} click(s).")
            self.main.toast("info", f"Image targeting stopped — {snapshot.get('matches', 0)} click(s)")

    def force_stop(self) -> bool:
        if self.engine.is_active or self._active_ui:
            self.stop(quiet=True)
            return True
        return False

    def _set_running_ui(self, running: bool) -> None:
        self.start_btn.setText("Stop scanning" if running else "Start scanning")
        self.start_btn.setProperty("running", running)
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)
        if running:
            self._glow.start()
        else:
            self._glow.stop()
        self.energy.set_running(running)
        self.hero_dot.set_state(running, COLORS["cyan"])
        self.radar.set_active(running)
        self.telemetry_badge.setText("LIVE" if running else "IDLE")
        if running:
            self.telemetry_badge.setStyleSheet(
                "background: #ffffe1; border: 1px solid #000000; "
                "color: #008000; padding: 3px 7px; font-size: 9px; font-weight: 700;"
            )
            self.hero_status.setText("Searching the screen")
            for widget in (
                self.browse_btn,
                self.paste_btn,
                self.test_btn,
                self.remove_btn,
                self.target_list,
            ):
                widget.setEnabled(False)
        else:
            self.telemetry_badge.setStyleSheet(
                "background: #c0c0c0; border: 2px solid; border-top-color: #ffffff; "
                "border-left-color: #ffffff; border-right-color: #404040; "
                "border-bottom-color: #404040; color: #404040; "
                "padding: 3px 7px; font-size: 9px; font-weight: 700;"
            )
            self.hero_status.setText("Vision engine standby")
            for widget in (
                self.browse_btn,
                self.paste_btn,
                self.test_btn,
                self.remove_btn,
                self.target_list,
            ):
                widget.setEnabled(bool(IMAGE_DEPS))
        self._update_summary()

    def _apply_snapshot(self, snapshot: dict) -> None:
        score = float(snapshot.get("score", 0.0))
        matches = int(snapshot.get("matches", 0))
        scans = int(snapshot.get("scans", 0))
        threshold = self._threshold_value()
        self._last_score = score
        self.score_label.setText(f"{score * 100:.1f}%")
        color = "#008000" if score >= threshold else "#808000" if score > max(0.55, threshold - 0.2) else "#404040"
        self.score_label.setStyleSheet(
            f"font-family: 'Courier New'; font-size: 18px; color: {color};"
        )
        self.score_bar.set_value(score)
        self.radar.set_state(score, threshold)
        self.scans_tile.set_value(f"{scans:,}")
        self.matches_tile.set_value(f"{matches:,}")
        self.time_tile.set_value(format_clock(snapshot.get("elapsed", 0)))
        pos = snapshot.get("pos")
        self.pos_label.setText(f"{pos[0]:,} {pos[1]:,}" if pos else "—")
        self.matched_label.setText(str(snapshot.get("matched") or "—"))
        self.hero_sub.setText(f"Best match {score * 100:.1f}%  ·  {scans:,} scans  ·  {matches:,} clicks")

    def _tick(self) -> None:
        snapshot = self.engine.snapshot()
        error = snapshot.get("error")
        if error and error != self._last_error:
            self._last_error = error
            self.main.toast("error", error)
            self.main.log("error", error)
            self.stop(quiet=True)
            return
        if snapshot.get("active"):
            self._apply_snapshot(snapshot)
        elif self._active_ui and not self.engine.is_active:
            self._active_ui = False
            matches = int(snapshot.get("matches", 0))
            self._apply_snapshot(snapshot)
            self._set_running_ui(False)
            self.main.release("image")
            if not self._manual_stop and matches > 0:
                self.main.log("success", "Image target found and clicked. One-shot scan complete.")
                self.main.toast("success", "Target found and clicked.")
            elif not self._manual_stop:
                self.main.log("info", "Image scan ended.")
