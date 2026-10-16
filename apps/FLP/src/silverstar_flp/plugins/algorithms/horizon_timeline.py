"""One forward body cycle, then its received requests, then atomic completion.

This coordinator requires an explicitly initialized owning numerical engine and
validated original records. Exact decoder/body/initial-state admission belongs
to the caller. No Recorded defaults, health claims or file opening are added.
"""

from dataclasses import dataclass

import numpy as np

from silverstar_flp.core.context import TaskContext
from silverstar_flp.decoder_profiles.fusion_horizon_records import CONTRACT
from silverstar_flp.plugins.algorithms.horizon_inputs import (
    EskfHorizonEvent_FromRecord,
    HorizonWhatIfDelays_Validate,
    HorizonWhatIfTime_Apply,
    KfHorizonEvent_FromRecord,
)


@dataclass(frozen=True, slots=True)
class HorizonKfState:
    # Timeline samples own numerical arrays only. Retaining a full filter here
    # would copy its cumulative diagnostic history into every output sample.
    state: np.ndarray
    covariance: np.ndarray


@dataclass(frozen=True, slots=True)
class HorizonSample:
    timestamp_us: int
    primary_timestamp_us: int
    output_covariance_timestamp_us: int
    primary: object
    output: object
    warmup: bool
    work_count: int


@dataclass(frozen=True, slots=True)
class HorizonTimelineResult:
    samples: tuple
    operations: tuple
    completions: tuple
    pending_operations: tuple
    failure: dict | None


def _Operation_Get(event, algorithm):
    return event.operation_sequence if algorithm == 1 else event.key[0]


def _WireResult_Get(result):
    name = "complete" if result.name == "OK" else result.name.lower()
    if name not in CONTRACT["execution_results"]:
        raise ValueError("fusion_horizon_execution_namespace_invalid:" + name)
    return CONTRACT["execution_results"][name]


def HorizonTimeline_Run(
    engine,
    algorithm_id,
    body_steps,
    evidence,
    *,
    strict_recorded=True,
    context=None,
    changed_delays_ms=None,
):
    if (
        type(algorithm_id) is not int
        or algorithm_id not in (1, 2)
        or type(strict_recorded) is not bool
    ):
        raise ValueError("fusion_horizon_timeline_configuration_invalid")
    context = context or TaskContext()
    requests = sorted(evidence.requests, key=lambda record: record.file_offset)
    if strict_recorded and changed_delays_ms is not None:
        raise ValueError("fusion_horizon_recorded_override_forbidden")
    delays = (
        {}
        if changed_delays_ms is None
        else HorizonWhatIfDelays_Validate(requests, changed_delays_ms)
    )
    records = (*requests, *evidence.completions, *evidence.statuses)
    if any(record.payload["algorithm_id"] != algorithm_id for record in records):
        raise ValueError("fusion_horizon_timeline_algorithm_mismatch")
    if any(
        record.payload["epoch"] != engine.epoch
        or record.payload["calibration_generation"] != engine.generation
        for record in records
    ) or any(record.payload["source_id"] != engine.source for record in evidence.statuses):
        raise ValueError("fusion_horizon_committed_epoch_mismatch")
    recorded_completions = {
        record.payload["operation_sequence"]: record for record in evidence.completions
    }
    if len(recorded_completions) != len(evidence.completions):
        raise ValueError("fusion_horizon_timeline_epoch_ambiguous")
    statuses = {record.timestamp_us: record for record in evidence.statuses}
    if len(statuses) != len(evidence.statuses):
        raise ValueError("fusion_horizon_timeline_status_ambiguous")
    samples, operations, completions = [], [], []
    request_index, failure = 0, None
    for index, body in enumerate(body_steps):
        context.Cancel_RaiseIfRequested()
        result = engine.Body_Receive(body)
        if result.name != "OK":
            failure = {"timestamp_us": body.end_us, "phase": "body", "result": result.name}
            break
        while request_index < len(requests) and requests[request_index].timestamp_us <= body.end_us:
            record = requests[request_index]
            if record.timestamp_us != body.end_us:
                raise ValueError("fusion_horizon_request_body_epoch_missing")
            builder = (
                KfHorizonEvent_FromRecord if algorithm_id == 1 else EskfHorizonEvent_FromRecord
            )
            event = builder(record, epoch=engine.epoch, calibration_generation=engine.generation)
            event = HorizonWhatIfTime_Apply(record, event, delays)
            admitted = (
                engine.Insert(event) if algorithm_id == 1 else engine.Measurement_Receive(event)
            )
            wire = _WireResult_Get(admitted)
            operations.append(
                {
                    "operation_sequence": record.payload["operation_sequence"],
                    "evaluation_timestamp_us": body.end_us,
                    "result": wire,
                    "recorded_result": record.payload["execution_result"],
                    "source_timestamp_us": event.timestamp_us,
                    "recorded_source_timestamp_us": record.payload["measurement_timestamp_us"],
                }
            )
            if strict_recorded and wire != record.payload["execution_result"]:
                raise ValueError("fusion_horizon_request_result_mismatch")
            request_index += 1
        result = engine.Advance()
        if result.name not in ("OK", "WARMUP"):
            failure = {"timestamp_us": body.end_us, "phase": "advance", "result": result.name}
            break
        status = statuses.get(body.end_us)
        if strict_recorded and (
            status is None
            or status.payload["primary_timestamp_us"] != engine.primary_us
            or status.payload["output_state_timestamp_us"] != engine.output_us
            or status.payload["phase"] != int(not engine.warmup)
        ):
            raise ValueError("fusion_horizon_committed_epoch_mismatch")
        for _ in range(engine.EVENT_CAPACITY + 1):
            popped, completed = engine.Completion_Pop()
            if popped.name == "EMPTY":
                break
            if popped.name != "OK":
                raise ValueError("fusion_horizon_completion_drain_failed")
            event, outcome = completed
            operation = _Operation_Get(event, algorithm_id)
            if strict_recorded:
                recorded = recorded_completions.pop(operation, None)
                if (
                    recorded is None
                    or recorded.timestamp_us != engine.output_us
                    or recorded.payload["group"] != event.group
                    or recorded.payload["application_timestamp_us"] != event.timestamp_us
                    or recorded.payload["update_result"] != int(outcome.result)
                ):
                    raise ValueError("fusion_horizon_completion_execution_mismatch")
            completions.append((body.end_us, event, outcome))
        else:
            raise ValueError("fusion_horizon_completion_drain_bound")
        primary = (
            HorizonKfState(engine.primary.state.copy(), engine.primary.covariance.copy())
            if algorithm_id == 1
            else engine.primary.State_Clone()
        )
        output = (
            HorizonKfState(engine.output.state.copy(), engine.output.covariance.copy())
            if algorithm_id == 1
            else engine.kernel.state.State_Clone()
        )
        samples.append(
            HorizonSample(
                body.end_us,
                engine.primary_us,
                engine.output_us,
                primary,
                output,
                engine.warmup,
                engine.last_work,
            )
        )
        if index % 200 == 0:
            context.Progress_Report(index / max(len(body_steps), 1), "replay.running")
    if request_index != len(requests) and failure is None:
        raise ValueError("fusion_horizon_request_body_history_incomplete")
    if strict_recorded and recorded_completions and failure is None:
        raise ValueError("fusion_horizon_recorded_completion_unexecuted")
    pending = tuple(_Operation_Get(event, algorithm_id) for event in engine.measurements)
    if (
        strict_recorded
        and failure is None
        and set(pending) != {r.payload["operation_sequence"] for r in evidence.pending}
    ):
        raise ValueError("fusion_horizon_pending_evidence_mismatch")
    return HorizonTimelineResult(
        tuple(samples), tuple(operations), tuple(completions), pending, failure
    )
