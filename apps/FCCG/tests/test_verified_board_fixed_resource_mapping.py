from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

import silverstar_fccg.generator.hardware_preparation as hardware_preparation
import silverstar_fccg.generator.render as render_module
import silverstar_fccg.project.resources as resources_module
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.hardware_preparation import (
    HardwarePreparationMetadata_Render,
    HardwareResourceBindingDescriptor_Get,
    HardwareResourceBindingFingerprint_Get,
)
from silverstar_fccg.generator.render import (
    _CustomPlatformResources_Get,
    _PlatformBinding_Render,
    _PlatformResources_Render,
)
from silverstar_fccg.project.model import HardwareConfiguration, HardwareResource
from silverstar_fccg.project.lifecycle import ProjectLifecycleState
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import (
    BoardHardwareInventory_Get,
    BoardResourceProvisions_Get,
    ResourceAssignments_Resolve,
    VERIFIED_BOARD_BINDING_ORIGIN,
)


SS05_GPIO_MAP = {
    "PLATFORM_GPIO_0": "RADIO_NSS",
    "PLATFORM_GPIO_1": "RADIO_RST",
    "PLATFORM_GPIO_2": "RADIO_BUSY",
    "PLATFORM_GPIO_3": "RADIO_DIO1",
    "PLATFORM_GPIO_4": "P_CONTROL1",
    "PLATFORM_GPIO_5": "P_CONTROL2",
    "PLATFORM_GPIO_6": "IMU_CAL_LED",
    "PLATFORM_GPIO_7": "GNSS_RST",
    "PLATFORM_GPIO_8": "GNSS_TIMEPULSE",
}


def test_ss05_fixed_connections_render_the_board_logical_map(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("VerifiedBoardGolden", catalog=builtin_catalog)
    board = builtin_catalog.Component_Get(model.board)
    provisions = {
        provision.resource_id: provision
        for provision in BoardResourceProvisions_Get(board)
    }
    assert {
        logical_id: provisions[logical_id].metadata["physical_alias"]
        for logical_id in SS05_GPIO_MAP
    } == SS05_GPIO_MAP
    for logical_id, physical_alias in SS05_GPIO_MAP.items():
        metadata = provisions[logical_id].metadata
        assert metadata["binding_origin"] == VERIFIED_BOARD_BINDING_ORIGIN
        assert metadata["logical_id"] == logical_id
        assert metadata["c_id"] == logical_id
        assert metadata["connection_fixed"] is True
        assert metadata["physical_alias"] == physical_alias
        assert "logical_index" not in metadata

    resolution = ResourceAssignments_Resolve(model, builtin_catalog)
    assert resolution.valid
    assert model.resource_assignments["launch_ignition0:output"] == (
        "PLATFORM_GPIO_4"
    )
    assert model.resource_assignments["parachute_pyro0:output"] == (
        "PLATFORM_GPIO_5"
    )
    assert model.resource_assignments["system_indicator0:output"] == (
        "PLATFORM_GPIO_6"
    )
    assert {
        model.resource_assignments[f"telemetry0:{name}"]
        for name in ("radio_nss", "radio_reset", "radio_busy", "radio_dio1")
    } == {
        "PLATFORM_GPIO_0",
        "PLATFORM_GPIO_1",
        "PLATFORM_GPIO_2",
        "PLATFORM_GPIO_3",
    }

    source = _PlatformResources_Render(model, builtin_catalog)
    for logical_id, alias in SS05_GPIO_MAP.items():
        assert f"[{logical_id}] = {{{alias}_GPIO_Port, {alias}_Pin," in source
        assert f"[{logical_id}] = 1U" in source
    assert "[PLATFORM_GPIO_4] = {P_CONTROL1_GPIO_Port, P_CONTROL1_Pin" in source
    assert "[PLATFORM_GPIO_5] = {P_CONTROL2_GPIO_Port, P_CONTROL2_Pin" in source
    assert "[PLATFORM_GPIO_6] = {IMU_CAL_LED_GPIO_Port, IMU_CAL_LED_Pin" in source


def test_verified_board_ignores_shuffled_inventory_indexes(
    builtin_catalog, monkeypatch
) -> None:
    model = ReferenceProject_Create("ShuffledInventory", catalog=builtin_catalog)
    board = builtin_catalog.Component_Get(model.board)
    inventory = BoardHardwareInventory_Get(board)
    assert inventory is not None
    original_resources = inventory.HardwareResources_Get()
    baseline_fingerprint = HardwareResourceBindingFingerprint_Get(
        model, builtin_catalog
    )

    class ShuffledInventory:
        def HardwareResources_Get(self):
            shuffled = []
            for index, resource in enumerate(reversed(original_resources)):
                shuffled.append(
                    replace(
                        resource,
                        metadata={
                            **resource.metadata,
                            "logical_index": (
                                0
                                if resource.resource_id == "IMU_CAL_LED"
                                else index
                            ),
                        },
                    )
                )
            return tuple(shuffled)

    original_get = resources_module.BoardHardwareInventory_Get

    def inventory_get(manifest):
        if manifest.component_id == board.component_id:
            return ShuffledInventory()
        return original_get(manifest)

    monkeypatch.setattr(
        resources_module, "BoardHardwareInventory_Get", inventory_get
    )
    provisions = {
        provision.resource_id: provision
        for provision in BoardResourceProvisions_Get(board)
    }
    assert provisions["PLATFORM_GPIO_6"].metadata[
        "inventory_logical_index"
    ] == 0
    assert provisions["PLATFORM_GPIO_6"].metadata[
        "fixed_logical_index"
    ] == 6
    assert HardwareResourceBindingFingerprint_Get(
        model, builtin_catalog
    ) == baseline_fingerprint
    source = _PlatformResources_Render(model, builtin_catalog)
    assert "[PLATFORM_GPIO_6] = {IMU_CAL_LED_GPIO_Port, IMU_CAL_LED_Pin" in source
    assert "[0U] = {IMU_CAL_LED_GPIO_Port, IMU_CAL_LED_Pin" not in source


def test_designator_source_differs_for_verified_board_and_custom_inventory(
    builtin_catalog,
) -> None:
    platform = builtin_catalog.Component_Get(
        "silverstar.mcu.stm32f407vet6"
    ).platform
    assert platform is not None
    gpio_binding = platform.resource_bindings["gpio"]
    physical = {
        "logical_index": 0,
        "fixed_logical_index": 6,
        "c_id": "PLATFORM_GPIO_6",
        "port": "IMU_CAL_LED_GPIO_Port",
        "pin": "IMU_CAL_LED_Pin",
    }
    verified = _PlatformBinding_Render(
        gpio_binding,
        [{**physical, "binding_origin": VERIFIED_BOARD_BINDING_ORIGIN}],
    )
    custom = _PlatformBinding_Render(gpio_binding, [physical])
    assert "[PLATFORM_GPIO_6]" in verified
    assert "[0U]" not in verified
    assert "[0U]" in custom
    assert "[PLATFORM_GPIO_6]" not in custom


def test_verified_board_alias_drift_fails_without_fallback(
    builtin_catalog, monkeypatch
) -> None:
    model = ReferenceProject_Create("AliasDrift", catalog=builtin_catalog)
    board = builtin_catalog.Component_Get(model.board)
    connection_path = board.package_root / "connections.json"
    original = json.loads(connection_path.read_text(encoding="utf-8"))
    missing = deepcopy(original)
    missing["resources"]["PLATFORM_GPIO_6"]["physical"] = "MISSING_LED"
    monkeypatch.setattr(
        resources_module, "_BoardConnections_Load", lambda _path: missing
    )
    with pytest.raises(
        ValueError,
        match=(
            r"Platform Resource Closure Check failed: logical ID "
            r"PLATFORM_GPIO_6, expected alias MISSING_LED, actual symbol "
            r"<missing>, Board plugin silverstar\.board\.silverstar_0_5"
        ),
    ):
        BoardResourceProvisions_Get(board)


def test_verified_board_duplicate_fixed_alias_is_rejected(
    builtin_catalog, monkeypatch
) -> None:
    model = ReferenceProject_Create("DuplicateAlias", catalog=builtin_catalog)
    board = builtin_catalog.Component_Get(model.board)
    connection_path = board.package_root / "connections.json"
    duplicate = json.loads(connection_path.read_text(encoding="utf-8"))
    duplicate["resources"]["PLATFORM_GPIO_6"]["physical"] = "RADIO_NSS"
    monkeypatch.setattr(
        resources_module, "_BoardConnections_Load", lambda _path: duplicate
    )
    with pytest.raises(ValueError, match="map one physical alias more than once"):
        BoardResourceProvisions_Get(board)


def test_platform_resource_closure_rejects_a_corrupted_table_entry(
    builtin_catalog, monkeypatch
) -> None:
    model = ReferenceProject_Create("ClosureFailure", catalog=builtin_catalog)
    original_get = render_module._BoardPlatformResources_Get

    def corrupted_get(board, active_resource_ids):
        collections = original_get(board, active_resource_ids)
        for entry in collections["gpios"]:
            if entry["id"] == "PLATFORM_GPIO_6":
                entry["port"] = "WRONG_LED_GPIO_Port"
        return collections

    monkeypatch.setattr(
        render_module, "_BoardPlatformResources_Get", corrupted_get
    )
    with pytest.raises(
        ValueError,
        match=(
            r"Platform Resource Closure Check failed: logical ID "
            r"PLATFORM_GPIO_6, expected alias IMU_CAL_LED, actual symbol "
            r"WRONG_LED_GPIO_Port/IMU_CAL_LED_Pin"
        ),
    ):
        _PlatformResources_Render(model, builtin_catalog)


def test_binding_fingerprint_covers_mapping_manifest_and_renderer_contract(
    builtin_catalog, monkeypatch
) -> None:
    model = ReferenceProject_Create("BindingFingerprint", catalog=builtin_catalog)
    descriptor = HardwareResourceBindingDescriptor_Get(model, builtin_catalog)
    assert descriptor["mode"] == "verified_board"
    assert descriptor["board"] == {
        "id": "silverstar.board.silverstar_0_5",
        "version": builtin_catalog.Component_Get(model.board).version,
        "manifest_sha256": builtin_catalog.Component_Get(
            model.board
        ).ManifestSha256_Get(),
    }
    system_indicator = next(
        binding
        for binding in descriptor["bindings"]
        if binding["logical_id"] == "PLATFORM_GPIO_6"
    )
    assert system_indicator["physical_alias"] == "IMU_CAL_LED"
    assert system_indicator["resolved_symbol"] == (
        "IMU_CAL_LED_GPIO_Port/IMU_CAL_LED_Pin"
    )
    assert system_indicator["physical_pin"]

    fingerprint = HardwareResourceBindingFingerprint_Get(model, builtin_catalog)
    preparation = json.loads(
        HardwarePreparationMetadata_Render(model, builtin_catalog)
    )
    assert preparation["resource_binding_fingerprint"] == fingerprint

    board = builtin_catalog.Component_Get(model.board)
    connection_path = board.package_root / "connections.json"
    changed_connections = json.loads(
        connection_path.read_text(encoding="utf-8")
    )
    launch = changed_connections["resources"]["PLATFORM_GPIO_4"]
    parachute = changed_connections["resources"]["PLATFORM_GPIO_5"]
    launch["physical"], parachute["physical"] = (
        parachute["physical"],
        launch["physical"],
    )
    original_loader = resources_module._BoardConnections_Load
    monkeypatch.setattr(
        resources_module,
        "_BoardConnections_Load",
        lambda _path: changed_connections,
    )
    assert HardwareResourceBindingFingerprint_Get(
        model, builtin_catalog
    ) != fingerprint
    monkeypatch.setattr(
        resources_module, "_BoardConnections_Load", original_loader
    )

    monkeypatch.setattr(
        hardware_preparation,
        "RESOURCE_BINDING_RENDERER_CONTRACT",
        "verified-board-fixed-v2-test",
    )
    assert HardwareResourceBindingFingerprint_Get(
        model, builtin_catalog
    ) != fingerprint


def test_binding_fingerprint_participates_in_project_readiness(
    tmp_path, workspace_root, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("BindingReadiness")
    project_root = tmp_path / "BindingReadiness"
    service.Project_Save(model, project_root)
    assert service.ProjectReadiness_Get(model, project_root).ready

    preparation = json.loads(
        (project_root / ".fccg" / "hardware-preparation.json").read_text(
            encoding="utf-8"
        )
    )
    ownership = json.loads(
        (project_root / ".fccg" / "ownership.json").read_text(
            encoding="utf-8"
        )
    )
    assert preparation["resource_binding_fingerprint"]
    assert ownership["hardware"]["resource_binding_fingerprint"] == (
        preparation["resource_binding_fingerprint"]
    )

    monkeypatch.setattr(
        hardware_preparation,
        "RESOURCE_BINDING_RENDERER_CONTRACT",
        "verified-board-fixed-v2-readiness-test",
    )
    readiness = service.ProjectReadiness_Get(model, project_root)
    assert readiness.state == ProjectLifecycleState.DIRTY
    assert ".fccg/hardware-preparation.json:resource-binding" in readiness.stale
    assert ".fccg/ownership.json:resource-binding" in readiness.stale


def test_custom_cubemx_keeps_manual_inventory_indexing(
    builtin_catalog, monkeypatch
) -> None:
    model = ReferenceProject_Create("CustomIndexing", catalog=builtin_catalog)
    model.board = ""
    model.hardware = HardwareConfiguration(
        mode="custom",
        source_kind="manual_import",
        resources=(
            HardwareResource(
                "CUSTOM_LED",
                "gpio_output",
                {
                    "c_id": "PLATFORM_GPIO_6",
                    "logical_index": 0,
                    "port": "CUSTOM_LED_GPIO_Port",
                    "pin": "CUSTOM_LED_Pin",
                },
            ),
        ),
    )
    monkeypatch.setattr(
        resources_module,
        "_BoardConnections_Load",
        lambda _path: pytest.fail("custom mode must not load Board connections"),
    )
    collections = _CustomPlatformResources_Get(model, {"CUSTOM_LED"})
    assert collections["gpios"] == [
        {
            "id": "CUSTOM_LED",
            "c_id": "PLATFORM_GPIO_6",
            "logical_index": 0,
            "port": "CUSTOM_LED_GPIO_Port",
            "pin": "CUSTOM_LED_Pin",
        }
    ]
    platform = builtin_catalog.Component_Get(model.mcu).platform
    assert platform is not None
    rendered = _PlatformBinding_Render(
        platform.resource_bindings["gpio"], collections["gpios"]
    )
    assert "[0U] = {CUSTOM_LED_GPIO_Port, CUSTOM_LED_Pin" in rendered
    assert "[PLATFORM_GPIO_6]" not in rendered
    descriptor = HardwareResourceBindingDescriptor_Get(model, builtin_catalog)
    assert descriptor["mode"] == "custom"
    assert descriptor["board"] is None
    assert descriptor["bindings"][0]["logical_index"] == 0
