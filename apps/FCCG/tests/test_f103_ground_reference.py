from __future__ import annotations

from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.model import (
    GroundTargetConfiguration,
    HardwareConfiguration,
    HardwareResource,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import (
    BoardHardwareInventory_Get,
    BoardResourceProvisions_Get,
)


def _GroundF103Model_Get(catalog):
    model = ReferenceProject_Create("F103Ground", catalog=catalog)
    board = catalog.Component_Get("silverstar.board.ground_station_0_5")
    inventory = BoardHardwareInventory_Get(board)
    assert inventory is not None and board.board is not None
    resources = tuple(
        HardwareResource(item.resource_id, item.kind, item.metadata)
        for item in BoardResourceProvisions_Get(board)
    )
    model.ground_target = GroundTargetConfiguration(
        enabled=True,
        mcu="silverstar.mcu.stm32f103c8t6",
        board=board.component_id,
        hardware=HardwareConfiguration(
            mode="board_plugin",
            source_kind=board.board.source_kind,
            mcu=inventory.mcu_part,
            inventory=inventory.Dictionary_Get(),
            resources=resources,
        ),
        radio_plugin="silverstar.device.telemetry.sx1281",
        module_variant="e28_2g4m12sx",
        resource_assignments={
            "radio0:radio_bus": "PLATFORM_SPI_1",
            "radio0:radio_nss": "PLATFORM_GPIO_0",
            "radio0:radio_reset": "PLATFORM_GPIO_1",
            "radio0:radio_busy": "PLATFORM_GPIO_2",
            "radio0:radio_dio1": "PLATFORM_GPIO_3",
            "radio0:time": "PLATFORM_TIME_1",
        },
        pc_interface="uart",
        pc_resource="PLATFORM_UART_1",
    )
    return model


def test_f103_ground_reference_has_exact_hardware_contract(builtin_catalog) -> None:
    model = _GroundF103Model_Get(builtin_catalog)
    assert not GroundTargetIssues_Get(model, builtin_catalog)
    board = builtin_catalog.Component_Get(model.ground_target.board)
    assert board.metadata["reference"]["commit"] == (
        "7fe0f61142c7360f7dbae0ac0000036315631320"
    )
    assert board.metadata["hardware_maturity"] == "hardware_validated_reference"
    assert not (board.payload_root / "Drivers").exists()
    assert not (board.payload_root / "Makefile").exists()
    exact = builtin_catalog.Component_Get(model.ground_target.mcu)
    assert exact.metadata["flash_bytes"] == 65536
    assert exact.metadata["sram_bytes"] == 20480
    assert exact.metadata["platform_family_id"] == "silverstar.mcu_family.stm32f1"


def test_f103_ground_generation_uses_f1_family_and_build_audit(
    builtin_catalog, tmp_path: Path,
) -> None:
    model = _GroundF103Model_Get(builtin_catalog)
    result = TargetGeneration_Apply(
        model, builtin_catalog, WorkspacePolicy(tmp_path),
        tmp_path / "project", TargetScope.GROUND,
    )
    ground = result.project_root / "Ground_Station"
    makefile = (ground / "Makefile").read_text(encoding="utf-8")
    assert "Platform/STM32F1/Inc" in makefile
    assert "Platform/STM32F4/Inc" not in makefile
    assert "startup_stm32f103xb.s" in makefile
    assert "-fstack-usage" in makefile
    assert "ground.map" in makefile
    assert "ground.size" in makefile
    main = (ground / "Core/Src/main.c").read_text(encoding="utf-8")
    assert "GroundBridge_Init()" in main
    assert "GroundBridge_Process(HAL_GetTick())" in main
    assert "legacy" not in main.casefold()
