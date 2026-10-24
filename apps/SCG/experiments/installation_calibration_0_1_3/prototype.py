"""Compatibility entry point; runtime ownership moved to the GSHC backend."""
from pathlib import Path
import sys

_gshc = str(Path(__file__).resolve().parents[3]/"GSHC")
if _gshc not in sys.path:
    sys.path.insert(0,_gshc)

from services.installation_calibration_fit import (
    CandidateResult, IntrinsicFitResult, FACES, FACE_AXES, MAX_RECORDS, IDENTITY, SensorIdentity, Intrinsic, Convention, RawPair, Policy, Candidate, CandidateReport, Geometry_Evaluate, Rotation_DistanceDeg, Supplement_Suggest, InstallationSession, ImuSixFace_Fit, MagEllipsoid_Fit, Snapshot_Export, Snapshot_Import, _matrix, _digest, _uint, _number
)
