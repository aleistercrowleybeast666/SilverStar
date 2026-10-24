"""Bounded arrival-order replay at recorded measurement times, revision 1.

The input path is independent of the C controller. Both implement the documented
piecewise-constant original IMU half means. Neither reconstructs within-half
motion. Mathematical model parity remains separate from provenance completeness.
"""
from bisect import bisect_right
import copy
from dataclasses import replace
import math
import numpy as np

from . import eskf20_reference as eskf
from . import inekf15_reference as inv15
from . import inekf20_reference as inv20
from .input_reference import ReferenceSession, Result, Event, Identity, unsigned

REVISION = 1
BODY_CAPACITY = 64
OBSERVATION_CAPACITY = 64
MAXIMUM_DELAY_US = 250000
_RESULT = {"ok": 0, "invalid_input": 1, "invalid_state": 11,
    "numeric_error": 8, "rejected_nis": 12, "rejected_correction": 13,
    "unsupported_observation": 14}
TERMINAL = {0, 10, 12, 13}


def result_code(value):
    return int(value) if isinstance(value, (Result, int)) else _RESULT.get(value, 8)


def result_label(value):
    return {0:'ok',1:'INVALID',2:'IDENTITY',3:'UNTRUSTED_TIME',4:'FUTURE',5:'DELAYED_UNSUPPORTED',
            6:'DUPLICATE',7:'OUT_OF_ORDER',8:'NUMERIC',9:'WRONG_STAGE',10:'FIELD_REJECTED',
            11:'INVALID_STATE',12:'rejected_nis',13:'rejected_correction',14:'unsupported_observation',
            15:'HISTORY_MISS',16:'CAPACITY'}[result_code(value)]


def _advance(session, body, target, gravity, canonical_density):
    start, end, gyro, force = body
    if not start <= session.state_us < target <= end or not 0 < end-start <= 20000:
        return 1
    # Relative doubled microseconds are exact even above absolute clock 2**53.
    lower, upper = 2*(session.state_us-start), 2*(target-start)
    duration = end-start
    density = canonical_density
    if session.model == "eskf20":
        density = np.r_[density[3:6], density[:3], density[6:]]
    predict = {"eskf20": eskf.Eskf20_Predict, "inekf15": inv15.InEkf15_Predict,
               "inekf20": inv20.InEkf20_Predict}[session.model]
    candidate = session.state
    for half in range(2):
        ticks = min(upper, (half+1)*duration) - max(lower, half*duration)
        if ticks > 0:
            step = predict(candidate, gyro[half], force[half], gravity, density, ticks/2000000.)
            code = result_code(step.result.value)
            if code:
                return code
            candidate = step.state
    session.state = replace(candidate, time_s=(target-session.origin_us)/1000000.)
    session.state_us = target
    return 0


class BufferedSession:
    def __init__(self, model, state, origin_us, identities, gravity, density,
                 maximum_delay_us=MAXIMUM_DELAY_US,magnetic_native_float32=False):
        gravity = np.asarray(gravity, dtype=float)
        density = np.asarray(density, dtype=float)
        if (gravity.shape != (3,) or density.shape != (12,)
                or not np.isfinite(gravity).all() or not np.isfinite(density).all()
                or (density < 0).any() or not unsigned(maximum_delay_us, 64)
                or not 0 < maximum_delay_us <= 1000000):
            raise ValueError("navigation_replay_configuration")
        self.current = ReferenceSession(model, state, origin_us, identities,magnetic_native_float32=magnetic_native_float32)
        self.anchor = copy.deepcopy(self.current)
        self.gravity, self.density = gravity.copy(), density.copy()
        self.maximum_delay_us = maximum_delay_us
        self.bodies, self.observations, self.outcomes = [], [], []
        self.retired_accepted, self.retired_rejected = [0]*3, [0]*3

    @property
    def state(self):
        return self.current.state

    @property
    def state_us(self):
        return self.current.state_us

    @staticmethod
    def _apply(session, row):
        event, kind, args = row
        if kind == "magnetic":
            return result_code(session.update_magnetic(event, *args))
        return result_code(session.update_vector(event, kind, *args))

    def _run(self, bodies, observations):
        candidate = copy.deepcopy(self.anchor)
        outcomes, cursor = [], 0
        for body in bodies:
            if body[0] != candidate.state_us:
                return 11, None, []
            while cursor < len(observations) and observations[cursor][0].sample_us <= body[1]:
                target = observations[cursor][0].sample_us
                if target < candidate.state_us:
                    return 11, None, []
                if target > candidate.state_us:
                    code = _advance(candidate, body, target, self.gravity, self.density)
                    if code:
                        return code, None, []
                code = self._apply(candidate, observations[cursor])
                if code not in TERMINAL:
                    return code, None, []
                outcomes.append(code)
                cursor += 1
            if candidate.state_us < body[1]:
                code = _advance(candidate, body, body[1], self.gravity, self.density)
                if code:
                    return code, None, []
        return 0, candidate, outcomes

    def _sequence_history_valid(self):
        # Stored history is a distinct contract from a proposed external event.
        for kind, anchor in self.anchor.ledgers.items():
            previous, time = anchor.last_sequence, anchor.last_sample_us
            for event, group, _ in self.observations:
                if group != kind:
                    continue
                if previous is not None and (event.sample_us <= time or
                        not 0 < (event.sequence-previous) % 2**32 < 2**31):
                    return False
                previous, time = event.sequence, event.sample_us
            current = self.current.ledgers[kind]
            if (current.last_sequence, current.last_sample_us) != (previous, time):
                return False
        return True

    def predict_pair(self, start, end, gyro, force, gravity, density):
        if not self._sequence_history_valid():
            return 11
        if not np.array_equal(gravity, self.gravity) or not np.array_equal(density, self.density):
            return 1
        candidate = copy.deepcopy(self.current)
        code = result_code(candidate.predict_pair(start, end, gyro, force, self.gravity, self.density))
        if code:
            return code
        anchor, removed = None, 0
        if len(self.bodies) == BODY_CAPACITY:
            code, anchor, outcomes = self._run(self.bodies[:1], self.observations)
            if code:
                return code
            removed = len(outcomes)
        if anchor is not None:
            for row, code in zip(self.observations[:removed], self.outcomes[:removed]):
                group = ("position", "velocity", "magnetic").index(row[1])
                (self.retired_accepted if code == 0 else self.retired_rejected)[group] += 1
            self.anchor = anchor
            self.bodies = self.bodies[1:]
            self.observations, self.outcomes = self.observations[removed:], self.outcomes[removed:]
        self.bodies.append((start, end, np.asarray(gyro, dtype=float).copy(), np.asarray(force, dtype=float).copy()))
        self.current = candidate
        return 0

    def _observe(self, event, kind, args):
        if not self._sequence_history_valid():
            return 11
        if not isinstance(event, Event) or not isinstance(event.identity,Identity):
            return 1
        if kind not in self.current.ledgers:
            return 14 if kind == "magnetic" and self.current.model == "inekf15" else 2
        gate = args[-1]
        if (not unsigned(event.sample_us, 64) or not unsigned(event.receive_us, 64)
                or not unsigned(event.sequence, 32) or type(event.trusted) is not int
                or event.trusted not in (0, 1) or type(gate) not in (int, float)
                or not math.isfinite(gate) or gate <= 0):
            return 1
        if event.identity != self.current.ledgers[kind].identity:
            return 2
        if event.trusted != 1:
            return 3
        if event.sample_us > event.receive_us:
            return 1
        if max(event.sample_us, event.receive_us) > self.state_us:
            return 4
        if event.sample_us <= self.anchor.state_us or self.state_us-event.sample_us > self.maximum_delay_us:
            return 15
        if any(row[1] == kind and row[0].sequence == event.sequence for row in self.observations):
            return 6
        previous = self.anchor.ledgers[kind].last_sequence
        successor = None
        for prior, group, _ in self.observations:
            if group != kind:
                continue
            if prior.sample_us == event.sample_us:
                return 7
            if prior.sample_us < event.sample_us:
                previous = prior.sequence
            else:
                successor = prior.sequence
                break
        if previous is not None:
            step = (event.sequence-previous) % 2**32
            if step == 0:
                return 6
            if step >= 2**31:
                return 7
        if successor is not None and not 0 < (successor-event.sequence) % 2**32 < 2**31:
            return 7
        if len(self.observations) == OBSERVATION_CAPACITY:
            return 16
        insertion = bisect_right([row[0].sample_us for row in self.observations], event.sample_us)
        proposed = self.observations.copy()
        proposed.insert(insertion, copy.deepcopy((event, kind, args)))
        code, candidate, outcomes = self._run(self.bodies, proposed)
        if code:
            return code
        self.current, self.observations, self.outcomes = candidate, proposed, outcomes
        return outcomes[insertion]

    def update_vector(self, event, kind, measured, covariance, gate):
        return self._observe(event, kind, (measured, covariance, gate))

    def update_magnetic(self, event, sensor, covariance, stage, bias, soft, reference, bounds, gate):
        if self.current.model == "inekf15":
            return 14
        return self._observe(event, "magnetic", (sensor, covariance, stage, bias, soft, reference, bounds, gate))

    def counts_get(self):
        accepted, rejected = self.retired_accepted.copy(), self.retired_rejected.copy()
        for row, code in zip(self.observations, self.outcomes):
            group = ("position", "velocity", "magnetic").index(row[1])
            (accepted if code == 0 else rejected)[group] += 1
        return accepted, rejected
