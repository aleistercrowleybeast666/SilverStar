"""Read optional SCG configuration from an already exact-opened decoder context."""
from collections.abc import Mapping
from pathlib import Path
import runpy
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[5]
_API = runpy.run_path(str(_ROOT / 'tools/silverstar_mission_profile.py'))


def _Value_Thaw(value, depth=0):
    if depth > 12:
        raise ValueError('mission_profile_depth')
    if isinstance(value, Mapping):
        return {key: _Value_Thaw(item, depth+1) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_Value_Thaw(item, depth+1) for item in value]
    return value


def MissionProfile_FromDataset(dataset):
    context = dataset.semantic_context
    if context is None:
        return None
    declaration = context.raw_metadata.get('metadata_declarations', {}).get('mission_profile')
    if declaration is None:
        return None
    if not dataset.metadata.get('parse_identity') or not dataset.metadata.get('source_log_sha256'):
        raise ValueError('mission_profile_exact_open_required')
    return _API['MissionProfile_Require'](_Value_Thaw(declaration))
