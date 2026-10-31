from copy import deepcopy
from importlib.resources import files
import json
import struct
import math
import zlib
import hashlib


def PersistentObject_Decode(record):
    """Validate a bounded SSOB envelope before exposing its immutable payload."""
    if type(record) is not bytes or not 19 <= len(record) <= 530:
        raise ValueError('ssob_length')
    magic, schema, kind, instance, reserved, generation, length, crc = struct.unpack_from('<4sBBBBIHI', record)
    if (magic != b'SSOB' or schema != 1 or not 1 <= kind <= 6 or instance >= 32 or
            reserved != 0 or generation == 0 or length != len(record)-18 or length > 512):
        raise ValueError('ssob_identity')
    if zlib.crc32(record[:14] + record[18:]) != crc:
        raise ValueError('ssob_crc')
    return {'kind':kind, 'instance':instance, 'generation':generation, 'payload':record[18:]}


def SnapshotHash_Get(payload):
    value = 0x811C9DC5
    for octet in payload:
        value = ((value ^ octet) * 0x01000193) & 0xffffffff
    return value


def InstallationActive_Decode(packet):
    """Decode recorded SSIC kind3; recorded flags are not hardware evidence."""
    if type(packet) is not bytes or len(packet) != 228:
        raise ValueError('ssic_active_length')
    if (packet[:8] != b'SSIC\x01\x03\x01\x03' or packet[13:16] != b'\x01\x01\x00'
            or packet[37:40] != bytes(3)):
        raise ValueError('ssic_active_header')
    crc = struct.unpack_from('<I',packet,224)[0]
    if zlib.crc32(packet[:224]) != crc: raise ValueError('ssic_active_crc')
    stable = hashlib.sha256(b'SSIC-ACTIVE-STABLE-v1\0'+packet[:52]+packet[152:188]).digest()
    if stable != packet[84:116] or packet[52:84] == bytes(32):
        raise ValueError('ssic_active_provenance')
    values = struct.unpack_from('<27f',packet,116)
    if not all(math.isfinite(value) for value in values): raise ValueError('ssic_active_nonfinite')
    if not all(0 < value <= 10 for value in values[3:6]): raise ValueError('ssic_active_scale')
    for matrix in (values[9:18],values[18:27]):
        if any(abs(sum(matrix[3*i+k]*matrix[3*j+k] for k in range(3))-(i==j)) > 0.0005
               for i in range(3) for j in range(3)):
            raise ValueError('ssic_active_rotation')
        determinant = (matrix[0]*(matrix[4]*matrix[8]-matrix[5]*matrix[7])
            -matrix[1]*(matrix[3]*matrix[8]-matrix[5]*matrix[6])
            +matrix[2]*(matrix[3]*matrix[7]-matrix[4]*matrix[6]))
        if abs(determinant-1) >= 0.0005: raise ValueError('ssic_active_rotation')
    imu = dict(zip(('descriptor','physical','instance'),struct.unpack_from('<HHB',packet,8)))
    imu.update(zip(('configuration_digest','driver_hash','model_hash','parent_intrinsic_crc'),
                   struct.unpack_from('<4I',packet,16)))
    mag = dict(zip(('descriptor','physical','instance'),struct.unpack_from('<HHB',packet,32)))
    mag.update(zip(('driver_hash','model_hash','intrinsic_generation'),struct.unpack_from('<3I',packet,40)))
    return {'imu':imu,'magnetometer':mag,'accel_bias_mps2':list(values[:3]),
        'accel_scale':list(values[3:6]),'gyro_bias_radps':list(values[6:9]),
        'R_GA':list(values[9:18]),'R_AM':list(values[18:27]),'record_crc32':crc,
        'raw_archive_sha256':packet[52:84].hex(),'stable_dependency_sha256':stable.hex(),
        'hardware_verified':False,'recorded_source_frame_qualified':True}


class _SnapshotReader:
    def __init__(self, data, offset=8):
        self.data, self.offset = data, offset

    def Read(self, layout):
        layout = '<' + layout
        size = struct.calcsize(layout)
        if self.offset + size > len(self.data):
            raise ValueError('ssms_truncated')
        values = struct.unpack_from(layout, self.data, self.offset)
        self.offset += size
        if any(isinstance(value, float) and not math.isfinite(value) for value in values):
            raise ValueError('ssms_nonfinite')
        return values

    def Finish(self):
        if self.offset != len(self.data):
            raise ValueError('ssms_trailing_bytes')


def MissionSnapshotSection_Decode(payload):
    """Decode actual SSMS schema2/3/4 fields; no inferred live values."""
    if type(payload) is not bytes or not 8 <= len(payload) <= 512:
        raise ValueError('ssms_length')
    magic, schema, section, count, reserved = struct.unpack_from('<4sBBBB', payload)
    if magic != b'SSMS' or schema not in (2,3,4) or section > 6 or reserved:
        raise ValueError('ssms_header')
    reader = _SnapshotReader(payload)
    result = {'schema':schema, 'section':section}
    if section == 0:
        if count != 6: raise ValueError('ssms_commit_count')
        names = ('base_instance','mission_id','snapshot_sequence','profile_id','configuration_digest')
        header = dict(zip(names, reader.Read('BIIII')))
        header['firmware_version'] = '.'.join(str(value) for value in reader.Read('BBBB'))
        header['build_tag'] = reader.Read('8s')[0].decode('ascii', errors='strict')
        if reader.Read('B')[0] != 0: raise ValueError('ssms_guidance_unsupported')
        names = ('imu_rate_hz','mechanization_subsamples','navigation_rate_hz',
            'imu_source_instance','gnss_source_instance','calibration_generation','imu_correction_hash',
            'mag_calibration_generation','mag_calibration_set_hash')
        header.update(zip(names, reader.Read('IHIBBIIII')))
        if header['base_instance'] not in (0,8) or header['mission_id'] == 0 or header['snapshot_sequence'] == 0:
            raise ValueError('ssms_commit_identity')
        radio = MissionRadioProfile_Decode(payload)
        radio_schema, radio_offset = (payload[66],67) if schema == 4 else (schema,66)
        reader.offset = radio_offset + (15 if radio_schema == 2 else 4 + struct.unpack_from('<H',payload,radio_offset+2)[0])
        algorithm, constraints, authoritative, yaw, selected, required = reader.Read('BBBfII')
        if not 2 <= constraints <= 6 or authoritative not in (0,1): raise ValueError('ssms_alignment')
        alignment = {'algorithm':algorithm,'external_yaw_authoritative':authoritative,
            'known_yaw_deg':yaw,'selected_mask':selected,'required_mask':required,
            'constraints':[dict(zip(('kind','body_axis','weight','declination_deg','nav_azimuth_deg'),
                                  reader.Read('BBfff'))) for _ in range(constraints)]}
        references = [dict(zip(('generation','hash'),reader.Read('II'))) for _ in range(6)]
        if any(item['generation'] == 0 for item in references): raise ValueError('ssms_section_generation')
        result.update(header=header, radio=radio, alignment=alignment, references=references)
    elif section in (1,2,3,4,5):
        layouts = {1:('HHBBHHIIII',('descriptor','physical','device_class','instance','driver','flags','capabilities','rate','driver_hash','model_hash'),16),
                   3:('HBBHHII',('descriptor','algorithm_class','instance','algorithm','flags','configuration_digest','name_hash'),16),
                   4:('IIB',('key_hash','value_bits','kind'),48)}
        layout,names,maximum = layouts[1 if section in (1,2) else 3 if section == 3 else 4]
        if count > maximum: raise ValueError('ssms_row_count')
        rows = [dict(zip(names,reader.Read(layout))) for _ in range(count)]
        if section in (4,5):
            for row in rows:
                if row['kind'] not in (1,2): raise ValueError('ssms_parameter_kind')
                row['value'] = struct.unpack('<f' if row['kind']==1 else '<i',struct.pack('<I',row['value_bits']))[0]
                if isinstance(row['value'],float) and not math.isfinite(row['value']): raise ValueError('ssms_parameter_nonfinite')
        result['rows'] = rows
    else:
        if count != 1: raise ValueError('ssms_calibration_count')
        calibration = dict(zip(('generation','mode','ready'),reader.Read('IBB')))
        if calibration['ready'] != 1: raise ValueError('ssms_calibration_not_ready')
        calibration['axes'] = [dict(zip(('accel_bias_mps2','accel_scale','gyro_bias_radps','gyro_scale'),reader.Read('ffff'))) for _ in range(3)]
        calibration.update(zip(('mag_generation','mag_hash','mag_set_hash'),reader.Read('III')))
        mag_count = reader.Read('B')[0]
        if mag_count > 8: raise ValueError('ssms_magnetometer_count')
        calibration['mag_instances'] = [dict(zip(('instance','physical','generation','hash'),reader.Read('BHII'))) for _ in range(mag_count)]
        if schema == 4:
            present = reader.Read('B')[0]
            if present not in (0,1): raise ValueError('ssms_active_present')
            calibration['active_installation'] = None
            if present:
                generation, crc = reader.Read('II')
                active = InstallationActive_Decode(reader.Read('228s')[0])
                if generation == 0 or active['record_crc32'] != crc: raise ValueError('ssms_active_identity')
                active['saved_generation'] = generation
                calibration['active_installation'] = active
        result['calibration'] = calibration
    reader.Finish()
    return result


def MissionRadioProfile_Decode(snapshot):
    """Decode radio identity in an SSMS section0 after its container is verified.

    This does not replace the exact decoder/generation and SSOB CRC checks.
    Unknown identities are rejected rather than reinterpreted as another radio.
    """
    if (not isinstance(snapshot, bytes) or len(snapshot) < 66 or
            snapshot[:4] != b'SSMS' or snapshot[5:8] != b'\x00\x06\x00'):
        raise ValueError('mission_radio_snapshot_header')
    schema = snapshot[4]
    radio_schema, offset = schema, 66
    if schema == 4:
        if len(snapshot) < 67: raise ValueError('mission_radio_typed_header')
        radio_schema, offset = snapshot[66], 67
    if radio_schema == 2:
        body = snapshot[offset:offset+15]
        family, module, version = 'sx128x', None, 0
    elif radio_schema == 3:
        if len(snapshot) < offset+4:
            raise ValueError('mission_radio_typed_header')
        backend, version, length = struct.unpack_from('<BBH', snapshot, offset)
        if version != 1 or backend not in (1, 2):
            raise ValueError('mission_radio_typed_identity')
        if length != (14 if backend == 1 else 16) or len(snapshot) < offset+4+length:
            raise ValueError('mission_radio_typed_length')
        body = snapshot[offset+4:offset+4+length]
        if backend == 1:
            if (body[0] > 125 or body[1] > 2 or body[2] not in (0,250,244,238) or
                    body[3:8] in (bytes(5),b'\xff'*5) or not 1 <= body[8] <= 15 or
                    body[9] > 15 or body[10:12] != b'\x02\x20' or
                    not 50 <= body[12] <= 61 or body[13] != 1):
                raise ValueError('mission_radio_nrf_profile')
            # Historical profile remains typed; do not expose an active choice.
            return {'schema':schema, 'family':'nrf24', 'version':version,
                    'module':'nrf24l01p', 'historical_only':True,
                    'channel':body[0], 'data_rate':body[1],
                    'tx_power_dbm':struct.unpack('b',body[2:3])[0], 'address':body[3:8].hex(),
                    'retry_delay':body[8], 'retry_count':body[9], 'crc_bytes':body[10],
                    'physical_mtu':body[11], 'packet_mtu':body[12], 'fragment_version':body[13]}
        if body != bytes.fromhex('01400ecf190748e801000510003d0011'):
            raise ValueError('mission_radio_sx1278_profile')
        family, module, body = 'sx127x', 'e32_400m20s', body[1:]
    else:
        raise ValueError('mission_radio_snapshot_schema')
    if len(body) != 15:
        raise ValueError('mission_radio_profile_length')
    frequency, sf, bandwidth, denominator, preamble, mtu, power = struct.unpack('<IBIBHHb', body)
    return {'schema':schema, 'family':family, 'module':module, 'version':version,
            'frequency_hz':frequency, 'spreading_factor':sf, 'bandwidth_hz':bandwidth,
            'coding_rate':'4/'+str(denominator), 'preamble_symbols':preamble,
            'packet_mtu':mtu, 'tx_power_dbm':power, 'hardware_verified':False}


def ObjectCatalog_DefaultGet():
    value = json.loads(files(__package__).joinpath('data/persistent_objects_v1.json').read_text(encoding='utf8'))
    ObjectCatalog_Validate(value)
    return value


def ObjectCatalog_Validate(document):
    if (type(document) is not dict or set(document) != {'schema_id', 'endianness', 'objects', 'rules'}
            or document['schema_id'] != 'silverstar.object-catalog/1.0' or document['endianness'] != 'little'):
        raise ValueError('object_catalog_schema')
    objects = document['objects']
    if type(objects) is not list or not 1 <= len(objects) <= 64:
        raise ValueError('object_catalog_capacity')
    seen = set()
    sizes = {'u8': 1, 'u16': 2, 'u32': 4, 'f32': 4, 'bytes': 1}
    tails = {'none', 'ssob_payload', 'ssic_kind_payload', 'canonical_snapshot_json', 'section_rows_or_flight_configuration'}
    for item in objects:
        if type(item) is not dict or set(item) != {'type_id', 'schema_version', 'min_bytes', 'max_bytes', 'fields', 'tail_encoding'}:
            raise ValueError('object_catalog_entry')
        identity = item['type_id']
        if type(identity) is not str or not 1 <= len(identity) <= 96 or identity in seen:
            raise ValueError('object_catalog_identity')
        seen.add(identity)
        if (type(item['schema_version']) is not int or item['schema_version'] != 1
                or type(item['min_bytes']) is not int or type(item['max_bytes']) is not int
                or not 0 < item['min_bytes'] <= item['max_bytes'] <= 1048576
                or type(item['tail_encoding']) is not str or item['tail_encoding'] not in tails):
            raise ValueError('object_catalog_bounds')
        fields = item['fields']
        if type(fields) is not list or not 1 <= len(fields) <= 64:
            raise ValueError('object_catalog_fields')
        names, end = set(), 0
        for field in fields:
            if type(field) is not dict or set(field) != {'name', 'type', 'count', 'offset', 'unit'}:
                raise ValueError('object_catalog_field')
            if (type(field['name']) is not str or not 1 <= len(field['name']) <= 96 or field['name'] in names
                    or type(field['type']) is not str or field['type'] not in sizes or type(field['count']) is not int or not 1 <= field['count'] <= 4096
                    or type(field['offset']) is not int or field['offset'] != end
                    or type(field['unit']) is not str or not 1 <= len(field['unit']) <= 64):
                raise ValueError('object_catalog_field_layout')
            names.add(field['name'])
            end += sizes[field['type']] * field['count']
        if end != item['min_bytes'] or item['tail_encoding'] == 'none' and end != item['max_bytes']:
            raise ValueError('object_catalog_layout_length')
    if (type(document['rules']) is not dict or len(document['rules']) > 32 or
            any(type(key) is not str or type(value) is not str or len(value) > 2048 for key, value in document['rules'].items())):
        raise ValueError('object_catalog_rules')
    return deepcopy(document)
