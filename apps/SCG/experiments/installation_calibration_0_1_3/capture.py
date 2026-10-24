"""Compatibility entry point; runtime ownership moved to the GSHC backend."""
from pathlib import Path
import sys

_gshc = str(Path(__file__).resolve().parents[3]/"GSHC")
if _gshc not in sys.path:
    sys.path.insert(0,_gshc)

from services.installation_calibration_data import (
    CaptureResult, Token_Check, SourceDescriptor, SourceSample, WindowTag, CapturePolicy, CapturedPair, BoundedCollector, ReplayArchive, Archive_Import
)
