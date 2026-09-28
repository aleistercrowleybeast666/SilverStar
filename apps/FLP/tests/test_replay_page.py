from __future__ import annotations

import math
import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFormLayout

from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import (
    ReplayFidelity,
    ReplayMode,
    ReplayRequest,
)
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.replay import ReplayPage
from tests.sslog_synthetic import AnalysisFlight_Build, StationaryFlight_Build

WARNING_CODES = (
    "firmware_build_differs_from_reimplementation",
    "source_log_has_integrity_or_sequence_gaps",
    "system_config_missing_current_firmware_bounds_used",
    "measurement_application_time_inferred",
    "kf6_state_timing_reference_is_decimated",
)


def test_replay_uses_fixed_corrected_imu_and_translates_every_visible_field(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        StationaryFlight_Build(tmp_path / "SYNTHETIC_replay_page.BIN")
    )
    page = ReplayPage(Translator("en_US"), builtin_registry())
    page.Dataset_Set(dataset, ReplayResultStore())
    page.show()
    application.processEvents()

    assert (
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ).input_source
        == "corrected_imu"
    )
    assert not hasattr(page, "source_combo")
    assert page.analysis_source_combo.count() == 1
    assert page.analysis_source_combo.itemData(0) == ReplayResultStore.RECORDED_SOURCE_ID
    assert page.analysis_source_combo.itemText(0) == "Recorded (flight controller) · Pure INS"

    requested: list[ReplayRequest] = []
    page.replayRequested.connect(lambda _algorithm_id, request: requested.append(request))
    page._Replay_Request()
    assert requested[-1].input_source == "corrected_imu"

    assert page.Fidelity_Text_Get(ReplayFidelity.EXACT) == "Exact"
    assert page.Fidelity_Text_Get(ReplayFidelity.APPROXIMATE) == "Approximate"
    assert page.Fidelity_Text_Get(ReplayFidelity.UNAVAILABLE) == "Unavailable"
    for code in WARNING_CODES:
        assert page._Warning_Text_Get(code) != code
        assert code not in page._Warning_Text_Get(code)

    kf6_index = page.algorithm_combo.findData("silverstar.algorithm.kf6")
    assert kf6_index >= 0
    page.algorithm_combo.setCurrentIndex(kf6_index)
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.WHAT_IF))
    page.Language_Apply(Translator("zh_CN"))
    application.processEvents()
    assert page.parameters_group.title() == "假设参数"
    assert page.Fidelity_Text_Get(ReplayFidelity.EXACT) == "完整复现"
    assert page.Fidelity_Text_Get(ReplayFidelity.UNAVAILABLE) == "不可复算"
    assert len(page._parameter_labels) == 36
    assert page.parameter_group_combo.count() == 5
    assert page.parameter_group_combo.currentText() == "过程模型"
    assert page.parameters_form.rowCount() == 4
    assert page._parameter_labels["process_accel_std_e"].text() == ("过程加速度标准差 E")
    for parameter_id, label in page._parameter_labels.items():
        assert label.text() != parameter_id
        assert parameter_id in label.toolTip()
    for code in WARNING_CODES:
        translated = page._Warning_Text_Get(code)
        assert translated != code
        assert code not in translated
    page.close()


def test_what_if_groups_dirty_and_reset_use_recorded_configuration(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    recorded_process = (2.25, 3.5, 4.75)
    recorded_nis = (5.5, 9.5, 8.5, 12.5, 10.5, 15.5, 7.0)
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_recorded_parameters.BIN",
            process_accel_std_mps2=recorded_process,
            nis_profile=recorded_nis,
        )
    )
    from tests.parameter_fixtures import SyntheticParameters_Attach

    overrides = {
        f"process_accel_std_{axis}": value
        for axis, value in zip("enu", recorded_process, strict=True)
    }
    if "recorded_nis" in locals():
        overrides.update(
            dict(
                zip(
                    (
                        "nis_1d_soft",
                        "nis_1d_hard",
                        "nis_2d_soft",
                        "nis_2d_hard",
                        "nis_3d_soft",
                        "nis_3d_hard",
                        "nis_max_r_scale",
                    ),
                    recorded_nis,
                    strict=True,
                )
            )
        )
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "params", {"kf6": overrides})
    page = ReplayPage(Translator("en_US"), builtin_registry())
    page.Dataset_Set(dataset, ReplayResultStore())
    page.algorithm_combo.setCurrentIndex(page.algorithm_combo.findData("silverstar.algorithm.kf6"))
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.WHAT_IF))
    page.show()
    application.processEvents()

    assert [
        page.parameter_group_combo.itemText(index)
        for index in range(page.parameter_group_combo.count())
    ] == [
        "Process Model",
        "Initial Covariance",
        "Measurement Noise",
        "Consistency Gating",
        "GNSS Position Self-Check",
    ]
    assert page.parameters_form.rowCount() == 4
    for axis, expected in zip("enu", recorded_process, strict=True):
        assert math.isclose(
            page._parameter_widgets[f"process_accel_std_{axis}"].value(),
            expected,
        )
    assert "prediction squares sigma" in page._parameter_labels["process_accel_std_e"].toolTip()

    measurement_index = page.parameter_group_combo.findData("parameter_group.measurement_noise")
    page.parameter_group_combo.setCurrentIndex(measurement_index)
    application.processEvents()
    assert page.parameters_form.rowCount() == 8
    assert "Actual sigma floor" in page._parameter_labels["gnss_position_std_horizontal"].toolTip()

    page._parameter_widgets["process_accel_std_e"].setValue(8.25)
    page._parameter_widgets["nis_1d_soft"].setValue(4.25)
    application.processEvents()
    assert page.parameter_modified_label.isVisible()
    assert page.parameter_modified_label.text() == "Modified"

    page.parameter_reset_button.click()
    application.processEvents()
    assert math.isclose(
        page._parameter_widgets["process_accel_std_e"].value(),
        recorded_process[0],
    )
    assert math.isclose(
        page._parameter_widgets["nis_1d_soft"].value(),
        recorded_nis[0],
    )
    assert not page.parameter_modified_label.isVisible()
    page.close()


def test_what_if_group_switch_removes_residual_rows_and_preserves_values(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    recorded_process = (2.25, 3.5, 4.75)
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_parameter_group_switch.BIN",
            process_accel_std_mps2=recorded_process,
        )
    )
    from tests.parameter_fixtures import SyntheticParameters_Attach

    overrides = {
        f"process_accel_std_{axis}": value
        for axis, value in zip("enu", recorded_process, strict=True)
    }
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "params", {"kf6": overrides})
    page = ReplayPage(Translator("en_US"), builtin_registry())
    page.Dataset_Set(dataset, ReplayResultStore())
    page.algorithm_combo.setCurrentIndex(page.algorithm_combo.findData("silverstar.algorithm.kf6"))
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.WHAT_IF))
    page.show()
    application.processEvents()

    edited_values = {
        "process_accel_std_e": 1.8,
        "process_accel_std_n": 1.7,
        "process_accel_std_u": 2.3,
    }
    for parameter_id, value in edited_values.items():
        page._parameter_widgets[parameter_id].setValue(value)

    group_keys = tuple(
        page.parameter_group_combo.itemData(index)
        for index in range(page.parameter_group_combo.count())
    )
    expected_ids = {
        group_key: tuple(
            parameter_id
            for parameter_id, spec in page._parameter_specs.items()
            if (spec.group_key or "parameter_group.general") == group_key
        )
        for group_key in group_keys
    }
    for _ in range(20):
        for group_key in group_keys:
            page.parameter_group_combo.setCurrentIndex(
                page.parameter_group_combo.findData(group_key)
            )
            application.processEvents()
            visible_ids = expected_ids[group_key]
            assert page.parameters_form.rowCount() == len(visible_ids)
            attached_widgets = []
            for row, parameter_id in enumerate(visible_ids):
                label = page._parameter_labels[parameter_id]
                editor = page._parameter_widgets[parameter_id]
                assert (
                    page.parameters_form.itemAt(
                        row,
                        QFormLayout.ItemRole.LabelRole,
                    ).widget()
                    is label
                )
                assert (
                    page.parameters_form.itemAt(
                        row,
                        QFormLayout.ItemRole.FieldRole,
                    ).widget()
                    is editor
                )
                assert label.isVisible()
                assert editor.isVisible()
                attached_widgets.extend((label, editor))
            assert len(attached_widgets) == len({id(widget) for widget in attached_widgets})
            hidden_ids = set(page._parameter_specs) - set(visible_ids)
            for parameter_id in hidden_ids:
                label = page._parameter_labels[parameter_id]
                editor = page._parameter_widgets[parameter_id]
                assert page.parameters_form.indexOf(label) == -1
                assert page.parameters_form.indexOf(editor) == -1
                assert not label.isVisible()
                assert not editor.isVisible()

    for parameter_id, value in edited_values.items():
        assert math.isclose(page._parameter_widgets[parameter_id].value(), value)
    assert page.parameter_modified_label.isVisible()
    page.parameter_reset_button.click()
    application.processEvents()
    for axis, expected in zip("enu", recorded_process, strict=True):
        assert math.isclose(
            page._parameter_widgets[f"process_accel_std_{axis}"].value(),
            expected,
        )
    assert not page.parameter_modified_label.isVisible()
    page.close()


def test_replay_is_the_only_global_source_selector_and_can_return_to_recorded(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        StationaryFlight_Build(tmp_path / "SYNTHETIC_replay_sources.BIN")
    )
    result = PureInsAlgorithmPlugin().run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ),
    )
    warned_result = replace(
        result,
        warnings=("firmware_build_differs_from_reimplementation",),
    )
    store = ReplayResultStore()
    ready = store.Result_Add(warned_result, algorithm_name="Pure INS")
    unavailable = store.Result_Add(
        replace(result, fidelity=ReplayFidelity.UNAVAILABLE),
        algorithm_name="Pure INS",
    )

    page = ReplayPage(Translator("en_US"), builtin_registry())
    page.Dataset_Set(dataset, store)
    page.Result_Set(ready)
    page.show()
    application.processEvents()

    assert ready.analysis_ready
    assert not unavailable.analysis_ready
    assert page.analysis_source_combo.count() == 2
    assert page.analysis_source_combo.itemData(0) == ReplayResultStore.RECORDED_SOURCE_ID
    ready_index = page.analysis_source_combo.findData(ready.source_id)
    assert ready_index == 1
    assert page.analysis_source_combo.findData(unavailable.source_id) == -1
    assert page.result_information_label.toolTip() == "firmware_build_differs_from_reimplementation"
    assert "differs from" in page.result_information_label.text()

    selected: list[str] = []
    page.analysisSourceRequested.connect(selected.append)
    page.analysis_source_combo.setCurrentIndex(ready_index)
    application.processEvents()
    assert store.ActiveSource_Get().source_id == ready.source_id
    assert selected[-1] == ready.source_id
    page.analysis_source_combo.setCurrentIndex(0)
    application.processEvents()
    assert store.ActiveSource_Get().source_id == ReplayResultStore.RECORDED_SOURCE_ID
    assert selected[-1] == ReplayResultStore.RECORDED_SOURCE_ID

    page.Language_Apply(Translator("zh_CN"))
    assert page.analysis_source_combo.itemText(0) == "飞控记录 · Pure INS"
    assert "固件构建版本" in page.result_information_label.text()
    page.close()
