"""Versioned actual-input parameter profiles; no executable content or hardware changes."""
from copy import deepcopy
from enum import Enum
import json
import os
import re
from pathlib import Path
import tempfile

from silverstar_fccg.plugins.algorithm_parameters import PARAMETER_SCHEMA_ID


class ParameterProfileResult(str, Enum):
    Ok = 'ok'
    Invalid = 'invalid'
    Conflict = 'conflict'
    IoError = 'io_error'


class ParameterProfileError(ValueError):
    def __init__(self, message, result=ParameterProfileResult.Invalid):
        self.result = result
        super().__init__(message)


def _Profile_Require(value):
    fields = {'schema_id','schema_version','plugin_id','plugin_version','manifest_sha256',
              'parameter_schema','value_source','parameters'}
    if type(value) is not dict or set(value) != fields:
        raise ParameterProfileError('parameter_profile_fields')
    if value['schema_id'] != 'silverstar.function-parameters/1' or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ParameterProfileError('parameter_profile_version')
    if value['parameter_schema'] != PARAMETER_SCHEMA_ID or value['value_source'] != 'project_actual_input':
        raise ParameterProfileError('parameter_profile_parameter_schema')
    if (type(value['plugin_id']) is not str or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,127}',value['plugin_id'])
            or type(value['plugin_version']) is not str or not re.fullmatch(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][A-Za-z0-9.-]+)?',value['plugin_version'])
            or type(value['manifest_sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}',value['manifest_sha256'])):
        raise ParameterProfileError('parameter_profile_identity')
    if type(value['parameters']) is not list or len(value['parameters']) > 128:
        raise ParameterProfileError('parameter_profile_count')
    identities = set()
    for item in value['parameters']:
        if type(item) is not dict or set(item) != {'id','value','unit','representation','storage_type'}:
            raise ParameterProfileError('parameter_profile_parameter_fields')
        if type(item['id']) is not str or item['id'] in identities:
            raise ParameterProfileError('parameter_profile_duplicate_parameter')
        identities.add(item['id'])
    try:
        data = json.dumps(value, allow_nan=False, ensure_ascii=False).encode('utf-8')
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise ParameterProfileError('parameter_profile_json') from error
    if len(data) > 262144:
        raise ParameterProfileError('parameter_profile_size')
    return deepcopy(value)


def ParameterProfile_Build(model, catalog, plugin_id):
    from silverstar_fccg.project.algorithm_parameters import AlgorithmParameterOwners_Get, AlgorithmParameters_Resolve
    owner = next((row for row in AlgorithmParameterOwners_Get(model,catalog) if row.component_id == plugin_id), None)
    if owner is None: raise ParameterProfileError('parameter_profile_owner_not_selected')
    AlgorithmParameters_Resolve(model,catalog)
    return {'schema_id':'silverstar.function-parameters/1','schema_version':1,
        'plugin_id':plugin_id,'plugin_version':owner.version,'manifest_sha256':owner.ManifestSha256_Get(),
        'parameter_schema':PARAMETER_SCHEMA_ID,'value_source':'project_actual_input',
        'parameters':[{'id':p.parameter_id,'value':deepcopy(model.algorithm_parameters[plugin_id][p.parameter_id]),
            'unit':p.unit,'representation':p.representation,'storage_type':'float32' if p.value_type=='float' else 'int32'}
            for p in owner.algorithm_parameters]}


def ParameterProfile_Apply(model, catalog, plugin_id, value):
    from silverstar_fccg.project.algorithm_parameters import AlgorithmParameterOwners_Get, AlgorithmParameters_Resolve
    profile = _Profile_Require(value)
    owner = next((row for row in AlgorithmParameterOwners_Get(model,catalog) if row.component_id==plugin_id),None)
    if owner is None: raise ParameterProfileError('parameter_profile_owner_not_selected')
    current = {'plugin_id':plugin_id,'plugin_version':owner.version,
               'manifest_sha256':owner.ManifestSha256_Get(),'parameter_schema':PARAMETER_SCHEMA_ID}
    if any(profile[key] != current[key] for key in current):
        raise ParameterProfileError('parameter_profile_identity_mismatch')
    supplied = {item['id']:item for item in profile['parameters']}
    if set(supplied) != {p.parameter_id for p in owner.algorithm_parameters}:
        raise ParameterProfileError('parameter_profile_missing_or_unknown_parameter')
    candidate = deepcopy(model)
    owners = AlgorithmParameterOwners_Get(candidate,catalog)
    candidate.algorithm_parameters[plugin_id] = {}
    for parameter in owner.algorithm_parameters:
        item = supplied[parameter.parameter_id]
        expected = {'unit':parameter.unit,'representation':parameter.representation,
                    'storage_type':'float32' if parameter.value_type=='float' else 'int32'}
        if any(item[key] != expected[key] for key in expected):
            raise ParameterProfileError('parameter_profile_unit_or_representation:' + parameter.parameter_id)
        parameter.Value_Resolve(item['value'])
        if parameter.lifecycle != 'active' and item['value'] != model.algorithm_parameters.get(plugin_id,{}).get(parameter.parameter_id,parameter.default):
            raise ParameterProfileError('parameter_profile_read_only:' + parameter.parameter_id)
        candidate.algorithm_parameters[plugin_id][parameter.parameter_id] = deepcopy(item['value'])
        if parameter.shared_key:
            for other in owners:
                for shared in other.algorithm_parameters:
                    if shared.shared_key == parameter.shared_key:
                        candidate.algorithm_parameters[other.component_id][shared.parameter_id] = deepcopy(item['value'])
    AlgorithmParameters_Resolve(candidate,catalog)
    return candidate


def ParameterProfile_Preview(model,catalog,plugin_id,value):
    candidate = ParameterProfile_Apply(model,catalog,plugin_id,value)
    changes = []
    for owner, parameters in candidate.algorithm_parameters.items():
        definitions = {p.parameter_id:p for p in catalog.Component_Get(owner).algorithm_parameters}
        for identity in dict.fromkeys([*parameters,*model.algorithm_parameters.get(owner,{})]):
            after = parameters.get(identity)
            before = model.algorithm_parameters.get(owner,{}).get(identity)
            if before != after:
                parameter = definitions.get(identity)
                changes.append({'plugin_id':owner,'parameter_id':identity,'before':deepcopy(before),
                    'after':deepcopy(after),'unit':parameter.unit if parameter is not None else 'unknown',
                    'shared':bool(parameter.shared_key) if parameter is not None else False})
    return changes


def _Pairs_Require(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ParameterProfileError('parameter_profile_duplicate_key')
        result[key] = value
    return result


def _Bytes_Read(path):
    with Path(path).open('rb') as stream: data = stream.read(262145)
    if len(data) > 262144: raise ParameterProfileError('parameter_profile_size')
    return data


def _Profile_Decode(data):
    try:
        return _Profile_Require(json.loads(data.decode('utf-8'),object_pairs_hook=_Pairs_Require))
    except (UnicodeError,json.JSONDecodeError,RecursionError) as error:
        raise ParameterProfileError('parameter_profile_json') from error


def ParameterProfile_Read(path):
    return _Profile_Decode(_Bytes_Read(path))


def ParameterProfile_Write(path,value,replace_existing=False):
    value = _Profile_Require(value); target = Path(path); previous = None
    if target.exists():
        if not replace_existing: raise ParameterProfileError('parameter_profile_exists',ParameterProfileResult.Conflict)
        previous = _Bytes_Read(target); _Profile_Decode(previous)
    data = (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
    if len(data) > 262144: raise ParameterProfileError('parameter_profile_size')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.parameters-',delete=False) as stream:
            temporary = Path(stream.name);stream.write(data);stream.flush();os.fsync(stream.fileno())
        if (previous is None and target.exists()) or (previous is not None and _Bytes_Read(target)!=previous):
            raise ParameterProfileError('parameter_profile_changed',ParameterProfileResult.Conflict)
        if previous is not None:
            backup = target.with_suffix(target.suffix+'.bak')
            backup_temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.parameters-backup-',delete=False) as stream:
                    backup_temporary=Path(stream.name);stream.write(previous);stream.flush();os.fsync(stream.fileno())
                os.replace(backup_temporary,backup)
            finally:
                if backup_temporary is not None: backup_temporary.unlink(missing_ok=True)
        os.replace(temporary,target)
        return ParameterProfileResult.Ok
    except OSError as error:
        raise ParameterProfileError(str(error),ParameterProfileResult.IoError) from error
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
