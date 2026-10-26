"""Shared, declarative SS-TM 0.1 wire contract. No Qt or transport dependencies."""
from .codec import CONTRACT, Frame, TelemetryProtocolError, Frame_Decode, Frame_Encode

__all__ = ['CONTRACT', 'Frame', 'TelemetryProtocolError', 'Frame_Decode', 'Frame_Encode']
