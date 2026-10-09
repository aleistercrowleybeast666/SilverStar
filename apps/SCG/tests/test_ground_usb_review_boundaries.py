from pathlib import Path
from dataclasses import replace
import importlib.util
import re
import shutil
import struct

import pytest

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImporter, CubeMxImportError
from silverstar_fccg.hardware.cubemx_ground import GroundEffectiveDefinitions_Validate
from silverstar_fccg.generator.assembler import ProjectAssembler, ProjectAssemblerError
from silverstar_fccg.generator.multi_target import _UsbCallback_Integrate, _GroundModel_Get
from silverstar_fccg.generator.ground_pc_usb_cdc import PcUsbCdc_Render
from test_ground_cubemx_base import _Cube_Get
from test_round2_targets import _GroundBoardProject_Get
from test_joint_sensor_library import _Command_Run, _Compiler_Get

SCG = Path(__file__).resolve().parents[1]
PAYLOAD = SCG / "plugins/builtin/silverstar_core_ground_0_1_0/payload"
COMMON = SCG / "plugins/builtin/silverstar_core_0_1_0/payload/Common"


@pytest.mark.parametrize("family", ["f103", "f407"])
def test_real_cubemx_init_deinit_hooks_execute_before_existing_return(tmp_path, family):
    source = SCG / f"tests/fixtures/ground_cdc/usbd_cdc_if_{family}.c"
    integrated = _UsbCallback_Integrate(source.read_bytes()).decode()
    bodies = [re.search(r"static int8_t CDC_" + name + r"_FS\(void\)\s*\{.*?\n\}", integrated, re.S)[0]
              for name in ("Init", "DeInit")]
    harness = tmp_path / "callbacks.c"
    harness.write_text('''#include <stdint.h>
#define USBD_OK 0
static int calls, hUsbDeviceFS;
static uint8_t UserTxBufferFS[1], UserRxBufferFS[1];
static void PcByteStream_OnUsbReset(void) { calls++; }
static void USBD_CDC_SetTxBuffer(int *d,uint8_t *b,int n) {(void)d;(void)b;(void)n;}
static void USBD_CDC_SetRxBuffer(int *d,uint8_t *b) {(void)d;(void)b;}
''' + "\n".join(bodies) + "\nint main(void) { CDC_Init_FS(); CDC_DeInit_FS(); return calls == 2 ? 0 : 23; }\n", encoding="utf8")
    executable = tmp_path / "callbacks.exe"
    _Command_Run([_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", str(harness), "-o", str(executable)], tmp_path, "compile")
    _Command_Run([str(executable)], tmp_path, "run")


def test_reset_during_read_and_cross_session_prefix_never_deliver(tmp_path):
    host = PAYLOAD / "Tests/Host"
    for old, new in (("usb_session_main.h", "main.h"), ("usb_device.h", "usb_device.h"), ("usb_cdc_if.h", "usbd_cdc_if.h")):
        (tmp_path / new).write_bytes((host / old).read_bytes())
    (tmp_path / "usbd_conf.h").write_text("/* Host stub */", encoding="utf8")
    adapter = tmp_path / "adapter.c"
    adapter.write_text(PcUsbCdc_Render(), encoding="utf8")
    executable = tmp_path / "session.exe"
    includes = [tmp_path, PAYLOAD / "Ground/Core/Inc", PAYLOAD / "Ground/Protocol/Inc", COMMON / "Inc"]
    sources = [adapter, host / "usb_session.c", PAYLOAD / "Ground/Core/Src/ground_bridge.c",
               PAYLOAD / "Ground/Protocol/Src/gsp_min_protocol.c", PAYLOAD / "Ground/Protocol/Src/protocol_crc16.c"]
    _Command_Run([_Compiler_Get(), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", *["-I" + str(path) for path in includes],
                  *map(str, sources), "-o", str(executable)], tmp_path, "compile")
    for args in ([], ["control"], ["read-reset"], ["delivery-reset"], ["normal"]):
        _Command_Run([str(executable), *args], tmp_path, "run")


@pytest.mark.parametrize("family", ["f103", "f407"])
def test_real_deconfigure_reconfigure_invalidates_rx_and_queued_tx_session(tmp_path, family):
    integrated = _UsbCallback_Integrate((SCG / f"tests/fixtures/ground_cdc/usbd_cdc_if_{family}.c").read_bytes()).decode()
    bodies = [re.search(r"static int8_t CDC_" + name + r"_FS\(void\)\s*\{.*?\n\}", integrated, re.S)[0]
              for name in ("Init", "DeInit")]
    host = PAYLOAD / "Tests/Host"
    for old, new in (("usb_main.h", "main.h"), ("usb_device.h", "usb_device.h"), ("usb_cdc_if.h", "usbd_cdc_if.h")):
        (tmp_path / new).write_bytes((host / old).read_bytes())
    (tmp_path / "usbd_conf.h").write_text("/* Host */", encoding="utf8")
    adapter = tmp_path / "adapter.c"
    adapter.write_text(PcUsbCdc_Render(), encoding="utf8")
    harness = tmp_path / "reconfigure.c"
    harness.write_text('''#include <assert.h>
#include "pc_byte_stream.h"
#include "usb_device.h"
#include "usbd_cdc_if.h"
uint32_t usb_test_mask;
USBD_HandleTypeDef hUsbDeviceFS;
static USBD_CDC_HandleTypeDef cls;
static uint8_t UserTxBufferFS[1], UserRxBufferFS[1];
static void USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *d,uint8_t *b,int n) {(void)d;(void)b;(void)n;}
static void USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *d,uint8_t *b) {(void)d;(void)b;}
uint8_t CDC_Transmit_FS(uint8_t *p,uint16_t n) {(void)p;(void)n;return USBD_OK;}
''' + "\n".join(bodies) + '''
int main(void) {
 uint8_t bytes[3]={1U,2U,3U}, out[3]; uint32_t old;
 hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED; hUsbDeviceFS.pClassData=&cls;
 assert(PcByteStream_Init()==PC_BYTE_STREAM_INIT_OK); old=PcByteStream_Session_Get();
 PcByteStream_OnUsbReceive(bytes,3U);
 assert(CDC_DeInit_FS()==USBD_OK); assert(CDC_Init_FS()==USBD_OK);
 assert(PcByteStream_Session_Get()==old+2U);
 assert(PcByteStream_Read(out,3U)==0U);
 assert(PcByteStream_WriteSession(bytes,3U,old)==PC_BYTE_STREAM_WRITE_BUSY);
 PcByteStream_OnUsbReceive(bytes,3U); assert(PcByteStream_Read(out,3U)==3U);
 assert(PcByteStream_Write(bytes,3U)==PC_BYTE_STREAM_WRITE_OK); return 0;
}
''', encoding="utf8")
    executable = tmp_path / "reconfigure.exe"
    includes = [tmp_path, PAYLOAD / "Ground/Core/Inc", PAYLOAD / "Ground/Protocol/Inc", COMMON / "Inc"]
    _Command_Run([_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", *["-I" + str(p) for p in includes],
                  str(adapter), str(harness), "-o", str(executable)], tmp_path, "compile")
    _Command_Run([str(executable)], tmp_path, "run")


@pytest.mark.parametrize("dependency", ["absolute_c", "relative_c", "macro_c", "non_header", "linker", "assembler"])
def test_external_or_indirect_dependencies_are_rejected_before_snapshot(tmp_path, dependency):
    root = _Cube_Get(tmp_path / "cube")
    external = tmp_path / "outside.h"
    external.write_text("#define VALUE 17", encoding="utf8")
    if dependency == "absolute_c":
        (root / "Core/Src/main.c").write_text('#include "' + external.as_posix() + '"\n', encoding="utf8")
    elif dependency == "relative_c":
        (root / "Core/Inc/main.h").write_text('#include "../../../outside.h"\n', encoding="utf8")
    elif dependency == "macro_c":
        (root / "Core/Src/main.c").write_text('#define OTHER "outside.h"\n#include OTHER\n', encoding="utf8")
    elif dependency == "non_header":
        (root / "Core/Src/main.c").write_text('#include "config.json"\n', encoding="utf8")
        (root / "Core/Inc/config.json").write_text('#include "' + external.as_posix() + '"\n', encoding="utf8")
    elif dependency == "linker":
        with (root / "STM32F103XX_FLASH.ld").open("a") as file:
            file.write('\nINCLUDE "' + (tmp_path / "outside.ld").as_posix() + '"\n')
    else:
        (root / "startup_stm32f103xb.s").write_text('.include "outside.inc"\n', encoding="utf8")
    with pytest.raises(CubeMxImportError, match="include|dependenc"):
        CubeMxImporter(WorkspacePolicy(tmp_path / "w")).Project_Import(root, target="ground")


@pytest.mark.parametrize("override", ["-DHSE_VALUE=16000000", "-DSTM32F407xx", "-DCMSIS_NVIC_VIRTUAL=1"])
def test_effective_macro_overrides_cannot_contradict_the_validated_profile(tmp_path, override):
    root = _Cube_Get(tmp_path / "cube")
    manifest = root / "Makefile"
    manifest.write_text(manifest.read_text().replace("-DSTM32F103xB", "-DSTM32F103xB " + override), encoding="utf8")
    with pytest.raises(CubeMxImportError, match="overrides"):
        CubeMxImporter(WorkspacePolicy(tmp_path / "w")).Project_Import(root, target="ground")


@pytest.mark.parametrize("override", ["HSE_VALUE=16000000", "STM32F407xx"])
def test_generated_effective_definitions_also_reject_plugin_overrides(override):
    ordinary = ("STM32F103xB", "USE_HAL_DRIVER", "AIR_LINK_HAL_BUFFER_SIZE=260")
    GroundEffectiveDefinitions_Validate(ordinary, "STM32F103C8T6")
    with pytest.raises(ValueError, match="contradicts"):
        GroundEffectiveDefinitions_Validate((*ordinary, override), "STM32F103C8T6")


def test_irq_handler_file_must_be_in_the_compilation_inventory(tmp_path):
    root = _Cube_Get(tmp_path / "cube")
    manifest = root / "Makefile"
    manifest.write_text(manifest.read_text().replace(" Core/Src/stm32f1xx_it.c", ""), encoding="utf8")
    with pytest.raises(CubeMxImportError, match="IRQ source in C_SOURCES"):
        CubeMxImporter(WorkspacePolicy(tmp_path / "w")).Project_Import(root, target="ground")


def test_added_header_cannot_shadow_toolchain_in_a_frozen_snapshot(tmp_path, builtin_catalog):
    policy = WorkspacePolicy(tmp_path / "w")
    result = CubeMxImporter(policy).Project_Import(_Cube_Get(tmp_path / "cube"), target="ground")
    model = _GroundBoardProject_Get(builtin_catalog)
    model.ground_target = replace(model.ground_target, board="", hardware=result.hardware)
    (result.snapshot_root / "Core/Inc/stdint.h").write_text("#define SHADOW 37\n", encoding="utf8")
    with pytest.raises(ProjectAssemblerError, match="file set changed"):
        ProjectAssembler(policy, builtin_catalog)._HardwareFiles_Get(_GroundModel_Get(model, builtin_catalog))


@pytest.mark.parametrize("failure", ["source", "interrupt"])
def test_timer_timebase_requires_its_compiled_owner_and_enabled_irq(tmp_path, failure):
    root = _Cube_Get(tmp_path / "cube")
    with (root / "test.ioc").open("a") as file:
        file.write("NVIC.TimeBaseIP=TIM1\nNVIC.TimeBase=TIM1_UP_IRQn\nNVIC.TIM1_UP_IRQn=" + ("false" if failure == "interrupt" else "true") + "\n")
    (root / "Core/Src/stm32f1xx_it.c").write_text("void TIM1_UP_IRQHandler(void) {}", encoding="utf8")
    if failure == "interrupt":
        (root / "Core/Src/stm32f1xx_hal_timebase_tim.c").write_text("/* data fixture */", encoding="utf8")
        manifest = root / "Makefile"
        manifest.write_text(manifest.read_text().replace("Core/Src/stm32f1xx_it.c", "Core/Src/stm32f1xx_it.c Core/Src/stm32f1xx_hal_timebase_tim.c"), encoding="utf8")
    with pytest.raises(CubeMxImportError, match="timer timebase"):
        CubeMxImporter(WorkspacePolicy(tmp_path / "w")).Project_Import(root, target="ground")


def _ArtifactModule_Get():
    spec = importlib.util.spec_from_file_location("ground_artifact_contract", PAYLOAD / "Tools/ground_artifact_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_linked_vector_gate_rejects_weak_or_misdirected_handlers(tmp_path):
    (tmp_path / "startup.s").write_text("g_pfnVectors:\n .word _estack\n .word SysTick_Handler\n", encoding="utf8")
    graph = {"asm_sources": ["startup.s"], "required_irq_handlers": ["SysTick_Handler"]}
    vector = struct.pack("<II", 0x20005000, 0x08000101)
    module = _ArtifactModule_Get()
    with pytest.raises(ValueError, match="weak"):
        module.InterruptVectors_Validate(tmp_path, graph, "08000100 W SysTick_Handler", vector)
    with pytest.raises(ValueError, match="vector does not"):
        module.InterruptVectors_Validate(tmp_path, graph, "08000200 T SysTick_Handler", vector)
    module.InterruptVectors_Validate(tmp_path, graph, "08000100 T SysTick_Handler", vector)


def test_actual_dependency_gate_rejects_non_system_headers_outside_target(tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "main.c").write_text("int main(void) {return 0;}", encoding="utf8")
    external = tmp_path.parent / (tmp_path.name + "-outside.h")
    external.write_text("/* external */", encoding="utf8")
    dependency = tmp_path / "build/main.d"
    dependency.write_text("build/main.o: main.c " + external.as_posix() + "\n", encoding="utf8")
    with pytest.raises(ValueError, match="escaped"):
        _ArtifactModule_Get().DependencyClosure_Validate(tmp_path, {"sources": ["main.c"]})


@pytest.mark.parametrize("directive", [
    '%:include "outside.h"', '??=include "outside.h"',
    '#inc??/\nlude "outside.h"', '%:inc\\\nlude "outside.h"', '%\\\n:include "outside.h"',
])
def test_import_rejects_alternate_preprocessing_before_snapshot(tmp_path, directive):
    cube = _Cube_Get(tmp_path / "cube")
    (cube / "Core/Inc/escape.h").write_text('#pragma GCC system_header\n' + directive + '\n', encoding="utf8")
    with pytest.raises(CubeMxImportError, match="alternate preprocessing"):
        CubeMxImporter(WorkspacePolicy(tmp_path / "workspace")).Project_Import(cube, target="ground")


def _ArmCompiler_Get():
    compiler = shutil.which("arm-none-eabi-gcc")
    if compiler is None:
        candidate = Path("D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gcc.exe")
        compiler = str(candidate) if candidate.is_file() else None
    if compiler is None:
        pytest.skip("actual ARM GCC unavailable; compiled dependency negative NOT PROVEN")
    return compiler


@pytest.mark.parametrize("directive", ["#include", "%:include", "??=include"])
def test_real_arm_system_marked_dependencies_cannot_escape(tmp_path, directive):
    compiler = _ArmCompiler_Get()
    target = tmp_path / "target"
    (target / "build").mkdir(parents=True)
    outside = tmp_path / "outside.h"
    (target / "marked.h").write_text('#pragma GCC system_header\n' + directive + ' "' + outside.as_posix() + '"\n', encoding="utf8")
    (target / "main.c").write_text('#include <stdint.h>\n#include "marked.h"\nint Probe(void);\nint Probe(void) {return EXTERNAL_VALUE;}\n', encoding="utf8")
    module = _ArtifactModule_Get()
    hashes = []
    for value in (17, 29):
        outside.write_text('#define EXTERNAL_VALUE ' + str(value) + '\n', encoding="utf8")
        _Command_Run([compiler, '-std=c11', '-mcpu=cortex-m3', '-mthumb', '-MD', '-MP', '-c',
                      str(target / 'main.c'), '-o', str(target / 'build/main.o')], target, "ARM compile")
        dependency = (target / 'build/main.d').read_text(encoding="utf8")
        assert 'outside.h' in dependency and 'marked.h' in dependency
        with pytest.raises(ValueError, match="escaped"):
            module.DependencyClosure_Validate(target, {"sources": ["main.c"]}, compiler)
        hashes.append((target / 'build/main.o').read_bytes())
    assert hashes[0] != hashes[1], "real ARM input mutation must affect the compiled object"
    # The same system marker on a frozen local header remains supported. Only
    # the tree-external dependency is refused; genuine default toolchain stdint
    # and its transitive system headers are admitted after canonical resolution.
    (target / 'marked.h').write_text('#pragma GCC system_header\n#define EXTERNAL_VALUE 17\n', encoding="utf8")
    _Command_Run([compiler, '-std=c11', '-mcpu=cortex-m3', '-mthumb', '-MD', '-MP', '-c',
                  str(target / 'main.c'), '-o', str(target / 'build/main.o')], target, "ARM normal compile")
    module.DependencyClosure_Validate(target, {"sources": ["main.c"]}, compiler)


def test_actual_dependency_gate_covers_preprocessed_assembly(tmp_path):
    (tmp_path / 'build').mkdir()
    (tmp_path / 'startup.s').write_text('/* imported assembly */', encoding="utf8")
    outside = tmp_path.parent / (tmp_path.name + '-assembly-outside.h')
    outside.write_text('/* external */', encoding="utf8")
    (tmp_path / 'build/startup.d').write_text('build/startup.o: startup.s ' + outside.as_posix() + '\n', encoding="utf8")
    with pytest.raises(ValueError, match="escaped"):
        _ArtifactModule_Get().DependencyClosure_Validate(tmp_path, {"sources": [], "asm_sources": ["startup.s"]})


@pytest.mark.parametrize("override", ["HSE_VALUE 16000000U", "STM32F407xx 1"])
def test_actual_preprocessor_rejects_source_defined_macro_contradictions(tmp_path, override):
    (tmp_path / "Core/Inc").mkdir(parents=True)
    (tmp_path / "Core/Src").mkdir()
    config = tmp_path / "Core/Inc/stm32f1xx_hal_conf.h"
    config.write_text("#ifndef HSE_VALUE\n#define HSE_VALUE 8000000U\n#endif\n", encoding="utf8")
    main = tmp_path / "Core/Src/main.c"
    main.write_text('#define ' + override + '\n#include "stm32f1xx_hal_conf.h"\n', encoding="utf8")
    rcc = tmp_path / "Core/Src/stm32f1xx_hal_rcc.c"
    rcc.write_text('#include "stm32f1xx_hal_conf.h"\n', encoding="utf8")
    graph = {"complete_cube_import": True, "defines": ["STM32F103xB", "USE_HAL_DRIVER"],
             "mcu_flags": [], "include_dirs": ["Core/Inc"],
             "sources": ["Core/Src/main.c", "Core/Src/stm32f1xx_hal_rcc.c"]}
    with pytest.raises(ValueError, match="contradict"):
        _ArtifactModule_Get().EffectiveMacros_Validate(tmp_path, graph, _Compiler_Get())
    main.write_text('#include "stm32f1xx_hal_conf.h"\n', encoding="utf8")
    _ArtifactModule_Get().EffectiveMacros_Validate(tmp_path, graph, _Compiler_Get())
