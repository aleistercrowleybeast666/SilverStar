from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from silverstar_flp.analysis.measurement_diagnostics import (
    RecomputedMeasurementChannels_Build,
    RecordedMeasurementChannels_Build,
)


def _Record(name, payload):
    return SimpleNamespace(record_name=name, payload=payload,
                           timestamp_us=1_000_000, record_sequence=1)


def test_recorded_group_sigma_and_distinct_ages_from_exact_timestamps():
    payload = {
        "valid_group_mask": 15,
        "position_variance_m2": (4.0, 9.0, 16.0),
        "velocity_variance_m2ps2": (.25, .36, .49),
        "group_nis": (1.0, 8.0, 12.0, 30.0),
        "group_update_result": (0, 1, 1, 2),
        "receive_timestamp_us": 1_000_000,
        "position_measurement_timestamp_us": 995_000,
        "velocity_measurement_timestamp_us": 730_000,
        "estimator_present_timestamp_us": 1_003_000,
    }
    baro = {
        "valid_mask": 1, "variance_m2": 25.0, "nis": 1.0,
        "update_result": 0, "receive_timestamp_us": 1_000_000,
        "measurement_timestamp_us": 990_000,
        "estimator_present_timestamp_us": 1_003_000,
    }
    params = {"nis_1d_soft": 6.0, "nis_1d_hard": 20.0,
              "nis_2d_soft": 10.0, "nis_2d_hard": 25.0,
              "nis_max_r_scale": 4.0}
    channels = RecordedMeasurementChannels_Build({
        "GNSS_MEASUREMENT": (_Record("GNSS_MEASUREMENT", payload),),
        "BARO_MEASUREMENT": (_Record("BARO_MEASUREMENT", baro),),
    }, params)
    prefix = "kf6.recorded.measurement_"
    np.testing.assert_array_equal(
        channels[prefix + "input_variance.position_en"].values[0], (4.0, 9.0)
    )
    np.testing.assert_array_equal(
        channels[prefix + "input_variance.position_u"].values[0], (16.0,)
    )
    np.testing.assert_array_equal(
        channels[prefix + "effective_variance.position_u"].values[0],
        (16.0 * 8.0 / 6.0,)
    )
    np.testing.assert_array_equal(
        channels[prefix + "input_variance.velocity_en"].values[0], (.25, .36)
    )
    np.testing.assert_array_equal(
        channels[prefix + "effective_variance.velocity_en"].values[0],
        (.25 * 1.2, .36 * 1.2)
    )
    assert not channels[prefix + "effective_variance.velocity_u"].valid[0]
    assert channels[prefix + "receive_age.velocity_en"].values[0] == 3.0
    assert channels[prefix + "fixed_lag_latency.velocity_en"].values[0] == 273.0
    assert channels[prefix + "fixed_lag_latency.position_en"].values[0] == 8.0
    assert channels[prefix + "input_variance.baro"].values[0, 0] == 25.0


def test_recorded_effective_unavailable_without_complete_firmware_parameters():
    payload = {
        "valid_group_mask": 1, "position_variance_m2": (4.0, 9.0, 16.0),
        "velocity_variance_m2ps2": (.25, .36, .49),
        "group_nis": (1.0, 0.0, 0.0, 0.0),
        "group_update_result": (0, 3, 3, 3),
        "receive_timestamp_us": 1_000_000,
        "position_measurement_timestamp_us": 995_000,
        "velocity_measurement_timestamp_us": 730_000,
        "estimator_present_timestamp_us": 1_003_000,
    }
    channels = RecordedMeasurementChannels_Build({
        "GNSS_MEASUREMENT": (_Record("GNSS_MEASUREMENT", payload),),
    }, {})
    assert channels["kf6.recorded.measurement_input_variance.position_en"].valid[0]
    assert not channels["kf6.recorded.measurement_effective_variance.position_en"].valid[0]


def test_recomputed_channels_use_actual_application_event_not_snapshot_time():
    rows = ({
        "group": "velocity_en", "timestamp_us": 1_010_000,
        "receive_timestamp_us": 1_000_000,
        "resolved_measurement_timestamp_us": 730_000,
        "operation_sequence": 42, "valid": True,
        "input_variance": np.asarray((.25, .36)),
        "effective_variance": np.asarray((.5, .72)),
        "receive_age": 10.0, "fixed_lag_latency": 280.0,
        "r_scale": 2.0,
    },)
    channels = RecomputedMeasurementChannels_Build(rows)
    age = channels["kf6.measurement_receive_age.velocity_en"]
    latency = channels["kf6.measurement_fixed_lag_latency.velocity_en"]
    assert int(age.timestamp_us[0]) == 1_010_000
    assert age.values[0] == 10.0 and latency.values[0] == 280.0
    assert latency.unit == "ms" and age.unit == "ms"
