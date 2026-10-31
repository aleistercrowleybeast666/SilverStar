"""Compile current C capture and active-owner peers for GSHC tests; no devices."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
SCG = REPO / 'apps/SCG'
BUILTIN = SCG / 'plugins/builtin'
CORE = BUILTIN / 'silverstar_core_0_1_0/payload'
CAPTURE = BUILTIN / 'silverstar_installation_capture/payload'
CODE = CAPTURE / 'Modules/InstallationCapture'
EXPERIMENT = SCG / 'experiments/installation_capture_stream_0_1_3/implementation_v1'
NAME = sys.argv[1] if len(sys.argv) == 2 else 'gshc-harness-v1'
assert re.fullmatch(r'gshc-harness-v[1-9][0-9]*', NAME)
OUTPUT = REPO / '.work/0.1.3-treediagram-20261101/silverstar' / NAME
GENERATED = REPO / '.work/0.1.3-treediagram-20261101/silverstar/firmware-v1/installation/Flight_Controller'
OUTPUT.mkdir(exist_ok=False)
GCC = 'D:/msys64/ucrt64/bin/gcc.exe'
commands = []


def Build(name, command):
    run = subprocess.run(list(map(str, command)), cwd=REPO, capture_output=True, text=True, check=False)
    source_hashes = {str(Path(item).relative_to(REPO)): hashlib.sha256(Path(item).read_bytes()).hexdigest()
                     for item in command if str(item).endswith('.c') and Path(item).is_file()}
    commands.append(dict(name=name, command=list(map(str, command)), exit_code=run.returncode,
                         stdout=run.stdout, stderr=run.stderr, source_sha256=source_hashes))
    (Path(__file__).parent / (NAME + '.json')).write_text(json.dumps(commands, indent=2), encoding='utf-8')
    if run.returncode:
        raise RuntimeError(run.stderr)


includes = [CODE/'Inc', CAPTURE/'ThirdParty/InstallationCapture', CORE/'Interfaces/Inc',
    CORE/'Common/Inc', CORE/'System/Inc', CORE/'System/Calibration/Inc', CORE/'System/Inertial/Inc',
    EXPERIMENT/'fixtures', CODE/'Src',
    BUILTIN/'silverstar_algorithm_calibration/payload/Algorithm/Calibration/Inc',
    BUILTIN/'silverstar_platform_api/payload/Platform/Inc',
    BUILTIN/'silverstar_mcu_family_stm32f4/payload/Drivers/CMSIS/Include']
sources = [EXPERIMENT/'capture_test_access.c', CODE/'Src/capture_info.c', CODE/'Src/capture_primitives.c',
    CAPTURE/'ThirdParty/InstallationCapture/ryu/d2s.c', CODE/'Src/system_installation_capture.c',
    CORE/'Common/Src/common_format.c', EXPERIMENT/'integration_stubs.c', EXPERIMENT/'capture_dependency_stubs.c',
    SCG/'tests/fixtures/installation_capture_only_active_boundary.c', EXPERIMENT/'capture_port_host.c']
Build('capture', [GCC, '-shared', '-std=c11', '-Wall', '-Wextra', '-Wconversion', '-Wshadow',
    '-Wstrict-prototypes', '-Werror', '-O2', '-DSYSTEM_INSTALLATION_CAPTURE_ENABLED=1', '-DRYU_ONLY_64_BIT_OPS',
    *['-I'+str(path) for path in includes], *sources, '-o', OUTPUT/'capture.dll'])
text = (GENERATED/'Generated/project_sources.mk').read_text(encoding='utf-8')
block = re.search(r'C_INCLUDES\s*\+=\s*\\\n(.*?)(?:\n\n|$)', text, re.S)
generated_includes = [GENERATED/path for path in block.group(1).replace('\\', '').split()] if block else []
assert generated_includes, 'Normal generated include graph is required'
active_sources = [SCG/'tests/fixtures/installation_active_consumer.c',
    GENERATED/'System/Calibration/Src/system_calibration.c',
    GENERATED/'System/Calibration/Src/system_calibration_correction.c',
    GENERATED/'Algorithm/Calibration/Src/imu_six_face_calibration.c', GENERATED/'Common/Src/silverstar_assert.c',
    CODE/'Src/capture_primitives.c', CODE/'Src/capture_info.c', EXPERIMENT/'capture_port_host.c',
    CAPTURE/'ThirdParty/InstallationCapture/ryu/d2s.c', GENERATED/'Common/Src/common_format.c']
active_includes = [*generated_includes, GENERATED/'Tests/Host', CODE/'Inc', CODE/'Src',
    CAPTURE/'ThirdParty/InstallationCapture',
    BUILTIN/'silverstar_device_storage_sd_sdio_fatfs/payload/Devices/Storage/SdSdioFatFs/Adapter/Src']
Build('active', [GCC, '-shared', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
    '-include', GENERATED/'Generated/Inc/project_flight_config.h',
    '-DSYSTEM_INSTALLATION_CAPTURE_ENABLED=1U', '-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=6U',
    *['-I'+str(path) for path in active_includes], *active_sources, '-lm', '-o', OUTPUT/'active.dll'])
print(OUTPUT)
