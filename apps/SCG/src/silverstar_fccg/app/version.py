"""Authoritative SilverStar platform and SCG product identity."""

import runpy
import sys
from pathlib import Path

_VERSION_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[5]
_VERSION_API = runpy.run_path(str(_VERSION_ROOT / "tools/silverstar_version.py"))
_RELEASE = _VERSION_API["ReleaseIdentity_Load"](_VERSION_ROOT)

PRODUCT_NAME = "SilverStar SCG"
SILVERSTAR_PLATFORM_VERSION = _RELEASE.full

_VERSION_PARTS = tuple(
    part for part in _RELEASE.numeric
)
if len(_VERSION_PARTS) != 3:
    raise RuntimeError("SilverStar platform version must have three numeric parts")

SILVERSTAR_PLATFORM_VERSION_MAJOR = _VERSION_PARTS[0]
SILVERSTAR_PLATFORM_VERSION_MINOR = _VERSION_PARTS[1]
SILVERSTAR_PLATFORM_VERSION_PATCH = _VERSION_PARTS[2]
SILVERSTAR_PLATFORM_ID_SUFFIX = _RELEASE.artifact_suffix
SILVERSTAR_BUILD_ID = f"SilverStar_{SILVERSTAR_PLATFORM_ID_SUFFIX}"
# The installed core plugin has its own schema/payload version.
SILVERSTAR_CORE_COMPONENT_ID = "silverstar.core.0_1_0"
SILVERSTAR_CORE_PACKAGE_SLUG = SILVERSTAR_CORE_COMPONENT_ID.replace(".", "_")
SILVERSTAR_LOG_BUILD_TAG = _RELEASE.firmware_tag
# Profile identity is a wire compatibility value, independent of the product release.
SILVERSTAR_SYSTEM_PROFILE_ID = 0x0000000C

__version__ = SILVERSTAR_PLATFORM_VERSION
__package_version__ = _RELEASE.package
FirmwareIdentity_Resolve = _VERSION_API["FirmwareIdentity_Resolve"]
ProductVersion_Parse = _VERSION_API["ProductVersion_Parse"]

__all__ = [
    "PRODUCT_NAME",
    "SILVERSTAR_BUILD_ID",
    "SILVERSTAR_CORE_COMPONENT_ID",
    "SILVERSTAR_CORE_PACKAGE_SLUG",
    "SILVERSTAR_LOG_BUILD_TAG",
    "SILVERSTAR_PLATFORM_ID_SUFFIX",
    "SILVERSTAR_PLATFORM_VERSION",
    "SILVERSTAR_PLATFORM_VERSION_MAJOR",
    "SILVERSTAR_PLATFORM_VERSION_MINOR",
    "SILVERSTAR_PLATFORM_VERSION_PATCH",
    "SILVERSTAR_SYSTEM_PROFILE_ID",
    "__version__",
]
