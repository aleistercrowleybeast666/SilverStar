"""Bounded, declarative mission phases and a desktop-only reference interpreter.

No hardware operations or executable expressions. START is not a launch event.
"""
from copy import deepcopy
from enum import Enum
import math
import re


EVENTS = ('ready', 'start_accepted', 'launch_detected', 'burnout_detected',
          'apogee_confirmed', 'deployment_confirmed', 'landed_confirmed', 'recovery_complete')
SIGNALS = {'event': 'event_id', 'stage_elapsed_s': 's', 'altitude_agl_m': 'm',
           'vertical_velocity_mps': 'm/s'}
ACTIONS = ('none', 'record_marker', 'request_recovery')


class MissionProcessResult(str, Enum):
    Waiting = 'waiting'
    Entered = 'entered'
    Complete = 'complete'
    Invalid = 'invalid'


def _Keys_Require(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('mission_process_fields')


def _Text_Require(value, maximum=128):
    if type(value) is not str or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError('mission_process_text')


def MissionProcess_Default():
    definitions = [('ready', '就绪', 'ready'), ('mission_start', '任务开始', 'start_accepted'),
        ('ascent', '动力上升', 'launch_detected'), ('coast', '无动力滑行', 'burnout_detected'),
        ('predeploy', '预开伞', 'apogee_confirmed'), ('deploy', '开伞请求', None),
        ('descent', '下降', 'deployment_confirmed'), ('landed', '已落地', 'landed_confirmed'),
        ('recovery', '地面找回', 'recovery_complete')]
    return {'schema_version': 1, 'execution': 'desktop_reference', 'start_policy': 'separate', 'maximum_gap_ms': 1000, 'stages': [
        {'stage_id': identity, 'name': name,
         'condition': {'signal': 'event' if event else 'stage_elapsed_s',
                       'operator': 'is' if event else '>=', 'value': event if event else 0.0,
                       'unit': 'event_id' if event else 's'},
         'hold_ms': 0, 'action': {'kind': 'record_marker', 'target': ''}}
        for identity, name, event in definitions]}


def MissionProcess_Require(value, device_ids=None):
    _Keys_Require(value, ('schema_version', 'execution', 'start_policy', 'maximum_gap_ms', 'stages'))
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['execution'] != 'desktop_reference':
        raise ValueError('mission_process_version_or_execution')
    if value['start_policy'] not in ('separate', 'start_is_launch'):
        raise ValueError('mission_process_start_policy')
    if type(value['maximum_gap_ms']) is not int or not 1 <= value['maximum_gap_ms'] <= 60000:
        raise ValueError('mission_process_sample_gap')
    if type(value['stages']) is not list or not 1 <= len(value['stages']) <= 32:
        raise ValueError('mission_process_stage_count')
    identities = set()
    for stage in value['stages']:
        _Keys_Require(stage, ('stage_id', 'name', 'condition', 'hold_ms', 'action'))
        identity = stage['stage_id']
        if type(identity) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', identity) or identity in identities:
            raise ValueError('mission_process_stage_id')
        identities.add(identity)
        _Text_Require(stage['name'])
        condition = stage['condition']
        _Keys_Require(condition, ('signal', 'operator', 'value', 'unit'))
        signal = condition['signal']
        if type(signal) is not str or signal not in SIGNALS or condition['unit'] != SIGNALS[signal]:
            raise ValueError('mission_process_signal_or_unit')
        if signal == 'event':
            if condition['operator'] != 'is' or condition['value'] not in EVENTS or stage['hold_ms'] != 0:
                raise ValueError('mission_process_event')
        else:
            number = condition['value']
            if type(number) not in (float, int) or abs(number) > 1e7 or not math.isfinite(number):
                raise ValueError('mission_process_number')
            if condition['operator'] not in ('>=', '<=') or (signal == 'stage_elapsed_s' and (number < 0 or condition['operator'] != '>=')):
                raise ValueError('mission_process_operator')
        if type(stage['hold_ms']) is not int or not 0 <= stage['hold_ms'] <= 3600000:
            raise ValueError('mission_process_hold')
        action = stage['action']
        _Keys_Require(action, ('kind', 'target'))
        if action['kind'] not in ACTIONS or type(action['target']) is not str:
            raise ValueError('mission_process_action')
        if action['kind'] == 'request_recovery':
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', action['target']):
                raise ValueError('mission_process_target')
            if device_ids is not None and action['target'] not in device_ids:
                raise ValueError('mission_process_target_missing:' + action['target'])
        elif action['target']:
            raise ValueError('mission_process_target_unexpected')
    ascent = next((row for row in value['stages'] if row['stage_id'] == 'ascent'), None)
    if value['start_policy'] == 'start_is_launch' and ascent is not None:
        if ascent['condition'] != {'signal':'event','operator':'is','value':'start_accepted','unit':'event_id'} or ascent['hold_ms'] != 0:
            raise ValueError('mission_process_start_policy_condition_mismatch')
        if any(row['stage_id'] == 'mission_start' for row in value['stages']):
            raise ValueError('mission_process_start_policy_duplicate_stage')
    return deepcopy(value)


class MissionProcessRunner:
    """One transition per fresh sample; missing/invalid data clears a pending hold.

    Events must be authoritative producer events supplied in this sample. This
    interpreter does not infer ignition, apogee or landing from a name/GUI value.
    Action records are simulated requests, never completed hardware actions.
    """
    def __init__(self, process):
        self.process = MissionProcess_Require(process)
        self.index = -1
        self.entered_us = None
        self.last_time_us = None
        self.hold_start_us = None
        self.sequence = 0

    def Sample_Step(self, sample):
        _Keys_Require(sample, ('time_us', 'valid', 'events', 'altitude_agl_m', 'vertical_velocity_mps'))
        time_us = sample['time_us']
        if type(time_us) is not int or not 0 <= time_us < 2**64 or (self.last_time_us is not None and time_us <= self.last_time_us):
            raise ValueError('mission_process_time_not_monotonic')
        if type(sample['valid']) is not bool or type(sample['events']) is not list or len(sample['events']) > 32 or any(type(event) is not str or event not in EVENTS for event in sample['events']):
            raise ValueError('mission_process_sample')
        for key in ('altitude_agl_m', 'vertical_velocity_mps'):
            value = sample[key]
            if value is not None and (type(value) not in (int, float) or abs(value) > 1e7 or not math.isfinite(value)):
                raise ValueError('mission_process_sample_number')
        # Validation above is transactional: rejected input never advances time.
        if self.last_time_us is not None and time_us - self.last_time_us > self.process['maximum_gap_ms'] * 1000:
            self.hold_start_us = None
        self.last_time_us = time_us
        if self.index + 1 == len(self.process['stages']):
            return MissionProcessResult.Complete, []
        stage = self.process['stages'][self.index + 1]
        condition = stage['condition']
        if condition['signal'] == 'event':
            met = condition['value'] in sample['events']
        else:
            value = ((time_us - self.entered_us) / 1e6 if self.entered_us is not None else 0.0
                     ) if condition['signal'] == 'stage_elapsed_s' else sample[condition['signal']]
            met = value is not None and (value >= condition['value'] if condition['operator'] == '>=' else value <= condition['value'])
        if not sample['valid'] or not met:
            self.hold_start_us = None
            return MissionProcessResult.Waiting, []
        if self.hold_start_us is None:
            self.hold_start_us = time_us
        if time_us - self.hold_start_us < stage['hold_ms'] * 1000:
            return MissionProcessResult.Waiting, []
        self.index += 1
        self.entered_us = time_us
        self.hold_start_us = None
        records = [self._Record_Create(time_us, stage, 'stage_entered')]
        if stage['action']['kind'] != 'none':
            records.append(self._Record_Create(time_us, stage, 'simulated_action_request'))
        return MissionProcessResult.Entered, records

    def _Record_Create(self, time_us, stage, kind):
        self.sequence += 1
        return {'sequence': self.sequence, 'time_us': time_us, 'stage_id': stage['stage_id'],
                'kind': kind, 'action': deepcopy(stage['action'])}


def MissionTrace_Require(trace, profile):
    _Keys_Require(trace, ('schema_id', 'profile_sha256', 'session_id', 'source', 'events'))
    if trace['schema_id'] != 'silverstar.mission-trace/1' or trace['source'] != 'desktop_reference':
        raise ValueError('mission_trace_version_or_source')
    if trace['profile_sha256'] != profile['sha256'] or 'process' not in profile:
        raise ValueError('mission_trace_profile_mismatch')
    _Text_Require(trace['session_id'], 64)
    if type(trace['events']) is not list or len(trace['events']) > 10000:
        raise ValueError('mission_trace_size')
    stages = MissionProcess_Require(profile['process'])['stages']
    index, previous_time, previous_kind = -1, -1, None
    pending_action = False
    for sequence, event in enumerate(trace['events'], 1):
        _Keys_Require(event, ('sequence', 'time_us', 'stage_id', 'kind', 'action'))
        if type(event['sequence']) is not int or event['sequence'] != sequence:
            raise ValueError('mission_trace_sequence_gap')
        if type(event['time_us']) is not int or not max(0, previous_time) <= event['time_us'] < 2**64:
            raise ValueError('mission_trace_time')
        if event['kind'] == 'stage_entered':
            if pending_action or event['time_us'] <= previous_time:
                raise ValueError('mission_trace_transition_time_or_missing_action')
            index += 1
        elif event['kind'] != 'simulated_action_request' or previous_kind != 'stage_entered':
            raise ValueError('mission_trace_transition')
        if not 0 <= index < len(stages) or event['stage_id'] != stages[index]['stage_id'] or event['action'] != stages[index]['action']:
            raise ValueError('mission_trace_stage_or_action')
        if event['kind'] == 'simulated_action_request':
            if not pending_action or event['time_us'] != previous_time:
                raise ValueError('mission_trace_unexpected_action_or_time')
            pending_action = False
        else:
            pending_action = event['action']['kind'] != 'none'
        previous_time, previous_kind = event['time_us'], event['kind']
    if pending_action:
        raise ValueError('mission_trace_missing_action')
    return deepcopy(trace)
