from pathlib import Path

import pytest

from test_joint_sensor_library import _Command_Run, _Compiler_Get

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "plugins/builtin/silverstar_core_ground_0_1_0/payload"
COMMON = ROOT / "plugins/builtin/silverstar_core_0_1_0/payload/Common"
SCENARIOS = ("idle", "burst", "radio", "mixed", "slow", "sessions", "queued-reset", "budget", "error", "error-reset")


@pytest.fixture(scope="module")
def backpressure_executable(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("uart_contract")
    sources = [PAYLOAD / name for name in (
        "Ground/Core/Src/ground_bridge.c", "Ground/Protocol/Src/gsp_min_protocol.c",
        "Ground/Protocol/Src/protocol_crc16.c", "Tests/Host/ground_backpressure.c")]
    executable = tmp_path / "backpressure.exe"
    includes = (tmp_path, PAYLOAD / "Ground/Core/Inc", PAYLOAD / "Ground/Protocol/Inc", COMMON / "Inc")
    _Command_Run([_Compiler_Get(), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                  "-Wconversion", "-Wsign-conversion", "-Wshadow", "-Wvla",
                  *["-I" + str(p) for p in includes], *map(str, sources), "-o", str(executable)],
                 tmp_path, "compile")
    return executable


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_ground_backpressure_recovers_without_lost_ack(backpressure_executable, scenario, tmp_path):
    _Command_Run([str(backpressure_executable), scenario], tmp_path, scenario)
