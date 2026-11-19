"""Per-application profiles and scheduled macro runs."""

from __future__ import annotations

import uuid
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from ...core import wininput
from ...core.profiles import (
    best_profile,
    days_label,
    due_schedules,
    next_occurrence,
    normalize_days,
    parse_clock,
    schedule_summary,
)
from ..widgets import Card, HeroCard, hline, label, make_button
from .base import Page


class AutomationPage(Page):
    """Trigger saved clicker presets by window title and run macros on a clock."""

    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self._profiles: list[dict] = []
        self._schedules: list[dict] = []
        self._last_fired: dict[str, str] = {}
        self._last_profile_id: str | None = None
        self._selected_profile_id: str | None = None
        self._selected_schedule_id: str | None = None
        self._loading = False

        self._build_header()
        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._build_profiles_card(), 1)
        columns.addWidget(self._build_schedules_card(), 1)
        self.layout.addLayout(columns)
        self.layout.addStretch(1)

        self._load()

        self._profile_timer = QTimer(self)
        self._profile_timer.setInterval(1500)
        self._profile_timer.timeout.connect(self._poll_profiles)
        self._profile_timer.start()

        self._schedule_timer = QTimer(self)
        self._schedule_timer.setInterval(15_000)
        self._schedule_timer.timeout.connect(self._schedule_tick)
        self._schedule_timer.start()

        self._refresh_profiles()
        self._refresh_schedules()
        self._update_next_label()
        self.main.log(
            "success",
            f"Automation online — {len(self._profiles)} app profile(s), {len(self._schedules)} schedule(s).",
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        frame = HeroCard()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 17, 22, 17)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(label("ORCHESTRATION", "Eyebrow"))
        text.addWidget(label("Trigger setups, not busywork.", "HeroTitle"))
        text.addWidget(
            label(
                "Window-aware app profiles and clock-based macro runs, handled locally.",
                "HeroSub",
            )
        )
        layout.addLayout(text, 1)
        layout.addWidget(label("AUTO TRIGGERS", "VersionBadge"), 0, Qt.AlignTop)
        self.layout.addWidget(frame)

    def _build_profiles_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("App profiles", "CardTitle"))
        header.addStretch(1)
        self.profile_badge = label("0 PROFILES", "VersionBadge")
        header.addWidget(self.profile_badge)
        card.body.addLayout(header)
        card.body.addWidget(
            label(
                "When the foreground window title contains your match text, the chosen "
                "clicker preset is applied automatically while the engine is idle.",
                "Muted",
                wrap=True,
            )
        )

        self.profile_list = QListWidget()
        self.profile_list.setFixedHeight(148)
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        self.profile_list.itemDoubleClicked.connect(lambda _item: self._apply_selected_profile())
        card.body.addWidget(self.profile_list)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(label("Window title contains", "SectionTitle"), 0, 0)
        self.match_input = QLineEdit()
        self.match_input.setPlaceholderText("e.g. Notepad")
        self.match_input.setClearButtonEnabled(True)
        grid.addWidget(self.match_input, 0, 1)
        grid.addWidget(label("Clicker preset", "SectionTitle"), 1, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(160)
        grid.addWidget(self.preset_combo, 1, 1)
        self.profile_enabled = QCheckBox("Profile enabled")
        self.profile_enabled.setChecked(True)
        grid.addWidget(self.profile_enabled, 2, 1)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)
        card.body.addWidget(hline())

        actions = QHBoxLayout()
        actions.setSpacing(8)
        active_btn = make_button("Use active window", "GhostButton")
        active_btn.setToolTip("Fill the match field with the current foreground window title")
        active_btn.clicked.connect(self._use_active_window)
        actions.addWidget(active_btn)
        apply_btn = make_button("Apply now", "GhostButton")
        apply_btn.setToolTip("Apply the selected profile immediately")
        apply_btn.clicked.connect(self._apply_selected_profile)
        actions.addWidget(apply_btn)
        actions.addStretch(1)
        delete_btn = make_button("Delete", "DangerButton")
        delete_btn.clicked.connect(self._delete_profile)
        actions.addWidget(delete_btn)
        save_btn = make_button("Save profile", "StartButton")
        save_btn.clicked.connect(self._save_profile)
        actions.addWidget(save_btn)
        card.body.addLayout(actions)

        self.profile_status = label("Waiting for a foreground window…", "Tiny", wrap=True)
        self.profile_status.setStyleSheet("color: #404040;")
        card.body.addWidget(self.profile_status)
        self._refresh_preset_combo()
        return card

    def _build_schedules_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Scheduled runs", "CardTitle"))
        header.addStretch(1)
        self.schedule_badge = label("0 RUNS", "VersionBadge")
        header.addWidget(self.schedule_badge)
        card.body.addLayout(header)
        card.body.addWidget(
            label(
                "Pick a macro, a local time and the days it should run. A check every "
                "15 seconds catches the window even if the app was busy.",
                "Muted",
                wrap=True,
            )
        )

        self.schedule_list = QListWidget()
        self.schedule_list.setFixedHeight(148)
        self.schedule_list.currentItemChanged.connect(self._on_schedule_selected)
        card.body.addWidget(self.schedule_list)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(label("Time", "SectionTitle"), 0, 0)
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("HH:MM")
        self.time_input.setFixedWidth(82)
        self.time_input.setToolTip("24-hour local time, for example 18:30")
        grid.addWidget(self.time_input, 0, 1, 1, 1)
        grid.addWidget(label("Days", "SectionTitle"), 0, 2)
        self.days_combo = QComboBox()
        for key, name in (
            ("every_day", "Every day"),
            ("weekdays", "Weekdays"),
            ("weekends", "Weekends"),
        ):
            self.days_combo.addItem(name, key)
        grid.addWidget(self.days_combo, 0, 3)
        grid.addWidget(label("Macro", "SectionTitle"), 1, 0)
        self.macro_combo = QComboBox()
        self.macro_combo.setMinimumWidth(190)
        grid.addWidget(self.macro_combo, 1, 1, 1, 3)
        self.schedule_enabled = QCheckBox("Schedule enabled")
        self.schedule_enabled.setChecked(True)
        grid.addWidget(self.schedule_enabled, 2, 1, 1, 3)
        grid.setColumnStretch(3, 1)
        card.body.addLayout(grid)
        card.body.addWidget(hline())

        actions = QHBoxLayout()
        actions.setSpacing(8)
        delete_btn = make_button("Delete", "DangerButton")
        delete_btn.clicked.connect(self._delete_schedule)
        actions.addWidget(delete_btn)
        actions.addStretch(1)
        save_btn = make_button("Save run", "StartButton")
        save_btn.clicked.connect(self._save_schedule)
        actions.addWidget(save_btn)
        card.body.addLayout(actions)

        self.next_label = label("No scheduled runs yet.", "Tiny", wrap=True)
        self.next_label.setStyleSheet("color: #404040;")
        card.body.addWidget(self.next_label)
        return card

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        self._loading = True
        profiles = self.main.settings.get("app_profiles", [])
        schedules = self.main.settings.get("scheduled_runs", [])
        fired = self.main.settings.get("schedule_last_fired", {})
        self._profiles = [dict(item) for item in profiles if isinstance(item, dict)]
        for profile in self._profiles:
            profile.setdefault("id", uuid.uuid4().hex)
            profile["enabled"] = bool(profile.get("enabled", True))
        self._schedules = [dict(item) for item in schedules if isinstance(item, dict)]
        for schedule in self._schedules:
            schedule.setdefault("id", uuid.uuid4().hex)
            schedule["enabled"] = bool(schedule.get("enabled", True))
        self._last_fired = dict(fired) if isinstance(fired, dict) else {}
        self._loading = False

    def _persist_profiles(self) -> None:
        self.main.settings.set("app_profiles", self._profiles)

    def _persist_schedules(self) -> None:
        self.main.settings.set("scheduled_runs", self._schedules)
        self.main.settings.set("schedule_last_fired", self._last_fired)

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------
    def _refresh_preset_combo(self) -> None:
        if not hasattr(self, "preset_combo"):
            return
        current = self.preset_combo.currentText()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        names = self.main.clicker_page.preset_names()
        self.preset_combo.addItems(names)
        if current in names:
            self.preset_combo.setCurrentText(current)
        self.preset_combo.blockSignals(False)

    def _refresh_profiles(self, select_id: str | None = None) -> None:
        if select_id is None:
            select_id = self._selected_profile_id
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for profile in self._profiles:
            match = str(profile.get("match", "")).strip() or "—"
            preset = str(profile.get("preset", "")).strip() or "missing preset"
            state = "ON" if profile.get("enabled", True) else "OFF"
            item = QListWidgetItem(f"{match}  →  {preset}  ·  {state}")
            item.setData(Qt.UserRole, profile.get("id"))
            self.profile_list.addItem(item)
            if profile.get("id") == select_id:
                self.profile_list.setCurrentItem(item)
        self.profile_list.blockSignals(False)
        self.profile_badge.setText(
            f"{len(self._profiles)} PROFILE{'S' if len(self._profiles) != 1 else ''}"
        )
        if not self._profiles:
            self.profile_list.clearSelection()
            self._selected_profile_id = None
        elif self.profile_list.currentItem() is not None:
            self._on_profile_selected(self.profile_list.currentItem(), None)
        self._refresh_preset_combo()

    def _on_profile_selected(self, current: QListWidgetItem | None, previous) -> None:
        if current is None:
            return
        profile_id = str(current.data(Qt.UserRole))
        profile = next(
            (item for item in self._profiles if item.get("id") == profile_id), None
        )
        if not profile:
            return
        self._selected_profile_id = profile_id
        self.match_input.setText(str(profile.get("match", "")))
        self.profile_enabled.setChecked(bool(profile.get("enabled", True)))
        index = self.preset_combo.findText(str(profile.get("preset", "")))
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)

    def _use_active_window(self) -> None:
        title = wininput.get_foreground_title()
        if not title:
            self.main.toast("warning", "No foreground window title could be read.")
            return
        self.match_input.setText(title[:80])
        self.profile_status.setText(f"Captured foreground title: {title}")
        self.main.toast("info", "Window title copied into the profile.")

    def _save_profile(self) -> None:
        match = self.match_input.text().strip()
        preset = self.preset_combo.currentText().strip()
        if not match:
            self.main.toast("warning", "Enter the window title fragment to match.")
            return
        if not preset:
            self.main.toast("warning", "Save a clicker preset first, then pick it here.")
            return
        profile = next(
            (item for item in self._profiles if item.get("id") == self._selected_profile_id),
            None,
        )
        if profile is None:
            profile = {"id": uuid.uuid4().hex}
            self._profiles.append(profile)
        profile.update(
            {
                "match": match,
                "preset": preset,
                "enabled": self.profile_enabled.isChecked(),
            }
        )
        self._selected_profile_id = profile["id"]
        self._persist_profiles()
        self._refresh_profiles(select_id=profile["id"])
        self.main.log(
            "success",
            f"App profile saved — “{match}” applies preset {preset}.",
        )
        self.main.toast("success", f"Profile saved · {match} → {preset}")

    def _delete_profile(self) -> None:
        if not self._selected_profile_id:
            self.main.toast("warning", "Select a profile to delete first.")
            return
        profile = next(
            (item for item in self._profiles if item.get("id") == self._selected_profile_id),
            None,
        )
        if not profile:
            return
        if self.main.settings.get("confirm_delete", True):
            answer = QMessageBox.question(
                self,
                "Delete app profile",
                f"Delete the profile for “{profile.get('match', '')}”?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self._profiles = [item for item in self._profiles if item is not profile]
        self._selected_profile_id = None
        self.match_input.clear()
        self._persist_profiles()
        self._refresh_profiles()
        self.main.toast("info", "App profile deleted.")

    def _apply_selected_profile(self) -> None:
        if not self._selected_profile_id:
            self.main.toast("warning", "Select a profile to apply first.")
            return
        profile = next(
            (item for item in self._profiles if item.get("id") == self._selected_profile_id),
            None,
        )
        if not profile:
            return
        if self.main.clicker_page.apply_preset(str(profile.get("preset", ""))):
            self.main.toast("success", f"Applied preset {profile.get('preset')}.")
        else:
            self.main.toast(
                "warning", "Could not apply the preset — stop the click engine or check the name."
            )

    def _poll_profiles(self) -> None:
        if self.main._shutting_down or not self._profiles:
            return
        title = wininput.get_foreground_title()
        match = best_profile(self._profiles, title)
        if not match:
            self._last_profile_id = None
            self.profile_status.setText(
                f"No profile matched · foreground: {title[:70] or 'unknown'}"
            )
            return
        profile_id = str(match.get("id"))
        preset = str(match.get("preset", "")).strip()
        self.profile_status.setText(
            f"Matched “{match.get('match')}” · preset {preset or '—'} · {title[:60]}"
        )
        if profile_id == self._last_profile_id:
            return
        self._last_profile_id = profile_id
        if not preset:
            return
        if self.main.clicker_page.engine.is_active:
            self.profile_status.setText(
                f"Profile “{match.get('match')}” matched, but the click engine is running."
            )
            return
        if self.main.clicker_page.apply_preset(preset, announce=False):
            self.main.log(
                "hotkey",
                f"App profile switched to {preset} for “{match.get('match')}”.",
            )
            self.main.toast("info", f"Profile active · {preset}")

    # ------------------------------------------------------------------
    # Schedules
    # ------------------------------------------------------------------
    def _refresh_macro_combo(self) -> None:
        if not hasattr(self, "macro_combo"):
            return
        current = self.macro_combo.currentData()
        self.macro_combo.blockSignals(True)
        self.macro_combo.clear()
        for macro_id, name in self.main.macro_page.macro_choices():
            self.macro_combo.addItem(name, macro_id)
        if current:
            index = self.macro_combo.findData(current)
            if index >= 0:
                self.macro_combo.setCurrentIndex(index)
        self.macro_combo.blockSignals(False)

    def _refresh_schedules(self, select_id: str | None = None) -> None:
        if select_id is None:
            select_id = self._selected_schedule_id
        self._refresh_macro_combo()
        self.schedule_list.blockSignals(True)
        self.schedule_list.clear()
        for schedule in self._schedules:
            item = QListWidgetItem(schedule_summary(schedule))
            item.setData(Qt.UserRole, schedule.get("id"))
            self.schedule_list.addItem(item)
            if schedule.get("id") == select_id:
                self.schedule_list.setCurrentItem(item)
        self.schedule_list.blockSignals(False)
        self.schedule_badge.setText(
            f"{len(self._schedules)} RUN{'S' if len(self._schedules) != 1 else ''}"
        )
        if not self._schedules:
            self._selected_schedule_id = None
        elif self.schedule_list.currentItem() is not None:
            self._on_schedule_selected(self.schedule_list.currentItem(), None)
        self._update_next_label()

    def _on_schedule_selected(self, current: QListWidgetItem | None, previous) -> None:
        if current is None:
            return
        schedule_id = str(current.data(Qt.UserRole))
        schedule = next(
            (item for item in self._schedules if item.get("id") == schedule_id), None
        )
        if not schedule:
            return
        self._selected_schedule_id = schedule_id
        self.time_input.setText(str(schedule.get("time", "")))
        self.schedule_enabled.setChecked(bool(schedule.get("enabled", True)))
        days = normalize_days(schedule.get("days"))
        preset_key = "every_day"
        if days == (0, 1, 2, 3, 4):
            preset_key = "weekdays"
        elif days == (5, 6):
            preset_key = "weekends"
        index = self.days_combo.findData(preset_key)
        if index >= 0:
            self.days_combo.setCurrentIndex(index)
        macro_index = self.macro_combo.findData(schedule.get("macro_id"))
        if macro_index >= 0:
            self.macro_combo.setCurrentIndex(macro_index)

    def _save_schedule(self) -> None:
        parsed = parse_clock(self.time_input.text())
        if not parsed:
            self.main.toast("warning", "Enter a valid 24-hour time, for example 18:30.")
            return
        macro_id = self.macro_combo.currentData()
        if not macro_id:
            self.main.toast("warning", "Record or import a macro before scheduling a run.")
            return
        macro_name = self.macro_combo.currentText()
        schedule = next(
            (item for item in self._schedules if item.get("id") == self._selected_schedule_id),
            None,
        )
        if schedule is None:
            schedule = {"id": uuid.uuid4().hex}
            self._schedules.append(schedule)
        schedule.update(
            {
                "time": f"{parsed[0]:02d}:{parsed[1]:02d}",
                "days": self.days_combo.currentData(),
                "macro_id": str(macro_id),
                "macro_name": macro_name,
                "enabled": self.schedule_enabled.isChecked(),
            }
        )
        self._last_fired.pop(str(schedule["id"]), None)
        self._selected_schedule_id = schedule["id"]
        self._persist_schedules()
        self._refresh_schedules(select_id=schedule["id"])
        self.main.log(
            "success",
            f"Scheduled run saved — {schedule['time']} {days_label(schedule['days'])}, {macro_name}.",
        )
        self.main.toast("success", f"Scheduled run saved · {schedule['time']}")

    def _delete_schedule(self) -> None:
        if not self._selected_schedule_id:
            self.main.toast("warning", "Select a scheduled run to delete first.")
            return
        schedule = next(
            (item for item in self._schedules if item.get("id") == self._selected_schedule_id),
            None,
        )
        if not schedule:
            return
        self._schedules = [item for item in self._schedules if item is not schedule]
        self._last_fired.pop(str(schedule.get("id")), None)
        self._selected_schedule_id = None
        self.time_input.clear()
        self._persist_schedules()
        self._refresh_schedules()
        self.main.toast("info", "Scheduled run deleted.")

    def _update_next_label(self) -> None:
        if not hasattr(self, "next_label"):
            return
        now = datetime.now()
        upcoming = []
        for schedule in self._schedules:
            if not schedule.get("enabled", True):
                continue
            moment = next_occurrence(str(schedule.get("time", "")), schedule.get("days"), now)
            if moment:
                upcoming.append((moment, schedule))
        if not upcoming:
            self.next_label.setText(
                "No upcoming runs — add a schedule or enable one below."
                if not self._schedules
                else "Every saved run is paused."
            )
            return
        moment, schedule = min(upcoming, key=lambda pair: pair[0])
        delta = moment - now
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        self.next_label.setText(
            f"NEXT RUN · {moment.strftime('%a %d %b %H:%M')} · {schedule.get('macro_name', 'Macro')} "
            f"(in {hours}h {minutes:02d}m)"
        )

    def _schedule_tick(self) -> None:
        self._update_next_label()
        if self.main._shutting_down:
            return
        now = datetime.now()
        due = due_schedules(self._schedules, now, self._last_fired)
        if not due:
            return
        for schedule, moment in due:
            key = str(schedule.get("id"))
            self._last_fired[key] = moment.isoformat(timespec="minutes")
            self._persist_schedules()
            macro_id = str(schedule.get("macro_id", ""))
            name = str(schedule.get("macro_name", "Macro"))
            if self.main.macro_page.play_macro_by_id(macro_id, loops=1):
                self.main.navigate("macro")
                self.main.log(
                    "hotkey",
                    f"Scheduled run started — {name} at {schedule.get('time')}.",
                )
                self.main.toast("success", f"Scheduled run · {name}")
            else:
                self.main.log(
                    "warning",
                    f"Scheduled run skipped — {name} is unavailable or another macro is playing.",
                )
        self._refresh_schedules(select_id=self._selected_schedule_id)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_preset_combo()
        self._refresh_macro_combo()
        self._update_next_label()


__all__ = ["AutomationPage"]
