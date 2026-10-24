"""Portable, data-only mission-profile validation and atomic persistence."""
import argparse
from copy import deepcopy
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import runpy
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts/mission_profile_v1.json").read_text(encoding="utf-8"))
_PROCESS = runpy.run_path(str(ROOT / 'tools/silverstar_mission_process.py'))
MissionProcess_Default = _PROCESS['MissionProcess_Default']
MissionProcess_Require = _PROCESS['MissionProcess_Require']
MissionProcessRunner = _PROCESS['MissionProcessRunner']
MissionTrace_Require = _PROCESS['MissionTrace_Require']


class MissionProfileResult(str, Enum):
    Ok = "ok"
    Invalid = "invalid_profile"
    IoError = "io_error"
    Conflict = "conflict"


class MissionProfileError(ValueError):
    def __init__(self, message, result=MissionProfileResult.Invalid):
        self.result = result
        super().__init__(message)


def _Keys_Require(value, keys, location):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise MissionProfileError("mission_profile_fields:" + location)


def _Text_Require(value):
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise MissionProfileError("mission_profile_text")


def _Number_Require(value, integer=False, minimum=None):
    if type(value) not in (int, float) or (integer and type(value) is not int):
        raise MissionProfileError("mission_profile_number")
    if type(value) is int and value.bit_length() > 64:
        raise MissionProfileError("mission_profile_number_range")
    if type(value) is float and not math.isfinite(value):
        raise MissionProfileError("mission_profile_number")
    if minimum is not None and value < minimum:
        raise MissionProfileError("mission_profile_number_range")


def MissionProfile_Digest(value):
    body = {key: item for key, item in value.items() if key != "sha256"}
    try:
        data = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise MissionProfileError("mission_profile_json") from error
    if len(data) > CONTRACT["maximum_bytes"]:
        raise MissionProfileError("mission_profile_size")
    return hashlib.sha256(data).hexdigest()


def _Component_Require(value):
    if value is None:
        return
    _Keys_Require(value, ("plugin_id", "version"), "component")
    for item in value.values():
        _Text_Require(item)
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", value["plugin_id"]):
        raise MissionProfileError("mission_profile_component")


def MissionProfile_Require(value):
    if type(value) is not dict or type(value.get('schema_version')) is not int or value['schema_version'] not in (1, 2):
        raise MissionProfileError('mission_profile_version')
    version = value['schema_version']
    _Keys_Require(value, [*CONTRACT['fields'], *(['process', 'devices'] if version == 2 else [])], 'root')
    if value["schema_id"] != 'silverstar.mission-profile/' + str(version):
        raise MissionProfileError("mission_profile_version")
    if version == 2:
        devices = value['devices']
        if type(devices) is not list or len(devices) > 128:
            raise MissionProfileError('mission_profile_devices')
        identities = set()
        recovery_targets = set()
        for device in devices:
            _Keys_Require(device, ('instance_id', 'plugin_id', 'recovery_action'), 'device')
            if type(device['instance_id']) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', device['instance_id']) or device['instance_id'] in identities:
                raise MissionProfileError('mission_profile_device_id')
            _Text_Require(device['plugin_id'])
            if type(device['recovery_action']) is not bool:
                raise MissionProfileError('mission_profile_device_capability')
            identities.add(device['instance_id'])
            if device['recovery_action']:
                recovery_targets.add(device['instance_id'])
        try:
            MissionProcess_Require(value['process'], recovery_targets)
        except (ValueError, TypeError) as error:
            raise MissionProfileError(str(error)) from error
    if value["source"] != "scg_project" or value["frame"] != CONTRACT["frame"]:
        raise MissionProfileError("mission_profile_frame_or_source")
    if value["lifecycle"] != {"template_id": CONTRACT["lifecycle_template"], "states": CONTRACT["states"]}:
        raise MissionProfileError("mission_profile_lifecycle")
    if any(type(row["state_id"]) is not int for row in value["lifecycle"]["states"]):
        raise MissionProfileError("mission_profile_lifecycle")
    if value["qualification"] != CONTRACT["qualification"] or type(value["qualification"]["hardware_tested"]) is not bool:
        raise MissionProfileError("mission_profile_qualification")
    _Keys_Require(value["project"], ("name", "firmware_version", "generator_version", "mcu", "board"), "project")
    for item in value["project"].values():
        _Text_Require(item)
    rules = value["rules"]
    if not isinstance(rules, list) or len(rules) > CONTRACT["maximum_rules"]:
        raise MissionProfileError("mission_profile_rules")
    seen = set()
    for rule in rules:
        _Keys_Require(rule, ("owner", "slot", "option", "enabled", "parameters"), "rule")
        _Component_Require(rule["owner"])
        if rule["owner"] is None or type(rule["enabled"]) is not bool:
            raise MissionProfileError("mission_profile_rule")
        for key in ("slot", "option"):
            _Text_Require(rule[key])
        if rule['owner'] != CONTRACT['rule_owner'] or rule['slot'] != 'deployment' or rule['option'] not in CONTRACT['rule_parameters']:
            raise MissionProfileError('mission_profile_rule_version_or_mapping')
        identity = (rule["slot"], rule["option"])
        if identity in seen:
            raise MissionProfileError("mission_profile_duplicate_rule")
        seen.add(identity)
        parameters = rule["parameters"]
        if not isinstance(parameters, list) or len(parameters) > CONTRACT["maximum_parameters_per_rule"]:
            raise MissionProfileError("mission_profile_parameters")
        if len(parameters) != 1:
            raise MissionProfileError('mission_profile_parameter_count')
        names = set()
        for parameter in parameters:
            _Keys_Require(parameter, ("id", "type", "value", "unit", "minimum", "maximum", "generated_symbol", "generated_scale"), "parameter")
            for key in ("id", "unit", "generated_symbol"):
                _Text_Require(parameter[key])
            if parameter["id"] in names or not re.fullmatch(r"[A-Z][A-Z0-9_]*", parameter["generated_symbol"]):
                raise MissionProfileError("mission_profile_parameter_identity")
            names.add(parameter["id"])
            if any(parameter.get(key) != item for key, item in CONTRACT['rule_parameters'][rule['option']].items()):
                raise MissionProfileError('mission_profile_parameter_unit_or_mapping')
            if parameter["type"] not in ("float", "integer"):
                raise MissionProfileError("mission_profile_parameter_type")
            _Number_Require(parameter["value"], integer=parameter["type"] == "integer")
            for key in ("minimum", "maximum", "generated_scale"):
                _Number_Require(parameter[key])
            if not parameter["minimum"] <= parameter["value"] <= parameter["maximum"] or parameter["generated_scale"] <= 0:
                raise MissionProfileError("mission_profile_parameter_range")
    continuous = value["continuous"]
    _Keys_Require(continuous, ("ins", "estimator", "landing", "logging"), "continuous")
    for key in ("ins", "estimator", "landing"):
        _Component_Require(continuous[key])
    streams = continuous["logging"]
    if not isinstance(streams, list) or len(streams) > CONTRACT["maximum_log_streams"]:
        raise MissionProfileError("mission_profile_logging")
    records = set()
    for row in streams:
        _Keys_Require(row, ("record", "enabled", "policy", "decimation", "period_us"), "logging")
        _Text_Require(row["record"])
        if row["record"] in records or type(row["enabled"]) is not bool or row["policy"] not in CONTRACT["logging_policies"]:
            raise MissionProfileError("mission_profile_logging_identity")
        records.add(row["record"])
        _Number_Require(row["decimation"], integer=True, minimum=1)
        _Number_Require(row["period_us"], integer=True, minimum=0)
        if row["decimation"] > 65535 or row["period_us"] > 0xFFFFFFFF:
            raise MissionProfileError("mission_profile_logging_range")
    if value["sha256"] != MissionProfile_Digest(value):
        raise MissionProfileError("mission_profile_integrity")
    return deepcopy(value)


def _Pairs_Require(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise MissionProfileError("mission_profile_duplicate_key")
        output[key] = value
    return output


def _Bytes_Read(path):
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(CONTRACT["maximum_bytes"] + 1)
        if len(data) > CONTRACT["maximum_bytes"]:
            raise MissionProfileError("mission_profile_size")
        return data
    except OSError as error:
        raise MissionProfileError(str(error), MissionProfileResult.IoError) from error


def _Profile_Decode(data):
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=_Pairs_Require)
        return MissionProfile_Require(value)
    except (json.JSONDecodeError, UnicodeError, RecursionError) as error:
        raise MissionProfileError("mission_profile_json") from error


def MissionProfile_Read(path):
    return _Profile_Decode(_Bytes_Read(path))


def MissionTrace_Read(path, profile):
    validated = MissionProfile_Require(profile)
    try:
        value = json.loads(_Bytes_Read(path).decode('utf-8'), object_pairs_hook=_Pairs_Require)
        return MissionTrace_Require(value, validated)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise MissionProfileError('mission_trace_json') from error


def MissionTrace_Write(path, trace, profile):
    validated = MissionTrace_Require(trace, MissionProfile_Require(profile))
    target = Path(path)
    if target.suffix != '.ssmissiontrace' or target.exists():
        raise MissionProfileError('mission_trace_new_path_required', MissionProfileResult.Conflict)
    data = (json.dumps(validated, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(data) > CONTRACT['maximum_bytes']:
        raise MissionProfileError('mission_trace_size')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.mission-trace-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if target.exists():
            raise MissionProfileError('mission_trace_path_changed', MissionProfileResult.Conflict)
        os.replace(temporary, target)
        return MissionProfileResult.Ok
    except OSError as error:
        raise MissionProfileError(str(error), MissionProfileResult.IoError) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def MissionProfile_Write(path, value, replace_existing=False):
    validated = MissionProfile_Require(value)
    target = Path(path)
    previous = None
    if target.exists():
        if not replace_existing:
            raise MissionProfileError("mission_profile_exists", MissionProfileResult.Conflict)
        previous = _Bytes_Read(target)
        _Profile_Decode(previous)
    data = (json.dumps(validated, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(data) > CONTRACT['maximum_bytes']:
        raise MissionProfileError('mission_profile_size')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".mission-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if (previous is None and target.exists()) or (previous is not None and _Bytes_Read(target) != previous):
            raise MissionProfileError("mission_profile_changed", MissionProfileResult.Conflict)
        if previous is not None:
            backup = target.with_suffix(target.suffix + ".bak")
            backup_temp = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".mission-backup-", delete=False) as stream:
                    backup_temp = Path(stream.name)
                    stream.write(previous); stream.flush(); os.fsync(stream.fileno())
                os.replace(backup_temp, backup)
            finally:
                if backup_temp is not None:
                    backup_temp.unlink(missing_ok=True)
        os.replace(temporary, target)
        return MissionProfileResult.Ok
    except OSError as error:
        raise MissionProfileError(str(error), MissionProfileResult.IoError) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def MissionProfile_Main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    options = parser.parse_args()
    try:
        profile = MissionProfile_Read(options.profile)
        print(json.dumps(profile, ensure_ascii=True, indent=2))
    except MissionProfileError as error:
        parser.exit(2, str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(MissionProfile_Main())
