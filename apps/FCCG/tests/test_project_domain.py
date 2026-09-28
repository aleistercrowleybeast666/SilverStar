from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from silverstar_fccg.build.runner import BuildAction, BuildRunner
from silverstar_fccg.build.toolchain import (
    ArmGnuSubtoolPaths_Derive,
    ToolchainDetector,
)
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.render import ProjectDigest_Get
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.model import (
    ProjectModel_Load,
    ProjectModel_Parse,
    ProjectModel_Save,
    ProjectModelError,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.validation import Project_Validate


def test_reference_project_json_round_trip(tmp_path: Path, builtin_catalog) -> None:
    model = ReferenceProject_Create("Domain_Roundtrip")
    model.build = replace(
        model.build,
        tool_paths={"compiler": str(tmp_path / "Arm Toolchain" / "gcc.exe")},
    )
    policy = WorkspacePolicy(tmp_path)
    path = ProjectModel_Save(model, tmp_path / "SilverStar.ssproject", policy)
    loaded = ProjectModel_Load(path)
    assert loaded.Dictionary_Get() == model.Dictionary_Get()
    assert Project_Validate(loaded, builtin_catalog).valid


def test_manual_tool_paths_drive_detection_and_make_arguments(tmp_path: Path) -> None:
    model = ReferenceProject_Create()
    portable_digest = ProjectDigest_Get(model)
    model.build = replace(
        model.build,
        tool_paths={
            "make": str(tmp_path / "tools" / "make.exe"),
            "compiler": str(tmp_path / "Arm Toolchain" / "arm-none-eabi-gcc.exe"),
            "objcopy": str(tmp_path / "Arm Toolchain" / "arm-none-eabi-objcopy.exe"),
        },
    )
    command = BuildRunner(WorkspacePolicy(tmp_path)).Command_Get(
        model, BuildAction.BUILD
    )
    assert command[0].endswith("make.exe")
    gcc_path = next(argument for argument in command if argument.startswith("GCC_PATH="))
    assert gcc_path == f"GCC_PATH={(tmp_path / 'Arm Toolchain').resolve().as_posix()}"
    assert not any(argument.startswith("CP=") for argument in command)
    assert ProjectDigest_Get(model) == portable_digest
    assert ToolchainDetector._Version_Compatible(
        "compiler", "arm-none-eabi-gcc (Arm GNU Toolchain) 14.3.1"
    )
    assert not ToolchainDetector._Version_Compatible(
        "compiler", "clang version 20"
    )


def test_arm_gnu_subtools_are_derived_from_the_compiler_directory(
    tmp_path: Path,
) -> None:
    bin_root = tmp_path / "Arm GNU" / "bin"
    bin_root.mkdir(parents=True)
    compiler = bin_root / "arm-none-eabi-gcc.exe"
    objcopy = bin_root / "arm-none-eabi-objcopy.exe"
    size = bin_root / "arm-none-eabi-size.exe"
    for path in (compiler, objcopy, size):
        path.write_bytes(b"fixture")

    assert ArmGnuSubtoolPaths_Derive(str(compiler)) == {
        "objcopy": str(objcopy.resolve()),
        "size": str(size.resolve()),
    }
    assert set(ToolchainDetector.TOOL_COMMANDS) == {
        "compiler",
        "make",
        "host_gcc",
    }


def test_project_loader_is_strict(tmp_path: Path) -> None:
    path = tmp_path / "bad.ssproject"
    path.write_text('{"format_version": 7}', encoding="utf-8")
    with pytest.raises(ProjectModelError):
        ProjectModel_Load(path)

    data = ReferenceProject_Create().Dictionary_Get()
    data["build"]["target_profile"] = "../../escape"
    with pytest.raises(ProjectModelError, match="target profile"):
        ProjectModel_Parse(data)

    data = ReferenceProject_Create().Dictionary_Get()
    data["logging"]["streams"][0]["record"] = "BAD\nmake:"
    with pytest.raises(ProjectModelError, match="record contains control characters"):
        ProjectModel_Parse(data)


def test_dependency_and_resource_conflicts_are_reported(builtin_catalog) -> None:
    model = ReferenceProject_Create()
    model.base_components.remove("silverstar.algorithm.common")
    validation = Project_Validate(model, builtin_catalog)
    assert not validation.valid
    assert any(issue.code == "dependency" for issue in validation.issues)

    model = ReferenceProject_Create()
    model.resource_assignments["maintenance0:console"] = "PLATFORM_UART_1"
    resources = ResourceAssignments_Resolve(model, builtin_catalog)
    assert not resources.valid
    assert any("not an allowed candidate" in error for error in resources.errors)

    model = ReferenceProject_Create()
    model.logging_streams.reverse()
    validation = Project_Validate(model, builtin_catalog)
    assert not validation.valid
    assert any(issue.code == "logging_records" for issue in validation.issues)


def test_source_graph_is_complete_and_has_one_truth(builtin_catalog) -> None:
    graph = SourceGraph_Resolve(ReferenceProject_Create(), builtin_catalog)
    assert len(graph.sources) == 143
    assert "Algorithm/Common/Src/navigation_quality.c" in graph.sources
    assert "System/Src/system_navigation_health.c" in graph.sources
    assert "Devices/IMU/JY901B/Adapter/Src/jy901b_sample_quality.c" in graph.sources
    assert "Algorithm/Estimator/KF6/Src/navigation_integrity.c" in graph.sources
    assert "Algorithm/Estimator/KF6/Src/navigation_kf_replay.c" in graph.sources
    assert len(graph.sources) == len(set(graph.sources))
    assert "APP/Src/diagnostic_log.c" in graph.sources
    assert "APP/Src/device_task.c" in graph.sources
    assert "APP/Src/telemetry_task.c" in graph.sources
    assert graph.asm_sources == ("startup_stm32f407xx.s",)
    assert "USE_HAL_DRIVER" in graph.defines
    assert "STM32F407xx" in graph.defines
    assert "SYSTEM_BUILD_FUSION_ALGORITHM=SYSTEM_FUSION_KF6" in graph.defines
    assert graph.forced_includes == (
        "Targets/SilverStar_F407/Inc/platform_memory_target.h",
        "Generated/Inc/project_flight_config.h",
    )
    assert graph.exclude_sources == (
        "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_mmc.c",
        "Platform/STM32F4/Src/platform_i2c_stm32f4.c",
        "Platform/STM32F4/Src/platform_can_stm32f4.c",
        "Platform/STM32F4/Src/platform_pwm_stm32f4.c",
        "Core/Src/sysmem.c",
        "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c.c",
        "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c_ex.c",
        "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_can.c",
        "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd.c",
        "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd_ex.c",
        "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_usb.c",
    )
    assert graph.linker_script == "STM32F407XX_FLASH.ld"
    fragment = graph.MakeFragment_Render()
    assert "wildcard" not in fragment
    assert "Generated/Src/project_metadata.c" in fragment
    assert "Generated/Src/project_capability_routes.c" in fragment
    assert "Generated/Src/project_log_decoder_profile.c" in fragment
