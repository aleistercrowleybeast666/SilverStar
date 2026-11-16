"""Real Qt message boxes retain buttons/results and fit the owning screen."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QRect, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget
from shiboken6 import isValid

from ui.message_box_placement import (
    FramePosition_Get, MessageBoxPlacement, MessageBox_Show, MessageBox_Watch,
)


@pytest.mark.parametrize("available,parent,frame,expected", [
    (QRect(0, 0, 1280, 720), QRect(200, 100, 800, 500), QRect(0, 0, 300, 180), (449, 259)),
    (QRect(-1280, 0, 1280, 720), QRect(-1100, 100, 800, 500), QRect(0, 0, 300, 180), (-850, 259)),
    (QRect(0, -900, 1440, 900), QRect(1000, -200, 800, 500), QRect(0, 0, 300, 180), (1140, -180)),
    (QRect(-1280, 0, 1280, 720), QRect(-1500, -200, 400, 300), QRect(0, 0, 300, 180), (-1280, 0)),
    (QRect(0, 0, 800, 600), QRect(0, 0, 800, 600), QRect(0, 0, 900, 700), (0, 0)),
])
def test_logical_position_clamps_all_screen_edges(available, parent, frame, expected):
    position = FramePosition_Get(frame, parent, available)
    assert (position.x(), position.y()) == expected


@pytest.mark.parametrize("text", ["Discard changes?", "是否放弃尚未保存的修改？"])
@pytest.mark.parametrize("nested", [False, True])
def test_owned_question_centered_without_changing_default_or_cancel(qtbot, text, nested):
    owner = QWidget()
    qtbot.addWidget(owner)
    owner.resize(500, 350)
    owner.move(80, 60)
    owner.show()
    parent = QDialog(owner) if nested else owner
    if nested:
        parent.resize(320, 220)
        parent.move(250, 150)
        parent.show()
    dialog = QMessageBox(QMessageBox.Warning, "Confirm", text,
                         QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, parent)
    dialog.setDefaultButton(QMessageBox.Save)
    placement = MessageBox_Watch(dialog)
    assert MessageBox_Watch(dialog) is placement
    dialog.move(0, 0)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.pos() == FramePosition_Get(
        dialog.frameGeometry(), parent.frameGeometry(), parent.screen().availableGeometry()))
    assert dialog.defaultButton() is dialog.button(QMessageBox.Save)
    assert dialog.standardButtons() == QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
    qtbot.keyClick(dialog, Qt.Key_Escape)
    assert dialog.result() == QMessageBox.Cancel
    assert not dialog.isVisible()
    assert isValid(placement)


def test_unrelated_window_and_pending_deleted_box_are_untouched(qtbot, qapp):
    owner, other = QWidget(), QWidget()
    qtbot.addWidget(owner)
    qtbot.addWidget(other)
    owner.show()
    other.show()
    unrelated = QMessageBox(other)
    unrelated.setText("Other application window")
    unrelated.move(17, 23)
    unrelated.show()
    saved = unrelated.pos()
    qapp.processEvents()
    assert unrelated.pos() == saved
    doomed = QMessageBox(owner)
    placement = MessageBox_Watch(doomed)
    doomed.setAttribute(Qt.WA_DeleteOnClose, True)
    doomed.show()
    doomed.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not isValid(doomed)
    qapp.processEvents()  # receiver-bound correction must not access a destroyed wrapper
    assert not isValid(placement)
    unrelated.close()


@pytest.mark.parametrize('text', ['Discard changes?', '是否放弃尚未保存的修改？'])
def test_real_static_warning_keeps_default_cancel_and_parent(qtbot, qapp, text):
    owner = QWidget()
    qtbot.addWidget(owner)
    owner.resize(500, 350)
    owner.move(80, 60)
    owner.show()
    observed = []
    def choose():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox) and dialog.parentWidget() is owner
        assert dialog.pos() == FramePosition_Get(dialog.frameGeometry(), owner.frameGeometry(),
                                                 owner.screen().availableGeometry())
        assert dialog.defaultButton() is dialog.button(QMessageBox.Save)
        observed.append(dialog)
        qtbot.keyClick(dialog, Qt.Key_Escape)
    QTimer.singleShot(50, choose)
    result = MessageBox_Show(QMessageBox.warning, owner, 'Confirm', text,
                             QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                             QMessageBox.Save)
    assert result == QMessageBox.Cancel and len(observed) == 1
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not qapp.findChildren(MessageBoxPlacement)


@pytest.mark.parametrize('failure', [False, True])
def test_modal_observer_is_scoped_even_when_original_operation_raises(qtbot, qapp, failure):
    owner = QWidget()
    qtbot.addWidget(owner)
    def operation(parent, title, *, sentinel):
        assert parent is owner and title == 'original' and sentinel == 42
        assert len(qapp.findChildren(MessageBoxPlacement)) == 1
        if failure:
            raise ValueError('original Qt operation error')
        return QMessageBox.No
    if failure:
        with pytest.raises(ValueError, match='original Qt operation error'):
            MessageBox_Show(operation, owner, 'original', sentinel=42)
    else:
        assert MessageBox_Show(operation, owner, 'original', sentinel=42) == QMessageBox.No
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not qapp.findChildren(MessageBoxPlacement)

