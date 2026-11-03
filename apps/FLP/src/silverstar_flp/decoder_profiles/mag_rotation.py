"""Interpret rotation words only when the matched package declares their encoding."""
from __future__ import annotations

import math
from collections.abc import Mapping


_ROTATIONS = {
    0x32: 'MAG_ROTATION_BASE', 0x33: 'MAG_ROTATION_ESTIMATE',
    0x34: 'MAG_ROTATION_ADOPTED', 0x35: 'MAG_ROTATION_FIXED',
}


def RotationEvent_FieldsGet(event_id: int, declaration: Mapping, arg0: int, arg1: int) -> dict:
    word = arg0 & 0xFFFFFFFF
    encoding = declaration.get('argument_encoding')
    name = declaration.get('name')
    if event_id == 0x36 and name == 'MAG_ROTATION_QUALITY' and encoding == 'mag_rotation_quality_v1':
        residual = (word >> 8) & 0xFFFF
        quality = word & 0xFF
        count = word >> 24
        relative = None if residual == 0xFFFF else residual / 10000.0
        codes = declaration.get('quality_codes')
        label = codes.get(str(quality)) if isinstance(codes, Mapping) else None
        quality_text = f'{quality} ({label})' if isinstance(label, str) and label else str(quality)
        return {'rotation_update_id': arg1 & 0xFFFFFFFF, 'rotation_quality_code': quality,
                'rotation_quality_label': label if isinstance(label, str) else None,
                'rotation_sample_count': count, 'rotation_relative_residual': relative,
                'rotation_display': f'Q={quality_text}  n={count}  residual={relative if relative is not None else "—"}'}
    if (event_id not in _ROTATIONS or name != _ROTATIONS[event_id] or
            encoding != 'hamilton_smallest3_s10_v1'):
        return {}
    largest = word >> 30
    values = []
    for shift in (0, 10, 20):
        code = (word >> shift) & 0x3FF
        if code == 0x200:
            return {'rotation_display': 'invalid q(wxyz)', 'rotation_encoding_valid': False}
        value = code - 1024 if code & 0x200 else code
        values.append(value / (511.0 * math.sqrt(2.0)))
    remaining = 1.0 - sum(value * value for value in values)
    if remaining < 0:
        return {'rotation_display': 'invalid q(wxyz)', 'rotation_encoding_valid': False}
    omitted = math.sqrt(remaining)
    # Rounding the three transmitted components can slightly change their order.
    if omitted + 4.0 / (511.0 * math.sqrt(2.0)) < max(abs(value) for value in values):
        return {'rotation_display': 'invalid q(wxyz)', 'rotation_encoding_valid': False}
    values.insert(largest, omitted)
    frame_from, frame_to = declaration.get('frame_from'), declaration.get('frame_to')
    frames = {}
    frame_text = ''
    if all(isinstance(value, str) and value for value in (frame_from, frame_to)):
        frames = {'rotation_frame_from': frame_from, 'rotation_frame_to': frame_to}
        frame_text = f'  {frame_from} → {frame_to}'
    return {'rotation_encoding_valid': True, 'rotation_update_id': arg1 & 0xFFFFFFFF,
            'rotation_q_wxyz': tuple(values), **frames,
            'rotation_display': 'q(wxyz) = (' + ', '.join(f'{value:.4f}' for value in values) + ')' + frame_text}
