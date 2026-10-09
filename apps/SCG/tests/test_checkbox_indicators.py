"""Render actual Qt indicators and exercise label/keyboard selection semantics."""
import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QCheckBox, QStyle, QStyleOptionButton

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.ui.pages.build import BuildPage
from silverstar_fccg.ui.theme import Theme_Apply, ThemeTokens_Get
from silverstar_fccg.ui.widgets import LockedCheckBox, StandardCheckBox


def _Indicator_Get(box):
    option = QStyleOptionButton()
    box.initStyleOption(option)
    rect = box.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, box)
    return box.grab().toImage().copy(rect)


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('checked,enabled', [(False, True), (True, True), (False, False), (True, False)])
def test_every_checkbox_has_the_same_visible_indicator(qapp, theme, checked, enabled):
    Theme_Apply(qapp, theme)
    boxes = [QCheckBox('Include'), StandardCheckBox('Include'), QCheckBox('Include')]
    boxes[2].setObjectName('targetSelection')
    images = []
    for box in boxes:
        box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        box.resize(180, 40)
        box.setChecked(checked)
        box.setEnabled(enabled)
        box.show()
        qapp.processEvents()
        qapp.sendEvent(box, QEvent(QEvent.Type.Leave))
        images.append(_Indicator_Get(box))
    assert images[0] == images[1] == images[2]
    image = images[0]
    colors = [image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())]
    if checked:
        # A real white tick survives disabled rendering; fill alone is insufficient.
        assert colors.count('#ffffff') >= 8
        fill = (ThemeTokens_Get(theme).accent if enabled else
                ThemeTokens_Get(theme).border_strong if theme == 'dark' else ThemeTokens_Get(theme).muted)
        assert colors.count(fill.lower()) >= 40
    else:
        # The square boundary must be painted, even for unnamed/disabled controls.
        assert colors.count(ThemeTokens_Get(theme).muted.lower()) >= 40


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_hover_focus_and_click_semantics(qapp, theme):
    Theme_Apply(qapp, theme)
    box = QCheckBox('Include this target')
    box.resize(220, 40)
    box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    box.show()
    qapp.processEvents()
    # Explicit enter/leave events keep offscreen cursor position deterministic.
    qapp.sendEvent(box, QEvent(QEvent.Type.Leave))
    normal = _Indicator_Get(box)
    qapp.sendEvent(box, QEvent(QEvent.Type.Enter))
    qapp.processEvents()
    hovered = _Indicator_Get(box)
    assert hovered != normal
    box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    box.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    assert box.hasFocus() and _Indicator_Get(box) != hovered
    changes = []
    box.toggled.connect(changes.append)
    QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(75, 20))
    assert changes == [True]
    QTest.keyClick(box, Qt.Key.Key_Space)
    assert changes == [True, False]
    box.setEnabled(False)
    QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(75, 20))
    assert changes == [True, False]
    locked = LockedCheckBox('Required')
    locked.click()
    assert locked.isChecked()


def test_real_dual_target_defaults_and_independent_selections(qapp):
    page = BuildPage(Translator('en_US'))
    assert page.QualityTargets_Get() == ('flight',)
    page.quality_target_checks['ground'].click()
    assert page.QualityTargets_Get() == ('flight', 'ground')
    page.quality_target_checks['flight'].click()
    assert page.QualityTargets_Get() == ('ground',)
    page.quality_target_checks['ground'].click()
    assert page.QualityTargets_Get() == ()
