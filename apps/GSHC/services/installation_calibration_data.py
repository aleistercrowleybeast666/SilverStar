"""Bounded offline source/pairing model. Not target firmware or a device driver."""
from collections import deque
from dataclasses import asdict, dataclass
from enum import Enum
import json
import re

from services.installation_calibration_fit import FACES, RawPair, SensorIdentity, _digest, _number, _uint


class CaptureResult(str, Enum):
    Accepted = "ACCEPTED"
    Paired = "PAIRED"
    Complete = "COMPLETE"
    Cancelled = "CANCELLED"
    Rejected = "REJECTED"
    Failed = "FAILED"


def Token_Check(value, limit=16):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,"+str(limit)+"}", value):
        raise ValueError("bounded ASCII token required")
    return value


@dataclass(frozen=True)
class SourceDescriptor:
    role: str
    identity: SensorIdentity
    units: tuple
    frame_provenance: str
    clock: str
    clock_provenance: str
    intrinsic_id: str
    intrinsic_generation: int
    epoch: int
    boot: str = "UNKNOWN"
    handedness: str = "RIGHT"
    axis_mapping_applied: tuple = (1, 2, 3)
    sequence_stride: int = 1
    sample_time_bits: int = 64
    timestamp_saturates: bool = False
    correction_layer: str = "PROVIDER_PHYSICAL_BEFORE_SOFTWARE_CORRECTION"
    provider_calibration: str = "UNKNOWN"

    def __post_init__(self):
        expected = {"IMU": ("m/s2", "rad/s"), "MAG": ("uT",)}
        if self.role not in expected or not isinstance(self.identity, SensorIdentity):
            raise ValueError("source role/identity required")
        object.__setattr__(self, "units", tuple(self.units))
        if self.units != expected[self.role] or self.correction_layer != "PROVIDER_PHYSICAL_BEFORE_SOFTWARE_CORRECTION":
            raise ValueError("explicit physical units and correction layer required")
        for key in ("frame_provenance", "clock", "clock_provenance", "intrinsic_id", "provider_calibration"):
            Token_Check(getattr(self, key), 64)
        _uint(self.epoch, 32); _uint(self.intrinsic_generation, 32)
        Token_Check(self.boot, 64)
        mapping = tuple(self.axis_mapping_applied)
        if (self.handedness != "RIGHT" or len(mapping) != 3
                or any(type(x) is not int for x in mapping) or sorted(abs(x) for x in mapping) != [1, 2, 3]):
            raise ValueError("explicit right-handed signed axis mapping required")
        inversions = sum(abs(mapping[i]) > abs(mapping[j]) for i in range(3) for j in range(i+1, 3))
        if (-1 if inversions % 2 else 1) * (-1 if sum(x < 0 for x in mapping) % 2 else 1) != 1:
            raise ValueError("axis reflection is not a proper mapping")
        object.__setattr__(self, "axis_mapping_applied", mapping)
        _uint(self.sequence_stride, 16, True)
        if self.sample_time_bits not in (32, 64) or type(self.timestamp_saturates) is not bool:
            raise ValueError("timestamp range/provenance required")

    def Digest(self):
        return _digest(asdict(self))


@dataclass(frozen=True)
class SourceSample:
    descriptor: SourceDescriptor
    sequence: int
    sample_us: int
    receive_us: int
    pc_receive_us: int
    uncertainty_us: int
    values: tuple
    flags: tuple = ()
    temperature_c: float | None = None
    raw_counts: tuple | None = None

    def __post_init__(self):
        if not isinstance(self.descriptor, SourceDescriptor):
            raise ValueError("immutable descriptor required")
        _uint(self.sequence, 32)
        _uint(self.sample_us, self.descriptor.sample_time_bits)
        for key in ("receive_us", "pc_receive_us"):
            _uint(getattr(self, key))
        _uint(self.uncertainty_us, 32)
        object.__setattr__(self, "values", tuple(_number(x) for x in self.values))
        count = 6 if self.descriptor.role == "IMU" else 3
        if len(self.values) != count:
            raise ValueError("complete source vector required")
        object.__setattr__(self, "flags", tuple(self.flags))
        if len(self.flags) != len(set(self.flags)) or not set(self.flags) <= {"GAP", "SATURATED", "INVALID"}:
            raise ValueError("known source quality flags required")
        if self.temperature_c is not None:
            object.__setattr__(self, "temperature_c", _number(self.temperature_c))
        if self.raw_counts is not None:
            counts = tuple(self.raw_counts)
            if len(counts) != count or any(type(x) is not int or not -2**31 <= x < 2**31 for x in counts):
                raise ValueError("signed source counts required")
            object.__setattr__(self, "raw_counts", counts)


@dataclass(frozen=True)
class WindowTag:
    stage: str
    face: str
    window: str
    pose: str
    split: str
    attempt: int = 1

    def __post_init__(self):
        if (self.stage not in ("MAG_ROTATE", "SIX_FACE", "SUPPLEMENT")
                or self.face not in (("NA",) if self.stage == "MAG_ROTATE" else FACES)):
            raise ValueError("static phase/face required; dynamic gyro is not implemented")
        if self.split not in ("TRAIN", "HOLDOUT"):
            raise ValueError("declared training/holdout split required")
        Token_Check(self.window); Token_Check(self.pose)
        _uint(self.attempt, 16, True)


@dataclass(frozen=True)
class CapturePolicy:
    source_capacity: int = 8
    pair_capacity: int = 32
    archive_capacity: int = 128
    min_pairs: int = 3
    max_skew_us: int = 2000
    max_uncertainty_us: int = 1000
    source_timeout_us: int = 250000
    window_timeout_us: int = 10000000

    def __post_init__(self):
        for value in asdict(self).values():
            _uint(value, 32, True)
        if (not 1 <= self.source_capacity <= 64 or not 1 <= self.pair_capacity <= 4096
                or not 1 <= self.archive_capacity <= 8192 or self.min_pairs > self.pair_capacity
                or self.source_timeout_us >= self.window_timeout_us):
            raise ValueError("bounded capture budget required")


@dataclass(frozen=True)
class CapturedPair:
    session: str
    boot: str
    pair_id: int
    tag: WindowTag
    imu: SourceSample
    mag: SourceSample

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{32}", self.session) or int(self.session, 16) == 0:
            raise ValueError("nonzero session id required")
        Token_Check(self.boot, 64); _uint(self.pair_id, 32, True)
        if self.imu.descriptor.role != "IMU" or self.mag.descriptor.role != "MAG":
            raise ValueError("two complete distinct sources required")
        if any(x.descriptor.boot != self.boot or x.descriptor.boot == "UNKNOWN" for x in (self.imu, self.mag)):
            raise ValueError("source boot binding required")

    def QualityCheck(self, policy=CapturePolicy()):
        """Shared source/pair boundary checks; does not prove static gravity."""
        a, m = self.imu, self.mag
        if (a.flags or m.flags or a.descriptor.clock != m.descriptor.clock
                or a.descriptor.clock_provenance == "UNKNOWN" or m.descriptor.clock_provenance == "UNKNOWN"
                or a.descriptor.clock == "PC_RECEIVE_PROXY"
                or a.descriptor.frame_provenance == "UNKNOWN" or m.descriptor.frame_provenance == "UNKNOWN"
                or abs(a.sample_us-m.sample_us)+a.uncertainty_us+m.uncertainty_us > policy.max_skew_us
                or a.uncertainty_us+m.uncertainty_us > policy.max_uncertainty_us
                or a.receive_us < a.sample_us or m.receive_us < m.sample_us):
            raise ValueError("unqualified paired data")
        if any(x.descriptor.timestamp_saturates and x.sample_us == 2**x.descriptor.sample_time_bits-1 for x in (a, m)):
            raise ValueError("saturated source timestamp")

    def RawPair(self, policy=CapturePolicy()):
        """Only qualified static pairs may enter the existing mathematical API."""
        if self.tag.stage == "MAG_ROTATE":
            raise ValueError("rotation motion is not static gravity")
        self.QualityCheck(policy)
        a, m = self.imu, self.mag
        return RawPair(self.session, self.boot, self.pair_id, a.descriptor.identity, m.descriptor.identity,
            a.descriptor.epoch, m.descriptor.epoch, a.sequence, m.sequence, a.sample_us, m.sample_us,
            a.receive_us, m.receive_us, a.descriptor.clock, a.uncertainty_us+m.uncertainty_us, True, (),
            self.tag.stage, self.tag.face, self.tag.window, self.tag.pose, self.tag.split,
            a.values[:3], a.values[3:], m.values,
            (a.descriptor.intrinsic_id, m.descriptor.intrinsic_id),
            (a.descriptor.intrinsic_generation, m.descriptor.intrinsic_generation))


class BoundedCollector:
    """Single-owner model with no nearest/latest-value substitution or silent drop.

    One-to-one FIFO matching, finite work per feed. Queue overflow, sequence gaps,
    excessive skew or timeout fail the entire window and preserve its archive.
    """
    def __init__(self, session, boot, imu, mag, policy=CapturePolicy()):
        if imu.role != "IMU" or mag.role != "MAG":
            raise ValueError("selected source roles required")
        if not re.fullmatch(r"[0-9a-f]{32}", session) or int(session, 16) == 0:
            raise ValueError("nonzero session id required")
        Token_Check(boot, 64)
        self.session, self.boot, self.sources, self.policy = session, boot, {"IMU": imu, "MAG": mag}, policy
        self.archive, self.pairs, self.windows, self.outcomes = [], [], [], {}
        self.owner_times, self.window_bounds = [], {}
        self.pending = {"IMU": deque(), "MAG": deque()}
        self.last, self.last_seen, self.next_pair = {}, {}, 1
        self.state, self.reason, self.tag = "IDLE", "NONE", None
        self.now, self.started, self.count, self.overflow_count = 0, 0, 0, 0

    def _fail(self, reason):
        active = self.state == "COLLECTING"
        self.state, self.reason = "FAILED", reason
        if active and self.tag is not None:
            self.outcomes[self.tag.window] = reason
            self.window_bounds[self.tag.window]["end_us"] = self.now
        return CaptureResult.Failed

    def _time(self, now):
        _uint(now)
        if now < self.now:
            return False
        self.now = now
        return True

    def Start(self, tag, now_us):
        if self.state == "COLLECTING" or self.state == "CANCELLED":
            self.reason = "WINDOW_BUSY_OR_CANCELLED"
            return CaptureResult.Rejected
        if not self._time(now_us):
            return self._fail("OWNER_CLOCK_REVERSED")
        if any(x.window == tag.window for x in self.windows) or len(self.windows) >= 64:
            self.reason = "WINDOW_LIMIT_OR_DUPLICATE"
            return CaptureResult.Rejected
        if (any(d.boot != self.boot or d.boot == "UNKNOWN" for d in self.sources.values())
                or self.sources["IMU"].clock != self.sources["MAG"].clock
                or self.sources["IMU"].clock == "PC_RECEIVE_PROXY"
                or any(x.clock_provenance == "UNKNOWN" or x.frame_provenance == "UNKNOWN" for x in self.sources.values())):
            return self._fail("BOOT_TIME_OR_COORDINATES_UNPROVEN")
        self.tag, self.started, self.count = tag, now_us, 0
        self.pending = {"IMU": deque(), "MAG": deque()}
        # Sequence continuity is required inside each selected window. Samples
        # outside a window are explicitly outside this archive's coverage.
        self.last = {}
        self.last_seen = {"IMU": now_us, "MAG": now_us}
        self.state, self.reason = "COLLECTING", "NONE"
        self.windows.append(tag)
        self.outcomes[tag.window] = "COLLECTING"
        self.window_bounds[tag.window] = {"start_us": now_us, "end_us": None}
        return CaptureResult.Accepted

    def Feed(self, sample, now_us):
        if self.state != "COLLECTING":
            return CaptureResult.Rejected
        if not self._time(now_us):
            return self._fail("OWNER_CLOCK_REVERSED")
        if self.Poll(now_us) == CaptureResult.Failed:
            return CaptureResult.Failed
        role = sample.descriptor.role
        if len(self.archive) >= self.policy.archive_capacity:
            self.overflow_count += 1
            return self._fail("ARCHIVE_BUFFER_FULL")
        self.archive.append((self.tag, sample))
        self.owner_times.append(now_us)
        if sample.descriptor != self.sources[role]:
            return self._fail("SOURCE_OR_PARENT_CHANGED")
        if (sample.flags or sample.uncertainty_us > self.policy.max_uncertainty_us
                or sample.receive_us < sample.sample_us or sample.receive_us > now_us):
            return self._fail("SOURCE_QUALITY_OR_TIME_UNCERTAIN")
        d = sample.descriptor
        if d.timestamp_saturates and sample.sample_us == 2**d.sample_time_bits-1:
            return self._fail("SAMPLE_TIME_SATURATED")
        previous = self.last.get(role)
        if previous is not None:
            delta = (sample.sequence-previous.sequence) % 2**32
            if delta != d.sequence_stride or sample.sample_us <= previous.sample_us:
                return self._fail("SOURCE_SEQUENCE_GAP_OR_REORDER")
        if len(self.pending[role]) >= self.policy.source_capacity:
            self.overflow_count += 1
            return self._fail("SOURCE_BUFFER_FULL")
        self.pending[role].append(sample); self.last[role] = sample; self.last_seen[role] = now_us
        if not all(self.pending.values()):
            return CaptureResult.Accepted
        a, m = self.pending["IMU"][0], self.pending["MAG"][0]
        if (abs(a.sample_us-m.sample_us)+a.uncertainty_us+m.uncertainty_us > self.policy.max_skew_us
                or a.uncertainty_us+m.uncertainty_us > self.policy.max_uncertainty_us):
            return self._fail("PAIR_SKEW_OR_UNCERTAINTY")
        if len(self.pairs) >= self.policy.pair_capacity or self.next_pair >= 2**32:
            self.overflow_count += 1
            return self._fail("PAIR_BUFFER_FULL")
        pair = CapturedPair(self.session, self.boot, self.next_pair, self.tag, a, m)
        self.pairs.append(pair); self.next_pair += 1; self.count += 1
        self.pending["IMU"].popleft(); self.pending["MAG"].popleft()
        return CaptureResult.Paired

    def Poll(self, now_us):
        if not self._time(now_us):
            return self._fail("OWNER_CLOCK_REVERSED")
        if self.state == "COLLECTING":
            if now_us-self.started >= self.policy.window_timeout_us:
                return self._fail("WINDOW_TIMEOUT")
            if any(now_us-x >= self.policy.source_timeout_us for x in self.last_seen.values()):
                return self._fail("SOURCE_TIMEOUT")
        return CaptureResult.Accepted

    def Stop(self, now_us):
        if self.Poll(now_us) == CaptureResult.Failed or self.state != "COLLECTING":
            return CaptureResult.Failed
        if any(self.pending.values()) or self.count < self.policy.min_pairs:
            return self._fail("INCOMPLETE_WINDOW")
        self.state = "COMPLETE"
        self.outcomes[self.tag.window] = "COMPLETE"
        self.window_bounds[self.tag.window]["end_us"] = now_us
        return CaptureResult.Complete

    def Cancel(self):
        # Keep raw archive and pairs; stop accepting new data before releasing owner.
        if self.tag is not None and self.state == "COLLECTING":
            self.outcomes[self.tag.window] = "CANCELLED"
            self.window_bounds[self.tag.window]["end_us"] = self.now
        self.state, self.reason = "CANCELLED", "CANCELLED"
        return CaptureResult.Cancelled

    def AbortWindow(self, now_us):
        if self.state != "COLLECTING" or not self._time(now_us): return CaptureResult.Rejected
        self.outcomes[self.tag.window] = "CANCELLED"
        self.window_bounds[self.tag.window]["end_us"] = now_us
        self.pending = {"IMU": deque(), "MAG": deque()}
        self.state, self.reason = "IDLE", "WINDOW_CANCELLED"
        return CaptureResult.Cancelled

    def Snapshot(self):
        return {"state": self.state, "reason": self.reason, "samples": len(self.archive),
                "pairs": len(self.pairs), "window_pairs": self.count, "overflow": self.overflow_count,
                "pending_imu": len(self.pending["IMU"]), "pending_mag": len(self.pending["MAG"]),
                "archive": tuple(self.archive), "records": tuple(self.pairs),
                "outcomes": tuple(self.outcomes.items()), "apply_allowed": False}

    def StaticRecords(self):
        return tuple(p.RawPair(self.policy) for p in self.pairs
                     if p.tag.stage != "MAG_ROTATE" and self.outcomes[p.tag.window] == "COMPLETE")

    def ArchiveExport(self):
        """Owned JSON-compatible raw archive; descriptor references are content hashes."""
        descriptors = {d.Digest(): asdict(d) for d in self.sources.values()}
        records = []
        sample_index = {}
        for index, (tag, sample) in enumerate(self.archive):
            digest = sample.descriptor.Digest()
            descriptors[digest] = asdict(sample.descriptor)
            values = asdict(sample); del values["descriptor"]
            records.append({"tag": asdict(tag), "descriptor": digest, "sample": values, "owner_us": self.owner_times[index]})
            sample_index.setdefault((tag, sample), index)
        return {"session": self.session, "boot": self.boot, "policy": asdict(self.policy),
                "descriptors": descriptors, "records": records, "outcomes": dict(self.outcomes),
                "selected_sources": {role: d.Digest() for role, d in self.sources.items()},
                "windows": [asdict(tag) for tag in self.windows],
                "window_bounds": {k: dict(v) for k, v in self.window_bounds.items()},
                "pairs": [{"pair_id": p.pair_id, "imu": sample_index[p.tag, p.imu], "mag": sample_index[p.tag, p.mag]} for p in self.pairs],
                "state": self.state, "reason": self.reason, "overflow_count": self.overflow_count,
                "apply_allowed": False}


@dataclass(frozen=True)
class ReplayArchive:
    payload_json: bytes
    archive_digest: str
    static_records: tuple
    sources: tuple
    samples: tuple
    complete_windows: tuple

    def MagTrainingSamples(self):
        return tuple(sample for tag, sample, _ in self.samples if tag.stage == "MAG_ROTATE"
                     and tag.split == "TRAIN" and tag.window in self.complete_windows
                     and sample.descriptor.role == "MAG")


def Archive_Import(payload):
    """Validate complete windows against recorded owner times; retain all raw data.

    Failed/cancelled windows remain evidence and never become fitting input.
    This is an offline archive format, not SSLOG or a wire-version addition.
    """
    expected = {"session", "boot", "policy", "descriptors", "selected_sources", "windows", "records",
                "outcomes", "window_bounds", "pairs", "state", "reason", "overflow_count", "apply_allowed"}
    if type(payload) is not dict or set(payload) != expected or payload["apply_allowed"] is not False:
        raise ValueError("complete bounded raw archive required")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > 16*1024*1024: raise ValueError("archive byte budget")
    data = json.loads(encoded)
    policy = CapturePolicy(**data["policy"])
    if (len(data["records"]) > policy.archive_capacity or len(data["pairs"]) > policy.pair_capacity
            or len(data["windows"]) > 64 or not 2 <= len(data["descriptors"]) <= 128
            or set(data["selected_sources"]) != {"IMU", "MAG"}):
        raise ValueError("archive count budget")
    descriptors = {}
    for digest, item in data["descriptors"].items():
        fields = dict(item); fields["identity"] = SensorIdentity(**fields["identity"])
        descriptor = SourceDescriptor(**fields)
        if descriptor.Digest() != digest: raise ValueError("descriptor digest")
        descriptors[digest] = descriptor
    sources = tuple(descriptors[data["selected_sources"][role]] for role in ("IMU", "MAG"))
    BoundedCollector(data["session"], data["boot"], *sources, policy)
    tags = {item["window"]: WindowTag(**item) for item in data["windows"]}
    if (len(tags) != len(data["windows"]) or set(tags) != set(data["outcomes"])
            or set(tags) != set(data["window_bounds"])): raise ValueError("window inventory")
    samples, last_owner = [], 0
    for row in data["records"]:
        if set(row) != {"tag", "descriptor", "sample", "owner_us"}: raise ValueError("raw row fields")
        tag, sample = WindowTag(**row["tag"]), SourceSample(descriptors[row["descriptor"]], **row["sample"])
        if tags.get(tag.window) != tag: raise ValueError("raw window binding")
        owner = _uint(row["owner_us"])
        bounds = data["window_bounds"][tag.window]
        if owner < last_owner or owner < bounds["start_us"] or (bounds["end_us"] is not None and owner > bounds["end_us"]):
            raise ValueError("recorded owner time")
        samples.append((tag, sample, owner)); last_owner = owner
    pairs = []
    for i, row in enumerate(data["pairs"]):
        if set(row) != {"pair_id", "imu", "mag"} or row["pair_id"] != i+1: raise ValueError("pair sequence")
        for key in ("imu", "mag"):
            if type(row[key]) is not int or not 0 <= row[key] < len(samples): raise ValueError("pair source index")
        a, m = samples[row["imu"]], samples[row["mag"]]
        if a[0] != m[0]: raise ValueError("pair window mismatch")
        pair = CapturedPair(data["session"], data["boot"], row["pair_id"], a[0], a[1], m[1])
        pair.QualityCheck(policy); pairs.append(pair)
    complete = tuple(name for name, outcome in data["outcomes"].items() if outcome == "COMPLETE")
    for name in complete:
        tag = tags[name]; bounds = data["window_bounds"][name]
        probe = BoundedCollector(data["session"], data["boot"], *sources, policy)
        if probe.Start(tag, bounds["start_us"]) != CaptureResult.Accepted: raise ValueError("window replay start")
        rows = [x for x in samples if x[0].window == name]
        for _, sample, owner in rows:
            if probe.Feed(sample, owner) not in (CaptureResult.Accepted, CaptureResult.Paired):
                raise ValueError("unqualified completed window")
        if bounds["end_us"] is None or probe.Stop(bounds["end_us"]) != CaptureResult.Complete:
            raise ValueError("window replay completion")
        selected = [p for p in pairs if p.tag.window == name]
        if (len(rows) != 2*len(selected) or len(probe.pairs) != len(selected)
                or any((a.imu, a.mag) != (b.imu, b.mag) for a, b in zip(probe.pairs, selected))):
            raise ValueError("raw/pair completeness")
    static = tuple(p.RawPair(policy) for p in pairs if p.tag.window in complete and p.tag.stage != "MAG_ROTATE")
    return ReplayArchive(encoded, _digest(data), static, sources, tuple(samples), complete)
