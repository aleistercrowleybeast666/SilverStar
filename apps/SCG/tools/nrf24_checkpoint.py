"""Fresh small NRF24 software fixture; no Cube installation or user project copy.

Uses only selected built-in Core/FATFS application files; HAL/CMSIS/RTOS come
from normal selected plugins. Changes the example CE initial level in both IOC
and GPIO source. This is a synthetic rewiring fixture, HARDWARE_UNVERIFIED.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import BoardHardwareInventory_Get, BoardResourceProvisions_Get
from silverstar_fccg.project.model import HardwareConfiguration, HardwareResource, GroundTargetConfiguration
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.project.nrf24 import NRF24_PLUGIN


def Nrf24Hardware_Create(catalog, board_id, policy):
    board = catalog.Component_Get(board_id)
    inventory = BoardHardwareInventory_Get(board)
    files = {p.relative_to(board.payload_root).as_posix(): p.read_bytes()
             for p in board.PayloadFiles_Get()
             if p.relative_to(board.payload_root).parts[0] in {"Core", "FATFS"} or p.suffix == ".ioc"}
    # Actual reference reset pin is rewired to CE only in this example snapshot.
    gpio_path = "Core/Src/gpio.c"
    gpio = files[gpio_path].decode("utf8")
    old = "HAL_GPIO_WritePin(RADIO_RST_GPIO_Port, RADIO_RST_Pin, GPIO_PIN_SET);"
    assert gpio.count(old) == 1
    files[gpio_path] = gpio.replace(old, old.replace("GPIO_PIN_SET", "GPIO_PIN_RESET")).encode("utf8")
    ioc_path = next(path for path in files if path.endswith(".ioc"))
    ioc = files[ioc_path].decode("utf8").replace("\r\n", "\n")
    import re
    reset_pin = next(match[1] for match in re.finditer(r"(?m)^([A-Z]+\d+)\.GPIO_Label=RADIO_RST$", ioc))
    setting = reset_pin + ".PinState=GPIO_PIN_RESET"
    ioc = re.sub(r"(?m)^" + reset_pin + r"\.PinState=.*$", setting, ioc)
    if setting not in ioc:
        ioc += "\n" + setting + "\n"
    files[ioc_path] = ioc.encode("utf8")
    digest = hashlib.sha256(b"".join(path.encode() + hashlib.sha256(data).digest() for path, data in sorted(files.items()))).hexdigest()
    snapshot = policy.root / ".fccg/hardware_imports" / digest / "STM32CubeMX"
    assert not snapshot.exists(), "Use a fresh output directory for this checkpoint"
    for path, data in files.items():
        dest = snapshot / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    resources = []
    for provision in BoardResourceProvisions_Get(board):
        metadata = dict(provision.metadata)
        for key in tuple(metadata):
            if key.startswith("binding_") or key.startswith("connection_"):
                metadata.pop(key)
        if provision.resource_id == "PLATFORM_GPIO_1":
            metadata.update(initial_level="low", output_default="low")
        resources.append(HardwareResource(provision.resource_id, provision.kind, metadata))
    return HardwareConfiguration(mode="custom", source_kind="manual_import",
        provider="silverstar.hardware_provider.stm32_cubemx", snapshot_id=digest,
        ioc_file=ioc_path, mcu=inventory.mcu_part,
        cubemx_version=inventory.cubemx_version, firmware_package=inventory.firmware_package,
        hal_cmsis_source_policy="plugin_payload_authoritative",
        resources=tuple(resources), inventory=inventory.Dictionary_Get(),
        build_sources=tuple("HardwareGenerated/STM32CubeMX/" + path for path in board.build.sources),
        include_dirs=tuple("HardwareGenerated/STM32CubeMX/" + path for path in board.build.include_dirs),
        source_digest=digest, source_label="NRF24 software-only CE rewiring fixture", risk_acknowledged=True)


def Nrf24Model_Create(catalog, policy):
    model = ReferenceProject_Create("Nrf24Checkpoint", catalog=catalog)
    model.hardware = Nrf24Hardware_Create(catalog, model.board, policy)
    model.board = ""
    model.device_instances = [replace(item, plugin=NRF24_PLUGIN, module_variant="nrf24l01p", tx_power_dbm=0)
        if item.instance_id == model.air_link.flight_radio_instance else item for item in model.device_instances]
    owner = model.air_link.flight_radio_instance
    model.resource_assignments = {key: value for key, value in model.resource_assignments.items() if not key.startswith(owner + ":")}
    model.resource_assignments.update({owner + ":" + key: value for key, value in
        {"radio_bus": "PLATFORM_SPI_1", "radio_csn": "PLATFORM_GPIO_0", "radio_ce": "PLATFORM_GPIO_1", "time": "PLATFORM_TIME_1"}.items()})
    model.air_link = replace(model.air_link, radio_family="nrf24", radio_technology="esb", phy_mode="esb",
        nrf24={"data_rate_kbps": 1000, "address": "E7E7E7E701", "retry_delay_us": 1000, "retry_count": 3})
    ground_hw = Nrf24Hardware_Create(catalog, "silverstar.board.ground_station_0_5", policy)
    model.ground_target = GroundTargetConfiguration(enabled=True, mcu="silverstar.mcu.stm32f103c8t6",
        hardware=ground_hw, radio_plugin=NRF24_PLUGIN, module_variant="nrf24l01p", tx_power_dbm=0,
        resource_assignments={"radio0:" + key: value for key, value in
            {"radio_bus": "PLATFORM_SPI_1", "radio_csn": "PLATFORM_GPIO_0", "radio_ce": "PLATFORM_GPIO_1", "time": "PLATFORM_TIME_1"}.items()},
        pc_interface="uart", pc_resource="PLATFORM_UART_1")
    return model


if __name__ == "__main__":
    output = Path(sys.argv[1]).resolve()
    assert not output.exists(), "Use a fresh output directory"
    output.mkdir(parents=True)
    policy = WorkspacePolicy(output / "internal")
    catalog = PluginCatalog(ROOT / "plugins/builtin", ROOT / "plugins/installed")
    catalog.Scan()
    model = Nrf24Model_Create(catalog, policy)
    (output / "configuration.json").write_text(json.dumps(model.Dictionary_Get(), indent=2), encoding="utf8")
    for issue in Project_Validate(replace(model, ground_target=replace(model.ground_target, enabled=False)), catalog).issues:
        print(issue)
    result = TargetGeneration_Apply(model, catalog, policy, output / "project", TargetScope.ALL if "--paired" in sys.argv[2:] else TargetScope.FLIGHT)
    print(result)
