"""Immutable synthetic objects; exact log coordinator and CRC/generation faults."""
import hashlib
import struct
import zlib
from pathlib import Path

import pytest
from silverstar_flp.decoder_profiles.mission_snapshot import MissionSnapshot_Read
from silverstar_data_contracts.objects import (
    SnapshotHash_Get, MissionSnapshotSection_Decode, ObjectCatalog_DefaultGet, InstallationActive_Decode,
)
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.plugins.registry import builtin_registry
from tests.sslog_synthetic import SyntheticSslogBuilder, START_TIMESTAMP_US, Event_Payload
from tests.test_decoder_profiles import (
    _CatalogDocument_Build, _PackageFiles_Build, _Package_Write,
    _DescriptorPayload_Build, _CalibrationNonePayload_Build, DESCRIPTOR_RECORD_TYPE,
)


def _Envelope(payload, instance, generation=1):
    head = struct.pack('<4sBBBBIH',b'SSOB',1,4,instance,0,generation,len(payload))
    return head + struct.pack('<I',zlib.crc32(head+payload)) + payload


def _Active_Record():
    packet=bytearray(228)
    packet[:8]=b'SSIC\x01\x03\x01\x03'
    struct.pack_into('<HHBBBB4I',packet,8,1,10,0,1,1,0,22,123,456,99)
    struct.pack_into('<HHB3x3I',packet,32,2,20,0,321,654,3)
    packet[52:84]=hashlib.sha256(b'explicit synthetic archive').digest()
    struct.pack_into('<9f',packet,116,0.,0.,0.,1.,1.,1.,0.,0.,0.)
    for offset in (152,188): struct.pack_into('<9f',packet,offset,1.,0.,0.,0.,1.,0.,0.,0.,1.)
    packet[84:116]=hashlib.sha256(b'SSIC-ACTIVE-STABLE-v1\0'+packet[:52]+packet[152:188]).digest()
    struct.pack_into('<I',packet,224,zlib.crc32(packet[:224]))
    return bytes(packet)


def _Objects_Write(root, schema=2, active=False):
    prefix = lambda section,count: struct.pack('<4sBBBB',b'SSMS',schema,section,count,0)
    calibration = prefix(6,1)+struct.pack('<IBB',0,0,1)+struct.pack('<12f',*(0.,1.,0.,1.)*3)
    imu_hash = SnapshotHash_Get(calibration)
    calibration += struct.pack('<IIIB',0,0,0,0)
    if schema == 4:
        packet=_Active_Record()
        calibration += (b'\x01'+struct.pack('<II',7,zlib.crc32(packet[:224]))+packet if active else b'\x00')
    parts = [prefix(1,1)+struct.pack('<HHBBHHIIII',1,10,1,0,1,1,1,200,123,456),
             prefix(2,0),prefix(3,0),
             prefix(4,1)+struct.pack('<IIB',12,struct.unpack('<I',struct.pack('<f',2.5))[0],1),
             prefix(5,0),calibration]
    if active:
        parts[1]=prefix(2,1)+struct.pack('<HHBBHHIIII',2,20,5,0,1,1,1,200,321,654)
    header = prefix(0,6)+struct.pack('<BIIII',0,11,1,1,22)+bytes((0,1,3,0))+b'20261027'+bytes(1)
    header += struct.pack('<IHIBBIIII',200,2,100,0,255,0,imu_hash,0,0)
    if schema == 4: header += b'\x03'
    header += (struct.pack('<IBIBHHb',2400000000,7,800000,5,24,61,12) if schema == 2
               else bytes.fromhex('0201100001400ecf190748e801000510003d0011'))
    header += struct.pack('<BBBfII',1,2,0,0.,3,3)+struct.pack('<BBfff',1,1,1.,0.,0.)*2
    header += b''.join(struct.pack('<II',1,SnapshotHash_Get(part)) for part in parts)
    for index,part in enumerate((header,*parts)):
        (root/f'snap{index:02d}.0').write_bytes(_Envelope(part,index))
    identity = dict(mission_id=11,commit_generation=1,snapshot_sequence=1,
                    imu_calibration_generation=0,mag_calibration_set_hash=0,base_instance=0,ready=1)
    return identity


@pytest.mark.parametrize('schema',[2,3,4])
def test_complete_recorded_snapshot_and_exact_identity(tmp_path,schema):
    identity = _Objects_Write(tmp_path,schema)
    hashes = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    result = MissionSnapshot_Read(tmp_path,identity,object_catalog=ObjectCatalog_DefaultGet())
    assert result['status']=='verified' and len(result['sources'])==7
    assert result['devices'][0]['physical']==10 and result['parameters'][0]['value']==2.5
    assert result['radio']['family']==('sx128x' if schema==2 else 'sx127x')
    assert result['calibration']['axes'][2]['gyro_scale']==1.
    with pytest.raises(ValueError,match='log_identity'): MissionSnapshot_Read(tmp_path,{**identity,'mission_id':12})
    target=tmp_path/'snap04.0'; raw=bytearray(target.read_bytes());raw[-1]^=1;target.write_bytes(raw)
    with pytest.raises(ValueError,match='object_missing'): MissionSnapshot_Read(tmp_path,identity,object_catalog=ObjectCatalog_DefaultGet())
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in hashes.items() if p!=target)


def test_snapshot_parser_rejects_truncation_unknown_version_and_nonfinite(tmp_path):
    _Objects_Write(tmp_path)
    payload=(tmp_path/'snap00.0').read_bytes()[18:]
    for end in range(len(payload)):
        with pytest.raises(ValueError): MissionSnapshotSection_Decode(payload[:end])
    with pytest.raises(ValueError): MissionSnapshotSection_Decode(payload[:4]+b'\x05'+payload[5:])
    data=bytearray((tmp_path/'snap06.0').read_bytes()[18:]);data[14:18]=struct.pack('<f',float('nan'))
    with pytest.raises(ValueError,match='nonfinite'): MissionSnapshotSection_Decode(bytes(data))


def test_real_log_coordinator_attaches_snapshot_and_preserves_log_on_bad_object(tmp_path):
    identity = _Objects_Write(tmp_path)
    catalog = _CatalogDocument_Build()
    catalog['records'].append({'id':'0x29','version':0,'name':'MISSION_SNAPSHOT_IDENTITY','payload_size':24,
        'fields':[{'name':name,'type':'u32'} for name in ('mission_id','commit_generation','snapshot_sequence','imu_calibration_generation','mag_calibration_set_hash')]+
                 [{'name':'base_instance','type':'u8'},{'name':'ready','type':'u8'},{'type':'pad','count':2}]})
    files,hashes = _PackageFiles_Build(catalog_document=catalog)
    package,_ = _Package_Write(tmp_path/'recorded.ssdecoder',files=files)
    builder=SyntheticSslogBuilder()
    builder.Record_Add(DESCRIPTOR_RECORD_TYPE,_DescriptorPayload_Build(hashes),START_TIMESTAMP_US-3)
    builder.Record_Add(0x17,_CalibrationNonePayload_Build(),START_TIMESTAMP_US-2)
    builder.Record_Add(0x29,struct.pack('<IIIIIBBH',11,1,1,0,0,0,1,0),START_TIMESTAMP_US-1)
    builder.Record_Add(0x02,Event_Payload(3),START_TIMESTAMP_US)
    log=builder.File_Write(tmp_path/'flight.sslog'); original=log.read_bytes()
    coordinator=LogOpenCoordinator(builtin_registry(),cache=DecoderProfileCache(tmp_path/'cache'))
    request=LogOpenRequest(log_path=log,decoder_package_path=package)
    result=coordinator.Open(request)
    assert result.match_mode=='exact_generation_profile'
    assert result.dataset.metadata['mission_snapshot']['status']=='verified'
    (tmp_path/'snap01.0').write_bytes(b'corrupt')
    result=coordinator.Open(request)
    assert result.dataset.metadata['mission_snapshot']['status']=='invalid'
    assert len(result.dataset.Records_Get('MISSION_SNAPSHOT_IDENTITY'))==1 and log.read_bytes()==original


def test_active_snapshot_keeps_recorded_identity_and_checks_actual_baseline(tmp_path):
    identity=_Objects_Write(tmp_path,4,True)
    value=MissionSnapshot_Read(tmp_path,identity,object_catalog=ObjectCatalog_DefaultGet())
    active=value['calibration']['active_installation']
    assert active['saved_generation']==7 and active['record_crc32']==zlib.crc32(_Active_Record()[:224])
    assert value['calibration']['effective_mode']=='recorded_active_installation'
    assert active['R_AM']==[1.,0.,0.,0.,1.,0.,0.,0.,1.] and not active['hardware_verified']
    with pytest.raises(ValueError,match='catalog_missing'): MissionSnapshot_Read(tmp_path,identity)


def test_active_packet_rejects_crc_stable_hash_nonfinite_and_reflection():
    original=_Active_Record()
    for end in range(len(original)):
        with pytest.raises(ValueError): InstallationActive_Decode(original[:end])
    for offset,replacement,expected in ((116,struct.pack('<f',float('nan')),'nonfinite'),
                                       (188,struct.pack('<f',-1.),'rotation'),
                                       (16,struct.pack('<I',23),'provenance'),
                                       (128,struct.pack('<f',0.),'scale')):
        packet=bytearray(original); packet[offset:offset+len(replacement)]=replacement
        struct.pack_into('<I',packet,224,zlib.crc32(packet[:224]))
        with pytest.raises(ValueError,match=expected): InstallationActive_Decode(bytes(packet))
