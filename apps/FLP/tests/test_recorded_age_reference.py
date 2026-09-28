from dataclasses import replace
from types import SimpleNamespace

import pytest

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from tests.recorded_age_reference import RecordedAgeSchedule_Build


def _Record_Build(name, payload, timestamp=40000):
    return DecodedRecord(1, name, 1, 0, 1, timestamp, 0, payload, 0)


@pytest.mark.parametrize(
    "evidence,expected",
    [
        ({}, 20000),
        ({"baro_sequence": 1, "baro_timestamp_us": 13000, "baro_measurement_age_us": 17000}, 30000),
        ({"baro_sequence": 2, "baro_timestamp_us": 13000, "baro_measurement_age_us": 17000}, 20000),
        ({"baro_sequence": 1, "baro_timestamp_us": 12000, "baro_measurement_age_us": 18000}, 20000),
        ({"baro_sequence": 1, "baro_timestamp_us": 13000, "baro_measurement_age_us": -1}, 20000),
        ({"baro_sequence": 1, "baro_timestamp_us": 13000, "baro_measurement_age_us": 16000}, 20000),
        (
            {"baro_sequence": 1, "baro_timestamp_us": 13000, "baro_measurement_age_us": 0xFFFFFFFF},
            20000,
        ),
    ],
)
def test_recorded_age_evidence_and_fallback(evidence, expected):
    measurement = _Record_Build(
        "BARO_MEASUREMENT",
        {"sequence": 1, "sample_timestamp_us": 13000, "receive_timestamp_us": 13000},
    )
    state = _Record_Build("ESTIMATOR", evidence)
    records = {"BARO_MEASUREMENT": (measurement,), "ESTIMATOR": (state, state)}
    dataset = SimpleNamespace(Records_Get=lambda kind: records.get(kind, ()))
    increments = tuple(
        SimpleNamespace(interval_end_timestamp_us=t) for t in (10000, 20000, 30000, 40000)
    )
    baseline, _ = Kf6AlgorithmPlugin._MeasurementSchedule_Build(dataset, increments)
    result, inferred = RecordedAgeSchedule_Build(dataset, increments, baseline)
    assert len(result) == 1
    assert result[0].application_timestamp_us == expected
    assert inferred == (expected == 20000)


def test_mixed_schedule_and_conflicting_age_keep_gnss_before_baro():
    payload = {"sequence": 1, "sample_timestamp_us": 13000, "receive_timestamp_us": 13000}
    baro = _Record_Build("BARO_MEASUREMENT", payload)
    gnss = _Record_Build("GNSS_MEASUREMENT", payload)
    fallback = replace(baro, record_sequence=3, payload={**payload, "sequence": 2})
    evidence = {
        kind + key: value
        for kind in ("gnss", "baro")
        for key, value in (
            ("_sequence", 1),
            ("_timestamp_us", 13000),
            ("_measurement_age_us", 17000),
        )
    }
    state = _Record_Build("ESTIMATOR", evidence)
    records = {
        "BARO_MEASUREMENT": (baro, fallback),
        "GNSS_MEASUREMENT": (gnss,),
        "ESTIMATOR": (state, state),
    }
    dataset = SimpleNamespace(Records_Get=lambda kind: records.get(kind, ()))
    increments = tuple(
        SimpleNamespace(interval_end_timestamp_us=t) for t in (10000, 20000, 30000, 40000)
    )
    baseline, _ = Kf6AlgorithmPlugin._MeasurementSchedule_Build(dataset, increments)
    resolved, inferred = RecordedAgeSchedule_Build(dataset, increments, baseline)
    assert inferred
    assert [(r.kind, r.application_timestamp_us, r.inferred) for r in resolved] == [
        ("baro", 20000, True),
        ("gnss", 30000, False),
        ("baro", 30000, False),
    ]
    records["ESTIMATOR"] += (replace(state, payload={**evidence, "baro_measurement_age_us": 7000}),)
    resolved, _ = RecordedAgeSchedule_Build(dataset, increments, baseline)
    assert all(r.inferred for r in resolved if r.kind == "baro")
