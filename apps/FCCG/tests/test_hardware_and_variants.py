from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath

import pytest

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.render import (
    ComponentProvenance_Get,
    GeneratedFiles_Render,
    MetadataFiles_Render,
    _PlatformResources_Render,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.hardware import (
    BoardPluginExporter,
    CubeMxImporter,
    CubeMxImportError,
)
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.installer import PluginInstaller
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.logging import LoggingProfile_Reconcile
from silverstar_fccg.project.model import DeviceInstance, HardwareConfiguration
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.validation import Project_Validate


def _Catalog_Create(workspace_root: Path, installed_root: Path) -> PluginCatalog:
    catalog = PluginCatalog(workspace_root / "plugins" / "builtin", installed_root)
    catalog.Scan()
    return catalog


def _TopLevelYamlList_Get(text: str, key: str) -> tuple[str, ...]:
    lines = text.splitlines()
    start = lines.index(f"{key}:") + 1
    values: list[str] = []
    for line in lines[start:]:
        if not line.startswith("  - "):
            break
        values.append(line[4:])
    return tuple(values)


def test_estimator_none_is_absent_from_make_and_eide(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("NoEstimator")
    model.strategies["estimator"] = None
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    # The selected INS implementation itself provides qualified vertical velocity,
    # so deployment availability is independent of whether KF6 is selected.
    assert "ApogeeVerticalVelocity" in model.modes["deployment"]
    validation = Project_Validate(model, builtin_catalog)
    assert validation.valid

    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert not any("Algorithm/Estimator/KF6" in source for source in graph.sources)
    assert "APP/Src/estimator_task.c" in graph.sources
    assert "APP/Src/estimator_task.c" not in graph.exclude_sources
    assert "SYSTEM_BUILD_FUSION_ALGORITHM=SYSTEM_FUSION_NONE" in graph.defines
    assert "SYSTEM_BUILD_ESTIMATOR_ENABLED=0U" in graph.defines

    make_graph = graph.MakeFragment_Render()
    eide = MetadataFiles_Render(model, builtin_catalog, graph)[
        ".eide/eide.yml"
    ].decode("utf-8")
    assert "Algorithm/Estimator/KF6" not in make_graph
    assert "Algorithm/Estimator/KF6" not in eide
    assert "SYSTEM_FUSION_NONE" in make_graph
    assert "SYSTEM_FUSION_NONE" in eide

    core = builtin_catalog.Component_Get("silverstar.core.0_1_0")
    estimator_header = (
        core.payload_root / "APP" / "Inc" / "estimator_task.h"
    ).read_text(encoding="utf-8")
    estimator_source_path = core.payload_root / "APP" / "Src" / "estimator_task.c"
    assert not (core.payload_root / "APP" / "Src" / "estimator_task_none.c").exists()
    estimator_source = estimator_source_path.read_text(encoding="utf-8")
    assert "AppTask_Estimator" in estimator_header
    for header_root in ("APP/Inc", "System/Inc", "Common/Inc",
                        "Modules/Inc", "Interfaces/Inc"):
        for header in (core.payload_root / header_root).rglob("*.h"):
            content = header.read_text(encoding="utf-8")
            assert '#include "navigation_kf.h"' not in content, header
            assert '#include "navigation_kf_replay.h"' not in content, header
            assert "Algorithm/Estimator/KF6/" not in content, header
    assert "return (uint8_t)(SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE);" in estimator_source


def test_environment_plugin_renders_one_resolved_source_graph(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("EnvironmentTruth")
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "APP/Src/estimator_task.c" in graph.sources
    assert "APP/Src/estimator_task_none.c" not in graph.sources
    assert not any("estimator_task_none.c" in path for path in graph.sources)
    metadata = MetadataFiles_Render(model, builtin_catalog, graph)
    expected_outputs = {
        "Flight_Controller.code-workspace",
        ".vscode/tasks.json",
        ".vscode/settings.json",
        ".vscode/extensions.json",
        ".eide/eide.yml",
        ".eide/files.options.yml",
        "Makefile",
        "Targets/SilverStar_F407/target.mk",
    }
    assert expected_outputs.issubset(metadata)

    eide = metadata[".eide/eide.yml"].decode("utf-8")
    actual_source_dirs = _TopLevelYamlList_Get(eide, "srcDirs")
    expected_source_dirs = tuple(
        dict.fromkeys(
            PurePosixPath(source).parent.as_posix()
            for source in graph.sources
            if source not in graph.virtual_sources
        )
    )
    assert actual_source_dirs == expected_source_dirs
    assert "srcDirs: []" not in eide
    assert "outDir: build\\FCCG\\SilverStar_F407\\EIDE" in eide
    assert "uploadConfigMap" in eide
    assert "uploader: OpenOCD" in eide
    assert "uploader: JLink" not in eide
    assert "OpenOCD" in eide
    assert "STLink" in eide
    assert "deviceName: null" in eide
    assert "packDir: null" in eide
    for include_dir in graph.include_dirs:
        assert include_dir in eide
    for define in graph.defines:
        assert define in eide
    assert graph.linker_script in eide
    workspace = json.loads(
        metadata["Flight_Controller.code-workspace"].decode("utf-8")
    )
    assert set(workspace) == {"folders", "settings", "extensions"}
    assert workspace["folders"] == [
        {"name": "EnvironmentTruth", "path": "."}
    ]
    assert workspace["extensions"]["recommendations"]
    assert "mingw32-make" in metadata[".vscode/tasks.json"].decode("utf-8")
    for source in graph.sources:
        assert source in graph.MakeFragment_Render()


def test_same_mcu_supports_two_board_resource_maps(workspace_root: Path) -> None:
    catalog = PluginCatalog(
        workspace_root / "plugins" / "builtin",
        workspace_root / "tests" / "fixtures" / "board_variants",
    )
    catalog.Scan()
    graphs = []
    mappings: list[dict[str, str]] = []
    platform_sources: list[str] = []
    mcu_provenance = ComponentProvenance_Get(
        catalog, "silverstar.mcu.stm32f407vet6"
    )

    for board_id in ("fixture.board.f407_a", "fixture.board.f407_b"):
        model = ReferenceProject_Create(board_id.rsplit("_", 1)[-1].upper())
        model.device_instances = [
            DeviceInstance("imu0", "silverstar.device.imu.jy901b"),
            DeviceInstance("gnss0", "silverstar.device.gnss.neo_m9n"),
            DeviceInstance(
                "voltage_monitor0", "silverstar.device.sensor.input_voltage"
            ),
            DeviceInstance(
                "launch_ignition0",
                "silverstar.device.actuator.launch_ignition",
            ),
            DeviceInstance(
                "parachute_pyro0",
                "silverstar.device.actuator.parachute_pyro",
            ),
        ]
        model.board = board_id
        platform = catalog.Component_Get(model.mcu)
        assert platform.platform is not None
        model.hardware = HardwareConfiguration(
            mode="board_plugin",
            source_kind="third_party",
            platform_component=platform.component_id,
            platform_version=platform.version,
            platform_manifest_sha256=platform.ManifestSha256_Get(),
            cubemx_version="6.15.0",
            firmware_package="STM32Cube FW_F4 V1.28.3",
            hal_cmsis_source_policy=(
                platform.platform.compatibility.source_policy
            ),
        )
        model.resource_assignments = {}
        resolution = ResourceAssignments_Resolve(model, catalog, auto_assign=True)
        assert resolution.valid
        LoggingProfile_Reconcile(model, catalog)
        validation = Project_Validate(model, catalog)
        assert any(
            issue.code == "log_sink_cardinality"
            for issue in validation.issues
        )
        graph = SourceGraph_Resolve(model, catalog)
        graphs.append(graph)
        mappings.append(dict(model.resource_assignments))
        platform_sources.append(_PlatformResources_Render(model, catalog))

    imu_key = "imu0:data"
    gnss_key = "gnss0:data"
    assert (mappings[0][imu_key], mappings[0][gnss_key]) == ("USART1", "USART2")
    assert (mappings[1][imu_key], mappings[1][gnss_key]) == ("USART3", "USART6")
    assert graphs[0] == graphs[1]
    assert platform_sources[0] != platform_sources[1]
    assert "&huart1" in platform_sources[0] and "&huart2" in platform_sources[0]
    assert "&huart3" in platform_sources[1] and "&huart6" in platform_sources[1]
    assert ComponentProvenance_Get(
        catalog, "silverstar.mcu.stm32f407vet6"
    ) == mcu_provenance


def test_optional_logical_devices_render_safe_disabled_resource_bindings(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("OptionalLogicalDevicesOff")
    model.modes["deployment"] = []
    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.plugin
        not in {
            "silverstar.device.sensor.input_voltage",
            "silverstar.device.actuator.parachute_pyro",
        }
    ]

    reconciled = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert "silverstar.device.sensor.input_voltage" not in (
        reconciled.DevicePluginIds_Get()
    )
    assert "silverstar.device.actuator.parachute_pyro" not in (
        reconciled.DevicePluginIds_Get()
    )
    assert Project_Validate(reconciled, builtin_catalog).valid

    graph = SourceGraph_Resolve(reconciled, builtin_catalog)
    header = GeneratedFiles_Render(reconciled, builtin_catalog, graph)[
        "Generated/Inc/project_resources.h"
    ].decode("utf-8")
    defines = {
        parts[1]: parts[2]
        for line in header.splitlines()
        if len(parts := line.split()) == 3 and parts[0] == "#define"
    }
    assert defines["PROJECT_RESOURCE_INPUT_VOLTAGE_ADC"] == "PLATFORM_ADC_COUNT"
    assert (
        defines["PROJECT_RESOURCE_PARACHUTE_PYRO_OUTPUT"]
        == "PLATFORM_GPIO_COUNT"
    )
    assert defines["PROJECT_FEATURE_INPUT_VOLTAGE_MONITOR"] == "0U"
    assert defines["PROJECT_FEATURE_PARACHUTE_PYRO_OUTPUT"] == "0U"


def test_cubemx_import_generate_export_install_and_reuse(
    tmp_path: Path, workspace_root: Path
) -> None:
    policy = WorkspacePolicy(tmp_path)
    installed_root = tmp_path / "plugins" / "installed"
    catalog = _Catalog_Create(workspace_root, installed_root)
    importer = CubeMxImporter(policy)
    fixture = workspace_root / "tests" / "fixtures" / "cubemx_minimal"

    model = ReferenceProject_Create("CustomHardware")
    imported = importer.Project_Import(
        fixture,
        expected_mcu="STM32F407VET6",
        risk_acknowledged=True,
    )
    model.board = ""
    model.hardware = imported.hardware
    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.plugin
        not in {
            "silverstar.device.indicator.system_status",
            "silverstar.device.storage.sd_sdio_fatfs",
        }
    ]
    model.resource_assignments = {}
    resources = ResourceAssignments_Resolve(model, catalog, auto_assign=True)
    assert resources.valid
    LoggingProfile_Reconcile(model, catalog)
    assert len(resources.assignments) == 19
    assert imported.snapshot_root.is_relative_to(tmp_path)
    assert imported.hardware.provider == "silverstar.hardware_provider.stm32_cubemx"
    assert imported.hardware.build_sources == (
        "HardwareGenerated/STM32CubeMX/Core/Src/main.c",
    )
    validation = Project_Validate(model, catalog)
    assert not validation.valid
    assert any(issue.code == "protocol_transport" for issue in validation.issues)
    assert any(issue.code == "log_sink_cardinality" for issue in validation.issues)
    assert any(issue.code == "hardware_timebase" for issue in validation.issues)
    assert any(issue.code == "hardware_manual" for issue in validation.issues)

    assembler = ProjectAssembler(policy, catalog)
    first_root = tmp_path / "generated" / "CustomHardware"
    first_plan = assembler.Plan(model, first_root)
    assert not first_plan.validation.valid
    assert not first_plan.dangerous

    archive = BoardPluginExporter(policy).Plugin_Export(
        model,
        imported.snapshot_root,
        tmp_path / "artifacts" / "mock_f407.ssplugin",
        component_id="local.board.mock_f407",
        name="Mock F407",
    )
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
    assert "plugin.json" in names
    assert "connections.json" in names
    assert "docs/HARDWARE_PROVENANCE.md" in names
    assert "hardware/MockFlightController.ioc" in names
    assert "payload/HardwareGenerated/STM32CubeMX/MockFlightController.ioc" in names

    installed = PluginInstaller(policy, installed_root, catalog).Install(archive)
    assert installed.component_id == "local.board.mock_f407"
    second = ReferenceProject_Create("ReusedBoard")
    second.board = installed.component_id
    second.hardware = HardwareConfiguration(
        mode="board_plugin", source_kind="manual_import"
    )
    second.device_instances = [
        instance
        for instance in second.device_instances
        if instance.plugin
        not in {
            "silverstar.device.indicator.system_status",
            "silverstar.device.storage.sd_sdio_fatfs",
        }
    ]
    second.resource_assignments = {}
    second_resources = ResourceAssignments_Resolve(
        second, catalog, auto_assign=True
    )
    assert second_resources.valid
    LoggingProfile_Reconcile(second, catalog)
    second_validation = Project_Validate(second, catalog)
    assert not second_validation.valid
    assert any(
        issue.code == "protocol_transport" for issue in second_validation.issues
    )
    installed_manifest = catalog.Component_Get(installed.component_id)
    assert (
        installed_manifest.payload_root
        / "HardwareGenerated"
        / "STM32CubeMX"
        / "MockFlightController.ioc"
    ).is_file()
    assert second.hardware.mode == "board_plugin"
    assert second.hardware.snapshot_id == ""


def test_cubemx_freertos_conflict_is_rejected(
    tmp_path: Path, workspace_root: Path
) -> None:
    fixture = workspace_root / "tests" / "fixtures" / "cubemx_minimal"
    conflict = tmp_path / "cubemx_rtos_conflict"
    shutil.copytree(fixture, conflict)
    ioc = conflict / "MockFlightController.ioc"
    ioc.write_text(
        ioc.read_text(encoding="utf-8") + "\nMcu.IP8=FREERTOS\n",
        encoding="utf-8",
    )
    with pytest.raises(CubeMxImportError, match="FreeRTOS/CMSIS-RTOS2"):
        CubeMxImporter(WorkspacePolicy(tmp_path)).Project_Import(
            conflict,
            expected_mcu="STM32F407VET6",
            risk_acknowledged=True,
        )
