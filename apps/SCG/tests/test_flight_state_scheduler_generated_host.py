from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture(scope="module")
def flight_scheduler_executable(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    configured = os.environ.get("SILVERSTAR_RADIO_GENERATED_PROJECT")
    if configured:
        project = Path(configured).resolve()
    else:
        from silverstar_fccg.app.service import FccgService
        service = FccgService(root)
        model = service.Project_Open(root / "tests/fixtures/radio_handshake.ssproject")
        project = tmp_path_factory.mktemp("flight-scheduler-generated") / "Flight_Controller"
        service.Project_Save(model, project, confirm_dangerous=True)
    executable = tmp_path_factory.mktemp("flight-scheduler-build") / "scheduler.exe"
    includes = [p for p in project.rglob("Inc") if "build" not in p.parts]
    includes += [project / p for p in ["System/User", "Tests/Host",
        "Devices/Telemetry/SX1281/Src", "Modules/Src", "Middlewares/Third_Party/SX1280lib"]]
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
        "-DSILVERSTAR_AIR_LINK_ENABLED=1",
        "-include", str(project / "Generated/Inc/project_flight_config.h")]
    for include in includes:
        command.extend(["-I", str(include)])
    command += [str(root / "tests/fixtures/flight_state_scheduler_host.c")]
    command += [str(project / p) for p in [
        "Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c",
        "Generated/Src/project_resources.c", "Protocol/Src/air_protocol.c",
        "Common/Src/silverstar_assert.c", "System/Calibration/Src/system_calibration_correction.c"]]
    command += ["-lm", "-o", str(executable)]
    result = subprocess.run(command, cwd=project, capture_output=True, text=True,
                            encoding="utf8", errors="replace", timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable, project


@pytest.mark.parametrize("scenario", ["contended", "no_navigation", "unavailable",
    "no_imu", "recovery", "outside_mission"])
def test_generated_flight_scheduler(flight_scheduler_executable, scenario):
    executable, project = flight_scheduler_executable
    result = subprocess.run([str(executable), scenario], cwd=project, capture_output=True,
                            text=True, encoding="utf8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failures" in result.stdout
    if scenario == "contended":
        # Use the actual generated C payload bytes in the unchanged GSHC parser.
        import struct
        import sys
        gshc = Path(__file__).resolve().parents[2] / "GSHC"
        sys.path.insert(0, str(gshc))
        try:
            from protocol.air import AirFlightStateMessage, parse_air_frame
            frames = [bytes.fromhex(line.split()[1]) for line in result.stdout.splitlines()
                      if line.startswith("FLIGHT_HEX ")]
            assert frames
            for frame in frames:
                _, message = parse_air_frame(frame)
                assert isinstance(message, AirFlightStateMessage)
                assert len(frame) == 50
                assert struct.unpack_from("<ffffff", frame, 26) == pytest.approx(
                    [-0.0981511548, 0.0991782993, 0.0932015106,
                     -0.467806935, 0.483857244, 0.072262131])
        finally:
            sys.path.remove(str(gshc))
