"""Bounded INFO/time qualification for the optional, read-only capture flow.

Declarations bind a snapshot; they are not independent hardware verification.
No port, GUI, target memory allocation, parameter apply or storage write occurs.
"""
from dataclasses import dataclass
from enum import Enum
import json
import re


class CaptureProofResult(str, Enum):
    Qualified = "DECLARED_QUALIFIED"
    Unproven = "NOT_PROVEN"
    Invalid = "INVALID"


def _uint(value, bits=32, nonzero=False):
    if type(value) is not int or not int(nonzero) <= value < 2**bits:
        raise ValueError("CAPTURE_UNSIGNED_RANGE")
    return value


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("CAPTURE_EXACT_FIELDS")


def _token(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value) is None:
        raise ValueError("CAPTURE_ASCII_TOKEN")


def InfoSnapshot_Decode(payload, rules):
    """Bound bytes/depth/nodes, reject duplicate keys and require canonical bytes."""
    if type(payload) is not bytes or not 1 <= len(payload) <= rules["maximum_bytes"]:
        raise ValueError("INFO_BYTE_BUDGET")
    depth = 0
    quoted = escaped = False
    for byte in payload:
        if byte > 127:
            raise ValueError("INFO_ASCII_JSON")
        if quoted:
            if escaped: escaped = False
            elif byte == 92: escaped = True
            elif byte == 34: quoted = False
        elif byte == 34: quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > rules["maximum_depth"]: raise ValueError("INFO_DEPTH_BUDGET")
        elif byte in (93, 125):
            depth -= 1
            if depth < 0: raise ValueError("INFO_JSON_DEPTH")
    if quoted or depth:
        raise ValueError("INFO_JSON_INCOMPLETE")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError("INFO_DUPLICATE_KEY")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("INFO_NONFINITE_CONSTANT")

    data = json.loads(payload, object_pairs_hook=unique, parse_constant=constant)
    optional=rules.get('optional_binding_fields',[])
    if type(data) is not dict:raise ValueError('CAPTURE_EXACT_FIELDS')
    present=tuple(key for key in optional if key in data)
    _exact(data, (*rules["canonical_binding_fields"], *present, "binding_digest"))
    if 'runtime_imu' in data:
        item=data['runtime_imu'];_exact(item,('bias_radps','scale','generation','mode','ready'))
        if (type(item['ready']) is not bool or type(item['mode']) is not int or not 0<=item['mode']<=2
                or type(item['generation']) is not int or not 0<=item['generation']<2**32):raise ValueError('RUNTIME_IMU_STATE')
        for key in ('bias_radps','scale'):
            vector=item[key]
            if item['ready']:
                if type(vector) is not list or len(vector)!=3 or any(type(v) not in (float,int) for v in vector):raise ValueError('RUNTIME_IMU_VECTOR')
            elif vector is not None:raise ValueError('UNKNOWN_RUNTIME_IMU_MUST_BE_NULL')
    pending, nodes = [data], 0
    while pending:
        current = pending.pop(); nodes += 1
        if nodes > rules["maximum_nodes"]: raise ValueError("INFO_NODE_BUDGET")
        if type(current) is dict:
            pending.extend(current.keys()); pending.extend(current.values())
        elif type(current) is list: pending.extend(current)
        elif type(current) is str and (len(current) > rules["maximum_string"] or not current.isascii()):
            raise ValueError("INFO_STRING_BUDGET")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if canonical != payload:
        raise ValueError("INFO_NONCANONICAL_JSON")
    return data


@dataclass(frozen=True)
class CaptureQualification:
    result: CaptureProofResult
    reason: str
    source_bounds: tuple

    def Sample_Check(self, sample):
        bound = dict(self.source_bounds).get(sample.descriptor.role)
        if (self.result != CaptureProofResult.Qualified or bound is None
                or type(sample.uncertainty_us) is not int or not bound <= sample.uncertainty_us < 2**32-1):
            return CaptureProofResult.Unproven
        return CaptureProofResult.Qualified


def CaptureProvenance_Audit(data, sources, policy, *, simulated):
    """Validate the exact declaration and retain UNKNOWN as a closed gate."""
    _exact(data, ("sources", "selection", "native_health_timeout_us", "selected_interval_max_us"))
    _exact(data["sources"], ("IMU", "MAG"))
    if type(sources) not in (tuple, list) or len(sources) != 2 or tuple(source.role for source in sources) != ("IMU", "MAG"):
        raise ValueError("EXACT_CAPTURE_SOURCE_PAIR")
    if type(simulated) is not bool: raise ValueError("CAPTURE_SIMULATION_FLAG")
    _uint(data["native_health_timeout_us"], nonzero=True)
    _uint(data["selected_interval_max_us"], nonzero=True)
    if data["native_health_timeout_us"] != policy.source_timeout_us:
        raise ValueError("NATIVE_HEALTH_TIMEOUT_CONTRACT")
    selection = data["selection"]
    _exact(selection, ("kind", "phase", "nominal_output_millihz", "native_rate_unchanged", "value_dependent"))
    _exact(selection["phase"], ("IMU", "MAG"))
    if (selection["kind"] != "FIXED_NATIVE_SEQUENCE_STRIDE" or selection["native_rate_unchanged"] is not True
            or selection["value_dependent"] is not False):
        raise ValueError("UNBIASED_FIXED_SELECTION_REQUIRED")
    _uint(selection["nominal_output_millihz"], nonzero=True)
    if data["selected_interval_max_us"] < (1000000000 + selection["nominal_output_millihz"] - 1) // selection["nominal_output_millihz"]:
        raise ValueError("SELECTED_INTERVAL_CONTRADICTS_RATE")
    reasons, bounds = [], []
    for source in sources:
        _uint(selection["phase"][source.role], 16)
        if selection["phase"][source.role] >= source.sequence_stride:
            raise ValueError("SELECTION_PHASE_OUTSIDE_STRIDE")
        item = data["sources"][source.role]
        _exact(item, ("identity_scope", "hardware_identity", "hardware_identity_provenance", "sample_time_basis",
                      "sample_time_provenance", "measurement_uncertainty_bound_us", "epoch_provenance", "native_sequence_provenance"))
        for name in ("hardware_identity_provenance", "sample_time_provenance", "epoch_provenance", "native_sequence_provenance"):
            _token(item[name])
        if item["identity_scope"] not in ("DECLARED_ENDPOINT", "CHIP_UNIQUE", "SYNTHETIC_ENDPOINT"):
            raise ValueError("IDENTITY_SCOPE")
        uid = item["hardware_identity"]
        if uid is not None: _token(uid)
        if item["identity_scope"] == "CHIP_UNIQUE" and (uid is None or item["hardware_identity_provenance"] == "UNKNOWN"):
            raise ValueError("UNPROVEN_UNIQUE_SENSOR_IDENTITY")
        if uid is None and item["hardware_identity_provenance"] != "UNKNOWN":
            raise ValueError("ABSENT_SENSOR_IDENTITY_PROVENANCE")
        if item["identity_scope"] == "SYNTHETIC_ENDPOINT" and not simulated:
            reasons.append("SYNTHETIC_IDENTITY_NOT_LIVE")
        basis = item["sample_time_basis"]
        if basis not in ("SENSOR_MEASUREMENT", "TARGET_RECEIVE_DECODE_PROXY", "SYNTHETIC_MEASUREMENT", "UNKNOWN"):
            raise ValueError("SAMPLE_TIME_BASIS")
        bound = item["measurement_uncertainty_bound_us"]
        if bound is not None: _uint(bound)
        if basis in ("UNKNOWN", "TARGET_RECEIVE_DECODE_PROXY"):
            reasons.append("MEASUREMENT_TIME_UNPROVEN")
        if basis == "SYNTHETIC_MEASUREMENT" and not simulated:
            reasons.append("SYNTHETIC_TIME_NOT_LIVE")
        if (bound is None or bound == 2**32-1 or item["sample_time_provenance"] == "UNKNOWN"
                or item["epoch_provenance"] == "UNKNOWN" or item["native_sequence_provenance"] == "UNKNOWN"):
            reasons.append("TIME_EPOCH_OR_NATIVE_CONTINUITY_UNPROVEN")
        if bound is not None and bound > policy.max_uncertainty_us:
            reasons.append("SOURCE_TIME_BOUND_EXCEEDS_POLICY")
        bounds.append((source.role, bound))
    if all(type(bound) is int for _, bound in bounds) and sum(bound for _, bound in bounds) > min(policy.max_uncertainty_us, policy.max_skew_us):
        reasons.append("PAIR_TIME_BOUND_EXCEEDS_POLICY")
    return CaptureQualification(CaptureProofResult.Unproven if reasons else CaptureProofResult.Qualified,
                                ";".join(dict.fromkeys(reasons)) or "DECLARED_ONLY_NOT_HARDWARE_VERIFIED", tuple(bounds))
