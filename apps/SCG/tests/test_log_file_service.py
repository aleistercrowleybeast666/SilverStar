"""Compile real service + storage adapter with a synthetic file/lifecycle backend."""
from pathlib import Path
import json
import os
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("logging,maximum", [(True, False), (False, False), (True, True)])
def test_log_file_service_fault_boundaries(tmp_path, workspace_root, logging, maximum):
    compiler = shutil.which("gcc")
    if not compiler:
        pytest.skip("Host GCC unavailable")
    base = workspace_root / "plugins/builtin"
    core = base / "silverstar_core_0_1_0/payload"
    fixture = workspace_root / "tests/log_file_service"
    adapter = base / "silverstar_device_storage_sd_sdio_fatfs/payload/Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c"
    includes = [fixture, core / "System/Inc", core / "Interfaces/Inc", core / "Common/Inc",
                base / "silverstar_platform_api/payload/Platform/Inc"]
    binary = tmp_path / "log-file-service.exe"
    command = [compiler, "-std=c11", "-O2" if logging else "-O0", "-Wall", "-Wextra", "-Werror", "-fanalyzer"]
    if not logging:
        command += ["-DSILVERSTAR_PROTOCOL_LOGGING_ENABLED=0"]
    command += ["-I" + str(path) for path in includes]
    command += ([str(fixture / "test_log_file_maximum.c")] if maximum else
                [str(fixture / "test_log_file_service.c"), str(core / "System/Src/system_log_file.c")])
    command += [str(core / "Common/Src/common_format.c"), str(adapter), "-o", str(binary)]
    log = []
    environment = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    cases = ([str(binary)],) if maximum else (([str(binary)], [str(binary), "close-fault"],
        [str(binary), "golden"], [str(binary), "start-window"], [str(binary), "unfinalized"],
        [str(binary), "full-chunk"], [str(binary), "status"],
        [str(binary), "boot-maintenance"]) if logging else ([str(binary), "disabled"],))
    for arguments in (command, *cases):
        run = subprocess.run(arguments, capture_output=True, text=True, env=environment, timeout=90)
        log.append({"command": arguments, "exit_code": run.returncode, "stdout": run.stdout, "stderr": run.stderr})
        (tmp_path / "run.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        if arguments[-1] == "golden":
            contract = json.loads((workspace_root.parents[1] / "contracts/log_file_service_v1.json").read_text())
            assert run.stdout.strip() == contract["golden"]["read_response"].strip()
        if maximum and arguments == [str(binary)]:
            import zlib
            assert f"crc32={zlib.crc32(bytes(range(191,255))):08X}" in run.stdout


def test_f1_and_f4_log_file_payloads_are_identical(workspace_root):
    root = workspace_root / "plugins/builtin"
    relative = "payload/Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c"
    assert (root / "silverstar_device_storage_sd_sdio_fatfs" / relative).read_bytes() == (
        root / "silverstar_device_storage_sd_sdio_fatfs_f1" / relative).read_bytes()


@pytest.mark.parametrize("logging,maintenance", [(True, True), (True, False), (False, True), (False, False)])
def test_log_file_source_graph_owns_backend_without_optional_link_gaps(builtin_catalog, logging, maintenance):
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
    model = ReferenceProject_Create(catalog=builtin_catalog)
    if not logging:
        model.protocols["logging"] = None
    if not maintenance:
        model.protocols["maintenance"] = None
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "System/Src/system_log_file.c" in graph.sources
    assert "Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c" in graph.sources
    assert ("APP/Src/logger_task.c" in graph.sources) is logging
    assert ("System/Src/system_console.c" in graph.sources) is maintenance


def test_log_file_never_silently_substitutes_missing_storage(builtin_catalog):
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.project.storage_binding import StorageBinding_Resolve
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances = [instance for instance in model.device_instances
                              if not instance.plugin.startswith("silverstar.device.storage.")]
    assert StorageBinding_Resolve(model, builtin_catalog).issues[0].code == "STORAGE_DEVICE_REQUIRED"
