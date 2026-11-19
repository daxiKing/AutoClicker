"""Retro Windows palette and Qt stylesheet for AutoClicker.

The visual language is deliberately Windows 95/98/2000: silver bevels, navy
selection bars, sunken white fields, Tahoma-style type and a teal desktop with
an animated Mystify backdrop. Nothing here uses rounded modern cards.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    "bg": "#008080",          # classic teal desktop
    "bg_alt": "#007070",
    "sidebar": "#c0c0c0",
    "card": "#c0c0c0",
    "card_soft": "#c0c0c0",
    "border": "#808080",
    "border_bright": "#ffffff",
    "input": "#ffffff",
    "text": "#000000",
    "muted": "#404040",
    "faint": "#808080",
    "accent": "#000080",      # active caption / selection navy
    "accent_soft": "#d4d0c8",
    "accent_2": "#800080",
    "cyan": "#008080",
    "pink": "#800040",
    "amber": "#808000",
    "green": "#008000",
    "red": "#800000",
    "red_soft": "#ffc0c0",
}

FONT_UI = "Tahoma"
FONT_MONO = "Courier New"

# Reusable QSS fragments cannot be used as variables, so the bevels are spelled
# out. A raised control is white on the top/left and dark on the bottom/right;
# a sunken field is the inverse.
RAISED = (
    "border: 2px solid; "
    "border-top-color: #ffffff; "
    "border-left-color: #ffffff; "
    "border-right-color: #404040; "
    "border-bottom-color: #404040; "
    "border-radius: 0;"
)
SUNKEN = (
    "border: 2px solid; "
    "border-top-color: #404040; "
    "border-left-color: #404040; "
    "border-right-color: #ffffff; "
    "border-bottom-color: #ffffff; "
    "border-radius: 0;"
)


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont(FONT_UI, 9))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["card"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor(COLORS["input"]))
    palette.setColor(QPalette.AlternateBase, QColor("#e8e8e8"))
    palette.setColor(QPalette.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.Button, QColor(COLORS["card"]))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Highlight, QColor(COLORS["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.PlaceholderText, QColor(COLORS["faint"]))
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffe1"))
    palette.setColor(QPalette.ToolTipText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Link, QColor(COLORS["accent"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(COLORS["faint"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(COLORS["faint"]))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(COLORS["faint"]))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)


STYLESHEET = f"""
* {{
    outline: none;
}}
QMainWindow, QDialog {{
    background: #c0c0c0;
}}
QWidget {{
    color: #000000;
    font-family: "Tahoma";
    font-size: 12px;
}}
QWidget#Root {{
    background: #008080;
}}
QScrollArea, QWidget#PageBody, QStackedWidget#PageStack {{
    background: transparent;
    border: none;
}}
QFrame#Sidebar {{
    background: #c0c0c0;
    border: none;
    border-right: 2px solid #404040;
}}
QFrame#TopBar {{
    background: #c0c0c0;
    border: none;
    border-bottom: 2px solid #404040;
}}
QFrame#Card {{
    background: #c0c0c0;
    {RAISED}
}}
QFrame#SoftCard {{
    background: #c0c0c0;
    {RAISED}
}}
QFrame#HeroCard {{
    background: #d4d0c8;
    {RAISED}
}}
QFrame#DangerCard {{
    background: #c0c0c0;
    border: 2px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #800000;
    border-bottom-color: #800000;
    border-radius: 0;
}}
QFrame#HLine {{
    background: transparent;
    border: none;
    border-top: 1px solid #808080;
    border-bottom: 1px solid #ffffff;
    max-height: 2px;
    min-height: 2px;
}}
QFrame#SidebarDivider {{
    background: transparent;
    border: none;
    border-top: 1px solid #808080;
    border-bottom: 1px solid #ffffff;
    max-height: 2px;
}}
QLabel {{
    background: transparent;
}}
QLabel#PageTitle {{
    font-size: 24px;
    font-weight: 700;
    color: #000000;
}}
QLabel#PageSub {{
    font-size: 11px;
    color: #404040;
}}
QLabel#Eyebrow {{
    font-size: 9px;
    font-weight: 700;
    color: #000080;
}}
QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 700;
    color: #000000;
}}
QLabel#SectionTitle {{
    font-size: 11px;
    font-weight: 700;
    color: #000000;
}}
QLabel#Muted {{
    color: #404040;
    font-size: 11px;
}}
QLabel#Tiny {{
    color: #404040;
    font-size: 10px;
}}
QLabel#Value {{
    color: #000080;
    font-size: 18px;
    font-weight: 700;
}}
QLabel#BigNumber {{
    font-family: "Courier New";
    font-size: 28px;
    font-weight: 700;
    color: #000080;
}}
QLabel#HeroTitle {{
    font-size: 22px;
    font-weight: 700;
    color: #000080;
}}
QLabel#HeroSub {{
    font-size: 11px;
    color: #404040;
}}
QLabel#Accent {{
    color: #000080;
}}
QLabel#DangerText {{
    color: #800000;
}}
QLabel#Link {{
    color: #000080;
}}
QLabel#VersionBadge {{
    background: #ffffff;
    border: 1px solid #808080;
    border-radius: 0;
    color: #000080;
    font-family: "Courier New";
    font-size: 9px;
    font-weight: 700;
    padding: 2px 5px;
}}
QPushButton {{
    {RAISED}
    background: #c0c0c0;
    color: #000000;
    padding: 5px 12px;
    min-height: 16px;
}}
QPushButton:hover {{
    background: #d4d0c8;
}}
QPushButton:pressed {{
    background: #b0b0b0;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
}}
QPushButton:focus {{
    outline: 1px dotted #000000;
    outline-offset: -5px;
}}
QPushButton:disabled {{
    color: #808080;
    background: #c0c0c0;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #808080;
    border-bottom-color: #808080;
}}
QPushButton#NavButton {{
    background: transparent;
    border: 1px solid transparent;
    color: #000000;
    text-align: left;
    padding: 9px 11px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#NavButton:hover {{
    background: #000080;
    border: 1px solid #000080;
    color: #ffffff;
}}
QPushButton#NavButton:checked {{
    background: #000080;
    border: 1px solid #000080;
    color: #ffffff;
    font-weight: 700;
}}
QPushButton#PrimaryButton {{
    background: #c0c0c0;
    color: #000080;
    font-size: 12px;
    font-weight: 800;
    padding: 8px 18px;
}}
QPushButton#PrimaryButton:hover {{
    background: #d4d0c8;
}}
QPushButton#PrimaryButton:pressed {{
    background: #b0b0b0;
}}
QPushButton#PrimaryButton:disabled {{
    color: #808080;
}}
QPushButton#StartButton {{
    background: #c0c0c0;
    color: #000080;
    font-size: 13px;
    font-weight: 800;
    padding: 10px 22px;
    min-height: 28px;
}}
QPushButton#StartButton:hover {{
    background: #d4d0c8;
}}
QPushButton#StartButton[running="true"] {{
    background: #800000;
    color: #ffffff;
    border-top-color: #ffc0c0;
    border-left-color: #ffc0c0;
    border-right-color: #400000;
    border-bottom-color: #400000;
}}
QPushButton#StartButton[running="true"]:hover {{
    background: #a00000;
}}
QPushButton#GhostButton {{
    background: #c0c0c0;
    color: #000000;
    font-size: 11px;
    padding: 6px 12px;
}}
QPushButton#GhostButton:hover {{
    background: #d4d0c8;
}}
QPushButton#DangerButton {{
    background: #c0c0c0;
    color: #800000;
    font-size: 11px;
    font-weight: 700;
    padding: 6px 13px;
}}
QPushButton#DangerButton:hover {{
    background: #e8c8c8;
}}
QPushButton#RecordButton {{
    background: #c0c0c0;
    color: #800000;
    font-size: 12px;
    font-weight: 700;
    padding: 8px 15px;
}}
QPushButton#RecordButton:hover {{
    background: #d4d0c8;
}}
QPushButton#RecordButton[recording="true"] {{
    background: #800000;
    color: #ffffff;
    border-top-color: #ffc0c0;
    border-left-color: #ffc0c0;
    border-right-color: #400000;
    border-bottom-color: #400000;
}}
QPushButton#Chip {{
    background: #c0c0c0;
    color: #000000;
    font-size: 10px;
    font-weight: 700;
    padding: 4px 10px;
}}
QPushButton#Chip:checked {{
    background: #000080;
    color: #ffffff;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
}}
QPushButton#LoopChip {{
    background: #ffffe1;
    color: #000080;
    font-size: 11px;
    font-weight: 800;
    padding: 6px 10px;
}}
QPushButton#LoopChip:hover {{
    background: #ffffc0;
}}
QPushButton#LoopChip:checked {{
    background: #000080;
    color: #ffffff;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
}}
QPushButton#LoopChip:disabled {{
    color: #808080;
    background: #d4d0c8;
}}
QPushButton#KeycapButton {{
    background: #ffffff;
    border: 2px solid;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
    color: #000080;
    font-family: "Courier New";
    font-size: 10px;
    font-weight: 700;
    padding: 2px 5px;
}}
QPushButton#KeycapButton:hover {{
    background: #ffffe1;
}}
QPushButton#KeycapButton[tone="violet"] {{
    color: #800080;
}}
QPushButton#KeycapButton[tone="red"] {{
    color: #800000;
}}
QPushButton#KeycapButton[capturing="true"] {{
    background: #ffff00;
    color: #000000;
}}
QPushButton#KeycapButton:disabled {{
    color: #808080;
    background: #d4d0c8;
}}
QPushButton#Segment {{
    background: #c0c0c0;
    color: #000000;
    font-size: 10px;
    font-weight: 700;
    padding: 5px 10px;
}}
QPushButton#Segment:hover {{
    background: #d4d0c8;
}}
QPushButton#Segment:checked {{
    background: #000080;
    color: #ffffff;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
}}
QPushButton#IconButton {{
    background: transparent;
    border: 1px solid transparent;
    color: #000000;
    padding: 3px;
}}
QPushButton#IconButton:hover {{
    background: #d4d0c8;
    border: 1px solid #808080;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    {SUNKEN}
    background: #ffffff;
    color: #000000;
    padding: 4px 6px;
    min-height: 20px;
    selection-background-color: #000080;
    selection-color: #ffffff;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-top-color: #000080;
    border-left-color: #000080;
    border-right-color: #000080;
    border-bottom-color: #000080;
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: #808080;
    background: #d4d0c8;
}}
QSpinBox#BigSpin {{
    font-family: "Courier New";
    font-size: 28px;
    font-weight: 700;
    color: #000080;
    background: #ffffff;
    {SUNKEN}
    padding: 4px 10px;
    min-height: 44px;
}}
QSpinBox#BigSpin::up-button, QSpinBox#BigSpin::down-button {{
    width: 0px;
    border: none;
    background: transparent;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 18px;
    background: #c0c0c0;
    border: 1px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: #d4d0c8;
}}
QComboBox::drop-down {{
    width: 22px;
    background: #c0c0c0;
    border-left: 1px solid #808080;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
}}
QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 2px solid #404040;
    color: #000000;
    selection-background-color: #000080;
    selection-color: #ffffff;
    padding: 2px;
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: #ffffff;
    border: 2px solid;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
}}
QSlider::sub-page:horizontal {{
    background: #000080;
}}
QSlider::handle:horizontal {{
    width: 12px;
    height: 20px;
    margin: -9px 0;
    background: #c0c0c0;
    border: 2px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
}}
QSlider::handle:horizontal:hover {{
    background: #d4d0c8;
}}
QSlider::handle:horizontal:disabled {{
    background: #d4d0c8;
}}
QCheckBox {{
    spacing: 7px;
    color: #000000;
    font-size: 11px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    background: #ffffff;
    border: 2px solid;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
}}
QCheckBox::indicator:checked {{
    background: #000080;
    border: 2px solid;
    border-top-color: #000000;
    border-left-color: #000000;
    border-right-color: #808080;
    border-bottom-color: #808080;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    width: 16px;
    background: #c0c0c0;
    border-left: 1px solid #808080;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #c0c0c0;
    border: 2px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
    min-height: 24px;
    margin: 1px;
}}
QScrollBar::handle:vertical:hover {{
    background: #d4d0c8;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 16px;
    background: #c0c0c0;
    border: 2px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: #c0c0c0;
}}
QScrollBar:horizontal {{
    height: 16px;
    background: #c0c0c0;
    border-top: 1px solid #808080;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #c0c0c0;
    border: 2px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
    min-width: 24px;
    margin: 1px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #d4d0c8;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 16px;
    background: #c0c0c0;
    border: 2px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: #c0c0c0;
}}
QListWidget {{
    background: #ffffff;
    border: 2px solid;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
    outline: none;
}}
QListWidget::item {{
    background: transparent;
    border: 1px solid transparent;
    margin: 0;
}}
QListWidget::item:hover {{
    background: #e8e8e8;
}}
QListWidget::item:selected {{
    background: #cce8ff;
    border: 1px dotted #000080;
    color: #000000;
}}
QTableWidget {{
    background: #ffffff;
    alternate-background-color: #f2f2f2;
    border: 2px solid;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
    gridline-color: #d4d0c8;
    outline: none;
    selection-background-color: #cce8ff;
    selection-color: #000000;
}}
QTableWidget::item {{
    padding: 4px 6px;
    border: none;
}}
QTableWidget::item:selected {{
    background: #cce8ff;
    color: #000000;
}}
QHeaderView::section {{
    background: #c0c0c0;
    border: 1px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
    color: #000000;
    padding: 4px 6px;
    font-size: 10px;
    font-weight: 700;
}}
QTextBrowser, QTextEdit {{
    background: #ffffff;
    border: 2px solid;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
    color: #000000;
    padding: 7px;
    selection-background-color: #000080;
    selection-color: #ffffff;
}}
QProgressBar {{
    background: #ffffff;
    border: 2px solid;
    border-top-color: #404040;
    border-left-color: #404040;
    border-right-color: #ffffff;
    border-bottom-color: #ffffff;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: #000080;
}}
QToolTip {{
    background: #ffffe1;
    color: #000000;
    border: 1px solid #000000;
    padding: 4px 6px;
}}
QMessageBox {{
    background: #c0c0c0;
}}
QMessageBox QLabel {{
    color: #000000;
    font-size: 12px;
}}
QMenu {{
    background: #c0c0c0;
    border: 2px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
    padding: 3px;
    color: #000000;
}}
QMenu::item {{
    padding: 5px 22px;
}}
QMenu::item:selected {{
    background: #000080;
    color: #ffffff;
}}
QDialogButtonBox QPushButton {{
    background: #c0c0c0;
    border: 2px solid;
    border-top-color: #ffffff;
    border-left-color: #ffffff;
    border-right-color: #404040;
    border-bottom-color: #404040;
    color: #000000;
    padding: 5px 14px;
    min-width: 70px;
}}
QDialogButtonBox QPushButton:hover {{
    background: #d4d0c8;
}}
"""
