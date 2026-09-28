from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from test_joint_sensor_library import (
    GNSS_MODELS,
    IMU_MODELS,
    SPECIAL_IMU_MODELS,
    SPI_IMU_MODELS,
    SYNC_IMU_MODELS,
    _ImuVariant_Get,
    _Command_Run,
)

from silverstar_fccg.project.model import DeviceInstance


def _SensorInventory_Create():
    from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
    lines = [
        "Mcu.CPN=STM32F407VET6", "Mcu.Name=STM32F407V(E-G)Tx", "Mcu.Family=STM32F4",
        "Mcu.Package=LQFP100", "Mcu.Core=ARM Cortex-M4", "Mcu.IP0=I2C1", "Mcu.IP1=SPI2", "Mcu.IP2=USART1", "Mcu.IP3=USART2",
        "PB6.Signal=I2C1_SCL", "PB7.Signal=I2C1_SDA", "I2C1.ClockSpeed=400000", "I2C1.AddressingMode=I2C_ADDRESSINGMODE_7BIT",
        "PB6.GPIO_PuPd=GPIO_PULLUP", "PB7.GPIO_PuPd=GPIO_PULLUP", "PB6.GPIO_OutputType=GPIO_MODE_AF_OD", "PB7.GPIO_OutputType=GPIO_MODE_AF_OD",
        "PB13.Signal=SPI2_SCK", "PB14.Signal=SPI2_MISO", "PB15.Signal=SPI2_MOSI",
        "SPI2.Mode=SPI_MODE_MASTER", "SPI2.Direction=SPI_DIRECTION_2LINES", "SPI2.DataSize=SPI_DATASIZE_8BIT",
        "SPI2.CLKPolarity=SPI_POLARITY_LOW", "SPI2.CLKPhase=SPI_PHASE_1EDGE", "SPI2.FirstBit=SPI_FIRSTBIT_MSB",
        "SPI2.BaudRatePrescaler=SPI_BAUDRATEPRESCALER_64", "SPI2.CalculateBaudRate=656.25 KBits/s", "RCC.APB1Freq_Value=42000000",
        "PA9.Signal=USART1_TX", "PA10.Signal=USART1_RX", "USART1.BaudRate=115200",
        "USART1.WordLength=WORDLENGTH_8B", "USART1.Parity=PARITY_NONE", "USART1.StopBits=STOPBITS_1",
        "NVIC.USART1_IRQn=true\\:5\\:0\\:false\\:false\\:true",
        "Dma.Request0=USART1_RX", "Dma.USART1_RX.0.Instance=DMA2_Stream2", "Dma.USART1_RX.0.Channel=DMA_CHANNEL_4",
        "Dma.USART1_RX.0.Direction=DMA_PERIPH_TO_MEMORY", "Dma.USART1_RX.0.Mode=DMA_CIRCULAR", "Dma.USART1_RX.0.Priority=DMA_PRIORITY_HIGH",
        "PD5.Signal=USART2_TX", "PD6.Signal=USART2_RX", "USART2.BaudRate=230400", "USART2.WordLength=WORDLENGTH_8B",
        "USART2.Parity=PARITY_NONE", "USART2.StopBits=STOPBITS_1", "NVIC.USART2_IRQn=true\\:5\\:0\\:false\\:false\\:true",
        "Dma.Request1=USART2_RX", "Dma.USART2_RX.0.Instance=DMA1_Stream5", "Dma.USART2_RX.0.Channel=DMA_CHANNEL_4",
        "Dma.USART2_RX.0.Direction=DMA_PERIPH_TO_MEMORY", "Dma.USART2_RX.0.Mode=DMA_CIRCULAR", "Dma.USART2_RX.0.Priority=DMA_PRIORITY_HIGH",
    ]
    for pin in ("PC0", "PC1"):
        lines += [f"{pin}.Signal=GPIO_Output", f"{pin}.GPIO_ModeDefaultOutputPP=GPIO_MODE_OUTPUT_PP",
                  f"{pin}.GPIO_PuPd=GPIO_NOPULL", f"{pin}.GPIO_Speed=GPIO_SPEED_FREQ_LOW", f"{pin}.PinState=GPIO_PIN_SET", f"{pin}.Locked=true"]
    lines += ["PC4.Signal=GPIO_Output", "PC4.GPIO_ModeDefaultOutputPP=GPIO_MODE_OUTPUT_PP", "PC4.GPIO_PuPd=GPIO_NOPULL",
              "PC4.GPIO_Speed=GPIO_SPEED_FREQ_LOW", "PC4.PinState=GPIO_PIN_RESET", "PC4.Locked=true"]
    for pin, index in (("PC2", 2), ("PC3", 3)):
        lines += [f"{pin}.Signal=GPIO_EXTI{index}", f"{pin}.GPIO_ModeDefaultEXTI=GPIO_MODE_IT_RISING", f"{pin}.GPIO_PuPd=GPIO_NOPULL",
                  f"NVIC.EXTI{index}_IRQn=true\\:5\\:0\\:false\\:false\\:true"]
    return CubeMxInventory_Parse("\n".join(lines))


DEVICES = [("imu", name.lower()) for name in IMU_MODELS + SPECIAL_IMU_MODELS + SPI_IMU_MODELS + SYNC_IMU_MODELS]
DEVICES += [("gnss", name) for name in GNSS_MODELS]


def _GnssNavigationModel_Create(catalog, component_id: str, output: Path):
    from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
    from silverstar_fccg.project.reference import ReferenceProject_Create

    model = ReferenceProject_Create("GeneratedGnss", catalog=catalog)
    board = catalog.Component_Get(model.board)
    original_ioc = board.package_root / model.hardware.ioc_file
    ioc = original_ioc.read_text(encoding="utf-8").replace("USART2.BaudRate=921600", "USART2.BaudRate=115200")
    assert ioc != original_ioc.read_text(encoding="utf-8")
    generated_files: dict[str, str] = {}
    for directory in ("Core", "FATFS"):
        for source in (board.payload_root / directory).rglob("*"):
            if source.is_file() and source.suffix in (".h", ".c"):
                relative = source.relative_to(board.payload_root).as_posix()
                content = source.read_text(encoding="utf-8")
                if relative.endswith("usart.c"):
                    content = content.replace("huart2.Init.BaudRate = 921600", "huart2.Init.BaudRate = 115200")
                generated_files[relative] = content
                destination = output / "HardwareGenerated/STM32CubeMX" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
    (output / "HardwareGenerated/STM32CubeMX" / original_ioc.name).write_text(ioc, encoding="utf-8")
    inventory = CubeMxInventory_Parse(ioc, generated_files=generated_files)
    model.device_instances = [DeviceInstance(instance.instance_id, component_id)
                              if instance.plugin == "silverstar.device.gnss.neo_m9n" else instance
                              for instance in model.device_instances]
    connections = json.loads((board.package_root / "connections.json").read_text(encoding="utf-8"))["resources"]
    model.resource_assignments = {key: connections[value]["physical"] for key, value in model.resource_assignments.items()
                                  if not key.startswith("gnss0:") or key.endswith((":data", ":time"))}
    digest = hashlib.sha256(ioc.encode("utf-8")).hexdigest()
    model.hardware = replace(model.hardware, mode="custom", source_kind="manual_import", snapshot_id=digest,
                             source_digest=digest, inventory=inventory.Dictionary_Get(), resources=inventory.HardwareResources_Get(),
                             risk_acknowledged=True,
                             build_sources=tuple("HardwareGenerated/STM32CubeMX/" + path for path in generated_files if path.endswith(".c")),
                             include_dirs=("HardwareGenerated/STM32CubeMX/Core/Inc", "HardwareGenerated/STM32CubeMX/FATFS/App", "HardwareGenerated/STM32CubeMX/FATFS/Target"))
    model.board = ""
    return model


def test_gpio_mode_token_preserves_push_pull_and_open_drain() -> None:
    from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
    inventory = CubeMxInventory_Parse("\n".join([
        "Mcu.CPN=STM32F407VET6", "PC0.Signal=GPIO_Output", "PC0.GPIO_ModeDefaultOutputPP=GPIO_MODE_OUTPUT_PP", "PC0.PinState=GPIO_PIN_SET",
        "PC1.Signal=GPIO_Output", "PC1.GPIO_ModeDefaultOutputPP=GPIO_MODE_OUTPUT_OD", "PC1.PinState=GPIO_PIN_RESET",
    ]))
    assert {pin.pin: pin.output_type for pin in inventory.pins} == {"PC0": "push_pull", "PC1": "open_drain"}
    assert {pin.pin: pin.output_default for pin in inventory.pins} == {"PC0": "high", "PC1": "low"}


def test_bmi088_sync_binding_requires_declared_nets_and_invalidates_fingerprint(builtin_catalog) -> None:
    from test_internal_platform_refactor import _CustomModel_Create

    from silverstar_fccg.generator.hardware_preparation import (
        HardwareAssignmentFingerprint_Get,
        HardwareResourceBindingFingerprint_Get,
    )
    from silverstar_fccg.project.resources import ResourceAssignments_Resolve

    model = _CustomModel_Create(builtin_catalog, [DeviceInstance(
        "sync0", "silverstar.device.imu.bmi088", "i2c", "bosch_sync_400_hz"
    )])
    model.resource_assignments = {"sync0:data": "I2C1", "sync0:gyro": "I2C1", "sync0:time": "SYSTEM_TIME",
                                  "sync0:drdy": "PC2", "sync0:auxiliary_drdy": "PC3"}
    inventory = _SensorInventory_Create()
    model.hardware = replace(model.hardware, inventory=inventory.Dictionary_Get(), resources=inventory.HardwareResources_Get())
    unbound = ResourceAssignments_Resolve(model, builtin_catalog)
    assert not unbound.valid
    assert any("pin_label" in error and "BMI088_G_INT3_A_INT1_SYNC_NET" in error for error in unbound.errors)
    absent = HardwareResourceBindingFingerprint_Get(model, builtin_catalog)
    inventory = replace(inventory, pins=tuple(replace(pin, label={
        "PC2": "BMI088_A_INT2_SYNC_READY", "PC3": "BMI088_G_INT3_A_INT1_SYNC_NET"
    }.get(pin.pin, pin.label)) for pin in inventory.pins))
    model.resource_assignments.update({"sync0:drdy": "BMI088_A_INT2_SYNC_READY",
                                       "sync0:auxiliary_drdy": "BMI088_G_INT3_A_INT1_SYNC_NET"})
    model.hardware = replace(model.hardware, inventory=inventory.Dictionary_Get(), resources=inventory.HardwareResources_Get())
    assert ResourceAssignments_Resolve(model, builtin_catalog).valid
    bound = HardwareResourceBindingFingerprint_Get(model, builtin_catalog)
    confirmed = HardwareAssignmentFingerprint_Get(model, builtin_catalog)
    assert bound != absent
    inventory = replace(inventory, pins=tuple(replace(pin, label="DISCONNECTED") if pin.pin == "PC3" else pin for pin in inventory.pins))
    model.hardware = replace(model.hardware, inventory=inventory.Dictionary_Get(), resources=inventory.HardwareResources_Get())
    assert not ResourceAssignments_Resolve(model, builtin_catalog).valid
    assert HardwareResourceBindingFingerprint_Get(model, builtin_catalog) != bound
    assert HardwareAssignmentFingerprint_Get(model, builtin_catalog) != confirmed


def test_bmi088_sync_qualification_cannot_be_borrowed_for_raw_source(builtin_catalog) -> None:
    from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
    from silverstar_fccg.project.reference import ReferenceProject_Create

    model = ReferenceProject_Create("SyncQualified", catalog=builtin_catalog)
    model.device_instances.insert(0, DeviceInstance(
        "sync0", "silverstar.device.imu.bmi088", "i2c", "bosch_sync_400_hz"
    ))
    assert not CapabilityResolution_Resolve(model, builtin_catalog).source_conflicts
    model.device_instances.insert(0, DeviceInstance("raw0", "silverstar.device.imu.bmi088"))
    conflicts = CapabilityResolution_Resolve(model, builtin_catalog).source_conflicts
    assert conflicts and any("raw0" in text and "sync0" in text for text in conflicts)


def test_bmi088_sync_image_is_exact_pinned_bosch_blob_and_license() -> None:
    import re

    from test_joint_sensor_library import BUILTIN, FIXTURES

    vendor = FIXTURES / "vendor_reference/BMI08x_SensorAPI"
    original = re.search(r"const uint8_t bmi08x_config_file\[\] = \{(.*?)\};",
                         (vendor / "bmi08xa.c").read_text(encoding="utf-8"), re.DOTALL)
    assert original is not None
    actual = BUILTIN / "silverstar_sensor_register_bus/payload/Devices/SensorBus"
    image = (actual / "Src/bmi088_sync_image.inc").read_text(encoding="utf-8")
    expected_bytes = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", original.group(1)))
    actual_bytes = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", image))
    assert actual_bytes == expected_bytes and len(actual_bytes) == 6144
    assert hashlib.sha256(actual_bytes).hexdigest() == "996efc7079e75bc0b93f302f520e8a3bfa74c147b0a28fd6a2306d74a690fe88"
    assert "BSD-3-Clause" in (actual / "BMI088_SYNC_LICENSE.txt").read_text(encoding="utf-8")
    _, sync_i2c, _, _ = _ImuVariant_Get("BMI088_SYNC400")
    _, sync_spi, _, _ = _ImuVariant_Get("BMI088_SYNC400_SPI")
    assert sync_i2c.component_id == sync_spi.component_id == "silverstar.device.imu.bmi088"
    assert sync_i2c.metadata["source_origins"]["default"] == "fccg_joint_sensor_library"
    assert sync_spi.metadata["source_origins"]["default"] == "fccg_joint_sensor_library"


@pytest.mark.parametrize(("kind", "name"), DEVICES)
def test_each_sensor_real_generated_graph_compiles(builtin_catalog, tmp_path: Path, kind: str, name: str) -> None:
    from test_internal_rc_closeout import _CustomStorageModel_Get

    from silverstar_fccg.generator.render import GeneratedFiles_Render
    from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
    from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
    from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
    from silverstar_fccg.project.resources import (
        BoardHardwareInventory_Get,
        ResourceAssignments_Resolve,
    )
    if kind == "imu":
        folder, manifest, interface, profile = _ImuVariant_Get(name)
        component_id = manifest.component_id
        selected_instance = DeviceInstance("sensor0", component_id, interface, profile)
    else:
        component_id = "silverstar.device." + kind + "." + name
        manifest = builtin_catalog.Component_Get(component_id)
        selected_instance = DeviceInstance("sensor0", component_id)
    model = _CustomStorageModel_Get(builtin_catalog)
    model.device_instances.insert(0, selected_instance)
    model.device_instances.append(DeviceInstance("launch_fixture", "silverstar.device.actuator.launch_ignition"))
    model.resource_assignments.update({"launch_fixture:output": "PC4", "launch_fixture:time": "SYSTEM_TIME"})
    if kind == "gnss":
        model.device_instances.append(DeviceInstance("aux_imu", "silverstar.device.imu.jy901b"))
        model.resource_assignments.update({"aux_imu:data": "USART2", "aux_imu:time": "SYSTEM_TIME"})
    inventory = _SensorInventory_Create()
    if "sync400" in name:
        inventory = replace(inventory, pins=tuple(replace(pin, label={
            "PC2": "BMI088_A_INT2_SYNC_READY", "PC3": "BMI088_G_INT3_A_INT1_SYNC_NET"
        }.get(pin.pin, pin.label)) for pin in inventory.pins))
    board = builtin_catalog.Component_Get("silverstar.board.silverstar_0_5")
    storage_inventory = BoardHardwareInventory_Get(board)
    assert storage_inventory is not None
    inventory = replace(inventory, fatfs=storage_inventory.fatfs, timebase=storage_inventory.timebase,
                        peripherals=inventory.peripherals + ("SDIO", "FATFS", storage_inventory.timebase.instance),
                        pins=inventory.pins + tuple(pin for pin in storage_inventory.pins if pin.signal.startswith("SDIO_")),
                        dmas=inventory.dmas + tuple(dma for dma in storage_inventory.dmas if dma.request.startswith("SDIO_")),
                        nvic=inventory.nvic + tuple(irq for irq in storage_inventory.nvic if irq.irq in ("SDIO_IRQn", storage_inventory.timebase.irq)))
    model.hardware = replace(model.hardware, inventory=inventory.Dictionary_Get(), resources=inventory.HardwareResources_Get())
    # No unrelated strategy can borrow a qualification from a different source.
    model.strategies = {slot: None for slot in model.strategies}
    model.base_components.remove("silverstar.flight_logic.cycle.reference")
    model.modes = {slot: [] for slot in model.modes}
    model.protocols = {slot: None for slot in model.protocols}
    model.capability_source_overrides = {}
    aliases = {"time": "SYSTEM_TIME", "gyro": "I2C1", "cs": "PC0", "auxiliary_cs": "PC1", "drdy": "PC2", "auxiliary_drdy": "PC3"}
    aliases["data"] = "USART1" if kind == "gnss" else ("SPI2" if name.endswith("_spi") else "I2C1")
    model.resource_assignments.update({"sensor0:" + requirement.name: aliases[requirement.name] for requirement in manifest.resource_requirements})
    if kind == "gnss":
        # A separate CubeMX fixture changes the GNSS UART consistently in IOC
        # and generated init C. The real reference firmware is never modified.
        model = _GnssNavigationModel_Create(builtin_catalog, component_id, tmp_path)
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    resources = ResourceAssignments_Resolve(model, builtin_catalog)
    assert resources.valid, resources.errors
    capabilities = CapabilityResolution_Resolve(model, builtin_catalog)
    assert capabilities.valid, (capabilities.missing, capabilities.invalid_overrides, capabilities.source_conflicts)
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert set(manifest.build.sources).issubset(graph.sources)
    files = GeneratedFiles_Render(model, builtin_catalog, graph)
    for relative, content in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for relative in model.hardware.include_dirs:
        original = board.payload_root / relative.removeprefix("HardwareGenerated/STM32CubeMX/")
        if original.is_dir() and kind != "gnss":
            shutil.copytree(original, tmp_path / relative, dirs_exist_ok=True)
    (tmp_path / "resolved_graph.json").write_text(json.dumps({"component": component_id, "assignments": model.resource_assignments, "sources": graph.sources, "includes": graph.include_dirs}, indent=2), encoding="utf-8")
    selected = [builtin_catalog.Component_Get(key) for key in model.ComponentIds_Get()]
    includes: list[Path] = []
    for relative in graph.include_dirs:
        candidates = [tmp_path / relative] + [item.payload_root / relative for item in selected]
        includes += [path for path in candidates if path.is_dir()]
    assert tmp_path / "Generated/Inc" in includes
    # Only source-graph include directories from selected packages are visible.
    compiler = os.environ.get("FCCG_TEST_ARM_GCC") or shutil.which("arm-none-eabi-gcc")
    assert compiler, "Real ARM GCC is required for the generated STM32 sensor matrix"
    command = [compiler, *graph.mcu_flags, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-c"]
    command += ["-I" + str(path) for path in dict.fromkeys(includes)]
    command += ["-D" + definition for definition in graph.defines]
    for header in graph.forced_includes:
        candidates = [tmp_path / header] + [item.payload_root / header for item in selected]
        command += ["-include", str(next(path for path in candidates if path.is_file()))]
    sources = [path for path in graph.sources if path.startswith("Devices/")]
    sources += ["Generated/Src/project_resources.c", "Generated/Src/project_device_instances.c"]
    for index, relative in enumerate(sources):
        candidates = [tmp_path / relative] + [item.payload_root / relative for item in selected]
        source = next(path for path in candidates if path.is_file())
        _Command_Run(command + [str(source), "-o", str(tmp_path / f"generated_{index}.o")], tmp_path, f"compile_{index}")
    if kind == "gnss":
        assert "Devices/GNSS/UBX/Src/ubx_receiver.c" in sources
        assert "Devices/GNSS/NEO_M9N/Src/neo_m9n_device.c" not in graph.sources
        assert model.resource_assignments["gnss0:data"] != model.resource_assignments["imu0:data"]
    if name.endswith("_spi"):
        assert "Platform/STM32F4/Src/platform_spi_stm32f4.c" in graph.sources
    if kind == "imu" and not name.endswith("_spi"):
        assert "Platform/STM32F4/Src/platform_i2c_stm32f4.c" in graph.sources
