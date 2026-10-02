"""Distinguish absent GNSS from an admitted observation lacking its evidence."""

from dataclasses import replace


def GnssUnavailableSchedule_Get(dataset, schedule, revision):
    """Return an explicit no-GNSS schedule, or None for normal quality evaluation."""
    from silverstar_flp.plugins.algorithms.eskf15.plugin import Native_PhysicalMask

    initial = dataset.initial_state
    origin_valid = initial is not None and bool(int(initial.payload.get('origin_valid_flags', 0)) & 1)
    natives = tuple(dataset.Records_Get('GNSS_NATIVE'))
    def mask(payload):
        if revision == 3:
            return Native_PhysicalMask(payload)
        return int(payload.get('valid_group_mask',
            (3 if payload.get('position_usable') else 0) |
            (4 if int(payload.get('velocity_valid_mask', 0)) & 3 == 3 else 0))) & 15
    if any(mask(record.payload) for record in natives):
        if not origin_valid:
            raise ValueError('gnss_origin_unavailable')
        return None
    native_keys = {(int(r.payload['sequence']), int(r.payload['receive_timestamp_us']))
                   for r in natives}
    output, excluded = [], 0
    for item in schedule:
        if item.kind != 'gnss':
            output.append(item)
            continue
        payload = dict(item.record.payload)
        admitted = int(payload.get('valid_group_mask',
            (3 if payload.get('position_usable') else 0) |
            (4 if int(payload.get('velocity_valid_mask', 0)) & 3 == 3 else 0))) & 15
        if admitted:
            key = (int(payload['sequence']), int(payload['receive_timestamp_us']))
            if key not in native_keys:
                raise ValueError('gnss_integrity_native_evidence_missing')
            raise ValueError('gnss_physical_evidence_contradiction')
        # Retain operation identity/timing but exclude the invalid observation.
        payload.update(fusion_allowed=0, valid_group_mask=0,
                       _integrity_native_valid_group_mask=0)
        output.append(replace(item, record=replace(item.record, payload=payload)))
        excluded += 1
    return tuple(output), {
        'revision': revision, 'gnss_available': False,
        'gnss_unavailable_reason': 'native_evidence_absent' if not natives else 'native_no_valid_groups',
        'gnss_origin_available': origin_valid, 'gnss_native_count': len(natives),
        'gnss_excluded_operation_count': excluded,
        'window_evidence': [], 'position_disabled_count': 0,
        'native_epoch_unavailable': not bool(natives), 'window_reset_count': 0,
        'consistency_role': 'unavailable_no_gnss_observation',
        'position_operation_missing_count': 0,
        'state_counts': (0, 0, 0), 'transitions': (),
        'recorded_mask_mismatches': 0, 'recorded_r_mismatches': 0,
    }
