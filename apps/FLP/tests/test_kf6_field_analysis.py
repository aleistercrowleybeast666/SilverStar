import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.plugins.algorithms.kf6.field_analysis import (
    FieldSweep_Run,
    LatencySweep_Run,
    VelocitySchedule_Shift,
)
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin, _ScheduledMeasurement
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayRequest
from tests.synthetic_parameter_navigation import NavigationPair_Open, SyntheticOperations_Attach


def Measurement_Create(timestamp, sequence, velocity):
    payload = {
        "sample_timestamp_us": timestamp,
        "receive_timestamp_us": timestamp,
        "sequence": sequence,
        "fusion_allowed": 1,
        "position_usable": 0,
        "position_enu_m": (0, 0, 0),
        "position_variance_m2": (1, 1, 1),
        "velocity_enu_mps": tuple(velocity),
        "velocity_variance_m2ps2": (0.01, 0.01, 0.01),
        "velocity_valid_mask": 7,
    }
    return DecodedRecord(0x1E, "GNSS_MEASUREMENT", 0, 0, sequence, timestamp, 2, payload, 0)


def test_shift_preserves_position_inputs_and_never_bridges_outage():
    records = [Measurement_Create(1000000 + i * 40000, i, (i, i, i)) for i in range(80)]
    schedule = tuple(
        _ScheduledMeasurement(r.timestamp_us, r.record_sequence, "gnss", r, True) for r in records
    )
    shifted = VelocitySchedule_Shift(schedule, 40)
    assert shifted[30].record.payload["velocity_enu_mps"] == (29, 29, 29)
    assert shifted[30].record.payload["position_enu_m"] == records[30].payload["position_enu_m"]
    assert shifted[30].record.timestamp_us == records[30].timestamp_us
    assert records[30].payload["velocity_enu_mps"] == (30, 30, 30)
    assert shifted[0].record.valid_flags & 2 == 0
    gap = schedule[:30] + schedule[40:]
    shifted_gap = VelocitySchedule_Shift(gap, 100)
    assert shifted_gap[30].record.valid_flags & 2 == 0
    with pytest.raises(ValueError):
        VelocitySchedule_Shift(schedule, 501)


def test_actual_replay_latency_scan_and_missing_native_sweep_are_explicit(tmp_path):
    opened = NavigationPair_Open(tmp_path / "pair", flight_samples=401)
    dataset = opened.dataset
    before = hashlib.sha256(dataset.source_path.read_bytes()).hexdigest()
    pure = PureInsAlgorithmPlugin().run(dataset, ReplayRequest())
    velocity = pure.channels["navigation.velocity_enu"]
    times = velocity.timestamp_us.astype(np.int64)
    records = []
    for index, timestamp in enumerate(times[::4]):
        # A synthetic +80 ms velocity latency, with a real replay as its known reference.
        delayed = [
            np.interp(timestamp - 80000, times, velocity.values[:, axis]) for axis in range(3)
        ]
        records.append(Measurement_Create(int(timestamp), index + 1, delayed))
    dataset = replace(
        dataset,
        records={**dataset.records, "GNSS_MEASUREMENT": tuple(records), "BARO_MEASUREMENT": ()},
    )
    dataset = SyntheticOperations_Attach(dataset)
    report = LatencySweep_Run(dataset, ReplayRequest())
    (tmp_path / "latency_synthetic.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert set(range(-500, 501, 20)) <= {run["shift_ms"] for run in report["runs"]}
    assert len(report["runs"]) > 51
    assert report["best_shift_ms"] <= 0
    assert report["firmware_compensation_authorized"] is False
    baseline = Kf6AlgorithmPlugin().run(dataset, ReplayRequest())
    assert (
        report["runs"][0]["final_velocity_mps"]
        != baseline.channels["navigation.velocity_enu"].values[-1].tolist()
    )
    assert hashlib.sha256(dataset.source_path.read_bytes()).hexdigest() == before
    dataset = SyntheticOperations_Attach(dataset)
    field = FieldSweep_Run(dataset, include_latency=False)
    assert any("unavailable" in item for item in field["sweeps"]["gnss_velocity_vertical_scale"])
    assert field["baseline"]["stationary_velocity_rmse"] is None
    (tmp_path / "field_synthetic.json").write_text(json.dumps(field, indent=2), encoding="utf-8")


def test_native_uncertainty_drives_independent_vertical_sweeps(tmp_path):
    opened = NavigationPair_Open(tmp_path / "pair", flight_samples=121)
    base = opened.dataset

    class GnssContext:
        def __getattr__(self, name):
            return getattr(base.semantic_context, name)

        def CanonicalRoute_Get(self, key):
            if key in ("canonical:gnss.position", "canonical:gnss.velocity"):
                return {"endpoint_descriptor_ids": (101,)}
            return base.semantic_context.CanonicalRoute_Get(key)

        def CapabilityEndpoint_Get(self, key):
            return (
                {"instance_id": 1}
                if key == 101
                else base.semantic_context.CapabilityEndpoint_Get(key)
            )

    measurements, native = [], []
    start = base.start_timestamp_us
    for index in range(25):
        timestamp = start + 40000 * (index + 1)
        measurement = Measurement_Create(timestamp, index + 1, (0.2, -0.1, 0.3))
        payload = {
            **measurement.payload,
            "position_usable": 1,
            "position_enu_m": (0.2, -0.1, 2),
            "position_variance_m2": (2.25, 2.25, 6.25),
            "velocity_variance_m2ps2": (0.0225, 0.0225, 0.0225),
        }
        measurements.append(replace(measurement, payload=payload, valid_flags=3))
        native.append(
            replace(
                measurement,
                record_name="GNSS_NATIVE",
                payload={
                    **payload,
                    "source_descriptor_id": 101,
                    "instance_id": 1,
                    "horizontal_accuracy_m": 0.5,
                    "vertical_accuracy_m": 0.8,
                    "velocity_variance_m2ps2": (0.01, 0.01, 0.01),
                },
            )
        )
    dataset = replace(
        base,
        semantic_context=GnssContext(),
        records={
            **base.records,
            "GNSS_MEASUREMENT": tuple(measurements),
            "GNSS_NATIVE": tuple(native),
        },
    )
    dataset = SyntheticOperations_Attach(dataset)
    report = FieldSweep_Run(dataset, include_latency=False)
    for rows in report["sweeps"].values():
        assert all("result" in row for row in rows)
    velocity_runs = report["sweeps"]["gnss_velocity_vertical_scale"]
    assert (
        velocity_runs[0]["result"]["final_velocity_mps"]
        != velocity_runs[-1]["result"]["final_velocity_mps"]
    )
    plugin = Kf6AlgorithmPlugin()
    schedule = (
        _ScheduledMeasurement(measurements[0].timestamp_us, 1, "gnss", measurements[0], True),
    )
    parameters = dict(plugin.Parameters_Resolve(dataset, ReplayRequest()))
    parameters["gnss_velocity_vertical_scale"] = 1.5
    shifted = plugin._MeasurementParameters_Apply(
        dataset, schedule, parameters, frozen_initial=True
    )
    np.testing.assert_allclose(
        shifted[0].record.payload["velocity_variance_m2ps2"], [0.0225, 0.0225, 0.0225 * 2.25]
    )
    (tmp_path / "native_weight_sweeps.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
