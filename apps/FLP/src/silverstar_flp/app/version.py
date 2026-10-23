"""Authoritative SilverStar_FLP product identity and application version."""

import runpy
import sys
from pathlib import Path

_VERSION_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[5]
_VERSION_API = runpy.run_path(str(_VERSION_ROOT / "tools/silverstar_version.py"))
_RELEASE = _VERSION_API["ReleaseIdentity_Load"](_VERSION_ROOT)

PRODUCT_NAME = "SilverStar FLP"
__version__ = _RELEASE.full

__package_version__ = _RELEASE.package

__all__ = ["PRODUCT_NAME", "__version__"]
