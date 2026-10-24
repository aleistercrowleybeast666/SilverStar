"""Trusted shared process contract; no GUI and no device I/O."""
from pathlib import Path
import runpy
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[5]
_API = runpy.run_path(str(_ROOT / 'tools/silverstar_mission_process.py'))
MissionProcess_Default = _API['MissionProcess_Default']
MissionProcess_Require = _API['MissionProcess_Require']
MissionProcessRunner = _API['MissionProcessRunner']
SIGNALS = _API['SIGNALS']
EVENTS = _API['EVENTS']
ACTIONS = _API['ACTIONS']
