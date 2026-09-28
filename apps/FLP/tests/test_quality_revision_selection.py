from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.analysis.navigation_revision3 import (
    QualitySchedule_Apply,
    Revision3Health_Build,
)
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.project import ReplayConfiguration_Validate
from silverstar_flp.plugins.algorithms.kf6.plugin import _ScheduledMeasurement
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.replay import ReplayPage
from tests.synthetic_parameter_navigation import NavigationPair_Open
from tests.test_gnss_integrity import Dataset_Build


def test_policy_revision_gui_request_and_saved_configuration(qtbot, tmp_path):
    dataset = NavigationPair_Open(tmp_path / "input").dataset
    registry = builtin_registry()
    page = ReplayPage(Translator("en_US"), registry)
    qtbot.addWidget(page)
    page.Dataset_Set(dataset)
    page.algorithm_combo.setCurrentIndex(page.algorithm_combo.findData("silverstar.algorithm.kf6"))
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.WHAT_IF))
    page.quality_policy_combo.setCurrentIndex(page.quality_policy_combo.findData(3))
    assert page._Request_Get().quality_policy_revision == 3
    assert page._parameter_widgets["gnss_integrity_recovery_threshold_m"].isReadOnly()
    assert not page._parameter_widgets["gnss_integrity_max_gap_ms"].isReadOnly()
    saved = page.Configuration_Get()
    ReplayConfiguration_Validate(saved)
    assert saved["quality_policy_revision"] == 3
    page.Language_Apply(Translator("zh_CN"))
    assert page.quality_policy_combo.currentData() == 3
    assert "新策略" in page.quality_policy_combo.currentText()
    page.quality_policy_combo.setCurrentIndex(0)
    assert not page._parameter_widgets["gnss_integrity_recovery_threshold_m"].isReadOnly()
    page.Configuration_Set(saved)
    assert page._Request_Get().quality_policy_revision == 3
    invalid = {**saved, "mode": ReplayMode.RECORDED_CONFIGURATION.value}
    with pytest.raises(ValueError, match="quality_policy_revision_invalid"):
        ReplayConfiguration_Validate(invalid)
    with pytest.raises(ValueError, match="quality_policy_override_requires_what_if"):
        ReplayRequest(quality_policy_revision=3)


def test_revision3_actual_parameter_bound_and_retired_override(tmp_path):
    dataset = NavigationPair_Open(tmp_path / "input").dataset
    plugin = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    runtime = plugin.RuntimeParameterSchema_Get(dataset, 3)
    assert len(runtime) == 30
    assert len(plugin.RuntimeParameterSchema_Get(dataset, 2)) == 36
    with pytest.raises(ValueError, match="parameter_retired_revision3"):
        plugin._Parameters_Resolve(
            dataset,
            ReplayRequest(
                mode=ReplayMode.WHAT_IF,
                quality_policy_revision=3,
                parameters={"gnss_integrity_recovery_threshold_m": 3.0},
            ),
        )
    with pytest.raises(ValueError, match="parameter_out_of_range"):
        plugin._Parameters_Resolve(
            dataset,
            ReplayRequest(
                mode=ReplayMode.WHAT_IF,
                quality_policy_revision=3,
                parameters={"gnss_integrity_position_r_scale": 5.0},
            ),
        )


def test_revision3_recovers_physical_mask_and_preserves_origin_variance():
    dataset = Dataset_Build()
    initial = replace(
        dataset.initial_state,
        payload={**dataset.initial_state.payload, "gnss_origin_position_std_m": (2.0, 3.0, 4.0)},
    )
    native = replace(
        dataset.Records_Get("GNSS_NATIVE")[1],
        payload={
            **dataset.Records_Get("GNSS_NATIVE")[1].payload,
            "supported_fields": 1023,
            "valid_fields": 1023,
            "fix_type": 3,
            "fix_ok": 1,
            "online": 1,
            "receive_timestamp_us": 40_000,
            "satellite_count": 4,
        },
    )
    dataset = replace(dataset, records={"INITIAL_STATE": (initial,), "GNSS_NATIVE": (native,)})
    measurement = replace(
        native,
        record_name="GNSS_MEASUREMENT",
        payload={
            "sequence": 1,
            "receive_timestamp_us": 40_000,
            "valid_group_mask": 0,
            "position_variance_m2": (99, 99, 99),
            "velocity_variance_m2ps2": (99, 99, 99),
        },
    )
    schedule = (_ScheduledMeasurement(40_000, 1, "gnss", measurement, False),)
    parameters = (
        builtin_registry().Algorithm_Get("silverstar.algorithm.kf6").OfflineParameters_Get()
    )
    actual, diagnostics = QualitySchedule_Apply(dataset, schedule, parameters)
    payload = actual[0].record.payload
    assert payload["valid_group_mask"] == 15
    np.testing.assert_allclose(
        payload["position_variance_m2"][:2],
        (np.maximum(1.25, parameters["gnss_position_std_horizontal"]) ** 2 + np.array([4, 9])) * 3,
    )
    assert diagnostics["revision"] == 3
    assert measurement.payload["valid_group_mask"] == 0
    quality = replace(
        native,
        record_name="NAV_QUALITY",
        payload={
            "native_sequence": 1,
            "receive_us": 40_000,
            "native_epoch_us": 40_000,
            "evaluation_us": 40_000,
            "calibration_generation": 3,
            "source_id": 7,
        },
    )
    with_source = replace(dataset, records={**dataset.records, "NAV_QUALITY": (quality,)})
    actual, _ = QualitySchedule_Apply(with_source, schedule, parameters)
    assert actual[0].record.payload["_quality_source_id"] == 7


def test_revision3_known_source_switch_does_not_deduplicate_equal_receive_time():
    updates = [
        dict(group="Pos EN", timestamp_us=t, result=0, valid=True, nis=0.1, source_id=source)
        for t, source in ((1_100_000, 1), (1_200_000, 2))
    ]
    events = [
        dict(group="position_en", timestamp_us=t, receive_timestamp_us=1_050_000)
        for t in (1_100_000, 1_200_000)
    ]
    _, facts = Revision3Health_Build([1_100_000, 1_200_000], updates, events, 1_000_000)
    assert facts["fusion_groups"][0]["accepted"] == 2
    assert facts["fusion_groups"][0]["last_source"] == 2


def test_revision3_window_actual_threshold_cap_and_gap_are_consumed():
    dataset = Dataset_Build(position_e_rate=3.0, velocity_e=0.0)
    initial = replace(
        dataset.initial_state,
        payload={**dataset.initial_state.payload, "gnss_origin_position_std_m": (0.0, 0.0, 0.0)},
    )
    native = tuple(
        replace(
            r,
            payload={
                **r.payload,
                "supported_fields": 1023,
                "valid_fields": 1023,
                "fix_type": 3,
                "fix_ok": 1,
                "online": 1,
                "receive_timestamp_us": r.timestamp_us,
            },
        )
        for r in dataset.Records_Get("GNSS_NATIVE")
    )
    dataset = replace(
        dataset, records={**dataset.records, "INITIAL_STATE": (initial,), "GNSS_NATIVE": native}
    )
    defaults = dict(
        builtin_registry().Algorithm_Get("silverstar.algorithm.kf6").OfflineParameters_Get()
    )
    _, first = QualitySchedule_Apply(dataset, (), defaults)
    _, limited = QualitySchedule_Apply(
        dataset, (), {**defaults, "gnss_integrity_position_r_scale": 2.0}
    )
    _, threshold = QualitySchedule_Apply(
        dataset, (), {**defaults, "gnss_integrity_error_threshold_m": 100.0}
    )
    assert first["window_evidence"][-1]["variance_scale"] == 4.0
    assert limited["window_evidence"][-1]["variance_scale"] == 2.0
    assert threshold["window_evidence"][-1]["variance_scale"] == 1.0
    slow_receiver = tuple(
        replace(row, payload={**row.payload, "sequence": index})
        for index, row in enumerate(native[::4])
    )
    sparse = replace(dataset, records={**dataset.records, "GNSS_NATIVE": slow_receiver})
    _, broken = QualitySchedule_Apply(sparse, (), defaults)
    _, covered = QualitySchedule_Apply(sparse, (), {**defaults, "gnss_integrity_max_gap_ms": 200})
    assert not broken["window_evidence"]
    assert covered["window_evidence"][-1]["valid"]


def test_revision3_outer_health_timeout_and_kf_not_attempted_enum():
    updates = [
        {"group": name, "timestamp_us": 1_100_000, "result": 0, "valid": True, "nis": 0.1}
        for name in ("Pos EN", "Pos U", "Vel EN", "Vel U")
    ]
    health, diagnostics = Revision3Health_Build(
        [1_100_000, 3_100_000, 11_100_000], updates, [], 1_000_000
    )
    assert health.values.tolist() == [1, 3, 4]
    assert diagnostics["fusion_groups"][0]["accepted"] == 1
    updates[0]["result"] = 5
    health, _ = Revision3Health_Build([1_100_000], updates, [], 1_000_000)
    assert health.values.tolist() == [0]
