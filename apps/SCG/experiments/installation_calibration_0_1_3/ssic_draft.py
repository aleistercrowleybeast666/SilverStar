"""Complete bounded SSIC schema-1 installation draft, never a production codec.

Kind 1 remains owned by the existing magnetic implementation. Draft kinds 2..8
are proposals only; publication requires the shared contracts/TF owners.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import struct
import zlib

import numpy as np

from .capture import SourceDescriptor
from .prototype import Intrinsic, Policy, SensorIdentity, _digest, _matrix, _uint

HEADER = struct.Struct("<4sBBBBHHB3xIIII")
IDENTITY = struct.Struct("<B64s64s64s64s32s")
PROVENANCE = struct.Struct("<32s64s64s64s64s64s64sIIHBB3bBB")
INTRINSIC = struct.Struct("<32s32sI64s32s3d9d3ddBB")
EXTRINSIC = struct.Struct("<32s32s32s32sII9d9ddB64s")
POLICY_FIELDS = tuple(k for k in asdict(Policy()) if k != "threshold_status")
POLICY = struct.Struct("<32s32s"+"d"*len(POLICY_FIELDS))
QUALITY = struct.Struct("<32s32s32s32s32s32s7dIIBBBBBB")
MANIFEST = struct.Struct("<16sIII32s32sB")
ENTRY = struct.Struct("<BBH32s")
MAX_RECORD, MAX_RECORDS, MAX_BUNDLE = 512, 10, 5140
KINDS = {"IDENTITY": 2, "PROVENANCE": 3, "INTRINSIC": 4, "EXTRINSIC": 5,
         "POLICY": 6, "QUALITY": 7, "MANIFEST": 8}
ALGORITHM = "OFFLINE_SCIPY_MULTISTART"
ROLES = {"IMU": 1, "MAG": 2}
INTEGER_POLICY = {"max_skew_us", "max_time_uncertainty_us", "starts", "max_nfev", "seed"}


def _text(value, width):
    if not isinstance(value, str) or not value or "\0" in value: raise ValueError("explicit text required")
    raw = value.encode("ascii")
    if len(raw) > width: raise ValueError("bounded text")
    return raw.ljust(width, b"\0")


def _untext(raw):
    value = raw.rstrip(b"\0").decode("ascii")
    if _text(value, len(raw)) != raw: raise ValueError("canonical text padding")
    return value


def _sha(data):
    return hashlib.sha256(data).digest()


def _record(kind, role, source, payload, config_u32, parent_crc=0):
    _uint(config_u32, 32)
    identity = source.identity
    header = HEADER.pack(b"SSIC", 1, kind, 1, role, identity.descriptor, identity.physical,
        identity.instance, config_u32, zlib.crc32(identity.driver.encode()),
        zlib.crc32(identity.model.encode()), parent_crc)
    if len(header)+len(payload) > MAX_RECORD: raise ValueError("SSIC record capacity")
    return header+payload


def Record_Decode(raw):
    if type(raw) is not bytes or not HEADER.size <= len(raw) <= MAX_RECORD: raise ValueError("SSIC record size")
    h = HEADER.unpack(raw[:32])
    if (h[0:2] != (b"SSIC", 1) or h[2] not in KINDS.values() or h[3] != 1 or h[4] not in (1, 2)
            or raw[13:16] != bytes(3) or h[5] == 0 or h[6] == 0):
        raise ValueError("SSIC header, draft kind or reserved bits")
    lengths = {2: IDENTITY.size, 3: PROVENANCE.size, 4: INTRINSIC.size, 5: EXTRINSIC.size,
               6: POLICY.size, 7: QUALITY.size}
    if h[2] in lengths and len(raw)-32 != lengths[h[2]]: raise ValueError("typed SSIC length")
    return h, raw[32:]


def _source_records(source, config):
    i, role = source.identity, ROLES[source.role]
    identity = _record(2, role, source, IDENTITY.pack(role, _text(i.board, 64), _text(i.driver, 64),
        _text(i.model, 64), _text(i.configuration, 64), _text(i.raw_frame, 32)), config)
    provenance = _record(3, role, source, PROVENANCE.pack(_sha(identity), _text(source.boot, 64),
        _text(source.frame_provenance, 64), _text(source.clock, 64), _text(source.clock_provenance, 64),
        _text(source.intrinsic_id, 64), _text(source.provider_calibration, 64), source.intrinsic_generation,
        source.epoch, source.sequence_stride, source.sample_time_bits, int(source.timestamp_saturates),
        *source.axis_mapping_applied, role, 0), config, zlib.crc32(identity))
    return identity, provenance


def _intrinsic_record(value, source, identity, provenance, gyro_bias, config, reference_uT):
    role = ROLES[source.role]
    if value.identity != source.identity: raise ValueError("intrinsic source identity")
    if role == 1 and not np.array_equal(np.array(value.matrix), np.diag(np.diag(value.matrix))):
        raise ValueError("six-face acceleration model is diagonal")
    values = (*value.bias, *np.array(value.matrix).ravel(), *gyro_bias, reference_uT if role == 2 else 0.)
    if not np.isfinite(values).all() or np.linalg.norm(gyro_bias) > 1: raise ValueError("intrinsic numeric range")
    return _record(4, role, source, INTRINSIC.pack(_sha(identity), _sha(provenance), value.generation,
        _text(value.calibration_id, 64), _text(value.output_frame, 32), *values, role, 0),
        config, zlib.crc32(identity+provenance))


def Partition_Digests(session):
    train = [asdict(r) for r in session.records if r.split == "TRAIN"]
    hold = [asdict(r) for r in session.records if r.split == "HOLDOUT"]
    if not train or not hold: raise ValueError("independent partitions required")
    return bytes.fromhex(_digest(train)), bytes.fromhex(_digest(hold)), len(train), len(hold)


@dataclass(frozen=True)
class DraftBundle:
    records: tuple
    sources: tuple
    intrinsics: tuple
    R_AM: tuple
    R_GA: tuple | None
    s: float
    policy: Policy
    archive_digest: str
    binding_digest: str
    base_generation: int
    candidate_generation: int
    session_id: str
    commit_rid: int

    @property
    def apply_allowed(self):
        return False

    def ParentsMatch(self, accel, mag):
        return self.intrinsics[0].Digest() == accel.Digest() and self.intrinsics[1].Digest() == mag.Digest()

    @property
    def fit_raw_digest(self):
        return QUALITY.unpack(self.records[-1][32:])[0].hex()

    def CorrectFromRaw(self, role, raw, layer="PROVIDER_PHYSICAL_BEFORE_SOFTWARE_CORRECTION"):
        if layer != "PROVIDER_PHYSICAL_BEFORE_SOFTWARE_CORRECTION": raise ValueError("never stack old correction")
        if role not in ROLES: raise ValueError("source role")
        return self.intrinsics[ROLES[role]-1].Correct(raw)

    def MagToGyro(self):
        return None if self.R_GA is None else _matrix(np.array(self.R_GA) @ self.R_AM, rotation=True)


def Bundle_Build(session, report, accel, mag, sources, binding_digest, *, config_u32,
                 archive_digest, base_generation=0, commit_rid=1, policy=Policy(), gyro_bias=(0., 0., 0.)):
    _uint(base_generation, 32); _uint(commit_rid, 32, True)
    if base_generation == 2**32-1: raise ValueError("installation generation exhausted")
    if (not session.CandidateIsCurrent(report, accel, mag, policy) or not report.candidates or report.apply_allowed
            or len(sources) != 2 or [x.role for x in sources] != ["IMU", "MAG"]):
        raise ValueError("bound complete candidate required")
    binding = bytes.fromhex(binding_digest)
    if len(binding) != 32: raise ValueError("full binding digest required")
    records, ids, provenance, intrinsic = {}, {}, {}, {}
    for source, value in zip(sources, (accel, mag)):
        role = ROLES[source.role]
        ids[role], provenance[role] = _source_records(source, config_u32)
        intrinsic[role] = _intrinsic_record(value, source, ids[role], provenance[role], gyro_bias if role == 1 else (0.,)*3, config_u32, policy.reference_uT)
        records[2, role], records[3, role], records[4, role] = ids[role], provenance[role], intrinsic[role]
    best, convention = report.candidates[0], session.convention
    rga = np.zeros((3, 3)) if convention.R_GA is None else np.array(convention.R_GA)
    _matrix(best.R_AM, rotation=True)
    if not -1 <= best.s <= 1: raise ValueError("inclination constraint")
    extrinsic = _record(5, 1, sources[0], EXTRINSIC.pack(_sha(ids[1]), _sha(ids[2]),
        _sha(intrinsic[1]), _sha(intrinsic[2]), accel.generation, mag.generation,
        *np.array(best.R_AM).ravel(), *rga.ravel(), best.s, int(convention.R_GA is not None),
        _text(convention.gyro_axis_evidence, 64)), config_u32, zlib.crc32(intrinsic[1]+intrinsic[2]))
    records[5, 1] = extrinsic
    values = asdict(policy)
    records[6, 1] = _record(6, 1, sources[0], POLICY.pack(_text(ALGORITHM, 32),
        _text(policy.threshold_status, 32), *(values[k] for k in POLICY_FIELDS)), config_u32)
    train, hold, nt, nh = Partition_Digests(session)
    records[7, 1] = _record(7, 1, sources[0], QUALITY.pack(bytes.fromhex(session.raw_digest), train, hold,
        _sha(records[6, 1]), _sha(extrinsic), bytes.fromhex(report.context_digest), *best.singular_values,
        best.train_rms, best.train_max, best.holdout_rms, best.holdout_max, nt, nh,
        0, 0, 0, 1, 0, 0), config_u32, zlib.crc32(extrinsic))
    archive = bytes.fromhex(archive_digest)
    if len(archive) != 32: raise ValueError("full raw archive digest required")
    manifest = MANIFEST.pack(bytes.fromhex(session.records[0].session), base_generation, base_generation+1,
        commit_rid, archive, binding, len(records))
    for (kind, role), record in sorted(records.items()): manifest += ENTRY.pack(kind, role, len(record), _sha(record))
    root = _record(8, 1, sources[0], manifest, config_u32)
    packet = b"".join(struct.pack("<H", len(x))+x for x in (root, *[r for _, r in sorted(records.items())]))
    if len(packet) > MAX_BUNDLE: raise ValueError("bundle capacity")
    Bundle_Decode(packet)
    return packet


def Bundle_Decode(packet):
    if type(packet) is not bytes or not 1 <= len(packet) <= MAX_BUNDLE: raise ValueError("bundle size")
    records, offset = [], 0
    for _ in range(MAX_RECORDS):
        if offset == len(packet): break
        if offset+2 > len(packet): raise ValueError("truncated record length")
        length = struct.unpack_from("<H", packet, offset)[0]; offset += 2
        if not 32 <= length <= MAX_RECORD or offset+length > len(packet): raise ValueError("record framing")
        raw = packet[offset:offset+length]; Record_Decode(raw); records.append(raw); offset += length
    if offset != len(packet) or len(records) != 10: raise ValueError("complete ten-record bundle required")
    header, payload = Record_Decode(records[0])
    if header[2] != 8 or header[4] != 1 or len(payload) < MANIFEST.size: raise ValueError("manifest first/role")
    sid, base, generation, rid, archive, binding, count = MANIFEST.unpack(payload[:MANIFEST.size])
    if (count != 9 or len(payload) != MANIFEST.size+count*ENTRY.size or not any(sid)
            or base == 2**32-1 or generation != base+1 or rid == 0 or not any(binding)):
        raise ValueError("manifest fields")
    expected_keys = [(2,1),(2,2),(3,1),(3,2),(4,1),(4,2),(5,1),(6,1),(7,1)]
    by_key = {}
    for i, raw in enumerate(records[1:]):
        kind, role, length, sha = ENTRY.unpack_from(payload, MANIFEST.size+i*ENTRY.size)
        h, _ = Record_Decode(raw)
        if ((kind, role) != expected_keys[i] or (h[2], h[4]) != (kind, role)
                or length != len(raw) or sha != _sha(raw) or h[8] != header[8]):
            raise ValueError("manifest content/order/config binding")
        by_key[kind, role] = raw
    for (kind, role), raw in by_key.items():
        h, _ = Record_Decode(raw); identity_header, _ = Record_Decode(by_key[2, role])
        if h[5:11] != identity_header[5:11]: raise ValueError("header endpoint mismatch")
    if header[5:11] != Record_Decode(by_key[2,1])[0][5:11] or header[-1] != 0:
        raise ValueError("manifest endpoint/header mismatch")
    sources, intrinsics = [], []
    for role in (1, 2):
        id_raw, provenance_raw = by_key[2, role], by_key[3, role]
        ih, ip = Record_Decode(id_raw); ph, pp = Record_Decode(provenance_raw)
        v, p = IDENTITY.unpack(ip), PROVENANCE.unpack(pp)
        identity = SensorIdentity(_untext(v[1]), ih[6], ih[5], ih[7], _untext(v[2]), _untext(v[3]), _untext(v[4]), _untext(v[5]))
        if (v[0] != role or p[0] != _sha(id_raw) or ph[-1] != zlib.crc32(id_raw)
                or ih[-1] != 0 or ih[9] != zlib.crc32(identity.driver.encode()) or ih[10] != zlib.crc32(identity.model.encode())
                or p[-2:] != (role, 0) or p[11] not in (0, 1)):
            raise ValueError("source identity/provenance binding")
        source = SourceDescriptor("IMU" if role == 1 else "MAG", identity,
            ("m/s2", "rad/s") if role == 1 else ("uT",), _untext(p[2]), _untext(p[3]), _untext(p[4]),
            _untext(p[5]), p[7], p[8], boot=_untext(p[1]), sequence_stride=p[9], sample_time_bits=p[10],
            timestamp_saturates=bool(p[11]), axis_mapping_applied=p[12:15], provider_calibration=_untext(p[6]))
        h, data = Record_Decode(by_key[4, role]); x = INTRINSIC.unpack(data)
        if x[:2] != (_sha(id_raw), _sha(provenance_raw)) or h[-1] != zlib.crc32(id_raw+provenance_raw) or x[-2:] != (role, 0):
            raise ValueError("intrinsic identity/model dependency")
        numeric = x[5:]
        if not np.isfinite(numeric).all() or np.linalg.norm(x[17:20]) > 1:
            raise ValueError("intrinsic numeric range")
        intrinsic = Intrinsic(identity, x[2], _untext(x[3]), x[5:8], np.array(x[8:17]).reshape(3,3),
            "m/s2" if role == 1 else "uT", _untext(x[4]))
        if (role == 1 and (x[20] != 0 or not np.array_equal(np.array(intrinsic.matrix), np.diag(np.diag(intrinsic.matrix))))) or (role == 2 and (x[17:20] != (0.,)*3 or not 10 <= x[20] <= 100)):
            raise ValueError("intrinsic physical model")
        sources.append(source); intrinsics.append(intrinsic)
    eh, ep = Record_Decode(by_key[5,1]); e = EXTRINSIC.unpack(ep)
    if (e[:4] != (_sha(by_key[2,1]), _sha(by_key[2,2]), _sha(by_key[4,1]), _sha(by_key[4,2]))
            or e[4:6] != tuple(x.generation for x in intrinsics) or eh[-1] != zlib.crc32(by_key[4,1]+by_key[4,2])):
        raise ValueError("extrinsic parent mismatch")
    ram = _matrix(np.array(e[6:15]).reshape(3,3), rotation=True)
    if not math.isfinite(e[24]) or not -1 <= e[24] <= 1 or e[25] not in (0,1): raise ValueError("extrinsic flags/value")
    rga = _matrix(np.array(e[15:24]).reshape(3,3), rotation=True) if e[25] else None
    if (not e[25] and any(e[15:24])) or (e[25] and _untext(e[26]) in ("UNKNOWN", "UNPROVEN")): raise ValueError("gyro axis evidence")
    policy_header, pp = Record_Decode(by_key[6,1]); p = POLICY.unpack(pp)
    if policy_header[-1] != 0: raise ValueError("policy parent CRC must be zero")
    if _untext(p[0]) != ALGORITHM or _untext(p[1]) != "PROVISIONAL_SYNTHETIC_ONLY": raise ValueError("policy provenance")
    vals = dict(zip(POLICY_FIELDS, p[2:]))
    for key in INTEGER_POLICY:
        if not math.isfinite(vals[key]) or not vals[key].is_integer(): raise ValueError("integer policy")
        vals[key] = int(vals[key])
    policy = Policy(**vals)
    qh, qp = Record_Decode(by_key[7,1]); q = QUALITY.unpack(qp)
    if (q[3:5] != (_sha(by_key[6,1]), _sha(by_key[5,1]))
            or qh[-1] != zlib.crc32(by_key[5,1]) or q[-6:] != (0,0,0,1,0,0)
            or q[13] == 0 or q[14] == 0 or not np.isfinite(q[6:13]).all() or min(q[6:13]) < 0):
        raise ValueError("quality evidence/dependency")
    return DraftBundle(tuple(records), tuple(sources), tuple(intrinsics), ram, rga, e[24], policy,
        archive.hex(), binding.hex(), base, generation, sid.hex(), rid)


def Bundle_VerifyContext(bundle, session, sources, binding_digest, base_generation, accel, mag, archive_digest, *, config_u32):
    if (bundle.fit_raw_digest != session.raw_digest or bundle.archive_digest != archive_digest or bundle.binding_digest != binding_digest
            or bundle.base_generation != base_generation or bundle.sources != tuple(sources)):
        raise ValueError("session/source/base dependency changed")
    if Record_Decode(bundle.records[0])[0][8] != config_u32: raise ValueError("configuration digest changed")
    for candidate, current in zip(bundle.intrinsics, (accel, mag)):
        if candidate.identity != current.identity or candidate.output_frame != current.output_frame:
            raise ValueError("identity/frame changed")
        if candidate.Digest() != current.Digest() and candidate.generation != current.generation+1:
            raise ValueError("intrinsic generation must replace current exactly once")
    q = QUALITY.unpack(bundle.records[-1][32:])
    train, hold, nt, nh = Partition_Digests(session)
    if q[1:3] != (train, hold) or q[13:15] != (nt, nh): raise ValueError("partition archive changed")
    if q[5].hex() != session.ContextDigest(bundle.intrinsics[0], bundle.intrinsics[1], bundle.policy):
        raise ValueError("fit context changed")
    return True
