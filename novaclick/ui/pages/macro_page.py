"""Macro recording, library, timeline and playback page."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.macros import (
    MacroPlayer,
    MacroRecorder,
    MacroStore,
    event_breakdown,
    format_clock,
    format_duration,
    macro_summary,
)
from ..theme import COLORS
from ..macro_editor import MacroEditorDialog
from ..widgets import (
    Card,
    EnergyLine,
    HeroCard,
    MacroTimeline,
    PulseDot,
    StatTile,
    hline,
    label,
    make_button,
)
from .base import Page


class MacroRow(QWidget):
    def __init__(self, macro: dict) -> None:
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        dot = QLabel("▶")
        dot.setStyleSheet("color: #000080; font-size: 9px;")
        dot.setFixedWidth(14)
        layout.addWidget(dot, 0, Qt.AlignTop)
        text_box = QVBoxLayout()
        text_box.setSpacing(3)
        name = label(macro.get("name", "Untitled"), "SectionTitle")
        name.setStyleSheet("font-size: 12px; font-weight: 700; color: #000000;")
        text_box.addWidget(name)
        counts = event_breakdown(macro)
        meta = (
            f"{format_duration(macro.get('duration', 0))}  ·  "
            f"{len(macro.get('events', [])):,} events  ·  "
            f"{counts['clicks']:,} click events"
        )
        text_box.addWidget(label(meta, "Tiny"))
        layout.addLayout(text_box, 1)
        badge = label(f"{macro.get('duration', 0) / 1000:.1f}s", "VersionBadge")
        badge.setStyleSheet(
            "background: #ffffff; border: 2px solid; border-top-color: #404040; "
            "border-left-color: #404040; border-right-color: #ffffff; "
            "border-bottom-color: #ffffff; color: #000080; "
            "padding: 3px 7px; font-size: 9px; font-weight: 700;"
        )
        layout.addWidget(badge, 0, Qt.AlignVCenter)


class MacroPage(Page):
    playback_finished = Signal(bool)

    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self.store = MacroStore()
        self.store.load()
        self.recorder = MacroRecorder()
        self.player = MacroPlayer()
        self.player.finished_callback = lambda finished: self.playback_finished.emit(bool(finished))
        self.playback_finished.connect(self._on_playback_finished)

        self._armed = False
        self._arm_deadline = 0.0
        self._recording = False
        self._playing = False
        self._playing_name = ""
        self._playing_duration = 0.0
        self._manual_stop = False
        self._selected_id: str | None = None
        self._last_selection_refresh = 0.0

        self._build_hero()
        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._build_library_card(), 5)
        columns.addWidget(self._build_details_card(), 6)
        self.layout.addLayout(columns)
        self.layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        if self.store.load_errors:
            for error in self.store.load_errors:
                self.main.log("warning", f"Macro library: {error}")
        self._refresh_list()
        self.parent_window_ready()

    def parent_window_ready(self) -> None:
        self.main.log("info", f"Macro vault loaded — {len(self.store.all())} macro(s).")

    # ------------------------------------------------------------------
    # Construction
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
        eyebrow.addWidget(label("MACRO STUDIO", "Eyebrow"))
        eyebrow.addStretch(1)
        left.addLayout(eyebrow)
        self.hero_status = label("Capture once. Replay forever.", "HeroTitle")
        left.addWidget(self.hero_status)
        self.hero_sub = label(
            "No duration limit  ·  Native-speed replay  ·  Loop until you say stop",
            "HeroSub",
        )
        left.addWidget(self.hero_sub)
        row.addLayout(left, 1)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        record_box = QVBoxLayout()
        record_box.setSpacing(4)
        self.record_btn = make_button("●  Record macro", "RecordButton")
        self.record_btn.setMinimumHeight(46)
        self.record_btn.setMinimumWidth(168)
        self.record_btn.setToolTip(
            f"Start or stop recording ({self.main.hotkey_label('record')})"
        )
        self.record_btn.clicked.connect(self.toggle_record)
        record_box.addWidget(self.record_btn)
        rec_hint = QHBoxLayout()
        rec_hint.setSpacing(4)
        rec_hint.addStretch(1)
        self._record_hint_key = label(self.main.hotkey_label("record"), "VersionBadge")
        rec_hint.addWidget(self._record_hint_key)
        rec_hint.addWidget(label("start / stop", "Tiny"))
        record_box.addLayout(rec_hint)
        actions.addLayout(record_box)

        play_box = QVBoxLayout()
        play_box.setSpacing(4)
        self.play_btn = make_button("▶  Play macro", "StartButton")
        self.play_btn.setMinimumHeight(46)
        self.play_btn.setMinimumWidth(158)
        self.play_btn.setToolTip(
            f"Play the selected macro ({self.main.hotkey_label('play')})"
        )
        self.play_btn.clicked.connect(self.toggle_play)
        play_box.addWidget(self.play_btn)
        play_hint = QHBoxLayout()
        play_hint.setSpacing(4)
        play_hint.addStretch(1)
        self._play_hint_key = label(self.main.hotkey_label("play"), "VersionBadge")
        play_hint.addWidget(self._play_hint_key)
        play_hint.addWidget(label("play / stop", "Tiny"))
        play_box.addLayout(play_hint)
        actions.addLayout(play_box)

        io_box = QVBoxLayout()
        io_box.setSpacing(4)
        self.export_btn = make_button("Export", "GhostButton")
        self.export_btn.setFixedWidth(92)
        self.export_btn.setToolTip("Export the selected macro to a JSON file")
        self.export_btn.clicked.connect(self._export_macro)
        io_box.addWidget(self.export_btn)
        self.import_btn = make_button("Import", "GhostButton")
        self.import_btn.setFixedWidth(92)
        self.import_btn.setToolTip("Import a macro from a JSON file")
        self.import_btn.clicked.connect(self._import_macro)
        io_box.addWidget(self.import_btn)
        actions.addLayout(io_box)

        loop_box = QVBoxLayout()
        loop_box.setSpacing(4)
        self.loop_chip = make_button("∞  Loop", "LoopChip")
        self.loop_chip.setCheckable(True)
        self.loop_chip.setMinimumHeight(46)
        self.loop_chip.setMinimumWidth(104)
        self.loop_chip.setToolTip(
            "Keep replaying the selected macro until you press stop or panic."
        )
        self.loop_chip.clicked.connect(self._on_loop_chip)
        loop_box.addWidget(self.loop_chip)
        loop_hint = QHBoxLayout()
        loop_hint.setSpacing(4)
        loop_hint.addStretch(1)
        loop_hint.addWidget(label("loop forever", "Tiny"))
        loop_box.addLayout(loop_hint)
        actions.addLayout(loop_box)
        row.addLayout(actions)
        outer.addLayout(row)
        self.energy = EnergyLine()
        outer.addWidget(self.energy)
        self.layout.addWidget(hero)

    def _build_library_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Macro library", "CardTitle"))
        header.addStretch(1)
        self.count_badge = label("0 MACROS", "VersionBadge")
        header.addWidget(self.count_badge)
        card.body.addLayout(header)

        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setContentsMargins(12, 34, 12, 30)
        empty_layout.setSpacing(7)
        icon = QLabel("◎")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 38px; color: #808080;")
        empty_layout.addWidget(icon)
        title = label("Your vault is empty", "CardTitle")
        title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(title)
        hint = label(
            "Hit Record, perform a sequence once, and replay it forever. "
            "There is no time limit.",
            "Muted",
            wrap=True,
        )
        hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(hint)
        card.body.addWidget(self.empty_widget)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.setSpacing(2)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.start_playback())
        card.body.addWidget(self.list_widget, 1)
        self.list_widget.setMinimumHeight(300)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        import_btn = make_button("Import JSON", "GhostButton")
        import_btn.clicked.connect(self._import_macro)
        controls.addWidget(import_btn)
        controls.addStretch(1)
        self.record_hint = label(
            f"{self.main.hotkey_label('record')} to capture", "Tiny"
        )
        controls.addWidget(self.record_hint)
        card.body.addLayout(controls)
        return card

    def _build_details_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Sequence details", "CardTitle"))
        header.addStretch(1)
        self.detail_badge = label("NO SELECTION", "VersionBadge")
        header.addWidget(self.detail_badge)
        card.body.addLayout(header)

        self.empty_details = QWidget()
        empty_layout = QVBoxLayout(self.empty_details)
        empty_layout.setContentsMargins(10, 50, 10, 40)
        empty_layout.setSpacing(8)
        icon = QLabel("⌁")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 34px; color: #808080;")
        empty_layout.addWidget(icon)
        empty_title = label("Nothing selected", "CardTitle")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_hint = label(
            "Select a macro from the library to inspect its timeline, event mix and replay options.",
            "Muted",
            wrap=True,
        )
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_hint)
        card.body.addWidget(self.empty_details)

        self.details = QWidget()
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(12)

        self.detail_name = label("", "HeroTitle")
        self.detail_name.setStyleSheet("font-size: 21px; font-weight: 700; color: #000080;")
        details_layout.addWidget(self.detail_name)
        self.detail_meta = label("", "Muted")
        details_layout.addWidget(self.detail_meta)

        self.timeline = MacroTimeline()
        details_layout.addWidget(self.timeline)

        breakdown_header = QHBoxLayout()
        breakdown_header.addWidget(label("Event breakdown", "SectionTitle"))
        breakdown_header.addStretch(1)
        breakdown_header.addWidget(label("RECORDED INPUT", "Tiny"))
        details_layout.addLayout(breakdown_header)
        breakdown = QHBoxLayout()
        breakdown.setSpacing(8)
        self.move_tile = StatTile("Moves", "0")
        self.click_tile = StatTile("Clicks", "0")
        self.key_tile = StatTile("Keys", "0")
        self.scroll_tile = StatTile("Scrolls", "0")
        for tile in (self.move_tile, self.click_tile, self.key_tile, self.scroll_tile):
            breakdown.addWidget(tile)
        details_layout.addLayout(breakdown)
        details_layout.addWidget(hline())

        playback_header = QHBoxLayout()
        playback_header.addWidget(label("Playback", "SectionTitle"))
        playback_header.addStretch(1)
        self.loop_hint = label("", "Tiny")
        playback_header.addWidget(self.loop_hint)
        details_layout.addLayout(playback_header)

        settings = QGridLayout()
        settings.setHorizontalSpacing(10)
        settings.setVerticalSpacing(8)
        settings.addWidget(label("Speed", "Muted"), 0, 0)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.25, 5.0)
        self.speed_spin.setSingleStep(0.25)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setSuffix(" ×")
        self.speed_spin.setFixedWidth(94)
        self.speed_spin.valueChanged.connect(lambda _v: self._update_loop_hint())
        settings.addWidget(self.speed_spin, 0, 1)
        settings.addWidget(label("Loop", "Muted"), 0, 2)
        self.loop_combo = QComboBox()
        self.loop_combo.addItems(["Once", "Repeat", "Infinite"])
        self.loop_combo.setFixedWidth(104)
        self.loop_combo.currentIndexChanged.connect(self._on_loop_changed)
        settings.addWidget(self.loop_combo, 0, 3)
        self.loop_count = QSpinBox()
        self.loop_count.setRange(2, 9999)
        self.loop_count.setValue(5)
        self.loop_count.setEnabled(False)
        self.loop_count.setFixedWidth(72)
        self.loop_count.valueChanged.connect(lambda _v: self._update_loop_hint())
        settings.addWidget(self.loop_count, 0, 4)
        settings.setColumnStretch(5, 1)
        details_layout.addLayout(settings)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.edit_btn = make_button("Edit timeline", "GhostButton")
        self.edit_btn.setToolTip("Trim, reorder, nudge or delete recorded events")
        self.edit_btn.clicked.connect(self._open_editor)
        self.rename_btn = make_button("Rename", "GhostButton")
        self.rename_btn.clicked.connect(self._rename_macro)
        self.export_btn = make_button("Export", "GhostButton")
        self.export_btn.clicked.connect(self._export_macro)
        self.delete_btn = make_button("Delete", "DangerButton")
        self.delete_btn.clicked.connect(self._delete_macro)
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.rename_btn)
        actions.addWidget(self.export_btn)
        actions.addStretch(1)
        actions.addWidget(self.delete_btn)
        details_layout.addLayout(actions)

        details_layout.addWidget(
            label(
                "Recorded macros are stored as plain JSON in the app's data/macros folder.",
                "Tiny",
                wrap=True,
            )
        )
        card.body.addWidget(self.details)
        self.details.setVisible(False)
        return card

    # ------------------------------------------------------------------
    # Library
    # ------------------------------------------------------------------
    def _refresh_list(self, select_id: str | None = None) -> None:
        if select_id is None:
            select_id = self._selected_id
        macros = self.store.all()
        self.count_badge.setText(f"{len(macros)} MACRO{'S' if len(macros) != 1 else ''}")
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for macro in macros:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, macro["id"])
            item.setSizeHint(QSize(0, 70))
            row = MacroRow(macro)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)
            if macro["id"] == select_id:
                self.list_widget.setCurrentItem(item)
        self.list_widget.blockSignals(False)

        has_macros = bool(macros)
        self.list_widget.setVisible(has_macros)
        self.empty_widget.setVisible(not has_macros)
        if not has_macros:
            self._selected_id = None
            self._show_details(None)
            return
        if select_id:
            self.list_widget.setCurrentRow(
                next((index for index, macro in enumerate(macros) if macro["id"] == select_id), 0)
            )
            self._on_selection_changed(self.list_widget.currentItem(), None)
        elif self.list_widget.currentItem() is None:
            self.list_widget.setCurrentRow(0)
            self._on_selection_changed(self.list_widget.currentItem(), None)

    def _selected_macro(self) -> dict | None:
        if not self._selected_id:
            return None
        return self.store.get(self._selected_id)

    def _on_selection_changed(self, current: QListWidgetItem | None, previous) -> None:
        if current is None:
            self._selected_id = None
            self._show_details(None)
            return
        macro_id = current.data(Qt.UserRole)
        self._selected_id = macro_id
        self._show_details(self.store.get(macro_id))

    def _show_details(self, macro: dict | None) -> None:
        if not macro:
            self.details.setVisible(False)
            self.empty_details.setVisible(True)
            self.timeline.set_macro(None)
            self.detail_badge.setText("NO SELECTION")
            return
        self.empty_details.setVisible(False)
        self.details.setVisible(True)
        self.detail_name.setText(macro.get("name", "Untitled"))
        self.detail_meta.setText(macro_summary(macro))
        self.timeline.set_macro(macro)
        counts = event_breakdown(macro)
        self.move_tile.set_value(f"{counts['moves']:,}")
        self.click_tile.set_value(f"{counts['clicks']:,}")
        self.key_tile.set_value(f"{counts['keys']:,}")
        self.scroll_tile.set_value(f"{counts['scrolls']:,}")
        self.detail_badge.setText(f"{format_duration(macro.get('duration', 0)).upper()}")
        self._update_loop_hint()
        self._sync_loop_chip(self.loop_combo.currentIndex() == 2)

    def _on_loop_changed(self, index: int) -> None:
        self.loop_count.setEnabled(index == 1)
        self._sync_loop_chip(index == 2)
        self._update_loop_hint()

    def _on_loop_chip(self, checked: bool) -> None:
        if hasattr(self, "loop_combo"):
            self.loop_combo.setCurrentIndex(2 if checked else 0)
        self._sync_loop_chip(bool(checked))
        if checked:
            self.main.toast("info", "Infinite loop armed — playback repeats until stopped.")

    def _sync_loop_chip(self, checked: bool) -> None:
        if not hasattr(self, "loop_chip"):
            return
        checked = bool(checked)
        self.loop_chip.blockSignals(True)
        self.loop_chip.setChecked(checked)
        self.loop_chip.setText("∞  LOOP ON" if checked else "∞  Loop")
        self.loop_chip.blockSignals(False)

    def _update_loop_hint(self) -> None:
        loops = self._loop_value()
        if loops is None:
            text = (
                f"Infinite loop · stop with {self.main.hotkey_label('play')} "
                f"or {self.main.hotkey_label('panic')}"
            )
        elif loops == 1:
            text = f"Play once at {self.speed_spin.value():.2f}×"
        else:
            text = f"Repeat {loops}× at {self.speed_spin.value():.2f}×"
        self.loop_hint.setText(text)

    def _loop_value(self) -> int | None:
        index = self.loop_combo.currentIndex()
        if index == 2:
            return None
        if index == 1:
            return max(2, self.loop_count.value())
        return 1

    def refresh_hotkeys(self) -> None:
        record = self.main.hotkey_label("record")
        play = self.main.hotkey_label("play")
        if hasattr(self, "_record_hint_key"):
            self._record_hint_key.setText(record)
        if hasattr(self, "_play_hint_key"):
            self._play_hint_key.setText(play)
        if hasattr(self, "record_btn"):
            self.record_btn.setToolTip(f"Start or stop recording ({record})")
        if hasattr(self, "play_btn"):
            self.play_btn.setToolTip(f"Play the selected macro ({play})")
        if hasattr(self, "loop_hint"):
            self._update_loop_hint()
        if not self._armed and not self._recording and not self._playing:
            if hasattr(self, "record_hint"):
                self.record_hint.setText(f"{record} to capture")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def toggle_record(self) -> None:
        if self._armed:
            self._cancel_armed()
            return
        if self._recording:
            self.stop_recording()
            return
        self.start_recording()

    def start_recording(self) -> None:
        if self._playing:
            self.stop_playback(quiet=True)
        if self._armed or self._recording:
            return
        self.main.acquire("macro")
        self._armed = True
        self._arm_deadline = time.perf_counter() + 3.0
        self._set_armed_ui()
        self.main.log("hotkey", "Macro recorder armed — recording begins in 3 seconds.")
        self.main.toast(
            "info",
            "Recording armed · starts in 3 seconds. "
            f"{self.main.hotkey_label('record')} cancels.",
        )

    def _set_armed_ui(self) -> None:
        self.record_btn.setText("■  Cancel arming")
        self.record_btn.setProperty("recording", True)
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        self.play_btn.setEnabled(False)
        self.list_widget.setEnabled(False)
        self.energy.set_running(True)
        self.hero_dot.set_state(True, COLORS["red"])
        self.hero_status.setText("Recording starts in 3.0s")
        self.hero_sub.setText("Get into position — every click and keystroke is captured after the countdown.")
        self.record_hint.setText("ARMED")

    def _cancel_armed(self) -> None:
        if not self._armed:
            return
        self._armed = False
        self.main.release("macro")
        self._reset_idle_ui()
        self.main.log("info", "Macro recording cancelled before capture.")
        self.main.toast("info", "Recording cancelled.")

    def _launch_recorder(self) -> None:
        self._armed = False
        if not self.recorder.start():
            self.main.release("macro")
            self._reset_idle_ui()
            self.main.toast("error", f"Recorder could not start: {self.recorder.error}")
            self.main.log("error", f"Recorder failed to start: {self.recorder.error}")
            return
        self._recording = True
        self.record_btn.setText("■  Stop & save")
        self.record_btn.setProperty("recording", True)
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        self.hero_status.setText("Recording — 00:00")
        self.hero_sub.setText(
            f"0 events captured  ·  Press {self.main.hotkey_label('record')} to stop and save"
        )
        self.hero_dot.set_state(True, COLORS["red"])
        self.energy.set_running(True)
        self.record_hint.setText("RECORDING")
        self.main.log("success", "Macro recording started. Perform your sequence.")
        self.main.toast(
            "warning",
            f"Recording started — press {self.main.hotkey_label('record')} to stop & save.",
        )

    def stop_recording(self, quiet: bool = False) -> None:
        if not self._recording:
            if self._armed:
                self._cancel_armed()
            return
        self._recording = False
        result = self.recorder.stop()
        self.main.release("macro")
        if not result or not result.get("events"):
            self._reset_idle_ui()
            self.main.log("warning", "Recording ended with no captured events.")
            if not quiet:
                self.main.toast("warning", "No events captured — nothing saved.")
            return

        name = self.store.next_name()
        try:
            macro = self.store.create(name, result["events"], result["duration"])
        except Exception as exc:
            self._reset_idle_ui()
            self.main.log("error", f"Could not save recording: {exc}")
            self.main.toast("error", f"Could not save recording: {exc}")
            return
        self._selected_id = macro["id"]
        self._refresh_list(select_id=macro["id"])
        self._reset_idle_ui()
        self.hero_status.setText("Macro saved")
        self.hero_sub.setText(f"{name} · {format_duration(macro['duration'])} · {len(macro['events']):,} events")
        self.main.log(
            "success",
            f"Saved {name} — {format_duration(macro['duration'])}, {len(macro['events']):,} events.",
        )
        if not quiet:
            self.main.toast("success", f"{name} saved · {format_duration(macro['duration'])}")

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------
    def _export_macro(self) -> None:
        macro = self._selected_macro()
        if not macro:
            self.main.toast("warning", "Select a macro to export first.")
            return
        suggested = f"{macro.get('name', 'macro').replace(' ', '_')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export macro",
            str(Path.home() / suggested),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            self.store.export(macro, path)
            self.main.toast("success", f"Exported {macro.get('name', 'macro')}.")
            self.main.log("success", f"Exported macro to {path}.")
        except Exception as exc:
            self.main.toast("error", f"Export failed: {exc}")
            self.main.log("error", f"Macro export failed: {exc}")

    def _import_macro(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import macro", str(Path.home()), "JSON (*.json)"
        )
        if not path:
            return
        try:
            macro = self.store.import_file(path)
            self.main.toast("success", f"Imported {macro.get('name', 'macro')}.")
            self.main.log("success", f"Imported macro from {path}.")
            self._refresh_list()
        except Exception as exc:
            self.main.toast("error", f"Import failed: {exc}")
            self.main.log("error", f"Macro import failed: {exc}")

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def toggle_play(self) -> None:
        if self._playing:
            self.stop_playback()
        else:
            self.start_playback()

    def start_playback(self) -> None:
        if self._playing:
            return
        if self._armed or self._recording:
            self.main.toast("warning", "Stop recording before playing a macro.")
            return
        macro = self._selected_macro()
        if not macro:
            self.main.toast("warning", "Select a macro to play first.")
            return
        loops = self._loop_value()
        speed = self.speed_spin.value()
        self.main.acquire("macro")
        if not self.player.start(macro, speed=speed, loops=loops):
            self.main.release("macro")
            self.main.toast("error", "Macro playback could not start.")
            return
        self._playing = True
        self._manual_stop = False
        self._playing_name = macro.get("name", "Macro")
        self._playing_duration = float(macro.get("duration", 0))
        self._set_playing_ui(True)
        loop_text = "∞" if loops is None else str(loops)
        self.main.log("hotkey", f"Playing {self._playing_name} — {loop_text} loop(s) at {speed:.2f}×.")
        self.main.toast("success", f"Playing {self._playing_name} · {loop_text} loop(s)")
        self.timeline.set_progress(0.0)

    def macro_choices(self) -> list[tuple[str, str]]:
        """Return ``(id, name)`` for the schedule editor."""
        return [(macro["id"], macro.get("name", "Untitled")) for macro in self.store.all()]

    def play_macro_by_id(self, macro_id: str, loops: int | None = 1) -> bool:
        """Select and play a macro by id — used by scheduled runs."""
        if self._armed or self._recording or self._playing or self.player.is_active:
            return False
        macro = self.store.get(macro_id)
        if not macro:
            return False
        self._selected_id = macro_id
        self._refresh_list(select_id=macro_id)
        if loops is None:
            self.loop_combo.setCurrentIndex(2)
        elif int(loops) > 1:
            self.loop_combo.setCurrentIndex(1)
            self.loop_count.setValue(max(2, int(loops)))
        else:
            self.loop_combo.setCurrentIndex(0)
        self.start_playback()
        return self._playing

    def stop_playback(self, quiet: bool = False) -> None:
        if not self._playing and not self.player.is_active:
            return
        self._playing = False
        self._manual_stop = True
        self.player.stop()
        self.main.release("macro")
        self._set_playing_ui(False)
        self.main.log("info", f"Playback stopped — {self._playing_name}.")
        if not quiet:
            self.main.toast("info", "Macro playback stopped.")

    def _set_playing_ui(self, playing: bool) -> None:
        self.play_btn.setText("■  Stop playback" if playing else "▶  Play macro")
        self.play_btn.setProperty("running", playing)
        self.play_btn.style().unpolish(self.play_btn)
        self.play_btn.style().polish(self.play_btn)
        self.record_btn.setEnabled(not playing)
        self.list_widget.setEnabled(not playing)
        self.energy.set_running(playing)
        if playing:
            self.hero_status.setText(f"Playing {self._playing_name}")
            self.hero_sub.setText(
                f"100% native replay  ·  {self.main.hotkey_label('play')} to stop  ·  "
                f"{self.main.hotkey_label('panic')} for panic stop"
            )
            self.hero_dot.set_state(True, COLORS["accent_2"])
            self.record_hint.setText("PLAYING")
            self.speed_spin.setEnabled(False)
            self.loop_combo.setEnabled(False)
            self.loop_count.setEnabled(False)
            self.loop_chip.setEnabled(False)
        else:
            self.hero_dot.set_state(False)
            self.hero_status.setText("Capture once. Replay forever.")
            self.hero_sub.setText(
                "No duration limit  ·  Native-speed replay  ·  Loop until you say stop"
            )
            self.energy.set_running(False)
            self.timeline.set_progress(0.0)
            self.record_hint.setText(f"{self.main.hotkey_label('record')} to capture")
            self.speed_spin.setEnabled(True)
            self.loop_combo.setEnabled(True)
            self.loop_count.setEnabled(self.loop_combo.currentIndex() == 1)
            self.loop_chip.setEnabled(True)
            self._sync_loop_chip(self.loop_combo.currentIndex() == 2)
            self.detail_badge.setText(
                format_duration(self._selected_macro().get("duration", 0)).upper()
                if self._selected_macro()
                else "NO SELECTION"
            )

    def _on_playback_finished(self, finished: bool) -> None:
        if not self._playing:
            return
        self._playing = False
        self.main.release("macro")
        name = self._playing_name
        self._set_playing_ui(False)
        if finished:
            self.main.log("success", f"Macro playback finished — {name}.")
            self.main.toast("success", f"Finished {name}.")
        else:
            self.main.log("info", f"Macro playback stopped — {name}.")

    def force_stop(self) -> bool:
        was_active = self._armed or self._recording or self._playing or self.player.is_active
        if self._armed:
            self._cancel_armed()
        if self._recording:
            self.stop_recording(quiet=True)
        if self._playing or self.player.is_active:
            self.stop_playback(quiet=True)
        return was_active

    # ------------------------------------------------------------------
    # Library actions
    # ------------------------------------------------------------------
    def _open_editor(self) -> None:
        macro = self._selected_macro()
        if not macro:
            self.main.toast("warning", "Select a macro to edit first.")
            return
        if self._playing or self._recording or self._armed:
            self.main.toast("warning", "Stop playback or recording before editing.")
            return
        dialog = MacroEditorDialog(macro, self)
        if not dialog.exec():
            return
        try:
            updated = self.store.save(dialog.edited_macro())
        except Exception as exc:
            self.main.toast("error", f"Could not save timeline: {exc}")
            self.main.log("error", f"Macro timeline save failed: {exc}")
            return
        self._selected_id = updated["id"]
        self._refresh_list(select_id=updated["id"])
        self.main.log(
            "success",
            f"Timeline saved for {updated['name']} — {len(updated['events']):,} events, {format_duration(updated['duration'])}.",
        )
        self.main.toast(
            "success",
            f"Timeline saved · {len(updated['events']):,} events · {format_duration(updated['duration'])}",
        )

    def _rename_macro(self) -> None:
        macro = self._selected_macro()
        if not macro:
            return
        name, accepted = QInputDialog.getText(self, "Rename macro", "Macro name:", text=macro.get("name", ""))
        if not accepted:
            return
        updated = self.store.rename(macro["id"], name)
        if updated:
            self._refresh_list(select_id=updated["id"])
            self.main.toast("success", f"Renamed to {updated['name']}.")
            self.main.log("info", f"Macro renamed to {updated['name']}.")

    def _delete_macro(self) -> None:
        macro = self._selected_macro()
        if not macro:
            return
        if self._playing:
            self.main.toast("warning", "Stop playback before deleting a macro.")
            return
        if self.main.settings.get("confirm_delete", True):
            answer = QMessageBox.question(
                self,
                "Delete macro",
                f"Delete “{macro.get('name')}”? This removes the JSON file from disk.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        if self.store.delete(macro["id"]):
            self.main.toast("info", f"Deleted {macro.get('name')}.")
            self.main.log("info", f"Macro deleted — {macro.get('name')}.")
            self._selected_id = None
            self._refresh_list()
        else:
            self.main.toast("error", "Could not delete that macro file.")

    def _export_macro(self) -> None:
        macro = self._selected_macro()
        if not macro:
            return
        safe_name = "".join(character if character.isalnum() or character in "-_ " else "_" for character in macro["name"])
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export macro",
            f"{safe_name.strip() or 'macro'}.json",
            "AutoClicker macro (*.json);;JSON (*.json)",
        )
        if not path:
            return
        try:
            self.store.export(macro, path)
            self.main.toast("success", f"Exported to {Path(path).name}.")
            self.main.log("success", f"Macro exported to {path}.")
        except Exception as exc:
            self.main.toast("error", f"Export failed: {exc}")
            self.main.log("error", f"Macro export failed: {exc}")

    def _import_macro(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import macro",
            "",
            "AutoClicker macro (*.json);;JSON (*.json)",
        )
        if not path:
            return
        try:
            macro = self.store.import_file(path)
        except Exception as exc:
            self.main.toast("error", f"Import failed: {exc}")
            self.main.log("error", f"Macro import failed: {exc}")
            return
        self._selected_id = macro["id"]
        self._refresh_list(select_id=macro["id"])
        self.main.toast("success", f"Imported {macro['name']}.")
        self.main.log("success", f"Macro imported from {path}.")

    # ------------------------------------------------------------------
    def _reset_idle_ui(self) -> None:
        self._armed = False
        self._recording = False
        self.record_btn.setText("●  Record macro")
        self.record_btn.setProperty("recording", False)
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        self.record_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.list_widget.setEnabled(True)
        self.energy.set_running(self._playing)
        self.hero_dot.set_state(self._playing, COLORS["accent_2"] if self._playing else COLORS["faint"])
        self.record_hint.setText(f"{self.main.hotkey_label('record')} to capture")
        if not self._playing:
            self.hero_status.setText("Capture once. Replay forever.")
            self.hero_sub.setText(
                "No duration limit  ·  Native-speed replay  ·  Loop until you say stop"
            )

    def _tick(self) -> None:
        now = time.perf_counter()
        if self._armed:
            remaining = max(0.0, self._arm_deadline - now)
            if remaining <= 0:
                self._launch_recorder()
            else:
                self.hero_status.setText(f"Recording starts in {remaining:.1f}s")
                self.record_hint.setText(f"ARMED {remaining:.1f}s")
        elif self._recording:
            elapsed = self.recorder.elapsed()
            count = self.recorder.event_count()
            self.hero_status.setText(f"Recording — {format_clock(elapsed)}")
            self.hero_sub.setText(
                f"{count:,} events captured  ·  Press {self.main.hotkey_label('record')} to stop and save"
            )
        elif self._playing:
            snapshot = self.player.snapshot()
            if not snapshot.get("active") and not self.player.is_active:
                # Safety net if the completion signal is delayed.
                self._on_playback_finished(True)
                return
            duration = max(1.0, self._playing_duration)
            progress = (float(snapshot.get("elapsed", 0)) * self.speed_spin.value() * 1000.0 / duration)
            self.timeline.set_progress(min(1.0, progress))
            loop = int(snapshot.get("loop", 0))
            total = snapshot.get("loops_total")
            if total is None:
                loop_text = f"loop {max(1, loop)} / ∞"
            else:
                loop_text = f"loop {max(1, loop)} / {total}"
            self.hero_status.setText(f"Playing {self._playing_name}")
            self.hero_sub.setText(
                f"{loop_text}  ·  {self.speed_spin.value():.2f}×  ·  "
                f"{self.main.hotkey_label('play')} to stop  ·  "
                f"{self.main.hotkey_label('panic')} for panic"
            )
