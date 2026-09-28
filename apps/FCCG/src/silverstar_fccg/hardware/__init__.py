"""Trusted hardware import and reusable Board plugin services."""

from silverstar_fccg.hardware.board_plugin import BoardPluginExporter
from silverstar_fccg.hardware.cubemx import (
    CubeMxImportError,
    CubeMxImportResult,
    CubeMxImporter,
)
from silverstar_fccg.hardware.platform import (
    DetectedMcuFacts,
    DetectedMcuFacts_FromInventory,
    PlatformCandidate,
    PlatformMatchError,
    PlatformMatchResult,
    PlatformMatch_Resolve,
    PlatformCompatibilityErrors_Get,
)

__all__ = [
    "BoardPluginExporter",
    "CubeMxImportError",
    "CubeMxImportResult",
    "CubeMxImporter",
    "DetectedMcuFacts",
    "DetectedMcuFacts_FromInventory",
    "PlatformCandidate",
    "PlatformMatchError",
    "PlatformMatchResult",
    "PlatformMatch_Resolve",
    "PlatformCompatibilityErrors_Get",
]
