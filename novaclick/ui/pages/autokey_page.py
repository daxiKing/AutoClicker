"""Auto-key engine page."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...core.engine import AutoKey, KeyConfig
from ...core.keys import pynput_key_to_vk, vk_name
from ...core.macros import format_clock
from ..theme import COLORS, FONT_MONO, FONT_UI
from ..widgets import (
    Card,
    EnergyLine,
    GlowPulse,
    HeroCard,
    PulseDot,
    SegmentedControl,
    Sparkline,
    StatTile,
    hline,
    label,
    make_button,
)
from .base import Page


class KeyWaves(QWidget):
    """Decorative key pulse visualisation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(172)
        self._phase = 0.0
        self._active = False
        self._key = "SPACE"
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def set_key(self, name: str) -> None:
        self._key = name
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.045) % (math.pi * 2)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        center = QPointF(self.width() / 2, self.height() / 2)

        # Sonar rings drawn as chunky square brackets rather than soft arcs.
        for index, radius in enumerate((44, 61, 78)):
            offset = self._phase + index * 1.6
            strength = 0.5 + 0.5 * math.sin(offset)
            color = QColor(COLORS["accent"] if self._active else "#808080")
            color.setAlpha(int(40 + 90 * strength) if self._active else 55)
            painter.setPen(QPen(color, 2))
            box = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
            span = 46
            start = int((math.degrees(offset) + index * 40) % 360)
            painter.drawArc(box, start * 16, span * 16)
            painter.drawArc(box, (start + 180) * 16, span * 16)

        keycap = QRectF(center.x() - 33, center.y() - 33, 66, 66)
        if self._active:
            keycap.translate(0, 2)
            painter.fillRect(keycap, QColor("#000000"))
            face = keycap.adjusted(1, 1, -1, -1)
            painter.fillRect(face, QColor("#ffffff"))
            painter.fillRect(face.left(), face.top(), face.width(), 2, QColor("#404040"))
            painter.fillRect(face.left(), face.top(), 2, face.height(), QColor("#404040"))
            painter.fillRect(face.left(), face.bottom() - 2, face.width(), 2, QColor("#ffffff"))
            painter.fillRect(face.right() - 2, face.top(), 2, face.height(), QColor("#ffffff"))
        else:
            painter.fillRect(keycap, QColor("#000000"))
            face = keycap.adjusted(1, 1, -1, -1)
            painter.fillRect(face, QColor("#c0c0c0"))
            painter.fillRect(face.left(), face.top(), face.width(), 3, QColor("#ffffff"))
            painter.fillRect(face.left(), face.top(), 3, face.height(), QColor("#ffffff"))
            painter.fillRect(face.left(), face.bottom() - 3, face.width(), 3, QColor("#404040"))
            painter.fillRect(face.right() - 3, face.top(), 3, face.height(), QColor("#404040"))

        text = self._key.upper()
        if len(text) > 9:
            text = text[:8] + "…"
        font_size = 13 if len(text) <= 3 else 9
        painter.setPen(QColor("#800000" if self._active else "#000080"))
        painter.setFont(QFont(FONT_MONO, font_size, QFont.Bold))
        painter.drawText(face, Qt.AlignCenter, text)

        if self._active:
            painter.setPen(QColor("#008000"))
            painter.setFont(QFont(FONT_UI, 7, QFont.DemiBold))
            painter.drawText(
                QRectF(0, self.height() - 22, self.width(), 14),
                Qt.AlignCenter,
                "STREAMING",
            )


class AutoKeyPage(Page):
    key_captured = Signal(int, str)

    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self.engine = AutoKey()
        self._active_ui = False
        self._vk = 0x20
        self._key_name = "Space"
        self._listening = False
        self._capture_listener = None
        self._capture_timeout = QTimer(self)
        self._capture_timeout.setSingleShot(True)
        self._capture_timeout.timeout.connect(lambda: self._cancel_capture(notify=True))
        self._last_count = 0
        self._last_time = time.perf_counter()
        self._last_push = 0.0
        self._live = 0.0
        self._peak = 0.0
        self._last_error = None
        self._guard = False
        self._arm_deadline = 0.0

        self.key_captured.connect(self._on_key_captured)
        self._build_hero()
        columns = QHBoxLayout()
        columns.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(self._build_binding_card())
        left.addWidget(self._build_notes_card())
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self._build_telemetry_card())
        right.addStretch(1)
        columns.addLayout(left, 5)
        columns.addLayout(right, 4)
        self.layout.addLayout(columns)

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._update_key_ui()
        self._sync_rate_controls()
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
        eyebrow.addWidget(label("AUTO KEY ENGINE", "Eyebrow"))
        eyebrow.addStretch(1)
        left.addLayout(eyebrow)
        self.hero_status = label("Key engine standby", "HeroTitle")
        left.addWidget(self.hero_status)
        self.hero_sub = label("", "HeroSub")
        left.addWidget(self.hero_sub)
        row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(5)
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.start_btn = make_button("Start pressing", "StartButton")
        self.start_btn.setMinimumWidth(190)
        self.start_btn.setMinimumHeight(54)
        self.start_btn.clicked.connect(self.toggle)
        self.start_btn.setToolTip(
            f"Toggle the auto-key engine ({self.main.hotkey_label('autokey')})"
        )
        self._glow = GlowPulse(self.start_btn)
        right.addWidget(self.start_btn, 0, Qt.AlignRight)
        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(5)
        hotkey_row.addStretch(1)
        hotkey_row.addWidget(label("GLOBAL HOTKEY", "Tiny"))
        self.hotkey_cap = label(self.main.hotkey_label("autokey"), "VersionBadge")
        self.hotkey_cap.setStyleSheet(
            "background: #ffffff; border: 2px solid; border-top-color: #404040; "
            "border-left-color: #404040; border-right-color: #ffffff; "
            "border-bottom-color: #ffffff; color: #000080; "
            "padding: 2px 6px; font-size: 9px; font-weight: 700;"
        )
        hotkey_row.addWidget(self.hotkey_cap)
        right.addLayout(hotkey_row)
        row.addLayout(right)
        outer.addLayout(row)
        self.energy = EnergyLine()
        outer.addWidget(self.energy)
        self.layout.addWidget(hero)

    def _build_binding_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Binding", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("ANY KEY", "Tiny"))
        card.body.addLayout(header)

        self.key_button = make_button("SPACE", "BigKey")
        self.key_button.setMinimumHeight(76)
        self.key_button.setStyleSheet(
            "QPushButton#BigKey { background: #c0c0c0; border: 2px solid; "
            "border-top-color: #ffffff; border-left-color: #ffffff; "
            "border-right-color: #404040; border-bottom-color: #404040; "
            "color: #000080; font-family: 'Courier New'; font-size: 25px; font-weight: 700; }"
            "QPushButton#BigKey:hover { background: #d4d0c8; }"
            "QPushButton#BigKey:pressed { border-top-color: #404040; border-left-color: #404040; "
            "border-right-color: #ffffff; border-bottom-color: #ffffff; }"
            "QPushButton#BigKey[listening=\"true\"] { background: #ffffe1; color: #800000; }"
        )
        self.key_button.setToolTip("Click, then press any key to bind it")
        self.key_button.clicked.connect(self._begin_bind)
        card.body.addWidget(self.key_button)
        self.bind_hint = label("Click to rebind · last captured key wins", "Muted")
        self.bind_hint.setAlignment(Qt.AlignCenter)
        card.body.addWidget(self.bind_hint)
        card.body.addWidget(hline())

        rate_header = QHBoxLayout()
        rate_header.addWidget(label("Press rate", "SectionTitle"))
        rate_header.addStretch(1)
        self.rate_hint = label("", "Tiny")
        rate_header.addWidget(self.rate_hint)
        card.body.addLayout(rate_header)

        rate_row = QHBoxLayout()
        rate_row.setSpacing(12)
        self.rate_spin = QSpinBox()
        self.rate_spin.setObjectName("BigSpin")
        self.rate_spin.setRange(1, 500)
        self.rate_spin.setValue(20)
        self.rate_spin.setAlignment(Qt.AlignCenter)
        self.rate_spin.setFixedWidth(132)
        self.rate_spin.valueChanged.connect(self._on_rate_spin)
        rate_row.addWidget(self.rate_spin)
        labels = QVBoxLayout()
        labels.setSpacing(2)
        labels.addWidget(label("KEYS / SECOND", "SectionTitle"))
        labels.addWidget(label("Up to 500 per second", "Muted"))
        labels.addStretch(1)
        rate_row.addLayout(labels, 1)
        card.body.addLayout(rate_row)
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(1, 500)
        self.rate_slider.setValue(20)
        self.rate_slider.valueChanged.connect(self._on_rate_slider)
        card.body.addWidget(self.rate_slider)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        self._chips = {}
        for value in (5, 10, 20, 50, 100, 250):
            chip = make_button(str(value), "Chip")
            chip.setCheckable(True)
            chip.clicked.connect(lambda checked=False, value=value: self._apply_chip(value))
            self._chip_group.addButton(chip)
            self._chips[value] = chip
            chips.addWidget(chip)
        chips.addStretch(1)
        card.body.addLayout(chips)
        card.body.addWidget(hline())

        hold_header = QHBoxLayout()
        hold_header.addWidget(label("Key hold", "SectionTitle"))
        hold_header.addStretch(1)
        self.hold_hint = label("0 ms = instant tap", "Tiny")
        hold_header.addWidget(self.hold_hint)
        card.body.addLayout(hold_header)
        hold_row = QHBoxLayout()
        hold_row.setSpacing(10)
        self.hold_spin = QSpinBox()
        self.hold_spin.setRange(0, 2000)
        self.hold_spin.setSuffix(" ms")
        self.hold_spin.setValue(0)
        self.hold_spin.setFixedWidth(104)
        self.hold_spin.valueChanged.connect(lambda _v: self._update_summary())
        hold_row.addWidget(self.hold_spin)
        hold_row.addWidget(
            label("Hold each press before releasing — useful for movement or charge keys.", "Muted", wrap=True),
            1,
        )
        card.body.addLayout(hold_row)
        card.body.addWidget(hline())

        astop = QGridLayout()
        astop.setHorizontalSpacing(12)
        astop.setVerticalSpacing(8)
        astop.setColumnStretch(3, 1)
        astop.addWidget(label("Auto-stop", "SectionTitle"), 0, 0)
        astop.addWidget(label("Stop the stream automatically after a limit.", "Tiny"), 0, 1, 1, 3)

        astop.addWidget(label("Presses", "SectionTitle"), 1, 0)
        self.stop_presses_spin = QSpinBox()
        self.stop_presses_spin.setRange(0, 999999)
        self.stop_presses_spin.setValue(0)
        self.stop_presses_spin.setSuffix(" presses")
        self.stop_presses_spin.setFixedWidth(128)
        self.stop_presses_spin.setToolTip("0 disables auto-stop by press count")
        self.stop_presses_spin.valueChanged.connect(lambda _v: self._update_summary())
        astop.addWidget(self.stop_presses_spin, 1, 1)
        astop.addWidget(label("0 = off", "Muted"), 1, 2, 1, 2)

        astop.addWidget(label("Seconds", "SectionTitle"), 2, 0)
        self.stop_seconds_spin = QSpinBox()
        self.stop_seconds_spin.setRange(0, 3600)
        self.stop_seconds_spin.setValue(0)
        self.stop_seconds_spin.setSuffix(" s")
        self.stop_seconds_spin.setFixedWidth(128)
        self.stop_seconds_spin.setToolTip("0 disables auto-stop by time")
        self.stop_seconds_spin.valueChanged.connect(lambda _v: self._update_summary())
        astop.addWidget(self.stop_seconds_spin, 2, 1)
        astop.addWidget(label("0 = off", "Muted"), 2, 2, 1, 2)
        card.body.addLayout(astop)
        return card

    def _build_notes_card(self) -> Card:
        card = Card()
        card.body.addWidget(label("How it works", "CardTitle"))
        for text in (
            "Bind any key — letters, arrows, function keys, even Esc.",
            "Keys are injected natively through Windows SendInput.",
        ):
            row = QHBoxLayout()
            row.setSpacing(9)
            dot = QLabel("●")
            dot.setStyleSheet("color: #000080; font-size: 8px;")
            row.addWidget(dot, 0, Qt.AlignTop)
            row.addWidget(label(text, "Muted", wrap=True), 1)
            card.body.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(9)
        dot = QLabel("●")
        dot.setStyleSheet("color: #000080; font-size: 8px;")
        row.addWidget(dot, 0, Qt.AlignTop)
        self._panic_note = label("", "Muted", wrap=True)
        self._panic_note.setText(
            f"{self.main.hotkey_label('panic')} always cuts input and releases held keys."
        )
        row.addWidget(self._panic_note, 1)
        card.body.addLayout(row)
        return card

    def refresh_hotkeys(self) -> None:
        if hasattr(self, "hotkey_cap"):
            self.hotkey_cap.setText(self.main.hotkey_label("autokey"))
        if hasattr(self, "start_btn"):
            self.start_btn.setToolTip(
                f"Toggle the auto-key engine ({self.main.hotkey_label('autokey')})"
            )
        if hasattr(self, "_panic_note"):
            self._panic_note.setText(
                f"{self.main.hotkey_label('panic')} always cuts input and releases held keys."
            )

    def _build_telemetry_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Live telemetry", "CardTitle"))
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

        self.waves = KeyWaves()
        card.body.addWidget(self.waves)

        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        self.total_tile = StatTile("Keys sent", "0")
        self.time_tile = StatTile("Session", "00:00")
        self.rate_tile = StatTile("Live rate", "0.0")
        tiles.addWidget(self.total_tile)
        tiles.addWidget(self.time_tile)
        tiles.addWidget(self.rate_tile)
        card.body.addLayout(tiles)

        spark_header = QHBoxLayout()
        spark_header.addWidget(label("PRESS THROUGHPUT", "Tiny"))
        spark_header.addStretch(1)
        spark_header.addWidget(label("KEYS / SEC", "Tiny"))
        card.body.addLayout(spark_header)
        self.sparkline = Sparkline(capacity=56)
        card.body.addWidget(self.sparkline)

        self.reset_btn = make_button("Reset statistics", "GhostButton")
        self.reset_btn.clicked.connect(self._reset_stats)
        card.body.addWidget(self.reset_btn, 0, Qt.AlignRight)
        return card

    # ------------------------------------------------------------------
    def _update_key_ui(self) -> None:
        self.key_button.setText(self._key_name.upper())
        self.waves.set_key(self._key_name)
        self.key_button.setToolTip(f"Bound to {self._key_name} — click to rebind")
        self._update_summary()

    def _begin_bind(self) -> None:
        if self._listening:
            self._cancel_capture(notify=True)
            return
        if self.engine.is_active:
            self.main.toast("warning", "Stop the auto-key engine before rebinding.")
            return
        try:
            from pynput import keyboard

            self._capture_listener = keyboard.Listener(on_press=self._listen_key)
            self._capture_listener.daemon = True
            self._capture_listener.start()
        except Exception as exc:
            self._capture_listener = None
            self.main.toast("error", f"Could not start key capture: {exc}")
            return
        self._listening = True
        self.key_button.setText("LISTENING…")
        self.key_button.setProperty("listening", True)
        self.key_button.style().unpolish(self.key_button)
        self.key_button.style().polish(self.key_button)
        self.bind_hint.setText("Press any key now · click the key to cancel")
        self.main.suspend_hotkeys(True)
        self._capture_timeout.start(8000)

    def _listen_key(self, key) -> None:
        vk = pynput_key_to_vk(key)
        if not vk:
            return
        self.key_captured.emit(int(vk), vk_name(int(vk)))

    def _on_key_captured(self, vk: int, name: str) -> None:
        if not self._listening:
            return
        self._finish_capture()
        self._vk = vk
        self._key_name = name
        self._update_key_ui()
        self.main.log("success", f"Auto-key rebound to {name} (VK {vk:02X}).")
        if self.engine.is_active:
            self.main.toast("warning", f"Key updated to {name} — restart the engine to apply.")
        else:
            self.main.toast("success", f"Key bound to {name}.")

    def _cancel_capture(self, notify: bool = False) -> None:
        if not self._listening:
            return
        self._finish_capture()
        if notify:
            self.main.toast("info", "Key capture cancelled.")
            self.main.log("info", "Key capture cancelled.")

    def _finish_capture(self) -> None:
        self._listening = False
        self._capture_timeout.stop()
        self.main.suspend_hotkeys(False)
        if self._capture_listener:
            try:
                self._capture_listener.stop()
            except Exception:
                pass
        self._capture_listener = None
        self.key_button.setProperty("listening", False)
        self.key_button.style().unpolish(self.key_button)
        self.key_button.style().polish(self.key_button)
        self.key_button.setText(self._key_name.upper())
        self.bind_hint.setText("Click to rebind · last captured key wins")

    def _on_rate_spin(self, value: int) -> None:
        if self._guard:
            return
        self._guard = True
        self.rate_slider.setValue(value)
        self._guard = False
        self._sync_rate_controls()

    def _on_rate_slider(self, value: int) -> None:
        if self._guard:
            return
        self._guard = True
        self.rate_spin.setValue(value)
        self._guard = False
        self._sync_rate_controls()

    def _apply_chip(self, value: int) -> None:
        self.rate_spin.setValue(value)
        self.rate_slider.setValue(value)
        self._sync_rate_controls()

    def _sync_rate_controls(self) -> None:
        value = max(1, self.rate_spin.value())
        self.rate_hint.setText(f"{1000.0 / value:.1f} ms between presses")
        self._chip_group.setExclusive(False)
        for candidate, chip in self._chips.items():
            chip.setChecked(candidate == value)
        self._chip_group.setExclusive(True)
        self._update_summary()

    def _update_summary(self) -> None:
        if not hasattr(self, "hero_sub"):
            return
        hold = "instant tap" if self.hold_spin.value() == 0 else f"hold {self.hold_spin.value()} ms"
        parts = [self._key_name.upper(), f"{self.rate_spin.value()} keys/sec", hold]
        if self.stop_presses_spin.value() > 0:
            parts.append(f"stop after {self.stop_presses_spin.value():,} presses")
        if self.stop_seconds_spin.value() > 0:
            parts.append(f"stop after {self.stop_seconds_spin.value()} s")
        self.hero_sub.setText("  ·  ".join(parts))

    # ------------------------------------------------------------------
    def config(self) -> KeyConfig:
        return KeyConfig(
            vk=self._vk,
            key_name=self._key_name,
            rate=float(self.rate_spin.value()),
            hold_ms=self.hold_spin.value(),
            start_delay=self.main.start_delay_s(),
            stop_after_presses=self.stop_presses_spin.value(),
            stop_after_seconds=float(self.stop_seconds_spin.value()),
        )

    def toggle(self) -> None:
        if self.engine.is_active:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.engine.is_active:
            return
        if self._listening:
            self._cancel_capture()
        cfg = self.config()
        self.main.acquire("autokey")
        if not self.engine.start(cfg):
            self.main.release("autokey")
            self.main.toast("error", "Auto-key engine could not start.")
            return
        self._active_ui = True
        self._last_count = 0
        self._last_time = time.perf_counter()
        self._last_push = 0.0
        self._live = 0.0
        self._peak = 0.0
        self._last_error = None
        self._arm_deadline = self._last_time + cfg.start_delay
        self.sparkline.clear()
        self.sparkline.push(0)
        self._set_running_ui(True)
        self.main.log("hotkey", f"Auto-key engaged — {cfg.key_name} at {cfg.rate:g}/sec.")
        self.main.toast("success", f"Auto-key engaged · {cfg.key_name} at {cfg.rate:g}/sec")

    def stop(self, quiet: bool = False) -> None:
        if not self.engine.is_active and not self._active_ui:
            return
        self.engine.stop()
        snapshot = self.engine.snapshot()
        count = int(snapshot.get("count", 0))
        self._active_ui = False
        self._set_running_ui(False)
        self._live = 0.0
        self.total_tile.set_value(f"{count:,}")
        self.rate_tile.set_value("0.0")
        self.time_tile.set_value(format_clock(snapshot.get("elapsed", 0)))
        self.main.release("autokey")
        if not quiet:
            suffix = f" — {count:,} keys" if count else ""
            self.main.log("info", f"Auto-key stopped{suffix}.")
            self.main.toast("info", f"Auto-key stopped{suffix}")

    def force_stop(self) -> bool:
        if self.engine.is_active or self._active_ui:
            self.stop(quiet=True)
            return True
        return False

    def _set_running_ui(self, running: bool) -> None:
        self.start_btn.setText("Stop pressing" if running else "Start pressing")
        self.start_btn.setProperty("running", running)
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)
        if running:
            self._glow.start()
        else:
            self._glow.stop()
        self.energy.set_running(running)
        self.hero_dot.set_state(running, COLORS["accent_2"])
        self.waves.set_active(running)
        self.telemetry_badge.setText("LIVE" if running else "IDLE")
        if running:
            self.telemetry_badge.setStyleSheet(
                "background: #ffffe1; border: 1px solid #000000; "
                "color: #008000; padding: 3px 7px; font-size: 9px; font-weight: 700;"
            )
            self.hero_status.setText("Key engine engaged")
        else:
            self.telemetry_badge.setStyleSheet(
                "background: #c0c0c0; border: 2px solid; border-top-color: #ffffff; "
                "border-left-color: #ffffff; border-right-color: #404040; "
                "border-bottom-color: #404040; color: #404040; "
                "padding: 3px 7px; font-size: 9px; font-weight: 700;"
            )
            self.hero_status.setText("Key engine standby")
            self.reset_btn.setEnabled(True)
        self._last_time = time.perf_counter()
        self._last_count = self.engine.snapshot().get("count", 0)

    def _tick(self) -> None:
        snapshot = self.engine.snapshot()
        active = bool(snapshot.get("active"))
        error = snapshot.get("error")
        if error and error != self._last_error:
            self._last_error = error
            self.main.toast("error", error)
            self.main.log("error", error)
            self.stop(quiet=True)
        now = time.perf_counter()
        count = int(snapshot.get("count", 0))
        if active and self._active_ui:
            if now < self._arm_deadline:
                remaining = max(0.0, self._arm_deadline - now)
                self.hero_status.setText(f"Arming in {remaining:.1f}s")
            else:
                if count > 0:
                    elapsed = max(1e-6, now - self._last_time)
                    raw = (count - self._last_count) / elapsed
                    self._live = raw if self._live <= 0 else self._live * 0.55 + raw * 0.45
                    self._last_count = count
                    self._last_time = now
                self.hero_status.setText(f"Pressing {self._key_name} · {self._live:,.0f}/sec")
                if now - self._last_push >= 0.3:
                    self.sparkline.push(self._live)
                    self._last_push = now
            self.total_tile.set_value(f"{count:,}")
            self.time_tile.set_value(format_clock(snapshot.get("elapsed", 0)))
            self.rate_tile.set_value(f"{self._live:,.1f}")
            self.reset_btn.setEnabled(False)
        elif self._active_ui and not active:
            self._active_ui = False
            self._set_running_ui(False)
            self._live = 0.0
            self.rate_tile.set_value("0.0")
            self.sparkline.push(0)
            self.main.release("autokey")

    def _reset_stats(self) -> None:
        if self.engine.is_active:
            self.main.toast("warning", "Stop the engine before resetting statistics.")
            return
        self._peak = 0.0
        self._live = 0.0
        self.total_tile.set_value("0")
        self.time_tile.set_value("00:00")
        self.rate_tile.set_value("0.0")
        self.sparkline.clear()
        self.main.toast("info", "Statistics cleared.")
