import runpy
from pathlib import Path, PureWindowsPath

import pytest

ROOT = Path(__file__).resolve().parents[2]
DestinationPaths_Validate = runpy.run_path(
    str(ROOT / "tools/packaging/path_limits.py")
)["DestinationPaths_Validate"]
ALIGNMENT_HEADER = (
    "apps/SCG/plugins/builtin/silverstar_algorithm_alignment_hardware_quat_6axis_known_yaw/"
    "payload/Algorithm/Alignment/HardwareQuat6AxisKnownYaw/Inc/alignment_strategy_binding.h"
)


def test_actual_failed_collection_path_is_rejected_before_copying():
    directory = PureWindowsPath(
        "D:/python_software/SilverStar/dist/gui-convergence-20261111-fit-final/SilverStar/_internal"
    )
    assert len(str(directory / ALIGNMENT_HEADER)) == 263
    with pytest.raises(RuntimeError, match=r"263 UTF-16.*shorter --distpath"):
        DestinationPaths_Validate(directory, [ALIGNMENT_HEADER], windows=True)


def test_same_resource_under_short_collection_root_is_allowed():
    directory = PureWindowsPath("D:/python_software/SilverStar/dist/gcf1111/SilverStar/_internal")
    assert len(str(directory / ALIGNMENT_HEADER)) == 236
    DestinationPaths_Validate(directory, [ALIGNMENT_HEADER], windows=True)


@pytest.mark.parametrize("units,allowed", [(259, True), (260, False)])
@pytest.mark.parametrize("tail", ["a", "\U0001f680"])
def test_windows_limit_counts_utf16_and_reserves_nul(units, allowed, tail):
    directory = PureWindowsPath("C:/out")
    tail_units = len(tail.encode("utf-16-le")) // 2
    name = "x" * (units - len(str(directory)) - 1 - tail_units) + tail
    if allowed:
        DestinationPaths_Validate(directory, [name], windows=True)
    else:
        with pytest.raises(RuntimeError, match=r"260 UTF-16"):
            DestinationPaths_Validate(directory, [name], windows=True)


def test_dependency_destinations_are_checked_after_short_entries():
    with pytest.raises(RuntimeError, match=r"shorter --distpath"):
        DestinationPaths_Validate(
            "C:/out", iter(["short.dll", "vendor/" + "x" * 250 + ".dll"]), windows=True
        )


def test_windows_limit_does_not_restrict_other_platforms():
    DestinationPaths_Validate("/opt/package", ["x" * 300], windows=False)
