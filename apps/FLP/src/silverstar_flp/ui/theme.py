from __future__ import annotations

import ctypes
import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

LIGHT_STYLESHEET = """
QLabel#dialogHeading { font-size: 26px; font-weight: 700; }
QLabel#noticeLabel { background: #FFFBEB; color: #172033; border: 1px solid #D97706;
    border-radius: 4px; padding: 10px; }
QTableWidget#pluginManagerTable::item:alternate { background: #F4F6FA; }

QMainWindow, QWidget#centralRoot, QStackedWidget, QScrollArea,
QScrollArea > QWidget > QWidget {
    background: #F4F6FA;
    color: #172033;
}
QDialog, QMessageBox, QFileDialog {
    background: #FFFFFF;
    color: #172033;
}
QLabel, QCheckBox, QRadioButton { background: transparent; }
QFrame#headerBar {
    background: #123A78;
    border: 0;
    border-bottom: 1px solid #315A94;
}
QLabel#headerTitle {
    color: #FFFFFF;
    font-size: 20px;
    font-weight: 700;
    padding: 4px 2px;
}
QLabel#headerVersion {
    color: #DCEAFF;
    font-size: 13px;
    font-weight: 600;
    padding: 4px 2px;
}
QLabel#headerCredit {
    color: #DCEAFF;
    font-size: 13px;
    font-weight: 500;
    padding: 4px 2px;
}
QLabel#headerControlLabel { color: #FFFFFF; font-weight: 600; }
QPushButton#topActionButton {
    background: #1C4F94;
    color: #FFFFFF;
    border: 1px solid #6F91BE;
    border-radius: 4px;
    padding: 5px 11px;
}
QPushButton#topActionButton:hover { background: #2F6FED; border-color: #9BBCFF; }
QPushButton#topActionButton:disabled { background: #315A7A; color: #AFC3DC; }
QComboBox#headerLanguageCombo, QComboBox#headerThemeCombo {
    background: #1C4F94;
    color: #FFFFFF;
    border: 1px solid #6F91BE;
    min-width: 92px;
    min-height: 25px;
    padding: 2px 6px;
}
QComboBox#headerLanguageCombo:hover, QComboBox#headerThemeCombo:hover {
    background: #2F6FED;
    border-color: #9BBCFF;
}
QFrame#sidebar { background: #123A78; border: 0; }
QListWidget#navigation {
    background: #123A78;
    color: #FFFFFF;
    border: 0;
    outline: 0;
    font-size: 14px;
}
QListWidget#navigation::item {
    background: #123A78;
    color: #FFFFFF;
    padding: 13px 14px;
    margin: 0;
    border: 0;
    border-bottom: 1px solid #315A94;
}
QListWidget#navigation::item:hover { background: #1C4F94; }
QListWidget#navigation::item:selected { background: #2F6FED; color: #FFFFFF; }
QGroupBox {
    background: #FFFFFF;
    border: 1px solid #D7DFEB;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #123A78;
}
QGroupBox[statusLevel="success"] { border: 2px solid #16A34A; background: #F0FDF4; }
QGroupBox[statusLevel="warning"] { border: 2px solid #D97706; background: #FFFBEB; }
QGroupBox[statusLevel="error"] { border: 2px solid #DC2626; background: #FEF2F2; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QTableWidget, QTreeWidget, QListWidget {
    background: #FFFFFF;
    color: #111827;
    border: 1px solid #AEB8C8;
    border-radius: 4px;
    selection-background-color: #2F6FED;
    selection-color: #FFFFFF;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { min-height: 25px; padding: 2px 6px; }
QComboBox QAbstractItemView {
    background: #FFFFFF;
    color: #111827;
    border: 1px solid #8F9BAD;
    selection-background-color: #2F6FED;
    selection-color: #FFFFFF;
    outline: 0;
}
QComboBox QAbstractItemView::item {
    background: #FFFFFF;
    color: #111827;
    min-height: 26px;
    padding: 3px 6px;
}
QComboBox QAbstractItemView::item:selected { background: #2F6FED; color: #FFFFFF; }
QAbstractItemView#headerComboPopup {
    background: #123A78;
    color: #FFFFFF;
    border: 1px solid #6F91BE;
    selection-background-color: #2F6FED;
    selection-color: #FFFFFF;
    outline: 0;
}
QAbstractItemView#headerComboPopup::item {
    background: #123A78;
    color: #FFFFFF;
    min-height: 26px;
    padding: 3px 6px;
}
QAbstractItemView#headerComboPopup::item:hover,
QAbstractItemView#headerComboPopup::item:selected {
    background: #2F6FED;
    color: #FFFFFF;
}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background: #E9EDF4;
    color: #596273;
}
QHeaderView::section {
    background: #E7ECF4;
    color: #172033;
    border: 0;
    border-right: 1px solid #C8D0DD;
    border-bottom: 1px solid #C8D0DD;
    padding: 6px;
    font-weight: 600;
}
QTableWidget::item, QListWidget::item {
    background: #FFFFFF;
    color: #111827;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background: #2F6FED;
    color: #FFFFFF;
}
QTabWidget::pane {
    background: #FFFFFF;
    border: 1px solid #315A94;
    top: -1px;
}
QTabBar::tab {
    background: #123A78;
    color: #FFFFFF;
    border: 1px solid #315A94;
    border-bottom: 0;
    min-width: 92px;
    min-height: 28px;
    padding: 6px 14px;
    margin-right: 1px;
    font-weight: 600;
}
QTabBar::tab:hover { background: #1C4F94; color: #FFFFFF; }
QTabBar::tab:selected { background: #D6E6FF; color: #123A78; border-color: #6F91BE; }
QTabBar::tab:disabled { background: #6B7F9D; color: #D7DFEB; }
QPushButton {
    background: #FFFFFF;
    color: #172033;
    border: 1px solid #9EABBF;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover { background: #EDF3FF; border-color: #547FCF; }
QPushButton:pressed { background: #DCE8FF; }
QPushButton:disabled { background: #E9EDF4; color: #6F7888; border-color: #C8D0DD; }
QPushButton#primaryButton { background: #2F6FED; color: #FFFFFF; border: 0; }
QPushButton#primaryButton:hover { background: #255FCF; }
QLabel#metricValue { font-size: 22px; font-weight: 700; color: #1D4ED8; }
QLabel#muted { color: #64748B; }
QLabel#warningLabel {
    background: #FFF2CC;
    color: #513F00;
    padding: 8px;
    border-radius: 4px;
}
QMenuBar, QMenuBar#mainMenuBar {
    background: #123A78;
    color: #FFFFFF;
    border: 0;
}
QMenuBar::item { background: transparent; color: #FFFFFF; padding: 5px 10px; }
QMenuBar::item:selected, QMenuBar::item:pressed { background: #D6E6FF; color: #123A78; }
QToolBar, QToolBar#mainToolBar {
    background: #123A78;
    color: #FFFFFF;
    border: 0;
    spacing: 4px;
    padding: 3px;
}
QToolButton, QToolBar#mainToolBar QToolButton {
    background: #123A78;
    color: #FFFFFF;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 5px 9px;
}
QToolButton:hover, QToolBar#mainToolBar QToolButton:hover {
    background: #2F6FED;
    color: #FFFFFF;
}
QToolButton:pressed, QToolBar#mainToolBar QToolButton:pressed {
    background: #D6E6FF;
    color: #123A78;
}
QMenu { background: #FFFFFF; color: #111827; border: 1px solid #8F9BAD; }
QMenu::item { padding: 6px 26px; }
QMenu::item:selected { background: #2F6FED; color: #FFFFFF; }
QStatusBar { background: #FFFFFF; color: #172033; }
QProgressBar { background: #E2E7EF; color: #172033; border: 0; border-radius: 4px; }
QProgressBar::chunk { background: #2F6FED; border-radius: 3px; }
QToolTip { background: #FFFFFF; color: #111827; border: 1px solid #5F6B7B; }
QScrollBar:vertical { background: #EDF1F6; width: 13px; margin: 0; }
QScrollBar::handle:vertical { background: #AEB8C8; min-height: 28px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #8D9BB0; }
QScrollBar:horizontal { background: #EDF1F6; height: 13px; margin: 0; }
QScrollBar::handle:horizontal { background: #AEB8C8; min-width: 28px; border-radius: 5px; }
QScrollBar::handle:horizontal:hover { background: #8D9BB0; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
"""


DARK_STYLESHEET = """
QLabel#dialogHeading { font-size: 26px; font-weight: 700; }
QLabel#noticeLabel { background: #302711; color: #FDE68A; border: 1px solid #D97706;
    border-radius: 4px; padding: 10px; }
QTableWidget#pluginManagerTable::item:alternate { background: #1E293B; }

QMainWindow, QWidget#centralRoot, QStackedWidget, QScrollArea,
QScrollArea > QWidget > QWidget {
    background: #0F172A;
    color: #E5E7EB;
}
QDialog, QMessageBox, QFileDialog { background: #111827; color: #E5E7EB; }
QLabel, QCheckBox, QRadioButton { background: transparent; }
QFrame#headerBar {
    background: #0B2447;
    border: 0;
    border-bottom: 1px solid #234A76;
}
QLabel#headerTitle { color: #F8FAFC; font-size: 20px; font-weight: 700; padding: 4px 2px; }
QLabel#headerVersion {
    color: #C8D8EC;
    font-size: 13px;
    font-weight: 600;
    padding: 4px 2px;
}
QLabel#headerCredit {
    color: #C8D8EC;
    font-size: 13px;
    font-weight: 500;
    padding: 4px 2px;
}
QLabel#headerControlLabel { color: #F8FAFC; font-weight: 600; }
QPushButton#topActionButton {
    background: #163B6C;
    color: #F8FAFC;
    border: 1px solid #4F6F99;
    border-radius: 4px;
    padding: 5px 11px;
}
QPushButton#topActionButton:hover { background: #3B82F6; border-color: #60A5FA; }
QPushButton#topActionButton:disabled { background: #172E4D; color: #647C9B; }
QComboBox#headerLanguageCombo, QComboBox#headerThemeCombo {
    background: #163B6C;
    color: #F8FAFC;
    border: 1px solid #4F6F99;
    min-width: 92px;
    min-height: 25px;
    padding: 2px 6px;
}
QComboBox#headerLanguageCombo:hover, QComboBox#headerThemeCombo:hover {
    background: #3B82F6;
    border-color: #60A5FA;
}
QFrame#sidebar { background: #0B2447; border: 0; }
QListWidget#navigation {
    background: #0B2447;
    color: #F8FAFC;
    border: 0;
    outline: 0;
    font-size: 14px;
}
QListWidget#navigation::item {
    background: #0B2447;
    color: #E5E7EB;
    padding: 13px 14px;
    margin: 0;
    border: 0;
    border-bottom: 1px solid #234A76;
}
QListWidget#navigation::item:hover { background: #163B6C; }
QListWidget#navigation::item:selected { background: #3B82F6; color: #FFFFFF; }
QGroupBox {
    background: #111827;
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #93C5FD;
}
QGroupBox[statusLevel="success"] { border: 2px solid #22C55E; background: #102A20; }
QGroupBox[statusLevel="warning"] { border: 2px solid #F59E0B; background: #302711; }
QGroupBox[statusLevel="error"] { border: 2px solid #EF4444; background: #321717; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QTableWidget, QTreeWidget, QListWidget {
    background: #182235;
    color: #E5E7EB;
    border: 1px solid #475569;
    border-radius: 4px;
    selection-background-color: #3B82F6;
    selection-color: #FFFFFF;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { min-height: 25px; padding: 2px 6px; }
QComboBox QAbstractItemView {
    background: #182235;
    color: #E5E7EB;
    border: 1px solid #475569;
    selection-background-color: #3B82F6;
    selection-color: #FFFFFF;
    outline: 0;
}
QComboBox QAbstractItemView::item {
    background: #182235;
    color: #E5E7EB;
    min-height: 26px;
    padding: 3px 6px;
}
QComboBox QAbstractItemView::item:selected { background: #3B82F6; color: #FFFFFF; }
QAbstractItemView#headerComboPopup {
    background: #0B2447;
    color: #F8FAFC;
    border: 1px solid #4F6F99;
    selection-background-color: #3B82F6;
    selection-color: #FFFFFF;
    outline: 0;
}
QAbstractItemView#headerComboPopup::item {
    background: #0B2447;
    color: #F8FAFC;
    min-height: 26px;
    padding: 3px 6px;
}
QAbstractItemView#headerComboPopup::item:hover,
QAbstractItemView#headerComboPopup::item:selected {
    background: #3B82F6;
    color: #FFFFFF;
}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background: #172033;
    color: #64748B;
    border-color: #334155;
}
QHeaderView::section {
    background: #1E293B;
    color: #E5E7EB;
    border: 0;
    border-right: 1px solid #334155;
    border-bottom: 1px solid #475569;
    padding: 6px;
    font-weight: 600;
}
QTableWidget::item, QListWidget::item {
    background: #182235;
    color: #E5E7EB;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background: #3B82F6;
    color: #FFFFFF;
}
QTabWidget::pane {
    background: #111827;
    border: 1px solid #234A76;
    top: -1px;
}
QTabBar::tab {
    background: #0B2447;
    color: #FFFFFF;
    border: 1px solid #234A76;
    border-bottom: 0;
    min-width: 92px;
    min-height: 28px;
    padding: 6px 14px;
    margin-right: 1px;
    font-weight: 600;
}
QTabBar::tab:hover { background: #163B6C; color: #FFFFFF; }
QTabBar::tab:selected { background: #60A5FA; color: #0B2447; border-color: #93C5FD; }
QTabBar::tab:disabled { background: #334155; color: #94A3B8; }
QPushButton {
    background: #1E293B;
    color: #E5E7EB;
    border: 1px solid #475569;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover { background: #27364D; border-color: #60A5FA; }
QPushButton:pressed { background: #334155; }
QPushButton:disabled { background: #172033; color: #64748B; border-color: #334155; }
QPushButton#primaryButton { background: #3B82F6; color: #FFFFFF; border: 0; }
QPushButton#primaryButton:hover { background: #4F8CFF; }
QLabel#metricValue { font-size: 22px; font-weight: 700; color: #60A5FA; }
QLabel#muted { color: #94A3B8; }
QLabel#warningLabel {
    background: #3B3215;
    color: #FDE68A;
    padding: 8px;
    border-radius: 4px;
}
QMenuBar, QMenuBar#mainMenuBar { background: #0B2447; color: #F8FAFC; border: 0; }
QMenuBar::item { background: transparent; color: #F8FAFC; padding: 5px 10px; }
QMenuBar::item:selected, QMenuBar::item:pressed { background: #60A5FA; color: #0B2447; }
QToolBar, QToolBar#mainToolBar {
    background: #0B2447;
    color: #F8FAFC;
    border: 0;
    spacing: 4px;
    padding: 3px;
}
QToolButton, QToolBar#mainToolBar QToolButton {
    background: #0B2447;
    color: #F8FAFC;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 5px 9px;
}
QToolButton:hover, QToolBar#mainToolBar QToolButton:hover {
    background: #3B82F6;
    color: #FFFFFF;
}
QToolButton:pressed, QToolBar#mainToolBar QToolButton:pressed {
    background: #60A5FA;
    color: #0B2447;
}
QMenu { background: #182235; color: #E5E7EB; border: 1px solid #475569; }
QMenu::item { padding: 6px 26px; }
QMenu::item:selected { background: #3B82F6; color: #FFFFFF; }
QStatusBar { background: #111827; color: #E5E7EB; border-top: 1px solid #334155; }
QProgressBar { background: #172033; color: #E5E7EB; border: 1px solid #334155; }
QProgressBar::chunk { background: #3B82F6; }
QToolTip { background: #182235; color: #E5E7EB; border: 1px solid #64748B; }
QScrollBar:vertical { background: #111827; width: 13px; margin: 0; }
QScrollBar::handle:vertical { background: #475569; min-height: 28px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #64748B; }
QScrollBar:horizontal { background: #111827; height: 13px; margin: 0; }
QScrollBar::handle:horizontal { background: #475569; min-width: 28px; border-radius: 5px; }
QScrollBar::handle:horizontal:hover { background: #64748B; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
"""


def _ColorRef_Get(color_hex: str) -> int:
    color = QColor(color_hex)
    return color.red() | (color.green() << 8) | (color.blue() << 16)


def WindowCaption_Apply(window: QWidget, theme: str) -> None:
    """Use the brand blue for the native Windows caption when DWM supports it."""

    if sys.platform != "win32":
        return
    caption_color = "#0B2447" if theme == "dark" else "#123A78"
    text_color = "#F8FAFC" if theme == "dark" else "#FFFFFF"
    attributes = (
        (34, caption_color),  # DWMWA_BORDER_COLOR
        (35, caption_color),  # DWMWA_CAPTION_COLOR
        (36, text_color),  # DWMWA_TEXT_COLOR
    )
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
    dark = theme == "dark"
    application.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#0F172A" if dark else "#F4F6FA"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#E5E7EB" if dark else "#172033"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#182235" if dark else "#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#E5E7EB" if dark else "#172033"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3B82F6" if dark else "#2F6FED"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    application.setPalette(palette)
    application.setStyleSheet(DARK_STYLESHEET if dark else LIGHT_STYLESHEET)


def Plot_Colors(theme: str) -> tuple[str, str]:
    return ("#111827", "#D1D5DB") if theme == "dark" else ("#FFFFFF", "#334155")
