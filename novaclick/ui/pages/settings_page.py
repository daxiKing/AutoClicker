"""Preferences, hotkey rebinding, data tools and about card."""

from __future__ import annotations

import sys
import threading

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import __tagline__, __version__
from ...core import i18n, wininput
from ...core.hotkeys import (
    ACTION_INFO,
    ACTION_ORDER,
    Binding,
    action_title,
    modifier_for_vk,
)
from ...core.keys import current_modifiers, pynput_key_to_vk
from ...core.paths import DATA_DIR
from ..theme import COLORS
from ..widgets import Card, HeroCard, LogoMark, ToggleSwitch, hline, label, make_button
from .base import Page


class SettingsPage(Page):
    hotkey_captured = Signal(object)

    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self._loading = True
        self._capture_action: str | None = None
        self._capture_listener = None
        self._capture_guard = threading.Event()
        self._capture_guard.set()
        self._capture_timeout = QTimer(self)
        self._capture_timeout.setSingleShot(True)
        self._capture_timeout.timeout.connect(self._cancel_hotkey_capture)
        self.hotkey_captured.connect(self._on_hotkey_captured)

        self._build_header()
        columns = QHBoxLayout()
        columns.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(self._build_behavior_card())
        left.addWidget(self._build_game_card())
        left.addWidget(self._build_data_card())
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self._build_hotkeys_card())
        right.addWidget(self._build_about_card())
        right.addStretch(1)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        self.layout.addLayout(columns)
        self._loading = False
        self._refresh()

    def _build_header(self) -> None:
        frame = HeroCard()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 17, 22, 17)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(label("CONTROL SURFACE", "Eyebrow"))
        text.addWidget(label("Make it behave your way.", "HeroTitle"))
        text.addWidget(label("Preferences apply instantly and persist between launches.", "HeroSub"))
        layout.addLayout(text, 1)
        layout.addWidget(label(f"v{__version__}", "VersionBadge"), 0, Qt.AlignTop)
        self.layout.addWidget(frame)

    def _build_behavior_card(self) -> Card:
        card = Card()
        card.body.addWidget(label("Behavior", "CardTitle"))

        delay_row = QHBoxLayout()
        delay_text = QVBoxLayout()
        delay_text.setSpacing(2)
        delay_text.addWidget(label("Start delay", "SectionTitle"))
        delay_text.addWidget(label("Give yourself time to switch windows after pressing start.", "Tiny", wrap=True))
        delay_row.addLayout(delay_text, 1)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 10.0)
        self.delay_spin.setSingleStep(0.5)
        self.delay_spin.setDecimals(1)
        self.delay_spin.setSuffix(" s")
        self.delay_spin.setFixedWidth(88)
        self.delay_spin.valueChanged.connect(self._on_delay_changed)
        delay_row.addWidget(self.delay_spin, 0, Qt.AlignTop)
        card.body.addLayout(delay_row)
        card.body.addWidget(hline())

        language_row = QHBoxLayout()
        language_text = QVBoxLayout()
        language_text.setSpacing(2)
        language_text.addWidget(label(i18n.tr("settings.language"), "SectionTitle"))
        language_text.addWidget(
            label(i18n.tr("settings.language_hint"), "Tiny", wrap=True)
        )
        language_row.addLayout(language_text, 1)
        self.language_combo = QComboBox()
        self.language_combo.setFixedWidth(230)
        self.language_combo.setToolTip(
            "Choose the interface language — untranslated text falls back to English."
        )
        for code, native, english in i18n.choices():
            text = native if native == english else f"{native} · {english}"
            self.language_combo.addItem(text, code)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_row.addWidget(self.language_combo, 0, Qt.AlignTop)
        card.body.addLayout(language_row)
        card.body.addWidget(hline())

        self.always_on_top = self._add_toggle(
            card.body,
            "Always on top",
            "Keep AutoClicker above other windows.",
            lambda checked: self.main.set_always_on_top(checked),
        )
        card.body.addWidget(hline())
        self.show_toasts = self._add_toggle(
            card.body,
            "Toast notifications",
            "Show small animated confirmations in the corner.",
            lambda checked: self.main.settings.set("show_toasts", checked),
        )
        card.body.addWidget(hline())
        self.confirm_delete = self._add_toggle(
            card.body,
            "Confirm macro deletion",
            "Ask before removing a macro and its JSON file.",
            lambda checked: self.main.settings.set("confirm_delete", checked),
        )
        card.body.addWidget(hline())

        self.click_sound = self._add_toggle(
            card.body,
            "Click sound",
            "Play a short system beep on each click for audible feedback.",
            lambda checked: self.main.settings.set("click_sound", checked),
        )
        card.body.addWidget(hline())

        self.target_window_toggle = self._add_toggle(
            card.body,
            "Only click when window matches",
            "Skip clicks unless the foreground window title contains the text below.",
            lambda checked: self.main.settings.set("target_window_filter", checked),
        )
        win_row = QHBoxLayout()
        win_text = QVBoxLayout()
        win_text.setSpacing(2)
        win_text.addWidget(label("Window title contains", "SectionTitle"))
        win_text.addWidget(label("Leave empty to match any window.", "Tiny", wrap=True))
        win_row.addLayout(win_text, 1)
        win_side = QVBoxLayout()
        win_side.setSpacing(4)
        self.target_window_combo = QComboBox()
        self.target_window_combo.setEditable(True)
        self.target_window_combo.setInsertPolicy(QComboBox.NoInsert)
        self.target_window_combo.setFixedWidth(240)
        self.target_window_combo.setToolTip("Type part of a title, or pick one from the list")
        self.target_window_combo.lineEdit().setPlaceholderText("e.g. Notepad")
        self.target_window_combo.lineEdit().textChanged.connect(
            lambda text: self.main.settings.set("target_window", text)
        )
        win_side.addWidget(self.target_window_combo)
        self.list_windows_btn = make_button("List open windows", "GhostButton")
        self.list_windows_btn.setToolTip("Fill the list with the titles of visible windows")
        self.list_windows_btn.clicked.connect(self._refresh_window_list)
        win_side.addWidget(self.list_windows_btn, 0, Qt.AlignRight)
        win_row.addLayout(win_side, 0)
        card.body.addLayout(win_row)
        return card

    def _refresh_window_list(self, notify: bool = True) -> None:
        combo = self.target_window_combo
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        titles = wininput.list_window_titles()
        combo.addItems(titles)
        combo.setCurrentText(current)
        combo.blockSignals(False)
        if not notify:
            return
        if titles:
            self.main.toast("info", f"Found {len(titles)} open windows.")
        else:
            self.main.toast("warning", "No open windows found.")

    def _build_game_card(self) -> Card:
        card = Card()
        card.body.addWidget(label("Game input", "CardTitle"))
        card.body.addWidget(
            label(
                "Send keyboard input as hardware scan codes and give AutoClicker high "
                "process priority. This improves reliability in DirectInput-era games "
                "that sample raw keyboard state, without touching anti-cheat.",
                "Muted",
                wrap=True,
            )
        )
        self.game_mode = self._add_toggle(
            card.body,
            "Game input mode",
            "Scan-code keystrokes + high priority. Works best with windowed or borderless games.",
            self._on_game_mode_toggled,
        )
        self.game_status = label("SCAN-CODE INPUT OFF · NORMAL PRIORITY", "Tiny", wrap=True)
        card.body.addWidget(self.game_status)
        if not sys.platform.startswith("win"):
            self.game_mode.setEnabled(False)
            self.game_status.setText(
                "GAME INPUT MODE IS WINDOWS-ONLY · X11/WAYLAND INPUT IS NATIVE"
            )
        card.body.addWidget(hline())

        admin_row = QHBoxLayout()
        admin_text = QVBoxLayout()
        admin_text.setSpacing(2)
        admin_text.addWidget(label("Administrator access", "SectionTitle"))
        self.admin_status = label("", "Tiny", wrap=True)
        admin_text.addWidget(self.admin_status)
        admin_row.addLayout(admin_text, 1)
        self.admin_btn = make_button("Restart as administrator", "GhostButton")
        self.admin_btn.setToolTip(
            "Relaunch elevated so hotkeys and input can reach elevated game windows."
        )
        self.admin_btn.clicked.connect(self._restart_as_admin)
        admin_row.addWidget(self.admin_btn, 0, Qt.AlignTop)
        card.body.addLayout(admin_row)
        card.body.addWidget(
            label(
                "Windows blocks synthetic input from reaching elevated windows unless both "
                "programs run at the same integrity level. Exclusive fullscreen games may "
                "still ignore any synthetic input; borderless windowed mode is recommended.",
                "Tiny",
                wrap=True,
            )
        )
        return card

    def _on_game_mode_toggled(self, checked: bool) -> None:
        if self._loading:
            return
        self.main.set_game_mode(bool(checked))

    def sync_game_mode(self, enabled: bool) -> None:
        if not hasattr(self, "game_mode"):
            return
        self.game_mode.blockSignals(True)
        self.game_mode.setChecked(bool(enabled))
        self.game_mode.blockSignals(False)
        if hasattr(self, "game_status"):
            if not sys.platform.startswith("win"):
                self.game_status.setText(
                    "GAME INPUT MODE IS WINDOWS-ONLY · X11/WAYLAND INPUT IS NATIVE"
                )
            else:
                self.game_status.setText(
                    "SCAN-CODE INPUT ON · HIGH PRIORITY"
                    if enabled
                    else "SCAN-CODE INPUT OFF · NORMAL PRIORITY"
                )
        self._refresh_admin_status()

    def _refresh_admin_status(self) -> None:
        if not hasattr(self, "admin_status"):
            return
        if not sys.platform.startswith("win"):
            self.admin_status.setText(
                "Linux uses native X11/Wayland input; administrator access is not required."
            )
            self.admin_btn.setEnabled(False)
            self.admin_btn.setText("Not required on Linux")
            return
        elevated = wininput.is_admin()
        self.admin_status.setText(
            "Running elevated — hotkeys can reach administrator windows."
            if elevated
            else "Standard user. Some elevated game windows will ignore input and hotkeys."
        )
        self.admin_btn.setEnabled(not elevated)
        self.admin_btn.setText("Administrator active" if elevated else "Restart as administrator")

    def _restart_as_admin(self) -> None:
        if wininput.is_admin():
            self.main.toast("info", "AutoClicker is already running as administrator.")
            return
        answer = QMessageBox.question(
            self,
            "Restart as administrator",
            "AutoClicker will close and Windows will ask for elevation. "
            "Macros and settings are kept.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if not wininput.relaunch_as_admin():
            self.main.toast("error", "Could not launch the elevated copy.")
            self.main.log("error", "Administrator relaunch failed.")
            return
        self.main.log("info", "Relaunching as administrator — waiting for UAC confirmation.")
        self.main.toast("info", "Relaunching elevated — confirm the Windows prompt.")
        QTimer.singleShot(350, QApplication.quit)

    def _add_toggle(self, layout: QVBoxLayout, title: str, description: str, callback) -> ToggleSwitch:
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title, "SectionTitle"))
        text.addWidget(label(description, "Tiny"))
        row.addLayout(text, 1)
        toggle = ToggleSwitch(False)
        toggle.toggled.connect(callback)
        row.addWidget(toggle)
        layout.addLayout(row)
        return toggle

    def _build_hotkeys_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Global hotkeys", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("CLICK TO REBIND", "Tiny"))
        card.body.addLayout(header)
        card.body.addWidget(
            label(
                "Bind any key or modifier combo. Changes are live and saved instantly.",
                "Muted",
                wrap=True,
            )
        )

        self._hotkey_buttons: dict[str, QPushButton] = {}
        for action in ACTION_ORDER:
            title, description, tone = ACTION_INFO[action]
            row = QHBoxLayout()
            row.setSpacing(11)
            button = QPushButton(self.main.hotkey_label(action))
            button.setObjectName("KeycapButton")
            button.setProperty("tone", tone)
            button.setFixedSize(124, 31)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(
                f"{title} · {self.main.hotkey_label(action)} — click, then press a key"
            )
            button.clicked.connect(
                lambda checked=False, key=action: self._begin_hotkey_capture(key)
            )
            self._hotkey_buttons[action] = button
            row.addWidget(button, 0, Qt.AlignTop)
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(label(title, "SectionTitle"))
            text.addWidget(label(description, "Tiny", wrap=True))
            row.addLayout(text, 1)
            card.body.addLayout(row)

        self.hotkey_status = label(
            "Click a keycap, then press any key or combo. Esc clears the binding; "
            "click the same keycap again to cancel.",
            "Tiny",
            wrap=True,
        )
        card.body.addWidget(self.hotkey_status)
        card.body.addWidget(hline())

        footer = QHBoxLayout()
        footer.setSpacing(8)
        reset_btn = make_button("Reset hotkeys", "GhostButton")
        reset_btn.clicked.connect(self.main.reset_hotkeys)
        footer.addWidget(reset_btn)
        footer.addStretch(1)
        footer.addWidget(label("ESC CLEARS", "Tiny"))
        card.body.addLayout(footer)
        card.body.addWidget(
            label(
                "Hotkeys listen globally without stealing keystrokes. Some elevated windows "
                "may require running AutoClicker as administrator.",
                "Tiny",
                wrap=True,
            )
        )
        return card

    def _build_data_card(self) -> Card:
        card = Card()
        card.body.addWidget(label("Data & maintenance", "CardTitle"))
        path = label(str(DATA_DIR), "Tiny", wrap=True)
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.body.addWidget(path)
        row = QHBoxLayout()
        row.setSpacing(8)
        open_btn = make_button("Open data folder", "GhostButton")
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR)))
        )
        row.addWidget(open_btn)
        clear_btn = make_button("Clear activity log", "GhostButton")
        clear_btn.clicked.connect(self.main.activity.clear)
        row.addWidget(clear_btn)
        row.addStretch(1)
        card.body.addLayout(row)
        card.body.addWidget(hline())
        reset_btn = make_button("Reset all preferences", "DangerButton")
        reset_btn.clicked.connect(self._reset_settings)
        card.body.addWidget(reset_btn, 0, Qt.AlignLeft)
        return card

    def _build_about_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.setSpacing(13)
        header.addWidget(LogoMark(52))
        text = QVBoxLayout()
        text.setSpacing(1)
        title = label("AutoClicker", "CardTitle")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #000080;")
        text.addWidget(title)
        text.addWidget(label(__tagline__, "Tiny"))
        header.addLayout(text, 1)
        header.addWidget(label(f"v{__version__}", "VersionBadge"), 0, Qt.AlignTop)
        card.body.addLayout(header)
        card.body.addWidget(hline())
        for key, value in (
            (
                "ENGINE",
                "Win32 SendInput"
                if sys.platform.startswith("win")
                else "pynput / X11-Wayland",
            ),
            ("INTERFACE", "PySide6 / Qt"),
            ("RELEASE", "November 16, 2026"),
            ("STORAGE", "Portable / local JSON"),
        ):
            row = QHBoxLayout()
            row.addWidget(label(key, "Tiny"))
            row.addStretch(1)
            row.addWidget(label(value, "Muted"))
            card.body.addLayout(row)
        card.body.addWidget(hline())
        card.body.addWidget(
            label(
                "AutoClicker only sends synthetic input; it does not read, collect or transmit screen "
                "content. Image matching happens entirely on this machine. Use automation "
                "responsibly and only where it is permitted.",
                "Tiny",
                wrap=True,
            )
        )
        return card

    # ------------------------------------------------------------------
    # Hotkey capture
    # ------------------------------------------------------------------
    def _refresh_hotkey_buttons(self) -> None:
        for action, button in getattr(self, "_hotkey_buttons", {}).items():
            title = action_title(action)
            if self._capture_action == action:
                button.setText("Press a key…")
                button.setToolTip(
                    "Listening for a key or combo. Esc clears this hotkey."
                )
                continue
            binding = self.main.hotkey_label(action)
            button.setText(binding)
            button.setToolTip(
                f"{title} · {binding} — click, then press a key (Esc clears it)"
            )

    def _begin_hotkey_capture(self, action: str) -> None:
        if self._capture_action == action:
            self._cancel_hotkey_capture()
            return
        if self._capture_action is not None:
            self._end_hotkey_capture(restore_status=False)

        self._capture_action = action
        self._capture_guard.clear()
        self.main.suspend_hotkeys(True)
        self._start_hotkey_listener()
        self._capture_timeout.start(8000)

        for key, button in self._hotkey_buttons.items():
            button.setEnabled(key == action)
            button.setProperty("capturing", key == action)
            button.style().unpolish(button)
            button.style().polish(button)
        self._refresh_hotkey_buttons()
        self._set_hotkey_status(
            f"Listening for {action_title(action)} — press a key or combo now. "
            "Esc clears the binding.",
            COLORS["accent"],
        )
        self.main.log("info", f"Rebinding {action_title(action)} hotkey — listening.")

    def _start_hotkey_listener(self) -> None:
        try:
            from pynput import keyboard

            listener = keyboard.Listener(on_press=self._on_hotkey_key)
            listener.daemon = True
            listener.start()
            self._capture_listener = listener
        except Exception as exc:
            self._capture_listener = None
            self._end_hotkey_capture(restore_status=False)
            self.main.toast("error", f"Hotkey capture unavailable: {exc}")
            self.main.log("error", f"Hotkey capture listener failed: {exc}")
            self._set_hotkey_status("Hotkey capture unavailable.", COLORS["red"])

    def _on_hotkey_key(self, key) -> None:
        """Called on the pynput thread; signal-marshalled back to the UI."""
        if self._capture_guard.is_set():
            return
        vk = pynput_key_to_vk(key)
        if vk is None:
            return
        if vk == 0x1B:
            # Esc is the "clear binding" key: the action becomes unbound.
            self._capture_guard.set()
            self.hotkey_captured.emit(None)
            return
        if modifier_for_vk(vk) is not None:
            return
        self._capture_guard.set()
        self.hotkey_captured.emit(Binding(vk, current_modifiers()))

    def _on_hotkey_captured(self, binding) -> None:
        action = self._capture_action
        if action is None:
            return
        self._end_hotkey_capture(restore_status=False)
        if binding is None:
            # Esc pressed during capture: clear this action's binding.
            success, message = self.main.unbind_hotkey(action)
            if success:
                self._set_hotkey_status(
                    f"{action_title(action)} is now unbound. Click a keycap to set a new key.",
                    COLORS["accent"],
                )
            else:
                self._set_hotkey_status(message, COLORS["red"])
                self.main.log("warning", f"Hotkey unbind failed — {message}")
            self._refresh_hotkey_buttons()
            return
        success, message = self.main.set_hotkey(action, binding)
        if success:
            self._set_hotkey_status(
                f"{action_title(action)} is now {binding.label()}.", COLORS["accent"]
            )
        else:
            self._set_hotkey_status(message, COLORS["red"])
            self.main.toast("warning", message)
            self.main.log("warning", f"Hotkey rejected — {message}")
        self._refresh_hotkey_buttons()

    def _cancel_hotkey_capture(self) -> None:
        if self._capture_action is None:
            return
        self._end_hotkey_capture(restore_status=False)
        self._set_hotkey_status("Rebind cancelled — hotkey unchanged.", COLORS["muted"])
        self.main.log("info", "Hotkey rebind cancelled.")

    def _end_hotkey_capture(self, restore_status: bool = True) -> None:
        self._capture_timeout.stop()
        self._capture_guard.set()
        listener = self._capture_listener
        self._capture_listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        self._capture_action = None
        try:
            self.main.suspend_hotkeys(False)
        except Exception:
            pass
        for button in getattr(self, "_hotkey_buttons", {}).values():
            button.setEnabled(True)
            button.setProperty("capturing", False)
            button.style().unpolish(button)
            button.style().polish(button)
        self._refresh_hotkey_buttons()
        if restore_status:
            self._set_hotkey_status(
                "Click a keycap, then press any key or combo. Esc clears the binding; "
                "click the same keycap again to cancel.",
                COLORS["muted"],
            )

    def _set_hotkey_status(self, text: str, color: str) -> None:
        if not hasattr(self, "hotkey_status"):
            return
        self.hotkey_status.setText(text)
        self.hotkey_status.setStyleSheet(f"font-size: 10px; color: {color};")

    def refresh_hotkeys(self) -> None:
        self._refresh_hotkey_buttons()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self._capture_action is not None:
            self._cancel_hotkey_capture()

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        self._loading = True
        settings = self.main.settings
        self.delay_spin.setValue(float(settings.get("start_delay_ms", 0)) / 1000.0)
        current_language = i18n.normalize_language(
            str(settings.get("language", i18n.get_language()) or "en")
        )
        index = self.language_combo.findData(current_language)
        if index >= 0:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(index)
            self.language_combo.blockSignals(False)
        for toggle, key, default in (
            (self.always_on_top, "always_on_top", False),
            (self.show_toasts, "show_toasts", True),
            (self.confirm_delete, "confirm_delete", True),
            (self.game_mode, "game_mode", False),
            (self.click_sound, "click_sound", False),
            (self.target_window_toggle, "target_window_filter", False),
        ):
            toggle.blockSignals(True)
            toggle.setChecked(bool(settings.get(key, default)))
            toggle.blockSignals(False)
        self.target_window_combo.setCurrentText(str(settings.get("target_window", "")))
        self._refresh_window_list(notify=False)
        self.sync_game_mode(bool(settings.get("game_mode", False)))
        self._refresh_hotkey_buttons()
        self._loading = False

    def _on_delay_changed(self, value: float) -> None:
        if self._loading:
            return
        self.main.settings.set("start_delay_ms", int(round(value * 1000)))

    def _on_language_changed(self, index: int) -> None:
        if self._loading or index < 0:
            return
        code = self.language_combo.itemData(index)
        if code:
            self.main.set_language(str(code))

    def _reset_settings(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset preferences",
            "Restore all preferences and hotkeys to their defaults? Macros and images will not be touched.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.main.settings.reset()
        self.main.set_always_on_top(False)
        self.main.set_game_mode(False, announce=False)
        self.main.reset_hotkeys()
        self._refresh()
        self.main.log("info", "Preferences and hotkeys reset to defaults.")
