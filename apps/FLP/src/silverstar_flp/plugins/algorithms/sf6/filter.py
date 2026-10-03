"""Float32 port of navigation_sf6.c; validated against the unmodified C core.

State/gain order: vE,vN,vU,pE,pN,pU. History: 256 boundaries/600 ms;
events: 256, ordered by measurement epoch then group. Updates are transactional.
"""

from dataclasses import dataclass
from enum import IntEnum

import numpy as np


class NavigationSf6Result(IntEnum):
    OK = 0
    INVALID_ARGUMENT = 1
    NOT_READY = 2
    STALE = 3
    DUPLICATE = 4
    NUMERIC_ERROR = 5
    FULL = 6


@dataclass(frozen=True, slots=True)
class Sf6Measurement:
    measurement_us: int
    receive_us: int
    sequence: int
    group: int
    observation: tuple[float, float]


@dataclass(slots=True)
class _Boundary:
    timestamp_us: int
    state: np.ndarray
    delta_velocity: np.ndarray
    dt_s: np.float32


class Sf6Filter:
    def __init__(self, gain, velocity=(0, 0, 0), timestamp_us=0):
        gain, velocity = np.asarray(gain, dtype=np.float32), np.asarray(velocity, dtype=np.float32)
        if (
            gain.shape != (6,)
            or velocity.shape != (3,)
            or not np.isfinite(gain).all()
            or not np.isfinite(velocity).all()
            or np.any((gain < 0) | (gain > 1))
            or not 0 <= timestamp_us < 2**64
        ):
            raise ValueError("sf6_initial_state_invalid")
        self.gain = gain.copy()
        self.base_state = np.r_[velocity, np.zeros(3, dtype=np.float32)]
        self.history = [
            _Boundary(
                timestamp_us, self.base_state.copy(), np.zeros(3, dtype=np.float32), np.float32(0)
            )
        ]
        self.events = []
        self.last = [None] * 5

    @property
    def state(self):
        return self.history[-1].state.copy()

    @staticmethod
    def _State_Advance(state, delta_velocity, dt_s):
        result = state.copy()
        with np.errstate(over="ignore", invalid="ignore"):
            for axis in range(3):
                result[3 + axis] += (result[axis] + np.float32(0.5) * delta_velocity[axis]) * dt_s
                result[axis] += delta_velocity[axis]
        return result

    def Predict(self, timestamp_us, delta_velocity, dt_s):
        dv, dt = np.asarray(delta_velocity, dtype=np.float32), np.float32(dt_s)
        if (
            dv.shape != (3,)
            or not np.isfinite(dv).all()
            or not np.isfinite(dt)
            or dt <= 0
            or dt > np.float32(0.02)
            or not 0 <= timestamp_us < 2**64
        ):
            return NavigationSf6Result.INVALID_ARGUMENT
        # llroundf is halfway away from zero; the firmware multiplies in float32.
        duration = int(np.floor(float(np.float32(dt * np.float32(1e6))) + 0.5))
        if (
            timestamp_us <= self.history[-1].timestamp_us
            or duration == 0
            or (timestamp_us - self.history[-1].timestamp_us != duration)
        ):
            return NavigationSf6Result.STALE
        state = self._State_Advance(self.state, dv, dt)
        if not np.isfinite(state).all():
            return NavigationSf6Result.NUMERIC_ERROR
        if len(self.history) == 256:
            self._Oldest_Drop()
        self.history.append(_Boundary(timestamp_us, state, dv.copy(), dt))
        while len(self.history) > 1 and timestamp_us - self.history[0].timestamp_us > 600_000:
            self._Oldest_Drop()
        return NavigationSf6Result.OK

    def _Oldest_Drop(self):
        next_boundary = self.history[1]
        self.base_state = self._State_Advance(
            self.history[0].state, next_boundary.delta_velocity, next_boundary.dt_s
        )
        self.history.pop(0)
        self.events = [e for e in self.events if e.measurement_us >= next_boundary.timestamp_us]

    def Update(self, measurement):
        group = measurement.group
        obs = np.asarray(measurement.observation, dtype=np.float32)
        if (
            not 0 <= group < 5
            or obs.shape != (2,)
            or not 0
            <= measurement.measurement_us
            <= measurement.receive_us
            <= self.history[-1].timestamp_us
            or not 0 <= measurement.sequence < 2**32
            or not np.isfinite(obs[0])
            or (group in (0, 2) and not np.isfinite(obs[1]))
        ):
            return NavigationSf6Result.INVALID_ARGUMENT, None
        if measurement.measurement_us < self.history[0].timestamp_us:
            return NavigationSf6Result.STALE, None
        last = self.last[group]
        if last is not None and (
            measurement.measurement_us <= last.measurement_us
            or measurement.receive_us <= last.receive_us
            or not 0 < (measurement.sequence - last.sequence) % 2**32 < 2**31
        ):
            return NavigationSf6Result.DUPLICATE, None
        if len(self.events) == 256:
            return NavigationSf6Result.FULL, None
        # Existing equal-time/equal-group events precede the new candidate (stable sort).
        events = sorted([*self.events, measurement], key=lambda e: (e.measurement_us, e.group))
        state = self.base_state.copy()
        states = []
        cursor = 0
        with np.errstate(over="ignore", invalid="ignore"):
            for index, boundary in enumerate(self.history):
                if index:
                    state = self._State_Advance(state, boundary.delta_velocity, boundary.dt_s)
                limit = (
                    self.history[index + 1].timestamp_us if index + 1 < len(self.history) else 2**64
                )
                while cursor < len(events) and events[cursor].measurement_us < limit:
                    event = events[cursor]
                    first = (3, 5, 0, 2, 5)[event.group]
                    for axis in range(2 if event.group in (0, 2) else 1):
                        i = first + axis
                        correction = (
                            np.float32(0)
                            if self.gain[i] == 0
                            else self.gain[i] * (np.float32(event.observation[axis]) - state[i])
                        )
                        state[i] += correction
                    cursor += 1
                if not np.isfinite(state).all():
                    return NavigationSf6Result.NUMERIC_ERROR, None
                states.append(state.copy())
        # Publish only after the complete candidate replay succeeds.
        for boundary, state in zip(self.history, states, strict=True):
            boundary.state = state
        self.events = events
        self.last[group] = measurement
        boundary_us = max(
            b.timestamp_us for b in self.history if b.timestamp_us <= measurement.measurement_us
        )
        return NavigationSf6Result.OK, boundary_us
