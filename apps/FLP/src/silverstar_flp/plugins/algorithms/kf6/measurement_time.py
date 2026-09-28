"""What-if delay resolution on the existing MCU time axis (no clock estimator)."""
from dataclasses import replace


def MeasurementTime_Resolve(receive_us, sample_us, trusted, delay_ms, present_us):
    if trusted:
        return int(sample_us)
    if delay_ms == 0:
        return int(present_us)
    timestamp = int(receive_us) - int(delay_ms) * 1000
    if timestamp < 0:
        raise ValueError("measurement_delay_precedes_clock_origin")
    return timestamp


def MeasurementDelays_Apply(dataset, schedule, parameters, recorded):
    names = ("gnss_position_measurement_delay_ms", "gnss_velocity_measurement_delay_ms",
             "baro_measurement_delay_ms")
    changed = {name for name in names if parameters.get(name) != recorded.get(name)}
    if not changed:
        return schedule
    observations = {}
    for record in dataset.Records_Get("GNSS_NATIVE"):
        key = (record.payload["sequence"], record.payload["receive_timestamp_us"])
        observations.setdefault(key, []).append(record)
    result = []
    for item in schedule:
        p = dict(item.record.payload)
        gnss = item.record.record_name == "GNSS_MEASUREMENT"
        relevant = changed.intersection(names[:2] if gnss else names[2:])
        if not relevant:
            result.append(item)
            continue
        if gnss:
            candidates = observations.get((p["sequence"], p["receive_timestamp_us"]), ())
            if len(candidates) != 1:
                raise ValueError("measurement_timestamp_trust_evidence_missing")
            trusted = candidates[0].payload["measurement_timestamp_trusted"]
        else:
            trusted = p["measurement_timestamp_trusted"]
        for name in relevant:
            field = ("position_measurement_timestamp_us" if name == names[0] else
                     "velocity_measurement_timestamp_us" if name == names[1] else
                     "measurement_timestamp_us")
            p[field] = MeasurementTime_Resolve(p["receive_timestamp_us"],
                p["sample_timestamp_us"], trusted, parameters[name],
                p["estimator_present_timestamp_us"])
        result.append(replace(item, record=replace(item.record, payload=p)))
    return tuple(result)
