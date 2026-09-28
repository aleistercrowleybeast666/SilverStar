"""Public project exports, loaded on demand to avoid import cycles."""

from importlib import import_module

_EXPORT_MODULES = {
    "model": (
        "BuildOptions", "DeviceInstance", "HardwareConfiguration", "HardwareResource",
        "LogStreamConfig", "ProjectIdentity", "ProjectModel", "ProjectModel_Load",
        "ProjectModel_Save",
    ),
    "resources": (
        "BoardCompatibilityResult", "BoardCompatibility_Resolve",
        "ResourceAssignmentResult", "ResourceAssignments_Resolve",
    ),
    "lifecycle": (
        "BUILDABLE_MAKE_TARGETS", "ProjectLifecycleState", "ProjectReadiness",
        "ProjectReadiness_Inspect",
    ),
}

__all__ = [name for names in _EXPORT_MODULES.values() for name in names]


def __getattr__(name: str):
    for module, names in _EXPORT_MODULES.items():
        if name in names:
            return getattr(import_module(f"silverstar_fccg.project.{module}"), name)
    raise AttributeError(name)
