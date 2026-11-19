"""Release notes and live activity log."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..activity import ActivityLog
from ..theme import COLORS
from ..widgets import Card, HeroCard, hline, label, make_button
from .base import Page

UPDATES = [
    {
        "version": "2.5.0",
        "codename": "Orbit",
        "date": "November 19, 2026",
        "latest": True,
        "items": [
            "Visual macro editor — open any recording and trim a time range, reorder events, nudge timestamps by ±10 ms, delete selections or revert, with the timeline rebuilt and saved in one step.",
            "App profiles — match a foreground window title fragment to a saved clicker preset and apply it automatically when the engine is idle, with a one-click “Use active window” capture.",
            "Scheduled runs — play a macro at a local time on weekdays, weekends or every day, checked every 15 seconds and remembered across restarts.",
            "Conditional image sequences — chain steps that click a target, press a key, wait or stop; each scan step has a timeout and a skip, retry-forever or hard-stop miss policy.",
            "Compact run HUD — a small always-on-top status bar shows click, key, macro or sequence telemetry and stops everything with one button.",
            "Automation page — a dedicated home for profiles and schedules, grouped under AUTOMATION in the sidebar.",
            "Sequence runner core — validated steps, template caching, per-step progress and injectable matcher/actor/grabber hooks for testing.",
            "All v2.4.0 features retained: rebuilt engines, Discord Rich Presence, Explore, 43 languages, Linux builds and GitHub auto-updates.",
        ],
    },
    {
        "version": "2.4.0",
        "codename": "Nebula",
        "date": "November 17, 2026",
        "latest": False,
        "items": [
            "1000× better everything — rebuilt click engine pacing, smoother auto-key timing, tighter macro playback and faster image-target scans across Windows and Linux.",
            "Discord Rich Presence — publishes the live engine state, session timer and a GitHub link through Discord's local IPC socket with its own public client ID.",
            "Explore tab — browse Steam Specials, top sellers, new releases and coming-soon games, with discount badges, USD prices and one-click store links.",
            "Connections — toggle Rich Presence, link a public Steam community profile (no password) and link the GitHub repository used for updates.",
            "GitHub auto-updates — compares the installed build with the newest public release, downloads the installer into Downloads and checks quietly on startup.",
            "43 interface languages — persisted language picker with English fallback for untranslated text.",
            "Linux support — a pynput X11/Wayland input backend, platform-aware settings, a .desktop entry and CI packages for Windows and Linux.",
            "Discord IPC fixed — presence connects reliably through the native asyncio named-pipe transport.",
            "Panic overlay fixed — the red flash now fades through a real Qt animation instead of referencing an undefined animation object.",
            "All v2.3.0 features retained: image targeting, exact-color matching, test probes and stop-after-N click limit.",
        ],
    },
    {
        "version": "2.3.0",
        "codename": "Atlas",
        "date": "November 17, 2026",
        "latest": False,
        "items": [
            "Discord Rich Presence — publish the live engine state, session timer and a GitHub link to your Discord profile; the app connects through the local Discord IPC socket with its own public client ID.",
            "Explore tab — browse Steam Specials, top sellers, new releases and coming-soon games, with discount badges, USD prices and one-click store links.",
            "Connections — toggle Rich Presence, link a public Steam community profile (no password) and link the GitHub repository used for updates.",
            "GitHub auto-updater — compare the installed build with the newest public release, download the installer into Downloads and optionally check on startup.",
            "30+ languages — 43 interface locales with a persisted language picker and English fallback for untranslated text.",
            "Linux support — a pynput X11/Wayland input backend, platform-aware settings, a .desktop entry and GitHub Actions packages for Windows and Linux.",
            "Panic overlay fixed — the red flash now fades through a real Qt animation instead of referencing an undefined animation object.",
            "All v2.2.0 features retained: the image-target library, exact-color matching, test probes and the stop-after-N click limit.",
        ],
    },
    {
        "version": "2.2.0",
        "codename": "Kaleidoscope",
        "date": "November 16, 2026",
        "latest": False,
        "items": [
            "Image targeting remastered — build a library of target images and scan them as a set; the best-scoring target wins each pass.",
            "Exact-color matching — compare full color instead of brightness, or flip it off for faster grayscale matching.",
            "Test match — probe the screen once, report the best score, position and matched target without clicking.",
            "Stop after N clicks — cap image runs alongside the existing one-shot mode.",
            "Target library persistence — enabled/disabled state and paths survive restarts; paste captures straight into data\\targets.",
            "Telemetry now names the matched target alongside score, scans, clicks and coordinates.",
            "All v2.1.1 features retained: Esc-to-unbind hotkeys and the expanded image format support.",
        ],
    },
    {
        "version": "2.1.1",
        "codename": "Service Pack",
        "date": "November 16, 2026",
        "latest": False,
        "items": [
            "Esc now clears a hotkey — while listening, press Esc to unbind that action; the keycap reads UNBOUND and the shortcut stops firing globally.",
            "Unbound hotkeys persist across restarts and are ignored by the global listener; bind a new key any time.",
            "Image targets accept far more formats — PNG, JPG, WebP, GIF, TIFF, BMP, ICO and SVG, with a Qt decode fallback for anything OpenCV cannot read.",
            "Paste target images straight from the clipboard — saved under data\\targets so they survive restarts.",
            "File picker and drag-and-drop now offer the full supported-format list.",
            "All v2.1.0 features retained: presets, auto-key auto-stop, window picker and the AutoClicker rebrand.",
        ],
    },
    {
        "version": "2.1.0",
        "codename": "Solid State",
        "date": "November 16, 2026",
        "latest": False,
        "items": [
            "Rebranded to AutoClicker — new name, new cursor-and-sparks icon, new installer and boot screen.",
            "Escape can now be bound as a hotkey — capture no longer cancels on Esc; click the keycap again to cancel.",
            "Presets — save, load and delete complete clicker setups: rate, button, style, position, jitter, chaos and auto-stop.",
            "Auto-key auto-stop — halt the key stream after N presses or N seconds, matching the click engine.",
            "Window picker — fill the click-filter list with the titles of all open windows instead of typing blind.",
            "Pages re-sorted — dedicated Presets and Auto-stop sections, clearer grouping on Settings.",
            "Settings store hardened — click sound, window filter and presets now persist across restarts.",
            "All v2.0.0 features retained: auto-stop timer, click sound, window filter and macro import/export.",
        ],
    },
    {
        "version": "2.0.0",
        "codename": "Overdrive",
        "date": "November 16, 2026",
        "latest": False,
        "items": [
            "Auto-stop timer — halt the click engine after N clicks or N seconds.",
            "Click sound — optional system beep on every click for audible feedback.",
            "Window target filter — only click when a matching foreground window is active.",
            "Macro import and export — share and restore recorded sequences as JSON.",
            "Clicker now exposes Left / Right / Middle mouse button in the rate card.",
            "Retro Windows 95/98 interface sharpened — flat bevels, no gradients, Tahoma throughout.",
            "All v1.0.0 features retained: 1–1,000 CPS, uncapped burst, infinite macro loops, image targeting, rebindable hotkeys, game input mode.",
        ],
    },
    {
        "version": "1.0.0",
        "codename": "Ignition",
        "date": "November 15, 2026",
        "latest": False,
        "items": [
            "Native SendInput click engine with 1–1,000 CPS pacing and uncapped burst mode.",
            "Unlimited-duration macro recorder with infinite replay, speed control and JSON export.",
            "Auto-key engine with any-key binding, hold duration and up to 500 presses per second.",
            "Image targeting with confidence threshold, click offsets, monitor selection and one-shot mode.",
            "Fully rebindable global hotkeys with modifier combos, conflict checks and instant persistence.",
            "Game input mode with scan-code keystrokes, high process priority and optional administrator relaunch.",
            "Retro Windows 95/98 interface with a Mystify desktop backdrop, boot screen and animated meters.",
            "Persistent macro vault, settings, session telemetry and a full activity log.",
        ],
    },
    {
        "version": "0.9.0",
        "codename": "Blueprint",
        "date": "November 2, 2026",
        "latest": False,
        "items": [
            "First pass at the Win32 input pipeline and click pacing scheduler.",
            "Macro capture and playback proof of concept.",
            "Visual language, navigation and component library established.",
        ],
    },
]

ROADMAP = [
    {
        "version": "2.5.0",
        "codename": "Orbit",
        "status": "SHIPPED",
        "headline": "Automation that watches your workflow.",
        "items": [
            "Visual macro timeline editor — trim, reorder, nudge, delete and rebuild.",
            "Per-app profiles — window-title matching applies saved clicker presets.",
            "Scheduled runs — local-time macro playback on chosen days.",
            "Conditional image sequences — click, key, wait or stop with miss policies.",
            "Compact run HUD — floating telemetry with a one-click panic stop.",
        ],
    },
    {
        "version": "2.6.0",
        "codename": "Pulse",
        "status": "NEXT",
        "headline": "Smarter flows, fewer gaps.",
        "items": [
            "Macro conditionals — per-event waits, loop counts and if-image-visible branches.",
            "Sequence branching — jump to another step on match or miss instead of running linearly.",
            "Profile bundles — export and import app profiles, schedules and macros together.",
            "HUD layouts — compact, expanded and corner-snapped placements.",
        ],
    },
    {
        "version": "2.7.0",
        "codename": "Prism",
        "status": "EXPLORING",
        "headline": "See more, script less.",
        "items": [
            "Drag-selected scan regions across multiple monitors.",
            "OCR triggers for menus, chat and HUD text.",
            "Opt-in, local-first cloud sync for the macro vault.",
            "Plugin hooks for community steps and actions.",
        ],
    },
]

STATUS_STYLES = {
    "SHIPPED": ("#008000", "#ffffe1"),
    "NEXT": ("#000080", "#cce8ff"),
    "EXPLORING": ("#404040", "#e8e8e8"),
}


class UpdatesPage(Page):
    def __init__(self, main, activity: ActivityLog) -> None:
        super().__init__()
        self.main = main
        self.activity = activity
        self._build_header()
        columns = QHBoxLayout()
        columns.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(self._build_roadmap_card())
        left.addWidget(self._build_release_card())
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self._build_activity_card())
        right.addStretch(1)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        self.layout.addLayout(columns)

        self.activity.entry.connect(self._append_entry)
        self.activity.cleared.connect(self._clear_view)
        self._reload_entries()

    def _build_header(self) -> None:
        frame = HeroCard()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 17, 22, 17)
        layout.setSpacing(14)
        text = QVBoxLayout()
        text.setSpacing(4)
        eyebrow = label("SYSTEM JOURNAL", "Eyebrow")
        text.addWidget(eyebrow)
        title = label("Every change, every action.", "HeroTitle")
        text.addWidget(title)
        sub = label(
            "Roadmap milestones, release notes and a real-time feed of engine events, hotkeys and faults.",
            "HeroSub",
        )
        text.addWidget(sub)
        layout.addLayout(text, 1)
        badge = label("v2.5.0 · LATEST", "VersionBadge")
        badge.setStyleSheet(
            "background: #ffffff; border: 2px solid; border-top-color: #404040; "
            "border-left-color: #404040; border-right-color: #ffffff; "
            "border-bottom-color: #ffffff; color: #000080; "
            "font-family: 'Courier New'; font-size: 10px; "
            "font-weight: 700; padding: 6px 10px;"
        )
        layout.addWidget(badge, 0, Qt.AlignTop)
        self.layout.addWidget(frame)

    def _build_release_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Update log", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("STABLE CHANNEL", "Tiny"))
        card.body.addLayout(header)

        for index, update in enumerate(UPDATES):
            if index:
                card.body.addWidget(hline())
            block = QVBoxLayout()
            block.setSpacing(7)
            version_row = QHBoxLayout()
            version_row.setSpacing(9)
            version = QLabel(f"v{update['version']}")
            version.setStyleSheet(
                "font-family: 'Courier New'; font-size: 18px; font-weight: 700; color: #000080;"
            )
            version_row.addWidget(version)
            codename = label(update["codename"], "SectionTitle")
            version_row.addWidget(codename)
            if update["latest"]:
                latest = label("LATEST", "VersionBadge")
                latest.setStyleSheet(
                    "background: #ffffe1; border: 1px solid #000000; "
                    "color: #008000; font-size: 8px; font-weight: 700; padding: 2px 6px;"
                )
                version_row.addWidget(latest)
            version_row.addStretch(1)
            version_row.addWidget(label(update["date"], "Tiny"))
            block.addLayout(version_row)

            for item in update["items"]:
                row = QHBoxLayout()
                row.setSpacing(9)
                dot = QLabel("▸")
                dot.setStyleSheet(
                    f"color: {COLORS['accent'] if update['latest'] else COLORS['faint']}; font-size: 10px;"
                )
                row.addWidget(dot, 0, Qt.AlignTop)
                row.addWidget(label(item, "Muted", wrap=True), 1)
                block.addLayout(row)
            card.body.addLayout(block)
        return card

    def _build_roadmap_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Roadmap", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("UPDATED FOR 2.5.0", "Tiny"))
        card.body.addLayout(header)
        card.body.addWidget(
            label(
                "Shipped work is archived below. Next is the planned 2.6.0 line; "
                "exploring items are under evaluation and may move.",
                "Muted",
                wrap=True,
            )
        )
        for index, milestone in enumerate(ROADMAP):
            if index:
                card.body.addWidget(hline())
            color, background = STATUS_STYLES.get(
                milestone["status"], STATUS_STYLES["EXPLORING"]
            )
            block = QVBoxLayout()
            block.setSpacing(6)
            title_row = QHBoxLayout()
            title_row.setSpacing(8)
            version = QLabel(f"v{milestone['version']}")
            version.setStyleSheet(
                "font-family: 'Courier New'; font-size: 15px; font-weight: 700; color: #000080;"
            )
            title_row.addWidget(version)
            title_row.addWidget(label(milestone["codename"], "SectionTitle"))
            chip = label(milestone["status"], "VersionBadge")
            chip.setStyleSheet(
                f"background: {background}; border: 1px solid #808080; color: {color}; "
                "font-size: 8px; font-weight: 700; padding: 2px 5px;"
            )
            title_row.addWidget(chip)
            title_row.addStretch(1)
            block.addLayout(title_row)
            block.addWidget(label(milestone["headline"], "Tiny"))
            for item in milestone["items"]:
                row = QHBoxLayout()
                row.setSpacing(9)
                dot = QLabel("▸")
                dot.setStyleSheet(f"color: {color}; font-size: 10px;")
                row.addWidget(dot, 0, Qt.AlignTop)
                row.addWidget(label(item, "Muted", wrap=True), 1)
                block.addLayout(row)
            card.body.addLayout(block)
        return card

    def _build_activity_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Activity log", "CardTitle"))
        header.addStretch(1)
        self.feed_badge = label("LIVE FEED", "VersionBadge")
        header.addWidget(self.feed_badge)
        card.body.addLayout(header)

        subtitle = label(
            "Runtime events, state changes and errors — newest at the bottom.",
            "Tiny",
        )
        card.body.addWidget(subtitle)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        self.view.setMinimumHeight(470)
        self.view.document().setMaximumBlockCount(800)
        self.view.setStyleSheet(
            "QTextBrowser { background: #ffffff; border: 2px solid; "
            "border-top-color: #404040; border-left-color: #404040; "
            "border-right-color: #ffffff; border-bottom-color: #ffffff; "
            "color: #000000; padding: 8px; font-size: 11px; }"
        )
        card.body.addWidget(self.view, 1)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        controls.addWidget(self.auto_scroll)
        controls.addStretch(1)
        self.copy_btn = make_button("Copy", "GhostButton")
        self.copy_btn.clicked.connect(self._copy_log)
        controls.addWidget(self.copy_btn)
        self.clear_btn = make_button("Clear", "GhostButton")
        self.clear_btn.clicked.connect(self.activity.clear)
        controls.addWidget(self.clear_btn)
        card.body.addLayout(controls)
        return card

    # ------------------------------------------------------------------
    def _reload_entries(self) -> None:
        self.view.clear()
        for timestamp, level, message in self.activity.entries():
            self._append_entry(timestamp, level, message)
        self._scroll_to_end()

    @staticmethod
    def _tag_for(level: str) -> tuple[str, str]:
        mapping = {
            "success": ("#008000", "OK"),
            "warning": ("#808000", "WARN"),
            "error": ("#800000", "ERR"),
            "hotkey": ("#800080", "HOTKEY"),
            "info": ("#404040", "INFO"),
        }
        return mapping.get(level, mapping["info"])

    def _append_entry(self, timestamp: str, level: str, message: str) -> None:
        color, tag = self._tag_for(level)
        safe_message = html.escape(str(message)).replace("\n", "<br>")
        block = (
            f'<div style="margin: 1px 0;">'
            f'<span style="color:#808080; font-family:\'Courier New\';">[{html.escape(timestamp)}]</span> '
            f'<span style="color:{color}; font-weight:700;">{tag}</span> '
            f'<span style="color:#000000; font-family:\'Courier New\';">{safe_message}</span>'
            f'</div>'
        )
        self.view.append(block)
        if self.auto_scroll.isChecked():
            self._scroll_to_end()

    def _scroll_to_end(self) -> None:
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _clear_view(self) -> None:
        self.view.clear()
        self.main.toast("info", "Activity log cleared.")

    def _copy_log(self) -> None:
        from PySide6.QtWidgets import QApplication

        lines = [f"[{timestamp}] {level.upper()}: {message}" for timestamp, level, message in self.activity.entries()]
        QApplication.clipboard().setText("\n".join(lines))
        self.main.toast("success", "Activity log copied to the clipboard.")
