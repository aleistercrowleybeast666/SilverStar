"""Small bounded diagnostics-shaped artifacts; no replay or real-log parsing."""
import gzip
import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from types import MappingProxyType

import numpy as np
import pytest

from silverstar_flp.core.artifacts import Artifact_Read, Artifact_Write, FileHash_Get


def _Audit(rows=800):
    nan = np.array([0x7ff8000000000123], dtype=np.uint64).view(np.float64)[0].item()
    return {
        'measurement_events': tuple({'timestamp_us': i*10000, 'accepted': i%2 == 0,
            'innovation': (float(i), -0.0 if i%2 else 0.0, nan),
            'nis': float('inf') if i%11 == 0 else float(i)/7,
            'covariance': np.arange(9, dtype=np.float32).reshape(3,3) + i,
            'reason': 'accepted' if i%2 == 0 else 'gate_rejected'} for i in range(rows)),
        'gnss_group_updates': [{'timestamp_us': i*10000, 'unit': 'm/s',
            'group': {'dimension': 3, 'source': 'GNSS', 'values': [float(i), None, float(i+1)]},
            'extra': None} if i%2 else {'unit': 'm/s', 'timestamp_us': i*10000,
            'group': {'dimension': 3, 'source': 'GNSS', 'values': [float(i), None, float(i+1)]}}
            for i in range(rows)],
        'mechanization_verification': {'passed': False, 'intervals': tuple({
            'timestamp_us': i*10000, 'source_sequence': i,
            'delta_theta_difference': (np.float32(i), np.float64(nan), np.int16(-i)),
            'delta_velocity_difference': [float(i), float(-i), -0.0],
            'passed': i%2 == 0, 'flags': MappingProxyType({'axis': 'ENU', 'enabled': True})}
            for i in range(rows)), 'first_divergence': None},
        'metadata': {'state_layout': ('position', 'velocity'), 'unit': '1', 'quantity': 'dimensionless'},
    }


def _Fingerprint(value):
    digest = hashlib.sha256()
    def add(item):
        if isinstance(item, np.ndarray):
            digest.update(b'array'+item.dtype.str.encode()+repr(item.shape).encode()+item.tobytes())
        elif isinstance(item, np.generic):
            digest.update(b'scalar'+item.dtype.str.encode()+item.tobytes())
        elif isinstance(item, Mapping):
            digest.update(b'frozen' if isinstance(item, MappingProxyType) else b'dict')
            for key, child in item.items(): add(key); add(child)
            digest.update(b'end-map')
        elif isinstance(item, (tuple, list)):
            digest.update(b'tuple' if isinstance(item, tuple) else b'list')
            for child in item: add(child)
            digest.update(b'end-sequence')
        elif type(item) is float:
            digest.update(b'float'+struct.pack('<d', item))
        elif is_dataclass(item):
            digest.update(type(item).__name__.encode())
            for field in fields(item): add(getattr(item, field.name))
        else:
            digest.update(type(item).__name__.encode()+repr(item).encode())
    add(value)
    return digest.hexdigest()


def _Bytes_Json(value):
    if type(value) is bytes:
        return {'bytes': value.hex()}
    raise TypeError(type(value).__name__)


def test_diagnostics_shaped_collections_fit_original_cumulative_budget(tmp_path, monkeypatch):
    import silverstar_flp.core.artifacts as codec
    original = _Audit()
    monkeypatch.setattr(codec, 'MAX_OBJECTS', 12000)
    reference = Artifact_Write(tmp_path/'flight.ssflp', original, {'scope':'synthetic-diagnostics'})
    restored = Artifact_Read(tmp_path/'flight.ssflp', reference, {'scope':'synthetic-diagnostics'})
    assert _Fingerprint(original) == _Fingerprint(restored)
    assert isinstance(restored['measurement_events'], tuple)
    assert isinstance(restored['gnss_group_updates'], list)
    row = restored['gnss_group_updates'][0]
    assert dict(row) == dict(original['gnss_group_updates'][0])
    assert list(row.keys()) == list(original['gnss_group_updates'][0])
    assert list(row.values()) == list(original['gnss_group_updates'][0].values())
    assert row.get('missing', 42) == 42 and 'extra' not in row and len(row) == 3
    assert json.dumps(row) == json.dumps(original['gnss_group_updates'][0])
    assert row.copy() == original['gnss_group_updates'][0]
    assert row | {'new': 1} == original['gnss_group_updates'][0] | {'new': 1}
    for mutate in (lambda: row.update(new=1), lambda: row.clear(), lambda: row.pop('unit'),
                   lambda: row.setdefault('new', 1)):
        with pytest.raises(TypeError, match='read_only'): mutate()
    with pytest.raises(ValueError):
        restored['measurement_events'][0]['covariance'][0,0] = 999
    # Saving the restored row views must retain the same complete typed data too.
    again = Artifact_Write(tmp_path/'copy.ssflp', restored, {'scope':'synthetic-diagnostics'})
    assert _Fingerprint(Artifact_Read(tmp_path/'copy.ssflp', again)) == _Fingerprint(original)


@pytest.mark.parametrize('budget', ['objects', 'memory', 'blocks'])
def test_audit_admission_keeps_cumulative_caps(tmp_path, monkeypatch, budget):
    import silverstar_flp.core.artifacts as codec
    if budget == 'objects': monkeypatch.setattr(codec, 'MAX_OBJECTS', 1500)
    elif budget == 'memory': monkeypatch.setattr(codec, 'MAX_LIVE_BYTES', 64000)
    else: monkeypatch.setattr(codec, 'MAX_RECORD_BLOCKS', 1)
    with pytest.raises(ValueError, match='limit'):
        Artifact_Write(tmp_path/'flight.ssflp', _Audit(), {})


@pytest.mark.parametrize('fault', ['corrupt', 'size', 'path', 'version'])
def test_audit_block_hash_path_expanded_size_and_version_are_strict(tmp_path, fault):
    reference = Artifact_Write(tmp_path/'flight.ssflp', _Audit(256), {})
    manifest_path = tmp_path/reference['path']
    manifest = json.loads(gzip.decompress(manifest_path.read_bytes()))
    def find(item):
        if isinstance(item, dict):
            if 'audit_blocks' in item: return item['audit_blocks'][0]
            for child in item.values():
                found = find(child)
                if found: return found
        elif isinstance(item, list):
            for child in item:
                found = find(child)
                if found: return found
    spec = find(manifest['payload'])
    assert spec is not None
    if fault == 'corrupt':
        (manifest_path.parent/spec['name']).write_bytes(b'broken')
    elif fault == 'size': spec['raw_bytes'] += 1
    elif fault == 'path': spec['name'] = '../escape.audit.json.gz'
    else: manifest['version'] = 2
    if fault != 'corrupt':
        manifest_path.write_bytes(gzip.compress(json.dumps(manifest).encode()))
        reference['sha256'] = FileHash_Get(manifest_path)
    with pytest.raises(ValueError, match='audit_block|record_block_size'):
        Artifact_Read(tmp_path/'flight.ssflp', reference)


def test_full_synthetic_algorithm_result_preserves_all_fields(tmp_path):
    from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayFidelity
    from silverstar_flp.core.dataset import TimeSeries
    series = TimeSeries(np.arange(3, dtype=np.uint64), np.arange(9,dtype=np.float64).reshape(3,3),
        'm/s', 'velocity', 'synthetic', np.ones(3,dtype=bool), ('E','N','U'), {'origin':'synthetic'})
    result = AlgorithmResult('silverstar.algorithm.pure_ins', 'synthetic-storage-fixture',
        'corrected_imu', {'gravity_mps2':9.8}, ReplayFidelity.APPROXIMATE,
        ('synthetic_input',), ('not_real_engine_evidence',), {'navigation.velocity_enu':series},
        _Audit(256), 'What-if')
    reference = Artifact_Write(tmp_path/'flight.ssflp', result, {})
    restored = Artifact_Read(tmp_path/'flight.ssflp', reference)
    assert _Fingerprint(result) == _Fingerprint(restored)
    assert restored.fidelity == ReplayFidelity.APPROXIMATE


@pytest.mark.parametrize('container', ['list', 'tuple', 'frozen'])
def test_changed_empty_layouts_big_integers_bytes_and_dict_read_interface(tmp_path, container):
    rows = [{} if i%3 == 0 else {'x': None, 2: 2**90+i, 'raw': bytes([i%256])}
            if i%3 == 1 else {'raw': bytes([i%256]), 2: 2**90+i, 'x': -0.0}
            for i in range(300)]
    if container == 'tuple': rows = tuple(rows)
    elif container == 'frozen': rows = tuple(MappingProxyType(row) for row in rows)
    reference = Artifact_Write(tmp_path/'flight.ssflp', rows, {})
    restored = Artifact_Read(tmp_path/'flight.ssflp', reference)
    assert _Fingerprint(rows) == _Fingerprint(restored)
    assert json.dumps([dict(row) for row in restored], default=_Bytes_Json) == json.dumps(
        [dict(row) for row in rows], default=_Bytes_Json)
    for first, second in zip(rows, restored):
        assert list(first) == list(second) and len(first) == len(second)
        assert dict(first) == dict(second)
        assert repr(first) == repr(second)


def test_v1_and_v2_plain_numerical_artifacts_remain_readable(tmp_path):
    reference = Artifact_Write(tmp_path/'flight.ssflp', {'values': np.arange(9)}, {})
    manifest_path = tmp_path/reference['path']
    manifest = json.loads(gzip.decompress(manifest_path.read_bytes()))
    for version in (1, 2):
        manifest['version'] = version
        manifest_path.write_bytes(gzip.compress(json.dumps(manifest).encode()))
        reference['sha256'] = FileHash_Get(manifest_path)
        np.testing.assert_array_equal(Artifact_Read(tmp_path/'flight.ssflp', reference)['values'], np.arange(9))
