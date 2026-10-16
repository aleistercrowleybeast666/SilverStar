from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QGraphicsView, QHeaderView,
    QListWidget, QPlainTextEdit, QPushButton, QScrollArea, QScroller,
    QSlider, QSpinBox, QTableWidget, QTextEdit, QTreeWidget,
)

from ui.touch_scroll import TouchScroll_Enable


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("factory", [
    QScrollArea, QListWidget, QTableWidget, QTreeWidget, QPlainTextEdit, QTextEdit,
])
def test_native_gesture_targets_only_the_content_viewport(application, factory):
    widget = factory()
    if isinstance(widget, QAbstractItemView):
        widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    with patch.object(QScroller, "grabGesture", wraps=QScroller.grabGesture) as grab:
        TouchScroll_Enable(widget)
        grab.assert_called_once_with(widget.viewport(), QScroller.ScrollerGestureType.TouchGesture)
    assert QScroller.hasScroller(widget.viewport())
    assert QScroller.grabbedGesture(widget.viewport()).value >= Qt.GestureType.CustomGesture.value
    assert not QScroller.hasScroller(widget)
    if isinstance(widget, QAbstractItemView):
        assert widget.verticalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel
    widget.close()


@pytest.mark.parametrize("factory", [
    QPushButton, QComboBox, QSpinBox, QSlider, QGraphicsView,
    lambda: QHeaderView(Qt.Orientation.Horizontal),
])
def test_specialized_controls_are_not_page_gesture_targets(application, factory):
    widget = factory()
    TouchScroll_Enable(widget)
    assert not QScroller.hasScroller(widget)
    if isinstance(widget, (QGraphicsView, QHeaderView)):
        assert not QScroller.hasScroller(widget.viewport())
    widget.close()


def test_list_click_selection_survives_touch_registration(application):
    widget = QListWidget()
    widget.addItems([str(row) for row in range(100)])
    TouchScroll_Enable(widget)
    widget.show()
    application.processEvents()
    QTest.mouseClick(widget.viewport(), Qt.MouseButton.LeftButton,
                     pos=widget.visualItemRect(widget.item(2)).center())
    assert widget.currentRow() == 2
    widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum())
    assert widget.verticalScrollBar().value() > 0
    widget.close()


def test_window_scroll_coverage_and_graphics_exclusions(application, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from services.i18n import I18n
    from ui.main_window import MainWindow
    window = MainWindow(I18n(QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)))
    try:
        window.show()
        application.processEvents()
        areas = window.findChildren(QScrollArea)
        assert areas
        for area in areas:
            assert QScroller.hasScroller(area.viewport())
        for cls in (QListWidget, QTableWidget, QTreeWidget, QPlainTextEdit, QTextEdit):
            for widget in window.findChildren(cls):
                assert QScroller.hasScroller(widget.viewport()), widget.objectName()
        for cls in (QPushButton, QSpinBox, QSlider, QComboBox, QGraphicsView):
            for widget in window.findChildren(cls):
                assert not QScroller.hasScroller(widget), widget.objectName()
                if isinstance(widget, QGraphicsView):
                    assert not QScroller.hasScroller(widget.viewport())
                    assert widget in window.plot_widgets.values()
                    assert [area for area in areas if area.isAncestorOf(widget)] == [window.flight_page]
        for widget in window.findChildren(QSlider):
            assert not any(area.isAncestorOf(widget) for area in areas)
        # pyqtgraph GLViewWidget is a QWidget, not a graphics/scroll view.
        from PySide6.QtWidgets import QWidget
        for widget in window.findChildren(QWidget):
            if any(cls.__name__ == "GLViewWidget" for cls in type(widget).__mro__):
                assert not QScroller.hasScroller(widget)
                assert not any(area.isAncestorOf(widget) for area in areas)
    finally:
        window.close()
        window.deleteLater()
        application.processEvents()


@pytest.mark.parametrize("name", ["catalog", "tree", "swd_diagnostics", "diagnostic_tree", "swd_target"])
def test_maintenance_content_viewports_have_touch_gestures(application, tmp_path, name):
    from PySide6.QtCore import QSettings
    from services.i18n import I18n
    from ui.maintenance_page import MaintenancePage

    page = MaintenancePage(I18n(QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat)))
    try:
        widget = getattr(page, name)
        if isinstance(widget, QComboBox):
            widget = widget.view()
        assert widget.verticalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel
        assert QScroller.hasScroller(widget.viewport()), name
        assert not QScroller.hasScroller(widget)
    finally:
        page.close()
        page.deleteLater()
        application.processEvents()


def test_maintenance_catalog_finger_scroll_keeps_click_selection(application, tmp_path):
    from PySide6.QtCore import QPoint, QSettings
    from services.i18n import I18n
    from ui.main_window import MainWindow

    window = MainWindow(I18n(QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat)))
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window.resize(1280, 720)
        catalog = window.maintenance_page.catalog
        window.maintenance_page.show_catalog(range(1, 101))
        window.pages.setCurrentWidget(window.maintenance_scroll)
        window.show()
        application.processEvents()
        window.maintenance_scroll.ensureWidgetVisible(catalog, 0, 0)
        application.processEvents()
        assert QScroller.hasScroller(catalog.viewport())
        assert catalog.verticalScrollBar().maximum() > 0
        QTest.mouseClick(catalog.viewport(), Qt.LeftButton,
                         pos=catalog.visualItemRect(catalog.item(2)).center())
        assert catalog.currentRow() == 2
        viewport = catalog.viewport()
        start = viewport.height() - 20
        device = QTest.createTouchDevice()
        QTest.touchEvent(viewport, device).press(0, QPoint(60, start), viewport).commit()
        QTest.qWait(50)
        for delta in (20, 40, 60, 80):
            QTest.touchEvent(viewport, device).move(0, QPoint(60, start - delta), viewport).commit()
            QTest.qWait(50)
        QTest.touchEvent(viewport, device).release(0, QPoint(60, start - 80), viewport).commit()
        QTest.qWait(100)
        assert catalog.verticalScrollBar().value() > 0
        QScroller.scroller(viewport).stop()
        catalog.scrollToBottom()
        application.processEvents()
        last = catalog.visualItemRect(catalog.item(99))
        assert viewport.rect().contains(last)
        QTest.mouseClick(viewport, Qt.LeftButton, pos=last.center())
        assert catalog.currentRow() == 99
        assert catalog.currentItem().text() == "Mission 000100 · flight.sslog · closed"
    finally:
        window.close()
        window.deleteLater()
        application.processEvents()


def test_flight_plot_mouse_pan_survives_page_touch_scroll(application, tmp_path):
    from PySide6.QtCore import QPoint, QSettings
    from services.i18n import I18n
    from ui.main_window import MainWindow

    window = MainWindow(I18n(QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat)))
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window.resize(1280, 720)
        window.pages.setCurrentWidget(window.flight_page)
        window.show()
        QTest.qWait(50)
        plot = window.plot_widgets[("vel", 0)]
        view = plot.getViewBox()
        view.setRange(xRange=(0, 10), yRange=(0, 10), padding=0)
        before = view.viewRange()
        center = plot.mapFromScene(view.sceneBoundingRect().center())
        assert QScroller.hasScroller(window.flight_page.viewport())
        assert not QScroller.hasScroller(plot.viewport())
        QTest.mousePress(plot.viewport(), Qt.LeftButton, pos=center)
        QTest.mouseMove(plot.viewport(), center + QPoint(30, 20), delay=50)
        QTest.mouseMove(plot.viewport(), center + QPoint(60, 40), delay=50)
        QTest.mouseRelease(plot.viewport(), Qt.LeftButton, pos=center + QPoint(60, 40))
        application.processEvents()
        assert view.viewRange()[1] != before[1]
        assert window.flight_page.verticalScrollBar().value() == 0
    finally:
        window.close()
        window.deleteLater()
        application.processEvents()


@pytest.mark.parametrize("kind", ["page", "list", "table", "text"])
def test_native_finger_drag_scrolls_content(application, kind):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QWidget

    if kind == "page":
        widget = QScrollArea()
        content = QWidget()
        content.setMinimumSize(200, 2000)
        widget.setWidget(content)
    elif kind == "list":
        widget = QListWidget()
        widget.addItems([str(row) for row in range(100)])
    elif kind == "table":
        widget = QTableWidget(100, 2)
    else:
        widget = QPlainTextEdit()
        widget.setReadOnly(True)
        widget.setPlainText("\n".join(str(row) for row in range(100)))
    TouchScroll_Enable(widget)
    widget.resize(260, 260)
    widget.show()
    application.processEvents()
    viewport = widget.viewport()
    device = QTest.createTouchDevice()
    QTest.touchEvent(viewport, device).press(0, QPoint(100, 180), viewport).commit()
    QTest.qWait(50)
    for y in (150, 120, 90, 60):
        QTest.touchEvent(viewport, device).move(0, QPoint(100, y), viewport).commit()
        QTest.qWait(50)
    QTest.touchEvent(viewport, device).release(0, QPoint(100, 60), viewport).commit()
    QTest.qWait(100)
    assert widget.verticalScrollBar().value() > 0
    QScroller.scroller(viewport).stop()
    widget.close()
