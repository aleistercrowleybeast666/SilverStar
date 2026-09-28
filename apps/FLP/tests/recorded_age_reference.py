"""Headless recorded-age A/B reference; not a production scheduling override."""

from dataclasses import replace


def RecordedAgeSchedule_Build(dataset, increments, baseline):
    endpoints = {item.interval_end_timestamp_us for item in increments}
    candidates = {}
    for state in dataset.Records_Get("ESTIMATOR"):
        for kind in ("gnss", "baro"):
            keys = tuple(
                kind + suffix for suffix in ("_sequence", "_timestamp_us", "_measurement_age_us")
            )
            if not all(key in state.payload for key in keys):
                continue
            sequence, sample, age = (state.payload[key] for key in keys)
            if not all(
                isinstance(v, int) and not isinstance(v, bool) for v in (sequence, sample, age)
            ):
                continue
            # UINT32_MAX represents a saturated age, not an exact duration.
            if sequence <= 0 or sample < 0 or not 0 <= age < 0xFFFFFFFF:
                continue
            application = sample + age
            if application <= state.timestamp_us:
                candidates.setdefault((kind, sequence, sample), set()).add(application)
    resolved = []
    for item in baseline:
        payload = item.record.payload
        times = candidates.get(
            (item.kind, payload["sequence"], payload["sample_timestamp_us"]), set()
        )
        if len(times) == 1:
            application = next(iter(times))
            if application in endpoints and application >= max(
                payload["sample_timestamp_us"], payload["receive_timestamp_us"]
            ):
                item = replace(item, application_timestamp_us=application, inferred=False)
        resolved.append(item)
    resolved.sort(
        key=lambda item: (
            item.application_timestamp_us,
            0 if item.kind == "gnss" else 1,
            item.source_order,
        )
    )
    return tuple(resolved), any(item.inferred for item in resolved)
