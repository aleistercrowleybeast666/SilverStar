from copy import deepcopy

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.horizon_inputs import (
    KfHorizonEvent_FromRecord, EskfHorizonEvent_FromRecord,
    HorizonWhatIfDelays_Validate, HorizonWhatIfTime_Apply,
)
from tests.test_fusion_horizon_records import MEASUREMENT, _Record, _Completed


def test_kf_record_keeps_exact_prepared_r_and_receipt_certificate():
    record = _Record(MEASUREMENT, prepared_variance=[.234567, .345678], quality_scale=3., consistency_scale=2.,
        kf_availability_timestamp_us=1009000, kf_consistency_start_timestamp_us=1001000,
        kf_recovery_generation=42, kf_consistent_count=3, kf_outage=1,
        kf_loss_latched=0, kf_recovery_valid=1, kf_consistency_valid=1)
    before = deepcopy(dict(record.payload))
    event = KfHorizonEvent_FromRecord(record, epoch=7, calibration_generation=3)
    np.testing.assert_array_equal(event.prepared_variance, np.float32(before['prepared_variance']))
    assert event.generation == 3 and event.evidence.generation == 42
    assert (event.evidence.availability_us, event.evidence.consistency_start_us) == (1009000, 1001000)
    assert (event.evidence.consistent_count, event.evidence.outage, event.evidence.recovery_valid) == (3, 1, 1)
    event.prepared_variance[:] = 123
    event.value[:] = 321
    assert dict(record.payload) == before


@pytest.mark.parametrize('group', range(5))
def test_eskf_record_uses_prepared_variance_without_quality_rescaling(group):
    record = _Record(MEASUREMENT, algorithm_id=2, algorithm_revision=1, numerical_revision=2,
        group=group, source_id=1 if group == 4 else 0,
        prepared_variance=[.234567, .345678], quality_scale=3., consistency_scale=2.)
    event = EskfHorizonEvent_FromRecord(record, epoch=7, calibration_generation=3)
    dimension = 2 if group in (0, 2) else 1
    np.testing.assert_array_equal(event.prepared_variance, np.float32(record.payload['prepared_variance'][:dimension]))
    assert event.quality_scale == 3. and event.consistency_scale == 2.
    assert event.mission_epoch == 7 and event.generation == 3


@pytest.mark.parametrize('builder,algorithm,revision,numerical', [
    (KfHorizonEvent_FromRecord, 1, 2, 1), (EskfHorizonEvent_FromRecord, 2, 1, 2)])
def test_event_conversion_cannot_borrow_completion_or_mission_identity(builder, algorithm, revision, numerical):
    record = _Record(MEASUREMENT, algorithm_id=algorithm, algorithm_revision=revision, numerical_revision=numerical)
    for candidate, epoch, calibration in ((record, 8, 3), (record, 7, 4), (_Completed(record), 7, 3)):
        with pytest.raises(ValueError, match='request_identity_mismatch'):
            builder(candidate, epoch=epoch, calibration_generation=calibration)


@pytest.mark.parametrize('builder,algorithm,revision,numerical', [
    (KfHorizonEvent_FromRecord, 1, 2, 1), (EskfHorizonEvent_FromRecord, 2, 1, 2)])
def test_explicit_fallback_delay_changes_only_owned_source_time(builder, algorithm, revision, numerical):
    record = _Record(MEASUREMENT, algorithm_id=algorithm, algorithm_revision=revision,
        numerical_revision=numerical, timing_flags=9)
    event = builder(record, epoch=7, calibration_generation=3)
    requested = {0: 7}
    delays = HorizonWhatIfDelays_Validate((record,), requested)
    requested[0] = 100
    changed = HorizonWhatIfTime_Apply(record, event, delays)
    assert changed.timestamp_us == record.payload['receive_timestamp_us'] - 7000
    assert changed.receive_us == event.receive_us and event.timestamp_us == 1005000
    np.testing.assert_array_equal(changed.prepared_variance, event.prepared_variance)
    assert record.payload['measurement_timestamp_us'] == 1005000
    invalid = HorizonWhatIfTime_Apply(record, event, {0: 2000})
    assert invalid.timestamp_us == 0


def test_trusted_timestamp_ignores_a_changed_fallback_delay_and_missing_trust_stops():
    trusted = _Record(MEASUREMENT)
    event = KfHorizonEvent_FromRecord(trusted, epoch=7, calibration_generation=3)
    delays = HorizonWhatIfDelays_Validate((trusted,), {0: 7})
    assert HorizonWhatIfTime_Apply(trusted, event, delays) is event
    unknown = _Record(MEASUREMENT, timing_flags=0, execution_result=1, measurement_timestamp_us=0)
    with pytest.raises(ValueError, match='delay_trust_evidence_missing'):
        HorizonWhatIfDelays_Validate((unknown,), {0: 7})


@pytest.mark.parametrize('changes', [{True: 7}, {0: True}, {0: 7.}, {'0': 7}, {5: 7}, {0: -1}])
def test_what_if_delay_control_requires_explicit_typed_group_and_milliseconds(changes):
    with pytest.raises(ValueError, match='what_if_delay_invalid'):
        HorizonWhatIfDelays_Validate((), changes)
