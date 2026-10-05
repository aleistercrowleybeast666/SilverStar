from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QVBoxLayout, QWidget

from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.committed_spin import (
    EnterCommittedDoubleSpinBox,
    EnterCommittedSpinBox,
)
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.pages.components import CadenceEditor


def _Window_Create(tmp_path: Path, qapp) -> MainWindow:
    window = MainWindow(SettingsStore(tmp_path / "enter-commit.ini"))
    window.show()
    qapp.processEvents()
    return window


def _TransactionCounts_Track(window: MainWindow, monkeypatch) -> dict[str, int]:
    counts = {"validation": 0, "display": 0}
    reconcile = window._service.ProjectConfiguration_Reconcile
    display = window._Project_Display

    def reconcile_count(*args, **kwargs):
        counts["validation"] += 1
        return reconcile(*args, **kwargs)

    def display_count(*args, **kwargs):
        counts["display"] += 1
        return display(*args, **kwargs)

    monkeypatch.setattr(window._service, "ProjectConfiguration_Reconcile", reconcile_count)
    monkeypatch.setattr(window, "_Project_Display", display_count)
    return counts


def _StreamRow_Get(window: MainWindow, record: str) -> int:
    return next(
        row for row, stream in enumerate(window.flight_configuration_page._streams)
        if stream.stream_id == record
    )


def test_numeric_drafts_invalid_enter_focus_loss_steps_and_wheel(qapp) -> None:
    container = QWidget()
    layout = QVBoxLayout(container)
    editor = EnterCommittedDoubleSpinBox()
    editor.setDecimals(3)
    editor.setRange(0.01, 180.0)
    editor.setSuffix(" °")
    editor.CommittedValue_Set(45.0)
    other = QPushButton("Other")
    layout.addWidget(editor)
    layout.addWidget(other)
    container.show()
    qapp.processEvents()
    commits = QSignalSpy(editor.committed)
    line_edit = editor.findChild(QLineEdit)
    assert line_edit is not None

    try:
        editor.setFocus()
        for draft in ("", "-", "0"):
            line_edit.setText(draft)
            assert editor.CommittedValue_Get() == 45.0
            QTest.keyClick(editor, Qt.Key.Key_Return)
            assert editor.CommittedValue_Get() == 45.0
            assert editor.value() == 45.0
            assert commits.count() == 0

        editor.selectAll()
        QTest.keyClicks(editor, "60")
        assert editor.CommittedValue_Get() == 45.0
        other.setFocus()
        qapp.processEvents()
        assert editor.value() == 45.0
        assert editor.text().startswith("45.000")

        editor.stepUp()
        assert editor.value() == 46.0
        assert editor.CommittedValue_Get() == 45.0
        assert commits.count() == 0

        wheel = QWheelEvent(
            QPointF(4, 4), QPointF(4, 4), QPoint(0, 0), QPoint(0, 120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate, False,
        )
        QApplication.sendEvent(editor, wheel)
        assert editor.value() == 46.0
        assert editor.CommittedValue_Get() == 45.0

        editor.setFocus()
        QTest.keyClick(editor, Qt.Key.Key_Return)
        assert editor.CommittedValue_Get() == 46.0
        assert commits.count() == 1

        integer_editor = EnterCommittedSpinBox()
        integer_editor.setRange(1, 65535)
        integer_editor.CommittedValue_Set(1)
        integer_commits = QSignalSpy(integer_editor.committed)
        integer_editor.setValue(3)
        assert integer_editor.CommittedValue_Get() == 1
        assert integer_commits.count() == 0
        QTest.keyClick(integer_editor, Qt.Key.Key_Return)
        assert integer_editor.CommittedValue_Get() == 3
        assert integer_commits.count() == 1
    finally:
        container.close()


def test_mode_parameter_enter_commits_once_and_dropdown_stays_immediate(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        window.pages.setCurrentWidget(window.flight_configuration_page)
        editor = window.flight_configuration_page.mode_parameter_spins[
            ("deployment", "Tilt", "tilt_threshold")
        ]
        assert isinstance(editor, EnterCommittedDoubleSpinBox)
        assert window._model.mode_parameters["deployment"]["Tilt"]["tilt_threshold"] == 45.0
        counts = _TransactionCounts_Track(window, monkeypatch)
        commits = QSignalSpy(editor.committed)
        editor.setFocus()
        editor.selectAll()
        for text in ("6", "0", ".5"):
            QTest.keyClicks(editor, text)
            qapp.processEvents()
            assert window._model.mode_parameters["deployment"]["Tilt"]["tilt_threshold"] == 45.0
            assert counts == {"validation": 0, "display": 0}
        QTest.keyClick(editor, Qt.Key.Key_Return)
        qapp.processEvents()
        assert window._model.mode_parameters["deployment"]["Tilt"]["tilt_threshold"] == 60.5
        assert commits.count() == 1
        assert counts == {"validation": 1, "display": 1}

        combo = window.flight_configuration_page.strategy_combos["estimator"]
        combo.setCurrentIndex(combo.findData(None))
        qapp.processEvents()
        assert window._model.strategies["estimator"] is None
        assert counts == {"validation": 2, "display": 2}
    finally:
        window.close()
        qapp.processEvents()


def test_algorithm_and_logging_numbers_commit_on_enter(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        counts = _TransactionCounts_Track(window, monkeypatch)
        editor = window.algorithm_parameters_page.editors[
            ("shared", "navigation.gravity_mps2")
        ]
        owner = "silverstar.algorithm.ins.coning2_sculling2"
        editor.setValue(9.81)
        qapp.processEvents()
        assert window._model.algorithm_parameters[owner]["gravity_mps2"] == 9.78
        assert counts == {"validation": 0, "display": 0}
        QTest.keyClick(editor, Qt.Key.Key_Return)
        qapp.processEvents()
        assert window._model.algorithm_parameters[owner]["gravity_mps2"] == 9.81
        assert counts == {"validation": 1, "display": 1}

        page = window.flight_configuration_page
        row = _StreamRow_Get(window, "FLIGHT_LOG_RECORD_MAG_NATIVE")
        decimation = page.logging_table.cellWidget(row, 4)
        assert isinstance(decimation, EnterCommittedSpinBox)
        old_decimation = int(decimation.CommittedValue_Get())
        decimation.setValue(old_decimation + 2)
        assert page.Streams_Get()[row].decimation == old_decimation
        assert counts == {"validation": 1, "display": 1}
        # The current official MAG stream is unavailable, but its draft must
        # never be swept into another logging transaction.
        assert not decimation.isEnabled()

        row = _StreamRow_Get(window, "FLIGHT_LOG_RECORD_STATS")
        cadence = page.logging_table.cellWidget(row, 5)
        assert isinstance(cadence, CadenceEditor)
        cadence.unit_combo.setCurrentIndex(cadence.unit_combo.findData("ms"))
        cadence.value_spin.setValue(500)
        assert page.Streams_Get()[row].period_us == 1_000_000
        assert counts == {"validation": 1, "display": 1}
        QTest.keyClick(cadence.value_spin, Qt.Key.Key_Return)
        qapp.processEvents()
        assert next(stream.period_us for stream in window._model.logging_streams
                    if stream.record == "FLIGHT_LOG_RECORD_STATS") == 500_000
        assert counts == {"validation": 2, "display": 2}
        assert next(stream.decimation for stream in window._model.logging_streams
                    if stream.record == "FLIGHT_LOG_RECORD_MAG_NATIVE") == old_decimation
    finally:
        window.close()
        qapp.processEvents()


def test_available_decimation_emits_once_only_after_enter(
    tmp_path: Path, qapp
) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        page = window.flight_configuration_page
        page.loggingChanged.disconnect()
        row = _StreamRow_Get(window, "FLIGHT_LOG_RECORD_MAG_NATIVE")
        page.Streams_Set(
            replace(stream, available=True) if index == row else stream
            for index, stream in enumerate(page._streams)
        )
        decimation = page.logging_table.cellWidget(row, 4)
        assert isinstance(decimation, EnterCommittedSpinBox)
        assert decimation.isEnabled()
        changed = QSignalSpy(page.loggingChanged)
        previous = int(decimation.CommittedValue_Get())
        decimation.setValue(previous + 2)
        assert page.Streams_Get()[row].decimation == previous
        assert changed.count() == 0
        QTest.keyClick(decimation, Qt.Key.Key_Return)
        qapp.processEvents()
        assert page.Streams_Get()[row].decimation == previous + 2
        assert changed.count() == 1
    finally:
        window.close()
        qapp.processEvents()
