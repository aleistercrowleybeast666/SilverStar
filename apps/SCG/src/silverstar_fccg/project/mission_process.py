"""Trusted shared process contract; no GUI and no device I/O."""
from pathlib import Path
import runpy
import sys
import zlib

_ROOT = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[5]
_API = runpy.run_path(str(_ROOT / 'tools/silverstar_mission_process.py'))
MissionProcess_Default = _API['MissionProcess_Default']
MissionProcess_FirmwareDefault = _API['MissionProcess_FirmwareDefault']
MissionProcess_Require = _API['MissionProcess_Require']
MissionProcessRunner = _API['MissionProcessRunner']
SIGNALS = _API['SIGNALS']
EVENTS = _API['EVENTS']
ACTIONS = _API['ACTIONS']


def MissionProcessFirmware_Require(model, catalog=None):
    process = MissionProcess_Require(model.mission_process or MissionProcess_FirmwareDefault())
    if process['execution'] != 'firmware_bounded':
        raise ValueError('MISSION_PROCESS_REFERENCE_ONLY: explicitly select a firmware template; desktop evidence is not executable')
    recovery = []
    identities = set()
    mission_started = False
    terminal = False
    for stage in process['stages']:
        identity = zlib.crc32(stage['stage_id'].encode('ascii'))
        if identity == 0 or identity in identities:
            raise ValueError('MISSION_PROCESS_STAGE_ID_HASH:' + stage['stage_id'])
        identities.add(identity)
        condition = stage['condition']
        if condition['signal'] == 'event':
            mission_started |= condition['value'] in ('start_accepted', 'apogee_confirmed', 'deployment_confirmed', 'landed_confirmed', 'recovery_complete')
            terminal |= condition['value'] in ('landed_confirmed', 'recovery_complete')
        elif condition['signal'] != 'stage_elapsed_s':
            mission_started = True  # MCU numeric conditions require accepted START.
        if stage['action']['kind'] == 'request_recovery':
            if not mission_started or terminal:
                raise ValueError('MISSION_PROCESS_ACTION_LIFECYCLE:' + stage['stage_id'] + ': recovery requires a preceding or current flight condition')
            recovery.append(stage)
        if stage['condition']['signal'] == 'event' and stage['condition']['value'] in ('launch_detected', 'burnout_detected'):
            raise ValueError('MISSION_PROCESS_EVENT_SOURCE: use an explicit acceleration_g condition for launch/burnout detection')
    if len(recovery) > 1:
        raise ValueError('MISSION_PROCESS_ACTION_OWNER: only one recovery request is permitted')
    if model.mission_process is not None:
        for stage in process['stages']:
            condition = stage['condition']
            if condition['signal'] != 'event': continue
            if not recovery and condition['value'] in ('apogee_confirmed', 'deployment_confirmed', 'landed_confirmed'):
                raise ValueError('MISSION_PROCESS_EVENT_SOURCE:' + stage['stage_id'] + ': this recovery event requires a configured recovery owner')
            if condition['value'] == 'apogee_confirmed' and 'ApogeeVerticalVelocity' not in model.modes.get('deployment', []):
                raise ValueError('MISSION_PROCESS_EVENT_SOURCE:' + stage['stage_id'] + ': enable the authoritative apogee deployment condition')
            if condition['value'] == 'landed_confirmed' and not model.strategies.get('landing'):
                raise ValueError('MISSION_PROCESS_EVENT_SOURCE:' + stage['stage_id'] + ': no landing strategy selected')
    if recovery and catalog is not None:
        from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
        routes = CapabilityResolution_Resolve(model, catalog).routes
        target = recovery[0]['action']['target']
        if not any(route.requirement.capability == 'actuator.mission_action.parachute_deploy' and route.provider.instance_id == target for route in routes):
            raise ValueError('MISSION_PROCESS_ACTION_TARGET:' + recovery[0]['stage_id'] + ': target must be the configured parachute output: ' + target)
    return process
