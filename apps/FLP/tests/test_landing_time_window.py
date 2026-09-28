from dataclasses import replace
from pathlib import Path

import pytest

from silverstar_flp.analysis.landing_window import ImuTimeWindow, LandingWindow_Replay
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset
from silverstar_flp.core.diagnostics import ParserDiagnostics


@pytest.mark.parametrize('rate', [100, 200, 400])
@pytest.mark.parametrize('disturbance', ['static', 'spike', 'brief_gap', 'walking', 'motion'])
def test_time_coverage_is_independent_of_sample_count(rate, disturbance):
    dt = 1_000_000 // rate
    window = ImuTimeWindow(0, 0, previous_valid=True, previous_still=True)
    for timestamp in range(dt, 3_000_001, dt):
        if disturbance == 'brief_gap' and 1_000_000 < timestamp < 1_030_000:
            continue
        still = not ((disturbance == 'spike' and timestamp == 1_500_000)
                     or disturbance == 'motion'
                     or (disturbance == 'walking' and timestamp % 500_000 < 150_000))
        assert window.Sample_Add(timestamp, True, still)
    assert window.Accepted_Get(3_000_000) == (disturbance in ('static', 'spike', 'brief_gap'))


def _Dataset_Build(rate, motion=False, duplicate=False):
    records = {'BARO_NATIVE': [], 'IMU_CORRECTED': []}
    for timestamp in range(10_000, 5_100_000, 1_000_000 // rate):
        payload = dict(sample_timestamp_us=timestamp, receive_timestamp_us=timestamp,
                       valid_mask=3, correction_valid=1, accel_b_mps2=[0,0,9.78],
                       gyro_b_radps=[.3 if motion else 0,0,0])
        record = DecodedRecord(0x12, 'IMU_CORRECTED', 0, 0, timestamp, timestamp, 3, payload, 0)
        records['IMU_CORRECTED'].append(record)
        if duplicate and timestamp == 1_000_000:
            records['IMU_CORRECTED'].append(record)
    for timestamp in range(10_000, 5_100_000, 50_000):
        payload = dict(sample_timestamp_us=timestamp, receive_timestamp_us=timestamp,
                       valid_mask=1, healthy=1, altitude_m=123.0,
                       source_descriptor_id=1, instance_id=0)
        records['BARO_NATIVE'].append(DecodedRecord(0xF, 'BARO_NATIVE', 1, 0, timestamp,
                                                  timestamp, 1, payload, 0))
    return FlightDataset(
        Path("synthetic"), 0, {"gravity_mps2": 9.78}, ParserDiagnostics(), records, {}
    )


@pytest.mark.parametrize('rate', [100, 200, 400])
def test_observation_landing_replay_and_motion_rejection(rate):
    config = dict(baro_trigger_window_ms=1000, baro_trigger_min_samples=10,
                  baro_trigger_rate_mps=1.0, candidate_duration_ms=3000,
                  baro_confirm_rate_mps=.30, baro_max_span_m=1.,
                  candidate_baro_min_samples=30, candidate_min_coverage_percent=80,
                  still_gyro_threshold_radps=.10, still_accel_tolerance_mps2=.5,
                  landing_sample_max_age_ms=100)
    dataset = _Dataset_Build(rate, duplicate=True)
    landing, _, report = LandingWindow_Replay(dataset, config, 0)
    assert landing is not None and 4_000_000 <= landing <= 4_100_000
    assert [r['transition'] for r in report['transitions']] == [1,3]
    assert report['fidelity'] == 'APPROXIMATE'
    assert LandingWindow_Replay(_Dataset_Build(rate, motion=True), config, 0)[0] is None
    # A second physical barometer is never silently mixed into the same window.
    other = replace(dataset.Records_Get('BARO_NATIVE')[0], payload={
        **dataset.Records_Get('BARO_NATIVE')[0].payload, 'source_descriptor_id': 2})
    ambiguous = replace(dataset, records={**dataset.records,
        'BARO_NATIVE': (*dataset.Records_Get('BARO_NATIVE'), other)})
    assert LandingWindow_Replay(ambiguous, config, 0)[1] == 'landing_barometer_source_ambiguous'
