"""Compatibility entry point; runtime ownership moved to the GSHC backend."""
from pathlib import Path
import sys

_gshc = str(Path(__file__).resolve().parents[3]/"GSHC")
if _gshc not in sys.path:
    sys.path.insert(0,_gshc)

from services.installation_calibration_protocol import (
    REQUEST_BYTES, RESPONSE_BYTES, CHUNK_BYTES, ACTIONS, ROLES, ProtocolResult, ProtocolError, _decimal, Sid_Check, Context_Check, Request, Request_Decode, Request_Encode, Response, Response_Encode, Response_Decode, LineFramer, SamplePart_Encode, SamplePart_Decode, PairAssembler, _PART, _STAGES, _WIRE_FACES
)

from services.installation_calibration_protocol import Request_Decode as _Request_Decode, Request_Encode as _Request_Encode


def Request_Decode(body):
    return _Request_Decode(body,allow_draft=True)


def Request_Encode(request):
    return _Request_Encode(request,allow_draft=True)
