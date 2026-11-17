"""Retro Windows startup screen for AutoClicker."""

from __future__ import annotations

import math

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import __tagline__, __version__
from .theme import COLORS, FONT_MONO
from .widgets import LogoMark, label


class SplashProgress(QWidget):
    """Segmented Windows-style progress meter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(18)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._value = 0.0
        self._phase = 0.0

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self.update()

    def advance_phase(self) -> None:
        self._phase = (self._phase + 0.09) % 1.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        outer = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(outer, QColor("#c0c0c0"))
        painter.fillRect(outer.left(), outer.top(), outer.width(), 2, QColor("#404040"))
        painter.fillRect(outer.left(), outer.top(), 2, outer.height(), QColor("#404040"))
        painter.fillRect(outer.left(), outer.bottom() - 2, outer.width(), 2, QColor("#ffffff"))
        painter.fillRect(outer.right() - 2, outer.top(), 2, outer.height(), QColor("#ffffff"))

        inner = outer.adjusted(4, 4, -4, -4)
        painter.fillRect(inner, QColor("#ffffff"))
        block = 13.0
        gap = 3.0
        count = max(1, int((inner.width() + gap) / (block + gap)))
        filled = int(round(count * self._value))
        for index in range(count):
            x = inner.left() + index * (block + gap)
            width = min(block, inner.right() - x)
            if width <= 0:
                break
            if index < filled:
                painter.fillRect(QRectF(x, inner.top(), width, inner.height()), QColor("#000080"))
                painter.fillRect(QRectF(x, inner.top(), width, 1), QColor("#4040c0"))
            elif index == filled and self._value < 1.0:
                # A single blinking slot leads the fill, like a disk activity light.
                if math.sin(self._phase * math.pi * 2) > 0:
                    painter.fillRect(
                        QRectF(x, inner.top(), width, inner.height()), QColor("#808000")
                    )


class BootConsole(QWidget):
    """Black terminal pane that prints the boot sequence line by line."""

    LINES = (
        "AutoClicker BIOS v2.4  ·  native input core",
        "Loading SendInput engine ............ OK",
        "Mounting macro vault ................ OK",
        "Calibrating click pipeline .......... OK",
        "Starting AutoClicker interface ...... OK",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(116)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._progress = 0.0
        self._phase = 0.0

    def set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, value))
        self.update()

    def advance_phase(self) -> None:
        self._phase = (self._phase + 0.5) % (math.pi * 2)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        outer = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(outer, QColor("#c0c0c0"))
        painter.fillRect(outer.left(), outer.top(), outer.width(), 2, QColor("#404040"))
        painter.fillRect(outer.left(), outer.top(), 2, outer.height(), QColor("#404040"))
        painter.fillRect(outer.left(), outer.bottom() - 2, outer.width(), 2, QColor("#ffffff"))
        painter.fillRect(outer.right() - 2, outer.top(), 2, outer.height(), QColor("#ffffff"))

        inner = outer.adjusted(4, 4, -4, -4)
        painter.fillRect(inner, QColor("#000000"))

        font = QFont(FONT_MONO, 9)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        line_height = metrics.height() + 2
        visible = max(1, int(self._progress * len(self.LINES) * 1.18) + 1)
        visible = min(len(self.LINES), visible)
        y = inner.top() + 5
        for index in range(visible):
            text = self.LINES[index]
            if index == len(self.LINES) - 1:
                color = QColor("#ffff00")
            elif text.endswith("OK"):
                color = QColor("#c0c0c0")
            else:
                color = QColor("#00c000")
            painter.setPen(color)
            painter.drawText(
                QRectF(inner.left() + 6, y, inner.width() - 12, line_height),
                Qt.AlignLeft | Qt.AlignVCenter,
                text,
            )
            y += line_height

        if self._progress >= 1.0:
            painter.setPen(QColor("#00ff00"))
            painter.drawText(
                QRectF(inner.left() + 6, y, inner.width() - 12, line_height),
                Qt.AlignLeft | Qt.AlignVCenter,
                "C:\\AUTOCLICKER> _",
            )
        elif math.sin(self._phase) > 0:
            painter.fillRect(
                QRectF(inner.left() + 6, y + 4, 7, max(8, metrics.height() - 3)),
                QColor("#00c000"),
            )


class SplashScreen(QWidget):
    finished = Signal()

    STATUS_STEPS = [
        (0.00, "Starting AutoClicker…"),
        (0.24, "Loading native input engine…"),
        (0.50, "Mounting the macro vault…"),
        (0.76, "Preparing the workspace…"),
        (0.97, "Ready."),
    ]

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setFixedSize(600, 424)
        self._progress = 0.0
        self._phase = 0.0
        self._ready = False
        self._emitted = False
        self._started = False
        self._elapsed = QElapsedTimer()
        self._closing = False
        self._marquee = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 48, 20, 12)
        layout.setSpacing(0)

        self.logo = LogoMark(74)
        logo_row = QHBoxLayout()
        logo_row.addStretch(1)
        logo_row.addWidget(self.logo)
        logo_row.addStretch(1)
        layout.addLayout(logo_row)
        layout.addSpacing(8)

        title = label("AutoClicker", "HeroTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 27px; font-weight: 700; color: #000080; "
            "background: transparent; letter-spacing: 1px;"
        )
        layout.addWidget(title)

        tagline = QLabel(__tagline__)
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setStyleSheet(
            "font-size: 9px; color: #404040; background: transparent;"
        )
        layout.addWidget(tagline)
        layout.addSpacing(10)

        self.console = BootConsole()
        layout.addWidget(self.console)
        layout.addSpacing(9)

        self.progress = SplashProgress()
        layout.addWidget(self.progress)
        layout.addSpacing(9)

        self.status_label = QLabel(self.STATUS_STEPS[0][1])
        self.status_label.setStyleSheet(
            "background: #ffffff; border: 2px solid; border-top-color: #404040; "
            "border-left-color: #404040; border-right-color: #ffffff; "
            "border-bottom-color: #ffffff; color: #000000; "
            "font-family: 'Courier New'; font-size: 10px; padding: 3px 7px;"
        )
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        footer = QHBoxLayout()
        version = QLabel(f"v{__version__}  ·  RELEASE")
        version.setStyleSheet(
            "font-family: 'Courier New'; font-size: 8px; color: #404040; "
            "background: transparent;"
        )
        right = QLabel("NATIVE INPUT  ·  WINDOWS")
        right.setStyleSheet(
            "font-family: 'Courier New'; font-size: 8px; color: #404040; "
            "background: transparent;"
        )
        footer.addWidget(version)
        footer.addStretch(1)
        footer.addWidget(right)
        layout.addLayout(footer)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._started:
            self._started = True
            self._elapsed.start()
            self._timer.start()
        screen = self.screen()
        if screen:
            geometry = screen.availableGeometry()
            self.move(geometry.center() - self.rect().center())

    def mark_ready(self) -> None:
        self._ready = True

    def _tick(self) -> None:
        self._phase += 0.045
        self._marquee = (self._marquee + 1) % 24
        elapsed = self._elapsed.elapsed() / 1000.0
        target = min(0.94, elapsed / 2.0)
        if self._ready:
            target = min(1.0, target + 0.06) if elapsed > 1.65 else target
        if target > self._progress:
            self._progress += min(0.016, target - self._progress)
        if self._ready and elapsed > 1.9:
            self._progress = min(1.0, self._progress + 0.018)
        self.progress.set_value(self._progress)
        self.progress.advance_phase()
        self.console.set_progress(self._progress)
        self.console.advance_phase()
        # Repaint the custom panes directly; this keeps the segmented meter in
        # sync with the console on every windowing backend.
        self.progress.repaint()
        self.console.repaint()
        self.logo.set_glow(0.55 + 0.45 * math.sin(self._phase))

        status = self.STATUS_STEPS[0][1]
        for threshold, message in self.STATUS_STEPS:
            if self._progress >= threshold:
                status = message
        self.status_label.setText(status)
        self.update()

        if self._ready and elapsed > 2.15 and not self._emitted:
            self._emitted = True
            self._timer.stop()
            self.finished.emit()

    def fade_out(self) -> None:
        if self._closing:
            return
        self._closing = True
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(220)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.InCubic)
        animation.finished.connect(self.close)
        animation.start(QPropertyAnimation.DeleteWhenStopped)
        self._fade_ref = animation

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        outer = QRectF(0, 0, self.width(), self.height())

        # Black outline, raised silver chassis.
        painter.fillRect(outer, QColor("#000000"))
        chassis = outer.adjusted(1, 1, -1, -1)
        painter.fillRect(chassis, QColor("#c0c0c0"))
        painter.fillRect(chassis.left(), chassis.top(), chassis.width(), 2, QColor("#ffffff"))
        painter.fillRect(chassis.left(), chassis.top(), 2, chassis.height(), QColor("#ffffff"))
        painter.fillRect(chassis.left(), chassis.bottom() - 2, chassis.width(), 2, QColor("#404040"))
        painter.fillRect(chassis.right() - 2, chassis.top(), 2, chassis.height(), QColor("#404040"))

        # Flat Windows 98 caption bar.
        caption = QRectF(chassis.left() + 3, chassis.top() + 3, chassis.width() - 6, 27)
        painter.fillRect(caption, QColor("#000080"))
        painter.fillRect(caption.left(), caption.top(), caption.width(), 1, QColor("#4040c0"))

        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Tahoma", 9, QFont.Bold))
        painter.drawText(
            QRectF(caption.left() + 7, caption.top(), caption.width() - 90, caption.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            "AutoClicker  ·  Starting up",
        )

        # Decorative minimize / maximize / close buttons.
        button_y = caption.top() + 4
        for index, glyph in enumerate(("_", "□", "×")):
            bx = caption.right() - 26 - index * 23
            painter.fillRect(QRectF(bx, button_y, 20, 18), QColor("#c0c0c0"))
            painter.fillRect(QRectF(bx, button_y, 20, 1), QColor("#ffffff"))
            painter.fillRect(QRectF(bx, button_y, 1, 18), QColor("#ffffff"))
            painter.fillRect(QRectF(bx, button_y + 17, 20, 1), QColor("#404040"))
            painter.fillRect(QRectF(bx + 19, button_y, 1, 18), QColor("#404040"))
            painter.setPen(QColor("#000000"))
            painter.setFont(QFont("Tahoma", 8, QFont.Bold))
            painter.drawText(
                QRectF(bx, button_y, 20, 18),
                Qt.AlignCenter,
                glyph,
            )


__all__ = ["SplashScreen", "SplashProgress", "BootConsole"]
