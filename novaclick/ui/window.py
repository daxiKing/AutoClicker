"""AutoClicker application shell — navigation, hotkeys and automation arbitration."""

from __future__ import annotations

import ctypes
import math
import threading

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__, __version__
from ..core import i18n, wininput
from ..core.engine import HotkeyManager
from ..core.hotkeys import (
    ACTION_INFO,
    ACTION_ORDER,
    DEFAULT_BINDINGS,
    Binding,
    action_title,
    conflict_for,
    load_bindings,
    serialize_bindings,
)
from ..core.paths import DATA_DIR, MACRO_DIR
from ..core.presence import PresenceService
from ..core.settings import SettingsStore
from .activity import ActivityLog
from .pages.autokey_page import AutoKeyPage
from .pages.clicker_page import ClickerPage
from .pages.explore_page import ExplorePage
from .pages.image_page import ImagePage
from .pages.macro_page import MacroPage
from .pages.settings_page import SettingsPage
from .pages.updates_page import UpdatesPage, UPDATES
from .theme import COLORS, FONT_MONO, FONT_UI

LATEST_CODENAME = (UPDATES[0].get("codename") if UPDATES else "") or "Release"
from .widgets import (
    AmbientLine,
    LogoMark,
    MystifyBackdrop,
    PulseDot,
    SoftCard,
    ToastHost,
    label,
    make_button,
    make_nav_icon,
)

# key, sidebar label, icon, breadcrumb label
PAGE_ORDER = [
    ("clicker", "Clicker", "click", "Clicker"),
    ("autokey", "Auto-key", "keys", "Auto-key"),
    ("macro", "Macros", "macro", "Macro studio"),
    ("image", "Image targeting", "image", "Image targeting"),
    ("explore", "Explore", "explore", "Explore"),
    ("updates", "Updates", "logs", "Updates & activity"),
    ("settings", "Settings", "settings", "Settings"),
]

MODE_LABELS = {
    "clicker": "click engine",
    "autokey": "auto-key engine",
    "macro": "macro engine",
    "image": "image targeting",
}

MODE_CHIPS = [
    ("clicker", "CLICK"),
    ("autokey", "KEYS"),
    ("macro", "MACRO"),
    ("image", "VISION"),
]

MODE_TONES = {
    "clicker": ("#000080", "#000000", "#ffffff"),
    "autokey": ("#800080", "#000000", "#ffffff"),
    "macro": ("#004080", "#000000", "#ffffff"),
    "image": ("#008080", "#000000", "#ffffff"),
}

IDLE_CHIP_STYLE = (
    "background: #c0c0c0; border: 2px solid; border-top-color: #ffffff; "
    "border-left-color: #ffffff; border-right-color: #404040; "
    "border-bottom-color: #404040; color: #404040;"
)


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _keycap(text: str) -> QLabel:
    cap = QLabel(text)
    cap.setAlignment(Qt.AlignCenter)
    cap.setFixedHeight(18)
    cap.setMinimumWidth(30)
    cap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    cap.setStyleSheet(
        "background: #ffffff; border: 2px solid; border-top-color: #404040; "
        "border-left-color: #404040; border-right-color: #ffffff; border-bottom-color: #ffffff; "
        "color: #000080; font-family: 'Courier New'; font-size: 8px; font-weight: 700; "
        "padding: 1px 5px;"
    )
    return cap


class ModeChip(QLabel):
    """Tiny top-bar indicator for one automation engine."""

    def __init__(self, key: str, text: str) -> None:
        super().__init__(text)
        self._key = key
        self._active: bool | None = None
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(24)
        self.setMinimumWidth(56)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFont(QFont(FONT_UI, 8, QFont.Bold))
        self.setContentsMargins(7, 0, 7, 0)
        self.setToolTip(f"{text.title()} engine")

    def set_active(self, active: bool) -> None:
        active = bool(active)
        if active == self._active:
            return
        self._active = active
        if active:
            background, border, text = MODE_TONES[self._key]
            self.setStyleSheet(
                f"background: {background}; border: 2px solid {border}; "
                f"color: {text}; padding: 2px 7px; font-weight: 700;"
            )
            self.setToolTip(f"{self.text().title()} engine — running")
        else:
            self.setStyleSheet(IDLE_CHIP_STYLE + " padding: 2px 7px;")
            self.setToolTip(f"{self.text().title()} engine — idle")


class PickHint(QFrame):
    """Frameless top-center HUD shown while the target picker counts down."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput,
        )
        self.setObjectName("PickHint")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(372, 78)
        self.setStyleSheet(
            "QFrame#PickHint { background: #c0c0c0; border: 2px solid; "
            "border-top-color: #ffffff; border-left-color: #ffffff; "
            "border-right-color: #404040; border-bottom-color: #404040; }"
            "QFrame#PickHint QLabel { background: transparent; border: none; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 11, 18, 11)
        layout.setSpacing(12)

        marker = QLabel("◎")
        marker.setAlignment(Qt.AlignCenter)
        marker.setFixedSize(38, 38)
        marker.setStyleSheet(
            "font-size: 21px; color: #000080; background: #ffffff; "
            "border: 2px solid; border-top-color: #404040; border-left-color: #404040; "
            "border-right-color: #ffffff; border-bottom-color: #ffffff;"
        )
        layout.addWidget(marker, 0, Qt.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = QLabel("LOCKING IN 3")
        self.title.setStyleSheet(
            "font-size: 9px; font-weight: 700; color: #000080; "
            "background: transparent; border: none;"
        )
        self.sub = QLabel("Aim at your target · F8 to lock · Esc to cancel")
        self.sub.setStyleSheet(
            "font-size: 10px; color: #000000; background: transparent; border: none;"
        )
        text.addWidget(self.title)
        text.addWidget(self.sub)
        layout.addLayout(text, 1)

        self._countdown = 3
        self._lock_label = "F8"

    def set_lock_label(self, label: str) -> None:
        self._lock_label = label or "F8"

    def update_countdown(self, countdown: int) -> None:
        self._countdown = max(0, int(countdown))
        if self._countdown > 0:
            self.title.setText(f"LOCKING IN {self._countdown}")
            self.sub.setText(
                f"Aim at your target · {self._lock_label} to lock · Esc to cancel"
            )
        else:
            self.title.setText("LOCKING TARGET")
            self.sub.setText("Reading cursor position…")

    def present(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            geometry = screen.availableGeometry()
            self.move(
                geometry.center().x() - self.width() // 2,
                geometry.top() + 52,
            )
        self.show()
        self.raise_()


class MainWindow(QMainWindow):
    position_picked = Signal(int, int)
    position_pick_cancelled = Signal()
    hotkey_fired = Signal(str)
    capture_result = Signal(object)
    toast_requested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.settings = SettingsStore()
        i18n.set_language(str(self.settings.get("language", "en") or "en"))
        self.activity = ActivityLog(self)
        self._bindings = load_bindings(self.settings.get("hotkeys", {}))
        self.hotkeys = HotkeyManager(self._dispatch_hotkey, bindings=self._bindings)
        self.presence = PresenceService(version=__version__)

        self._shutting_down = False
        self._closing = False
        self._services_started = False
        self._ui_ready = False
        self._frame_applied = False
        self._logo_phase = 0.0
        self._current_key = ""
        self._last_page_key = "clicker"
        self._start_maximized = False
        self._active_modes: set[str] = set()
        self._mode_states: dict[str, bool] = {}
        self._status_signature: tuple[str, bool, str] | None = None
        self._pending_toasts: list[tuple[str, str]] = []
        self._nav_anim: QPropertyAnimation | None = None
        self._stack_anim: QPropertyAnimation | None = None
        self._stack_slide_anim: QPropertyAnimation | None = None
        self._stack_effect: QGraphicsOpacityEffect | None = None
        self._stack_overlay: QLabel | None = None
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_group_labels: list[tuple[QLabel, str]] = []
        self._local_label: QLabel | None = None
        self._hotkey_keycaps: dict[str, QLabel] = {}
        self._panic_buttons: list[tuple[QPushButton, str]] = []
        self._page_fade_ready = False

        self._hotkey_suspensions = 0
        self._capture_active = False
        self._pick_guard = threading.Event()
        self._pick_countdown = 3
        self._capture_was_visible = True
        self._capture_was_maximized = False
        self._pick_hint: PickHint | None = None
        self._pick_key_listener = None
        self._pick_delay_timer = QTimer(self)
        self._pick_delay_timer.setSingleShot(True)
        self._pick_delay_timer.timeout.connect(self._begin_pick)
        self._pick_countdown_timer = QTimer(self)
        self._pick_countdown_timer.setInterval(1000)
        self._pick_countdown_timer.timeout.connect(self._pick_countdown_tick)

        self._qsettings = QSettings(str(DATA_DIR / "window.ini"), QSettings.IniFormat)
        self._load_window_state()

        self.setWindowTitle(f"{__app_name__} — {i18n.tr('app.tagline')}")
        self.setMinimumSize(1080, 660)
        if bool(self.settings.get("always_on_top", False)):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        # Connect before constructing pages so startup toasts and errors survive.
        self.hotkey_fired.connect(self._on_hotkey)
        self.capture_result.connect(self._on_capture_result)
        self.toast_requested.connect(self._deliver_toast)

        self._build_pages()
        self._build_shell()
        self._restore_page()
        self._refresh_hotkey_ui()

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(260)
        self._status_timer.timeout.connect(self._update_status)

        self._logo_timer = QTimer(self)
        self._logo_timer.setInterval(70)
        self._logo_timer.timeout.connect(self._pulse_logo)

        self.activity.log(
            "info",
            f"{__app_name__} {__version__} interface constructed — vault at {MACRO_DIR}.",
        )

    # ------------------------------------------------------------------
    # State and pages
    # ------------------------------------------------------------------
    def _load_window_state(self) -> None:
        geometry = self._qsettings.value("window/geometry")
        restored = False
        if geometry is not None:
            try:
                restored = self.restoreGeometry(geometry)
            except Exception:
                restored = False

        if not restored:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                width = min(1440, max(1080, available.width() - 120))
                height = min(920, max(660, available.height() - 100))
                self.resize(width, height)
                self.move(available.center() - self.rect().center())
            else:
                self.resize(1400, 880)

        self._start_maximized = _coerce_bool(
            self._qsettings.value("window/maximized", False)
        )
        saved_page = str(self._qsettings.value("window/last_page", "clicker"))
        self._last_page_key = saved_page if saved_page else "clicker"

    def _save_window_state(self) -> None:
        try:
            self._qsettings.setValue("window/geometry", self.saveGeometry())
            self._qsettings.setValue("window/maximized", self.isMaximized())
            self._qsettings.setValue("window/last_page", self._current_key)
            self._qsettings.sync()
        except Exception:
            pass

    def _build_pages(self) -> None:
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageStack")
        self.stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")

        self.clicker_page = ClickerPage(self)
        self.autokey_page = AutoKeyPage(self)
        self.macro_page = MacroPage(self)
        self.image_page = ImagePage(self)
        self.explore_page = ExplorePage(self)
        self.updates_page = UpdatesPage(self, self.activity)
        self.settings_page = SettingsPage(self)

        self.pages = {
            "clicker": self.clicker_page,
            "autokey": self.autokey_page,
            "macro": self.macro_page,
            "image": self.image_page,
            "explore": self.explore_page,
            "updates": self.updates_page,
            "settings": self.settings_page,
        }
        for key, _nav, _icon, _crumb in PAGE_ORDER:
            self.stack.addWidget(self.pages[key])

    def _build_shell(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        root.setAttribute(Qt.WA_StyledBackground, True)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_topbar())
        self._ambient_line = AmbientLine()
        content_layout.addWidget(self._ambient_line)
        content_layout.addWidget(self.stack, 1)
        root_layout.addWidget(self.content, 1)

        self.setCentralWidget(root)

        self._backdrop = MystifyBackdrop(self.content)
        self._layout_backdrop()
        self._backdrop.lower()

        self.toast_host = ToastHost(self.content)
        self.toast_host.setGeometry(self.content.rect())
        self.toast_host.raise_()

        self._update_status(force=True)

    def _layout_backdrop(self) -> None:
        if not hasattr(self, "_backdrop") or not hasattr(self, "content"):
            return
        top = 62
        self._backdrop.setGeometry(
            0,
            top,
            max(0, self.content.width()),
            max(0, self.content.height() - top),
        )

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(238)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 12)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 0, 0, 0)
        header_layout.setSpacing(11)
        self._logo = LogoMark(40)
        self._logo.set_glow(0.45)
        header_layout.addWidget(self._logo, 0, Qt.AlignVCenter)

        brand = QVBoxLayout()
        brand.setSpacing(1)
        title = QLabel(__app_name__)
        title.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #000080; background: transparent;"
        )
        brand.addWidget(title)
        subtitle = QLabel(f"v{__version__}  ·  {LATEST_CODENAME.upper()}")
        subtitle.setStyleSheet(
            "font-family: 'Courier New'; font-size: 8px; color: #404040; "
            "background: transparent;"
        )
        brand.addWidget(subtitle)
        header_layout.addLayout(brand, 1)
        layout.addWidget(header)
        layout.addSpacing(14)

        divider = QFrame()
        divider.setObjectName("SidebarDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addSpacing(8)

        nav = QWidget()
        self._nav_container = nav
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(2)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        self._add_nav_group(nav_layout, "group.automation")
        for key, nav_label, icon, _crumb in PAGE_ORDER[:4]:
            self._add_nav_button(nav_layout, key, nav_label, icon)
        nav_layout.addSpacing(10)
        self._add_nav_group(nav_layout, "group.system")
        for key, nav_label, icon, _crumb in PAGE_ORDER[4:]:
            self._add_nav_button(nav_layout, key, nav_label, icon)

        layout.addWidget(nav)

        self._nav_indicator = QWidget(nav)
        self._nav_indicator.setObjectName("NavIndicator")
        self._nav_indicator.setStyleSheet("background: #ffff00; border: 1px solid #000000;")
        self._nav_indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._nav_indicator.hide()
        self._nav_indicator.raise_()

        layout.addStretch(1)
        layout.addWidget(self._build_hotkey_card())
        layout.addSpacing(8)

        panic_btn = make_button("PANIC STOP  ·  F10", "DangerButton")
        panic_btn.setFixedHeight(35)
        panic_btn.setToolTip("Instantly stop every engine and release held input")
        panic_btn.clicked.connect(self.panic)
        self._panic_buttons.append((panic_btn, "PANIC STOP  ·  "))
        layout.addWidget(panic_btn)
        layout.addSpacing(9)

        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        version = QLabel(f"v{__version__}  ·  {LATEST_CODENAME.upper()}")
        version.setStyleSheet(
            "font-family: 'Courier New'; font-size: 8px; color: #404040;"
        )
        local = QLabel(i18n.tr("shell.local_only"))
        local.setStyleSheet(
            "font-family: 'Courier New'; font-size: 8px; color: #808080;"
        )
        self._local_label = local
        footer.addWidget(version)
        footer.addStretch(1)
        footer.addWidget(local)
        layout.addLayout(footer)

        QTimer.singleShot(0, self._sync_nav_indicator)
        return sidebar

    def _add_nav_group(self, layout: QVBoxLayout, key: str) -> None:
        group = QLabel(i18n.tr(key))
        group.setContentsMargins(10, 5, 0, 3)
        group.setStyleSheet(
            "font-size: 8px; font-weight: 700; color: #404040; "
            "background: transparent; letter-spacing: 1px;"
        )
        layout.addWidget(group)
        self._nav_group_labels.append((group, key))

    def _add_nav_button(
        self, layout: QVBoxLayout, key: str, text: str, icon: str
    ) -> None:
        text = i18n.tr(f"nav.{key}")
        button = QPushButton(text)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setFixedHeight(38)
        button.setCursor(Qt.PointingHandCursor)
        button.setIcon(make_nav_icon(icon))
        button.setIconSize(QSize(17, 17))
        button.setToolTip(f"Open {text}")
        button.clicked.connect(lambda checked=False, key=key: self._navigate(key))
        self._nav_group.addButton(button)
        self._nav_buttons[key] = button
        layout.addWidget(button)

    def _build_hotkey_card(self) -> SoftCard:
        card = SoftCard()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.body.setContentsMargins(12, 10, 12, 10)
        card.body.setSpacing(3)
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addWidget(label("GLOBAL HOTKEYS", "Eyebrow"))
        header.addStretch(1)
        dot = PulseDot(COLORS["accent"], 6)
        dot.setFixedSize(12, 12)
        dot.set_state(True, COLORS["accent"])
        header.addWidget(dot)
        card.body.addLayout(header)
        card.body.addSpacing(2)

        for action in ACTION_ORDER:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(0, 0, 0, 0)
            cap = _keycap(self.hotkey_label(action))
            self._hotkey_keycaps[action] = cap
            row.addWidget(cap)
            text = label(ACTION_INFO[action][0], "Tiny")
            text.setStyleSheet(
                "font-size: 10px; color: #800000;"
                if action == "panic"
                else "font-size: 10px; color: #404040;"
            )
            row.addWidget(text)
            row.addStretch(1)
            card.body.addLayout(row)
        return card

    # ------------------------------------------------------------------
    # Top bar
    # ------------------------------------------------------------------
    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(60)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 22, 0)
        layout.setSpacing(10)

        self._status_dot = PulseDot(COLORS["faint"], 7)
        layout.addWidget(self._status_dot, 0, Qt.AlignVCenter)

        self._status_text = QLabel(i18n.tr("status.ready"))
        self._status_text.setFixedWidth(154)
        self._status_text.setStyleSheet(
            "font-size: 9px; font-weight: 700; color: #404040;"
        )
        layout.addWidget(self._status_text, 0, Qt.AlignVCenter)

        divider = QFrame()
        divider.setFixedSize(1, 16)
        divider.setStyleSheet("background: #808080;")
        layout.addWidget(divider, 0, Qt.AlignVCenter)

        self._crumb = QLabel("WORKSPACE  /  CLICKER")
        self._crumb.setStyleSheet(
            "font-family: 'Courier New'; font-size: 8px; color: #404040;"
        )
        layout.addWidget(self._crumb, 0, Qt.AlignVCenter)
        layout.addStretch(1)

        self._mode_chips: dict[str, ModeChip] = {}
        for key, text in MODE_CHIPS:
            chip = ModeChip(key, text)
            self._mode_chips[key] = chip
            layout.addWidget(chip, 0, Qt.AlignVCenter)

        layout.addSpacing(4)
        self._top_toggle = QPushButton(i18n.tr("shell.on_top"))
        self._top_toggle.setObjectName("Chip")
        self._top_toggle.setCheckable(True)
        self._top_toggle.setCursor(Qt.PointingHandCursor)
        self._top_toggle.setFixedHeight(28)
        self._top_toggle.setToolTip("Keep AutoClicker above other windows")
        self._top_toggle.setChecked(bool(self.settings.get("always_on_top", False)))
        self._top_toggle.clicked.connect(
            lambda checked: self.set_always_on_top(bool(checked))
        )
        layout.addWidget(self._top_toggle, 0, Qt.AlignVCenter)

        panic_btn = make_button("PANIC  ·  F10", "DangerButton")
        panic_btn.setFixedHeight(29)
        panic_btn.setToolTip("Stop every engine now (F10)")
        panic_btn.clicked.connect(self.panic)
        self._panic_buttons.append((panic_btn, "PANIC  ·  "))
        layout.addWidget(panic_btn, 0, Qt.AlignVCenter)
        return bar

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _restore_page(self) -> None:
        key = self._last_page_key if self._last_page_key in self.pages else "clicker"
        self._navigate(key, animate=False)
        self._page_fade_ready = True

    def _navigate(self, key: str, animate: bool = True) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        changed = key != self._current_key
        transitioning = bool(animate and changed and self.isVisible())
        if transitioning:
            self._capture_stack_snapshot()
        self._current_key = key
        self.stack.setCurrentWidget(page)
        button = self._nav_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self._update_crumb(key)
        if key == "settings" and hasattr(page, "_refresh"):
            page._refresh()
        if transitioning:
            self._animate_stack()
        self._move_nav_indicator(animate and changed)

    def _update_crumb(self, key: str) -> None:
        title = i18n.tr(f"nav.{key}") if key else "Clicker"
        self._crumb.setText(
            f"{i18n.tr('shell.workspace')}  /  {title.upper()}"
        )

    def _move_nav_indicator(self, animate: bool) -> None:
        button = self._nav_buttons.get(self._current_key)
        if button is None or not hasattr(self, "_nav_indicator"):
            return
        if button.height() <= 2:
            QTimer.singleShot(0, self._sync_nav_indicator)
            return

        top = button.mapTo(self._nav_container, QPoint(0, 0)).y()
        target_y = top + 8
        target_height = max(10, button.height() - 16)
        target = QRect(0, target_y, 3, target_height)
        self._nav_indicator.show()
        self._nav_indicator.raise_()

        if animate and self._nav_indicator.width() > 0:
            if self._nav_anim is not None:
                self._nav_anim.stop()
            anim = QPropertyAnimation(self._nav_indicator, b"geometry", self)
            anim.setDuration(200)
            anim.setStartValue(self._nav_indicator.geometry())
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._nav_anim = anim
        else:
            self._nav_indicator.setGeometry(target)

    def _sync_nav_indicator(self) -> None:
        self._move_nav_indicator(False)

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------
    def set_language(self, code: str, announce: bool = True) -> str:
        """Switch the shell language and persist the choice."""
        code = i18n.set_language(code)
        self.settings.set("language", code)
        self._apply_language()
        if announce:
            name = i18n.language_name(code)
            self.activity.log("success", f"Language set to {name} ({code}).")
            self.toast("success", f"Language · {name}")
        return code

    def _apply_language(self) -> None:
        for key, button in self._nav_buttons.items():
            text = i18n.tr(f"nav.{key}")
            button.setText(text)
            button.setToolTip(f"Open {text}")
        for group, key in self._nav_group_labels:
            group.setText(i18n.tr(key))
        if self._local_label is not None:
            self._local_label.setText(i18n.tr("shell.local_only"))
        if hasattr(self, "_top_toggle"):
            self._top_toggle.setText(i18n.tr("shell.on_top"))
        self.setWindowTitle(f"{__app_name__} — {i18n.tr('app.tagline')}")
        self._update_crumb(self._current_key or "clicker")
        self._update_status(force=True)
        for page in getattr(self, "pages", {}).values():
            retranslate = getattr(page, "retranslate", None)
            if callable(retranslate):
                try:
                    retranslate()
                except Exception:
                    pass
        QTimer.singleShot(0, self._sync_nav_indicator)

    # ------------------------------------------------------------------
    # Discord Rich Presence
    # ------------------------------------------------------------------
    def set_presence(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.settings.set("discord_presence", enabled)
        if enabled:
            self.presence.start()
            self.activity.log(
                "success",
                "Discord Rich Presence enabled — waiting for the desktop app.",
            )
            self.toast("info", "Rich Presence enabled.")
        else:
            self.presence.stop()
            self.activity.log("info", "Discord Rich Presence disabled.")
            self.toast("info", "Rich Presence disabled.")
        page = getattr(self, "explore_page", None)
        if page is not None and hasattr(page, "refresh_presence"):
            try:
                page.refresh_presence()
            except Exception:
                pass

    def _capture_stack_snapshot(self) -> None:
        self._dispose_stack_fade()
        try:
            pixmap = self.stack.grab()
        except Exception:
            self._stack_overlay = None
            return
        overlay = QLabel(self.stack)
        overlay.setPixmap(pixmap)
        overlay.setGeometry(self.stack.rect())
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        overlay.setStyleSheet("background: transparent;")
        overlay.show()
        overlay.raise_()
        self._stack_overlay = overlay

    def _animate_stack(self) -> None:
        overlay = self._stack_overlay
        if overlay is None:
            return
        effect = QGraphicsOpacityEffect(overlay)
        effect.setOpacity(0.96)
        overlay.setGraphicsEffect(effect)

        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(250)
        fade.setStartValue(0.96)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.finished.connect(lambda: self._finish_stack_fade(effect))

        slide = QPropertyAnimation(overlay, b"pos", self)
        slide.setDuration(300)
        slide.setStartValue(overlay.pos())
        slide.setEndValue(overlay.pos() - QPoint(20, 0))
        slide.setEasingCurve(QEasingCurve.OutCubic)

        self._stack_effect = effect
        self._stack_anim = fade
        self._stack_slide_anim = slide
        fade.start()
        slide.start()

    def _finish_stack_fade(self, effect: QGraphicsOpacityEffect) -> None:
        if self._stack_effect is not effect:
            return
        overlay = self._stack_overlay
        self._stack_overlay = None
        self._stack_effect = None
        self._stack_anim = None
        self._stack_slide_anim = None
        if overlay is not None:
            overlay.deleteLater()

    def _dispose_stack_fade(self) -> None:
        anim, slide = self._stack_anim, self._stack_slide_anim
        effect, overlay = self._stack_effect, self._stack_overlay
        self._stack_anim = None
        self._stack_slide_anim = None
        self._stack_effect = None
        self._stack_overlay = None
        for animation in (anim, slide):
            if animation is not None:
                animation.stop()
        if overlay is not None:
            overlay.deleteLater()
        if effect is not None and self.stack.graphicsEffect() is effect:
            self.stack.setGraphicsEffect(None)
            effect.deleteLater()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def show_initial(self) -> None:
        if self._start_maximized:
            self.showMaximized()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def start_services(self) -> None:
        if self._services_started or self._shutting_down:
            return
        self._services_started = True
        self._ui_ready = True

        if bool(self.settings.get("game_mode", False)):
            self.set_game_mode(True, announce=False)

        if self.hotkeys.start():
            summary = "  ·  ".join(
                f"{action_title(action)} {self.hotkey_label(action)}"
                for action in ACTION_ORDER
            )
            self.activity.log("success", f"Global hotkeys online — {summary}.")
        else:
            message = self.hotkeys.error or "unknown listener error"
            self.activity.log("error", f"Global hotkeys unavailable — {message}.")
            self.toast("error", "Global hotkeys unavailable — use the on-screen controls.")
        self._status_timer.start()
        self._logo_timer.start()
        self._update_status(force=True)
        if bool(self.settings.get("discord_presence", False)):
            self.presence.start()
            self.activity.log(
                "info", "Discord Rich Presence requested — connecting to the desktop app."
            )
        if hasattr(self, "explore_page"):
            self.explore_page.on_services_started()
        self.activity.log(
            "success", f"{__app_name__} {__version__} online — native input ready."
        )
        QTimer.singleShot(420, self._flush_toasts)
        QTimer.singleShot(600, self._sync_nav_indicator)

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._status_timer.stop()
        self._logo_timer.stop()
        self._abort_capture(restore=False)
        self._stop_all_automations()
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            self.presence.stop()
        except Exception:
            pass
        try:
            wininput.release_all()
        except Exception:
            pass
        self.activity.log("info", "AutoClicker offline — all engines released.")
        self._save_window_state()

    def closeEvent(self, event) -> None:
        if self._closing:
            event.accept()
            return
        self._closing = True
        self.shutdown()
        event.accept()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "toast_host"):
            self.toast_host.setGeometry(self.content.rect())
            self.toast_host.raise_()
        if not self._frame_applied:
            self._frame_applied = True
            self._apply_window_frame()
        QTimer.singleShot(0, self._sync_nav_indicator)
        self._layout_backdrop()
        self._set_cinematics_running(not any(self._engine_states().values()))
        if self._services_started:
            QTimer.singleShot(350, self._flush_toasts)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast_host") and hasattr(self, "content"):
            self.toast_host.setGeometry(self.content.rect())
            self.toast_host.relayout()
        self._layout_backdrop()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._set_cinematics_running(False)

    def _set_cinematics_running(self, running: bool) -> None:
        running = bool(running)
        backdrop = getattr(self, "_backdrop", None)
        if backdrop is not None:
            backdrop.set_running(running)
        line = getattr(self, "_ambient_line", None)
        if line is not None:
            line.set_running(running)

    # ------------------------------------------------------------------
    # Windows chrome
    # ------------------------------------------------------------------
    def _apply_window_frame(self) -> None:
        """Ask Windows for a square, navy-captioned window that matches the UI."""
        try:
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi
            dark = ctypes.c_int(0)
            result = dwm.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)
            )
            if result:
                dwm.DwmSetWindowAttribute(
                    hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark)
                )

            def colorref(hex_color: str) -> int:
                color = QColor(hex_color)
                return color.red() | (color.green() << 8) | (color.blue() << 16)

            for attribute, value in (
                (35, colorref(COLORS["accent"])),
                (36, colorref("#ffffff")),
                (34, colorref(COLORS["card"])),
            ):
                data = ctypes.c_int(value)
                try:
                    dwm.DwmSetWindowAttribute(
                        hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data)
                    )
                except Exception:
                    pass
            corner = ctypes.c_int(1)
            try:
                dwm.DwmSetWindowAttribute(
                    hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner)
                )
            except Exception:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Automation arbitration
    # ------------------------------------------------------------------
    def acquire(self, mode: str) -> None:
        if self._shutting_down:
            return
        stopped: list[str] = []
        try:
            if mode in ("macro", "image"):
                if self.clicker_page.force_stop():
                    stopped.append("click engine")
                if self.autokey_page.force_stop():
                    stopped.append("auto-key engine")
                other = self.image_page if mode == "macro" else self.macro_page
                if other.force_stop():
                    stopped.append("image targeting" if mode == "macro" else "macro engine")
            else:
                if self.macro_page.force_stop():
                    stopped.append("macro engine")
                if self.image_page.force_stop():
                    stopped.append("image targeting")
            if stopped:
                wininput.release_all()
                self.activity.log(
                    "info",
                    f"Input arbitration — stopped {', '.join(stopped)} before {MODE_LABELS[mode]}.",
                )
        except Exception as exc:
            self.activity.log("error", f"Automation arbitration fault: {exc}")
        self._active_modes.add(mode)
        self._update_status(force=True)

    def release(self, mode: str) -> None:
        self._active_modes.discard(mode)
        self._update_status(force=True)

    def _stop_all_automations(self) -> list[str]:
        stopped: list[str] = []
        for page, name in (
            (self.macro_page, "macro"),
            (self.image_page, "image targeting"),
            (self.clicker_page, "click engine"),
            (self.autokey_page, "auto-key engine"),
        ):
            try:
                if page.force_stop():
                    stopped.append(name)
            except Exception:
                pass
        self._active_modes.clear()
        return stopped

    def panic(self) -> None:
        if self._shutting_down:
            return
        if self._capture_active:
            self._finish_capture(None, restore=True)
        stopped = self._stop_all_automations()
        try:
            wininput.release_all()
        except Exception:
            pass
        if stopped:
            detail = ", ".join(stopped)
            self.activity.log("warning", f"PANIC STOP — halted {detail}; input released.")
            self.toast("warning", f"Panic stop — halted {detail}.")
        else:
            self.activity.log("warning", "PANIC STOP — all engines already idle.")
            self.toast("info", "Panic stop — all engines already idle.")
        self._flash_alert()
        self._update_status(force=True)

    def _flash_alert(self) -> None:
        if not hasattr(self, "content"):
            return
        flash = QFrame(self.content)
        flash.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        flash.setStyleSheet(
            "background: #ffc0c0; border: 2px solid #800000;"
        )
        flash.setGeometry(self.content.rect())
        effect = QGraphicsOpacityEffect(flash)
        effect.setOpacity(0.9)
        flash.setGraphicsEffect(effect)
        flash.show()
        flash.raise_()
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(480)
        anim.setStartValue(0.9)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(flash.deleteLater)
        anim.start()
        self._flash_anim = anim
        if hasattr(self, "toast_host"):
            self.toast_host.raise_()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def _engine_states(self) -> dict[str, bool]:
        armed = bool(getattr(self.macro_page, "_armed", False))
        recording = bool(self.macro_page.recorder.is_active)
        playing = bool(self.macro_page.player.is_active)
        return {
            "clicker": bool(self.clicker_page.engine.is_active),
            "autokey": bool(self.autokey_page.engine.is_active),
            "macro": armed or recording or playing,
            "image": bool(self.image_page.engine.is_active),
        }

    def _update_status(self, force: bool = False) -> None:
        if not hasattr(self, "_mode_chips"):
            return
        states = self._engine_states()
        for key, active in states.items():
            chip = self._mode_chips.get(key)
            if chip is not None:
                chip.set_active(active)
        self._mode_states = states

        armed = bool(getattr(self.macro_page, "_armed", False))
        recording = bool(self.macro_page.recorder.is_active)
        playing = bool(self.macro_page.player.is_active)

        if playing:
            text, tone, active = i18n.tr("status.playing"), "violet", True
        elif recording:
            text, tone, active = i18n.tr("status.recording"), "violet", True
        elif armed:
            text, tone, active = i18n.tr("status.armed"), "violet", True
        elif states["image"]:
            text, tone, active = i18n.tr("status.vision"), "cyan", True
        elif states["clicker"] and states["autokey"]:
            text, tone, active = i18n.tr("status.dual"), "accent", True
        elif states["clicker"]:
            text, tone, active = i18n.tr("status.clicking"), "accent", True
        elif states["autokey"]:
            text, tone, active = i18n.tr("status.autokey"), "accent", True
        else:
            text, tone, active = i18n.tr("status.ready"), "muted", False

        signature = (text, active, tone)
        if force or signature != self._status_signature:
            self._status_signature = signature
            color = {
                "accent": COLORS["accent"],
                "violet": COLORS["accent_2"],
                "cyan": COLORS["cyan"],
                "muted": COLORS["faint"],
            }.get(tone, COLORS["faint"])
            self._status_text.setText(text)
            self._status_text.setStyleSheet(
                f"font-size: 9px; font-weight: 700; color: {color};"
            )

            self._status_dot.set_state(active, color)

        try:
            self.presence.set_state(text, active)
        except Exception:
            pass

        # Keep the tracked set in sync even if a page stopped itself.
        tracked = {key for key, value in states.items() if value}
        self._active_modes = tracked
        self._set_cinematics_running(not tracked)

    def _pulse_logo(self) -> None:
        self._logo_phase = (self._logo_phase + 0.09) % math.tau
        self._logo.set_glow(0.45 + 0.32 * math.sin(self._logo_phase))

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------
    def _dispatch_hotkey(self, action: str) -> None:
        self.hotkey_fired.emit(str(action))

    def _on_hotkey(self, action: str) -> None:
        if self._shutting_down or self._capture_active:
            return
        if self._hotkey_suspensions > 0:
            return
        if action != "panic":
            if QApplication.activeModalWidget() is not None:
                return
            if QApplication.activePopupWidget() is not None:
                return
        try:
            if action == "clicker":
                self.clicker_page.toggle()
            elif action == "autokey":
                self.autokey_page.toggle()
            elif action == "record":
                self.macro_page.toggle_record()
            elif action == "play":
                self.macro_page.toggle_play()
            elif action == "panic":
                self.panic()
            self._update_status(force=True)
        except Exception as exc:
            self.activity.log("error", f"Hotkey action '{action}' failed: {exc}")

    def suspend_hotkeys(self, suspended: bool) -> None:
        if suspended:
            self._hotkey_suspensions += 1
        else:
            self._hotkey_suspensions = max(0, self._hotkey_suspensions - 1)
        try:
            self.hotkeys.set_suspended(
                self._hotkey_suspensions > 0 or self._capture_active
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Customizable hotkeys
    # ------------------------------------------------------------------
    def hotkey_bindings(self) -> dict[str, Binding]:
        return self.hotkeys.bindings

    def hotkey_label(self, action: str) -> str:
        binding = self.hotkeys.bindings.get(action)
        return binding.label() if binding is not None else "Unbound"

    def set_hotkey(self, action: str, binding) -> tuple[bool, str]:
        if action not in ACTION_INFO:
            return False, "Unknown hotkey action."
        candidate = (
            binding if isinstance(binding, Binding) else Binding.from_payload(binding)
        )
        if candidate is None:
            return False, "That key cannot be used as a global hotkey."
        other = conflict_for(self.hotkeys.bindings, action, candidate)
        if other is not None:
            return False, f"{candidate.label()} is already bound to {action_title(other)}."
        bindings = self.hotkeys.bindings
        bindings[action] = candidate
        self._bindings = bindings
        self.hotkeys.set_bindings(bindings)
        self.settings.set("hotkeys", serialize_bindings(bindings))
        self._refresh_hotkey_ui()
        self.activity.log(
            "success", f"{action_title(action)} hotkey set to {candidate.label()}."
        )
        self.toast("success", f"{action_title(action)} hotkey · {candidate.label()}")
        return True, ""

    def reset_hotkeys(self) -> None:
        bindings = dict(DEFAULT_BINDINGS)
        self._bindings = bindings
        self.hotkeys.set_bindings(bindings)
        self.settings.set("hotkeys", serialize_bindings(bindings))
        self._refresh_hotkey_ui()
        self.activity.log("success", "Global hotkeys restored to defaults.")
        self.toast("success", "Hotkeys restored to factory defaults.")

    def unbind_hotkey(self, action: str) -> tuple[bool, str]:
        """Clear an action's global hotkey (Esc during capture)."""
        if action not in ACTION_INFO:
            return False, "Unknown hotkey action."
        bindings = self.hotkeys.bindings
        bindings[action] = Binding(0)
        self._bindings = bindings
        self.hotkeys.set_bindings(bindings)
        self.settings.set("hotkeys", serialize_bindings(bindings))
        self._refresh_hotkey_ui()
        self.activity.log("info", f"{action_title(action)} hotkey unbound.")
        if action == "panic":
            self.toast(
                "warning",
                "Panic hotkey unbound — use the window buttons to stop engines.",
            )
        else:
            self.toast("info", f"{action_title(action)} hotkey unbound")
        return True, ""

    def _refresh_hotkey_ui(self) -> None:
        bindings = self.hotkeys.bindings
        for action, cap in self._hotkey_keycaps.items():
            binding = bindings.get(action)
            if binding is not None:
                cap.setText(binding.label())
        panic = bindings.get("panic")
        if panic is not None:
            for button, prefix in self._panic_buttons:
                button.setText(f"{prefix}{panic.label()}")
                button.setToolTip(f"Stop every engine now ({panic.label()})")
        record = bindings.get("record")
        if self._pick_hint is not None:
            self._pick_hint.set_lock_label(record.key_name if record else "F8")
            self._pick_hint.update_countdown(self._pick_countdown)
        for page in getattr(self, "pages", {}).values():
            refresh = getattr(page, "refresh_hotkeys", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception as exc:
                    self.activity.log("warning", f"Hotkey label refresh failed: {exc}")

    # ------------------------------------------------------------------
    # Position picker
    # ------------------------------------------------------------------
    def capture_position(self, delay_s: float = 3.0) -> None:
        if self._capture_active or self._shutting_down:
            return
        self._capture_active = True
        self._pick_guard.clear()
        self._pick_countdown = max(1, min(10, int(math.ceil(float(delay_s)))))
        self._capture_was_visible = self.isVisible()
        self._capture_was_maximized = self.isMaximized()
        self.suspend_hotkeys(True)
        self._start_pick_keyboard()
        # Let the page toast breathe for a moment, then hide and show the HUD.
        self._pick_delay_timer.start(350)

    def _start_pick_keyboard(self) -> bool:
        try:
            from pynput import keyboard

            listener = keyboard.Listener(on_press=self._pick_on_key)
            listener.daemon = True
            listener.start()
            self._pick_key_listener = listener
            return True
        except Exception as exc:
            self._pick_key_listener = None
            self.activity.log("warning", f"Picker keyboard hook unavailable: {exc}")
            return False

    def _pick_on_key(self, key) -> None:
        from ..core.keys import pynput_key_to_vk

        try:
            from pynput import keyboard
        except Exception:
            return
        if key == keyboard.Key.esc:
            if self._pick_guard.is_set():
                return
            self._pick_guard.set()
            self.capture_result.emit(None)
            return
        record = self.hotkeys.bindings.get("record")
        lock_vk = record.vk if record is not None else 0x77
        if pynput_key_to_vk(key) == lock_vk:
            if self._pick_guard.is_set():
                return
            self._pick_guard.set()
            try:
                position = wininput.cursor_position()
            except Exception:
                position = None
            self.capture_result.emit(position)

    def _begin_pick(self) -> None:
        if not self._capture_active:
            return
        if self._pick_hint is None:
            self._pick_hint = PickHint()
        record = self.hotkeys.bindings.get("record")
        self._pick_hint.set_lock_label(record.key_name if record is not None else "F8")
        self._pick_hint.update_countdown(self._pick_countdown)
        self._pick_hint.present()
        self.hide()
        self._pick_countdown_timer.start()

    def _pick_countdown_tick(self) -> None:
        if not self._capture_active:
            self._pick_countdown_timer.stop()
            return
        self._pick_countdown -= 1
        if self._pick_countdown <= 0:
            self._pick_countdown_timer.stop()
            if self._pick_hint is not None:
                self._pick_hint.update_countdown(0)
            if self._pick_guard.is_set():
                return
            self._pick_guard.set()
            try:
                position = wininput.cursor_position()
            except Exception:
                position = None
            self.capture_result.emit(position)
        elif self._pick_hint is not None:
            self._pick_hint.update_countdown(self._pick_countdown)

    def _on_capture_result(self, result) -> None:
        if not self._capture_active:
            return
        self._finish_capture(result, restore=True)

    def _finish_capture(self, result, restore: bool) -> None:
        self._capture_active = False
        self._pick_guard.set()
        self._pick_delay_timer.stop()
        self._pick_countdown_timer.stop()
        listener = self._pick_key_listener
        self._pick_key_listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        if self._pick_hint is not None:
            self._pick_hint.hide()
        self.suspend_hotkeys(False)
        if restore and not self._shutting_down and self._capture_was_visible:
            if self._capture_was_maximized:
                self.showMaximized()
            else:
                self.show()
            self.raise_()
            self.activateWindow()
        if self._shutting_down:
            return
        if isinstance(result, tuple) and len(result) == 2:
            try:
                x, y = int(result[0]), int(result[1])
            except (TypeError, ValueError):
                self.position_pick_cancelled.emit()
                return
            self.position_picked.emit(x, y)
        else:
            self.position_pick_cancelled.emit()

    def _abort_capture(self, restore: bool = False) -> None:
        if not self._capture_active and self._pick_key_listener is None:
            return
        self._capture_active = False
        self._pick_guard.set()
        self._pick_delay_timer.stop()
        self._pick_countdown_timer.stop()
        listener = self._pick_key_listener
        self._pick_key_listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        if self._pick_hint is not None:
            self._pick_hint.hide()
        if not self._shutting_down:
            self.suspend_hotkeys(False)
        if restore and not self._shutting_down:
            if self._capture_was_maximized:
                self.showMaximized()
            else:
                self.show()

    # ------------------------------------------------------------------
    # Preferences and toasts
    # ------------------------------------------------------------------
    def start_delay_s(self) -> float:
        try:
            return max(0.0, min(10.0, float(self.settings.get("start_delay_ms", 0)) / 1000.0))
        except (TypeError, ValueError):
            return 0.0

    def set_game_mode(self, enabled: bool, announce: bool = True) -> None:
        """Enable scan-code input and high process priority for game clients.

        This is ordinary Windows input, not an anti-cheat bypass: it only makes
        synthetic keystrokes look like hardware scan codes and gives the input
        threads scheduling headroom while a game is focused.
        """
        enabled = bool(enabled)
        self.settings.set("game_mode", enabled)
        wininput.set_scan_code_mode(enabled)
        wininput.set_high_priority(enabled)
        page = getattr(self, "settings_page", None)
        if page is not None and hasattr(page, "sync_game_mode"):
            try:
                page.sync_game_mode(enabled)
            except Exception:
                pass
        if announce:
            state = "enabled" if enabled else "disabled"
            self.activity.log(
                "success" if enabled else "info",
                f"Game input mode {state} — scan-code keys "
                f"{'on' if enabled else 'off'}, high priority "
                f"{'on' if enabled else 'off'}.",
            )
            self.toast(
                "success" if enabled else "info",
                f"Game input mode {state}.",
            )

    def set_always_on_top(self, enabled: bool) -> None:
        enabled = bool(enabled)
        current = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        if enabled != current:
            was_visible = self.isVisible()
            was_maximized = self.isMaximized()
            self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
            if was_visible:
                if was_maximized:
                    self.showMaximized()
                else:
                    self.show()
                self.raise_()
            self.activity.log(
                "info", f"Always on top {'enabled' if enabled else 'disabled'}."
            )
        self.settings.set("always_on_top", enabled)
        if hasattr(self, "_top_toggle"):
            self._top_toggle.blockSignals(True)
            self._top_toggle.setChecked(enabled)
            self._top_toggle.blockSignals(False)
        page = getattr(self, "settings_page", None)
        toggle = getattr(page, "always_on_top", None) if page is not None else None
        if toggle is not None:
            toggle.blockSignals(True)
            toggle.setChecked(enabled)
            toggle.blockSignals(False)

    def log(self, level: str, message: str) -> None:
        self.activity.log(str(level), str(message))

    def toast(self, level: str, message: str) -> None:
        if self._shutting_down:
            return
        self.toast_requested.emit(str(level), str(message))

    def _deliver_toast(self, level: str, message: str) -> None:
        if self._shutting_down:
            return
        if not self._ui_ready or not self.isVisible():
            self._pending_toasts.append((level, message))
            if len(self._pending_toasts) > 8:
                self._pending_toasts = self._pending_toasts[-8:]
            return
        if not bool(self.settings.get("show_toasts", True)):
            return
        if not hasattr(self, "toast_host"):
            self._pending_toasts.append((level, message))
            return
        self.toast_host.show_toast(level, message)

    def _flush_toasts(self) -> None:
        if not self._pending_toasts or self._shutting_down:
            return
        pending = self._pending_toasts
        self._pending_toasts = []
        for level, message in pending:
            self._deliver_toast(level, message)
