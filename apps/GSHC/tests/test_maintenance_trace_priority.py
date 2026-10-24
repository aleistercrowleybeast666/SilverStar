"""Synthetic diagnostic capacity checks; never open a device."""
import json
from unittest.mock import patch

from services.maintenance_trace import MaintenanceTrace


def rows(trace):
    return [json.loads(line) for line in trace.path.read_text(encoding='utf-8').splitlines()]


def test_critical_rejection_and_failure_survive_normal_budget_exhaustion(tmp_path):
    trace = MaintenanceTrace(tmp_path, 'SYNTHETIC', 921600, limit=32768)
    for _ in range(300):
        trace.event('normal', detail='x'*1000)
    for _ in range(500):
        trace.event('normal')
    assert trace.truncated
    trace.event('local_rejected', reason='declaration_changed', request_sent=False)
    trace.event('job_failed', error='synthetic failure after normal budget filled')
    trace.close('synthetic test only')
    content = rows(trace)
    assert any(row['kind'] == 'local_rejected' for row in content)
    assert any(row['kind'] == 'job_failed' for row in content)
    assert content[-1]['kind'] == 'closed'
    assert trace.path.stat().st_size <= 32768


def test_poll_sampling_keeps_state_changes_and_errors(tmp_path):
    now = [0.0]
    with patch('services.maintenance_trace.time.monotonic', side_effect=lambda: now[0]):
        trace = MaintenanceTrace(tmp_path, 'SYNTHETIC', 921600)
        for i in range(1000):
            now[0] = i/5
            trace.exchange('SYSTEM DIAG 3', 'OK SYSTEM DIAG version=1 state=OBSERVED counter='+str(i), .005)
            trace.exchange('LOGFILE STATUS', f'OK LOGFILE STATUS sequence={i} age_ms=1 lifecycle=2 writer_open=1 healthy=1', .005)
        now[0] += .01
        trace.exchange('LOGFILE STATUS', 'OK LOGFILE STATUS lifecycle=2 writer_open=0 healthy=1', .005)
        trace.exchange('SYSTEM DIAG 3', 'ERR SYSTEM DIAG code=BUSY', .005)
        trace.close()
    content = rows(trace)
    assert trace.exchanges == 2002 and trace.sampled_exchanges > 1900
    assert not trace.truncated and trace.path.stat().st_size < 40000
    assert any(row.get('response', '').endswith('writer_open=0 healthy=1') for row in content)
    assert any(row.get('response', '').startswith('ERR ') for row in content)


def test_priority_overflow_is_bounded_and_terminal_tail_retains_latest_errors(tmp_path):
    trace = MaintenanceTrace(tmp_path, 'SYNTHETIC', 921600, limit=32768)
    for i in range(200):
        trace.event('job_failed', error=f'failure {i} '+('错误'*300))
    trace.event('local_rejected', reason='last_refusal', request_sent=False)
    trace.close('closed after synthetic overload')
    content = rows(trace)
    assert content[-1]['kind'] == 'closed'
    assert content[-1]['critical_dropped'] > 0
    assert content[-1]['critical_tail'][-1]['reason'] == 'last_refusal'
    assert trace.path.stat().st_size <= 32768


def test_gui_posts_are_bounded_drained_by_owner_and_closed_posts_refused(tmp_path):
    trace = MaintenanceTrace(tmp_path, 'SYNTHETIC', 921600)
    before = trace.path.read_bytes()
    for i in range(64):
        assert trace.Event_Post('local_rejected', reason=str(i), request_sent=False)
    assert len(trace._pending) == 32 and trace.path.read_bytes() == before
    trace.Pending_Flush()
    content = rows(trace)
    assert next(row['dropped'] for row in content if row['kind'] == 'diagnostic_queue_overflow') == 32
    assert [row['reason'] for row in content if row['kind'] == 'local_rejected'] == [str(i) for i in range(32, 64)]
    trace.close()
    assert not trace.Event_Post('local_rejected', reason='too late')


def test_terminal_record_survives_large_unicode_exchange_tails(tmp_path):
    trace = MaintenanceTrace(tmp_path, 'SYNTHETIC', 921600, limit=32768)
    for _ in range(100):
        trace.raw('rx', b'x'*256)
        trace.exchange('命令'*200, '回复'*500, .001, '错误'*500)
    trace.event('local_rejected', reason='final_refusal', request_sent=False)
    trace.close('Unicode capacity case')
    content = rows(trace)
    assert content[-1]['kind'] == 'closed' and content[-1]['exchanges'] == 100
    assert content[-1]['critical_tail'][-1]['reason'] == 'final_refusal'
    assert trace.path.stat().st_size <= 32768


def test_queued_refusal_is_flushed_on_close_after_normal_budget_fills(tmp_path):
    trace = MaintenanceTrace(tmp_path, 'SYNTHETIC', 921600, limit=32768)
    for _ in range(500):trace.event('normal', detail='x'*1024)
    assert trace.Event_Post('local_rejected', reason='declaration_loading', request_sent=False)
    trace.close()
    assert any(row.get('reason') == 'declaration_loading' for row in rows(trace))
