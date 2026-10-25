"""Portable declarative bindings. No algorithm dispatch or hardware operations."""
from copy import deepcopy
import re

BOUNDARIES = ('system_prepare', 'mission_start', 'stage_enter', 'system_landed', 'lifecycle_end')
CATEGORIES = ('estimation', 'preparation', 'control', 'recording', 'telemetry')


def _Keys_Require(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError('mission_functions_fields')


def _Id_Require(value, *, empty=False):
    if type(value) is not str or (value == '' and not empty) or (value and not re.fullmatch(r'[a-z][a-z0-9_.-]{0,127}', value)):
        raise ValueError('mission_functions_identity')


def Functions_Require(value):
    """Validate structure, retaining unresolved boundaries as repairable drafts."""
    _Keys_Require(value, ('schema_version', 'functions'))
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('mission_functions_version')
    if type(value['functions']) is not list or len(value['functions']) > 32:
        raise ValueError('mission_functions_count')
    identities = set()
    for function in value['functions']:
        _Keys_Require(function, ('instance_id', 'plugin_id', 'category', 'execution', 'start', 'stop',
                                 'depends_on', 'input_bindings', 'output'))
        _Id_Require(function['instance_id']); _Id_Require(function['plugin_id']); _Id_Require(function['output'])
        if function['instance_id'] in identities:
            raise ValueError('mission_functions_duplicate_instance')
        identities.add(function['instance_id'])
        if function['category'] not in CATEGORIES or function['execution'] not in ('once', 'continuous'):
            raise ValueError('mission_functions_execution_or_category')
        for key in ('start', 'stop'):
            boundary = function[key]
            _Keys_Require(boundary, ('kind', 'stage_id'))
            if boundary['kind'] not in BOUNDARIES:
                raise ValueError('mission_functions_boundary_kind')
            _Id_Require(boundary['stage_id'], empty=True)
            if boundary['kind'] != 'stage_enter' and boundary['stage_id']:
                raise ValueError('mission_functions_unexpected_stage')
        if type(function['depends_on']) is not list or len(function['depends_on']) > 32:
            raise ValueError('mission_functions_dependencies')
        for identity in function['depends_on']: _Id_Require(identity)
        if len(set(function['depends_on'])) != len(function['depends_on']):
            raise ValueError('mission_functions_duplicate_dependency')
        if type(function['input_bindings']) is not dict or len(function['input_bindings']) > 64:
            raise ValueError('mission_functions_inputs')
        for capability, device in function['input_bindings'].items():
            _Id_Require(capability); _Id_Require(device)
    return deepcopy(value)


def BoundaryIndex_Get(boundary, stage_ids):
    kind = boundary['kind']
    if kind == 'stage_enter':
        return stage_ids.index(boundary['stage_id']) if boundary['stage_id'] in stage_ids else None
    if kind == 'system_landed':
        return stage_ids.index('landed') if 'landed' in stage_ids else len(stage_ids)
    return {'system_prepare': -2, 'mission_start': -1, 'lifecycle_end': len(stage_ids)}[kind]


def FunctionCoverage_Get(function, stage_ids):
    """Start inclusive, stop exclusive. A stop marker is displayed separately."""
    start, stop = (BoundaryIndex_Get(function[key], stage_ids) for key in ('start', 'stop'))
    result = {}
    if start is None or stop is None or start >= stop:
        return result
    if function['start']['kind'] == 'mission_start':
        # Display marker only. Initialization and runtime START stay independent.
        if 'mission_start' not in stage_ids:
            return {stage_ids[stop]: 'stop'} if 0 <= stop < len(stage_ids) else {}
        start = stage_ids.index('mission_start')
    for index, identity in enumerate(stage_ids):
        if index == stop:
            result[identity] = 'stop'
        elif index == start:
            result[identity] = 'start' if function['execution'] == 'continuous' else 'once'
        elif function['execution'] == 'continuous' and start < index < stop:
            result[identity] = 'active'
    return result


class FunctionsReferenceRunner:
    """Reference requests only: stop, start, then one active set per snapshot.

    Preparation and accepted START are supplied independently of phase entry.
    Once tasks remain pending until explicit completion/failure is reported.
    No computation, physical completion or firmware support is inferred.
    """
    def __init__(self, configuration, stage_ids):
        self.functions = Functions_Require(configuration)['functions']
        self.stage_ids = tuple(stage_ids)
        if len(self.stage_ids) > 32 or len(set(self.stage_ids)) != len(self.stage_ids):
            raise ValueError('mission_functions_stages')
        for function in self.functions:
            start, stop = (BoundaryIndex_Get(function[key],self.stage_ids) for key in ('start','stop'))
            if start is None or stop is None or start >= stop:
                raise ValueError('mission_functions_invalid_reference_interval')
        self.started, self.stopped, self.completed = set(), set(), {}
        self.last_time_us = None
        self.last_stage_index = -3

    def Snapshot_Step(self, time_us, *, stage_id='', system_prepared=False, mission_started=False):
        if type(time_us) is not int or not 0 <= time_us < 2**64 or (self.last_time_us is not None and time_us <= self.last_time_us):
            raise ValueError('mission_functions_time_not_monotonic')
        if type(stage_id) is not str or type(system_prepared) is not bool or type(mission_started) is not bool or (stage_id and stage_id not in self.stage_ids):
            raise ValueError('mission_functions_snapshot')
        stage_index = self.stage_ids.index(stage_id) if stage_id else self.last_stage_index
        if stage_index < self.last_stage_index:
            raise ValueError('mission_functions_stage_not_monotonic')
        def Reached(boundary):
            if boundary['kind'] == 'system_prepare': return system_prepared
            if boundary['kind'] == 'mission_start': return mission_started
            if boundary['kind'] == 'lifecycle_end': return False
            if boundary['kind'] == 'system_landed':
                return 'landed' in self.stage_ids and stage_index >= self.stage_ids.index('landed')
            boundary_index = BoundaryIndex_Get(boundary, self.stage_ids)
            return boundary_index is not None and stage_index >= boundary_index
        started, stopped = [], []
        for function in self.functions:
            identity = function['instance_id']
            if Reached(function['stop']) and identity not in self.stopped:
                self.stopped.add(identity)
                if identity in self.started: stopped.append(identity)
        for _pass in range(len(self.functions)):
            previous_count = len(started)
            for function in self.functions:
                identity = function['instance_id']
                if identity not in self.started | self.stopped and Reached(function['start']):
                    if all(dep in self.started and dep not in self.stopped for dep in function['depends_on']):
                        self.started.add(identity); started.append(identity)
            if len(started) == previous_count: break
        self.last_time_us = time_us
        self.last_stage_index = stage_index
        active = [f['instance_id'] for f in self.functions if f['execution'] == 'continuous'
                  and f['instance_id'] in self.started - self.stopped]
        return {'source': 'desktop_reference', 'stop_requests': stopped, 'start_requests': started,
                'active': active, 'pending_once': [f['instance_id'] for f in self.functions
                    if f['execution'] == 'once' and f['instance_id'] in self.started - self.stopped
                    and f['instance_id'] not in self.completed]}

    def Completion_Report(self, instance_id, result):
        once = {row['instance_id'] for row in self.functions if row['execution']=='once'}
        if instance_id not in once or instance_id not in self.started or instance_id in self.completed or result not in ('completed', 'failed'):
            raise ValueError('mission_functions_completion')
        self.completed[instance_id] = result
