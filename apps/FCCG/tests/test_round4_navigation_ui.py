from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QGroupBox
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.alignment import (
    AlignmentConfiguration,
    AlignmentConstraint,
)
from silverstar_fccg.ui.pages.algorithm_parameters import NavigationConfigurationPage


def test_navigation_page_has_owned_sections_and_preserves_zero_azimuth(qapp) -> None:
    page = NavigationConfigurationPage(Translator("en_US"))
    changes: list[AlignmentConfiguration] = []
    page.alignmentChanged.connect(changes.append)
    try:
        sections = [
            section.property("navigationSectionKey")
            for section in page.findChildren(QGroupBox)
            if section.property("navigationSectionKey")
        ]
        assert sections == [
            "navigation.sources",
            "navigation.calibration",
            "navigation.initial_alignment",
            "navigation.ins",
            "navigation.estimator",
            "navigation.parameters",
            "navigation.resource_timing",
        ]
        page.AlignmentConfiguration_Set(
            AlignmentConfiguration(
                external_known_azimuth_deg=0.0,
            ),
            "silverstar.algorithm.alignment.external_attitude_source",
            (),
        )
        authority = next(
            child for child in page.alignment_editor.findChildren(QCheckBox)
            if child.text() == "Yaw is absolute (verified nine-axis only)"
        )
        authority.setChecked(True)
        assert changes[-1].external_known_azimuth_deg == 0.0
        page.AlignmentConfiguration_Set(
            changes[-1],
            "silverstar.algorithm.alignment.external_attitude_source",
            (),
        )
        authority = next(
            child for child in page.alignment_editor.findChildren(QCheckBox)
            if child.text() == "Yaw is absolute (verified nine-axis only)"
        )
        authority.setChecked(False)
        assert changes[-1].external_known_azimuth_deg == 0.0
        translated = Translator("zh_CN")
        page.Language_Apply(translated)
        assert any(
            child.text() == translated.Text_Get("alignment.yaw_authoritative")
            for child in page.alignment_editor.findChildren(QCheckBox)
        )
    finally:
        page.close()
        qapp.processEvents()


def test_vector_editor_commits_constraint_without_discarding_common_fields(qapp) -> None:
    page = NavigationConfigurationPage(Translator("en_US"))
    changes: list[AlignmentConfiguration] = []
    page.alignmentChanged.connect(changes.append)
    original = AlignmentConfiguration(
        constraints=(
            AlignmentConstraint("gravity"),
            AlignmentConstraint("reference_direction", nav_azimuth_deg=0.0),
        ),
        external_source_instance="imu0",
        external_known_azimuth_deg=0.0,
    )
    try:
        page.AlignmentConfiguration_Set(
            original, "silverstar.algorithm.alignment.vector_constraints", (),
        )
        add = next(
            child for child in page.alignment_editor.findChildren(QCheckBox)
            if child.text() == "Use magnetic constraint"
        )
        add.setChecked(True)
        assert len(changes) == 1
        assert changes[0].constraints[1].kind == "magnetic_field"
        assert changes[0].external_source_instance == "imu0"
        assert changes[0].external_known_azimuth_deg == 0.0
    finally:
        page.close()
        qapp.processEvents()
