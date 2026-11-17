"""Custom painted widgets, cards, toasts and icons for AutoClicker."""

from __future__ import annotations

import math
from collections import deque

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import COLORS, FONT_MONO, FONT_UI


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def pointer(widget: QWidget) -> QWidget:
    widget.setCursor(Qt.PointingHandCursor)
    return widget


def label(
    text: str = "",
    object_name: str | None = None,
    parent: QWidget | None = None,
    wrap: bool = False,
) -> QLabel:
    widget = QLabel(text, parent)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(wrap)
    return widget


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("HLine")
    line.setFixedHeight(1)
    return line


def make_button(text: str, kind: str = "GhostButton", cursor: bool = True) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(kind)
    if cursor:
        button.setCursor(Qt.PointingHandCursor)
    return button


def add_glow(widget: QWidget, color: str = COLORS["accent"], blur: int = 0, offset: int = 0) -> None:
    """No-op kept for API compatibility — retro UI has no drop-shadow glows."""
    return None


def shade(color: str, alpha: int) -> QColor:
    value = QColor(color)
    value.setAlpha(alpha)
    return value


# ---------------------------------------------------------------------------
# Brand / logo
# ---------------------------------------------------------------------------

def _paint_logo(painter: QPainter, rect: QRectF, glow: float = 0.0) -> None:
    """Paint the AutoClicker mark: a chunky cursor arrow firing click sparks."""
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.save()

    # Outer black frame, raised silver bezel and a sunken navy "screen".
    painter.fillRect(rect, QColor("#000000"))
    bezel = rect.adjusted(1, 1, -1, -1)
    painter.fillRect(bezel, QColor("#c0c0c0"))
    painter.fillRect(bezel.left(), bezel.top(), bezel.width(), 2, QColor("#ffffff"))
    painter.fillRect(bezel.left(), bezel.top(), 2, bezel.height(), QColor("#ffffff"))
    painter.fillRect(bezel.left(), bezel.bottom() - 2, bezel.width(), 2, QColor("#404040"))
    painter.fillRect(bezel.right() - 2, bezel.top(), 2, bezel.height(), QColor("#404040"))

    screen = bezel.adjusted(4, 4, -4, -4)
    painter.fillRect(screen, QColor("#000080"))

    # A 1px highlight line across the top of the navy face.
    painter.fillRect(screen.left(), screen.top(), screen.width(), 1, QColor("#4040c0"))

    sw = screen.width()
    sh = screen.height()

    # Classic arrow cursor, tip upper-left, drawn as a hard polygon.
    tip_x = screen.left() + 0.30 * sw
    tip_y = screen.top() + 0.24 * sh
    box_w = 0.44 * sw
    box_h = 0.64 * sh
    points = [
        (0.00, 0.00),
        (0.00, 0.84),
        (0.35, 0.66),
        (0.58, 1.00),
        (0.81, 0.92),
        (0.58, 0.61),
        (1.00, 0.61),
    ]
    arrow = QPainterPath()
    arrow.moveTo(tip_x + points[0][0] * box_w, tip_y + points[0][1] * box_h)
    for px, py in points[1:]:
        arrow.lineTo(tip_x + px * box_w, tip_y + py * box_h)
    arrow.closeSubpath()
    painter.setPen(QPen(QColor("#000000"), 1))
    painter.setBrush(QColor("#ffffff"))
    painter.drawPath(arrow)

    # Click sparks radiating up and left from the tip.
    s = max(2.0, sw * 0.055)
    brightness = max(0.0, min(1.0, glow))
    spark_color = QColor("#ffff00")
    if brightness > 0.75:
        spark_color = QColor("#ffffff")
    painter.setPen(QPen(spark_color, max(2, int(s * 0.9))))
    painter.drawLine(
        QPointF(tip_x, tip_y - s * 2.2),
        QPointF(tip_x, tip_y - s * 0.9),
    )
    painter.drawLine(
        QPointF(tip_x - s * 2.2, tip_y),
        QPointF(tip_x - s * 0.9, tip_y),
    )
    painter.drawLine(
        QPointF(tip_x - s * 1.8, tip_y - s * 1.8),
        QPointF(tip_x - s * 1.05, tip_y - s * 1.05),
    )

    # Pixel sparkle in the corner gives the mark some life without a modern glow.
    if brightness > 0.58:
        spark = max(2, int(sw * 0.06))
        painter.fillRect(screen.right() - spark * 2, screen.top() + spark, spark, spark, QColor("#ffffff"))
        painter.fillRect(screen.right() - spark * 2 - spark, screen.top() + spark * 2, spark, spark, QColor("#ffff00"))
    painter.restore()


class LogoMark(QWidget):
    def __init__(self, size: int = 38, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._glow = 0.0

    def set_glow(self, value: float) -> None:
        self._glow = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        inset = self.width() * 0.08
        _paint_logo(painter, QRectF(inset, inset, self.width() - inset * 2, self.height() - inset * 2), self._glow)


def make_app_icon(size: int = 256) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    _paint_logo(painter, QRectF(10, 10, size - 20, size - 20))
    painter.end()
    return QIcon(pixmap)


# ---------------------------------------------------------------------------
# Navigation icons
# ---------------------------------------------------------------------------

def _icon_pixmap(kind: str, color: str, size: int = 40) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    scale = size / 20.0
    pen = QPen(QColor(color), 1.55 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.scale(scale, scale)
    center = QPointF(10, 10)

    if kind == "click":
        body = QRectF(5.0, 2.2, 10.0, 15.6)
        painter.drawRoundedRect(body, 4.9, 4.9)
        painter.drawLine(QPointF(10, 2.4), QPointF(10, 7.2))
        painter.drawLine(QPointF(8.4, 10.0), QPointF(8.4, 13.8))
        painter.drawLine(QPointF(11.6, 10.0), QPointF(11.6, 13.8))
    elif kind == "keys":
        painter.drawRoundedRect(QRectF(2.2, 5.2, 15.6, 10.2), 2.4, 2.4)
        for x in (5.3, 8.0, 10.7, 13.4):
            painter.drawPoint(QPointF(x, 8.4))
        painter.drawLine(QPointF(6.2, 12.3), QPointF(13.8, 12.3))
    elif kind == "macro":
        painter.drawEllipse(center, 7.3, 7.3)
        path = QPainterPath()
        path.moveTo(QPointF(8.5, 6.4))
        path.lineTo(QPointF(14.0, 10.0))
        path.lineTo(QPointF(8.5, 13.6))
        path.closeSubpath()
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)
    elif kind == "image":
        painter.drawRoundedRect(QRectF(2.6, 3.4, 14.8, 13.2), 2.2, 2.2)
        painter.drawEllipse(QPointF(7.0, 7.2), 1.4, 1.4)
        path = QPainterPath()
        path.moveTo(QPointF(4.0, 14.0))
        path.lineTo(QPointF(8.0, 9.8))
        path.lineTo(QPointF(10.6, 12.3))
        path.lineTo(QPointF(12.5, 10.5))
        path.lineTo(QPointF(16.2, 14.0))
        painter.drawPath(path)
    elif kind == "logs":
        painter.drawRoundedRect(QRectF(3.5, 2.2, 13.0, 15.6), 2.4, 2.4)
        painter.drawLine(QPointF(6.4, 6.5), QPointF(13.6, 6.5))
        painter.drawLine(QPointF(6.4, 9.8), QPointF(13.6, 9.8))
        painter.drawLine(QPointF(6.4, 13.1), QPointF(11.6, 13.1))
    elif kind == "settings":
        for y, knob in ((5.3, 7.1), (10.0, 12.7), (14.7, 6.0)):
            painter.drawLine(QPointF(3.2, y), QPointF(16.8, y))
            painter.setBrush(QColor("#c0c0c0"))
            painter.drawEllipse(QPointF(knob, y), 2.1, 2.1)
    elif kind == "explore":
        painter.drawEllipse(center, 7.4, 7.4)
        painter.drawEllipse(center, 3.1, 7.4)
        painter.drawLine(QPointF(2.6, 10.0), QPointF(17.4, 10.0))
    elif kind == "bolt":
        path = QPainterPath()
        path.moveTo(QPointF(11.6, 2.2))
        path.lineTo(QPointF(5.3, 11.0))
        path.lineTo(QPointF(9.4, 11.0))
        path.lineTo(QPointF(8.2, 17.8))
        path.lineTo(QPointF(14.9, 8.7))
        path.lineTo(QPointF(10.5, 8.7))
        path.closeSubpath()
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)
    elif kind == "target":
        painter.drawEllipse(center, 7.2, 7.2)
        painter.drawEllipse(center, 3.0, 3.0)
        painter.drawLine(QPointF(10, 1.2), QPointF(10, 4.2))
        painter.drawLine(QPointF(10, 15.8), QPointF(10, 18.8))
        painter.drawLine(QPointF(1.2, 10), QPointF(4.2, 10))
        painter.drawLine(QPointF(15.8, 10), QPointF(18.8, 10))
    elif kind == "cursor":
        path = QPainterPath()
        path.moveTo(QPointF(5.0, 2.4))
        path.lineTo(QPointF(15.5, 11.4))
        path.lineTo(QPointF(10.5, 11.9))
        path.lineTo(QPointF(12.9, 17.3))
        path.lineTo(QPointF(9.9, 18.6))
        path.lineTo(QPointF(7.6, 13.0))
        path.lineTo(QPointF(4.2, 16.2))
        path.closeSubpath()
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)
    painter.end()
    return pixmap


def make_nav_icon(kind: str) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_icon_pixmap(kind, "#000000"), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_icon_pixmap(kind, "#ffffff"), QIcon.Normal, QIcon.On)
    icon.addPixmap(_icon_pixmap(kind, "#ffffff"), QIcon.Active, QIcon.On)
    icon.addPixmap(_icon_pixmap(kind, "#000000"), QIcon.Active, QIcon.Off)
    return icon


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------

class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, margins: tuple[int, int, int, int] = (20, 18, 20, 18)) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(13)


class SoftCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SoftCard")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(5)


class HeroCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeroCard")


class StatTile(SoftCard):
    def __init__(self, title: str, value: str = "0", hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.value_label = label(value, "Value")
        self.value_label.setFont(QFont(FONT_MONO, 16, QFont.Bold))
        self.title_label = label(title.upper(), "Tiny")
        self.hint_label = label(hint, "Tiny")
        self.body.addWidget(self.title_label)
        self.body.addWidget(self.value_label)
        if hint:
            self.body.addWidget(self.hint_label)
        self.body.addStretch(1)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


# ---------------------------------------------------------------------------
# Animated controls
# ---------------------------------------------------------------------------

class ToggleSwitch(QAbstractButton):
    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._offset = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_anim_value)
        self.setChecked(checked)
        self.toggled.connect(self._animate)

    def _set_anim_value(self, value) -> None:
        self._offset = float(value)
        self.update()

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        track = QRectF(0, 2, self.width(), self.height() - 4)
        painter.fillRect(track, QColor("#c0c0c0"))
        painter.fillRect(track.left(), track.top(), track.width(), 2, QColor("#404040"))
        painter.fillRect(track.left(), track.top(), 2, track.height(), QColor("#404040"))
        painter.fillRect(track.left(), track.bottom() - 2, track.width(), 2, QColor("#ffffff"))
        painter.fillRect(track.right() - 2, track.top(), 2, track.height(), QColor("#ffffff"))
        inner = track.adjusted(3, 3, -3, -3)
        painter.fillRect(inner, QColor("#ffffff" if not self.isChecked() else "#000080"))

        diameter = self.height() - 8
        x = 4 + self._offset * (self.width() - diameter - 8)
        knob = QRectF(x, 4, diameter, diameter)
        painter.fillRect(knob, QColor("#000000"))
        face = knob.adjusted(1, 1, -1, -1)
        painter.fillRect(face, QColor("#c0c0c0"))
        painter.fillRect(face.left(), face.top(), face.width(), 2, QColor("#ffffff"))
        painter.fillRect(face.left(), face.top(), 2, face.height(), QColor("#ffffff"))
        painter.fillRect(face.left(), face.bottom() - 2, face.width(), 2, QColor("#404040"))
        painter.fillRect(face.right() - 2, face.top(), 2, face.height(), QColor("#404040"))
        if self.isChecked():
            painter.fillRect(face.adjusted(5, 5, -5, -5), QColor("#000080"))

    def sizeHint(self) -> QSize:
        return QSize(44, 24)


class SegmentedControl(QWidget):
    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._guard = False
        for key, text in items:
            button = QPushButton(text)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda checked=False, key=key: self._select(key))
            self._group.addButton(button)
            self._buttons[key] = button
            layout.addWidget(button, 1)
        if items:
            self._buttons[items[0][0]].setChecked(True)

    def _select(self, key: str) -> None:
        if not self._guard:
            self.changed.emit(key)

    def current_key(self) -> str:
        for key, button in self._buttons.items():
            if button.isChecked():
                return key
        return next(iter(self._buttons), "")

    def set_current(self, key: str) -> None:
        button = self._buttons.get(key)
        if not button:
            return
        self._guard = True
        button.setChecked(True)
        self._guard = False

    def set_enabled(self, enabled: bool) -> None:
        for button in self._buttons.values():
            button.setEnabled(enabled)


class PulseDot(QWidget):
    def __init__(self, color: str = COLORS["accent"], size: int = 10, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size + 8, size + 8)
        self._color = QColor(color)
        self._phase = 0.0
        self._active = False
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def set_state(self, active: bool, color: str | None = None) -> None:
        self._active = active
        if color:
            self._color = QColor(color)
        if active and not self._timer.isActive():
            self._timer.start()
        elif not active:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.075) % (math.pi * 2)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        size = max(4, min(self.width(), self.height()) - 6)
        x = (self.width() - size) // 2
        y = (self.height() - size) // 2
        color = QColor(self._color)
        if self._active:
            # Square LEDs blink rather than glow in this design language.
            if math.sin(self._phase) < -0.35:
                color = QColor("#404040")
        else:
            color = QColor("#808080")
        painter.fillRect(x - 1, y - 1, size + 2, size + 2, QColor("#000000"))
        painter.fillRect(x, y, size, size, color)
        painter.fillRect(x, y, size, 1, QColor("#ffffff"))
        painter.fillRect(x, y, 1, size, QColor("#ffffff"))
        painter.fillRect(x, y + size - 1, size, 1, QColor("#404040"))
        painter.fillRect(x + size - 1, y, 1, size, QColor("#404040"))


class StatusPill(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 14, 0)
        layout.setSpacing(1)
        self.dot = PulseDot(COLORS["faint"], 8)
        self.text = label("READY", "Tiny")
        self.text.setStyleSheet("font-size: 9px; font-weight: 700; color: #404040;")
        layout.addWidget(self.dot)
        layout.addWidget(self.text)
        self.set_state(False, "READY")

    def set_state(self, active: bool, text: str, tone: str = "accent") -> None:
        color = {
            "accent": COLORS["accent"],
            "violet": COLORS["accent_2"],
            "amber": COLORS["amber"],
            "red": COLORS["red"],
        }.get(tone, COLORS["accent"])
        self.dot.set_state(active, color if active else COLORS["faint"])
        self.text.setText(text.upper())
        if active:
            self.text.setStyleSheet(f"font-size: 9px; font-weight: 700; color: {color};")
            self.setStyleSheet(
                "QFrame { background: #ffffe1; border: 1px solid #000000; }"
            )
        else:
            self.text.setStyleSheet("font-size: 9px; font-weight: 700; color: #404040;")
            self.setStyleSheet("QFrame { background: #c0c0c0; border: 1px solid #808080; }")


class EnergyLine(QWidget):
    """Classic segmented activity bar with a marching blue fill."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(9)
        self._phase = 0.0
        self._running = False
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def set_running(self, running: bool) -> None:
        self._running = running
        if running and not self._timer.isActive():
            self._timer.start()
        elif not running:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.035) % 1.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        rect = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(rect, QColor("#ffffff"))
        painter.fillRect(rect.left(), rect.top(), rect.width(), 2, QColor("#404040"))
        painter.fillRect(rect.left(), rect.top(), 2, rect.height(), QColor("#404040"))
        painter.fillRect(rect.left(), rect.bottom() - 2, rect.width(), 2, QColor("#ffffff"))
        painter.fillRect(rect.right() - 2, rect.top(), 2, rect.height(), QColor("#ffffff"))
        if not self._running:
            return
        inner = rect.adjusted(3, 3, -3, -3)
        block = 14.0
        gap = 3.0
        offset = self._phase * (block + gap) * 3
        x = inner.left() - (block + gap) * 3 + offset
        while x < inner.right():
            start = max(inner.left(), x)
            end = min(inner.right(), x + block)
            if end > start:
                painter.fillRect(QRectF(start, inner.top(), end - start, inner.height()), QColor("#000080"))
                painter.fillRect(QRectF(start, inner.top(), end - start, 1), QColor("#4040c0"))
            x += block + gap


class AmbientLine(QWidget):
    """Classic raised divider with a slow marching highlight."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._phase = 0.0
        self._wanted = False
        self._running = False
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def set_running(self, running: bool) -> None:
        self._wanted = bool(running)
        self._sync()

    def _sync(self) -> None:
        should_run = self._wanted and self.isVisible()
        if should_run and not self._timer.isActive():
            self._timer.start()
        elif not should_run and self._timer.isActive():
            self._timer.stop()
        self._running = should_run
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._sync()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.010) % 1.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.fillRect(0, 1, self.width(), 1, QColor("#808080"))
        if self.width() <= 0 or not self._running:
            return
        painter.setRenderHint(QPainter.Antialiasing, False)
        x = int(self._phase * self.width())
        painter.fillRect(x, 0, min(90, self.width() - x), 1, QColor("#000080"))
        painter.fillRect(max(0, x - 40), 2, 40, 1, QColor("#000080"))


class MystifyBackdrop(QWidget):
    """Animated Mystify screensaver running on the teal desktop.

    Each polyline is a small chain of points with independent velocities that
    reflect off the edges. Three translucent ghosts behind every line recreate
    the phosphor trail of the original screensaver without any blur filters.
    """

    LINE_COLORS = (
        QColor(255, 255, 255),
        QColor(0, 255, 255),
        QColor(255, 0, 255),
        QColor(255, 255, 0),
        QColor(192, 192, 192),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._wanted = False
        self._running = False
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._lines: list[dict] = []
        self._seed_lines()

        self._pattern = QPixmap(4, 4)
        self._pattern.fill(QColor("#008080"))
        pattern_painter = QPainter(self._pattern)
        pattern_painter.fillRect(0, 0, 1, 1, QColor("#007878"))
        pattern_painter.fillRect(2, 2, 1, 1, QColor("#007878"))
        pattern_painter.end()

    def _seed_lines(self) -> None:
        seeds = (
            (0.12, 0.20, 0.30, 0.68, 0.52, 0.15, 0.64, 0.34),
            (0.72, 0.14, 0.16, 0.44, 0.38, 0.78, 0.86, 0.58),
            (0.44, 0.78, 0.82, 0.24, 0.18, 0.52, 0.54, 0.86),
            (0.24, 0.56, 0.72, 0.82, 0.88, 0.36, 0.42, 0.12),
            (0.86, 0.72, 0.10, 0.10, 0.58, 0.48, 0.34, 0.90),
        )
        for index, (x0, y0, x1, y1, x2, y2, x3, y3) in enumerate(seeds):
            points = [QPointF(x0, y0), QPointF(x1, y1), QPointF(x2, y2), QPointF(x3, y3)]
            velocities = []
            for point_index in range(4):
                angle = (index * 1.7 + point_index * 2.1) % (math.pi * 2)
                speed = 0.055 + 0.014 * ((index + point_index) % 4)
                velocities.append(QPointF(math.cos(angle) * speed, math.sin(angle) * speed))
            self._lines.append({
                "points": points,
                "velocities": velocities,
                "color": self.LINE_COLORS[index % len(self.LINE_COLORS)],
            })

    def set_running(self, running: bool) -> None:
        self._wanted = bool(running)
        self._sync()

    def _sync(self) -> None:
        should_run = self._wanted and self.isVisible()
        if should_run and not self._timer.isActive():
            self._timer.start()
        elif not should_run and self._timer.isActive():
            self._timer.stop()
        self._running = should_run
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._sync()

    def _tick(self) -> None:
        dt = 0.033
        for line in self._lines:
            for point, velocity in zip(line["points"], line["velocities"]):
                point.setX(point.x() + velocity.x() * dt)
                point.setY(point.y() + velocity.y() * dt)
                if point.x() < 0.02:
                    point.setX(0.02)
                    velocity.setX(abs(velocity.x()))
                elif point.x() > 0.98:
                    point.setX(0.98)
                    velocity.setX(-abs(velocity.x()))
                if point.y() < 0.02:
                    point.setY(0.02)
                    velocity.setY(abs(velocity.y()))
                elif point.y() > 0.98:
                    point.setY(0.98)
                    velocity.setY(-abs(velocity.y()))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = QRectF(self.rect())
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.drawTiledPixmap(rect.toRect(), self._pattern)

        for line in self._lines:
            color = line["color"]
            painter.setBrush(Qt.NoBrush)
            for trail in (4, 3, 2, 1):
                alpha = 16 + (4 - trail) * 24
                ghost = QColor(color)
                ghost.setAlpha(alpha)
                painter.setPen(QPen(ghost, 2))
                path = QPainterPath()
                for index, point in enumerate(line["points"]):
                    velocity = line["velocities"][index]
                    x = rect.left() + (point.x() - velocity.x() * 0.026 * trail) * rect.width()
                    y = rect.top() + (point.y() - velocity.y() * 0.026 * trail) * rect.height()
                    if index == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                painter.drawPath(path)

            bright = QColor(color)
            bright.setAlpha(230)
            painter.setPen(QPen(bright, 2))
            painter.setBrush(Qt.NoBrush)
            path = QPainterPath()
            for index, point in enumerate(line["points"]):
                x = rect.left() + point.x() * rect.width()
                y = rect.top() + point.y() * rect.height()
                if index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.drawPath(path)

            # Square handles make the bouncing vertices read as classic VGA.
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 90))
            for point in line["points"]:
                painter.drawRect(QRectF(
                    rect.left() + point.x() * rect.width() - 1.5,
                    rect.top() + point.y() * rect.height() - 1.5,
                    3,
                    3,
                ))
            painter.setBrush(Qt.NoBrush)


# Backwards-compatible name used by the shell.
AuroraBackdrop = MystifyBackdrop


class RingGauge(QWidget):
    gaugeValue = Property(float, lambda self: self._gauge_value, lambda self, value: self._set_gauge_value(value))

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self._gauge_value = 0.0
        self._max_value = 1000.0
        self._anim = QPropertyAnimation(self, b"gaugeValue", self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _set_gauge_value(self, value: float) -> None:
        self._gauge_value = max(0.0, min(float(self._max_value), float(value)))
        self.update()

    def set_value(self, value: float, animate: bool = True) -> None:
        target = max(0.0, min(float(self._max_value), float(value)))
        if not animate:
            self._anim.stop()
            self._set_gauge_value(target)
            return
        self._anim.stop()
        self._anim.setStartValue(self._gauge_value)
        self._anim.setEndValue(target)
        self._anim.start()

    def set_scale(self, maximum: float) -> None:
        self._max_value = max(10.0, float(maximum))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        side = min(self.width(), self.height())
        rect = QRectF(
            (self.width() - side) / 2 + 14,
            (self.height() - side) / 2 + 14,
            side - 28,
            side - 28,
        )
        ratio = min(1.0, self._gauge_value / self._max_value) if self._max_value else 0.0

        # Tick marks around the dial, like a piece of lab equipment.
        painter.setPen(QPen(QColor("#808080"), 1))
        center = rect.center()
        for step in range(28):
            angle = math.radians(225 - 270 * step / 27)
            outer = QPointF(
                center.x() + math.cos(angle) * (rect.width() / 2 + 8),
                center.y() - math.sin(angle) * (rect.height() / 2 + 8),
            )
            inner = QPointF(
                center.x() + math.cos(angle) * (rect.width() / 2 + 2),
                center.y() - math.sin(angle) * (rect.height() / 2 + 2),
            )
            painter.drawLine(inner, outer)

        track_pen = QPen(QColor("#808080"), 13)
        track_pen.setCapStyle(Qt.FlatCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        if ratio > 0.001:
            progress_pen = QPen(QColor("#000080"), 13)
            progress_pen.setCapStyle(Qt.FlatCap)
            painter.setPen(progress_pen)
            painter.drawArc(rect, 225 * 16, int(-270 * ratio * 16))

        angle = math.radians(225 - 270 * ratio)
        dot = QPointF(
            center.x() + math.cos(angle) * rect.width() / 2,
            center.y() - math.sin(angle) * rect.height() / 2,
        )
        painter.fillRect(QRectF(dot.x() - 5, dot.y() - 5, 10, 10), QColor("#000000"))
        painter.fillRect(QRectF(dot.x() - 4, dot.y() - 4, 8, 8), QColor("#ffff00"))

        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(QFont(FONT_UI, 8, QFont.DemiBold))
        painter.drawText(
            QRectF(rect.left(), rect.top() + 34, rect.width(), 20),
            Qt.AlignHCenter | Qt.AlignVCenter,
            "LIVE CPS",
        )

        painter.setPen(QColor("#000080"))
        painter.setFont(QFont(FONT_MONO, 28, QFont.Bold))
        display = f"{self._gauge_value:,.0f}" if self._gauge_value < 10000 else f"{self._gauge_value / 1000:.1f}k"
        painter.drawText(
            QRectF(rect.left(), rect.top() + 55, rect.width(), 54),
            Qt.AlignHCenter | Qt.AlignVCenter,
            display,
        )

        painter.setPen(QColor(COLORS["faint"]))
        painter.setFont(QFont(FONT_UI, 8))
        painter.drawText(
            QRectF(rect.left(), rect.bottom() - 46, rect.width(), 20),
            Qt.AlignHCenter | Qt.AlignVCenter,
            f"SCALE 0 — {self._max_value:,.0f}",
        )


class Sparkline(QWidget):
    def __init__(self, parent: QWidget | None = None, capacity: int = 64) -> None:
        super().__init__(parent)
        self.setMinimumHeight(86)
        self._values: deque[float] = deque(maxlen=capacity)
        self._accent = QColor(COLORS["accent"])

    def push(self, value: float) -> None:
        self._values.append(max(0.0, float(value)))
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        outer = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(outer, QColor("#ffffff"))
        painter.fillRect(outer.left(), outer.top(), outer.width(), 2, QColor("#404040"))
        painter.fillRect(outer.left(), outer.top(), 2, outer.height(), QColor("#404040"))
        painter.fillRect(outer.left(), outer.bottom() - 2, outer.width(), 2, QColor("#ffffff"))
        painter.fillRect(outer.right() - 2, outer.top(), 2, outer.height(), QColor("#ffffff"))
        rect = outer.adjusted(8, 8, -8, -8)
        painter.setPen(QPen(QColor("#c0c0c0"), 1, Qt.DotLine))
        for fraction in (0.0, 0.5, 1.0):
            y = rect.top() + fraction * rect.height()
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        if len(self._values) < 2:
            painter.setPen(QColor(COLORS["faint"]))
            painter.setFont(QFont(FONT_UI, 8))
            painter.drawText(rect, Qt.AlignCenter, "Waiting for live samples…")
            return

        values = list(self._values)
        maximum = max(10.0, max(values) * 1.2)
        points = []
        for index, value in enumerate(values):
            x = rect.left() + rect.width() * index / (len(values) - 1)
            y = rect.bottom() - rect.height() * min(1.0, value / maximum)
            points.append(QPointF(x, y))

        fill = QPainterPath()
        fill.moveTo(points[0])
        for point in points[1:]:
            fill.lineTo(point)
        fill.lineTo(rect.right(), rect.bottom())
        fill.lineTo(rect.left(), rect.bottom())
        fill.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#cce8ff"))
        painter.drawPath(fill)

        painter.setPen(QPen(QColor(COLORS["accent"]), 2))
        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.drawPath(path)

        last = points[-1]
        painter.fillRect(QRectF(last.x() - 3, last.y() - 3, 6, 6), QColor("#000000"))
        painter.fillRect(QRectF(last.x() - 2, last.y() - 2, 4, 4), QColor("#ffff00"))


class ThresholdBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(10)
        self._value = 0.0
        self._threshold = 0.85

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self.update()

    def set_threshold(self, value: float) -> None:
        self._threshold = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        rect = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(rect, QColor("#ffffff"))
        painter.fillRect(rect.left(), rect.top(), rect.width(), 2, QColor("#404040"))
        painter.fillRect(rect.left(), rect.top(), 2, rect.height(), QColor("#404040"))
        painter.fillRect(rect.left(), rect.bottom() - 2, rect.width(), 2, QColor("#ffffff"))
        painter.fillRect(rect.right() - 2, rect.top(), 2, rect.height(), QColor("#ffffff"))
        inner = rect.adjusted(3, 3, -3, -3)
        if self._value > 0:
            fill = QRectF(inner.left(), inner.top(), inner.width() * self._value, inner.height())
            painter.fillRect(fill, QColor("#000080" if self._value >= self._threshold else "#808000"))
        marker_x = inner.left() + inner.width() * self._threshold
        painter.setPen(QPen(QColor("#000000"), 2))
        painter.drawLine(QPointF(marker_x, rect.top() - 1), QPointF(marker_x, rect.bottom() + 1))


class MacroTimeline(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(104)
        self._macro: dict | None = None
        self._progress = 0.0

    def set_macro(self, macro: dict | None) -> None:
        self._macro = macro
        self._progress = 0.0
        self.update()

    def set_progress(self, progress: float) -> None:
        self._progress = max(0.0, min(1.0, progress))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        rect = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(rect, QColor("#ffffff"))
        painter.fillRect(rect.left(), rect.top(), rect.width(), 2, QColor("#404040"))
        painter.fillRect(rect.left(), rect.top(), 2, rect.height(), QColor("#404040"))
        painter.fillRect(rect.left(), rect.bottom() - 2, rect.width(), 2, QColor("#ffffff"))
        painter.fillRect(rect.right() - 2, rect.top(), 2, rect.height(), QColor("#ffffff"))

        if not self._macro or not self._macro.get("events"):
            painter.setPen(QColor(COLORS["faint"]))
            painter.setFont(QFont(FONT_UI, 9))
            painter.drawText(rect, Qt.AlignCenter, "Select a macro to inspect its timeline")
            return

        macro = self._macro
        duration = max(1.0, float(macro.get("duration", 0)))
        events = macro.get("events", [])
        inner = rect.adjusted(14, 14, -14, -24)
        baseline = inner.bottom()
        colors = {
            "move": QColor("#c0c0c0"),
            "down": QColor("#800000"),
            "up": QColor("#c06060"),
            "keydown": QColor("#808000"),
            "keyup": QColor("#a0a040"),
            "scroll": QColor("#008000"),
        }
        heights = {"move": 0.22, "down": 0.78, "up": 0.3, "keydown": 0.58, "keyup": 0.24, "scroll": 0.36}
        skip = max(1, len(events) // 700)
        for index in range(0, len(events), skip):
            item = events[index]
            kind = item.get("type", "move")
            x = inner.left() + inner.width() * min(1.0, max(0.0, float(item.get("t", 0))) / duration)
            height = inner.height() * heights.get(kind, 0.2)
            color = colors.get(kind, QColor("#404040"))
            width = 1 if kind == "move" else 2
            painter.setPen(QPen(color, width))
            painter.drawLine(QPointF(x, baseline), QPointF(x, baseline - max(3, height)))

        painter.setPen(QColor(COLORS["faint"]))
        painter.setFont(QFont(FONT_UI, 7))
        painter.drawText(QRectF(inner.left(), rect.bottom() - 17, 80, 12), Qt.AlignLeft, "0:00")
        painter.drawText(
            QRectF(inner.right() - 90, rect.bottom() - 17, 90, 12),
            Qt.AlignRight,
            f"{duration / 1000:.1f}s",
        )

        if self._progress > 0:
            x = inner.left() + inner.width() * self._progress
            painter.setPen(QPen(QColor("#800000"), 2))
            painter.drawLine(QPointF(x, inner.top()), QPointF(x, inner.bottom()))
            painter.fillRect(QRectF(x - 2, inner.top() - 2, 5, 5), QColor("#ffff00"))


class GlowPulse:
    """Retro active-state indicator — no drop shadows, just a held reference."""

    def __init__(self, widget: QWidget, color: str = COLORS["accent"]) -> None:
        self.widget = widget
        self._active = False

    def start(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False


# ---------------------------------------------------------------------------
# Toasts
# ---------------------------------------------------------------------------

_TOAST_STYLES = {
    "success": ("#c0c0c0", "#008000", "#008000", "✓"),
    "info": ("#c0c0c0", "#000080", "#000080", "i"),
    "warning": ("#c0c0c0", "#808000", "#808000", "!"),
    "error": ("#c0c0c0", "#800000", "#800000", "×"),
}


class Toast(QFrame):
    dismissed = Signal(object)

    def __init__(self, level: str, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(356, 62)
        bg, border, accent, icon = _TOAST_STYLES.get(level, _TOAST_STYLES["info"])
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 2px solid; "
            f"border-top-color: #ffffff; border-left-color: {accent}; "
            "border-right-color: #404040; border-bottom-color: #404040; }}"
            f"QLabel {{ background: transparent; border: none; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 14, 10)
        layout.setSpacing(10)
        icon_label = QLabel(icon)
        icon_label.setFixedSize(28, 28)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            f"font-size: 13px; font-weight: 800; color: {accent}; "
            "background: #ffffff; border: 2px solid; border-top-color: #404040; "
            "border-left-color: #404040; border-right-color: #ffffff; border-bottom-color: #ffffff;"
        )
        text = QLabel(message)
        text.setWordWrap(True)
        text.setStyleSheet("color: #000000; font-size: 11px; font-weight: 500;")
        layout.addWidget(icon_label)
        layout.addWidget(text, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._dismissing = False

    def enter(self, target: QPoint) -> None:
        self.move(target)
        self.show()
        self.raise_()
        self._timer.start(4200)

    def dismiss(self) -> None:
        if self._dismissing:
            return
        self._dismissing = True
        self._timer.stop()
        self.hide()
        self.dismissed.emit(self)

    def mousePressEvent(self, event) -> None:
        self.dismiss()


class ToastHost(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._toasts: list[Toast] = []

    def show_toast(self, level: str, message: str) -> None:
        self.raise_()
        while len(self._toasts) >= 3:
            oldest = self._toasts.pop(0)
            oldest.deleteLater()
        toast = Toast(level, message, self)
        toast.dismissed.connect(self._remove)
        self._toasts.append(toast)
        self._relayout(entering=toast)
        toast.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def _remove(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        toast.deleteLater()
        self._relayout()

    def _relayout(self, entering: Toast | None = None) -> None:
        if not self._toasts:
            return
        x = self.width() - 356 - 24
        y = self.height() - 24
        for toast in reversed(self._toasts):
            y -= toast.height()
            target = QPoint(max(12, x), max(12, y))
            if toast is entering:
                toast.enter(target)
            else:
                toast.move(target)
            y -= 10

    def relayout(self) -> None:
        self._relayout()


__all__ = [
    "Card",
    "SoftCard",
    "HeroCard",
    "StatTile",
    "ToggleSwitch",
    "SegmentedControl",
    "StatusPill",
    "PulseDot",
    "EnergyLine",
    "AmbientLine",
    "AuroraBackdrop",
    "RingGauge",
    "Sparkline",
    "ThresholdBar",
    "MacroTimeline",
    "LogoMark",
    "ToastHost",
    "GlowPulse",
    "make_app_icon",
    "make_nav_icon",
    "make_button",
    "label",
    "hline",
    "pointer",
    "add_glow",
]
