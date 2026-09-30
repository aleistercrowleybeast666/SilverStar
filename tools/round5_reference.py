"""Create and identify the Round 5 software reference under ignored .work/."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from silverstar_fccg.plugins.catalog import PluginCatalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FCCG_ROOT = REPOSITORY_ROOT / "apps" / "FCCG"
sys.path.insert(0, str(FCCG_ROOT / "src"))

PROJECT_NAME = "Round5_Field_Qualification"
GROUND_BOARD_ID = "silverstar.board.ground_station_0_5"


def Round5Path_Validate(project_root: Path) -> Path:
    root = project_root.resolve()
    work_root = (REPOSITORY_ROOT / ".work").resolve()
    if root == work_root or not root.is_relative_to(work_root):
        raise ValueError("Round 5 generated project must stay below repository .work/")
    return root


def Round5Catalog_Load() -> PluginCatalog:
    from silverstar_fccg.plugins.catalog import PluginCatalog

    catalog = PluginCatalog(
        FCCG_ROOT / "plugins" / "builtin",
        FCCG_ROOT / "plugins" / "installed",
    )
    catalog.Scan()
    return catalog


def Round5Model_Create(catalog: PluginCatalog):
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
    from silverstar_fccg.project.validation import Project_Validate

    model = ReferenceProject_Create(PROJECT_NAME, catalog=catalog)
    board = catalog.Component_Get(GROUND_BOARD_ID)
    inventory = BoardHardwareInventory_Get(board)
    if inventory is None or board.board is None:
        raise ValueError("Ground Station 0.5 board lacks its hardware snapshot")
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
    if GroundTargetIssues_Get(model, catalog):
        raise ValueError("Ground target is not generation ready")
    validation = Project_Validate(model, catalog)
    if not validation.valid:
        raise ValueError(f"Reference project validation failed: {validation.issues}")
    return model


def Round5Project_Generate(project_root: Path) -> dict[str, object]:
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.generator.multi_target import (
        TargetGeneration_Apply,
        TargetScope,
    )
    from silverstar_fccg.project.folder_contract import ProjectRoot_Save

    root = Round5Path_Validate(project_root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fresh Round 5 generation requires an empty project root")
    catalog = Round5Catalog_Load()
    model = Round5Model_Create(catalog)
    ProjectRoot_Save(model, root)
    result = TargetGeneration_Apply(
        model, catalog, WorkspacePolicy(FCCG_ROOT), root, TargetScope.ALL
    )
    required = (
        root / "SilverStar.ssproject",
        root / f"{PROJECT_NAME}.ssdecoder",
        root / "Flight_Controller" / "Flight_Controller.code-workspace",
        root / "Ground_Station" / "Ground_Station.code-workspace",
        root / "Log",
    )
    if any(not path.exists() for path in required):
        raise ValueError("Fresh generation did not fulfill the project folder contract")
    return {"project_root": str(root), "targets": result.targets}


def Round5File_Hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def Round5Artifacts_Record(project_root: Path) -> dict[str, object]:
    from silverstar_fccg.project.build_audit import BuildAudit_Run

    root = Round5Path_Validate(project_root)
    flight_elf = root / "Flight_Controller/build/FCCG/SilverStar_F407/Release/SilverStar_0_1_0.elf"
    flight_bin = flight_elf.with_suffix(".bin")
    ground_elf = root / "Ground_Station/build/ground.elf"
    ground_bin = root / "Ground_Station/build/ground.bin"
    named = {
        "project": root / "SilverStar.ssproject",
        "decoder": root / f"{PROJECT_NAME}.ssdecoder",
        "flight_elf": flight_elf,
        "flight_bin": flight_bin,
        "ground_elf": ground_elf,
        "ground_bin": ground_bin,
    }
    missing = [name for name, path in named.items() if not path.is_file()]
    if missing:
        raise ValueError(f"Cannot freeze missing built artifacts: {missing}")
    catalog = Round5Catalog_Load()
    audits = {
        "flight": BuildAudit_Run(
            flight_elf, flight_elf.with_suffix(".map"),
            root / "Flight_Controller/STM32F407XX_FLASH.ld",
            flight_elf.parent,
            catalog.Component_Get("silverstar.mcu.stm32f407vet6").metadata,
        ),
        "ground": BuildAudit_Run(
            ground_elf, ground_elf.with_suffix(".map"),
            root / "Ground_Station/STM32F103XX_FLASH.ld",
            root / "Ground_Station/build",
            catalog.Component_Get("silverstar.mcu.stm32f103c8t6").metadata,
        ),
    }
    if any(audit.errors for audit in audits.values()):
        raise ValueError({name: audit.errors for name, audit in audits.items()})
    return {
        "project_root": str(root),
        "files": {
            name: {"relative_path": path.relative_to(root).as_posix(),
                   "sha256": Round5File_Hash(path), "bytes": path.stat().st_size}
            for name, path in named.items()
        },
        "build_audits": {
            name: asdict(audit) for name, audit in audits.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("generate", "record"))
    parser.add_argument(
        "--project-root", type=Path,
        default=REPOSITORY_ROOT / ".work/round5/Round5_Field_Qualification",
    )
    args = parser.parse_args()
    if args.action == "generate":
        result = Round5Project_Generate(args.project_root)
    else:
        result = Round5Artifacts_Record(args.project_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
