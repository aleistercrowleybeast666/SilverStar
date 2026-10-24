"""Offline candidate-only AM calibration experiment; no production imports or I/O.

Independent implementation of a.T R m = s. Multistart is NOT a global solver.
All thresholds are provisional synthetic-test policy, not hardware calibration.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Callable

import numpy as np


class CandidateResult(str, Enum):
    Candidate = "CANDIDATE_ONLY"
    NeedSamples = "NEED_SAMPLES"
    Rejected = "REJECTED"
    Cancelled = "CANCELLED"
    NumericalFailure = "NUMERICAL_FAILURE"


class IntrinsicFitResult(str, Enum):
    Candidate = "CANDIDATE_ONLY"
    Rejected = "REJECTED"


FACES = ("XP", "XN", "YP", "YN", "ZP", "ZN")
FACE_AXES = dict(zip(FACES, (np.eye(3)[0], -np.eye(3)[0], np.eye(3)[1],
                            -np.eye(3)[1], np.eye(3)[2], -np.eye(3)[2])))
MAX_RECORDS = 4096
IDENTITY = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def _number(value):
    if isinstance(value, (bool, str, complex)) or np.ndim(value) != 0:
        raise ValueError("finite real scalar required")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("finite real scalar required")
    return value


def _uint(value, bits=64, nonzero=False):
    if type(value) is not int or not int(nonzero) <= value < 2 ** bits:
        raise ValueError("unsigned integer range")
    return value


def _vec(value):
    if len(value) != 3:
        raise ValueError("three-vector required")
    return tuple(_number(x) for x in value)


def _matrix(value, rotation=False, spd=False):
    if len(value) != 3:
        raise ValueError("3x3 matrix required")
    result = tuple(_vec(row) for row in value)
    a = np.array(result)
    if rotation and (not np.allclose(a.T @ a, np.eye(3), atol=1e-9, rtol=0)
                     or abs(np.linalg.det(a)-1) > 1e-9):
        raise ValueError("proper rotation required; no silent projection")
    if spd and (not np.allclose(a, a.T, atol=1e-10, rtol=0)
                or np.linalg.eigvalsh(a)[0] <= 0 or np.linalg.cond(a) > 100):
        raise ValueError("fixed SPD intrinsic gauge required")
    return result


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class SensorIdentity:
    board: str
    physical: int
    descriptor: int
    instance: int
    driver: str
    model: str
    configuration: str
    raw_frame: str

    def __post_init__(self):
        for name in ("board", "driver", "model", "configuration", "raw_frame"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError("explicit sensor identity required")
        _uint(self.physical, 16, True)
        _uint(self.descriptor, 16, True)
        _uint(self.instance, 8)


@dataclass(frozen=True)
class Intrinsic:
    identity: SensorIdentity
    generation: int
    calibration_id: str
    bias: tuple
    matrix: tuple
    unit: str
    output_frame: str
    gauge: str = "SPD_COLUMN"

    def __post_init__(self):
        _uint(self.generation, 32, True)
        if (not isinstance(self.identity, SensorIdentity)
                or not all(isinstance(x, str) and x for x in (self.calibration_id, self.output_frame))
                or self.gauge != "SPD_COLUMN"):
            raise ValueError("intrinsic identity/frame/gauge missing")
        if self.unit not in ("m/s2", "uT"):
            raise ValueError("unsupported intrinsic unit")
        object.__setattr__(self, "bias", _vec(self.bias))
        object.__setattr__(self, "matrix", _matrix(self.matrix, spd=True))

    def Correct(self, vector):
        return np.array(self.matrix) @ (np.asarray(vector)-self.bias)

    def Digest(self):
        return _digest(asdict(self))


@dataclass(frozen=True)
class Convention:
    accel_frame: str = "A"
    mag_frame: str = "M"
    gyro_frame: str = "G"
    handedness: str = "RIGHT"
    acceleration_kind: str = "STATIC_SPECIFIC_FORCE_UP"
    transformation: str = "COLUMN_M_TO_A"
    units: tuple = ("m/s2", "rad/s", "uT")
    evidence: str = "DECLARED_ONLY"
    R_GA: tuple | None = None
    gyro_axis_evidence: str = "UNPROVEN"

    def __post_init__(self):
        if not all(isinstance(x, str) and x for x in (self.accel_frame, self.mag_frame,
                self.gyro_frame, self.evidence, self.gyro_axis_evidence)):
            raise ValueError("coordinate identity and provenance required")
        if (self.handedness != "RIGHT" or self.acceleration_kind != "STATIC_SPECIFIC_FORCE_UP"
                or self.transformation != "COLUMN_M_TO_A"
                or tuple(self.units) != ("m/s2", "rad/s", "uT")):
            raise ValueError("unsupported coordinate/unit convention")
        object.__setattr__(self, "units", tuple(self.units))
        if self.R_GA is not None:
            object.__setattr__(self, "R_GA", _matrix(self.R_GA, rotation=True))
            if self.gyro_axis_evidence == "UNPROVEN":
                raise ValueError("R_GA needs declared provenance")


@dataclass(frozen=True)
class RawPair:
    session: str
    boot: str
    pair_id: int
    imu: SensorIdentity
    mag: SensorIdentity
    imu_epoch: int
    mag_epoch: int
    imu_seq: int
    mag_seq: int
    imu_us: int
    mag_us: int
    imu_receive_us: int
    mag_receive_us: int
    clock: str
    time_uncertainty_us: int
    sync_valid: bool
    quality_flags: tuple
    stage: str
    face: str
    window: str
    pose: str
    split: str
    accel: tuple
    gyro: tuple
    magnetic: tuple
    acquisition_intrinsic_ids: tuple
    acquisition_intrinsic_generations: tuple
    raw_kind: str = "PROVIDER_PHYSICAL_BEFORE_SOFTWARE_CORRECTION"

    def __post_init__(self):
        if not isinstance(self.imu, SensorIdentity) or not isinstance(self.mag, SensorIdentity):
            raise ValueError("immutable sensor identities required")
        for name in ("pair_id", "imu_us", "mag_us", "imu_receive_us", "mag_receive_us",
                     "time_uncertainty_us"):
            _uint(getattr(self, name))
        for name in ("imu_epoch", "mag_epoch", "imu_seq", "mag_seq"):
            _uint(getattr(self, name), 32)
        for name in ("session", "boot", "clock", "window", "pose"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError("record identity missing")
        if type(self.sync_valid) is not bool or self.split not in ("TRAIN", "HOLDOUT"):
            raise ValueError("split/synchronization declaration")
        if self.face not in FACES or self.stage not in ("SIX_FACE", "SUPPLEMENT", "DYNAMIC"):
            raise ValueError("phase/face required")
        if self.raw_kind != "PROVIDER_PHYSICAL_BEFORE_SOFTWARE_CORRECTION":
            raise ValueError("already-corrected input cannot be replayed as raw")
        for name in ("accel", "gyro", "magnetic"):
            object.__setattr__(self, name, _vec(getattr(self, name)))
        object.__setattr__(self, "quality_flags", tuple(self.quality_flags))
        object.__setattr__(self, "acquisition_intrinsic_ids", tuple(self.acquisition_intrinsic_ids))
        object.__setattr__(self, "acquisition_intrinsic_generations", tuple(self.acquisition_intrinsic_generations))
        if (len(self.acquisition_intrinsic_ids) != 2
                or not all(isinstance(x, str) and x for x in self.acquisition_intrinsic_ids)
                or not all(isinstance(x, str) and x for x in self.quality_flags)):
            raise ValueError("acquisition intrinsic provenance missing")
        if len(self.acquisition_intrinsic_generations) != 2:
            raise ValueError("two acquisition intrinsic generations required")
        for generation in self.acquisition_intrinsic_generations:
            _uint(generation, 32)


@dataclass(frozen=True)
class Policy:
    gravity: float = 9.80665
    reference_uT: float = 48.0
    max_skew_us: int = 2000
    max_time_uncertainty_us: int = 1000
    max_accel_error: float = 0.7
    max_accel_std: float = 0.10
    max_gyro_norm: float = 0.15
    max_field_error_fraction: float = 0.18
    max_field_std: float = 0.8
    max_face_angle_deg: float = 20.0
    residual_rms: float = 0.015
    residual_max: float = 0.045
    min_horizontal: float = 0.15
    min_singular: float = 0.035
    min_singular_ratio: float = 0.08
    ambiguity_delta: float = 0.002
    distinct_rotation_deg: float = 5.0
    starts: int = 72
    max_nfev: int = 160
    seed: int = 417
    threshold_status: str = "PROVISIONAL_SYNTHETIC_ONLY"

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key == "threshold_status":
                if value != "PROVISIONAL_SYNTHETIC_ONLY":
                    raise ValueError("hardware threshold qualification is unavailable")
            elif key in ("max_skew_us", "max_time_uncertainty_us", "starts", "max_nfev", "seed"):
                _uint(value, 32, key != "seed")
            elif _number(value) <= 0:
                raise ValueError("positive policy value required")
        if not 8 <= self.starts <= 256 or not 20 <= self.max_nfev <= 400:
            raise ValueError("bounded solver budget required")


@dataclass(frozen=True)
class Candidate:
    R_AM: tuple
    s: float
    train_rms: float
    train_max: float
    holdout_rms: float
    holdout_max: float
    singular_values: tuple
    weak_axis_A: tuple
    horizontal: float
    R_GM: tuple | None


@dataclass(frozen=True)
class CandidateReport:
    result: CandidateResult
    reasons: tuple
    gates: dict
    raw_digest: str
    context_digest: str
    candidates: tuple = ()
    supplemental_faces: tuple = ()
    windows: int = 0
    rejected_windows: tuple = ()
    search_attempts: int = 0
    search_converged: int = 0
    apply_allowed: bool = field(default=False, init=False)
    gyro_scale_status: str = "NOT_ESTIMATED_STATIC_SIX_FACE"
    dynamic_gyro_status: str = "NOT_IMPLEMENTED"


class _Cancelled(Exception):
    pass


def Geometry_Evaluate(a, m, R, weights=None):
    """Left rotation perturbation; eliminate s by weighted centering."""
    a, m, R = np.asarray(a), np.asarray(m), np.asarray(R)
    weights = np.ones(len(a)) if weights is None else np.asarray(weights)
    weights = weights/weights.sum()
    v = m @ R.T
    dots = np.einsum("ij,ij->i", a, v)
    s = float(weights @ dots)
    jacobian = np.cross(v, a)
    centered = jacobian - weights @ jacobian
    _, singular, vt = np.linalg.svd(np.sqrt(weights[:, None])*centered, full_matrices=False)
    return s, dots-s, singular, vt[-1], centered


def Rotation_DistanceDeg(a, b):
    from scipy.spatial.transform import Rotation
    return float(np.degrees(Rotation.from_matrix(np.array(a) @ np.array(b).T).magnitude()))


def Supplement_Suggest(weak_axis_A):
    """Choose a face normal perpendicular to the weakest local rotation axis.

    Scores rank potential excitation only. No claimed rotation angle or success.
    """
    weak = np.asarray(weak_axis_A)
    scores = [(name, float(1-(axis @ weak)**2)) for name, axis in FACE_AXES.items()]
    return tuple(sorted(scores, key=lambda row: (-row[1], FACES.index(row[0]))))


@dataclass(frozen=True)
class InstallationSession:
    records: tuple
    convention: Convention = Convention()
    raw_digest: str = field(init=False)

    def __post_init__(self):
        if not isinstance(self.convention, Convention):
            raise ValueError("immutable convention required")
        object.__setattr__(self, "records", tuple(self.records))
        if not self.records or len(self.records) > MAX_RECORDS or not all(
                isinstance(x, RawPair) for x in self.records):
            raise ValueError("bounded nonempty raw records required")
        object.__setattr__(self, "raw_digest", _digest([asdict(x) for x in self.records]))

    def ContextDigest(self, accel, mag, policy):
        return _digest({"raw": self.raw_digest, "accel": accel.Digest(),
                        "mag": mag.Digest(), "convention": asdict(self.convention),
                        "policy": asdict(policy)})

    def CandidateIsCurrent(self, report, accel, mag, policy):
        return report.context_digest == self.ContextDigest(accel, mag, policy)

    def _validate_metadata(self, policy):
        first = self.records[0]
        windows, seen, last = {}, set(), None
        for r in self.records:
            if (r.session, r.boot, r.imu, r.mag, r.imu_epoch, r.mag_epoch, r.clock) != (
                    first.session, first.boot, first.imu, first.mag, first.imu_epoch,
                    first.mag_epoch, first.clock):
                raise ValueError("SESSION_DEVICE_EPOCH_OR_CLOCK_CHANGED")
            if r.pair_id in seen:
                raise ValueError("DUPLICATE_PAIR")
            seen.add(r.pair_id)
            if last is not None and (r.imu_us <= last.imu_us or r.mag_us <= last.mag_us
                    or not 0 < (r.imu_seq-last.imu_seq) % 2**32 < 2**31
                    or not 0 < (r.mag_seq-last.mag_seq) % 2**32 < 2**31):
                raise ValueError("TIME_OR_SEQUENCE_DISCONTINUITY")
            if (not r.sync_valid or r.clock == "PC_RECEIVE_PROXY" or r.quality_flags
                    or abs(r.imu_us-r.mag_us) > policy.max_skew_us
                    or r.time_uncertainty_us > policy.max_time_uncertainty_us
                    or r.imu_receive_us < r.imu_us or r.mag_receive_us < r.mag_us):
                raise ValueError("UNQUALIFIED_SYNC_OR_QUALITY")
            if r.stage == "DYNAMIC":
                raise ValueError("DYNAMIC_GYRO_NOT_IMPLEMENTED")
            group = windows.setdefault(r.window, [])
            if group and (r.split, r.face, r.pose, r.stage) != (
                    group[0].split, group[0].face, group[0].pose, group[0].stage):
                raise ValueError("WINDOW_SPLIT_OR_POSE_CONFLICT")
            group.append(r)
            last = r
        return windows

    def _prepare(self, accel, mag, policy):
        first = self.records[0]
        if accel.identity != first.imu or mag.identity != first.mag:
            raise ValueError("WRONG_DEVICE_OR_CONFIG")
        if (accel.unit, mag.unit, accel.output_frame, mag.output_frame) != (
                "m/s2", "uT", self.convention.accel_frame, self.convention.mag_frame):
            raise ValueError("FRAME_OR_UNIT_MISMATCH")
        windows = self._validate_metadata(policy)
        accepted, rejected = [], []
        for name, group in windows.items():
            aa = np.array([accel.Correct(r.accel) for r in group])
            mm = np.array([mag.Correct(r.magnetic) for r in group])
            gg = np.array([r.gyro for r in group])
            av, mv = aa.mean(axis=0), mm.mean(axis=0)
            an, mn = np.linalg.norm(av), np.linalg.norm(mv)
            if (len(group) < 3 or abs(an-policy.gravity) > policy.max_accel_error
                    or max(np.std(aa, axis=0)) > policy.max_accel_std
                    or max(np.linalg.norm(gg, axis=1)) > policy.max_gyro_norm
                    or abs(mn-policy.reference_uT) > policy.reference_uT*policy.max_field_error_fraction
                    or max(np.std(mm, axis=0)) > policy.max_field_std):
                rejected.append((name, "STATIC_OR_FIELD_QUALITY"))
                continue
            if av @ FACE_AXES[group[0].face]/an < math.cos(math.radians(policy.max_face_angle_deg)):
                rejected.append((name, "FACE_CONVENTION_MISMATCH"))
                continue
            accepted.append((group[0], av/an, mv/mn))
        return accepted, rejected

    def Solve(self, accel, mag, policy=Policy(), cancel: Callable[[], bool] = lambda: False,
              coarse_prior_R=None, coarse_prior_radius_deg=None,
              progress: Callable[[int, int], None] | None = None):
        context = self.ContextDigest(accel, mag, policy)
        gates = {"global_uniqueness": "NOT_PROVEN_MULTISTART",
                 "thresholds": policy.threshold_status,
                 "coordinate_evidence": "DECLARED_NOT_HARDWARE_VERIFIED",
                 "gyro_axes": "DECLARED" if self.convention.R_GA is not None else "NOT_PROVEN",
                 "coarse_prior": "DIAGNOSTIC_ONLY_NEVER_DISAMBIGUATES",
                 "holdout_selection": "VALIDATION_ONLY_NEVER_SELECTS",
                 "dynamic_gyro": "NOT_IMPLEMENTED", "apply": "DISABLED_OFFLINE"}

        def report(status, reasons, **kwargs):
            return CandidateReport(status, tuple(reasons), dict(gates), self.raw_digest, context, **kwargs)

        if cancel():
            return report(CandidateResult.Cancelled, ["CANCELLED"])
        try:
            from scipy.optimize import least_squares
            from scipy.spatial.transform import Rotation
        except ImportError:
            return report(CandidateResult.NumericalFailure, ["FIT_DEPENDENCY_UNAVAILABLE"])
        try:
            if coarse_prior_R is not None:
                _matrix(coarse_prior_R, rotation=True)
                if not 0 < _number(coarse_prior_radius_deg) <= 180:
                    raise ValueError("INVALID_COARSE_PRIOR")
            rows, rejected = self._prepare(accel, mag, policy)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            gates["input"] = "FAIL"
            return report(CandidateResult.Rejected, [str(exc)])
        gates["input"] = "PASS_DECLARED_METADATA"
        train = [r for r in rows if r[0].split == "TRAIN"]
        hold = [r for r in rows if r[0].split == "HOLDOUT"]
        base = {"windows": len(rows), "rejected_windows": tuple(rejected)}
        if (set(x[0].face for x in train) != set(FACES) or len(hold) < 3):
            return report(CandidateResult.NeedSamples, ["SIX_FACES_AND_HOLDOUT_REQUIRED"], **base)
        # Each declared pose has equal total weight even with repeated windows.
        weights = np.array([1/sum(t[0].pose == x[0].pose for t in train) for x in train])
        weights /= weights.sum()
        a, m = np.array([x[1] for x in train]), np.array([x[2] for x in train])
        ha, hm = np.array([x[1] for x in hold]), np.array([x[2] for x in hold])
        rng = np.random.default_rng(policy.seed)
        starts = [np.zeros(3), *list(np.pi*np.eye(3))]
        starts.extend(Rotation.random(policy.starts-4, random_state=rng).as_rotvec())
        solutions, converged, attempted = [], 0, 0

        def residual(x):
            if cancel():
                raise _Cancelled()
            rotated = m @ Rotation.from_rotvec(x[:3]).as_matrix().T
            return np.sqrt(weights*len(a))*(np.einsum("ij,ij->i", a, rotated)-x[3])

        try:
            for start in starts:
                if progress is not None:
                    progress(attempted, len(starts))
                attempted += 1
                initial = np.r_[start, np.clip(np.mean(np.sum(a*(m @ Rotation.from_rotvec(start).as_matrix().T), axis=1)), -.999, .999)]
                fit = least_squares(residual, initial, bounds=([-np.inf]*3+[-1.], [np.inf]*3+[1.]),
                                    loss="soft_l1", f_scale=.006, max_nfev=policy.max_nfev,
                                    ftol=1e-10, xtol=1e-10, gtol=1e-10)
                if not fit.success or not np.isfinite(fit.x).all():
                    continue
                converged += 1
                R = Rotation.from_rotvec(fit.x[:3]).as_matrix()
                if any(Rotation_DistanceDeg(R, sol.R_AM) < .2 for sol in solutions):
                    continue
                # Ordinary residual/conditioning still gate a robustly optimized fit.
                s, res, singular, weak, _ = Geometry_Evaluate(a, m, R, weights)
                hres = np.einsum("ij,ij->i", ha, hm @ R.T)-s
                rga = self.convention.R_GA
                solutions.append(Candidate(_matrix(R), s, float(np.sqrt(weights @ res**2)),
                    float(max(abs(res))), float(np.sqrt(np.mean(hres**2))), float(max(abs(hres))),
                    tuple(singular), tuple(weak), math.sqrt(max(0., 1-s*s)),
                    None if rga is None else _matrix(np.array(rga) @ R)))
        except _Cancelled:
            return report(CandidateResult.Cancelled, ["CANCELLED"], search_attempts=attempted,
                          search_converged=converged, **base)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            return report(CandidateResult.NumericalFailure, [str(exc)], search_attempts=attempted,
                          search_converged=converged, **base)
        if progress is not None:
            progress(attempted, len(starts))
        if not solutions:
            return report(CandidateResult.NumericalFailure, ["NO_CONVERGED_SEARCH"], search_attempts=attempted, **base)
        solutions.sort(key=lambda x: x.train_rms)
        minimum = solutions[0].train_rms
        plausible = [x for x in solutions if x.train_rms <= minimum+policy.ambiguity_delta]
        # Holdout is validation only: never select or dismiss a training solution
        # using it. Resolving ambiguity needs newly acquired training evidence.
        best = plausible[0]
        competitors = [x for x in plausible
                       if Rotation_DistanceDeg(x.R_AM, best.R_AM) >= policy.distinct_rotation_deg]
        gates.update({"train": "PASS" if best.train_rms <= policy.residual_rms and best.train_max <= policy.residual_max else "FAIL",
                      "holdout": "PASS" if best.holdout_rms <= policy.residual_rms and best.holdout_max <= policy.residual_max else "FAIL",
                      "local_excitation": "PASS" if best.singular_values[-1] >= policy.min_singular and best.singular_values[-1]/max(best.singular_values[0], 1e-12) >= policy.min_singular_ratio else "FAIL",
                      "horizontal_field": "PASS" if best.horizontal >= policy.min_horizontal else "FAIL",
                      "candidate_separation": "FAIL" if competitors else "NO_COMPETITOR_FOUND_NOT_PROOF",
                      "window_quality": "FAIL" if rejected else "PASS"})
        reasons = [name.upper() for name in ("train", "holdout", "local_excitation", "horizontal_field", "window_quality") if gates[name] == "FAIL"]
        if competitors:
            reasons.append("MULTIPLE_SOLUTIONS")
        if coarse_prior_R is not None:
            inside = sum(Rotation_DistanceDeg(x.R_AM, coarse_prior_R) <= coarse_prior_radius_deg for x in plausible)
            gates["coarse_prior_candidates_inside"] = str(inside)
        return report(CandidateResult.NeedSamples if reasons else CandidateResult.Candidate, reasons,
                      candidates=tuple([best]+[x for x in solutions if x is not best]),
                      supplemental_faces=Supplement_Suggest(best.weak_axis_A),
                      search_attempts=len(starts), search_converged=converged, **base)


def ImuSixFace_Fit(session, previous, gravity=9.80665):
    """Diagonal accel bias/scale and stationary gyro bias only, candidate output."""
    gravity = _number(gravity)
    if (gravity <= 0 or previous.identity != session.records[0].imu or previous.unit != "m/s2"
            or previous.output_frame != session.convention.accel_frame):
        return IntrinsicFitResult.Rejected, None, None
    try:
        session._validate_metadata(Policy(gravity=gravity))
    except ValueError:
        return IntrinsicFitResult.Rejected, None, None
    means, gyro = [], []
    for face in FACES:
        group = [r for r in session.records if r.face == face and r.split == "TRAIN" and r.stage == "SIX_FACE"]
        if len(group) < 3 or any(r.imu != previous.identity or not r.sync_valid or r.quality_flags for r in group):
            return IntrinsicFitResult.Rejected, None, None
        a = np.array([r.accel for r in group]); g = np.array([r.gyro for r in group])
        if max(np.std(a, axis=0)) > .12 or max(np.linalg.norm(g, axis=1)) > .15:
            return IntrinsicFitResult.Rejected, None, None
        means.append(a.mean(axis=0)); gyro.append(g.mean(axis=0))
    means = np.array(means)
    positive = np.array([means[2*i, i] for i in range(3)])
    negative = np.array([means[2*i+1, i] for i in range(3)])
    difference = positive-negative
    if np.any(difference <= 0):
        return IntrinsicFitResult.Rejected, None, None
    scale = 2*gravity/difference
    if np.any((scale < .8) | (scale > 1.2)) or previous.generation == 2**32-1:
        return IntrinsicFitResult.Rejected, None, None
    fit = Intrinsic(previous.identity, previous.generation+1, "six-face-diagonal-candidate",
                    tuple((positive+negative)/2), _matrix(np.diag(scale)), "m/s2", previous.output_frame)
    expected = np.array([FACE_AXES[face]*gravity for face in FACES])
    if max(np.linalg.norm(np.array([fit.Correct(x) for x in means])-expected, axis=1)) > .7:
        return IntrinsicFitResult.Rejected, None, None
    return IntrinsicFitResult.Candidate, fit, tuple(np.mean(gyro, axis=0))


def Snapshot_Export(session, accel, mag, policy=Policy()):
    """Pure-data replay snapshot, not a wire protocol or a committed calibration."""
    return {"records": [asdict(r) for r in session.records], "convention": asdict(session.convention),
            "accel": asdict(accel), "mag": asdict(mag), "policy": asdict(policy)}


def Snapshot_Import(payload):
    """Reconstruct owned immutable values; rejects incomplete/unknown top-level data."""
    if (type(payload) is not dict or set(payload) != {"records", "convention", "accel", "mag", "policy"}
            or type(payload["records"]) is not list or not 1 <= len(payload["records"]) <= MAX_RECORDS):
        raise ValueError("complete bounded replay snapshot required")
    try:
        records = []
        for value in payload["records"]:
            values = dict(value)
            values["imu"] = SensorIdentity(**values["imu"])
            values["mag"] = SensorIdentity(**values["mag"])
            records.append(RawPair(**values))
        intrinsics = []
        for key in ("accel", "mag"):
            value = dict(payload[key]); value["identity"] = SensorIdentity(**value["identity"])
            intrinsics.append(Intrinsic(**value))
        session = InstallationSession(records, Convention(**payload["convention"]))
        return session, intrinsics[0], intrinsics[1], Policy(**payload["policy"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid replay snapshot: "+str(exc)) from exc


def MagEllipsoid_Fit(raw_points, previous, reference_uT=48.):
    """Standalone algebraic ellipsoid fit in a fixed SPD gauge; no outlier certification."""
    try:
        points = np.asarray(raw_points, dtype=float)
        reference = _number(reference_uT)
    except (TypeError, ValueError):
        return IntrinsicFitResult.Rejected, None
    if (points.ndim != 2 or points.shape[1] != 3 or not 128 <= len(points) <= MAX_RECORDS
            or not np.isfinite(points).all() or not 10 <= reference <= 100
            or previous.generation == 2**32-1 or previous.unit != "uT"):
        return IntrinsicFitResult.Rejected, None
    center0 = points.mean(axis=0)
    scale0 = np.std(points, axis=0).max()
    if scale0 < 1e-9:
        return IntrinsicFitResult.Rejected, None
    x, y, z = ((points-center0)/scale0).T
    design = np.array([x*x, y*y, z*z, 2*x*y, 2*x*z, 2*y*z, x, y, z]).T
    try:
        q, _, rank, _ = np.linalg.lstsq(design, np.ones(len(points)), rcond=None)
        if rank != 9:
            return IntrinsicFitResult.Rejected, None
        Q = np.array([[q[0], q[3], q[4]], [q[3], q[1], q[5]], [q[4], q[5], q[2]]])
        bias0 = np.linalg.solve(Q, -.5*q[6:])
        radius2 = 1+float(bias0 @ Q @ bias0)
        if radius2 <= 0:
            return IntrinsicFitResult.Rejected, None
        eig, axes = np.linalg.eigh(Q/radius2)
        if min(eig) <= 0 or math.sqrt(max(eig)/min(eig)) > 25:
            return IntrinsicFitResult.Rejected, None
        matrix = reference/scale0 * ((axes*np.sqrt(eig)) @ axes.T)
        bias = center0+scale0*bias0
        corrected = (points-bias) @ matrix.T
        octants = ((corrected >= 0)*[4, 2, 1]).sum(axis=1)
        norm_error = np.linalg.norm(corrected, axis=1)-reference
        if min(np.bincount(octants, minlength=8)) < 4 or np.sqrt(np.mean(norm_error**2)) > .15*reference or max(abs(norm_error)) > .5*reference:
            return IntrinsicFitResult.Rejected, None
        result = Intrinsic(previous.identity, previous.generation+1, "ellipsoid-SPD-candidate",
                           _vec(bias), _matrix(matrix, spd=True), "uT", previous.output_frame)
        return IntrinsicFitResult.Candidate, result
    except np.linalg.LinAlgError:
        return IntrinsicFitResult.Rejected, None
