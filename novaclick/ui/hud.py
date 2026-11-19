"""Compact always-on-top run HUD for active automations."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout



class RunHud(QFrame):
    """Small floating panel with live status and a one-click panic stop."""

    stop_requested = Signal()
    show_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("RunHud")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(378, 94)
        self.setStyleSheet(
            "QFrame#RunHud { background: #c0c0c0; border: 2px solid; "
            "border-top-color: #ffffff; border-left-color: #ffffff; "
            "border-right-color: #404040; border-bottom-color: #404040; }"
            "QFrame#RunHud QLabel { background: transparent; border: none; }"
        )
        self._drag_offset: QPoint | None = None
        self._placed = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 10, 9)
        layout.setSpacing(10)

        mark = QLabel("▶")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(34, 34)
        mark.setStyleSheet(
            "font-size: 14px; color: #000080; background: #ffffff; border: 2px solid; "
            "border-top-color: #404040; border-left-color: #404040; "
            "border-right-color: #ffffff; border-bottom-color: #ffffff;"
        )
        self.mark = mark
        layout.addWidget(mark, 0, Qt.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = QLabel("AUTOMATION LIVE")
        self.title.setStyleSheet(
            "font-family: 'Courier New'; font-size: 8px; font-weight: 700; color: #000080;"
        )
        self.status = QLabel("SYSTEM READY")
        self.status.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #000000;"
        )
        self.detail = QLabel("F10 stops everything")
        self.detail.setStyleSheet(
            "font-family: 'Courier New'; font-size: 8px; color: #404040;"
        )
        text.addWidget(self.title)
        text.addWidget(self.status)
        text.addWidget(self.detail)
        layout.addLayout(text, 1)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("DangerButton")
        self.stop_btn.setFixedSize(64, 46)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setToolTip("Stop every engine (same as F10 panic)")
        self.stop_btn.clicked.connect(self.stop_requested)
        layout.addWidget(self.stop_btn, 0, Qt.AlignVCenter)

    # ------------------------------------------------------------------
    def update_state(self, status: str, detail: str, tone: str = "accent") -> None:
        self.status.setText(status.upper())
        self.detail.setText(detail)
        color = {
            "accent": "#000080",
            "violet": "#800080",
            "cyan": "#008080",
            "warning": "#800000",
        }.get(tone, "#000080")
        self.title.setStyleSheet(
            f"font-family: 'Courier New'; font-size: 8px; font-weight: 700; color: {color};"
        )
        self.mark.setStyleSheet(
            f"font-size: 14px; color: {color}; background: #ffffff; border: 2px solid; "
            "border-top-color: #404040; border-left-color: #404040; "
            "border-right-color: #ffffff; border-bottom-color: #ffffff;"
        )

    def present(self) -> None:
        if not self._placed:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                self.move(
                    area.right() - self.width() - 26,
                    area.bottom() - self.height() - 26,
                )
            self._placed = True
        self.show()
        self.raise_()

    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.show_requested.emit()
        event.accept()


__all__ = ["RunHud"]
