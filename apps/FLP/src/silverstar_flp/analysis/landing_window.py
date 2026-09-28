"""Independent landing reconstruction from corrected IMU and barometer observations.

Uses recorded thresholds and time coverage. FlightTask evaluation ticks are not
logged, so this is explicitly APPROXIMATE even when every observation is present.
"""
from dataclasses import dataclass
from itertools import groupby

import numpy as np


@dataclass
class ImuTimeWindow:
    start: int
    last: int
    valid: int = 0
    still: int = 0
    bad: int = 0
    maximum_bad: int = 0
    last_good: int = 0
    previous_valid: bool = False
    previous_still: bool = False

    def Sample_Add(self, timestamp, valid, still):
        dt = timestamp - self.last
        if dt <= 0:
            return False
        covered = dt if dt <= 20000 and valid and self.previous_valid else 0
        self.valid += covered
        if covered and still and self.previous_still:
            self.still += covered
            self.bad = 0
        else:
            self.bad += dt
        self.maximum_bad = max(self.maximum_bad, self.bad)
        if valid and still:
            self.last_good = timestamp
        self.last = timestamp
        self.previous_valid, self.previous_still = valid, valid and still
        return True

    def Accepted_Get(self, duration):
        elapsed = self.last - self.start
        return (elapsed >= duration and self.valid * 100 >= elapsed * 90
                and self.still * 100 >= self.valid * 95 and self.maximum_bad <= 200000
                and self.previous_still and self.last - self.last_good <= 20000)


def _Regression_Get(points):
    times = np.array([item[0] - points[0][0] for item in points], dtype=float) * 1e-6
    values = np.array([item[1] for item in points], dtype=float)
    centered = times - np.mean(times)
    denominator = np.sum(centered ** 2)
    if len(points) < 2 or denominator <= 0:
        return float('nan'), float('nan')
    return float(np.float32(np.sum(centered * (values - np.mean(values))) / denominator)), float(
        np.ptp(values)
    )


def LandingWindow_Replay(dataset, config, recovery_start, context=None):
    required = ('baro_trigger_window_ms', 'baro_trigger_min_samples', 'baro_trigger_rate_mps',
                'candidate_duration_ms', 'baro_confirm_rate_mps', 'baro_max_span_m',
                'candidate_baro_min_samples', 'candidate_min_coverage_percent',
                'still_gyro_threshold_radps', 'still_accel_tolerance_mps2',
                'landing_sample_max_age_ms')
    if any(key not in config for key in required) or 'gravity_mps2' not in dataset.header:
        return None, 'landing_configuration_incomplete', {}
    baro = dataset.Records_Get('BARO_NATIVE')
    imu = dataset.Records_Get('IMU_CORRECTED')
    if not baro or not imu:
        return None, 'barometer_or_corrected_imu_missing', {}
    # Reject ambiguous observations rather than mixing physical sources.
    if (
        len({(r.payload.get("source_descriptor_id"), r.payload.get("instance_id")) for r in baro})
        > 1
    ):
        return None, 'landing_barometer_source_ambiguous', {}
    timeline = sorted(
        (
            (int(r.payload["receive_timestamp_us"]), kind, r)
            for kind, records in ((0, baro), (1, imu))
            for r in records
            if int(r.payload["receive_timestamp_us"]) >= recovery_start
        ),
        key=lambda item: item[:2],
    )
    trigger, candidate, transitions = [], [], []
    window = None
    coverage = 0
    latest = [None, None]
    maximum_age = int(config['landing_sample_max_age_ms']) * 1000
    duration = int(config['candidate_duration_ms']) * 1000
    gravity = np.float32(dataset.header['gravity_mps2'])

    def transition(now, code, reason=0, slope=0.0, span=0.0):
        elapsed = window.last - window.start if window else 0
        transitions.append(
            dict(
                evaluation_timestamp_us=now,
                transition=code,
                reset_reason=reason,
                candidate_start_timestamp_us=window.start if window else 0,
                candidate_elapsed_us=elapsed,
                valid_coverage=window.valid / elapsed if elapsed else 0,
                still_ratio=window.still / window.valid if window and window.valid else 0,
                maximum_bad_duration_us=window.maximum_bad if window else 0,
                baro_slope_mps=slope,
                baro_span_m=span,
                baro_coverage=coverage / elapsed if elapsed else 0,
            )
        )

    for iteration, (now, arrivals) in enumerate(groupby(timeline, key=lambda item: item[0])):
        if context is not None and iteration % 128 == 0:
            context.Progress_Report(iteration / max(1, len(timeline)), "replay.inputs")
        changed = set()
        for _, kind, record in arrivals:
            latest[kind] = record.payload
            changed.add(kind)
        b, i = latest
        bt = int(b['sample_timestamp_us']) if b else 0
        it = int(i['sample_timestamp_us']) if i else 0
        bvalid = bool(b and b.get('healthy') and int(b.get('valid_mask', 0))
                      and 0 <= now - bt <= maximum_age and np.isfinite(b['altitude_m']))
        if window is None:
            if 0 not in changed:
                continue
            if not bvalid or (trigger and bt <= trigger[-1][0]):
                trigger = []
                continue
            trigger.append((bt, b['altitude_m']))
            if bt - trigger[0][0] < int(config['baro_trigger_window_ms']) * 1000:
                continue
            slope, span = _Regression_Get(trigger)
            ready = (
                len(trigger) >= int(config["baro_trigger_min_samples"])
                and abs(slope) < config["baro_trigger_rate_mps"]
            )
            trigger = []
            if ready:
                window = ImuTimeWindow(bt, bt)
                candidate, coverage = [], 0
                transition(now, 1)
            continue
        previous_baro = candidate[-1][0] if candidate else window.start
        reason = 0
        if not bvalid and now - previous_baro > maximum_age:
            reason = 5
        elif not i or now - it > maximum_age:
            reason = 1
        if not reason and 0 in changed and bvalid:
            if bt <= previous_baro:
                reason = 9
            else:
                coverage += bt - previous_baro if bt - previous_baro <= maximum_age else 0
                candidate.append((bt, b['altitude_m']))
        if not reason and 1 in changed:
            valid = (it > window.start and 0 <= now - it <= maximum_age
                     and bool(i.get('correction_valid')) and int(i.get('valid_mask', 0)) & 3 == 3)
            acceleration = np.asarray(i['accel_b_mps2'], dtype=np.float32)
            gyro = np.asarray(i['gyro_b_radps'], dtype=np.float32)
            valid = bool(valid and np.isfinite(acceleration).all() and np.isfinite(gyro).all())
            still = bool(
                valid
                and np.linalg.norm(gyro) < config["still_gyro_threshold_radps"]
                and abs(np.linalg.norm(acceleration) - gravity)
                < config["still_accel_tolerance_mps2"]
            )
            if not window.Sample_Add(it, valid, still):
                reason = 9
            elif window.maximum_bad > 200000:
                reason = 3
        if reason:
            transition(now, 2, reason)
            window, trigger, candidate = None, [], []
            continue
        if (not candidate or not window.valid or not bvalid or now - window.last_good > 20000
                or min(candidate[-1][0], window.last) - window.start < duration):
            continue
        minimum = duration * config['candidate_min_coverage_percent'] / 100
        slope, span = _Regression_Get(candidate)
        if coverage < minimum:
            reason = 6
        elif (
            not window.Accepted_Get(duration)
            or len(candidate) < config["candidate_baro_min_samples"]
        ):
            reason = 2
        elif (
            not abs(slope) < config["baro_confirm_rate_mps"] or not span < config["baro_max_span_m"]
        ):
            reason = 8 if span > config['baro_max_span_m'] else 7
        transition(now, 2 if reason else 3, reason, slope, span)
        if not reason:
            return (
                now,
                "baro_imu_candidate_confirmed",
                {"transitions": transitions, "fidelity": "APPROXIMATE"},
            )
        window, trigger, candidate = None, [], []
    return (
        None,
        "no_landing_candidate_confirmed",
        {"transitions": transitions, "fidelity": "APPROXIMATE"},
    )


def LandingReplay_Run(dataset, context):
    configs = dataset.Records_Get("MISSION_CONFIG")
    deploy = next((r.timestamp_us for r in dataset.Records_Get("EVENT")
                   if r.payload.get("event_id") == 0x29), None)
    if not configs or deploy is None:
        return {"transitions": [], "reason": "landing_inputs_missing"}
    if not configs[0].payload.get("landing_enable") or configs[0].payload.get("landing_mode") != 2:
        return {"transitions": [], "reason": "landing_mode_unavailable"}
    _, reason, diagnostics = LandingWindow_Replay(dataset, configs[0].payload, deploy, context)
    context.Progress_Report(1.0, "replay.complete")
    return {"transitions": diagnostics.get("transitions", []), "reason": reason}
