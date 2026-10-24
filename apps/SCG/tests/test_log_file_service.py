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


def test_block_corrupt_internal_state_enters_terminal_trap(tmp_path, workspace_root):
    import importlib.util
    import sys
    compiler = shutil.which('gcc')
    assert compiler, 'Host GCC is required'
    base = workspace_root/'plugins/builtin'
    core = base/'silverstar_core_0_1_0/payload'
    fixture = workspace_root/'tests/log_file_service'
    includes = [fixture, core/'System/Inc', core/'Interfaces/Inc', core/'Common/Inc', base/'silverstar_platform_api/payload/Platform/Inc']
    binary = tmp_path/'block_faults.exe'
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fanalyzer',
               *['-I'+str(p) for p in includes], str(fixture/'test_log_file_block_faults.c'),
               str(core/'Common/Src/common_format.c'),
               str(base/'silverstar_device_storage_sd_sdio_fatfs/payload/Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c'),
               '-o', str(binary)]
    rows = []
    for args in (command, [str(binary)]):
        run = subprocess.run(args, capture_output=True, text=True, timeout=90,
                             env={**os.environ, 'TEMP':str(tmp_path), 'TMP':str(tmp_path)})
        rows.append(dict(command=args, exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr))
        (tmp_path/'block_faults.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
        assert run.returncode == 0, run.stdout+run.stderr
        if args == [str(binary)]:
            spec = importlib.util.spec_from_file_location('gshc_inplace_codec', workspace_root.parent/'GSHC/services/file_service_block.py')
            codec = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = codec
            spec.loader.exec_module(codec)
            for line in run.stdout.splitlines():
                if not line.startswith('ENCODER_HEX '):
                    continue
                _, pattern_text, encoded = line.split()
                pattern = int(pattern_text)
                framed = bytes.fromhex(encoded)
                assert framed[0] == framed[-1] == 0
                expected = bytes(0 if pattern == 0 else 255 if pattern == 1 else i%256 if pattern == 2 else (i*137+29)%256 for i in range(560))
                assert codec.Cobs_Decode(framed[1:-1]) == expected


@pytest.mark.parametrize('variant', ['silverstar_device_storage_sd_sdio_fatfs', 'silverstar_device_storage_sd_sdio_fatfs_f1'])
def test_negotiated_binary_blocks_real_service_and_adapter(tmp_path, workspace_root, variant):
    import importlib.util
    import zlib
    compiler = shutil.which('gcc')
    assert compiler, 'Host GCC required for actual analyzer compilation'
    base = workspace_root / 'plugins/builtin'
    core = base / 'silverstar_core_0_1_0/payload'
    fixture = workspace_root / 'tests/log_file_service'
    adapter = base / variant / 'payload/Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c'
    includes = [fixture, core/'System/Inc', core/'Interfaces/Inc', core/'Common/Inc', base/'silverstar_platform_api/payload/Platform/Inc']
    binary = tmp_path/'blocks.exe'
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fanalyzer',
               *['-I'+str(path) for path in includes], str(fixture/'test_log_file_blocks.c'),
               str(core/'System/Src/system_log_file.c'), str(core/'Common/Src/common_format.c'), str(adapter), '-o', str(binary)]
    # Decode target-C-produced frames with the actual GSHC codec, not a duplicate decoder.
    codec_path = workspace_root.parent/'GSHC/services/file_service_block.py'
    spec = importlib.util.spec_from_file_location('gshc_block_codec_regression', codec_path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cases = ['replay', 'arguments', 'short-read', 'read-error', 'seek-error', 'lifecycle', 'size-change', 'cancel-io',
             'idle', 'capacity', 'cancel-done', *[f'size={size}' for size in (0, 1, 63, 64, 65, 255, 511, 512, 513, 1025, 8192)]]
    rows = []
    for args in [command, *[[str(binary), case] for case in cases]]:
        run = subprocess.run(args, capture_output=True, text=True, timeout=90,
                             env={**os.environ, 'TEMP':str(tmp_path), 'TMP':str(tmp_path)})
        rows.append(dict(command=args, exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr))
        (tmp_path/'block_runs.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
        assert run.returncode == 0, run.stdout + run.stderr
        for line in run.stdout.splitlines():
            if not line.startswith('FRAME_HEX '):
                continue
            framed = bytes.fromhex(line.split()[1])
            assert framed[0] == framed[-1] == 0
            block = module.Block_Decode(framed[1:-1])
            assert block.transfer == 0x1122334455667788 and block.file_id == 1
            assert block.sequence == block.offset//512
            assert block.data == bytes((block.offset+i)%256 for i in range(len(block.data)))
            assert block.whole_crc == zlib.crc32(bytes(i%256 for i in range(block.size)))


@pytest.mark.parametrize('variant',['silverstar_device_storage_sd_sdio_fatfs','silverstar_device_storage_sd_sdio_fatfs_f1'])
def test_bounded_hash_and_retained_reader(tmp_path,workspace_root,variant):
    compiler=shutil.which('gcc')
    assert compiler, 'Required Host compiler unavailable; no target claim is possible'
    base=workspace_root/'plugins/builtin'
    core=base/'silverstar_core_0_1_0/payload'
    fixture=workspace_root/'tests/log_file_service'
    adapter=base/variant/'payload/Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c'
    includes=[fixture,core/'System/Inc',core/'Interfaces/Inc',core/'Common/Inc',base/'silverstar_platform_api/payload/Platform/Inc']
    binary=tmp_path/'transfer.exe'
    command=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fanalyzer',
        *['-I'+str(path) for path in includes],str(fixture/'test_log_file_transfer.c'),
        str(core/'System/Src/system_log_file.c'),str(core/'Common/Src/common_format.c'),str(adapter),'-o',str(binary)]
    cases=['budget','timed-budget','sequential','short-read','read-error','seek-error','lifecycle','size-change',
           'idle-reconnect','cancel-quantum','close-failure',*[f'size={n}' for n in (0,1,63,64,65,511,512,513,8192)]]
    rows=[]
    for args in [command,*[[str(binary),case] for case in cases]]:
        result=subprocess.run(args,capture_output=True,text=True,timeout=90,
            env={**os.environ,'TEMP':str(tmp_path),'TMP':str(tmp_path)})
        rows.append(dict(command=args,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
        (tmp_path/'transfer_runs.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        assert result.returncode==0,result.stdout+result.stderr


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
    enabled = logging and maintenance
    assert ("System/Src/system_log_file.c" in graph.sources) is enabled
    assert ("System/Src/system_log_file_disabled.c" in graph.sources) is not enabled
    assert ("Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c" in graph.sources) is enabled
    assert ("Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c" in graph.exclude_sources) is not enabled
    assert ("APP/Src/logger_task.c" in graph.sources) is logging
    assert ("System/Src/system_console.c" in graph.sources) is maintenance


def test_log_file_never_silently_substitutes_missing_storage(builtin_catalog):
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.project.storage_binding import StorageBinding_Resolve
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances = [instance for instance in model.device_instances
                              if not instance.plugin.startswith("silverstar.device.storage.")]
    assert StorageBinding_Resolve(model, builtin_catalog).issues[0].code == "STORAGE_DEVICE_REQUIRED"

@pytest.mark.parametrize('variant', ['silverstar_device_storage_sd_sdio_fatfs', 'silverstar_device_storage_sd_sdio_fatfs_f1'])
def test_negotiated_batch_real_service_and_adapter(tmp_path, workspace_root, variant):
    import importlib.util
    import zlib
    compiler = shutil.which('gcc')
    assert compiler, 'Host GCC required for actual analyzer compilation'
    base = workspace_root / 'plugins/builtin'
    core = base / 'silverstar_core_0_1_0/payload'
    fixture = workspace_root / 'tests/log_file_service'
    adapter = base / variant / 'payload/Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c'
    includes = [fixture, core/'System/Inc', core/'Interfaces/Inc', core/'Common/Inc', base/'silverstar_platform_api/payload/Platform/Inc']
    binary = tmp_path/'batch.exe'
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fanalyzer',
               *['-I'+str(path) for path in includes], str(fixture/'test_log_file_batch.c'),
               str(core/'System/Src/system_log_file.c'), str(core/'Common/Src/common_format.c'), str(adapter), '-o', str(binary)]
    # Decode target-C-produced frames with the actual GSHC codec, not a duplicate decoder.
    codec_path = workspace_root.parent/'GSHC/services/file_service_block.py'
    spec = importlib.util.spec_from_file_location('gshc_block_codec_regression', codec_path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cases = ['backpressure', 'overlap', 'short-read', 'read-error', 'seek-error', 'lifecycle', 'size-change',
             'cancel-io', 'cancel-done', 'cancel-claimed', 'idle', *[f'size={size}' for size in (0, 1, 511, 512, 513, 2047, 2048, 2049, 8192)]]
    rows = []
    for args in [command, *[[str(binary), case] for case in cases]]:
        run = subprocess.run(args, capture_output=True, text=True, timeout=90,
                             env={**os.environ, 'TEMP':str(tmp_path), 'TMP':str(tmp_path)})
        rows.append(dict(command=args, exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr))
        (tmp_path/'batch_runs.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
        assert run.returncode == 0, run.stdout + run.stderr
        for line in run.stdout.splitlines():
            if not line.startswith('FRAME_HEX '):
                continue
            framed = bytes.fromhex(line.split()[1])
            assert framed[0] == framed[-1] == 0
            block = module.Block_Decode(framed[1:-1])
            assert block.transfer == 0x1122334455667788 and block.file_id == 1
            assert block.sequence == block.offset//512
            assert block.data == bytes((block.offset+i)%256 for i in range(len(block.data)))
            assert block.whole_crc == zlib.crc32(bytes(i%256 for i in range(block.size)))


