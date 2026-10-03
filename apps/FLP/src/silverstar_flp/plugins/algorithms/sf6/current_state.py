"""SF6 revision 2: float32 fixed gains applied to the latest predicted state.

Source epochs only guard age/order. No history, event queue or delay replay.
"""

import numpy as np

from silverstar_flp.plugins.algorithms.sf6.filter import NavigationSf6Result as Result
from silverstar_flp.plugins.algorithms.sf6.filter import Sf6Filter


class Sf6CurrentStateFilter:
    MAX_MEASUREMENT_AGE_US = 500_000

    def __init__(self, gain, velocity=(0, 0, 0), timestamp_us=0):
        # Share initialization validation, without retaining legacy history.
        initial = Sf6Filter(gain, velocity, timestamp_us)
        self.gain = initial.gain
        self._state = initial.state
        self.timestamp_us = self.initial_epoch_us = timestamp_us
        self.last = [None] * 5

    @property
    def state(self):
        return self._state.copy()

    def Predict(self, timestamp_us, delta_velocity, dt_s):
        dv, dt = np.asarray(delta_velocity, dtype=np.float32), np.float32(dt_s)
        if (dv.shape != (3,) or not np.isfinite(dv).all()
                or not np.isfinite(dt) or dt <= 0 or dt > np.float32(0.02)
                or not 0 <= timestamp_us < 2**64):
            return Result.INVALID_ARGUMENT
        duration = int(np.floor(float(np.float32(dt * np.float32(1e6))) + 0.5))
        if (timestamp_us <= self.timestamp_us or duration == 0
                or timestamp_us - self.timestamp_us != duration):
            return Result.STALE
        candidate = Sf6Filter._State_Advance(self._state, dv, dt)
        if not np.isfinite(candidate).all():
            return Result.NUMERIC_ERROR
        self._state, self.timestamp_us = candidate, timestamp_us
        return Result.OK

    def Update(self, measurement):
        group = measurement.group
        obs = np.asarray(measurement.observation, dtype=np.float32)
        if (not 0 <= group < 5 or obs.shape != (2,)
                or not 0 <= measurement.measurement_us <= measurement.receive_us <= self.timestamp_us
                or not 0 <= measurement.sequence < 2**32
                or not np.isfinite(obs[0]) or (group in (0, 2) and not np.isfinite(obs[1]))):
            return Result.INVALID_ARGUMENT, None
        if (measurement.measurement_us < self.initial_epoch_us
                or self.timestamp_us - measurement.measurement_us > self.MAX_MEASUREMENT_AGE_US):
            return Result.STALE, None
        last = self.last[group]
        if last is not None and (measurement.measurement_us <= last.measurement_us
                or measurement.receive_us <= last.receive_us
                or not 0 < (measurement.sequence - last.sequence) % 2**32 < 2**31):
            return Result.DUPLICATE, None
        candidate = self._state.copy()
        first = (3, 5, 0, 2, 5)[group]
        with np.errstate(over="ignore", invalid="ignore"):
            for axis in range(2 if group in (0, 2) else 1):
                index = first + axis
                correction = (np.float32(0) if self.gain[index] == 0
                              else self.gain[index] * (obs[axis] - candidate[index]))
                candidate[index] += correction
        if not np.isfinite(candidate).all():
            return Result.NUMERIC_ERROR, None
        self._state, self.last[group] = candidate, measurement
        return Result.OK, self.timestamp_us
