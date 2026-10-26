from dataclasses import dataclass
from importlib.resources import files
import json
import math
import struct

CONTRACT = json.loads(files(__package__).joinpath('data/ss_tm_v0_1.json').read_text(encoding='utf8'))
MESSAGES = {value['type']: {'name': name, **value} for name, value in CONTRACT['messages'].items()}
TYPES = {name: value['type'] for name, value in CONTRACT['messages'].items()}
_SCALARS = {'u8': 'B', 'u16': 'H', 'u32': 'I', 'u64': 'Q', 'i16': 'h', 'i32': 'i', 'f32': 'f'}


class TelemetryProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Frame:
    profile: str
    message_type: int
    sequence: int
    boot_session: int
    values: dict
    raw: bytes
    known: bool = True


def _FieldFormat_Get(field_type):
    if '[' not in field_type:
        return '<' + _SCALARS[field_type], 1
    scalar, count = field_type.removesuffix(']').split('[')
    return '<' + count + _SCALARS[scalar], int(count)


def _Integer_Require(value, minimum, maximum, field):
    if type(value) is not int or not minimum <= value <= maximum:
        raise TelemetryProtocolError('invalid_integer:' + field)


def _Fields_Validate(name, value):
    if name == 'POSITION':
        flags = value['position_flags']
        if flags & ~0x3F:
            raise TelemetryProtocolError('position_reserved_flags')
        valid = bool(flags & 1)
        lat, lon, height = value['latitude_e7'], value['longitude_e7'], value['ellipsoid_height_mm']
        if valid:
            if not (-900000000 <= lat <= 900000000 and -1800000000 <= lon <= 1800000000):
                raise TelemetryProtocolError('position_coordinate_range')
        elif lat != -2147483648 or lon != -2147483648:
            raise TelemetryProtocolError('position_invalid_sentinel')
        if (flags & 2 and height == -2147483648) or (not flags & 2 and height != -2147483648):
            raise TelemetryProtocolError('height_validity_sentinel')
        if flags & 16 and (not valid or flags & 4):
            raise TelemetryProtocolError('retained_fix_flags')
        if flags & 4 and not valid:
            raise TelemetryProtocolError('current_fix_without_position')
    elif name == 'HEALTH':
        known, fault = value['known_mask'], value['fault_mask']
        if (known | fault) & ~0x7FF or fault & ~known:
            raise TelemetryProtocolError('health_masks')
        if value['battery_mv'] == 65535 and value['battery_age_ds'] != 65535:
            raise TelemetryProtocolError('battery_unknown_age')
    elif name == 'EVENT':
        if value['event_id'] == 0 or value['event_code'] == 0:
            raise TelemetryProtocolError('event_identity')
    elif name == 'CAPABILITY':
        if value['flight_encoding'] != 0 or value['preflight_flags'] != 1:
            raise TelemetryProtocolError('capability_encoding_or_phase')
        if value['command_policy'] not in (1, 2) or value['calibration_mode_mask'] & ~7:
            raise TelemetryProtocolError('capability_policy')
        if value['sensor_summary_flags'] & ~15 or not value['accel_full_scale_g'] or not value['gyro_full_scale_dps']:
            raise TelemetryProtocolError('capability_ranges')
    elif name == 'ACK':
        if value['result'] > 0x16:
            raise TelemetryProtocolError('ack_result')
    elif name == 'PREFLIGHT_STATUS':
        if value['flags'] & ~0x7F or value['alignment_state'] & 0xF0:
            raise TelemetryProtocolError('preflight_reserved_bits')


def Frame_Encode(profile, message, sequence, boot_session, values):
    if profile not in ('S', 'H'):
        raise TelemetryProtocolError('unsupported_profile')
    _Integer_Require(sequence, 0, 65535, 'sequence')
    _Integer_Require(boot_session, 1, 4294967295, 'boot_session')
    message_type = TYPES.get(message) if isinstance(message, str) else message
    declaration = MESSAGES.get(message_type)
    if declaration is None:
        raise TelemetryProtocolError('unknown_message_for_encoding')
    if set(values) != {field['name'] for field in declaration['fields']}:
        raise TelemetryProtocolError('message_fields')
    output = bytearray(struct.pack('<BBHI', 1, message_type | (0x80 if profile == 'H' else 0), sequence, boot_session))
    for field in declaration['fields']:
        format_string, count = _FieldFormat_Get(field['type'])
        field_value = values[field['name']]
        items = (field_value,) if count == 1 else field_value
        if not isinstance(items, (tuple, list)) or len(items) != count:
            raise TelemetryProtocolError('field_dimension:' + field['name'])
        if any(type(item) is bool or type(item) not in (int, float) for item in items):
            raise TelemetryProtocolError('field_type:' + field['name'])
        if field['type'].startswith('f32'):
            if not all(math.isfinite(item) for item in items):
                raise TelemetryProtocolError('nonfinite:' + field['name'])
        elif any(type(item) is not int for item in items):
            raise TelemetryProtocolError('integer_required:' + field['name'])
        try:
            output.extend(struct.pack(format_string, *items))
        except (struct.error, OverflowError) as error:
            raise TelemetryProtocolError('field_range:' + field['name']) from error
    _Fields_Validate(declaration['name'], values)
    if declaration['name'] == 'CAPABILITY' and values['command_policy'] != (1 if profile == 'S' else 2):
        raise TelemetryProtocolError('profile_policy_conflict')
    if len(output) != declaration['length'] or len(output) > 61:
        raise TelemetryProtocolError('contract_length')
    return bytes(output)


def Frame_Decode(raw, *, expected_profile=None, expected_session=None):
    if not isinstance(raw, bytes) or not 8 <= len(raw) <= 61:
        raise TelemetryProtocolError('header_or_mtu_length')
    version, profile_type, sequence, session = struct.unpack_from('<BBHI', raw)
    if version != 1:
        raise TelemetryProtocolError('unsupported_version:' + str(version))
    profile, message_type = ('H' if profile_type & 0x80 else 'S'), profile_type & 0x7F
    if expected_profile is not None and profile != expected_profile:
        raise TelemetryProtocolError('profile_mismatch')
    if not session or expected_session is not None and session != expected_session:
        raise TelemetryProtocolError('boot_session_mismatch')
    declaration = MESSAGES.get(message_type)
    if declaration is None:
        return Frame(profile, message_type, sequence, session, {}, raw, False)
    if len(raw) != declaration['length']:
        raise TelemetryProtocolError('message_length:' + declaration['name'])
    values, offset = {}, 8
    for field in declaration['fields']:
        format_string, count = _FieldFormat_Get(field['type'])
        unpacked = struct.unpack_from(format_string, raw, offset)
        values[field['name']] = unpacked[0] if count == 1 else unpacked
        offset += struct.calcsize(format_string)
    # The same validation is used in both directions, including finite floats.
    Frame_Encode(profile, message_type, sequence, session, values)
    return Frame(profile, message_type, sequence, session, values, raw)
