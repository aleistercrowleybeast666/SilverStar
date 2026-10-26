"""Same final metadata bytes/results before and after bounded projection."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import pytest
from silverstar_fccg.app.service import FccgService

ROOT = Path(__file__).resolve().parents[3]
BASELINE = "79eeadad53c70e55a1f52a278f950283d3486227"


@pytest.fixture(scope="module")
def contract_project(workspace_root, tmp_path_factory):
    # This harness exercises two storage service implementations against shared
    # interface types. It does not compile or execute either MCU platform.
    project = tmp_path_factory.mktemp('logger-final-interface')
    service = FccgService(workspace_root)
    service.Project_Save(service.ReferenceProject_Create('LoggerFinalInterface'), project,
                         confirm_dangerous=True)
    return project


@pytest.mark.parametrize("target", ["ret6", "f407_regression"])
def test_final_status_bytes_and_failures(target, tmp_path, contract_project):
    project = contract_project
    includes = re.findall(r'"-I\$repoRoot\\([^"\r\n]+)"',
                          (project / "Tests/Host/run_tests.ps1").read_text(encoding='utf8'))
    includes += ["Devices/Storage/SdSdioFatFs/Adapter/Inc"]
    # The interface harness has no SD hardware. Reuse the existing Host FatFs
    # type boundary rather than depend on an untracked CubeMX project layout.
    includes.insert(0, "Tests/Host/storage_integrity")
    includes += ["Middlewares/Third_Party/FatFs/src", "FATFS/Target"]
    profile = json.loads((project / "SilverStar.ssproject").read_text(encoding='utf8'))["build"]["target_profile"]
    includes.insert(0, "Targets/" + profile + "/Inc")
    fixture = Path(__file__).parent / "fixtures/logger_final_status.c"
    plugin = "silverstar_device_storage_sd_sdio_fatfs" + ("_f1" if target == "ret6" else "")
    name = "apps/SCG/plugins/builtin/" + plugin + "/payload/Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c"
    old = subprocess.check_output(["git", "show", BASELINE + ":" + name], cwd=ROOT)
    baseline = tmp_path / "baseline_mission_snapshot.c"
    baseline.write_bytes(old)
    # Preserve all FatFs options; omit only board/HAL includes for this Host
    # type boundary, as the storage-integrity harness already does.
    ffconf = (project / 'FATFS/Target/ffconf.h').read_text(encoding='utf8')
    for header in ('main.h','stm32f4xx_hal.h','stm32f1xx_hal.h','bsp_driver_sd.h'):
        ffconf = ffconf.replace('#include "' + header + '"', '')
    (tmp_path / 'ffconf.h').write_text(ffconf, encoding='utf8')
    results = []
    payloads = {}
    for label, source in [("before", baseline), ("after", ROOT / name)]:
        binary = tmp_path / (label + ".exe")
        command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-O2", "-flto", "-Wall", "-Wextra", "-Werror",
                   "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections", "-include",
                   str(project / "Generated/Inc/project_flight_config.h")]
        command += ['-I' + str(tmp_path)]
        command += ["-I" + str(project / p.replace("\\", "/")) for p in includes]
        command += [str(fixture), str(source), "-o", str(binary)]
        env = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
        compile_result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
        results.append({"label": label, "argv": command, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "compile_exit": compile_result.returncode, "stderr": compile_result.stderr})
        (tmp_path / "results.json").write_text(json.dumps(results, indent=2))
        assert compile_result.returncode == 0, compile_result.stderr
        for case in range(9):
            result = subprocess.run([str(binary), str(case)], env=env, capture_output=True, text=True, timeout=10)
            results.append({"label": label, "case": case, "exit": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr})
            (tmp_path / "results.json").write_text(json.dumps(results, indent=2))
            assert result.returncode == 0, (label, case, result.stdout, result.stderr)
            if label == "before":
                payloads[case] = result.stdout
            else:
                assert result.stdout == payloads[case]
