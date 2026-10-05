from __future__ import annotations

import ctypes
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    surface: str
    surface_alt: str
    surface_input: str
    disabled_surface: str
    text: str
    muted: str
    border: str
    border_strong: str
    brand: str
    brand_hover: str
    accent: str
    accent_soft: str
    accent_text: str
    success: str
    success_surface: str
    warning: str
    warning_surface: str
    error: str
    error_surface: str
    header_text: str
    header_muted: str


_LIGHT = ThemeTokens(
    surface="#F4F6FA",
    surface_alt="#FFFFFF",
    surface_input="#FFFFFF",
    disabled_surface="#E2E8F0",
    text="#172033",
    muted="#64748B",
    border="#D7DFEB",
    border_strong="#AEB8C8",
    brand="#123A78",
    brand_hover="#1C4F94",
    accent="#2F6FED",
    accent_soft="#D6E6FF",
    accent_text="#FFFFFF",
    success="#16A34A",
    success_surface="#F0FDF4",
    warning="#D97706",
    warning_surface="#FFFBEB",
    error="#DC2626",
    error_surface="#FEF2F2",
    header_text="#FFFFFF",
    header_muted="#DCEAFF",
)

_DARK = ThemeTokens(
    surface="#0F172A",
    surface_alt="#111827",
    surface_input="#182235",
    disabled_surface="#263449",
    text="#E5E7EB",
    muted="#94A3B8",
    border="#334155",
    border_strong="#475569",
    brand="#0B2447",
    brand_hover="#163B6C",
    accent="#3B82F6",
    accent_soft="#60A5FA",
    accent_text="#FFFFFF",
    success="#22C55E",
    success_surface="#102A20",
    warning="#F59E0B",
    warning_surface="#302711",
    error="#EF4444",
    error_surface="#321717",
    header_text="#F8FAFC",
    header_muted="#C8D8EC",
)

_STYLESHEET = Template(
    """
QMainWindow, QWidget#centralRoot, QStackedWidget, QScrollArea,
QScrollArea > QWidget > QWidget {
    background: $surface;
    color: $text;
}
QDialog, QMessageBox, QFileDialog, QWizard { background: $surface_alt; color: $text; }
QLabel, QCheckBox, QRadioButton { background: transparent; }
QCheckBox#standardCheckBox { spacing: 7px; }
QCheckBox#standardCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid $border_strong;
    border-radius: 3px;
    background: $surface_input;
}
QCheckBox#standardCheckBox::indicator:hover { border-color: $accent; }
QCheckBox#standardCheckBox::indicator:checked {
    background: $accent;
    border-color: $accent;
    image: url("$checkbox_check_image");
}
QCheckBox#standardCheckBox::indicator:disabled {
    background: $surface;
    border-color: $border;
}
QFrame#headerBar {
    background: $brand;
    border: 0;
    border-bottom: 1px solid $border_strong;
}
QLabel#headerTitle { color: $header_text; font-size: 20px; font-weight: 700; padding: 4px 2px; }
QLabel#headerVersion { color: $header_muted; font-size: 13px; font-weight: 600; padding: 4px 2px; }
QLabel#headerCredit { color: $header_muted; font-size: 13px; font-weight: 500; padding: 4px 2px; }
QLabel#headerControlLabel { color: $header_text; font-weight: 600; }
QLabel#headerProjectValue { color: $header_muted; font-weight: 600; }
QLabel#pageTitle { color: $text; font-size: 23px; font-weight: 700; }
QLabel#pageDescription, QLabel#muted { color: $muted; }
QLabel#noticeLabel {
    color: $text;
    background: $warning_surface;
    border: 1px solid $warning;
    border-radius: 5px;
    padding: 8px;
}
QLabel#statusPill {
    border-radius: 9px;
    padding: 3px 9px;
    font-weight: 700;
}
QLabel#statusPill[statusLevel="success"] { color: $success; background: $success_surface; }
QLabel#statusPill[statusLevel="warning"] { color: $warning; background: $warning_surface; }
QLabel#statusPill[statusLevel="error"] { color: $error; background: $error_surface; }
QLabel#statusPill[statusLevel="info"] { color: $accent_text; background: $accent; }
QComboBox#headerLanguageCombo, QComboBox#headerThemeCombo {
    background: $brand_hover;
    color: $header_text;
    border: 1px solid $header_muted;
    min-width: 96px;
    min-height: 25px;
    padding: 2px 7px;
}
QComboBox#headerLanguageCombo:hover, QComboBox#headerThemeCombo:hover {
    background: $accent;
}
QAbstractItemView#headerComboPopup {
    background: $brand;
    color: $header_text;
    border: 1px solid $header_muted;
    selection-background-color: $accent;
    selection-color: $accent_text;
    outline: 0;
}
QAbstractItemView#headerComboPopup::item {
    background: $brand;
    color: $header_text;
    min-height: 26px;
    padding: 3px 7px;
}
QAbstractItemView#headerComboPopup::item:hover,
QAbstractItemView#headerComboPopup::item:selected { background: $accent; color: $accent_text; }
QFrame#sidebar { background: $brand; border: 0; }
QListWidget#navigation {
    background: $brand;
    color: $header_text;
    border: 0;
    outline: 0;
    font-size: 14px;
}
QListWidget#navigation::item {
    background: $brand;
    color: $header_text;
    padding: 12px 14px;
    border: 0;
    border-bottom: 1px solid $brand_hover;
}
QListWidget#navigation::item:hover { background: $brand_hover; }
QListWidget#navigation::item:selected { background: $accent; color: $accent_text; }
QGroupBox {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: $accent;
}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QTableWidget, QTreeWidget, QListWidget {
    background: $surface_input;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 4px;
    selection-background-color: $accent;
    selection-color: $accent_text;
}
QLineEdit, QComboBox { min-height: 26px; padding: 2px 7px; }
QSpinBox, QDoubleSpinBox {
    min-height: 26px;
    padding: 2px 30px 2px 7px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    width: 24px;
    background: $surface;
    border-left: 1px solid $border_strong;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-position: top right;
    border-bottom: 1px solid $border;
    border-top-right-radius: 3px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-position: bottom right;
    border-bottom-right-radius: 3px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: $accent_soft;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("$spin_plus_image");
    width: 11px;
    height: 11px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("$spin_minus_image");
    width: 11px;
    height: 11px;
}
QComboBox[validationIssue="true"], QTableWidget[validationIssue="true"],
QCheckBox[validationIssue="true"], QWidget[validationIssue="true"] {
    border: 2px solid $error;
}
QComboBox QAbstractItemView {
    background: $surface_input;
    color: $text;
    border: 1px solid $border_strong;
    selection-background-color: $accent;
    selection-color: $accent_text;
    outline: 0;
}
QComboBox QAbstractItemView::item { min-height: 26px; padding: 3px 7px; }
QComboBox QAbstractItemView::item:disabled {
    color: $muted;
    background: $disabled_surface;
}
QHeaderView::section {
    background: $surface;
    color: $text;
    border: 0;
    border-right: 1px solid $border;
    border-bottom: 1px solid $border_strong;
    padding: 6px;
    font-weight: 600;
}
QTableWidget { gridline-color: $border; alternate-background-color: $surface; }
QTabWidget::pane { background: $surface_alt; border: 1px solid $brand_hover; top: -1px; }
QTabBar::tab {
    background: $brand;
    color: $header_text;
    border: 1px solid $brand_hover;
    border-bottom: 0;
    min-width: 90px;
    min-height: 27px;
    padding: 6px 13px;
    margin-right: 1px;
    font-weight: 600;
}
QTabBar::tab:hover { background: $brand_hover; }
QTabBar::tab:selected { background: $accent; color: $accent_text; }
QPushButton {
    background: $surface_alt;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover { background: $surface; border-color: $accent; }
QPushButton:pressed { background: $accent_soft; }
QPushButton:disabled { color: $muted; border-color: $border; }
QPushButton#primaryButton { background: $accent; color: $accent_text; border: 0; }
QPushButton#primaryButton:hover { background: $brand_hover; }
QPushButton#primaryButton:disabled {
    background: $disabled_surface;
    color: $muted;
    border: 1px solid $border;
}
QPushButton#dangerButton { color: $error; border-color: $error; }
QMenuBar, QMenuBar#mainMenuBar { background: $brand; color: $header_text; border: 0; }
QMenuBar::item { background: transparent; color: $header_text; padding: 5px 10px; }
QMenuBar::item:selected, QMenuBar::item:pressed { background: $accent; color: $accent_text; }
QToolBar, QToolBar#mainToolBar {
    background: $brand;
    color: $header_text;
    border: 0;
    spacing: 4px;
    padding: 3px;
}
QToolButton { background: $brand; color: $header_text; border: 1px solid transparent;
    border-radius: 3px; padding: 5px 9px; }
QToolButton:hover { background: $accent; color: $accent_text; }
QToolButton#collapsibleHeader {
    background: $surface_alt;
    color: $accent;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 7px 9px;
    font-weight: 700;
    text-align: left;
}
QToolButton#collapsibleHeader:hover { background: $surface; color: $accent; }
QWidget#collapsibleBody {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 6px;
}
QMenu { background: $surface_input; color: $text; border: 1px solid $border_strong; }
QMenu::item { padding: 6px 26px; }
QMenu::item:selected { background: $accent; color: $accent_text; }
QStatusBar { background: $surface_alt; color: $text; border-top: 1px solid $border; }
QProgressBar { background: $surface; color: $text; border: 1px solid $border; border-radius: 4px; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QScrollBar:vertical { background: $surface_alt; width: 13px; margin: 0; }
QScrollBar::handle:vertical { background: $border_strong; min-height: 28px; border-radius: 5px; }
QScrollBar:horizontal { background: $surface_alt; height: 13px; margin: 0; }
QScrollBar::handle:horizontal { background: $border_strong; min-width: 28px; border-radius: 5px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QSplitter::handle { background: $border; }
QToolTip { background: $surface_input; color: $text; border: 1px solid $border_strong; }
"""
)


def ThemeTokens_Get(theme: str) -> ThemeTokens:
    return _DARK if theme == "dark" else _LIGHT


def Stylesheet_Get(theme: str) -> str:
    values = asdict(ThemeTokens_Get(theme))
    asset_root = Path(__file__).resolve().parent / "assets"
    values["checkbox_check_image"] = (asset_root / "check_white.svg").as_posix()
    icon_suffix = "dark" if theme == "dark" else "light"
    values["spin_plus_image"] = (
        asset_root / f"spin_plus_{icon_suffix}.svg"
    ).as_posix()
    values["spin_minus_image"] = (
        asset_root / f"spin_minus_{icon_suffix}.svg"
    ).as_posix()
    return _STYLESHEET.substitute(values)


def _ColorRef_Get(color_hex: str) -> int:
    color = QColor(color_hex)
    return color.red() | (color.green() << 8) | (color.blue() << 16)


def WindowCaption_Apply(window: QWidget, theme: str) -> None:
    if sys.platform != "win32":
        return
    tokens = ThemeTokens_Get(theme)
    attributes = ((34, tokens.brand), (35, tokens.brand), (36, tokens.header_text))
    try:
        handle = ctypes.c_void_p(int(window.winId()))
        setter = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute
        for attribute, color_hex in attributes:
            value = ctypes.c_uint32(_ColorRef_Get(color_hex))
            setter(
                handle,
                ctypes.c_uint32(attribute),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return


def Theme_Apply(application: QApplication, theme: str) -> None:
    if application.property("fccgAppliedTheme") == theme:
        return
    tokens = ThemeTokens_Get(theme)
    if not bool(application.property("fccgFusionStyleInitialized")):
        application.setStyle("Fusion")
        application.setProperty("fccgFusionStyleInitialized", True)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(tokens.surface))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(tokens.surface_input))
    palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Base,
        QColor(tokens.disabled_surface),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(tokens.muted),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(tokens.muted),
    )
    palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens.accent_text))
    application.setPalette(palette)
    application.setStyleSheet(Stylesheet_Get(theme))
    application.setProperty("fccgAppliedTheme", theme)
