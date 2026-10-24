"""Offline INSTALL owner/mailbox model; no device, filesystem or GUI operations."""
from dataclasses import asdict, dataclass, replace
from enum import Enum
import hashlib
import json
import zlib

from .capture import BoundedCollector, CapturePolicy, CaptureResult, WindowTag
from .protocol import CHUNK_BYTES, Request_Decode, Response, Response_Decode, Response_Encode
from .prototype import CandidateReport, CandidateResult, Convention, InstallationSession, Policy, _digest, _uint
from .ssic_draft import Bundle_Decode, Bundle_VerifyContext, MAX_BUNDLE


class CapabilityResult(str, Enum):
    Supported = "SUPPORTED_OFFLINE"
    Unsupported = "UNSUPPORTED"
    Unknown = "UNKNOWN"


class CandidateAttachResult(str, Enum):
    Accepted = "ACCEPTED"
    PhaseNotReady = "PHASE_NOT_READY"
    ContextMismatch = "CONTEXT_MISMATCH"
    EvidenceInvalid = "EVIDENCE_INVALID"


def Capability_Decode(line):
    # Only explicit unsupported results allow legacy fallback, never timeout or
    # malformed partial fields. A maintenance version alone implies nothing.
    if line in (b"ERR INSTALL CAPS code=BAD_MODULE reason=UNKNOWN",
                b"ERR INSTALL CAPS code=UNSUPPORTED reason=CAPABILITY"):
        return CapabilityResult.Unsupported
    try:
        response = Response_Decode(line, operation="CAPS")
        if (response.status != "OK" or response.Field("maintenance") != "0.1"
                or response.Field("supported") != "1" or response.Field("offline") != "1"
                or response.Field("apply") != "0" or response.Field("max_request") != "191"
                or response.Field("max_line") != "511" or response.Field("max_chunk") != "48"
                or response.Field("lease_us") != "30000000"):
            return CapabilityResult.Unknown
        for key, maximum in (("source_capacity", 64), ("pair_capacity", 4096), ("archive_capacity", 8192)):
            value = response.Field(key)
            if value is None or not value.isdecimal() or not 1 <= int(value) <= maximum:
                return CapabilityResult.Unknown
        return CapabilityResult.Supported
    except ValueError:
        return CapabilityResult.Unknown


@dataclass(frozen=True)
class StateView:
    phase: str
    reason: str
    sequence: int
    face_mask: int
    pairs: int
    cleanup_complete: bool
    connected: bool


def State_Decode(line, sid):
    """Strict complete state view; a future phase is UNKNOWN, never READY."""
    response = Response_Decode(line, "STATUS", sid)
    if response.status != "OK" or response.Field("role") != "STATE":
        raise ValueError("complete STATE response required")
    required = ("state", "reason", "seq", "face_mask", "pairs", "cleanup_complete", "connected",
                "imu_ready", "extrinsic_validated", "apply", "saved")
    if any(response.Field(key) is None for key in required): raise ValueError("missing STATE fields")
    if any(response.Field(key) != "0" for key in ("imu_ready", "extrinsic_validated", "apply", "saved")):
        raise ValueError("offline readiness or application assertion is forbidden")
    from .protocol import _decimal
    sequence = _decimal(response.Field("seq"), 64)
    mask, pairs = _decimal(response.Field("face_mask"), 8), _decimal(response.Field("pairs"), 32)
    if mask > 63 or any(response.Field(key) not in ("0", "1") for key in ("cleanup_complete", "connected")):
        raise ValueError("STATE ranges")
    phase = response.Field("state")
    if phase not in {"IDLE", "MAG_COLLECT", "MAG_FIT", "FACE_WAIT", "FACE_COLLECT", "SOLVE", "NEED_SAMPLES",
                     "CANDIDATE_ONLY", "CANCEL_PENDING", "CANCELLED", "FAILED", "UNKNOWN"}: phase = "UNKNOWN"
    return StateView(phase, response.Field("reason"), sequence, mask, pairs,
                     response.Field("cleanup_complete") == "1", response.Field("connected") == "1")


class ResourceGate:
    """Models both shared transport ownership and latched export exclusion."""
    def __init__(self):
        self.owner, self.export_latched = None, False

    def Acquire(self, owner):
        if self.owner == "LOGFILE": return "TF_TRANSFER"
        if self.export_latched: return "REBOOT_REQUIRED"
        if self.owner is not None: return "TF_TRANSFER" if self.owner == "LOGFILE" else "CONFIG_ACTION"
        self.owner = owner
        return None

    def Release(self, owner):
        if self.owner == owner: self.owner = None

    def TransferEnter(self):
        if self.owner is not None: return "CONFIG_ACTION"
        self.owner, self.export_latched = "LOGFILE", True
        return None

    def TransferCancel(self):
        self.Release("LOGFILE")  # Export latch persists until actual boot reset.


@dataclass(frozen=True)
class UploadSpec:
    length: int
    sha256: str
    crc32: str

    def __post_init__(self):
        import re
        if (type(self.length) is not int or not 1 <= self.length <= MAX_BUNDLE
                or not re.fullmatch(r"[0-9a-f]{64}", self.sha256)
                or not re.fullmatch(r"[0-9A-F]{8}", self.crc32)):
            raise ValueError("bounded declared opaque upload metadata required")


class OfflineSession:
    """Single pending operation; only latest rid retry is retained.

    UploadSpec is deliberately injected by a test binding, because a complete
    installation SSIC object/header is NOT frozen by this experiment.
    """
    def __init__(self, boot, imu, mag, accel_intrinsic, mag_intrinsic, gate=None,
                 policy=CapturePolicy(), upload=None, math_convention=Convention(), base_generation=0, config_u32=0):
        if (accel_intrinsic.identity != imu.identity or mag_intrinsic.identity != mag.identity
                or accel_intrinsic.unit != "m/s2" or mag_intrinsic.unit != "uT"):
            raise ValueError("matching source/parent identity and units required")
        self.boot, self.sources = boot, {"IMU": imu, "MAG": mag}
        self.accel, self.mag, self.capture_policy = accel_intrinsic, mag_intrinsic, policy
        self.gate, self.upload_spec = gate or ResourceGate(), upload
        _uint(base_generation, 32); _uint(config_u32, 32)
        self.convention, self.base_generation, self.config_u32 = math_convention, base_generation, config_u32
        self.explicit_windows, self._formal_upload, self.staged_bundle = False, False, None
        self.upload_origin_rid, self.upload_previous_state = 0, "SOLVE"
        self.sid, self.state, self.reason, self.now = None, "IDLE", "NONE", 0
        self.sequence, self.face_mask, self.attempt = 0, 0, 0
        self.latest, self.collector, self.candidate = None, None, None
        self.candidate_context = None
        self.connected, self.lease, self.started = True, 0, 0
        self.upload = bytearray(upload.length if upload else 0)
        self.written = bytearray(len(self.upload))
        self.views = {}
        self._binding()

    def _binding(self):
        self.binding_digest = _digest({"boot": self.boot, "sources": {k: asdict(v) for k, v in self.sources.items()},
            "accel": self.accel.Digest(), "mag": self.mag.Digest(),
            "convention": asdict(self.convention), "base_generation": self.base_generation,
            "configuration_u32": self.config_u32, "capture_policy": asdict(self.capture_policy)})
        self.binding = "B-"+self.binding_digest[:30]
        self.binding_deadline = self.now+5000000
        self.info = json.dumps({"boot": self.boot, "sources": {k: asdict(v) for k, v in self.sources.items()},
            "accel": asdict(self.accel), "mag": asdict(self.mag), "binding_digest": self.binding_digest,
            "convention": asdict(self.convention), "base_generation": self.base_generation,
            "configuration_u32": self.config_u32, "hardware_evidence": "NOT_PROVEN"},
            sort_keys=True, separators=(",", ":")).encode("ascii")

    def _change(self, state, reason="NONE"):
        self.state, self.reason = state, reason
        self.sequence += 1; self.views.clear()

    def _discard_staging(self):
        self.candidate, self.candidate_context = None, None
        self.staged_bundle = None
        if self._formal_upload:
            self.upload_spec = None; self.upload, self.written = bytearray(), bytearray()
        self._formal_upload = False
        self.upload[:] = bytes(len(self.upload)); self.written[:] = bytes(len(self.written))
        self.views.clear()

    def _response(self, status, op, **fields):
        return Response(status, op, tuple((k, str(v)) for k, v in fields.items()))

    def _error(self, op, code, reason, **fields):
        return self._response("ERR", op, code=code, reason=reason, **fields)

    def Tick(self, now_us):
        _uint(now_us)
        if now_us < self.now: raise ValueError("owner clock reversed")
        self.now = now_us
        if self.state == "CANCEL_PENDING" and now_us-self.lease >= 500000:
            self.Process(now_us)
            return
        if self.sid and self.gate.owner == self.sid and self.state != "CANCEL_PENDING":
            if now_us-self.lease >= 30000000 or now_us-self.started >= 120000000:
                if self.collector: self.collector.Cancel()
                self._discard_staging()
                self.gate.Release(self.sid); self._change("FAILED", "SESSION_TIMEOUT")
                if self.latest:
                    rid, fingerprint, prior = self.latest
                    self.latest = rid, fingerprint, self._error(prior.operation, "TIMEOUT", "SESSION_TIMEOUT",
                        sid=self.sid, rid=rid, cleanup_complete=1, apply=0)
        if self.collector and self.collector.state == "COLLECTING" and self.state != "UNKNOWN":
            if self.collector.Poll(now_us) == CaptureResult.Failed:
                self.candidate = None; self._change("FAILED", self.collector.reason)

    def Process(self, now_us):
        """Model owner cleanup completion independently of request acceptance."""
        if self.state != "CANCEL_PENDING": self.Tick(now_us)
        elif now_us < self.now: raise ValueError("owner clock reversed")
        self.now = now_us
        if self.state == "CANCEL_PENDING":
            self._discard_staging()
            self.gate.Release(self.sid); self._change("CANCELLED", "CANCELLED")
            if self.latest:
                rid, fingerprint, _ = self.latest
                response = self._response("OK", "DO", sid=self.sid, rid=rid, action="CANCEL",
                    state="CANCELLED", cleanup_complete=1, apply=0)
                self.latest = rid, fingerprint, response

    def Disconnect(self):
        self.connected = False
        if self.sid and self.state not in ("CANCELLED", "FAILED", "CANCEL_PENDING"):
            self.candidate = None; self._change("UNKNOWN", "DISCONNECTED")

    def Reconnect(self):
        self.connected = True  # No resumption, automatic retries or fresh BEGIN.

    def ParentsUpdate(self, accel, mag):
        if accel.Digest() == self.accel.Digest() and mag.Digest() == self.mag.Digest(): return
        if (accel.identity != self.sources["IMU"].identity or mag.identity != self.sources["MAG"].identity
                or accel.unit != "m/s2" or mag.unit != "uT"):
            raise ValueError("parent identity or unit change requires a new explicit source binding")
        self.accel, self.mag, self.candidate = accel, mag, None
        self._discard_staging()
        self.sources["IMU"] = replace(self.sources["IMU"], intrinsic_id=accel.calibration_id,
                                      intrinsic_generation=accel.generation)
        self.sources["MAG"] = replace(self.sources["MAG"], intrinsic_id=mag.calibration_id,
                                      intrinsic_generation=mag.generation)
        if self.collector: self.collector.Cancel()
        self._change("FAILED", "PARENT_CHANGED"); self._binding()

    def Feed(self, sample, now_us):
        self.Tick(now_us)
        if not self.connected or self.state not in ("MAG_COLLECT", "FACE_COLLECT"):
            return CaptureResult.Rejected
        result = self.collector.Feed(sample, now_us)
        if result == CaptureResult.Failed:
            self.candidate = None; self._change("FAILED", self.collector.reason)
        return result

    def CandidateAttach(self, report, mathematical_session, policy=Policy()):
        if self.state not in ("SOLVE", "NEED_SAMPLES") or self.collector is None:
            return CandidateAttachResult.PhaseNotReady
        if (not isinstance(report, CandidateReport) or report.apply_allowed
                or (report.result == CandidateResult.Candidate and not report.candidates)):
            return CandidateAttachResult.EvidenceInvalid
        if (tuple(mathematical_session.records) != self.collector.StaticRecords()
                or not mathematical_session.CandidateIsCurrent(report, self.accel, self.mag, policy)):
            return CandidateAttachResult.ContextMismatch
        self.candidate = report
        self.candidate_context = {"convention": asdict(mathematical_session.convention),
            "policy": asdict(policy), "raw_digest": mathematical_session.raw_digest,
            "algorithm": "OFFLINE_SCIPY_MULTISTART"}
        self._change("NEED_SAMPLES" if report.result != CandidateResult.Candidate else "CANDIDATE_ONLY",
                     "OFFLINE_REVIEW_REQUIRED")
        return CandidateAttachResult.Accepted

    def Handle(self, body, now_us):
        request = Request_Decode(body); self.Tick(now_us)
        op, args = request.operation, request.arguments
        if op == "CAPS":
            return self._response("OK", op, maintenance="0.1", supported=1, offline=1, apply=0,
                max_request=191, max_line=511, max_chunk=48, source_capacity=self.capture_policy.source_capacity,
                pair_capacity=self.capture_policy.pair_capacity, archive_capacity=self.capture_policy.archive_capacity,
                lease_us=30000000, dynamic_gyro="NOT_IMPLEMENTED", windows="EXPLICIT", ssic_schema=1,
                max_record=512, max_bundle=MAX_BUNDLE, install_kinds="DRAFT_2-8")
        if op == "INFO":
            if args[0] != f'{self.sources["IMU"].identity.instance}:{self.sources["MAG"].identity.instance}':
                return self._error(op, "WRONG_DEVICE", "ENDPOINTS")
            if int(args[1]) == 0: self._binding()
            offset = int(args[1])
            if offset >= len(self.info) or offset % CHUNK_BYTES:
                return self._error(op, "STALE", "INFO_CURSOR")
            chunk = self.info[offset:offset+CHUNK_BYTES]
            return self._response("OK", op, binding=self.binding, cursor=offset,
                next=offset+len(chunk), end=int(offset+len(chunk) == len(self.info)),
                length=len(self.info), sha256=hashlib.sha256(self.info).hexdigest(), data=chunk.hex().upper())
        if op == "STATUS": return self._status(args)
        if op == "READ": return self._read(args)
        if op == "POLL":
            if args[0] != self.sid: return self._error(op, "SESSION_UNKNOWN", "SID", sid=args[0], rid=args[1])
            if not self.latest or self.latest[0] != int(args[1]):
                return self._error(op, "STALE", "REQUEST", sid=self.sid, rid=args[1])
            return self.latest[2]  # Original operation, not OK ... POLL.
        sid, rid = args[0], int(args[1]); fingerprint = _digest(asdict(request))
        if sid == self.sid and self.latest:
            if rid == self.latest[0]:
                return self.latest[2] if fingerprint == self.latest[1] else self._error(op, "CONFLICT", "REQUEST_CHANGED", sid=sid, rid=rid)
            if rid < self.latest[0]: return self._error(op, "STALE", "REQUEST", sid=sid, rid=rid)
            if self.latest[2].status == "PENDING" and not (op == "DO" and args[2] == "CANCEL"):
                return self._error(op, "BUSY", "PENDING_OPERATION", sid=sid, rid=rid)
        if not self.connected or (self.state == "UNKNOWN" and not (op == "DO" and args[2] == "CANCEL")):
            return self._error(op, "UNKNOWN", "QUERY_BEFORE_RETRY", sid=sid, rid=rid)
        if op == "BEGIN":
            response = self._begin(sid, rid, args[2])
        elif sid != self.sid:
            return self._error(op, "SESSION_UNKNOWN", "SID", sid=sid, rid=rid)
        elif self.gate.owner != self.sid or (self.state in ("CANCELLED", "FAILED") and not (op == "DO" and args[2] == "CANCEL")):
            return self._error(op, "NOT_READY", "SESSION_TERMINAL", sid=sid, rid=rid)
        elif op == "PUT": response = self._put(sid, rid, args[2])
        elif op == "WINDOW": response = self._window(sid, rid, args[2])
        elif op == "UPLOAD": response = self._upload_start(sid, rid, args[2])
        else: response = self._action(sid, rid, args[2])
        if sid == self.sid:
            self.latest = rid, fingerprint, response; self.lease = self.now
        return response

    def _begin(self, sid, rid, binding):
        if binding != self.binding or self.now >= self.binding_deadline:
            return self._error("BEGIN", "STALE", "BINDING", sid=sid, rid=rid)
        if sid == self.sid:
            return self._error("BEGIN", "CONFLICT", "SID_REUSE", sid=sid, rid=rid)
        reason = self.gate.Acquire(sid)
        if reason: return self._error("BEGIN", "LOCKED" if reason == "REBOOT_REQUIRED" else "BUSY", reason, sid=sid, rid=rid)
        self.sid, self.started, self.lease = sid, self.now, self.now
        self.collector = BoundedCollector(sid, self.boot, self.sources["IMU"], self.sources["MAG"], self.capture_policy)
        self.face_mask, self.attempt, self.latest = 0, 0, None
        self.explicit_windows = False
        self._discard_staging()
        self._change("IDLE")
        return self._response("OK", "BEGIN", sid=sid, rid=rid, state=self.state, apply=0)

    def _action(self, sid, rid, action):
        common = {"sid": sid, "rid": rid, "action": action}
        if action == "CANCEL":
            self.collector.Cancel(); self.candidate = None; self._change("CANCEL_PENDING", "CANCELLED")
            return self._response("PENDING", "DO", **common, state=self.state, cleanup_complete=0)
        if action in ("APPLY", "SAVE", "VALIDATE"):
            complete = bool(self.written) and all(self.written)
            reason = "NO_QUALITY_EVIDENCE" if self.candidate is None else "OFFLINE_REVIEW_REQUIRED"
            if action == "VALIDATE" and self.upload_spec and not complete: reason = "INCOMPLETE_OBJECT"
            return self._error("DO", "NOT_PROVEN", reason, **common, apply=0, saved=0)
        if action == "UPLOAD_CANCEL":
            if not self._formal_upload:
                return self._error("DO", "NOT_READY", "NO_UPLOAD", **common)
            self._discard_staging(); self._change(self.upload_previous_state, "UPLOAD_CANCELLED")
            return self._response("OK", "DO", **common, state=self.state, cleanup_complete=1, apply=0)
        if action == "CAPTURE_DONE":
            holds = {p.tag.window for p in self.collector.pairs if p.tag.split == "HOLDOUT"
                     and self.collector.outcomes[p.tag.window] == "COMPLETE" and p.tag.stage != "MAG_ROTATE"}
            if self.state not in ("FACE_WAIT", "NEED_SAMPLES") or self.face_mask != 63 or len(holds) < 3:
                return self._error("DO", "NOT_READY", "TRAIN_SIX_AND_HOLDOUT_REQUIRED", **common)
            self._discard_staging(); self._change("SOLVE")
            return self._response("OK", "DO", **common, state=self.state, raw_digest=_digest(self.collector.ArchiveExport()), apply=0)
        if action == "WINDOW_CANCEL" and self.state in ("MAG_COLLECT", "FACE_COLLECT"):
            stage = self.collector.tag.stage
            self.collector.AbortWindow(self.now)
            self._change("IDLE" if stage == "MAG_ROTATE" else "NEED_SAMPLES" if stage == "SUPPLEMENT" else "FACE_WAIT", "WINDOW_CANCELLED")
            return self._response("OK", "DO", **common, state=self.state, apply=0)
        if action == "WINDOW_STOP" and self.state in ("MAG_COLLECT", "FACE_COLLECT"):
            tag = self.collector.tag
            if self.collector.Stop(self.now) != CaptureResult.Complete:
                self._change("FAILED", self.collector.reason)
                return self._error("DO", "NOT_READY", self.reason, **common)
            if tag.split == "TRAIN" and tag.stage == "SIX_FACE":
                from .prototype import FACES
                self.face_mask |= 1 << FACES.index(tag.face)
            self._change("MAG_FIT" if tag.stage == "MAG_ROTATE" else "NEED_SAMPLES" if tag.stage == "SUPPLEMENT" else "FACE_WAIT")
            return self._response("OK", "DO", **common, state=self.state, face_mask=self.face_mask, apply=0)
        if self.explicit_windows and (action in ("MAG_START", "MAG_STOP", "FACE_STOP") or action.startswith("FACE_")):
            return self._error("DO", "NOT_READY", "EXPLICIT_WINDOW_REQUIRED", **common)
        if action == "MAG_START" and self.state == "IDLE":
            tag = WindowTag("MAG_ROTATE", "NA", "mag-1", "mag-motion", "TRAIN")
            result = self.collector.Start(tag, self.now)
            self._change("MAG_COLLECT" if result == CaptureResult.Accepted else "FAILED", self.collector.reason)
        elif action == "MAG_STOP" and self.state == "MAG_COLLECT":
            result = self.collector.Stop(self.now)
            self._change("MAG_FIT" if result == CaptureResult.Complete else "FAILED", self.collector.reason)
        elif action == "SIX_START" and self.state == "MAG_FIT":
            self._change("FACE_WAIT")
        elif action.startswith("FACE_") and action != "FACE_STOP" and self.state in ("FACE_WAIT", "NEED_SAMPLES"):
            if self.attempt == 65535: return self._error("DO", "NOT_READY", "ATTEMPT_EXHAUSTED", **common)
            self.attempt += 1; face = action[5:]
            tag = WindowTag("SUPPLEMENT" if self.face_mask == 63 else "SIX_FACE", face,
                f"w-{self.attempt}", f"p-{self.attempt}", "TRAIN", self.attempt)
            result = self.collector.Start(tag, self.now)
            self._change("FACE_COLLECT" if result == CaptureResult.Accepted else "FAILED", self.collector.reason)
        elif action == "FACE_STOP" and self.state == "FACE_COLLECT":
            result = self.collector.Stop(self.now)
            if result == CaptureResult.Complete:
                from .prototype import FACES
                self.face_mask |= 1 << FACES.index(self.collector.tag.face)
            self._change(("SOLVE" if self.face_mask == 63 else "FACE_WAIT") if result == CaptureResult.Complete else "FAILED", self.collector.reason)
        else:
            return self._error("DO", "NOT_READY", "PHASE", **common)
        if self.state == "FAILED": return self._error("DO", "NOT_READY", self.reason, **common)
        return self._response("OK", "DO", **common, state=self.state, face_mask=self.face_mask, apply=0)

    def _put(self, sid, rid, value):
        if self.upload_spec is None:
            return self._error("PUT", "NOT_READY", "UPLOAD_REQUIRED", sid=sid, rid=rid)
        offset, data = value.split(":"); offset, data = int(offset), bytes.fromhex(data)
        if offset+len(data) > len(self.upload):
            return self._error("PUT", "BAD_FORMAT", "OBJECT_RANGE", sid=sid, rid=rid)
        if any(self.written[offset+i] and self.upload[offset+i] != x for i, x in enumerate(data)):
            return self._error("PUT", "CONFLICT", "OBJECT_CHANGED", sid=sid, rid=rid)
        staged = bytearray(self.upload); staged[offset:offset+len(data)] = data
        written = bytearray(self.written); written[offset:offset+len(data)] = bytes([1])*len(data)
        if all(written) and (hashlib.sha256(staged).hexdigest() != self.upload_spec.sha256 or f"{zlib.crc32(staged):08X}" != self.upload_spec.crc32):
            return self._error("PUT", "VERIFY_FAILED", "OBJECT_HASH", sid=sid, rid=rid)
        parsed = None
        if all(written) and self._formal_upload:
            try:
                parsed = Bundle_Decode(bytes(staged))
                math_session = InstallationSession(self.collector.StaticRecords(), self.convention)
                Bundle_VerifyContext(parsed, math_session, tuple(self.sources.values()), self.binding_digest,
                    self.base_generation, self.accel, self.mag, _digest(self.collector.ArchiveExport()), config_u32=self.config_u32)
                if parsed.session_id != self.sid or parsed.commit_rid != self.upload_origin_rid:
                    raise ValueError("transaction key changed")
                if parsed.R_GA != self.convention.R_GA: raise ValueError("gyro coordinate assumption changed")
            except ValueError:
                return self._error("PUT", "VERIFY_FAILED", "SSIC_DEPENDENCY_OR_STRUCTURE", sid=sid, rid=rid)
        self.upload[:], self.written[:] = staged, written
        self.candidate = None; self.sequence += 1; self.views.clear()
        if parsed is not None:
            self.staged_bundle = parsed; self._change("CANDIDATE_ONLY", "STRUCTURE_ONLY_NOT_PROVEN")
        return self._response("OK", "PUT", sid=sid, rid=rid, received=sum(written), complete=int(all(written)), apply=0)

    def _window(self, sid, rid, spec):
        stage, face, split, window, pose, attempt = spec.split(":")
        allowed = {"MAG_ROTATE": {"IDLE", "MAG_FIT"}, "SIX_FACE": {"FACE_WAIT"}, "SUPPLEMENT": {"NEED_SAMPLES"}}
        if self.state not in allowed[stage] or self._formal_upload:
            return self._error("WINDOW", "NOT_READY", "PHASE_OR_UPLOAD", sid=sid, rid=rid)
        tag = WindowTag(stage, face, window, pose, split, int(attempt))
        if self.collector.Start(tag, self.now) != CaptureResult.Accepted:
            return self._error("WINDOW", "NOT_READY", self.collector.reason, sid=sid, rid=rid)
        self.explicit_windows = True; self._discard_staging()
        self._change("MAG_COLLECT" if stage == "MAG_ROTATE" else "FACE_COLLECT")
        return self._response("OK", "WINDOW", sid=sid, rid=rid, window=window, split=split,
            stage=stage, face=face, attempt=attempt, state=self.state, apply=0)

    def _upload_start(self, sid, rid, spec):
        length, crc, sha = spec.split(":"); declaration = UploadSpec(int(length), sha, crc)
        if self.state not in ("SOLVE", "NEED_SAMPLES", "CANDIDATE_ONLY"):
            return self._error("UPLOAD", "NOT_READY", "CAPTURE_NOT_FROZEN", sid=sid, rid=rid)
        if self._formal_upload:
            if declaration != self.upload_spec:
                return self._error("UPLOAD", "CONFLICT", "CANCEL_UPLOAD_FIRST", sid=sid, rid=rid)
        else:
            self._discard_staging(); self.upload_previous_state = self.state
            self.upload_spec, self._formal_upload, self.upload_origin_rid = declaration, True, rid
            self.upload, self.written = bytearray(declaration.length), bytearray(declaration.length)
            self._change(self.state, "UPLOAD_PENDING")
        return self._response("OK", "UPLOAD", sid=sid, rid=rid, length=declaration.length,
            received=sum(self.written), apply=0)

    def _status(self, args):
        context, spec = args; role, cursor = spec.split(":")
        if context != self.sid and context != self.binding:
            return self._error("STATUS", "SESSION_UNKNOWN", "CONTEXT")
        if role in ("ACTIVE", "SAVED"):
            return self._error("STATUS", "NOT_AVAILABLE", "NO_PERSISTENCE_MODEL")
        if cursor != "0": return self._error("STATUS", "STALE", "CURSOR")
        if role == "STATE":
            return self._response("OK", "STATUS", sid=self.sid, role=role, state=self.state,
                reason=self.reason, seq=self.sequence, face_mask=self.face_mask,
                pairs=0 if self.collector is None else len(self.collector.pairs), apply=0, saved=0,
                imu_ready=0, extrinsic_validated=0,
                cleanup_complete=int(self.gate.owner != self.sid), connected=int(self.connected))
        if self.candidate is None and self.staged_bundle is None: return self._error("STATUS", "NOT_READY", "NO_CANDIDATE")
        if self.staged_bundle is not None:
            payload = bytes(self.upload)
            token = "S-"+_digest((context, role, self.sequence, hashlib.sha256(payload).hexdigest()))[:30]
            self.views[token] = self.sequence, self.now+5000000, context, role, payload
            return self._response("OK", "STATUS", sid=self.sid, role=role, seq=self.sequence,
                snapshot=token, length=len(payload), sha256=hashlib.sha256(payload).hexdigest(), format="SSIC_DRAFT", apply=0)
        candidate = asdict(self.candidate)
        candidate["candidates"] = candidate["candidates"][:1]
        payload = json.dumps({"report": candidate, "accel": asdict(self.accel), "mag": asdict(self.mag),
            "context": self.candidate_context,
            "sources": {k: asdict(v) for k, v in self.sources.items()}, "kind": "OFFLINE_DIAGNOSTIC_ONLY"},
            sort_keys=True, separators=(",", ":")).encode("ascii")
        if len(payload) > 8192: return self._error("STATUS", "BUFFER_FULL", "SNAPSHOT")
        token = "S-"+_digest((context, role, self.sequence, hashlib.sha256(payload).hexdigest()))[:30]
        self.views[token] = self.sequence, self.now+5000000, context, role, payload
        return self._response("OK", "STATUS", sid=self.sid, role=role, seq=self.sequence,
            snapshot=token, length=len(payload), sha256=hashlib.sha256(payload).hexdigest(), apply=0)

    def _read(self, args):
        context, token, offset = args; view = self.views.get(token)
        if (not view or view[0] != self.sequence or self.now >= view[1] or view[2] != context):
            return self._error("READ", "STALE", "SNAPSHOT")
        payload = view[4]; offset = int(offset)
        if offset >= len(payload) or offset % CHUNK_BYTES: return self._error("READ", "BAD_FORMAT", "OFFSET")
        chunk = payload[offset:offset+CHUNK_BYTES]
        return self._response("OK", "READ", role=view[3], seq=view[0], snapshot=token, offset=offset,
            length=len(chunk), crc32=f"{zlib.crc32(chunk):08X}", sha256=hashlib.sha256(payload).hexdigest(), data=chunk.hex().upper())
