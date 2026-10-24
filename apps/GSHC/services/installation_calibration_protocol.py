"""Experimental INSTALL codec within existing maintenance 0.1 line budgets.

Not imported by existing decoders. No production protocol/version is changed.
"""
from dataclasses import dataclass
from enum import Enum
import re
import struct
import zlib

from services.installation_calibration_data import CapturedPair, CapturePolicy, SourceSample, WindowTag
from services.installation_calibration_fit import FACES, _uint
from services.installation_calibration_contract import InstallationContract_Load

_CONTRACT = InstallationContract_Load().Read()
REQUEST_BYTES, RESPONSE_BYTES, CHUNK_BYTES = (_CONTRACT["limits"][key] for key in ("request_bytes","response_bytes","chunk_bytes"))
ACTIONS = {"MAG_START", "MAG_STOP", "SIX_START", "FACE_STOP", "VALIDATE", "APPLY", "SAVE", "CANCEL"}
ACTIONS |= {"FACE_"+x for x in FACES}
ACTIONS |= {"WINDOW_STOP", "WINDOW_CANCEL", "CAPTURE_DONE", "UPLOAD_CANCEL"}
ROLES = {"STATE", "CANDIDATE", "ACTIVE", "SAVED"}


class ProtocolResult(str, Enum):
    BadFormat = "BAD_FORMAT"
    TooLong = "LINE_TOO_LONG"
    Conflict = "CONFLICT"
    Stale = "STALE"
    Timeout = "TIMEOUT"
    Overflow = "BUFFER_FULL"
    WrongContext = "WRONG_CONTEXT"


class ProtocolError(ValueError):
    def __init__(self, code, reason):
        self.code, self.reason = code, reason
        super().__init__(str(code)+":"+reason)


def _decimal(value, bits=32, nonzero=False):
    if not re.fullmatch(r"0|[1-9][0-9]{0,19}", value):
        raise ProtocolError(ProtocolResult.BadFormat, "DECIMAL")
    result = int(value)
    try:
        _uint(result, bits, nonzero)
    except ValueError as exc:
        raise ProtocolError(ProtocolResult.BadFormat, "INTEGER_RANGE") from exc
    return result


def Sid_Check(value):
    if not re.fullmatch(r"[0-9a-f]{32}", value) or int(value, 16) == 0:
        raise ProtocolError(ProtocolResult.BadFormat, "SID")
    return value


def Context_Check(value):
    if re.fullmatch(r"B-[0-9a-f]{30}", value):
        return value
    return Sid_Check(value)


@dataclass(frozen=True)
class Request:
    operation: str
    arguments: tuple = ()


def Request_Decode(body,*,allow_draft=False):
    if type(body) is not bytes or len(body) > REQUEST_BYTES:
        raise ProtocolError(ProtocolResult.TooLong, "REQUEST")
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProtocolError(ProtocolResult.BadFormat, "ASCII") from exc
    if any(ord(c) < 32 and c != "\t" for c in text) or any(ord(c) == 127 for c in text):
        raise ProtocolError(ProtocolResult.BadFormat, "CONTROL_BYTE")
    tokens = text.split()
    if not 2 <= len(tokens) <= 5 or tokens[0] != "INSTALL":
        raise ProtocolError(ProtocolResult.BadFormat, "INSTALL_TOKENS")
    op, args = tokens[1], tokens[2:]
    counts = {"CAPS": 0, "INFO": 2, "BEGIN": 3, "DO": 3, "PUT": 3, "WINDOW": 3, "UPLOAD": 3,
              "POLL": 2, "STATUS": 2, "READ": 3, "FACE": 3}
    if op not in counts or len(args) != counts[op]:
        raise ProtocolError(ProtocolResult.BadFormat, "OPERATION_ARGUMENTS")
    if not allow_draft and (op not in ("CAPS","INFO","BEGIN","FACE","POLL","STATUS","DO")
            or (op=="DO" and args[-1]!="CANCEL") or (op=="STATUS" and args[-1]!="STATE:0")):
        raise ProtocolError(ProtocolResult.BadFormat,"UNADOPTED_DRAFT_COMMAND")
    if op == "INFO":
        endpoints = args[0].split(":")
        if len(endpoints) != 2:
            raise ProtocolError(ProtocolResult.BadFormat, "ENDPOINTS")
        for value in endpoints: _decimal(value, 8)
        _decimal(args[1], 16)
    elif op in ("BEGIN", "DO", "PUT", "POLL", "WINDOW", "UPLOAD", "FACE"):
        Sid_Check(args[0]); _decimal(args[1], nonzero=True)
        if op == "BEGIN" and not re.fullmatch(r"B-[0-9a-f]{30}", args[2]):
            raise ProtocolError(ProtocolResult.BadFormat, "BINDING")
        if op == "DO" and args[2] not in ACTIONS:
            raise ProtocolError(ProtocolResult.BadFormat, "ACTION")
        if op == "PUT":
            values = args[2].split(":")
            if (len(values) != 2 or not re.fullmatch(r"(?:[0-9A-F]{2}){1,48}", values[1])):
                raise ProtocolError(ProtocolResult.BadFormat, "PUT_CHUNK")
            _decimal(values[0])
        if op == "WINDOW":
            values = args[2].split(":")
            if len(values) != 6: raise ProtocolError(ProtocolResult.BadFormat, "WINDOW_FIELDS")
            try:
                WindowTag(values[0], values[1], values[3], values[4], values[2], _decimal(values[5], 16, True))
            except ValueError as exc:
                raise ProtocolError(ProtocolResult.BadFormat, "WINDOW_FIELDS") from exc
        if op == "UPLOAD":
            values = args[2].split(":")
            if (len(values) != 3 or not 1 <= _decimal(values[0]) <= 5140
                    or not re.fullmatch(r"[0-9A-F]{8}", values[1]) or not re.fullmatch(r"[0-9a-f]{64}", values[2])):
                raise ProtocolError(ProtocolResult.BadFormat, "UPLOAD_DECLARATION")
        if op == "FACE":
            values=args[2].split(":")
            if (len(values)!=4 or values[0] not in _CONTRACT["face_plan"]["modes"]
                    or values[1] not in _CONTRACT["face_plan"]["stages"] or values[2] not in FACES):
                raise ProtocolError(ProtocolResult.BadFormat,"AUTO_FACE_FIELDS")
            _decimal(values[3],16,True)
    elif op == "STATUS":
        Context_Check(args[0]); values = args[1].split(":")
        if len(values) != 2 or values[0] not in ROLES:
            raise ProtocolError(ProtocolResult.BadFormat, "STATUS_ROLE")
        _decimal(values[1], 16)
        if args[0].startswith("B-") and values[0] not in ("ACTIVE", "SAVED"):
            raise ProtocolError(ProtocolResult.BadFormat, "READ_ONLY_BINDING_ROLE")
    elif op == "READ":
        Context_Check(args[0]); _decimal(args[2])
        if not re.fullmatch(r"S-[0-9a-f]{30}", args[1]):
            raise ProtocolError(ProtocolResult.BadFormat, "SNAPSHOT_TOKEN")
    return Request(op, tuple(args))


def Request_Encode(request,*,allow_draft=False):
    body = " ".join(("INSTALL", request.operation, *request.arguments)).encode("ascii")
    Request_Decode(body,allow_draft=allow_draft)
    return body+b"\r\n"


@dataclass(frozen=True)
class Response:
    status: str
    operation: str
    fields: tuple

    def Field(self, name):
        return dict(self.fields).get(name)


def Response_Encode(response):
    if response.status not in ("OK", "ERR", "PENDING") or response.operation not in ("CAPS", "INFO", "BEGIN", "DO", "PUT", "POLL", "STATUS", "READ", "WINDOW", "UPLOAD", "FACE"):
        raise ProtocolError(ProtocolResult.BadFormat, "RESPONSE_OPERATION")
    fields, seen = [], set()
    for key, value in response.fields:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", key) or key in seen:
            raise ProtocolError(ProtocolResult.BadFormat, "FIELD_NAME")
        value = str(value)
        if not re.fullmatch(r"[A-Za-z0-9_.:+-]{1,400}", value):
            raise ProtocolError(ProtocolResult.BadFormat, "FIELD_VALUE")
        seen.add(key); fields.append(key+"="+value)
    body = " ".join((response.status, "INSTALL", response.operation, *fields)).encode("ascii")
    if len(body) > RESPONSE_BYTES:
        raise ProtocolError(ProtocolResult.TooLong, "RESPONSE")
    return body+b"\r\n"


def Response_Decode(body, operation=None, sid=None, rid=None):
    if type(body) is not bytes or len(body) > RESPONSE_BYTES:
        raise ProtocolError(ProtocolResult.TooLong, "RESPONSE")
    try:
        tokens = body.decode("ascii").split()
        if len(tokens) < 3 or tokens[1] != "INSTALL": raise ValueError()
        fields = []
        for token in tokens[3:]:
            key, value = token.split("=", 1); fields.append((key, value))
        result = Response(tokens[0], tokens[2], tuple(fields))
        # Canonical reconstruction also rejects duplicate keys and control values.
        if Response_Encode(result)[:-2] != body: raise ValueError()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError(ProtocolResult.BadFormat, "COMPLETE_RESPONSE") from exc
    if ((operation is not None and result.operation != operation)
            or (sid is not None and result.Field("sid") != sid)
            or (rid is not None and result.Field("rid") != str(rid))):
        raise ProtocolError(ProtocolResult.WrongContext, "RESPONSE_MATCH")
    if result.status == "ERR" and (result.Field("code") is None or result.Field("reason") is None):
        raise ProtocolError(ProtocolResult.BadFormat, "ERROR_FIELDS")
    return result


class LineFramer:
    def __init__(self, limit=RESPONSE_BYTES):
        if limit not in (REQUEST_BYTES, RESPONSE_BYTES): raise ValueError("line budget")
        self.limit, self.partial, self.discard = limit, bytearray(), False

    def Discontinuity(self):
        self.partial.clear(); self.discard = True

    def Feed(self, chunk):
        if type(chunk) is not bytes or len(chunk) > 256:
            self.Discontinuity()
            raise ProtocolError(ProtocolResult.Overflow, "CHUNK_BUDGET")
        lines = []
        for byte in chunk:
            if byte in (10, 13):
                if self.partial and not self.discard: lines.append(bytes(self.partial))
                self.partial.clear(); self.discard = False
            elif not self.discard:
                if len(self.partial) >= self.limit:
                    self.partial.clear(); self.discard = True
                    lines.append(ProtocolError(ProtocolResult.TooLong, "FRAMED_LINE"))
                else: self.partial.append(byte)
        return tuple(lines)


_PART = struct.Struct(_CONTRACT["sample"]["payload_struct_le"])
_STAGES = tuple(_CONTRACT["sample"]["stage_codes"])
_WIRE_FACES = tuple(_CONTRACT["sample"]["face_codes"])


def SamplePart_Encode(pair, role, context):
    if not re.fullmatch(r"B-[0-9a-f]{30}", context): raise ValueError("binding context")
    sample = pair.imu if role == "IMU" else pair.mag if role == "MAG" else None
    if sample is None: raise ValueError("source role")
    flags = sum(1 << i for i, name in enumerate(("GAP", "SATURATED", "INVALID")) if name in sample.flags)
    flags |= (8 if sample.temperature_c is not None else 0) | (16 if sample.raw_counts is not None else 0)
    values = (*sample.values, *((0.,)*3 if role == "MAG" else ()))
    counts = (*sample.raw_counts, *((0,)*3 if role == "MAG" else ())) if sample.raw_counts is not None else (0,)*6
    body = _PART.pack(sample.sequence, sample.descriptor.epoch, sample.sample_us, sample.receive_us,
        0, sample.uncertainty_us, flags, *values, sample.temperature_c or 0., *counts,
        pair.tag.window.encode(), pair.tag.pose.encode(), _STAGES.index(pair.tag.stage), _WIRE_FACES.index(pair.tag.face),
        ("TRAIN", "HOLDOUT").index(pair.tag.split), pair.tag.attempt)
    line = (f"EVENT INSTALL {role} sid={pair.session} pair={pair.pair_id} ctx={context} "
            f"data={body.hex().upper()} crc32={zlib.crc32(body):08X}").encode()
    if len(line) > RESPONSE_BYTES: raise ProtocolError(ProtocolResult.TooLong, "SAMPLE_PART")
    return line+b"\r\n"


def SamplePart_Decode(line, sid, context, descriptors):
    if type(line) is not bytes or len(line) > RESPONSE_BYTES:
        raise ProtocolError(ProtocolResult.TooLong, "SAMPLE_PART")
    try:
        tokens = line.decode("ascii").split()
        if len(tokens) != 8 or tokens[:2] != ["EVENT", "INSTALL"] or tokens[2] not in ("IMU", "MAG"):
            raise ValueError()
        fields = dict(x.split("=", 1) for x in tokens[3:])
        if set(fields) != {"sid", "pair", "ctx", "data", "crc32"}: raise ValueError()
        if fields["sid"] != sid or fields["ctx"] != context:
            raise ProtocolError(ProtocolResult.WrongContext, "SAMPLE_BINDING")
        pair_id = _decimal(fields["pair"], nonzero=True)
        if not re.fullmatch(r"[0-9A-F]{"+str(2*_PART.size)+"}", fields["data"]): raise ValueError()
        payload = bytes.fromhex(fields["data"])
        if fields["crc32"] != f"{zlib.crc32(payload):08X}": raise ValueError()
        v = _PART.unpack(payload); role = tokens[2]; d = descriptors[role]
        if v[1] != d.epoch or v[6] & ~31 or v[4] != 0: raise ValueError()
        count = 6 if role == "IMU" else 3
        if role == "MAG" and (any(v[10:13]) or any(v[17:20])): raise ValueError()
        flags = tuple(name for i, name in enumerate(("GAP", "SATURATED", "INVALID")) if v[6] & (1 << i))
        if (not v[6] & 8 and v[13] != 0) or (not v[6] & 16 and any(v[14:20])): raise ValueError()
        tag = WindowTag(_STAGES[v[22]], _WIRE_FACES[v[23]], v[20].rstrip(b"\0").decode(),
                        v[21].rstrip(b"\0").decode(), ("TRAIN", "HOLDOUT")[v[24]], v[25])
        sample = SourceSample(d, v[0], v[2], v[3], v[4], v[5], v[7:7+count], flags,
            v[13] if v[6] & 8 else None, v[14:14+count] if v[6] & 16 else None)
        return pair_id, role, tag, sample
    except (ValueError, IndexError, KeyError, struct.error, UnicodeDecodeError) as exc:
        if isinstance(exc, ProtocolError): raise
        raise ProtocolError(ProtocolResult.BadFormat, "SAMPLE_PAYLOAD_CRC") from exc


class PairAssembler:
    def __init__(self, sid, context, boot, descriptors, capacity=4, timeout_us=100000,
                 quality_policy=CapturePolicy()):
        Sid_Check(sid); Context_Check(context)
        if not 1 <= capacity <= 16 or not 1 <= timeout_us <= 1000000: raise ValueError("assembly budget")
        self.sid, self.context, self.boot, self.descriptors = sid, context, boot, dict(descriptors)
        self.capacity, self.timeout, self.pending, self.highwater, self.now = capacity, timeout_us, {}, 0, 0
        self.last_complete, self.requires_resample = None, False
        self.quality_policy = quality_policy

    def Poll(self, now_us):
        _uint(now_us)
        if now_us < self.now: raise ProtocolError(ProtocolResult.Stale, "ASSEMBLER_CLOCK")
        self.now = now_us
        expired = tuple(key for key, value in self.pending.items() if now_us-value[0] >= self.timeout)
        for key in expired: del self.pending[key]
        if expired:
            self.requires_resample = True
            raise ProtocolError(ProtocolResult.Timeout, "MISSING_SAMPLE_PART")

    def Feed(self, line, now_us):
        if self.requires_resample:
            raise ProtocolError(ProtocolResult.Stale, "WINDOW_FAILED_REACQUIRE")
        self.Poll(now_us)
        pair_id, role, tag, sample = SamplePart_Decode(line, self.sid, self.context, self.descriptors)
        if pair_id <= self.highwater:
            if self.last_complete and pair_id == self.highwater and sample == getattr(self.last_complete, role.lower()) and tag == self.last_complete.tag:
                return None
            raise ProtocolError(ProtocolResult.Stale, "SAMPLE_PAIR_REPLAY")
        if pair_id not in self.pending:
            if len(self.pending) >= self.capacity:
                self.requires_resample = True
                raise ProtocolError(ProtocolResult.Overflow, "ASSEMBLY_SLOTS")
            self.pending[pair_id] = (now_us, {})
        parts = self.pending[pair_id][1]
        if role in parts and parts[role] != (tag, sample):
            self.requires_resample = True
            raise ProtocolError(ProtocolResult.Conflict, "SAMPLE_PART_CHANGED")
        parts[role] = (tag, sample)
        if len(parts) != 2: return None
        if parts["IMU"][0] != parts["MAG"][0]:
            self.requires_resample = True
            raise ProtocolError(ProtocolResult.Conflict, "PAIR_TAG_CHANGED")
        if pair_id != self.highwater+1:
            self.requires_resample = True
            raise ProtocolError(ProtocolResult.Stale, "PAIR_SEQUENCE_GAP")
        try:
            result = CapturedPair(self.sid, self.boot, pair_id, tag, parts["IMU"][1], parts["MAG"][1])
            result.QualityCheck(self.quality_policy)
            if self.last_complete:
                for source in ("imu", "mag"):
                    current, previous = getattr(result, source), getattr(self.last_complete, source)
                    if (current.sample_us <= previous.sample_us
                            or (tag.window == self.last_complete.tag.window
                                and (current.sequence-previous.sequence) % 2**32 != current.descriptor.sequence_stride)):
                        raise ValueError("source sequence/time gap")
        except ValueError as exc:
            self.requires_resample = True
            raise ProtocolError(ProtocolResult.BadFormat, "PAIR_SOURCE_QUALITY_OR_SEQUENCE") from exc
        del self.pending[pair_id]; self.highwater = pair_id; self.last_complete = result
        return result
