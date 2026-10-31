"""Bounded receive-session facts. ACKs gate transport, never invent stages."""
from collections import OrderedDict, deque
from dataclasses import dataclass
from enum import Enum


class TelemetryObserveResult(str, Enum):
    Accepted = 'accepted'
    Duplicate = 'duplicate'
    Retired = 'retired_session'
    Conflict = 'identity_conflict'


@dataclass(frozen=True)
class TelemetrySnapshot:
    """Immutable presentation facts produced by the ordered receive owner."""
    boot_session: int | None
    profile: str | None
    passive: bool
    current_mission_key: tuple
    last_stage_id: int | None
    history_complete: bool
    missions: tuple
    health: tuple | None
    health_received_ns: int | None
    last_phase_key: tuple

    def HealthSnapshot_Get(self, now_ns):
        return _HealthSnapshot_Get(self.health, self.health_received_ns, now_ns)


def _HealthSnapshot_Get(health, received_ns, now_ns):
    if health is None:
        return None
    result = dict(health)
    elapsed = max(0, now_ns - received_ns) / 1e9
    result['stale'] = elapsed > 12.0
    result['received_age_s'] = elapsed
    result['current_known_mask'] = 0 if result['stale'] else result['known_mask']
    result['battery_age_s'] = None if result['battery_age_ds'] == 65535 else result['battery_age_ds'] / 10 + elapsed
    return result


class TelemetrySession:
    def __init__(self):
        self.boot_session = None
        self.profile = None
        self.passive = True
        self.phase_floor_us = 0
        self._downlink_only = False
        self.retired = deque(maxlen=16)
        self.events = OrderedDict()
        self.sequences = {}
        self._sequence_high = None
        self._sequence_index = 0
        self._received_sequences = {}
        self.event_floor_id = 0
        self.missions = deque(maxlen=32)
        self.last_stage_id = None
        self.history_complete = False
        self.current_mission_key = (-1, -1)
        self.last_stage_key = (-1, -1)
        self.last_phase_key = (-1, -1)
        self.health = None
        self.health_received_ns = None

    def Frame_Observe(self, frame, received_ns):
        if self.boot_session != frame.boot_session:
            if frame.boot_session in self.retired:
                return TelemetryObserveResult.Retired
            if self.boot_session is not None:
                self.retired.append(self.boot_session)
            self.boot_session, self.profile = frame.boot_session, frame.profile
            self.passive = True
            self.phase_floor_us = 0
            self._downlink_only = False
            self.events.clear()
            self.sequences.clear()
            self._sequence_high = None
            self._sequence_index = 0
            self._received_sequences.clear()
            self.event_floor_id = 0
            self.last_stage_id = None
            self.current_mission_key = self.last_stage_key = (-1, -1)
            self.last_phase_key = (-1, -1)
            self.history_complete = False
            self.health = self.health_received_ns = None
        if frame.profile != self.profile:
            return TelemetryObserveResult.Conflict
        sequence_result = self.Sequence_Observe(frame)
        if sequence_result is not TelemetryObserveResult.Accepted:
            return sequence_result
        fields = frame.values
        if frame.message_type == 0x12:
            if not self._downlink_only and fields['advertised_monotonic_us'] > self.phase_floor_us:
                self.passive = False
        elif frame.message_type == 0x10:
            self.phase_floor_us = max(self.phase_floor_us, fields['time_ms'] * 1000)
            self.passive = self.profile == 'S'
            self._downlink_only = self.passive
        elif frame.message_type == 0x40 and fields['command_id'] == 1 and fields['result'] == 0:
            self.phase_floor_us = max(self.phase_floor_us, fields['time_ms'] * 1000)
            if self.profile == 'S': self.passive = self._downlink_only = True
        elif frame.message_type == 0x19:
            self.health, self.health_received_ns = dict(fields), received_ns
        elif frame.message_type == 0x20:
            key = fields['event_id']
            if key <= self.event_floor_id:
                return TelemetryObserveResult.Duplicate
            old = self.events.get(key)
            if old is not None:
                return TelemetryObserveResult.Duplicate if old == fields else TelemetryObserveResult.Conflict
            self.events[key] = dict(fields)
            if len(self.events) > 2048:
                retired_id, _ = self.events.popitem(last=False)
                self.event_floor_id = max(self.event_floor_id, retired_id)
                self.history_complete = False
            code = fields['event_code']
            if code == 3:
                self.missions.append((frame.boot_session, key, fields['occurred_us']))
                if (fields['occurred_us'], key) > self.current_mission_key:
                    self.current_mission_key = (fields['occurred_us'], key)
                    if self.current_mission_key > self.last_stage_key:
                        self.last_stage_id = None
                        self.last_stage_key = self.current_mission_key
            if code in (3, 4, 5, 6, 0x100, 0x101):
                self.phase_floor_us = max(self.phase_floor_us, fields['occurred_us'])
                if self.profile == 'S': self.passive = self._downlink_only = True
            if code in (3, 4, 5, 6):
                self.last_phase_key = max(self.last_phase_key, (fields['occurred_us'], key))
            if code == 0x100 and (fields['occurred_us'], key) > self.last_stage_key:
                self.last_stage_id = fields['stage_id'] or None
                self.last_stage_key = (fields['occurred_us'], key)
            # Finite event reception cannot establish a complete lost history.
        return TelemetryObserveResult.Accepted

    def Sequence_Observe(self, frame):
        """Unwrap the *global* sender sequence; allow 255 frames of reordering.

        A gap of half a sequence space is ambiguous without independent sender
        evidence and is rejected. Sparse types do not create such a gap when
        intervening traffic was received. New sequence numbers on event retries
        are deduplicated separately by their stable event identity.
        """
        if self._sequence_high is None:
            index = 0
            self._sequence_high = frame.sequence
        else:
            delta = (frame.sequence - self._sequence_high) & 0xFFFF
            offset = delta if delta < 0x8000 else delta - 0x10000
            if offset <= -256:
                return TelemetryObserveResult.Duplicate
            index = self._sequence_index + offset
            if offset > 0:
                self._sequence_high = frame.sequence
                self._sequence_index = index
        old = self._received_sequences.get(index)
        if old is not None:
            return TelemetryObserveResult.Duplicate if old == frame.raw else TelemetryObserveResult.Conflict
        self._received_sequences[index] = frame.raw
        floor = self._sequence_index - 255
        self._received_sequences = {key: value for key, value in self._received_sequences.items() if key >= floor}
        previous = self.sequences.get(frame.message_type)
        # Late unique events are history, but an old CAP/HEALTH/data snapshot
        # must not overwrite the newer accepted state for that message type.
        if previous is not None and index <= previous and frame.message_type != 0x20:
            return TelemetryObserveResult.Duplicate
        self.sequences[frame.message_type] = max(index, previous if previous is not None else index)
        return TelemetryObserveResult.Accepted

    def Snapshot_Get(self):
        return TelemetrySnapshot(self.boot_session, self.profile, self.passive,
            self.current_mission_key, self.last_stage_id, self.history_complete,
            tuple(self.missions), None if self.health is None else tuple(self.health.items()),
            self.health_received_ns, self.last_phase_key)

    def HealthSnapshot_Get(self, now_ns):
        return _HealthSnapshot_Get(self.health, self.health_received_ns, now_ns)
