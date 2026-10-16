"""Actual C frame codecs against independent Python LE/CRC and native ABI inputs."""
import ctypes as ct
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / 'apps/SCG/plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG'
COMMON = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Common'
CONTRACT = ROOT / 'contracts/navigation_fusion_horizon_records_v1.json'
RECORDS = json.loads(CONTRACT.read_text())['records']
TYPES = {'u8': ct.c_uint8, 'u16': ct.c_uint16, 'u32': ct.c_uint32, 'u64': ct.c_uint64, 'f32': ct.c_float}
FORMATS = {'u8':'B', 'u16':'H', 'u32':'I', 'u64':'Q', 'f32':'f'}


@pytest.fixture(scope='module', params=['-O0', '-O2'])
def codec(request, tmp_path_factory):
    output = tmp_path_factory.mktemp('horizon_wire' + request.param)
    sources = [PROTOCOL/'Src/sslog_records.c', PROTOCOL/'Src/sslog_protocol.c',
               COMMON/'Src/silverstar_assert.c', Path(__file__).with_name('fixtures')/'fusion_horizon_records.c']
    compiler = shutil.which('gcc')
    assert compiler, 'Actual GCC is required'
    target = output / 'wire.dll'
    command = [compiler, request.param, '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wpedantic',
               '-Wconversion', '-Wsign-conversion', '-Wshadow', '-Wstrict-prototypes', '-Wmissing-prototypes',
               '-shared', '-I'+str(PROTOCOL/'Inc'), '-I'+str(COMMON/'Inc'), *map(str,sources), '-o', str(target)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (output/'compile.json').write_text(json.dumps(dict(command=command,exit_code=run.returncode,
        stdout=run.stdout,stderr=run.stderr,compiler=subprocess.check_output([compiler,'--version'],text=True),
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}),indent=2))
    assert run.returncode == 0, run.stdout+run.stderr
    lib = ct.CDLL(str(target))
    lib.Test_HorizonSerialize.argtypes = [ct.c_uint32,ct.c_void_p,ct.c_void_p,ct.c_uint16]
    lib.Test_HorizonDeserialize.argtypes = [ct.c_void_p,ct.c_uint16,ct.c_void_p]
    return lib


def native_pattern(record):
    class Payload(ct.Structure):
        _fields_ = [(f['name'], TYPES[f['type']] * f['count'] if 'count' in f else TYPES[f['type']])
                    for f in record['fields']]
    native = Payload()
    wire = b''
    index = 0
    for field in record['fields']:
        values = []
        for axis in range(field.get('count',1)):
            index += 1
            kind = field['type']
            value = (-1)**index * (index+.125) if kind == 'f32' else ({'u8':0,'u16':0xAB00,'u32':0xDEAD0000,'u64':0xFEDCBA9800000000}[kind]+index)
            values.append(value)
        if 'count' in field: getattr(native,field['name'])[:] = values
        else: setattr(native,field['name'],values[0])
        wire += struct.pack('<'+FORMATS[field['type']]*len(values),*values)
    return native, wire


@pytest.mark.parametrize('record',RECORDS,ids=lambda r:r['name'])
def test_actual_frame_serialization_and_deserialization(codec, record):
    native, payload = native_pattern(record)
    assert len(payload) == record['payload_size']
    expected = struct.pack('<IBBHIQI',0x31474C46,1,int(record['id'],16),len(payload),0x89ABCDEF,
                           0x1020304050607080,0x12345678)+payload
    expected += struct.pack('<I', zlib.crc32(expected))
    output = ct.create_string_buffer(284)
    assert codec.Test_HorizonSerialize(int(record['id'],16),ct.byref(native),output,len(output)) == len(expected)
    assert output.raw[:len(expected)] == expected
    restored = type(native)()
    assert codec.Test_HorizonDeserialize(expected,len(expected),ct.byref(restored)) == 0
    assert bytes(restored) == bytes(native)
    # These are ordinary decode errors, never assertion traps or success.
    for offset, value, result in [(4,2,5),(6,0,6),(24,expected[24]^1,7)]:
        bad = bytearray(expected); bad[offset] = value
        assert codec.Test_HorizonDeserialize(bytes(bad),len(bad),ct.byref(restored)) == result
    assert codec.Test_HorizonDeserialize(expected,len(expected)-1,ct.byref(restored)) == 2
    assert codec.Test_HorizonSerialize(int(record['id'],16),ct.byref(native),output,len(expected)-1) == -2


def test_catalogs_and_frozen_predecessor():
    assert hashlib.sha256((ROOT/'contracts/navigation_fusion_timing_records_v2.json').read_bytes()).hexdigest() == '257f574479bd3fea5cc4564c7afd00504c39f1f66dda6ad793c34e9b7834f5fd'
    for name in ['sslog_schema.json','sslog_parser_metadata.json']:
        records = json.loads((PROTOCOL/'schema'/name).read_text(encoding='utf-8'))['records']
        for expected in RECORDS:
            assert next(r for r in records if r['name']==expected['name']) == expected


@pytest.mark.parametrize('owner',['silverstar.algorithm.estimator.kf6','silverstar.algorithm.estimator.eskf15'])
@pytest.mark.parametrize('mode',[0,1])
def test_legacy_modes_never_enable_unproduced_horizon_streams(builtin_catalog, owner, mode):
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
    from silverstar_fccg.project.logging import LogAvailability_Get, ProtocolLogDefinitions_Get
    model = ReferenceProject_Create('HorizonWireIsolation',catalog=builtin_catalog)
    model.strategies['estimator']=owner
    model.algorithm_parameters.setdefault(owner,{})['fusion_timing_mode']=mode
    model=ProjectConfiguration_Reconcile(model,builtin_catalog).model
    definitions={d.record:d for d in ProtocolLogDefinitions_Get(model,builtin_catalog)}
    streams={s.record:s for s in model.logging_streams}
    for record in RECORDS:
        assert not LogAvailability_Get(definitions[record['enum']],model,builtin_catalog).available
        assert not streams[record['enum']].enabled
