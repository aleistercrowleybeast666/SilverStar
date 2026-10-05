from __future__ import annotations

import json
import shutil
import zipfile
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pytest

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.log_decoder_profile import (
    LOG_DECODER_PACKAGE_SCHEMA_ID,
)
from silverstar_fccg.generator.render import (
    GeneratedFiles_Render,
    LogDecoderProfile_Render,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
from silverstar_fccg.project.model import (
    DeviceInstance,
    ProjectModel_Load,
    ProjectModel_Save,
)
from silverstar_fccg.project.protocols import ProtocolResolution_Resolve
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.plugins.manifest import (
    PluginManifestError,
    PluginManifest_Load,
)
from tests.multi_instance_fixture import (
    MultiInstanceCatalog_Create,
    MultiInstanceProject_Create,
)


@pytest.fixture(scope="module")
def multi_instance_catalog(workspace_root: Path):
    runtime_root = workspace_root / "tests" / ".multi_instance_catalog_runtime"
    catalog = MultiInstanceCatalog_Create(workspace_root, runtime_root)
    yield catalog
    if runtime_root.is_dir():
        shutil.rmtree(runtime_root)


def test_multi_instance_cubemx_fixture_declares_required_capacity(
    workspace_root: Path,
) -> None:
    fixture = (
        workspace_root
        / "tests"
        / "fixtures"
        / "multi_instance_cubemx"
        / "MultiInstanceFlightController.ioc"
    )
    inventory = CubeMxInventory_Parse(fixture.read_text(encoding="utf-8"))

    assert len(inventory.uarts) == 5
    assert {item.instance for item in inventory.uarts} == {
        "UART4",
        "USART1",
        "USART2",
        "USART3",
        "USART6",
    }
    assert {item.instance for item in inventory.spis} == {"SPI1", "SPI2"}


def test_official_devices_declare_bounded_context_safe_repetition(
    builtin_catalog,
) -> None:
    for component_id in (
        "silverstar.device.imu.jy901b",
        "silverstar.device.gnss.neo_m9n",
        "silverstar.device.telemetry.sx1281",
    ):
        manifest = builtin_catalog.Component_Get(component_id)
        binding = manifest.instance_resource_binding

        assert manifest.instance_policy.plugin_max == 4
        assert manifest.instance_policy.class_max == 4
        assert manifest.instance_policy.same_plugin_multiple
        assert manifest.instance_policy.multi_instance_ready
        assert binding is not None
        assert binding.runtime_context_upper_bound == 4
        assert {field.requirement for field in binding.fields} == {
            requirement.name for requirement in manifest.resource_requirements
        }

    for component_id in (
        "silverstar.device.console.uart",
        "silverstar.device.storage.sd_sdio_fatfs",
    ):
        policy = builtin_catalog.Component_Get(component_id).instance_policy
        assert policy.plugin_max == 1
        assert not policy.same_plugin_multiple
        assert not policy.multi_instance_ready


def test_sx1280_hal_spi_workspaces_are_instance_owned(
    workspace_root: Path,
) -> None:
    source = (
        workspace_root
        / "plugins/builtin/silverstar_device_telemetry_sx1281/payload"
        / "Middlewares/Third_Party/SX1280lib/sx1280-hal.c"
    ).read_text(encoding="utf-8")

    assert "Sx1280HalContext s_hal_contexts[" in source
    assert "PROJECT_SX1281_INSTANCE_COUNT" in source
    assert "static uint8_t s_hal_tx_buffer" not in source
    assert "static uint8_t s_hal_rx_buffer" not in source


def test_jy901b_build_contract_enables_verified_multi_instance_overlay(
    workspace_root: Path,
) -> None:
    source = (
        workspace_root
        / "plugins/builtin/silverstar_device_imu_jy901b/payload"
        / "Devices/IMU/JY901B/Inc/jy901b_imu_build_capabilities.h"
    ).read_text(encoding="utf-8")

    assert "JY901B_BUILD_MULTI_INSTANCE_READY" in source
    assert "JY901B_BUILD_MULTI_INSTANCE_READY                        1U" in source


@pytest.mark.parametrize(
    ("mutation", "error_pattern"),
    (
        ("unknown", "invalid fields"),
        ("unsafe_accessor", "unsafe C tokens"),
        ("excess_bound", "unsafe C tokens or bounds"),
        ("missing_requirement", "map every resource requirement"),
    ),
)
def test_instance_resource_binding_contract_is_strict(
    workspace_root: Path,
    tmp_path: Path,
    mutation: str,
    error_pattern: str,
) -> None:
    source = (
        workspace_root
        / "plugins/builtin/silverstar_device_imu_jy901b/plugin.json"
    )
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["payload"]["roots"] = ["Fixture"]
    manifest["build"]["sources"] = []
    manifest["build"]["include_dirs"] = []
    (tmp_path / "payload" / "Fixture").mkdir(parents=True)
    binding = manifest["metadata"]["instance_resource_binding"]
    if mutation == "unknown":
        binding["unknown"] = True
    elif mutation == "unsafe_accessor":
        binding["accessor"] = "ProjectResources_Get();"
    elif mutation == "excess_bound":
        binding["runtime_context_upper_bound"] = 5
    else:
        binding["fields"].pop()
    target = tmp_path / f"{mutation}.json"
    target.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PluginManifestError, match=error_pattern):
        PluginManifest_Load(target, source="installed")


def test_protocol_transport_selection_rejects_unknown_policy(
    workspace_root: Path, tmp_path: Path
) -> None:
    source = (
        workspace_root
        / "plugins/builtin/silverstar_protocol_telemetry_air_m0/plugin.json"
    )
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["protocol"]["profiles"]["telemetry"][0][
        "transport_selection"
    ] = "round_robin"
    target = tmp_path / "invalid_transport_selection.json"
    target.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(
        PluginManifestError, match="protocol profile in telemetry is invalid"
    ):
        PluginManifest_Load(target, source="installed")


def test_multi_instance_model_has_distinct_resources_and_ordered_air_failover(
    multi_instance_catalog,
) -> None:
    model = MultiInstanceProject_Create(multi_instance_catalog)
    validation = Project_Validate(model, multi_instance_catalog)
    resources = ResourceAssignments_Resolve(model, multi_instance_catalog)
    protocols = ProtocolResolution_Resolve(model, multi_instance_catalog)

    assert validation.valid
    assert {issue.code for issue in validation.issues} == {
        "board_ioc",
        "board_unverified",
    }
    assert resources.valid
    for prefix in ("imu", "gnss", "telemetry"):
        first = {
            value
            for key, value in model.resource_assignments.items()
            if key.startswith(f"{prefix}0:")
        }
        second = {
            value
            for key, value in model.resource_assignments.items()
            if key.startswith(f"{prefix}1:")
        }
        assert first - {"MULTI_TIME"}
        assert second - {"MULTI_TIME"}
        assert not (first - {"MULTI_TIME"}).intersection(second - {"MULTI_TIME"})

    assert protocols.valid
    by_category = {binding.category: binding for binding in protocols.bindings}
    assert by_category["telemetry"].transport_selection == "ordered_failover"
    assert by_category["telemetry"].candidate_instances == (
        "telemetry0",
        "telemetry1",
    )
    assert by_category["maintenance"].transport_selection == "single"
    assert by_category["maintenance"].candidate_instances == ("maintenance0",)
    assert by_category["logging"].transport_selection == "single"
    assert by_category["logging"].candidate_instances == ("storage0",)


def test_multi_instance_limits_conflicts_and_round_trip(
    workspace_root: Path, multi_instance_catalog
) -> None:
    model = MultiInstanceProject_Create(multi_instance_catalog, "RoundTripMulti")
    conflicting = deepcopy(model)
    conflicting.resource_assignments["imu1:data"] = conflicting.resource_assignments[
        "imu0:data"
    ]
    conflict = ResourceAssignments_Resolve(conflicting, multi_instance_catalog)
    assert not conflict.valid
    assert any("imu1:data" in error for error in conflict.errors)

    fifth = deepcopy(model)
    fifth.device_instances.extend(
        (
            DeviceInstance("imu2", "silverstar.device.imu.jy901b"),
            DeviceInstance("imu3", "silverstar.device.imu.jy901b"),
            DeviceInstance("imu4", "silverstar.device.imu.jy901b"),
        )
    )
    issue_codes = {
        issue.code for issue in Project_Validate(fifth, multi_instance_catalog).issues
    }
    assert "device_instance_limit" in issue_codes
    assert "device_class_instance_limit" in issue_codes

    duplicate_storage = deepcopy(model)
    duplicate_storage.device_instances.append(
        DeviceInstance("storage1", "silverstar.device.storage.sd_sdio_fatfs")
    )
    issue_codes = {
        issue.code
        for issue in Project_Validate(
            duplicate_storage, multi_instance_catalog
        ).issues
    }
    assert "device_instance_limit" in issue_codes
    assert "device_same_plugin_multiple" in issue_codes

    round_trip_root = workspace_root / "tests" / ".multi_instance_round_trip"
    if round_trip_root.is_dir():
        shutil.rmtree(round_trip_root)
    round_trip_root.mkdir(parents=True)
    try:
        project_file = round_trip_root / "SilverStar.ssproject"
        ProjectModel_Save(model, project_file, WorkspacePolicy(round_trip_root))
        loaded = ProjectModel_Load(project_file)
        assert loaded.Dictionary_Get() == model.Dictionary_Get()
        assert ResourceAssignments_Resolve(
            loaded, multi_instance_catalog
        ).valid
        assert ProtocolResolution_Resolve(loaded, multi_instance_catalog).valid
    finally:
        shutil.rmtree(round_trip_root)


def test_generated_multi_instance_glue_and_decoder_are_deterministic(
    multi_instance_catalog,
) -> None:
    model = MultiInstanceProject_Create(multi_instance_catalog, "DecoderMulti")
    graph = SourceGraph_Resolve(model, multi_instance_catalog)
    generated = GeneratedFiles_Render(model, multi_instance_catalog, graph)
    second = GeneratedFiles_Render(model, multi_instance_catalog, graph)

    assert generated == second
    for source in (
        "Devices/IMU/JY901B/Src/jy901b_device.c",
        "Devices/GNSS/NEO_M9N/Src/neo_m9n_device.c",
        "Devices/Telemetry/SX1281/Src/sx1281_device.c",
    ):
        assert graph.sources.count(source) == 1

    resources = generated["Generated/Src/project_resources.c"].decode("utf-8")
    assert "PROJECT_JY901B_INSTANCE_COUNT              2U" in generated[
        "Generated/Inc/project_resources.h"
    ].decode("utf-8")
    assert "PROJECT_NEO_M9N_INSTANCE_COUNT             2U" in generated[
        "Generated/Inc/project_resources.h"
    ].decode("utf-8")
    assert "PROJECT_SX1281_INSTANCE_COUNT              2U" in generated[
        "Generated/Inc/project_resources.h"
    ].decode("utf-8")
    assert ".uart = PLATFORM_UART_1" in resources
    assert ".uart = ((PlatformUartId)3U)" in resources
    assert ".uart = ((PlatformUartId)4U)" in resources
    assert ".spi = PLATFORM_SPI_1" in resources
    assert ".spi = ((PlatformSpiId)1U)" in resources

    decoder = LogDecoderProfile_Render(model, multi_instance_catalog)
    repeat = LogDecoderProfile_Render(model, multi_instance_catalog)
    assert decoder.content == repeat.content
    with zipfile.ZipFile(BytesIO(decoder.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        semantics = json.loads(archive.read("project_semantics.json"))

    assert manifest["package_schema"]["id"] == LOG_DECODER_PACKAGE_SCHEMA_ID
    assert (manifest["package_schema"]["major"], manifest["package_schema"]["minor"]) == (
        1,
        2,
    )
    assert semantics["schema_id"] == "silverstar.project-semantics/1.2"
    device_ids = {item["instance_id"] for item in semantics["physical_devices"]}
    assert {"imu0", "imu1", "gnss0", "gnss1", "telemetry0", "telemetry1"} <= device_ids
    telemetry_binding = next(
        item
        for item in semantics["protocol_bindings"]
        if item["slot"] == "telemetry_protocol"
    )
    assert telemetry_binding["transport_selection"] == "ordered_failover"
    assert telemetry_binding["candidate_instances"] == ["telemetry0", "telemetry1"]
    assert telemetry_binding["physical_device_instance"] == "telemetry0"
    descriptor_instances = {
        (item["device_class"], item["instance_id"])
        for item in semantics["device_descriptors"]
    }
    assert ("SYSTEM_DEVICE_CLASS_IMU", 0) in descriptor_instances
    assert ("SYSTEM_DEVICE_CLASS_IMU", 1) in descriptor_instances
    assert ("SYSTEM_DEVICE_CLASS_GNSS", 0) in descriptor_instances
    assert ("SYSTEM_DEVICE_CLASS_GNSS", 1) in descriptor_instances
    assert ("SYSTEM_DEVICE_CLASS_TELEMETRY", 0) in descriptor_instances
    assert ("SYSTEM_DEVICE_CLASS_TELEMETRY", 1) in descriptor_instances
