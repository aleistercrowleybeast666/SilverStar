"""Synthetic adapted CubeMX wiring; never a PCB or flight acceptance claim."""
from dataclasses import replace
from pathlib import Path
import shutil

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.project.resources import BoardResourceProvisions_Get
from silverstar_fccg.project.radio_variants import RADIO_PLUGIN, EBYTE_VARIANTS
from test_round2_targets import _GroundBoardProject_Get


def _Input_Create(catalog, model, board_id, root, pins):
    board = catalog.Component_Get(board_id)
    source = board.payload_root
    root.mkdir(parents=True)
    for directory in ("Core", "FATFS"):
        if (source / directory).is_dir(): shutil.copytree(source / directory, root / directory)
    family = catalog.Component_Get(catalog.Component_Get(model.mcu).metadata["platform_family_id"])
    shutil.copytree(family.payload_root / "Drivers", root / "Drivers")
    mcu = catalog.Component_Get(model.mcu)
    for relative in (*mcu.build.asm_sources, mcu.build.linker_script):
        shutil.copyfile(mcu.payload_root / relative, root / Path(relative).name)
    ioc = next(source.glob("*.ioc")).read_text(encoding="utf8")
    main = (root / "Core/Inc/main.h").read_text(encoding="utf8")
    gpio = (root / "Core/Src/gpio.c").read_text(encoding="utf8")
    import re
    count = int(re.search(r"Mcu.PinsNb=(\d+)", ioc)[1])
    extra, init = [], []
    for index, (physical, name) in enumerate(zip(pins, ("RF_RX_EN", "RF_TX_EN"))):
        assert physical + ".Signal=" not in ioc
        bank, pin = physical[:2], int(physical[2:])
        extra.extend([f"Mcu.Pin{count + index}={physical}", f"{physical}.Signal=GPIO_Output",
            f"{physical}.GPIOParameters=GPIO_Label", f"{physical}.GPIO_Label={name}",
            f"{physical}.GPIO_ModeDefaultOutputPP=GPIO_MODE_OUTPUT_PP", f"{physical}.GPIO_PuPd=GPIO_NOPULL",
            f"{physical}.GPIO_Speed=GPIO_SPEED_FREQ_LOW", f"{physical}.PinState=GPIO_PIN_RESET", f"{physical}.Locked=true"])
        main += f"\n#define {name}_Pin GPIO_PIN_{pin}\n#define {name}_GPIO_Port GPIO{bank[1]}\n"
        init.extend([f"  HAL_GPIO_WritePin(GPIO{bank[1]}, GPIO_PIN_{pin}, GPIO_PIN_RESET);",
            f"  GPIO_InitStruct.Pin = GPIO_PIN_{pin};", "  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;",
            "  GPIO_InitStruct.Pull = GPIO_NOPULL;", "  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;",
            f"  HAL_GPIO_Init(GPIO{bank[1]}, &GPIO_InitStruct);"])
    ioc = ioc.replace(f"Mcu.PinsNb={count}", f"Mcu.PinsNb={count + 2}") + "\n" + "\n".join(extra)
    gpio = gpio.replace("  /* EXTI interrupt init*/", "\n".join(init) + "\n  /* EXTI interrupt init*/", 1)
    (root / "SyntheticRadio.ioc").write_text(ioc, encoding="utf8")
    (root / "Core/Inc/main.h").write_text(main, encoding="utf8")
    (root / "Core/Src/gpio.c").write_text(gpio, encoding="utf8")
    return board


def RadioVariantFixture_Create(catalog, root: Path):
    model = _GroundBoardProject_Get(catalog)
    board = _Input_Create(catalog, model, model.board, root / "flight_input", ("PC1", "PC2"))
    service = FccgService(Path(__file__).resolve().parents[1])
    imported = CubeMxImporter(WorkspacePolicy(root)).Project_Import(root / "flight_input", risk_acknowledged=True)
    mapping = {item.resource_id: item.metadata["physical_resource"] for item in BoardResourceProvisions_Get(board)}
    model.resource_assignments = {key: mapping[value] for key, value in model.resource_assignments.items()}
    model.hardware = imported.hardware
    model.board = ""
    ground = model.ground_target
    ground_model = replace(model, mcu=ground.mcu)
    board = _Input_Create(catalog, ground_model, ground.board, root / "ground_input", ("PA8", "PA11"))
    imported = CubeMxImporter(WorkspacePolicy(root)).Project_Import(root / "ground_input", risk_acknowledged=True)
    mapping = {item.resource_id: item.metadata["physical_resource"] for item in BoardResourceProvisions_Get(board)}
    assignments = {key: mapping[value] for key, value in ground.resource_assignments.items()}
    model.ground_target = replace(ground, board="", hardware=imported.hardware,
        resource_assignments=assignments, pc_resource="USART1")
    return service.ProjectConfiguration_Reconcile(model).model


def RadioVariantFixture_Apply(model, module):
    capability = EBYTE_VARIANTS[module]
    for index, instance in enumerate(model.device_instances):
        if instance.plugin == RADIO_PLUGIN:
            model.device_instances[index] = replace(instance, module_variant=module, tx_power_dbm=capability.nominal_output_dbm)
            if capability.external_frontend:
                model.resource_assignments.update({instance.instance_id + ":radio_rx_en": "RF_RX_EN",
                    instance.instance_id + ":radio_tx_en": "RF_TX_EN"})
    ground = model.ground_target
    model.ground_target = replace(ground, module_variant=module, tx_power_dbm=capability.nominal_output_dbm,
        resource_assignments={**ground.resource_assignments, **({"radio0:radio_rx_en": "RF_RX_EN",
            "radio0:radio_tx_en": "RF_TX_EN"} if capability.external_frontend else {})})
    return model
