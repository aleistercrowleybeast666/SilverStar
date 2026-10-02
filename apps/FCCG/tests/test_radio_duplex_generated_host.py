from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


@pytest.fixture(scope="module")
def radio_duplex_executable(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    from silverstar_fccg.app.service import FccgService
    service = FccgService(root)
    flight = os.environ.get("SILVERSTAR_RADIO_GENERATED_PROJECT")
    ground = os.environ.get("SILVERSTAR_RADIO_GROUND_PROJECT")
    if flight:
        flight = Path(flight).resolve()
    else:
        model = service.Project_Open(root / "tests/fixtures/radio_handshake.ssproject")
        flight = tmp_path_factory.mktemp("duplex-flight") / "Flight_Controller"
        service.Project_Save(model, flight, confirm_dangerous=True)
    if ground:
        ground = Path(ground).resolve()
    else:
        from test_f103_ground_reference import _GroundF103Model_Get
        from silverstar_fccg.core.workspace import WorkspacePolicy
        from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
        model = _GroundF103Model_Get(service.catalog)
        directory = tmp_path_factory.mktemp("duplex-ground")
        result = TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(root),
                                        directory, TargetScope.GROUND)
        ground = result.project_root / "Ground_Station"
    build = tmp_path_factory.mktemp("duplex-build")
    records = []
    def compile_run(command):
        result = subprocess.run(command, cwd=build, capture_output=True, text=True,
                                encoding="utf8", errors="replace", timeout=90)
        records.append({"command": command, "cwd": str(build), "exit_code": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
        (build / "compile-record.json").write_text(json.dumps(records, indent=2), encoding="utf8")
        assert result.returncode == 0, result.stdout + result.stderr
    def flags(project):
        includes = [p for p in project.rglob("Inc") if "build" not in p.parts]
        includes += [flight / "Tests/Host", project / "Devices/Telemetry/SX1281/Src",
                     project / "Middlewares/Third_Party/SX1280lib"]
        command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
                   "-ffunction-sections", "-fdata-sections", "-DSILVERSTAR_AIR_LINK_ENABLED=1"]
        for include in includes:
            command.extend(["-I", str(include)])
        return command
    source = ground / "Devices/Telemetry/SX1281/Src/sx1281_device.c"
    aliases = [f"-D{name}=Ground_{name}" for name in sorted(set(re.findall(
        r"\bLora_\w+", source.read_text(encoding="utf8"))))]
    ground_object = build / "ground-radio.o"
    adapter_object = build / "ground-adapter.o"
    compile_run(flags(ground) + aliases + ["-c", str(source), "-o", str(ground_object)])
    adapter = ground / "Ground/Radio/Src/ground_radio_sx1281.c"
    compile_run(flags(ground) + aliases + ["-c", str(adapter), "-o", str(adapter_object)])
    executable = build / "duplex.exe"
    fixture = root / "tests/fixtures/radio_duplex_host.c"
    compile_run(flags(flight) + ["-I", str(ground / "Ground/Core/Inc"),
        "-include", str(flight / "Generated/Inc/project_flight_config.h"),
        str(fixture), str(ground_object), str(adapter_object),
        str(flight / "Generated/Src/project_resources.c"),
        str(flight / "Common/Src/silverstar_assert.c"), "-lm", "-Wl,--gc-sections", "-o", str(executable)])
    files = [source, adapter, fixture, flight / "Devices/Telemetry/SX1281/Src/sx1281_device.c",
             ground / "Generated/Inc/air_link_config.h", flight / "Generated/Inc/air_link_config.h", executable]
    (build / "source-hashes.json").write_text(json.dumps({str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                                         for path in files}, indent=2), encoding="utf8")
    return executable, build


@pytest.mark.parametrize("scenario", ["phase_scan", "boundary", "queue_no_peer", "noise_lost_tx",
                                     "startup_full_stream", "rx_errors", "airtime_profiles", "spi_read_failures", "spi_command_failures", "owner_jitter"])
def test_generated_duplex_radio(radio_duplex_executable, scenario):
    executable, build = radio_duplex_executable
    result = subprocess.run([str(executable), scenario], cwd=build, capture_output=True,
                            text=True, encoding="utf8", errors="replace", timeout=60)
    (build / f"{scenario}.log").write_text(result.stdout + result.stderr, encoding="utf8")
    (build / f"{scenario}.exit").write_text(str(result.returncode), encoding="utf8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failures" in result.stdout
