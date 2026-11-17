"""Shared page scaffold."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


class Page(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("PageBody")
        self.body.setAttribute(Qt.WA_StyledBackground, False)
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(28, 24, 28, 26)
        self.layout.setSpacing(16)
        self.setWidget(self.body)
