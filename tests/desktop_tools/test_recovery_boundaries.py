"""V1 review counterexamples exercised against v2, without creating Qt widgets."""
import ast
from collections import deque
from enum import Enum
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import threading
import pytest
ROOT = Path(__file__).parents[2]
FLP = 'apps/FLP/src/silverstar_flp/ui/main_window.py'

def source_function(relative, name, cls=None, globals_=None):
    path = ROOT / relative
    tree = ast.parse(path.read_text(encoding='utf-8'))
    body = tree.body if cls is None else next((n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls))
    node = next((n for n in body if isinstance(n, ast.FunctionDef) and n.name == name))
    node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(globals_ or {})
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace[name]

def flight(time_ms, east):
    import struct
    from protocol.gsp_min import build_gsp_frame
    air = struct.pack('<BBI10h6f', 16, 7, time_ms, 0, 0, 0, 0, 0, 0, 32767, 0, 0, 0, 0.0, 0.0, 0.0, east, 0.0, 10.0)
    return build_gsp_frame(2, bytes([180, 4, len(air)]) + air)

def boot():
    from protocol.gsp_min import build_gsp_frame
    air = bytes([32, 8, 1, 0, 0, 0, 0, 0, 0])
    return build_gsp_frame(2, bytes([180, 4, len(air)]) + air)

def worker_saturated():
    from services.recovery_position import RecoveryPosition
    from protocol.air import AirFlightStateMessage
    from transport.protocol_worker import ProtocolBatch
    dummy = NS(air_message=None, parsed_gsp=None, host_rx_monotonic_ns=1)
    worker = NS(_mailbox=deque([dummy] * 256), ui_mailbox_capacity=256, _mailbox_latest={}, _mailbox_lock=threading.Lock(), _ui_coalesced_events=0, _warning='', session_generation=1, _recovery_session=1 << 32, _recovery_position=RecoveryPosition(), _is_ui_coalescible=lambda e: isinstance(e.air_message, AirFlightStateMessage))
    worker.publish = lambda events: source_function('apps/GSHC/transport/protocol_worker.py', '_publish_events', 'ProtocolWorker', {'AirFlightStateMessage': AirFlightStateMessage})(worker, events)
    worker.take = lambda limit=512: source_function('apps/GSHC/transport/protocol_worker.py', 'take_batch', 'ProtocolWorker', {'ProtocolBatch': ProtocolBatch})(worker, limit)
    return worker

def controller():
    from services.state_model import FlightControllerState, MissionPhase
    from protocol.air import AirFlightStateMessage, AirStatusMessage
    from protocol.gsp_min import GsToPcAirFrame, GsStatus, GspAck
    c = NS(state=FlightControllerState(connected=True), _connection_generation=1, pending_air_cmds={}, _clear_capability_ack=Mock(), _clear_mission_packet_stats=Mock(), _log=Mock(), _mark_mission_started=Mock(), _handle_sensor_message=Mock())
    restart = source_function('apps/GSHC/app.py', 'FlightSession_Restart', 'Controller', {'FlightControllerState': FlightControllerState})
    handle = source_function('apps/GSHC/app.py', '_handle_flight_state', 'Controller', {'MissionPhase': MissionPhase})

    def dispatch(message, event):
        if isinstance(message, AirFlightStateMessage):
            handle(c, message, event)
        elif isinstance(message, AirStatusMessage) and message.status_id == 1:
            restart(c, 'BOOT')
    c._handle_air_message = dispatch
    c.publish = lambda batch: source_function('apps/GSHC/app.py', 'on_protocol_batch', 'Controller', dict(GsToPcAirFrame=GsToPcAirFrame, GsStatus=GsStatus, GspAck=GspAck))(c, batch)
    return c

def test_receive_identity_captured_per_event_same_chunk():
    from protocol.receive_pipeline import ReceivePipeline
    events = ReceivePipeline(recovery_connection=1).feed(flight(10000, 100) + boot() + flight(1, 2), 100)
    assert [e.recovery_session for e in events] == [1 << 32, (1 << 32) + 1, (1 << 32) + 1]
    w = worker_saturated()
    w.publish(events)
    c = controller()
    c.publish(w.take())
    assert c.state.recovery.sample.enu_m == (2, 0, 10)
    assert c.state.recovery.sample.time_ms == 1
    assert c.state.recovery.sample.session == (1 << 32) + 1

@pytest.mark.parametrize('batch_size', [1, 512])
def test_boot_before_old_coalesced_position_keeps_identity(batch_size):
    from protocol.receive_pipeline import ReceivePipeline
    p = ReceivePipeline(recovery_connection=1)
    w = worker_saturated()
    c = controller()
    events = p.feed(flight(10000, 100) + boot(), 100)
    w.publish(events)
    seen = []
    while (batch := w.take(batch_size)) is not None:
        seen.extend((e for e in batch.events if e in events))
        c.publish(batch)
    assert seen == [events[1], events[0]]
    assert c.state.recovery.sample.session == 1 << 32
    assert c.state.recovery_current_session == (1 << 32) + 1
    assert not c.state.recovery.Snapshot_Get(200, connected=True, current_session=c.state.recovery_current_session)['source_current']
    c.state.recovery.Frame_Confirm(True)
    w.publish(p.feed(flight(1, 2), 300))
    c.publish(w.take())
    assert c.state.recovery.sample.time_ms == 1
    assert c.state.recovery.sample.enu_m == (2, 0, 10)
    assert c.state.recovery.confirmed_session is None

def test_invalid_latest_coalesced_event_does_not_erase_valid_received_point():
    from protocol.receive_pipeline import ReceivePipeline
    w = worker_saturated()
    c = controller()
    w.publish(ReceivePipeline(recovery_connection=1).feed(flight(1, 3) + flight(2, float('nan')), 100))
    batch = w.take()
    assert batch.recovery_sample.enu_m == (3, 0, 10)
    c.publish(batch)
    assert c.state.recovery.sample.enu_m == (3, 0, 10)

def test_obsolete_connection_batch_ignored():
    from transport.protocol_worker import ProtocolBatch
    from services.recovery_position import RecoverySample
    c = controller()
    c.publish(ProtocolBatch(0, (), 0, RecoverySample(0, 1, (1.0, 2.0, 3.0), 1, 'old', 0)))
    assert c.state.recovery.sample is None
