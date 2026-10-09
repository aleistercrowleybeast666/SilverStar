from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImporter, CubeMxImportError
from silverstar_fccg.hardware.cubemx_ground import GroundCubeInputs_Get, _UsbClock_Validate
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.generator.multi_target import _GroundModel_Get
from silverstar_fccg.generator.assembler import ProjectAssembler, ProjectAssemblerError
from silverstar_fccg.hardware.platform import PlatformCompatibilityErrors_Get
from test_round2_targets import _GroundBoardProject_Get


def _Cube_Get(root: Path) -> Path:
    """Minimal data fixture, never presented as a compiled MCU project."""
    files = {
        "test.ioc": "Mcu.CPN=STM32F103C8T6\nMcu.Family=STM32F1\nMcu.Name=STM32F103C8Tx\nMcu.Package=LQFP48\nMcu.IP0=RCC\nMxCube.Version=6.15.0\nProjectManager.FirmwarePackage=STM32Cube FW_F1 V1.8.7\n",
        "Core/Src/main.c": "int main(void) { return 0; }\n",
        "Core/Inc/main.h": "#include <stdint.h>\n",
        "Drivers/CMSIS/core_cm3.h": "/* fixture */\n",
        "Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal.c": "/* fixture */\n",
        "Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal.h": "/* fixture */\n",
        "startup_stm32f103xb.s": "/* fixture */\n",
        "STM32F103XX_FLASH.ld": "MEMORY\n{\nFLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K\nRAM (xrw) : ORIGIN = 0x20000000, LENGTH = 20K\n}\n",
        "Makefile": "C_SOURCES = Core/Src/main.c Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal.c\nASM_SOURCES = startup_stm32f103xb.s\nLDSCRIPT = STM32F103XX_FLASH.ld\nC_INCLUDES = -ICore/Inc -IDrivers/STM32F1xx_HAL_Driver/Inc -IDrivers/CMSIS\nC_DEFS = -DUSE_HAL_DRIVER -DSTM32F103xB\nCPU = -mcpu=cortex-m3\n",
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf8")
    return root


def test_ground_import_registers_one_vendor_base_and_detects_snapshot_change(builtin_catalog, tmp_path):
    cube = _Cube_Get(tmp_path / "cube")
    policy = WorkspacePolicy(tmp_path / "w")
    result = CubeMxImporter(policy).Project_Import(cube, target="ground")
    assert result.hardware.hal_cmsis_source_policy == "imported_tree_authoritative"
    model = _GroundBoardProject_Get(builtin_catalog)
    original = model.ground_target.hardware
    model.ground_target = replace(model.ground_target, board="", hardware=replace(
        result.hardware, resources=original.resources,
        inventory={**original.inventory, **result.hardware.inventory}))
    ground = _GroundModel_Get(model, builtin_catalog)
    graph = SourceGraph_Resolve(ground, builtin_catalog)
    assert graph.asm_sources == result.hardware.asm_sources
    assert graph.linker_script == result.hardware.linker_script
    assert not any(path.startswith("Drivers/") for path in (*graph.sources, *graph.include_dirs))
    assembler = ProjectAssembler(policy, builtin_catalog)
    assert assembler._HardwareFiles_Get(ground)
    (result.snapshot_root / "Core/Src/main.c").write_text("/* changed */", encoding="utf8")
    with pytest.raises(ProjectAssemblerError, match="snapshot changed"):
        assembler._HardwareFiles_Get(ground)


@pytest.mark.parametrize(("old", "new", "reason"), [
    ("Core/Src/main.c Drivers", "../outside.c Drivers", "Unsupported"),
    ("Core/Src/main.c Drivers", "$(shell echo unsafe) Drivers", "expressions"),
    ("Core/Src/main.c Drivers", "Core/Src/missing.c Drivers", "dependency missing"),
    ("64K", "128K", "memory contract"),
    ("-mcpu=cortex-m3", "-mcpu=cortex-m4", "CPU"),
    ("startup_stm32f103xb.s", "startup_stm32f407xx.s", "matching GNU startup"),
])
def test_ground_import_rejects_incomplete_unsafe_or_wrong_build(tmp_path, old, new, reason):
    cube = _Cube_Get(tmp_path / "cube")
    path = cube / ("STM32F103XX_FLASH.ld" if old == "64K" else "Makefile")
    path.write_text(path.read_text(encoding="utf8").replace(old, new), encoding="utf8")
    with pytest.raises(ValueError, match=reason):
        GroundCubeInputs_Get(cube, "STM32F103C8T6")


def test_directory_ambiguity_and_ioc_only_ground_are_rejected(tmp_path):
    cube = _Cube_Get(tmp_path / "cube")
    importer = CubeMxImporter(WorkspacePolicy(tmp_path / "workspace"))
    (cube / "second.ioc").write_text("Mcu.CPN=STM32F103C8T6", encoding="utf8")
    with pytest.raises(CubeMxImportError, match="exactly one"):
        importer.Project_Import(cube, target="ground")
    with pytest.raises(CubeMxImportError, match="exactly one"):
        importer.Project_Import(cube / "test.ioc", target="ground")
    only = tmp_path / "only"
    only.mkdir()
    (only / "test.ioc").write_text("Mcu.CPN=STM32F103C8T6", encoding="utf8")
    with pytest.raises(CubeMxImportError, match="generated CubeMX project"):
        importer.Project_Import(only, target="ground")
    assert importer.Project_Import(only).hardware.hal_cmsis_source_policy == ""


def test_import_policy_is_allowed_for_ground_only(builtin_catalog):
    mcu = builtin_catalog.Component_Get("silverstar.mcu.stm32f103c8t6")
    args = dict(cubemx_version="6.15.0", firmware_package="STM32Cube FW_F1 V1.8.7",
                source_policy="imported_tree_authoritative")
    assert PlatformCompatibilityErrors_Get(mcu, **args)
    assert not PlatformCompatibilityErrors_Get(mcu, allow_ground_imported=True, **args)


@pytest.mark.parametrize("f1,clock,old,new", [
    (True, "PLLSource = RCC_PLLSOURCE_HSE; HSEPredivValue = RCC_HSE_PREDIV_DIV1; PLLMUL = RCC_PLL_MUL9;", "MUL9", "MUL8"),
    (False, "PLLSource = RCC_PLLSOURCE_HSE; PLLM = 8; PLLN = 336; PLLQ = 7;", "PLLQ = 7", "PLLQ = 8"),
])
def test_usb_clock_is_calculated_from_generated_hse_and_pll(tmp_path, f1, clock, old, new):
    main = tmp_path / "Core/Src/main.c"
    main.parent.mkdir(parents=True)
    main.write_text(clock, encoding="utf8")
    _UsbClock_Validate(tmp_path, "#define HSE_VALUE 8000000U", f1)
    main.write_text(clock.replace(old, new), encoding="utf8")
    with pytest.raises(ValueError, match="48000000"):
        _UsbClock_Validate(tmp_path, "#define HSE_VALUE 8000000U", f1)
