"""Physical rigid-pose fixtures, independently generated from world field vectors."""
from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation

from .prototype import (Convention, FACE_AXES, FACES, InstallationSession, Intrinsic,
                       RawPair, SensorIdentity, _matrix)


@dataclass(frozen=True)
class Case:
    session: InstallationSession
    accel: Intrinsic
    mag: Intrinsic
    R_AM_true: tuple
    s_true: float
    R_WA: tuple
    alternate_R_AM: tuple | None = None


def _tangent(axis, angle):
    basis = np.eye(3)[int(np.argmin(abs(axis)))]
    return np.cos(angle)*basis + np.sin(angle)*np.cross(axis, basis)


def _pose(a, magnetic, s):
    """Construct actual SO(3) A-to-world orientation for a fixed world field."""
    t = (magnetic-s*a)/np.sqrt(1-s*s)
    body_basis = np.column_stack((a, t, np.cross(a, t)))
    world_a, world_t = np.array([0., 0., 1.]), np.array([1., 0., 0.])
    world_basis = np.column_stack((world_a, world_t, np.cross(world_a, world_t)))
    return _matrix(world_basis @ body_basis.T, rotation=True)


def Case_Build(kind="normal", *, noise=0., s=.45, seed=901, supplement=(), convention=None):
    rng = np.random.default_rng(seed)
    imu = SensorIdentity("synthetic-board", 1, 1, 0, "synthetic-imu", "fixture", "cfg-A", "A0")
    magid = SensorIdentity("synthetic-board", 2, 2, 0, "synthetic-mag", "fixture", "cfg-M", "M0")
    accel = Intrinsic(imu, 7, "accel-truth", (.10, -.08, .06),
                      _matrix(np.diag([1.02, .98, 1.01])), "m/s2", "A")
    magnetic = Intrinsic(magid, 11, "mag-truth", (3., -2., 1.),
                         ((1.15, .04, .02), (.04, .9, -.03), (.02, -.03, 1.07)), "uT", "M")
    R = Rotation.from_rotvec([.13, -.09, .11]).as_matrix()
    alt = Rotation.from_rotvec(np.array([1., 1., 1.])*.32).as_matrix()
    definitions = []
    angles = [.13, .87, 1.2, 2.6, -.45, 1.7]
    for i, face in enumerate(FACES):
        a = FACE_AXES[face]
        if kind == "symmetric":
            positive = FACE_AXES[FACES[i-i % 2]]
            t = _tangent(positive, angles[i-i % 2]) * (-1 if i % 2 else 1)
            m = s*a+np.sqrt(1-s*s)*t
        elif kind == "ambiguous":
            constraints = np.array([a, alt.T @ a])
            base = constraints.T @ np.linalg.solve(constraints @ constraints.T, [s, s])
            null = np.cross(*constraints); null /= np.linalg.norm(null)
            sign = [1, 1, -1, 1, -1, -1][i]
            m = base+sign*np.sqrt(1-base @ base)*null
        elif kind == "normal":
            m = s*a+np.sqrt(1-s*s)*_tangent(a, angles[i])
        else:
            raise ValueError("unknown synthetic case")
        definitions.append((face, m, "SIX_FACE", face+"-original"))
    for j, (face, angle) in enumerate(supplement):
        a = FACE_AXES[face]
        m = s*a+np.sqrt(1-s*s)*_tangent(a, angle)
        definitions.append((face, m, "SUPPLEMENT", f"{face}-supplement-{j}"))
    records, poses = [], []
    for face, m_A, stage, pose_id in definitions:
        a = FACE_AXES[face]
        poses.append(_pose(a, m_A, s))
        for split in ("TRAIN", "HOLDOUT"):
            for _ in range(5):
                n = len(records)+1; now = 100000+50000*n
                corrected_a = a*9.80665+rng.normal(0, noise, 3)
                corrected_m = (R.T @ m_A)*48+rng.normal(0, noise, 3)
                raw_a = np.linalg.solve(accel.matrix, corrected_a)+accel.bias
                raw_m = np.linalg.solve(magnetic.matrix, corrected_m)+magnetic.bias
                records.append(RawPair("synthetic-session", "synthetic-boot", n, imu, magid,
                    3, 4, n, n, now, now+100, now+500, now+600, "SHARED_SYNTHETIC_CLOCK", 20,
                    True, (), stage, face, pose_id+"-"+split, pose_id, split,
                    tuple(raw_a), tuple(np.array([.003, -.005, .002])+rng.normal(0, noise*.01, 3)),
                    tuple(raw_m), ("acquisition-accel-g6", "acquisition-mag-g10"), (6, 10)))
    convention = convention or Convention(R_GA=_matrix(np.eye(3)), gyro_axis_evidence="SYNTHETIC_TRUTH")
    return Case(InstallationSession(tuple(records), convention), accel, magnetic,
                _matrix(R), s, tuple(poses), _matrix(alt @ R) if kind == "ambiguous" else None)


def RotationCloud_Build(intrinsic, count=384, seed=812):
    rng = np.random.default_rng(seed)
    v = rng.normal(size=(count, 3)); v *= 48/np.linalg.norm(v, axis=1)[:, None]
    return tuple(tuple(x) for x in (np.linalg.solve(intrinsic.matrix, v.T).T+intrinsic.bias))
