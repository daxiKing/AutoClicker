"""Primary auto-clicker page."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import wininput
from ...core.engine import AutoClicker, ClickConfig
from ...core.macros import format_clock
from ..theme import COLORS
from ..widgets import (
    Card,
    EnergyLine,
    GlowPulse,
    HeroCard,
    PulseDot,
    RingGauge,
    SegmentedControl,
    Sparkline,
    StatTile,
    ToggleSwitch,
    hline,
    label,
    make_button,
    pointer,
)
from .base import Page


class ClickerPage(Page):
    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self.engine = AutoClicker()
        self._active_ui = False
        self._capturing = False
        self._last_count = 0
        self._last_time = time.perf_counter()
        self._last_push = 0.0
        self._live = 0.0
        self._peak = 0.0
        self._arm_deadline = 0.0
        self._last_error: str | None = None
        self._guard = False

        self._build_hero()
        columns = QHBoxLayout()
        columns.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(self._build_engine_card())
        left.addWidget(self._build_presets_card())
        left.addWidget(self._build_target_card())
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self._build_telemetry_card())
        right.addWidget(self._build_notes_card())
        right.addStretch(1)
        columns.addLayout(left, 5)
        columns.addLayout(right, 4)
        self.layout.addLayout(columns)

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self.main.position_picked.connect(self._on_position_picked)
        self.main.position_pick_cancelled.connect(self._on_position_cancelled)

        self._sync_rate_controls()
        self._sync_position_controls()
        self._sync_hold_control()
        self._update_summary()

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    def _make_start_button(self):
        button = make_button("Start clicking", "StartButton")
        button.setMinimumWidth(190)
        button.setMinimumHeight(54)
        button.setToolTip(f"Toggle the click engine ({self.main.hotkey_label('clicker')})")
        button.clicked.connect(self.toggle)
        return button

    def _build_hero(self) -> None:
        hero = HeroCard()
        outer = QVBoxLayout(hero)
        outer.setContentsMargins(22, 17, 22, 14)
        outer.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(4)

        eyebrow_row = QHBoxLayout()
        eyebrow_row.setSpacing(4)
        self.hero_dot = PulseDot(COLORS["faint"], 8)
        eyebrow_row.addWidget(self.hero_dot)
        eyebrow_row.addWidget(label("CLICK ENGINE", "Eyebrow"))
        eyebrow_row.addStretch(1)
        left.addLayout(eyebrow_row)

        self.hero_status = label("Engine standby", "HeroTitle")
        left.addWidget(self.hero_status)
        self.hero_sub = label("", "HeroSub")
        left.addWidget(self.hero_sub)
        row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(5)
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.start_btn = self._make_start_button()
        self._glow = GlowPulse(self.start_btn)
        right.addWidget(self.start_btn, 0, Qt.AlignRight)

        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(5)
        hotkey_row.addStretch(1)
        hotkey_row.addWidget(label("GLOBAL HOTKEY", "Tiny"))
        self.hotkey_cap = label(self.main.hotkey_label("clicker"), "VersionBadge")
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

    def _build_engine_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(label("Click rate", "CardTitle"))
        title_box.addWidget(label("Dial in the exact pressure you need.", "Muted"))
        header.addLayout(title_box, 1)
        uncap_box = QVBoxLayout()
        uncap_box.setSpacing(2)
        self.uncapped_toggle = ToggleSwitch(False)
        self.uncapped_toggle.setToolTip("Remove the interval cap and fire as fast as Windows allows")
        self.uncapped_toggle.toggled.connect(self._on_uncapped_changed)
        uncap_row = QHBoxLayout()
        uncap_row.setSpacing(8)
        uncap_row.addStretch(1)
        uncap_row.addWidget(label("UNCAPPED", "Tiny"))
        uncap_row.addWidget(self.uncapped_toggle)
        uncap_box.addLayout(uncap_row)
        header.addLayout(uncap_box)
        card.body.addLayout(header)

        rate_row = QHBoxLayout()
        rate_row.setSpacing(12)
        self.cps_spin = QSpinBox()
        self.cps_spin.setObjectName("BigSpin")
        self.cps_spin.setRange(1, 1000)
        self.cps_spin.setValue(100)
        self.cps_spin.setAlignment(Qt.AlignCenter)
        self.cps_spin.setFixedWidth(142)
        self.cps_spin.setToolTip("Clicks per second (1–1,000)")
        self.cps_spin.valueChanged.connect(self._on_cps_spin)
        rate_row.addWidget(self.cps_spin)
        rate_labels = QVBoxLayout()
        rate_labels.setSpacing(2)
        rate_labels.addWidget(label("CLICKS / SECOND", "SectionTitle"))
        self.rate_hint = label("Steady pacing · 10 ms interval", "Muted")
        rate_labels.addWidget(self.rate_hint)
        rate_labels.addStretch(1)
        rate_row.addLayout(rate_labels, 1)
        card.body.addLayout(rate_row)

        self.cps_slider = QSlider(Qt.Horizontal)
        self.cps_slider.setRange(1, 1000)
        self.cps_slider.setValue(100)
        self.cps_slider.setPageStep(25)
        self.cps_slider.valueChanged.connect(self._on_cps_slider)
        card.body.addWidget(self.cps_slider)

        presets = QHBoxLayout()
        presets.setSpacing(6)
        self._preset_group = QButtonGroup(self)
        self._preset_group.setExclusive(True)
        self._preset_buttons = {}
        for value in (25, 50, 100, 250, 500, 1000):
            button = make_button(f"{value:,}", "Chip")
            button.setCheckable(True)
            button.setToolTip(f"Set {value:,} clicks per second")
            button.clicked.connect(lambda checked=False, value=value: self._apply_preset(value))
            self._preset_group.addButton(button)
            self._preset_buttons[value] = button
            presets.addWidget(button)
        self.max_chip = make_button("MAX", "Chip")
        self.max_chip.setCheckable(True)
        self.max_chip.setToolTip("Uncapped burst mode")
        self.max_chip.clicked.connect(self._max_preset)
        presets.addWidget(self.max_chip)
        presets.addStretch(1)
        card.body.addLayout(presets)

        self.uncapped_hint = label(
            "Uncapped mode sends input with zero interval. It is deliberately extreme — "
            f"use {self.main.hotkey_label('panic')} to stop.",
            "Tiny",
            wrap=True,
        )
        self.uncapped_hint.setVisible(False)
        card.body.addWidget(self.uncapped_hint)
        card.body.addWidget(hline())

        # ------------------------------------------------------------------
        # Auto-stop
        # ------------------------------------------------------------------
        astop = QGridLayout()
        astop.setHorizontalSpacing(12)
        astop.setVerticalSpacing(8)
        astop.setColumnStretch(3, 1)
        astop.addWidget(label("Auto-stop", "SectionTitle"), 0, 0)
        astop.addWidget(label("Stop the engine automatically after a limit.", "Tiny"), 0, 1, 1, 3)

        astop.addWidget(label("Clicks", "SectionTitle"), 1, 0)
        self.stop_clicks_spin = QSpinBox()
        self.stop_clicks_spin.setRange(0, 999999)
        self.stop_clicks_spin.setValue(0)
        self.stop_clicks_spin.setSuffix(" clicks")
        self.stop_clicks_spin.setFixedWidth(128)
        self.stop_clicks_spin.setToolTip("0 disables auto-stop by click count")
        self.stop_clicks_spin.valueChanged.connect(lambda _v: self._update_summary())
        astop.addWidget(self.stop_clicks_spin, 1, 1)
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

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        grid.addWidget(label("Mouse button", "SectionTitle"), 0, 0)
        self.button_segment = SegmentedControl([("left", "Left"), ("right", "Right"), ("middle", "Middle")])
        self.button_segment.changed.connect(lambda _key: self._update_summary())
        grid.addWidget(self.button_segment, 0, 1, 1, 2)

        grid.addWidget(label("Click style", "SectionTitle"), 1, 0)
        self.style_segment = SegmentedControl([("single", "Single"), ("double", "Double"), ("hold", "Hold")])
        self.style_segment.changed.connect(self._on_style_changed)
        grid.addWidget(self.style_segment, 1, 1, 1, 2)

        grid.addWidget(label("Hold duration", "SectionTitle"), 2, 0)
        hold_row = QHBoxLayout()
        hold_row.setSpacing(8)
        self.hold_spin = QSpinBox()
        self.hold_spin.setRange(1, 1000)
        self.hold_spin.setValue(80)
        self.hold_spin.setSuffix(" ms")
        self.hold_spin.setFixedWidth(108)
        self.hold_spin.valueChanged.connect(lambda _v: self._update_summary())
        hold_row.addWidget(self.hold_spin)
        self.hold_hint = label("Used by hold-style clicks", "Tiny")
        hold_row.addWidget(self.hold_hint)
        hold_row.addStretch(1)
        grid.addLayout(hold_row, 2, 1, 1, 2)

        card.body.addLayout(grid)
        return card

    def _build_target_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Targeting", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("PRECISION LAYER", "Tiny"))
        card.body.addLayout(header)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(label("Click position", "SectionTitle"))
        self.position_segment = SegmentedControl([("cursor", "Cursor"), ("fixed", "Fixed point")])
        self.position_segment.changed.connect(self._on_position_mode)
        row.addWidget(self.position_segment, 1)
        card.body.addLayout(row)

        self.fixed_widget = QWidget()
        fixed_row = QHBoxLayout(self.fixed_widget)
        fixed_row.setContentsMargins(0, 0, 0, 0)
        fixed_row.setSpacing(8)
        fixed_row.addWidget(label("X", "Muted"))
        self.x_spin = QSpinBox()
        self.x_spin.setRange(-20000, 20000)
        self.x_spin.setFixedWidth(88)
        self.x_spin.valueChanged.connect(lambda _v: self._update_summary())
        fixed_row.addWidget(self.x_spin)
        fixed_row.addWidget(label("Y", "Muted"))
        self.y_spin = QSpinBox()
        self.y_spin.setRange(-20000, 20000)
        self.y_spin.setFixedWidth(88)
        self.y_spin.valueChanged.connect(lambda _v: self._update_summary())
        fixed_row.addWidget(self.y_spin)
        self.use_cursor_btn = make_button("Use cursor", "GhostButton")
        self.use_cursor_btn.setToolTip("Copy the current cursor position")
        self.use_cursor_btn.clicked.connect(self._use_current_cursor)
        fixed_row.addWidget(self.use_cursor_btn)
        self.pick_btn = make_button("Pick spot", "GhostButton")
        self.pick_btn.setToolTip("Hide the window and capture the next click")
        self.pick_btn.clicked.connect(self._pick_position)
        fixed_row.addWidget(self.pick_btn)
        fixed_row.addStretch(1)
        card.body.addWidget(self.fixed_widget)
        card.body.addWidget(hline())

        advanced = QGridLayout()
        advanced.setHorizontalSpacing(12)
        advanced.setVerticalSpacing(8)
        advanced.setColumnStretch(3, 1)
        advanced.addWidget(label("Position jitter", "SectionTitle"), 0, 0)
        self.jitter_spin = QSpinBox()
        self.jitter_spin.setRange(0, 100)
        self.jitter_spin.setSuffix(" px")
        self.jitter_spin.setFixedWidth(88)
        self.jitter_spin.setToolTip("Scatter fixed-point clicks within this radius")
        advanced.addWidget(self.jitter_spin, 0, 1)
        self.jitter_hint = label("Scatters fixed-point clicks", "Tiny")
        advanced.addWidget(self.jitter_hint, 0, 2, 1, 2)

        advanced.addWidget(label("Timing chaos", "SectionTitle"), 1, 0)
        self.chaos_spin = QSpinBox()
        self.chaos_spin.setRange(0, 50)
        self.chaos_spin.setSuffix(" %")
        self.chaos_spin.setFixedWidth(88)
        self.chaos_spin.setToolTip("Randomizes the interval by up to this percentage")
        advanced.addWidget(self.chaos_spin, 1, 1)
        advanced.addWidget(label("Human-like interval variance", "Tiny"), 1, 2, 1, 2)
        card.body.addLayout(advanced)
        return card

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

        self.gauge = RingGauge()
        self.gauge.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.gauge.setFixedHeight(224)
        card.body.addWidget(self.gauge, 0, Qt.AlignHCenter)

        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        self.total_tile = StatTile("Total clicks", "0")
        self.time_tile = StatTile("Session", "00:00")
        self.peak_tile = StatTile("Peak", "0.0")
        tiles.addWidget(self.total_tile)
        tiles.addWidget(self.time_tile)
        tiles.addWidget(self.peak_tile)
        card.body.addLayout(tiles)

        spark_header = QHBoxLayout()
        spark_header.addWidget(label("THROUGHPUT", "Tiny"))
        spark_header.addStretch(1)
        spark_header.addWidget(label("LAST ~19 SECONDS", "Tiny"))
        card.body.addLayout(spark_header)
        self.sparkline = Sparkline()
        card.body.addWidget(self.sparkline)

        self.reset_stats_btn = make_button("Reset statistics", "GhostButton")
        self.reset_stats_btn.clicked.connect(self._reset_stats)
        card.body.addWidget(self.reset_stats_btn, 0, Qt.AlignRight)
        return card

    def _build_notes_card(self) -> Card:
        card = Card()
        card.body.addWidget(label("Field notes", "CardTitle"))
        notes = [
            ("panic", "Panic stop — cuts every engine and releases held input."),
            ("clicker", "Start or stop the click engine from anywhere."),
            ("MAX", "Uncapped mode bypasses pacing entirely. Use with intent."),
        ]
        self._note_badges: list[tuple[QLabel, str]] = []
        for action, text in notes:
            row = QHBoxLayout()
            row.setSpacing(9)
            badge = label(
                self.main.hotkey_label(action) if action != "MAX" else action,
                "VersionBadge",
            )
            badge.setAlignment(Qt.AlignCenter)
            badge.setMinimumWidth(34)
            row.addWidget(badge, 0, Qt.AlignTop)
            description = label(text, "Muted", wrap=True)
            row.addWidget(description, 1)
            card.body.addLayout(row)
            self._note_badges.append((badge, action))
        return card

    # ------------------------------------------------------------------
    # Hotkey labels
    # ------------------------------------------------------------------
    def refresh_hotkeys(self) -> None:
        if hasattr(self, "hotkey_cap"):
            self.hotkey_cap.setText(self.main.hotkey_label("clicker"))
        for badge, action in getattr(self, "_note_badges", []):
            if action != "MAX":
                badge.setText(self.main.hotkey_label(action))
        if hasattr(self, "start_btn"):
            self.start_btn.setToolTip(
                f"Toggle the click engine ({self.main.hotkey_label('clicker')})"
            )
        if hasattr(self, "uncapped_hint"):
            self.uncapped_hint.setText(
                "Uncapped mode sends input with zero interval. It is deliberately extreme — "
                f"use {self.main.hotkey_label('panic')} to stop."
            )

    # ------------------------------------------------------------------
    # UI sync
    # ------------------------------------------------------------------
    def _sync_rate_controls(self) -> None:
        uncapped = self.uncapped_toggle.isChecked()
        self.cps_spin.setEnabled(not uncapped)
        self.cps_slider.setEnabled(not uncapped)
        for button in self._preset_buttons.values():
            button.setEnabled(not uncapped)
        self.max_chip.setChecked(uncapped)
        self.uncapped_hint.setVisible(uncapped)
        if uncapped:
            self.rate_hint.setText("Burst mode · no interval cap")
            self.gauge.set_scale(2000)
        else:
            cps = max(1, self.cps_spin.value())
            interval_ms = 1000.0 / cps
            self.rate_hint.setText(f"Steady pacing · {interval_ms:.1f} ms interval")
            self.gauge.set_scale(1000)
        self._update_preset_checks()
        self._update_summary()

    def _update_preset_checks(self) -> None:
        value = self.cps_spin.value()
        checked = self._preset_buttons.get(value)
        self._preset_group.setExclusive(False)
        for candidate, button in self._preset_buttons.items():
            button.setChecked(button is checked and not self.uncapped_toggle.isChecked())
        self._preset_group.setExclusive(True)

    def _sync_position_controls(self) -> None:
        fixed = self.position_segment.current_key() == "fixed"
        self.fixed_widget.setEnabled(fixed)
        if fixed and self.x_spin.value() == 0 and self.y_spin.value() == 0:
            x, y = wininput.cursor_position()
            if x or y:
                self.x_spin.setValue(x)
                self.y_spin.setValue(y)
        self._update_summary()

    def _sync_hold_control(self) -> None:
        hold = self.style_segment.current_key() == "hold"
        self.hold_spin.setEnabled(hold)
        self.hold_hint.setText("Used by hold-style clicks" if hold else "Switch style to Hold to use")
        self.hold_hint.setStyleSheet("color: #808080;" if not hold else "")

    def _on_cps_spin(self, value: int) -> None:
        if self._guard:
            return
        self._guard = True
        self.cps_slider.setValue(value)
        self._guard = False
        self._sync_rate_controls()

    def _on_cps_slider(self, value: int) -> None:
        if self._guard:
            return
        self._guard = True
        self.cps_spin.setValue(value)
        self._guard = False
        self._sync_rate_controls()

    def _apply_preset(self, value: int) -> None:
        if self.uncapped_toggle.isChecked():
            self.uncapped_toggle.setChecked(False)
        self.cps_spin.setValue(value)
        self.cps_slider.setValue(value)
        self._sync_rate_controls()

    def _max_preset(self) -> None:
        self.uncapped_toggle.setChecked(True)

    def _on_uncapped_changed(self, checked: bool) -> None:
        self._sync_rate_controls()

    def _on_style_changed(self, _key: str) -> None:
        self._sync_hold_control()
        self._update_summary()

    def _on_position_mode(self, _key: str) -> None:
        self._sync_position_controls()

    def _update_summary(self) -> None:
        if not hasattr(self, "hero_sub"):
            return
        button = self.button_segment.current_key().capitalize()
        style = {"single": "Single click", "double": "Double click", "hold": "Hold"}[self.style_segment.current_key()]
        if self.position_segment.current_key() == "fixed":
            position = f"Fixed {self.x_spin.value():,}, {self.y_spin.value():,}"
        else:
            position = "Cursor position"
        rate = "Uncapped burst" if self.uncapped_toggle.isChecked() else f"{self.cps_spin.value():,} CPS"
        parts = [rate, button, style, position]
        if self.stop_clicks_spin.value() > 0:
            parts.append(f"stop after {self.stop_clicks_spin.value():,} clicks")
        if self.stop_seconds_spin.value() > 0:
            parts.append(f"stop after {self.stop_seconds_spin.value()} s")
        self.hero_sub.setText("  ·  ".join(parts))

    def _use_current_cursor(self) -> None:
        x, y = wininput.cursor_position()
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        self.position_segment.set_current("fixed")
        self._sync_position_controls()
        self.main.log("info", f"Fixed position captured at {x}, {y}.")
        self.main.toast("success", f"Fixed point set to {x}, {y}.")

    def _pick_position(self) -> None:
        if self._capturing:
            return
        if self.engine.is_active:
            self.main.toast("warning", "Stop the click engine before picking a target.")
            return
        self._capturing = True
        self.pick_btn.setEnabled(False)
        self.pick_btn.setText("Arming…")
        self.main.toast("info", "Pick mode armed — aim and hold. Locks in 3 seconds. Esc cancels.")
        self.main.log("info", "Position picker armed — overlay countdown active.")
        self.main.capture_position(delay_s=3.0)

    def _on_position_picked(self, x: int, y: int) -> None:
        self._capturing = False
        self.pick_btn.setEnabled(True)
        self.pick_btn.setText("Pick spot")
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        self.position_segment.set_current("fixed")
        self._sync_position_controls()
        self.main.log("success", f"Picked fixed position at {x}, {y}.")
        self.main.toast("success", f"Fixed point set to {x}, {y}.")

    def _on_position_cancelled(self) -> None:
        self._capturing = False
        self.pick_btn.setEnabled(True)
        self.pick_btn.setText("Pick spot")
        self.main.toast("info", "Position picker cancelled.")
        self.main.log("info", "Position picker cancelled.")

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------
    def _build_presets_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Presets", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("SAVE & RESTORE", "Tiny"))
        card.body.addLayout(header)
        card.body.addWidget(
            label(
                "A preset stores the whole setup — rate, button, style, position, "
                "jitter, chaos and auto-stop.",
                "Muted",
                wrap=True,
            )
        )
        row = QHBoxLayout()
        row.setSpacing(8)
        self.profile_combo = QComboBox()
        self.profile_combo.setFixedWidth(168)
        self.profile_combo.setToolTip("Choose a saved preset to restore")
        row.addWidget(self.profile_combo, 1)
        load_btn = make_button("Load", "GhostButton")
        load_btn.clicked.connect(self._load_profile)
        row.addWidget(load_btn)
        save_btn = make_button("Save", "GhostButton")
        save_btn.clicked.connect(self._save_profile)
        row.addWidget(save_btn)
        delete_btn = make_button("Delete", "GhostButton")
        delete_btn.clicked.connect(self._delete_profile)
        row.addWidget(delete_btn)
        card.body.addLayout(row)
        self._refresh_profile_combo()
        return card

    def _profiles(self) -> dict:
        data = self.main.settings.get("clicker_presets", {})
        return dict(data) if isinstance(data, dict) else {}

    def _refresh_profile_combo(self, select: str | None = None) -> None:
        if not hasattr(self, "profile_combo"):
            return
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        profiles = self._profiles()
        names = sorted(profiles)
        if names:
            self.profile_combo.addItems(names)
        self.profile_combo.setCurrentText(select) if select in profiles else self.profile_combo.setCurrentIndex(-1)
        self.profile_combo.blockSignals(False)

    def _profile_snapshot(self) -> dict:
        return {
            "cps": self.cps_spin.value(),
            "uncapped": self.uncapped_toggle.isChecked(),
            "button": self.button_segment.current_key(),
            "style": self.style_segment.current_key(),
            "hold_ms": self.hold_spin.value(),
            "position": self.position_segment.current_key(),
            "x": self.x_spin.value(),
            "y": self.y_spin.value(),
            "jitter": self.jitter_spin.value(),
            "chaos": self.chaos_spin.value(),
            "stop_clicks": self.stop_clicks_spin.value(),
            "stop_seconds": self.stop_seconds_spin.value(),
        }

    def _apply_profile_data(self, data: dict) -> None:
        data = data if isinstance(data, dict) else {}
        self.cps_spin.setValue(max(1, int(data.get("cps", 100))))
        self.uncapped_toggle.setChecked(bool(data.get("uncapped", False)))
        button = str(data.get("button", "left"))
        self.button_segment.set_current(button if button in ("left", "right", "middle") else "left")
        style = str(data.get("style", "single"))
        self.style_segment.set_current(style if style in ("single", "double", "hold") else "single")
        self.hold_spin.setValue(max(1, int(data.get("hold_ms", 80))))
        position = str(data.get("position", "cursor"))
        self.position_segment.set_current(position if position in ("cursor", "fixed") else "cursor")
        self.x_spin.setValue(int(data.get("x", 0)))
        self.y_spin.setValue(int(data.get("y", 0)))
        self.jitter_spin.setValue(max(0, int(data.get("jitter", 0))))
        self.chaos_spin.setValue(max(0, int(data.get("chaos", 0))))
        self.stop_clicks_spin.setValue(max(0, int(data.get("stop_clicks", 0))))
        self.stop_seconds_spin.setValue(max(0, int(data.get("stop_seconds", 0))))
        self._sync_rate_controls()
        self._sync_hold_control()
        self._sync_position_controls()
        self._update_summary()

    def _save_profile(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Save preset", "Preset name:", text=self.profile_combo.currentText().strip()
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            self.main.toast("warning", "Preset name cannot be empty.")
            return
        profiles = self._profiles()
        profiles[name] = self._profile_snapshot()
        self.main.settings.set("clicker_presets", profiles)
        self._refresh_profile_combo(select=name)
        self.main.log("success", f"Saved preset {name}.")
        self.main.toast("success", f"Preset {name} saved.")

    def _load_profile(self) -> None:
        name = self.profile_combo.currentText().strip()
        profiles = self._profiles()
        if not name or name not in profiles:
            self.main.toast("warning", "Select a preset to load first.")
            return
        if self.engine.is_active:
            self.main.toast("warning", "Stop the click engine before loading a preset.")
            return
        self._apply_profile_data(profiles[name])
        self.main.log("success", f"Loaded preset {name}.")
        self.main.toast("success", f"Preset {name} loaded.")

    def _delete_profile(self) -> None:
        name = self.profile_combo.currentText().strip()
        profiles = self._profiles()
        if not name or name not in profiles:
            self.main.toast("warning", "Select a preset to delete first.")
            return
        if self.main.settings.get("confirm_delete", True):
            answer = QMessageBox.question(
                self,
                "Delete preset",
                f"Delete preset {name}?\n\nThis cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        profiles.pop(name, None)
        self.main.settings.set("clicker_presets", profiles)
        self._refresh_profile_combo()
        self.main.log("info", f"Deleted preset {name}.")
        self.main.toast("info", f"Preset {name} deleted.")

    # ------------------------------------------------------------------
    # Engine control
    # ------------------------------------------------------------------
    def config(self) -> ClickConfig:
        fixed = self.position_segment.current_key() == "fixed"
        return ClickConfig(
            cps=float(self.cps_spin.value()),
            uncapped=self.uncapped_toggle.isChecked(),
            button=self.button_segment.current_key(),
            click_type=self.style_segment.current_key(),
            hold_ms=self.hold_spin.value(),
            x=self.x_spin.value() if fixed else None,
            y=self.y_spin.value() if fixed else None,
            jitter_px=self.jitter_spin.value(),
            chaos_pct=self.chaos_spin.value(),
            start_delay=self.main.start_delay_s(),
            stop_after_clicks=self.stop_clicks_spin.value(),
            stop_after_seconds=float(self.stop_seconds_spin.value()),
            click_sound=bool(self.main.settings.get("click_sound", False)),
            target_window=str(self.main.settings.get("target_window", "")),
        )

    def toggle(self) -> None:
        if self.engine.is_active:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.engine.is_active:
            return
        cfg = self.config()
        self.main.acquire("clicker")
        if not self.engine.start(cfg):
            self.main.release("clicker")
            self.main.toast("error", "Click engine could not start.")
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
        self.gauge.set_value(0, animate=False)
        self._set_running_ui(True)
        rate = "UNCAPPED" if cfg.uncapped else f"{cfg.cps:,.0f} CPS"
        detail = f"{rate} · {cfg.button} · {cfg.click_type}"
        self.main.log("hotkey", f"Click engine engaged — {detail}.")
        self.main.toast("success", f"Click engine engaged · {rate}")

    def stop(self, quiet: bool = False) -> None:
        was_active = self.engine.is_active
        if not was_active and not self._active_ui:
            return
        self.engine.stop()
        snapshot = self.engine.snapshot()
        count = int(snapshot.get("count", 0))
        self._active_ui = False
        self._set_running_ui(False)
        self._live = 0.0
        self._live_display_reset()
        self.main.release("clicker")
        if not quiet:
            suffix = f" — {count:,} clicks" if count else ""
            self.main.log("info", f"Click engine stopped{suffix}.")
            self.main.toast("info", f"Click engine stopped{suffix}")

    def force_stop(self) -> bool:
        if self.engine.is_active or self._active_ui:
            self.stop(quiet=True)
            return True
        return False

    def _set_running_ui(self, running: bool) -> None:
        self.start_btn.setText("Stop clicking" if running else "Start clicking")
        self.start_btn.setProperty("running", running)
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)
        if running:
            self._glow.start()
        else:
            self._glow.stop()
        self.energy.set_running(running)
        self.hero_dot.set_state(running, COLORS["accent"])
        self.telemetry_badge.setText("LIVE" if running else "IDLE")
        if running:
            self.telemetry_badge.setStyleSheet(
                "background: #ffffe1; border: 1px solid #000000; "
                "color: #008000; padding: 3px 7px; font-size: 9px; font-weight: 700;"
            )
            self.hero_status.setText("Click engine engaged")
        else:
            self.telemetry_badge.setStyleSheet(
                "background: #c0c0c0; border: 2px solid; border-top-color: #ffffff; "
                "border-left-color: #ffffff; border-right-color: #404040; "
                "border-bottom-color: #404040; color: #404040; "
                "padding: 3px 7px; font-size: 9px; font-weight: 700;"
            )
            self.hero_status.setText("Engine standby")
            self.reset_stats_btn.setEnabled(True)
        self._last_time = time.perf_counter()
        self._last_count = self.engine.snapshot().get("count", 0)
        self._last_push = 0.0

    def _live_display_reset(self) -> None:
        self.gauge.set_value(0)
        self.sparkline.push(0)
        self.telemetry_badge.setText("IDLE")
        self.total_tile.set_value(f"{self.engine.snapshot().get('count', 0):,}")
        self.time_tile.set_value(format_clock(self.engine.snapshot().get("elapsed", 0)))
        self.peak_tile.set_value(f"{self._peak:,.1f}")
        self.hero_status.setText("Engine standby")

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
                    self._peak = max(self._peak, self._live)
                    self._last_count = count
                    self._last_time = now
                if now - self._last_push >= 0.3:
                    self.sparkline.push(self._live)
                    self._last_push = now
                self.hero_status.setText(f"Clicking at {self._live:,.0f} CPS")
            self.gauge.set_value(self._live)
            self.total_tile.set_value(f"{count:,}")
            self.time_tile.set_value(format_clock(snapshot.get("elapsed", 0)))
            self.peak_tile.set_value(f"{self._peak:,.1f}")
            self.reset_stats_btn.setEnabled(False)
            if self.uncapped_toggle.isChecked() and self._peak > self.gauge._max_value:
                self.gauge.set_scale(math.ceil(self._peak / 1000) * 1000)
        elif self._active_ui and not active:
            self._active_ui = False
            self._set_running_ui(False)
            self._live = 0.0
            self.gauge.set_value(0)
            self._live_display_reset()
            self.main.release("clicker")

    def _reset_stats(self) -> None:
        if self.engine.is_active:
            self.main.toast("warning", "Stop the engine before resetting statistics.")
            return
        self._peak = 0.0
        self._live = 0.0
        self.gauge.set_value(0)
        self.sparkline.clear()
        self.total_tile.set_value("0")
        self.time_tile.set_value("00:00")
        self.peak_tile.set_value("0.0")
        self.main.toast("info", "Statistics cleared.")
