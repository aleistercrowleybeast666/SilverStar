"""ctypes binding of the actual FCCG C core; no duplicate C implementation."""

from __future__ import annotations

import ctypes as ct

import numpy as np

Float3 = ct.c_float * 3
Float2 = ct.c_float * 2
Float15 = ct.c_float * 15
Matrix15 = Float15 * 15


class Config(ct.Structure):
    _fields_ = [
        (name, ct.c_float)
        for name in ("gravity", "gyro_noise", "accel_noise", "gyro_rw", "accel_rw")
    ]
    _fields_ += [("soft", Float2), ("hard", Float2), ("r_max", ct.c_float)]


class State(ct.Structure):
    _fields_ = [
        ("p", Float3),
        ("v", Float3),
        ("q", ct.c_float * 4),
        ("bg", Float3),
        ("ba", Float3),
        ("covariance", Matrix15),
        ("timestamp", ct.c_uint64),
        ("source", ct.c_uint32),
        ("generation", ct.c_uint32),
        ("initialized", ct.c_uint8),
    ]


class Body(ct.Structure):
    _fields_ = [
        ("gyro", Float3 * 2),
        ("accel", Float3 * 2),
        ("dt", ct.c_float),
        ("start", ct.c_uint64),
        ("end", ct.c_uint64),
        ("source", ct.c_uint32),
        ("generation", ct.c_uint32),
        ("quality", ct.c_uint32),
    ]


class Observation(ct.Structure):
    _fields_ = [
        ("group", ct.c_uint8),
        ("valid", ct.c_uint8),
        ("observation", Float2),
        ("variance", Float2),
        ("lever", Float3),
        ("gyro", Float3),
    ]


class Outcome(ct.Structure):
    _fields_ = [
        ("nis", ct.c_float),
        ("scale", ct.c_float),
        ("innovation", Float2),
        ("variance", Float2),
        ("gain_norm", ct.c_float),
        ("dimension", ct.c_uint8),
        ("result", ct.c_int),
    ]


class Workspace(ct.Structure):
    _fields_ = [(name, Matrix15) for name in ("f", "phi", "temporary", "candidate_p")]
    _fields_ += [
        ("candidate_x", ct.c_float * 16),
        ("correction", Float15),
        ("h", Float15 * 2),
        ("gain", Float2 * 15),
        ("innovation_covariance", Float2 * 2),
    ]


class CCore:
    def __init__(self, library, initial):
        self.library = library
        self.state, self.workspace = State(), Workspace()
        self.config = Config(
            9.78, 0.003, 0.08, 0.0001, 0.001, Float2(6.635, 9.21), Float2(10.828, 13.816), 4.0
        )
        nominal = np.asarray(
            np.r_[initial.p, initial.v, initial.q, initial.bg, initial.ba], dtype=np.float32
        )
        covariance = np.asarray(initial.covariance, dtype=np.float32)
        self.library.NavigationEskf_Initialize.argtypes = [
            ct.POINTER(State),
            ct.POINTER(Workspace),
            ct.POINTER(ct.c_float),
            ct.POINTER(Float15),
            ct.c_uint64,
            ct.c_uint32,
            ct.c_uint32,
        ]
        self.library.NavigationEskf_Predict.argtypes = [
            ct.POINTER(State),
            ct.POINTER(Workspace),
            ct.POINTER(Config),
            ct.POINTER(Body),
        ]
        self.library.NavigationEskf_Update.argtypes = [
            ct.POINTER(State),
            ct.POINTER(Workspace),
            ct.POINTER(Config),
            ct.POINTER(Observation),
            ct.POINTER(Outcome),
        ]
        result = self.library.NavigationEskf_Initialize(
            ct.byref(self.state),
            ct.byref(self.workspace),
            nominal.ctypes.data_as(ct.POINTER(ct.c_float)),
            covariance.ctypes.data_as(ct.POINTER(Float15)),
            1_000_000,
            0,
            1,
        )
        assert result == 0

    def Predict(self, w1, a1, w2, a2):
        body = Body(
            (Float3 * 2)(Float3(*w1), Float3(*w2)),
            (Float3 * 2)(Float3(*a1), Float3(*a2)),
            0.01,
            self.state.timestamp,
            self.state.timestamp + 10_000,
            0,
            1,
            0,
        )
        return self.library.NavigationEskf_Predict(
            ct.byref(self.state), ct.byref(self.workspace), ct.byref(self.config), ct.byref(body)
        )

    def Update(self, group, z, r, gyro, lever, valid=True):
        observation = Observation(
            group,
            valid,
            Float2(*(list(z) + [0])[:2]),
            Float2(*(list(r) + [0])[:2]),
            Float3(*lever),
            Float3(*gyro),
        )
        outcome = Outcome()
        result = self.library.NavigationEskf_Update(
            ct.byref(self.state),
            ct.byref(self.workspace),
            ct.byref(self.config),
            ct.byref(observation),
            ct.byref(outcome),
        )
        return result, outcome
