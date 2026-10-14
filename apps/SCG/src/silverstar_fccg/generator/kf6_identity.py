"""Do not label preserved or edited KF6 kernels with a catalog-only revision."""
import hashlib
from pathlib import Path

COMPONENT = "silverstar.algorithm.estimator.kf6"
KERNEL_PATHS = (
    "Algorithm/Estimator/KF6/Inc/navigation_kf.h",
    "Algorithm/Estimator/KF6/Src/navigation_kf.c",
    "Algorithm/Estimator/KF6/Src/navigation_kf_replay.c",
)


def Kf6Identity_Validate(project_root: Path, previous: dict, current: dict) -> None:
    prior = previous.get("components", {}).get(COMPONENT, {}).get("files", {})
    if not prior:
        # A new project is assembled atomically from the owning payload.
        if any(project_root.joinpath(*path.split("/")).exists() for path in KERNEL_PATHS):
            raise ValueError("KF6 source model identity NOT PROVEN: existing kernel without ownership")
        return
    upstream = current["files"]
    for relative in KERNEL_PATHS:
        target = project_root.joinpath(*relative.split("/"))
        expected = prior.get(relative)
        if (expected != upstream.get(relative) or not target.is_file()
                or hashlib.sha256(target.read_bytes()).hexdigest() != expected):
            raise ValueError(
                "KF6 source model identity NOT PROVEN: preserved/edited kernel "
                f"{relative}; revision 2 requires a fresh separately named project. "
                "Existing user payload and decoder are not replaced."
            )


ESKF_COMPONENT = "silverstar.algorithm.estimator.eskf15"
ESKF_NIS_PATHS = (
    "Algorithm/Estimator/ESKF15/Inc/navigation_eskf.h",
    "Algorithm/Estimator/ESKF15/Inc/navigation_eskf_config.h",
    "Algorithm/Estimator/ESKF15/Src/navigation_eskf.c",
    "Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c",
)


def EskfNisIdentity_Validate(project_root: Path, previous: dict, current: dict) -> None:
    """Never describe preserved old ESKF payload as implementing new gate controls."""
    prior = previous.get("components", {}).get(ESKF_COMPONENT, {}).get("files", {})
    if not prior:
        if any(project_root.joinpath(*path.split("/")).exists() for path in ESKF_NIS_PATHS):
            raise ValueError("ESKF NIS contract NOT PROVEN: existing source without ownership")
        return
    for relative in ESKF_NIS_PATHS:
        target = project_root.joinpath(*relative.split("/"))
        expected = prior.get(relative)
        if (expected != current["files"].get(relative) or not target.is_file()
                or hashlib.sha256(target.read_bytes()).hexdigest() != expected):
            raise ValueError("ESKF NIS contract NOT PROVEN: preserved/edited payload "
                f"{relative}; use a fresh separately named project. User source is not replaced.")
