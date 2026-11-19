"""Visual macro timeline editor — trim, reorder, delete and nudge events."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.macro_edit import (
    delete_events,
    describe_event,
    event_duration,
    move_event,
    nudge_events,
    rebuild_macro,
    trim_events,
)
from ..core.macros import format_duration
from .widgets import hline, label, make_button


class MacroEditorDialog(QDialog):
    """Modeless-free editor for one recorded macro.

    The dialog keeps an in-memory copy; the caller saves it only after
    ``exec()`` returns Accepted.
    """

    def __init__(self, macro: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._macro = dict(macro)
        self._events = [dict(event) for event in macro.get("events", [])]
        self._edited = False
        self.setWindowTitle(f"Edit timeline — {macro.get('name', 'Macro')}")
        self.resize(900, 620)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(11)

        header = QHBoxLayout()
        title = QLabel("Visual timeline editor")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #000080; background: transparent;"
        )
        header.addWidget(title)
        header.addStretch(1)
        self.count_label = label("", "VersionBadge")
        header.addWidget(self.count_label)
        layout.addLayout(header)
        layout.addWidget(
            label(
                "Select one or more events to delete or nudge. Move reorders the event "
                "in time without changing the rest of the recording. Trim keeps only "
                "the chosen time range and rebases it to zero.",
                "Muted",
                wrap=True,
            )
        )
        layout.addWidget(hline())

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Time", "Type", "Event"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Fixed)
        header_view.setSectionResizeMode(1, QHeaderView.Fixed)
        header_view.setSectionResizeMode(2, QHeaderView.Fixed)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 48)
        self.table.setColumnWidth(1, 96)
        self.table.setColumnWidth(2, 110)
        self.table.itemSelectionChanged.connect(self._sync_trim_defaults)
        layout.addWidget(self.table, 1)

        tools = QGridLayout()
        tools.setHorizontalSpacing(8)
        tools.setVerticalSpacing(8)

        self.up_btn = make_button("Move up", "GhostButton")
        self.up_btn.clicked.connect(lambda: self._move(-1))
        self.down_btn = make_button("Move down", "GhostButton")
        self.down_btn.clicked.connect(lambda: self._move(1))
        self.delete_btn = make_button("Delete selected", "DangerButton")
        self.delete_btn.clicked.connect(self._delete)
        self.minus_btn = make_button("−10 ms", "GhostButton")
        self.minus_btn.clicked.connect(lambda: self._nudge(-10))
        self.plus_btn = make_button("+10 ms", "GhostButton")
        self.plus_btn.clicked.connect(lambda: self._nudge(10))
        for column, button in enumerate(
            (self.up_btn, self.down_btn, self.delete_btn, self.minus_btn, self.plus_btn)
        ):
            tools.addWidget(button, 0, column)
        tools.setColumnStretch(5, 1)
        layout.addLayout(tools)

        layout.addWidget(hline())
        trim_header = QHBoxLayout()
        trim_header.addWidget(label("Trim range", "SectionTitle"))
        trim_header.addStretch(1)
        self.trim_hint = label("", "Tiny")
        trim_header.addWidget(self.trim_hint)
        layout.addLayout(trim_header)

        trim_row = QHBoxLayout()
        trim_row.setSpacing(8)
        trim_row.addWidget(label("Start", "Muted"))
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0.0, 86_400.0)
        self.start_spin.setDecimals(2)
        self.start_spin.setSuffix(" s")
        self.start_spin.setFixedWidth(104)
        trim_row.addWidget(self.start_spin)
        trim_row.addWidget(label("End", "Muted"))
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0.0, 86_400.0)
        self.end_spin.setDecimals(2)
        self.end_spin.setSuffix(" s")
        self.end_spin.setFixedWidth(104)
        trim_row.addWidget(self.end_spin)
        self.use_selection_btn = make_button("Set from selection", "GhostButton")
        self.use_selection_btn.clicked.connect(self._set_trim_from_selection)
        trim_row.addWidget(self.use_selection_btn)
        self.trim_btn = make_button("Trim", "GhostButton")
        self.trim_btn.clicked.connect(self._trim)
        trim_row.addWidget(self.trim_btn)
        trim_row.addStretch(1)
        layout.addLayout(trim_row)

        self.status = label("", "Tiny", wrap=True)
        layout.addWidget(self.status)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.revert_btn = make_button("Revert changes", "GhostButton")
        self.revert_btn.clicked.connect(self._revert)
        footer.addWidget(self.revert_btn)
        footer.addStretch(1)
        cancel = make_button("Cancel", "GhostButton")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        save = make_button("Save changes", "StartButton")
        save.clicked.connect(self._accept)
        footer.addWidget(save)
        layout.addLayout(footer)

        self._reload()

    # ------------------------------------------------------------------
    def edited_macro(self) -> dict:
        return rebuild_macro(self._macro, self._events)

    def _reload(self, select: int | None = None) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._events))
        for row, event in enumerate(self._events):
            values = (
                str(row + 1),
                f"{float(event.get('t', 0)) / 1000.0:.3f}s",
                str(event.get("type", "")).title(),
                describe_event(event),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        duration = event_duration(self._events) / 1000.0
        self.count_label.setText(f"{len(self._events):,} EVENTS · {format_duration(duration * 1000)}")
        self.end_spin.setMaximum(max(0.01, duration))
        self.start_spin.setMaximum(max(0.0, duration))
        if select is not None and self._events:
            row = max(0, min(len(self._events) - 1, select))
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, 0))
        self._update_buttons()

    def _update_buttons(self) -> None:
        rows = self._selected_rows()
        self.up_btn.setEnabled(bool(rows) and min(rows) > 0)
        self.down_btn.setEnabled(bool(rows) and max(rows) < len(self._events) - 1)
        self.delete_btn.setEnabled(bool(rows))
        self.minus_btn.setEnabled(bool(rows))
        self.plus_btn.setEnabled(bool(rows))
        self.trim_btn.setEnabled(bool(self._events))
        self.trim_hint.setText(f"Timeline {event_duration(self._events) / 1000:.2f}s" if self._events else "")

    def _selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectedIndexes()})

    def _sync_trim_defaults(self) -> None:
        self._update_buttons()

    def _current_row(self) -> int:
        rows = self._selected_rows()
        return rows[0] if rows else 0

    def _move(self, offset: int) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        self._events, new_index = move_event(self._events, rows[0], offset)
        self._edited = True
        self._reload(select=new_index)

    def _delete(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        self._events = delete_events(self._events, rows)
        self._edited = True
        self._reload(select=min(rows[0], max(0, len(self._events) - 1)))

    def _nudge(self, delta_ms: float) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        self._events = nudge_events(self._events, rows, delta_ms)
        self._edited = True
        self._reload(select=rows[0])

    def _set_trim_from_selection(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self.status.setText("Select events first — their time range becomes the trim window.")
            return
        times = [float(self._events[row].get("t", 0)) for row in rows]
        self.start_spin.setValue(min(times) / 1000.0)
        self.end_spin.setValue(max(times) / 1000.0)
        self.status.setText("Trim window set from the selected events.")

    def _trim(self) -> None:
        start_ms = self.start_spin.value() * 1000.0
        end_ms = self.end_spin.value() * 1000.0
        try:
            trimmed = trim_events(self._events, start_ms, end_ms)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        if not trimmed:
            self.status.setText("That range contains no events — nothing was trimmed.")
            return
        self._events = trimmed
        self._edited = True
        self._last_trim = (start_ms, end_ms)
        self._reload()
        self.status.setText(
            f"Trimmed to {start_ms / 1000:.2f}s – {end_ms / 1000:.2f}s and rebased to zero."
        )

    def _revert(self) -> None:
        self._events = [dict(event) for event in self._macro.get("events", [])]
        self._edited = False
        self._reload()
        self.status.setText("Reverted to the recorded timeline.")

    def _accept(self) -> None:
        if not self._events:
            self.status.setText("A macro needs at least one event — use Revert to restore it.")
            return
        self.accept()


__all__ = ["MacroEditorDialog"]
