"""Explore page — Steam storefront, account connections and GitHub releases."""

from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from ...core import updater
from ..theme import COLORS
from ..widgets import (
    Card,
    HeroCard,
    SegmentedControl,
    ToggleSwitch,
    hline,
    label,
    make_button,
    PulseDot,
)
from .base import Page

STEAM_FEED_URL = "https://store.steampowered.com/api/featuredcategories?cc=us&l=english"
STEAM_CATEGORIES = (
    ("specials", "SPECIALS", "Steam Specials"),
    ("top_sellers", "TOP SELLERS", "Top Sellers"),
    ("new_releases", "NEW RELEASES", "New Releases"),
    ("coming_soon", "COMING SOON", "Coming Soon"),
)
MAX_ROWS = 7


def _format_price(value) -> str:
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return ""
    if cents <= 0:
        return "Free"
    return f"${cents / 100:.2f}"


def _extract_steam_target(value: str) -> tuple[str, str]:
    """Return ("id"|"vanity", token) from a profile URL or bare name."""
    text = value.strip()
    if not text:
        raise ValueError("Enter a Steam profile URL, vanity name or SteamID64.")
    if "steamcommunity.com" in text or text.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(text if "://" in text else f"https://{text}")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in ("id", "profiles"):
            kind = "profiles" if parts[0] == "profiles" else "id"
            return ("id" if kind == "profiles" else "vanity", parts[1])
        raise ValueError("That URL is not a Steam community profile.")
    if text.isdigit() and len(text) >= 16:
        return "id", text
    return "vanity", text


class ExplorePage(Page):
    steam_ready = Signal(object)
    steam_failed = Signal(str)
    profile_ready = Signal(str, object)
    profile_failed = Signal(str, str)
    release_ready = Signal(object)
    release_failed = Signal(str)
    download_ready = Signal(str, str)
    download_failed = Signal(str)
    download_progress = Signal(int, int)

    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self._steam_payload: dict | None = None
        self._steam_category = "specials"
        self._steam_busy = False
        self._release: dict | None = None
        self._checking = False
        self._downloading = False
        self._silent_check = False
        self._profile_meta: dict = {}

        self._build_header()
        columns = QHBoxLayout()
        columns.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(self._build_steam_card())
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self._build_connections_card())
        right.addWidget(self._build_updates_card())
        right.addStretch(1)
        columns.addLayout(left, 3)
        columns.addLayout(right, 2)
        self.layout.addLayout(columns)

        self.steam_ready.connect(self._on_steam_ready)
        self.steam_failed.connect(self._on_steam_failed)
        self.profile_ready.connect(self._on_profile_ready)
        self.profile_failed.connect(self._on_profile_failed)
        self.release_ready.connect(self._on_release_ready)
        self.release_failed.connect(self._on_release_failed)
        self.download_ready.connect(self._on_download_ready)
        self.download_failed.connect(self._on_download_failed)
        self.download_progress.connect(self._on_download_progress)

        self._presence_timer = QTimer(self)
        self._presence_timer.setInterval(1100)
        self._presence_timer.timeout.connect(self.refresh_presence)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        frame = HeroCard()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 17, 22, 17)
        layout.setSpacing(14)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(label("DISCOVERY NETWORK", "Eyebrow"))
        text.addWidget(label("Explore beyond the click.", "HeroTitle"))
        text.addWidget(
            label(
                "Steam deals, connected accounts and GitHub releases — one retro console.",
                "HeroSub",
            )
        )
        layout.addLayout(text, 1)
        badge = label(f"v{__version__} · NETWORKED", "VersionBadge")
        badge.setStyleSheet(
            "background: #ffffff; border: 2px solid; border-top-color: #404040; "
            "border-left-color: #404040; border-right-color: #ffffff; "
            "border-bottom-color: #ffffff; color: #000080; "
            "font-family: 'Courier New'; font-size: 10px; "
            "font-weight: 700; padding: 6px 10px;"
        )
        layout.addWidget(badge, 0, Qt.AlignTop)
        self.layout.addWidget(frame)

    # ------------------------------------------------------------------
    # Steam storefront
    # ------------------------------------------------------------------
    def _build_steam_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Steam storefront", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("STEAM WEB API", "Tiny"))
        card.body.addLayout(header)
        card.body.addWidget(
            label(
                "Browse live Specials, top sellers, new releases and upcoming games. "
                "Prices are shown in USD; every row opens the Steam store page.",
                "Muted",
                wrap=True,
            )
        )

        self.steam_segment = SegmentedControl(
            [(key, text) for key, text, _title in STEAM_CATEGORIES]
        )
        self.steam_segment.changed.connect(self._on_steam_category)
        card.body.addWidget(self.steam_segment)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.steam_status = label("Waiting for the storefront…", "Tiny", wrap=True)
        status_row.addWidget(self.steam_status, 1)
        self.steam_refresh = make_button("Refresh", "GhostButton")
        self.steam_refresh.clicked.connect(self.refresh_steam)
        status_row.addWidget(self.steam_refresh, 0)
        card.body.addLayout(status_row)
        card.body.addWidget(hline())

        self.steam_items_host = QWidget()
        self.steam_items = QVBoxLayout(self.steam_items_host)
        self.steam_items.setContentsMargins(0, 0, 0, 0)
        self.steam_items.setSpacing(0)
        card.body.addWidget(self.steam_items_host)
        self._render_steam_message("Press Refresh to load the Steam storefront.")
        return card

    def _on_steam_category(self, key: str) -> None:
        self._steam_category = key
        self.steam_segment.set_current(key)
        if self._steam_payload is None:
            self.refresh_steam()
        else:
            self._render_steam()

    def refresh_steam(self) -> None:
        if self._steam_busy:
            return
        self._steam_busy = True
        self.steam_refresh.setEnabled(False)
        self.steam_status.setText("Contacting the Steam storefront…")
        threading.Thread(
            target=self._steam_worker, name="steam-featured", daemon=True
        ).start()

    def _steam_worker(self) -> None:
        try:
            request = urllib.request.Request(
                STEAM_FEED_URL,
                headers={"User-Agent": "AutoClicker/2.3 Explore"},
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Steam returned an unexpected payload.")
            self.steam_ready.emit(payload)
        except Exception as exc:
            self.steam_failed.emit(str(exc))

    def _on_steam_ready(self, payload) -> None:
        self._steam_busy = False
        self.steam_refresh.setEnabled(True)
        if not isinstance(payload, dict):
            self._render_steam_message("Steam returned no data.")
            return
        self._steam_payload = payload
        self._render_steam()

    def _on_steam_failed(self, message: str) -> None:
        self._steam_busy = False
        self.steam_refresh.setEnabled(True)
        self.steam_status.setText(f"Steam is unreachable — {message}")
        self.main.log("warning", f"Steam storefront fetch failed: {message}")
        self._render_steam_message(
            "The storefront could not be reached. Check your connection and refresh."
        )

    def _clear_steam_rows(self) -> None:
        while self.steam_items.count():
            item = self.steam_items.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_steam_message(self, message: str) -> None:
        self._clear_steam_rows()
        self.steam_items.addWidget(label(message, "Tiny", wrap=True))

    def _render_steam(self) -> None:
        if self._steam_payload is None:
            return
        category = self._steam_category
        block = self._steam_payload.get(category) or {}
        items = block.get("items") if isinstance(block, dict) else None
        if not isinstance(items, list) or not items:
            self._render_steam_message("No items in this category right now.")
            self.steam_status.setText("The storefront returned an empty category.")
            return
        self._clear_steam_rows()
        title = next(
            (name for key, _text, name in STEAM_CATEGORIES if key == category),
            "Steam",
        )
        shown = items[:MAX_ROWS]
        for index, item in enumerate(shown):
            if not isinstance(item, dict) or not item.get("name"):
                continue
            if index:
                self.steam_items.addWidget(hline())
            self.steam_items.addWidget(self._steam_row(item))
        more = len(items) - len(shown)
        suffix = f" · {more} more on Steam" if more > 0 else ""
        self.steam_status.setText(
            f"{title} · {len(shown)} shown{suffix} · prices in USD"
        )

    def _steam_row(self, item: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(10)

        discount = item.get("discount_percent")
        if discount:
            badge = QLabel(f"-{int(discount)}%")
            badge.setStyleSheet(
                "background: #800000; color: #ffffff; font-family: 'Courier New'; "
                "font-size: 10px; font-weight: 700; padding: 2px 5px;"
            )
            badge.setFixedWidth(48)
            badge.setAlignment(Qt.AlignCenter)
            layout.addWidget(badge, 0, Qt.AlignTop)
        else:
            dot = QLabel("▸")
            dot.setStyleSheet(f"color: {COLORS['accent']}; font-size: 12px;")
            dot.setFixedWidth(12)
            layout.addWidget(dot, 0, Qt.AlignTop)

        name = label(str(item.get("name")), "SectionTitle", wrap=True)
        layout.addWidget(name, 1)

        original = _format_price(item.get("original_price"))
        final = _format_price(item.get("final_price"))
        if final:
            if original and original != final:
                price_html = (
                    f"<span style='color:#808080; text-decoration: line-through;'>"
                    f"{original}</span> <b>{final}</b>"
                )
            else:
                price_html = f"<b>{final}</b>"
            price = QLabel(price_html)
            price.setStyleSheet(
                "font-family: 'Courier New'; font-size: 10px; color: #000080;"
            )
            layout.addWidget(price, 0, Qt.AlignVCenter)
        elif item.get("coming_soon"):
            layout.addWidget(label("SOON", "Tiny"), 0, Qt.AlignVCenter)

        open_btn = make_button("OPEN", "GhostButton")
        open_btn.setFixedSize(64, 27)
        app_id = item.get("id")
        if app_id:
            open_btn.clicked.connect(
                lambda checked=False, app_id=app_id: QDesktopServices.openUrl(
                    QUrl(f"https://store.steampowered.com/app/{app_id}")
                )
            )
        else:
            open_btn.setEnabled(False)
        layout.addWidget(open_btn, 0, Qt.AlignVCenter)
        return row

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------
    def _build_connections_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("Connections", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("LOCAL CREDENTIALS", "Tiny"))
        card.body.addLayout(header)
        card.body.addWidget(
            label(
                "Link Discord, Steam and GitHub. AutoClicker keeps these links on this "
                "machine and never asks for a password.",
                "Muted",
                wrap=True,
            )
        )
        card.body.addWidget(hline())

        # Discord --------------------------------------------------------
        discord_row = QHBoxLayout()
        discord_text = QVBoxLayout()
        discord_text.setSpacing(2)
        discord_text.addWidget(label("Discord", "SectionTitle"))
        discord_text.addWidget(
            label("Publish the live engine state through Rich Presence.", "Tiny", wrap=True)
        )
        discord_row.addLayout(discord_text, 1)
        self.discord_dot = PulseDot(COLORS["faint"], 8)
        discord_row.addWidget(self.discord_dot, 0, Qt.AlignVCenter)
        self.discord_toggle = ToggleSwitch(
            bool(self.main.settings.get("discord_presence", False))
        )
        self.discord_toggle.toggled.connect(self._on_presence_toggled)
        discord_row.addWidget(self.discord_toggle, 0, Qt.AlignVCenter)
        card.body.addLayout(discord_row)
        self.discord_status = label("Rich Presence off", "Tiny", wrap=True)
        card.body.addWidget(self.discord_status)
        card.body.addWidget(hline())

        # Steam ----------------------------------------------------------
        card.body.addWidget(label("Steam", "SectionTitle"))
        card.body.addWidget(
            label(
                "Connect a public community profile to see who is linked. "
                "Steam passwords are never requested.",
                "Tiny",
                wrap=True,
            )
        )
        steam_row = QHBoxLayout()
        steam_row.setSpacing(6)
        self.steam_input = QLineEdit()
        self.steam_input.setPlaceholderText("steamcommunity.com/id/yourname or SteamID64")
        self.steam_input.setText(str(self.main.settings.get("steam_profile", "")))
        self.steam_input.returnPressed.connect(self._connect_steam)
        steam_row.addWidget(self.steam_input, 1)
        self.steam_connect_btn = make_button("Connect", "GhostButton")
        self.steam_connect_btn.clicked.connect(self._connect_steam)
        steam_row.addWidget(self.steam_connect_btn, 0)
        card.body.addLayout(steam_row)
        steam_status_row = QHBoxLayout()
        self.steam_connect_status = label("No Steam profile linked.", "Tiny", wrap=True)
        steam_status_row.addWidget(self.steam_connect_status, 1)
        self.steam_open_btn = make_button("Open profile", "GhostButton")
        self.steam_open_btn.setEnabled(False)
        self.steam_open_btn.clicked.connect(self._open_steam_profile)
        steam_status_row.addWidget(self.steam_open_btn, 0)
        card.body.addLayout(steam_status_row)
        card.body.addWidget(hline())

        # GitHub ---------------------------------------------------------
        card.body.addWidget(label("GitHub", "SectionTitle"))
        card.body.addWidget(
            label(
                "The release feed and auto-updater use this public repository.",
                "Tiny",
                wrap=True,
            )
        )
        github_row = QHBoxLayout()
        github_row.setSpacing(6)
        self.github_input = QLineEdit()
        self.github_input.setPlaceholderText("owner/repository")
        self.github_input.setText(
            str(
                self.main.settings.get("github_repo", updater.DEFAULT_REPO)
                or updater.DEFAULT_REPO
            )
        )
        self.github_input.returnPressed.connect(self._connect_github)
        github_row.addWidget(self.github_input, 1)
        self.github_connect_btn = make_button("Link", "GhostButton")
        self.github_connect_btn.clicked.connect(self._connect_github)
        github_row.addWidget(self.github_connect_btn, 0)
        card.body.addLayout(github_row)
        github_status_row = QHBoxLayout()
        self.github_status = label("No repository linked.", "Tiny", wrap=True)
        github_status_row.addWidget(self.github_status, 1)
        self.github_open_btn = make_button("Open repo", "GhostButton")
        self.github_open_btn.setEnabled(False)
        self.github_open_btn.clicked.connect(self._open_github_repo)
        github_status_row.addWidget(self.github_open_btn, 0)
        card.body.addLayout(github_status_row)

        self._refresh_steam_connected()
        return card

    # ------------------------------------------------------------------
    # GitHub releases
    # ------------------------------------------------------------------
    def _build_updates_card(self) -> Card:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(label("GitHub releases", "CardTitle"))
        header.addStretch(1)
        header.addWidget(label("AUTO-UPDATE", "Tiny"))
        card.body.addLayout(header)
        card.body.addWidget(
            label(
                "Check the public releases feed, then download the newest installer "
                "straight into your Downloads folder.",
                "Muted",
                wrap=True,
            )
        )

        version_row = QHBoxLayout()
        version_row.addWidget(label("Installed", "Tiny"))
        version_row.addStretch(1)
        version_row.addWidget(label(f"v{__version__}", "Value"))
        card.body.addLayout(version_row)
        latest_row = QHBoxLayout()
        latest_row.addWidget(label("Latest release", "Tiny"))
        latest_row.addStretch(1)
        self.latest_label = label("Not checked", "Muted")
        latest_row.addWidget(self.latest_label)
        card.body.addLayout(latest_row)
        self.update_status = label("No update check has run yet.", "Tiny", wrap=True)
        card.body.addWidget(self.update_status)
        card.body.addWidget(hline())

        buttons = QHBoxLayout()
        buttons.setSpacing(7)
        self.check_btn = make_button("Check for updates", "GhostButton")
        self.check_btn.clicked.connect(lambda: self.check_updates(silent=False))
        buttons.addWidget(self.check_btn, 1)
        self.download_btn = make_button("Download installer", "PrimaryButton")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._download_installer)
        buttons.addWidget(self.download_btn, 1)
        card.body.addLayout(buttons)

        self.release_btn = make_button("Open release page", "GhostButton")
        self.release_btn.setEnabled(False)
        self.release_btn.clicked.connect(self._open_release_page)
        card.body.addWidget(self.release_btn)
        self.auto_update_toggle = self._toggle_row(
            card.body,
            "Check on startup",
            "Run a quiet release check a few seconds after launch.",
            bool(self.main.settings.get("auto_update", True)),
            lambda checked: self.main.settings.set("auto_update", bool(checked)),
        )
        self.download_status = label("", "Tiny", wrap=True)
        card.body.addWidget(self.download_status)
        self._github_release = None
        return card

    def _toggle_row(self, layout: QVBoxLayout, title: str, description: str, checked: bool, callback) -> ToggleSwitch:
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title, "SectionTitle"))
        text.addWidget(label(description, "Tiny", wrap=True))
        row.addLayout(text, 1)
        toggle = ToggleSwitch(bool(checked))
        toggle.toggled.connect(callback)
        row.addWidget(toggle)
        layout.addLayout(row)
        return toggle

    # ------------------------------------------------------------------
    # Discord presence
    # ------------------------------------------------------------------
    def _on_presence_toggled(self, checked: bool) -> None:
        self.main.set_presence(bool(checked))
        self.discord_status.setText(
            "Starting Rich Presence…" if checked else "Rich Presence off"
        )
        QTimer.singleShot(1200, self.refresh_presence)

    def refresh_presence(self) -> None:
        service = getattr(self.main, "presence", None)
        if service is None:
            self.discord_status.setText("Rich Presence service unavailable.")
            self.discord_dot.set_state(False, COLORS["faint"])
            return
        enabled = service.enabled
        status = service.status_text()
        self.discord_toggle.blockSignals(True)
        self.discord_toggle.setChecked(enabled)
        self.discord_toggle.blockSignals(False)
        connected = service.connected
        self.discord_dot.set_state(
            connected, COLORS["green"] if connected else COLORS["faint"]
        )
        self.discord_status.setText(status)
        color = COLORS["green"] if connected else COLORS["muted"]
        self.discord_status.setStyleSheet(f"font-size: 10px; color: {color};")

    # ------------------------------------------------------------------
    # Steam profile linking
    # ------------------------------------------------------------------
    def _connect_steam(self) -> None:
        value = self.steam_input.text().strip()
        try:
            _extract_steam_target(value)
        except ValueError as exc:
            self.steam_connect_status.setText(str(exc))
            self.steam_connect_status.setStyleSheet(
                f"font-size: 10px; color: {COLORS['red']};"
            )
            return
        self.steam_connect_btn.setEnabled(False)
        self.steam_connect_status.setText("Contacting Steam…")
        threading.Thread(
            target=self._steam_profile_worker,
            args=(value,),
            name="steam-profile",
            daemon=True,
        ).start()

    def _steam_profile_worker(self, value: str) -> None:
        try:
            kind, token = _extract_steam_target(value)
            quoted = urllib.parse.quote(token)
            if kind == "id":
                url = f"https://steamcommunity.com/profiles/{quoted}/?xml=1"
            else:
                url = f"https://steamcommunity.com/id/{quoted}/?xml=1"
            request = urllib.request.Request(
                url, headers={"User-Agent": "AutoClicker/2.3 Explore"}
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                root = ET.fromstring(response.read())
            error = root.findtext("error")
            if error:
                raise ValueError(error.strip())
            steam_id = (root.findtext("steamID64") or "").strip()
            persona = (root.findtext("personaName") or "").strip()
            if not steam_id:
                raise ValueError("Steam did not return a SteamID64 for that profile.")
            avatar = (root.findtext("avatarMedium") or "").strip()
            state = (root.findtext("onlineState") or "").strip()
            self.profile_ready.emit(
                "steam",
                {
                    "input": value,
                    "steam_id": steam_id,
                    "persona": persona or steam_id,
                    "avatar": avatar,
                    "online_state": state,
                    "url": f"https://steamcommunity.com/profiles/{steam_id}",
                },
            )
        except Exception as exc:
            self.profile_failed.emit("steam", str(exc))

    def _refresh_steam_connected(self) -> None:
        persona = str(self.main.settings.get("steam_persona", "") or "")
        steam_id = str(self.main.settings.get("steam_id", "") or "")
        if steam_id:
            text = f"Connected as {persona or steam_id}" if persona else f"SteamID64 {steam_id}"
            self.steam_connect_status.setText(text)
            self.steam_connect_status.setStyleSheet(
                f"font-size: 10px; color: {COLORS['green']};"
            )
            self.steam_open_btn.setEnabled(True)
        else:
            self.steam_connect_status.setText("No Steam profile linked.")
            self.steam_connect_status.setStyleSheet("font-size: 10px; color: #404040;")
            self.steam_open_btn.setEnabled(False)

    def _open_steam_profile(self) -> None:
        steam_id = str(self.main.settings.get("steam_id", "") or "")
        if steam_id:
            QDesktopServices.openUrl(
                QUrl(f"https://steamcommunity.com/profiles/{steam_id}")
            )

    # ------------------------------------------------------------------
    # GitHub linking
    # ------------------------------------------------------------------
    def _connect_github(self) -> None:
        repo = updater.normalize_repo(self.github_input.text())
        self.github_input.setText(repo)
        self.main.settings.set("github_repo", repo)
        self.github_connect_btn.setEnabled(False)
        self.github_status.setText("Contacting GitHub…")
        threading.Thread(
            target=self._github_worker,
            args=(repo,),
            name="github-repo",
            daemon=True,
        ).start()

    def _github_worker(self, repo: str) -> None:
        try:
            self.profile_ready.emit("github", updater.fetch_repo(repo))
        except Exception as exc:
            self.profile_failed.emit("github", str(exc))

    def _open_github_repo(self) -> None:
        repo = updater.normalize_repo(self.github_input.text())
        QDesktopServices.openUrl(QUrl(f"https://github.com/{repo}"))

    # ------------------------------------------------------------------
    # Profile results
    # ------------------------------------------------------------------
    def _on_profile_ready(self, source: str, payload) -> None:
        if source == "steam" and isinstance(payload, dict):
            self.steam_connect_btn.setEnabled(True)
            self.main.settings.set("steam_profile", payload.get("input", ""))
            self.main.settings.set("steam_id", payload.get("steam_id", ""))
            self.main.settings.set("steam_persona", payload.get("persona", ""))
            self._refresh_steam_connected()
            self.main.log(
                "success",
                f"Steam profile linked — {payload.get('persona') or payload.get('steam_id')}.",
            )
            self.main.toast("success", f"Steam linked · {payload.get('persona', '')}")
        elif source == "github" and isinstance(payload, dict):
            self.github_connect_btn.setEnabled(True)
            repo = str(payload.get("repo") or updater.DEFAULT_REPO)
            self.main.settings.set("github_repo", repo)
            self.github_input.setText(repo)
            self.github_status.setText(
                f"Linked {payload.get('full_name', repo)} · ★ {payload.get('stars', 0)}"
            )
            self.github_status.setStyleSheet(
                f"font-size: 10px; color: {COLORS['green']};"
            )
            self.github_open_btn.setEnabled(True)
            self._profile_meta = payload
            self.main.log(
                "success",
                f"GitHub repository linked — {payload.get('full_name', repo)}.",
            )
            self.main.toast("success", f"GitHub linked · {repo}")

    def _on_profile_failed(self, source: str, message: str) -> None:
        if source == "steam":
            self.steam_connect_btn.setEnabled(True)
            self.steam_connect_status.setText(f"Steam link failed — {message}")
            self.steam_connect_status.setStyleSheet(
                f"font-size: 10px; color: {COLORS['red']};"
            )
            self.main.log("warning", f"Steam profile link failed: {message}")
        else:
            self.github_connect_btn.setEnabled(True)
            self.github_status.setText(f"GitHub link failed — {message}")
            self.github_status.setStyleSheet(
                f"font-size: 10px; color: {COLORS['red']};"
            )
            self.main.log("warning", f"GitHub repository link failed: {message}")
        self.main.toast("warning", f"{source.title()} link failed.")

    # ------------------------------------------------------------------
    # Release checks
    # ------------------------------------------------------------------
    def _repo(self) -> str:
        return updater.normalize_repo(
            self.github_input.text()
            or self.main.settings.get("github_repo", updater.DEFAULT_REPO)
        )

    def check_updates(self, silent: bool = False) -> None:
        if self._checking:
            return
        self._checking = True
        self._silent_check = bool(silent)
        self.check_btn.setEnabled(False)
        self.check_btn.setText("Checking…")
        self.update_status.setText("Contacting GitHub releases…")
        threading.Thread(
            target=self._release_worker,
            args=(self._repo(),),
            name="github-release",
            daemon=True,
        ).start()

    def _release_worker(self, repo: str) -> None:
        try:
            self.release_ready.emit(updater.fetch_latest(repo))
        except Exception as exc:
            self.release_failed.emit(str(exc))

    def _on_release_ready(self, release) -> None:
        self._checking = False
        self.check_btn.setEnabled(True)
        self.check_btn.setText("Check for updates")
        if not isinstance(release, dict):
            self._on_release_failed("Unexpected release payload.")
            return
        self._release = release
        self.latest_label.setText(f"v{release.get('version', '0.0.0')}")
        newer = updater.is_newer(release.get("version"), __version__)
        asset = updater.pick_installer(list(release.get("assets") or []))
        self.release_btn.setEnabled(True)
        self.download_btn.setEnabled(bool(newer and asset))
        if newer:
            self.update_status.setText(
                f"Update available — v{release.get('version')} was published on GitHub."
            )
            self.update_status.setStyleSheet(
                f"font-size: 10px; color: {COLORS['accent']}; font-weight: 700;"
            )
            self.main.log(
                "success",
                f"Update available — v{release.get('version')} (installed v{__version__}).",
            )
            self.main.toast("success", f"Update available · v{release.get('version')}")
        else:
            self.update_status.setText(
                "You're up to date with the newest published release."
            )
            self.update_status.setStyleSheet(
                f"font-size: 10px; color: {COLORS['green']};"
            )
            if not self._silent_check:
                self.main.log(
                    "info",
                    f"Release check — v{release.get('version')} is current (installed v{__version__}).",
                )

    def _on_release_failed(self, message: str) -> None:
        self._checking = False
        self.check_btn.setEnabled(True)
        self.check_btn.setText("Check for updates")
        if message == updater.NO_RELEASE_MESSAGE:
            self.latest_label.setText("No release")
            self.update_status.setText(
                "No public release yet — publish one on GitHub to enable updates."
            )
            self.update_status.setStyleSheet(
                f"font-size: 10px; color: {COLORS['muted']};"
            )
            self.main.log("info", "GitHub release check — the repository has no releases yet.")
            return
        self.update_status.setText(f"Release check failed — {message}")
        self.update_status.setStyleSheet(f"font-size: 10px; color: {COLORS['red']};")
        self.main.log("warning", f"GitHub release check failed: {message}")
        if not self._silent_check:
            self.main.toast("warning", "Update check failed — see the status line.")

    def _download_installer(self) -> None:
        if self._release is None or self._downloading:
            return
        self._downloading = True
        self.download_btn.setEnabled(False)
        self.download_btn.setText("Downloading…")
        self.download_status.setText("Starting download…")
        threading.Thread(
            target=self._download_worker,
            args=(self._release,),
            name="github-download",
            daemon=True,
        ).start()

    def _download_worker(self, release: dict) -> None:
        try:
            path = updater.download_installer(
                release,
                progress=lambda done, total: self.download_progress.emit(done, total),
            )
            self.download_ready.emit(str(path), str(release.get("version", "")))
        except Exception as exc:
            self.download_failed.emit(str(exc))

    def _on_download_progress(self, done: int, total: int) -> None:
        if total > 0:
            percent = min(100, int(done * 100 / total))
            self.download_status.setText(
                f"Downloading installer — {percent}% ({done / 1048576:.1f} MB)"
            )
        else:
            self.download_status.setText(f"Downloading installer — {done / 1048576:.1f} MB")

    def _on_download_ready(self, path: str, version: str) -> None:
        self._downloading = False
        self.download_btn.setEnabled(True)
        self.download_btn.setText("Download installer")
        self.download_status.setText(f"Saved {Path(path).name} · {version}")
        self.update_status.setText(f"Installer saved to {Path(path).parent}.")
        self.main.log("success", f"Installer v{version} downloaded to {path}.")
        self.main.toast("success", f"Installer v{version} saved to Downloads")

    def _on_download_failed(self, message: str) -> None:
        self._downloading = False
        self.download_btn.setEnabled(bool(self._release))
        self.download_btn.setText("Download installer")
        self.download_status.setText(f"Download failed — {message}")
        self.main.log("error", f"Installer download failed: {message}")
        self.main.toast("error", "Installer download failed.")

    def _open_release_page(self) -> None:
        if self._release:
            QDesktopServices.openUrl(QUrl(str(self._release.get("html_url"))))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def on_services_started(self) -> None:
        self.refresh_presence()
        if bool(self.main.settings.get("auto_update", True)):
            QTimer.singleShot(2600, lambda: self.check_updates(silent=True))
        QTimer.singleShot(900, self.refresh_steam)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._presence_timer.start()
        self.refresh_presence()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._presence_timer.stop()

    def retranslate(self) -> None:
        # The page body is intentionally English-first; the shell language
        # picker translates navigation and status chrome. This hook keeps the
        # API ready for future full-page catalogs.
        return None
