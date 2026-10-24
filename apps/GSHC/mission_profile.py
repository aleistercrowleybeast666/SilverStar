"""Offline declared configuration reader; never changes telemetry authority."""
from pathlib import Path
import runpy
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
_API = runpy.run_path(str(_ROOT / 'tools/silverstar_mission_profile.py'))
MissionProfile_Read = _API['MissionProfile_Read']
MissionTrace_Read = _API['MissionTrace_Read']
