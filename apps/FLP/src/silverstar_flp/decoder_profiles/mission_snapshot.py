"""Recorded SSOB/SSMS views admitted only after exact log/decoder matching.

Never opens live-device storage or selects a newer snapshot than the recorded
identity. An unavailable auxiliary object cannot invalidate the original log.
"""
from dataclasses import replace
import hashlib
import math
from pathlib import Path

from . import object_catalog  # fixed trusted shared package import boundary
from silverstar_data_contracts.objects import (
    MissionSnapshotSection_Decode, PersistentObject_Decode, SnapshotHash_Get,
)


def _Object_Read(directory, instance, generation, expected_hash=None):
    candidates = []
    for slot in range(2):
        path = directory / f'snap{instance:02d}.{slot}'
        if not path.exists(): continue
        resolved = path.resolve()
        if not resolved.is_relative_to(directory) or path.is_symlink():
            raise ValueError('snapshot_path_escape')
        with path.open('rb') as stream:
            raw = stream.read(531)
        try:
            value = PersistentObject_Decode(raw)
        except ValueError:
            continue  # The other atomic slot may contain the recorded commit.
        if (value['kind'] != 4 or value['instance'] != instance or value['generation'] != generation):
            continue
        if expected_hash is not None and SnapshotHash_Get(value['payload']) != expected_hash:
            continue
        candidates.append((value['payload'], {'path':str(resolved),
            'sha256':hashlib.sha256(raw).hexdigest(),'generation':generation,'instance':instance}))
    if not candidates: raise ValueError('snapshot_exact_object_missing_or_invalid')
    if any(payload != candidates[0][0] for payload,_ in candidates[1:]):
        raise ValueError('snapshot_same_generation_conflict')
    return candidates[0]


def MissionSnapshot_Read(directory: Path, identity, *, object_catalog=None):
    directory = directory.resolve()
    names = ('mission_id','commit_generation','snapshot_sequence','imu_calibration_generation',
             'mag_calibration_set_hash','base_instance','ready')
    if any(type(identity.get(name)) is not int for name in names):
        raise ValueError('snapshot_record_identity')
    if identity['ready'] != 1 or identity['base_instance'] not in (0,8) or identity.get('reserved',0) != 0:
        raise ValueError('snapshot_record_not_ready')
    payload, source = _Object_Read(directory,identity['base_instance'],identity['commit_generation'])
    root = MissionSnapshotSection_Decode(payload)
    if root['section'] != 0: raise ValueError('snapshot_commit_section')
    header = root['header']
    comparisons = {'mission_id':'mission_id','snapshot_sequence':'snapshot_sequence',
        'base_instance':'base_instance','calibration_generation':'imu_calibration_generation',
        'mag_calibration_set_hash':'mag_calibration_set_hash'}
    if any(header[left] != identity[right] for left,right in comparisons.items()):
        raise ValueError('snapshot_log_identity_mismatch')
    if root['radio']['family'] == 'sx127x':
        types = {item['type_id'] for item in (object_catalog or {}).get('objects',())}
        if 'ssms.radio.sx1278.v1' not in types:
            raise ValueError('snapshot_radio_catalog_missing')
    header['commit_generation'] = identity['commit_generation']
    result = {'status':'verified','reason':'recorded_identity_and_six_section_hashes',
        'header':header,'radio':root['radio'],'alignment':root['alignment'],
        'devices':[],'algorithms':[],'parameters':[],'sources':[source]}
    for index, reference in enumerate(root['references'],1):
        data, source = _Object_Read(directory,header['base_instance']+index,
                                    reference['generation'],reference['hash'])
        section = MissionSnapshotSection_Decode(data)
        if section['section'] != index or section['schema'] != root['schema']:
            raise ValueError('snapshot_section_identity')
        result['sources'].append(source)
        if index in (1,2): result['devices'].extend(section['rows'])
        elif index == 3: result['algorithms'] = section['rows']
        elif index in (4,5): result['parameters'].extend(section['rows'])
        else:
            result['calibration'] = section['calibration']
            calibration = section['calibration']
            if (calibration['generation'] != header['calibration_generation'] or
                    calibration['mag_set_hash'] != header['mag_calibration_set_hash'] or
                    SnapshotHash_Get(data[:62]) != header['imu_correction_hash']):
                raise ValueError('snapshot_calibration_identity')
            active = calibration.get('active_installation')
            if active is not None:
                types = {item['type_id'] for item in (object_catalog or {}).get('objects',())}
                if 'ssic.active.packet' not in types or 'ssms.configuration.v4.prefix' not in types:
                    raise ValueError('snapshot_active_catalog_missing')
                if active['imu']['configuration_digest'] != header['configuration_digest']:
                    raise ValueError('snapshot_active_configuration')
                for key in ('imu','magnetometer'):
                    recorded = active[key]
                    if not any(all(device[field] == recorded[field] for field in
                        ('descriptor','physical','instance','driver_hash','model_hash')) for device in result['devices']):
                        raise ValueError('snapshot_active_device_identity')
                for axis, recorded in enumerate(calibration['axes']):
                    for field in ('accel_bias_mps2','accel_scale','gyro_bias_radps'):
                        if not math.isclose(recorded[field],active[field][axis],rel_tol=1e-6,abs_tol=1e-8):
                            raise ValueError('snapshot_active_baseline_mismatch')
                calibration['effective_mode'] = 'recorded_active_installation'
    return result


def _ParameterDictionary_Build(groups, recorded):
    """Names and units come from the exact decoder. Values remain recorded facts."""
    candidates = {}
    for group in groups:
        for parameter in group['parameters']:
            key = group['component'] + '/' + parameter['id']
            digest = SnapshotHash_Get(key.encode('utf-8'))
            kind = {'float32': 1, 'int32': 2}.get(parameter['storage_type'])
            entry = (kind, {'component': group['component'], 'name': parameter['id'], 'unit': parameter['unit']})
            candidates[digest] = None if digest in candidates else entry
    labels = {}
    for row in recorded:
        entry = candidates.get(row['key_hash'])
        if entry and entry[0] == row['kind']:
            labels[str(row['key_hash'])] = entry[1]
    return labels


def MissionSnapshot_Attach(dataset, package):
    identities = [item for item in dataset.Records_Get('MISSION_SNAPSHOT_IDENTITY')
                  if item.payload.get('ready') == 1]
    result = {'status':'unavailable','reason':'snapshot_identity_not_recorded'}
    if identities:
        identity = max(identities,key=lambda item:item.timestamp_us).payload
        try:
            result = MissionSnapshot_Read(dataset.source_path.parent,identity,
                                           object_catalog=package.object_catalog)
            result['parameter_dictionary'] = _ParameterDictionary_Build(
                package.semantics.raw_metadata.get('firmware_algorithm_parameters', ()), result['parameters'])
        except (ValueError,OSError,KeyError,UnicodeError) as error:
            result = {'status':'invalid','reason':str(error)}
    return replace(dataset,metadata={**dataset.metadata,'mission_snapshot':result})
