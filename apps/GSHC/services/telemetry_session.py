"""Bounded receive-session facts. ACKs gate transport, never invent stages."""
from collections import OrderedDict, deque
from enum import Enum


class TelemetryObserveResult(str, Enum):
    Accepted = 'accepted'
    Duplicate = 'duplicate'
    Retired = 'retired_session'
    Conflict = 'identity_conflict'


class TelemetrySession:
    def __init__(self):
        self.boot_session = None
        self.profile = None
        self.passive = True
        self.phase_floor_us = 0
        self.retired = deque(maxlen=16)
        self.events = OrderedDict()
        self.sequences = {}
        self.event_floor_id = 0
        self.missions = deque(maxlen=32)
        self.last_stage_id = None
        self.history_complete = False
        self.current_mission_key = (-1, -1)
        self.last_stage_key = (-1, -1)
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
            self.events.clear()
            self.sequences.clear()
            self.event_floor_id = 0
            self.last_stage_id = None
            self.current_mission_key = self.last_stage_key = (-1, -1)
            self.history_complete = False
            self.health = self.health_received_ns = None
        if frame.profile != self.profile:
            return TelemetryObserveResult.Conflict
        previous = self.sequences.get(frame.message_type)
        if previous is not None:
            delta = (frame.sequence - previous) & 0xFFFF
            if delta == 0 or delta >= 0x8000:
                return TelemetryObserveResult.Duplicate
        self.sequences[frame.message_type] = frame.sequence
        fields = frame.values
        if frame.message_type == 0x12:
            if fields['advertised_monotonic_us'] > self.phase_floor_us:
                self.passive = False
        elif frame.message_type == 0x10:
            self.phase_floor_us = max(self.phase_floor_us, fields['time_ms'] * 1000)
            self.passive = self.profile == 'S'
        elif frame.message_type == 0x40 and fields['command_id'] == 1 and fields['result'] == 0:
            self.phase_floor_us = max(self.phase_floor_us, fields['time_ms'] * 1000)
            if self.profile == 'S': self.passive = True
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
                    self.last_stage_id = None
                    self.last_stage_key = self.current_mission_key
            if code in (3, 4, 5, 6, 0x100, 0x101):
                self.phase_floor_us = max(self.phase_floor_us, fields['occurred_us'])
                if self.profile == 'S': self.passive = True
            if code == 0x100 and (fields['occurred_us'], key) > self.last_stage_key:
                self.last_stage_id = fields['stage_id'] or None
                self.last_stage_key = (fields['occurred_us'], key)
            # Finite event reception cannot establish a complete lost history.
        return TelemetryObserveResult.Accepted

    def HealthSnapshot_Get(self, now_ns):
        if self.health is None:
            return None
        result = dict(self.health)
        elapsed = max(0, now_ns - self.health_received_ns) / 1e9
        result['stale'] = elapsed > 12.0
        result['received_age_s'] = elapsed
        result['current_known_mask'] = 0 if result['stale'] else result['known_mask']
        result['battery_age_s'] = None if result['battery_age_ds'] == 65535 else result['battery_age_ds'] / 10 + elapsed
        return result
