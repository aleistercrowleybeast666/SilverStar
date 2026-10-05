from __future__ import annotations

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QCheckBox, QLabel

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.alignment import (
    AlignmentConfiguration,
    AlignmentConstraint,
)
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.ui.pages.algorithm_parameters import NavigationConfigurationPage


VECTOR = "silverstar.algorithm.alignment.vector_constraints"
EXTERNAL = "silverstar.algorithm.alignment.external_attitude_source"


def test_navigation_sections_are_single_level_and_draft_is_cancelable(qapp) -> None:
    page = NavigationConfigurationPage(Translator("en_US"))
    changes: list[tuple[str, AlignmentConfiguration]] = []
    page.alignmentConfirmed.connect(lambda strategy, config: changes.append((strategy, config)))
    try:
        parameters = page.parameters_section
        headings = [label for label in page.findChildren(QLabel)
                    if label.property("navigationSectionKey")]
        assert [label.property("navigationSectionKey") for label in headings] == ["navigation.resource_timing"]
        assert parameters.toggle_button.text() == "Algorithm Parameters"
        assert not parameters.Expanded_Is()
        assert page.root_layout.indexOf(parameters) < page.root_layout.indexOf(headings[0].parentWidget())
        assert not any(label.text() == parameters.toggle_button.text() for label in page.findChildren(QLabel))
        original = AlignmentConfiguration(external_known_azimuth_deg=0.0)
        page.AlignmentConfiguration_Set(original, EXTERNAL,
            (DeviceInstance("imu0", "silverstar.device.imu.jy901b"),))
        editor = page.alignment_editor
        assert editor._azimuth.text() == "0.0"
        authority = next(child for child in editor.findChildren(QCheckBox)
                         if child.text() == "Yaw is absolute (verified nine-axis only)")
        authority.setChecked(True)
        assert not changes
        editor.DraftStrategy_Set(VECTOR)
        editor.cancel_button.click()
        assert editor.DraftStrategy_Get() == EXTERNAL
        assert editor._azimuth.text() == "0.0"
        assert not changes
        page.Language_Apply(Translator("zh_CN"))
        assert any(child.text() == "Yaw 具有绝对航向权威（仅已验证九轴）"
                   for child in editor.findChildren(QCheckBox))
    finally:
        page.close()
        qapp.processEvents()


def test_vector_editor_commits_only_after_confirm_and_reads_focused_text(qapp) -> None:
    page = NavigationConfigurationPage(Translator("en_US"))
    changes: list[tuple[str, AlignmentConfiguration]] = []
    page.alignmentConfirmed.connect(lambda strategy, config: changes.append((strategy, config)))
    original = AlignmentConfiguration(
        constraints=(AlignmentConstraint("gravity"),
                     AlignmentConstraint("reference_direction", nav_azimuth_deg=0.0)),
        external_source_instance="imu0",
        external_known_azimuth_deg=0.0,
    )
    try:
        page.AlignmentConfiguration_Set(original, VECTOR, ())
        editor = page.alignment_editor
        editor._rows[1]["weight"].setFocus()
        editor._rows[1]["weight"].selectAll()
        QTest.keyClicks(editor._rows[1]["weight"], "2.75")
        assert not changes
        editor.confirm_button.click()
        assert changes == [(VECTOR, AlignmentConfiguration(
            constraints=(AlignmentConstraint("gravity"),
                         AlignmentConstraint("reference_direction", weight=2.75,
                                             nav_azimuth_deg=0.0)),
            external_source_instance="imu0", external_known_azimuth_deg=0.0))]
        editor.Draft_Commit(changes[-1][1], VECTOR)
        editor._Row_Add()
        qapp.processEvents()
        assert len(editor._rows) == 3
        assert not changes[1:]
        editor._Row_Remove(2)
        qapp.processEvents()
        assert len(editor._rows) == 2
    finally:
        page.close()
        qapp.processEvents()


def test_vector_editor_enforces_bounded_rows_and_rejects_invalid_draft(qapp) -> None:
    page = NavigationConfigurationPage(Translator("en_US"))
    changes: list[tuple[str, AlignmentConfiguration]] = []
    page.alignmentConfirmed.connect(lambda strategy, config: changes.append((strategy, config)))
    try:
        page.AlignmentConfiguration_Set(AlignmentConfiguration(), VECTOR, ())
        editor = page.alignment_editor
        for expected in range(3, 7):
            editor._Row_Add()
            qapp.processEvents()
            assert len(editor._rows) == expected
        editor._Row_Add()
        qapp.processEvents()
        assert len(editor._rows) == 6
        for expected in range(5, 1, -1):
            editor._Row_Remove(len(editor._rows) - 1)
            qapp.processEvents()
            assert len(editor._rows) == expected
        editor._Row_Remove(1)
        qapp.processEvents()
        assert len(editor._rows) == 2

        editor._rows[1]["kind"].setCurrentIndex(0)  # Duplicate gravity.
        qapp.processEvents()
        editor.confirm_button.click()
        assert not changes
        assert "one gravity" in editor._notice.text()
        editor._rows[1]["kind"].setCurrentIndex(2)
        qapp.processEvents()
        editor._rows[1]["weight"].setText("inf")
        editor.confirm_button.click()
        assert not changes
        assert "Row 2" in editor._rows[1]["error"].text()
        editor.cancel_button.click()
        assert not editor.draft_dirty
        assert len(editor._rows) == 2
    finally:
        page.close()
        qapp.processEvents()


def test_external_source_is_checked_before_draft_commit(qapp) -> None:
    page = NavigationConfigurationPage(Translator("en_US"))
    changes: list[tuple[str, AlignmentConfiguration]] = []
    page.alignmentConfirmed.connect(lambda strategy, config: changes.append((strategy, config)))
    try:
        page.AlignmentConfiguration_Set(AlignmentConfiguration(), EXTERNAL, ())
        page.alignment_editor.confirm_button.click()
        assert not changes
        assert "JY901B" in page.alignment_editor._notice.text()
        page.alignment_editor.cancel_button.click()
        assert not changes
    finally:
        page.close()
        qapp.processEvents()

