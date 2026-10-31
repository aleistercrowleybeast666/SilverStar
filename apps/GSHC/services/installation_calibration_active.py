"""SSIC kind 3 active record, built separately from immutable kind 2 evidence.

Target native qualification and current dependencies remain authoritative.
This serializer never upgrades hardware acceptance or edits the candidate.
"""
import hashlib
import re
import struct
import zlib

from silverstar_data_contracts.objects import InstallationActive_Decode, SnapshotHash_Get
from services.installation_calibration_candidate import Candidate_Decode, InstallationCandidateResult


def ActivePacket_FromCandidate(packet):
    result, candidate = Candidate_Decode(packet)
    if result is not InstallationCandidateResult.Ok:
        raise ValueError('CANDIDATE_INVALID')
    binding, solution = candidate['binding'], candidate['solution']
    convention = solution['convention']
    if convention != binding['convention']:
        raise ValueError('SOURCE_FRAME_DEPENDENCY_MISMATCH')
    rga = convention.get('R_GA')
    if rga is None or convention.get('gyro_axis_evidence') in (None, 'UNKNOWN', 'UNPROVEN'):
        raise ValueError('SOURCE_FRAME_RELATION_UNPROVEN')
    # The initial real consumer accepts provider A/G already in one configured
    # body frame. A declared nonidentity rotation is rejected, never discarded.
    if any(abs(rga[i][j] - (i == j)) > 0.00001 for i in range(3) for j in range(3)):
        raise ValueError('R_GA_RUNTIME_NOT_SUPPORTED')
    acceleration = solution['accel_candidate']
    matrix = acceleration['matrix']
    if any(abs(matrix[i][j]) > 0.0000001 for i in range(3) for j in range(3) if i != j):
        raise ValueError('ACCEL_FULL_MATRIX_RUNTIME_NOT_SUPPORTED')
    parent = solution['mag_parent']
    match = re.fullmatch(r'mag-([1-9][0-9]*)-([0-9a-fA-F]{8})', parent['calibration_id'])
    if match is None or int(match[1]) != parent['generation']:
        raise ValueError('PERSISTED_MAG_PARENT_IDENTITY_REQUIRED')
    imu, mag = (binding['sources'][role]['identity'] for role in ('IMU', 'MAG'))
    record = bytearray(228)
    record[:8] = b'SSIC\x01\x03\x01\x03'
    struct.pack_into('<HHBBB', record, 8, imu['descriptor'], imu['physical'], imu['instance'], 1, 1)
    struct.pack_into('<4I', record, 16, binding['configuration_u32'],
        SnapshotHash_Get(imu['driver'].encode('utf-8')), SnapshotHash_Get(imu['model'].encode('utf-8')), int(match[2], 16))
    struct.pack_into('<HHB', record, 32, mag['descriptor'], mag['physical'], mag['instance'])
    struct.pack_into('<3I', record, 40, SnapshotHash_Get(mag['driver'].encode('utf-8')),
        SnapshotHash_Get(mag['model'].encode('utf-8')), parent['generation'])
    record[52:84] = bytes.fromhex(candidate['raw_archive_sha256'])
    ram = solution['report']['candidates'][0]['R_AM']
    values = (*acceleration['bias'], *(matrix[i][i] for i in range(3)), *solution['gyro_bias'],
        *(value for row in rga for value in row), *(value for row in ram for value in row))
    struct.pack_into('<27f', record, 116, *values)
    record[84:116] = hashlib.sha256(b'SSIC-ACTIVE-STABLE-v1\0' + record[:52] + record[152:188]).digest()
    struct.pack_into('<I', record, 224, zlib.crc32(record[:224]))
    InstallationActive_Decode(bytes(record))
    return bytes(record)


def ActivePacket_Check(packet):
    return InstallationActive_Decode(packet)
