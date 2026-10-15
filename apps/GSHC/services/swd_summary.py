"""Stable evidence-only summary for people and local automation."""
from dataclasses import asdict
import time


_FIELDS = (
    ('task.preparation', ('ready','start_blocking_mask','warning_mask','attitude_status')),
    ('thread.estimator', ('last_duration_us','last_prediction_count','prediction_cap_count')),
    ('sensor.ins_solution', ('ins_valid','alignment_valid','mission_running','update_seq')),
    ('thread.logger', ('completed_writes','writer_open','log_fault','finalization','healthy')),
)


def Summary_Build(rows, matched):
    indexed = {row['id']:row for row in rows}
    result = []
    for identifier, fields in _FIELDS:
        row = indexed.get(identifier)
        available = matched and row is not None and row.get('state') == 'OBSERVED'
        values = {key:row['fields'][key] for key in fields if key in row['fields']} if available else {}
        age = max(0,(time.monotonic_ns()-row['received_ns'])/1e6) if row else None
        state = ('STALE' if age > 3000 else 'OBSERVED') if available else 'UNKNOWN'
        result.append(dict(id=identifier,state=state,values=values,
            reason=row.get('reason','') if row else 'firmware_unmatched_or_field_unavailable',
            host_age_ms=age,
            mcu_sample_age_ms=None,consistency=row.get('consistency','unknown') if row else 'unknown'))
    return result


def Snapshot_Document(reply):
    value = asdict(reply)
    value.update(format='silverstar.swd-snapshot',version=1,
        summary=Summary_Build(reply.diagnostics,bool(reply.snapshot and reply.snapshot.symbols=='matched')),
        authorization='observations_only; not READY/START authority',
        time_semantics='host receipt times are not MCU sample times; multi-field live reads may be incoherent')
    return value
