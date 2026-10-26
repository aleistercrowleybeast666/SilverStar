"""Explicit SS-TM decoding; only unchanged numeric bodies reuse M0 arithmetic."""
from dataclasses import replace
import sys
from pathlib import Path
try:
    import silverstar_telemetry
except ModuleNotFoundError as error:
    if error.name != 'silverstar_telemetry': raise
    # Fixed first-party location, never a log/project supplied import path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'SCG/src'))
from silverstar_telemetry.codec import Frame_Decode, Frame_Encode
from .air import AirFrame, AirAckMessage, AirStatusMessage, parse_air_frame


def TelemetryFrame_Parse(raw):
    frame = Frame_Decode(raw)
    view = AirFrame(frame.message_type, frame.sequence, raw[8:], raw)
    fields = frame.values
    if not frame.known or frame.message_type in (0x18, 0x19):
        return view, frame, frame
    if frame.message_type == 0x20:
        # New stage/function events have no legacy status interpretation.
        message = frame
        if 1 <= fields['event_code'] <= 13:
            message = AirStatusMessage(frame.sequence, fields['event_code'],
                (fields['occurred_us'] // 1000) & 0xFFFFFFFF, fields['arg0'], fields['arg1'])
    elif frame.message_type == 0x40:
        message = AirAckMessage(frame.sequence, fields['acked_sequence'], fields['command_id'],
                                fields['result'], fields['time_ms'])
    else:
        body = raw[8:15] if frame.message_type == 0x12 else raw[8:]
        # Wire selection already validated the common header/profile and exact
        # body length. The legacy parser is solely a numeric payload adapter.
        _, legacy = parse_air_frame(bytes((frame.message_type, 0)) + body)
        message = replace(legacy, seq=frame.sequence)
    return view, message, frame


def TelemetryCommand_Build(profile, session, sequence, command, token, param0=0, param1=0):
    return Frame_Encode(profile, 'CMD', sequence, session, dict(command_id=command,
        token=token, param0=param0, param1=param1))
