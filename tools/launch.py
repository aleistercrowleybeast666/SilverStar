"""Locate a migrated application without changing the user's working directory."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def Application_Start(name: str) -> int:
    application_root = Path(__file__).resolve().parents[1] / "apps" / name
    sys.path.insert(0, str(application_root))
    try:
        runpy.run_path(str(application_root / "main.py"), run_name="__main__")
    except SystemExit as result:
        return int(result.code or 0)
    return 0
