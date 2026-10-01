from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import (
    GroundFiles_Render,
    TargetGeneration_Apply,
    TargetScope,
    _PcAdapter_Render,
    _UsbCallback_Integrate,
)
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.air_link import (
    AirLinkIssues_Get,
    GroundTargetIssues_Get,
    RadioLinkCompatible_Get,
)
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.project.model import (
    PROJECT_FORMAT_VERSION,
    DeviceInstance,
    GroundTargetConfiguration,
    HardwareConfiguration,
    HardwareResource,
    ProjectModel_Parse,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import (
    BoardHardwareInventory_Get,
    BoardResourceProvisions_Get,
)
from silverstar_fccg.project.validation import Project_Validate


def _GroundBoardProject_Get(catalog: PluginCatalog):
    model = ReferenceProject_Create("Round2Targets", catalog=catalog)
    board = catalog.Component_Get("silverstar.board.ground_station_0_5")
    inventory = BoardHardwareInventory_Get(board)
    assert board.board is not None and inventory is not None
    resources = tuple(
        HardwareResource(item.resource_id, item.kind, item.metadata)
        for item in BoardResourceProvisions_Get(board)
    )
    model.ground_target = GroundTargetConfiguration(
        enabled=True, mcu="silverstar.mcu.stm32f103c8t6", board=board.component_id,
        hardware=HardwareConfiguration(
            mode="board_plugin", source_kind=board.board.source_kind,
            mcu=inventory.mcu_part, inventory=inventory.Dictionary_Get(),
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
        pc_interface="uart", pc_resource="PLATFORM_UART_1",
    )
    return model


def test_project_root_can_exist_without_generated_targets(builtin_catalog, tmp_path: Path) -> None:
    model = ReferenceProject_Create("FolderOnly", catalog=builtin_catalog)
    root = ProjectRoot_Save(model, tmp_path / "folder_only")
    assert (root / "SilverStar.ssproject").is_file()
    assert (root / "Log").is_dir()
    assert (root / "Flight_Controller").is_dir()
    assert (root / "Ground_Station").is_dir()
    assert not (root / "Flight_Controller" / "Makefile").exists()
    assert not (root / "Ground_Station" / "Makefile").exists()
    assert not list(root.glob("*.ssdecoder"))


def test_two_targets_have_independent_hardware_and_serialization(builtin_catalog) -> None:
    model = _GroundBoardProject_Get(builtin_catalog)
    assert not GroundTargetIssues_Get(model, builtin_catalog)
    assert model.hardware is not model.ground_target.hardware
    assert model.resource_assignments is not model.ground_target.resource_assignments
    restored = ProjectModel_Parse(model.Dictionary_Get())
    assert restored.format_version == PROJECT_FORMAT_VERSION
    assert restored.ground_target == model.ground_target
    assert restored.air_link == model.air_link
    assert restored.hardware == model.hardware


def test_one_bmi088_plugin_resolves_mixed_interfaces_without_duplicate_sources(
    builtin_catalog,
) -> None:
    physical = {}
    for manifest in builtin_catalog.Type_Get("device"):
        assert manifest.physical_device is not None
        key = (
            manifest.physical_device.vendor,
            manifest.physical_device.model,
            manifest.physical_device.chipset,
        )
        assert key not in physical, (physical.get(key), manifest.component_id)
        physical[key] = manifest.component_id
    model = ReferenceProject_Create("MixedBmi088", catalog=builtin_catalog)
    model.device_instances.extend((
        DeviceInstance("bmi_i2c", "silverstar.device.imu.bmi088", "i2c", "raw_200_hz"),
        DeviceInstance("bmi_spi", "silverstar.device.imu.bmi088", "spi", "bosch_sync_400_hz"),
    ))
    view = builtin_catalog.ProjectView_Get(model)
    i2c = view.InstanceIdComponent_Get("bmi_i2c")
    spi = view.InstanceIdComponent_Get("bmi_spi")
    assert i2c.component_id == spi.component_id
    assert i2c.physical_device == spi.physical_device
    assert next(item.kind for item in i2c.resource_requirements if item.name == "data") == "i2c"
    assert next(item.kind for item in spi.resource_requirements if item.name == "data") == "spi"
    assert "路 SPI" not in spi.DisplayName_Get("zh_CN")
    combined = view.Component_Get("silverstar.device.imu.bmi088")
    assert len(combined.build.sources) == len(set(combined.build.sources))
    restored = ProjectModel_Parse(model.Dictionary_Get())
    assert restored.DeviceInstance_Get("bmi_spi") == model.DeviceInstance_Get("bmi_spi")


def test_air_link_readiness_rejects_missing_and_incompatible_radios(builtin_catalog) -> None:
    model = _GroundBoardProject_Get(builtin_catalog)
    assert not AirLinkIssues_Get(model, builtin_catalog)
    model.air_link = replace(model.air_link, frequency_hz=2400000000)
    assert "AIR_LINK_FREQUENCY_OUT_OF_RANGE" in {
        issue.code for issue in AirLinkIssues_Get(model, builtin_catalog)
    }
    model.air_link = replace(model.air_link, frequency_hz=2473000000, spreading_factor=7)
    assert "AIR_LINK_PHY_INCOMPATIBLE" in {
        issue.code for issue in AirLinkIssues_Get(model, builtin_catalog)
    }
    model.air_link = replace(model.air_link, spreading_factor=10, packet_mtu=65)
    assert "AIR_LINK_MTU_TOO_SMALL" in {
        issue.code for issue in AirLinkIssues_Get(model, builtin_catalog)
    }
    model.ground_target = replace(model.ground_target, radio_plugin="")
    assert "AIR_LINK_NO_RADIO" in {
        issue.code for issue in AirLinkIssues_Get(model, builtin_catalog)
    }
    model.ground_target = replace(model.ground_target, radio_plugin="test.ground.radio")
    reference = builtin_catalog.Component_Get("silverstar.device.telemetry.sx1281")
    assert reference.radio is not None

    class OtherRadioCatalog:
        def __init__(self, radio):
            self.radio = radio

        def Component_Get(self, component_id):
            if component_id == "test.ground.radio":
                return replace(reference, component_id=component_id, radio=self.radio)
            return builtin_catalog.Component_Get(component_id)

    incompatible = OtherRadioCatalog(replace(reference.radio, family="sx126x"))
    assert not RadioLinkCompatible_Get(
        model.air_link, incompatible.radio
    )
    assert "AIR_LINK_FAMILY_MISMATCH" in {
        issue.code for issue in AirLinkIssues_Get(model, incompatible)
    }
    separate_band = OtherRadioCatalog(replace(
        reference.radio, frequency_min_hz=2500000000, frequency_max_hz=2500000000
    ))
    assert "AIR_LINK_FREQUENCY_OUT_OF_RANGE" in {
        issue.code for issue in AirLinkIssues_Get(model, separate_band)
    }
    model.air_link = replace(model.air_link, flight_radio_instance="missing")
    assert "AIR_LINK_NO_RADIO" in {
        issue.code for issue in AirLinkIssues_Get(model, separate_band)
    }
    flight_only = ReferenceProject_Create("FlightOnlyAir", catalog=builtin_catalog)
    flight_only.air_link = replace(flight_only.air_link, crc_enabled=False)
    assert "AIR_LINK_PHY_INCOMPATIBLE" in {
        issue.code for issue in Project_Validate(flight_only, builtin_catalog).issues
    }


def test_ground_pc_interface_requires_uart_or_usb_cdc_capability(builtin_catalog) -> None:
    model = _GroundBoardProject_Get(builtin_catalog)
    assert not GroundTargetIssues_Get(model, builtin_catalog)
    model.ground_target = replace(model.ground_target, pc_resource="")
    assert "GROUND_UART_UNBOUND" in {
        issue.code for issue in GroundTargetIssues_Get(model, builtin_catalog)
    }
    model.ground_target = replace(model.ground_target, pc_interface="usb_cdc")
    assert "GROUND_USB_CDC_UNAVAILABLE" in {
        issue.code for issue in GroundTargetIssues_Get(model, builtin_catalog)
    }
    hardware = replace(
        model.ground_target.hardware,
        inventory={**model.ground_target.hardware.inventory, "usb_cdc": True},
        resources=(*model.ground_target.hardware.resources,
                   HardwareResource("USB_CDC", "usb_cdc")),
        build_sources=tuple(
            "HardwareGenerated/STM32CubeMX/USB_DEVICE/" + name
            for name in (
                "usb_device.c", "usbd_cdc_if.c", "usbd_desc.c", "usbd_conf.c",
                "usbd_core.c", "usbd_ctlreq.c", "usbd_ioreq.c", "usbd_cdc.c",
            )
        ),
    )
    model.ground_target = replace(model.ground_target, hardware=hardware)
    assert "GROUND_USB_CDC_UNAVAILABLE" not in {
        issue.code for issue in GroundTargetIssues_Get(model, builtin_catalog)
    }


def test_usb_cdc_adapter_uses_the_same_gsp_byte_stream(
    builtin_catalog, tmp_path: Path,
) -> None:
    model = _GroundBoardProject_Get(builtin_catalog)
    model.ground_target = replace(model.ground_target, pc_interface="usb_cdc")
    adapter = _PcAdapter_Render(model)
    assert "PcByteStream_Read" in adapter
    assert "PcByteStream_Write" in adapter
    assert "CDC_Transmit_FS" in adapter
    assert "USBD_BUSY" in adapter
    assert "s_rx_overflow_count" in adapter
    assert "PcByteStream_OverflowCount_Get" in adapter
    callback = (
        b'#include "usbd_cdc_if.h"\n'
        b"static int8_t CDC_Receive_FS(uint8_t *Buf, uint32_t *Len)\n"
        b"{\n  /* USER CODE BEGIN 6 */\n"
        b"  USBD_CDC_ReceivePacket(&hUsbDeviceFS);\n"
        b"  /* USER CODE END 6 */\n  return USBD_OK;\n}\n"
    )
    integrated = _UsbCallback_Integrate(callback)
    assert b"PcByteStream_OnUsbReceive(Buf, (uint16_t)*Len)" in integrated
    assert b"USBD_CDC_ReceivePacket" in integrated
    usb_root = tmp_path / "USB_DEVICE/App"
    usb_root.mkdir(parents=True)
    (usb_root / "usbd_cdc_if.c").write_bytes(callback)
    assert "USB_DEVICE/App/usbd_cdc_if.c" in CubeMxImporter._GeneratedFiles_Get(
        tmp_path
    )
    board = builtin_catalog.Component_Get("silverstar.board.silverstar_0_5")
    assert board.board is not None
    ioc = (
        board.package_root / board.board.ioc_file
    ).read_text(encoding="utf-8")
    usb_inventory = CubeMxInventory_Parse(
        ioc + "\nMcu.IP99=USB_DEVICE\nUSB_DEVICE.CLASS_NAME=CDC\n",
        generated_files={"USB_DEVICE/App/usbd_cdc_if.c": callback.decode()},
    )
    assert usb_inventory.usb_cdc
    assert any(item.kind == "usb_cdc" for item in usb_inventory.HardwareResources_Get())


def test_standalone_ground_ioc_import_is_pending_generation(
    builtin_catalog, tmp_path: Path,
) -> None:
    board = builtin_catalog.Component_Get("silverstar.board.silverstar_0_5")
    assert board.board is not None
    input_root = tmp_path / "ioc_only"
    input_root.mkdir()
    ioc = input_root / "Ground.ioc"
    ioc.write_bytes((board.package_root / board.board.ioc_file).read_bytes())
    imported = CubeMxImporter(
        WorkspacePolicy(tmp_path), cache_root=tmp_path / "import_cache"
    ).Project_Import(ioc, risk_acknowledged=True)
    assert imported.hardware.mode == "custom"
    assert imported.hardware.build_sources == ()
    assert any("generate CubeMX" in warning for warning in imported.warnings)
    model = _GroundBoardProject_Get(builtin_catalog)
    model.ground_target = replace(
        model.ground_target, board="", hardware=imported.hardware,
        resource_assignments={}, pc_resource="USART1",
    )
    assert "GROUND_CUBEMX_GENERATION_REQUIRED" in {
        issue.code for issue in GroundTargetIssues_Get(model, builtin_catalog)
    }


def test_ground_source_graph_excludes_flight_tasks_and_is_repeatable(
    builtin_catalog, workspace_root: Path, tmp_path: Path,
) -> None:
    model = _GroundBoardProject_Get(builtin_catalog)
    files = GroundFiles_Render(model, builtin_catalog, WorkspacePolicy(workspace_root))
    assert files == GroundFiles_Render(
        model, builtin_catalog, WorkspacePolicy(workspace_root)
    )
    graph = json.loads(files["Generated/ground_source_graph.json"])
    assert len(graph["sources"]) == len(set(graph["sources"]))
    assert not any(source.startswith("FATFS/") for source in graph["sources"])
    assert not any("Telemetry/SX1281/Adapter/" in source for source in graph["sources"])
    main = files["Core/Src/main.c"]
    assert b"GroundBridge_Process" in main
    assert b"AppTasks_Init" not in main
    assert b"SystemStartup_Run" not in main
    assert b"MX_FATFS_Init" not in main
    assert b"air_link_config.h" in files["Devices/Telemetry/SX1281/Inc/sx1281_config.h"]
    flight = TargetGeneration_Apply(
        model, builtin_catalog, WorkspacePolicy(workspace_root),
        tmp_path / "flight_only", TargetScope.FLIGHT,
    )
    assert flight.targets == ("Flight_Controller",)
    assert (flight.project_root / "Ground_Station").is_dir()
    assert not (flight.project_root / "Ground_Station" / "Makefile").exists()
    flight_sources = (
        flight.project_root / "Flight_Controller/Generated/project_sources.mk"
    ).read_text()
    assert "SILVERSTAR_AIR_LINK_ENABLED=1" in flight_sources
    flight_only_model = deepcopy(model)
    flight_only_model.ground_target = replace(flight_only_model.ground_target, enabled=False)
    disabled = TargetGeneration_Apply(
        flight_only_model, builtin_catalog, WorkspacePolicy(workspace_root),
        tmp_path / "ground_disabled", TargetScope.FLIGHT,
    )
    assert disabled.targets == ("Flight_Controller",)
    assert (disabled.project_root / "Ground_Station").is_dir()
    assert not (disabled.project_root / "Ground_Station" / "Makefile").exists()
    both = TargetGeneration_Apply(
        model, builtin_catalog, WorkspacePolicy(workspace_root),
        tmp_path / "both", TargetScope.ALL,
    )
    assert both.targets == ("Flight_Controller", "Ground_Station")
    assert (both.project_root / "SilverStar.ssproject").is_file()
    assert (both.project_root / "Log").is_dir()
    assert (both.project_root / "Flight_Controller/Flight_Controller.code-workspace").is_file()
    assert not (both.project_root / "FlightController").exists()
    assert not (both.project_root / "GroundStation").exists()
    decoder = both.project_root / f"{model.identity.name}.ssdecoder"
    assert decoder.is_file()
    assert json.loads((both.project_root / "SilverStar.ssproject").read_text())[
        "log_decoder_profile"
    ]["relative_path"] == decoder.name
    metadata = json.loads(
        (both.project_root / "Ground_Station/Generated/ground_target_metadata.json").read_text()
    )
    from silverstar_fccg import __version__
    assert metadata["silverstar_version"] == __version__
    assert metadata["target_role"] == "ground_station"
    assert len(metadata["hardware_fingerprint"]) == 64
    workspace = json.loads(
        (both.project_root / "Ground_Station/Ground_Station.code-workspace").read_text()
    )
    assert workspace["tasks"]["tasks"][0]["command"] == model.ground_target.build.make_command
    repeated = TargetGeneration_Apply(
        model, builtin_catalog, WorkspacePolicy(workspace_root),
        both.project_root, TargetScope.ALL,
    )
    assert repeated.file_hashes == both.file_hashes
    changed = deepcopy(model)
    changed.ground_target = replace(
        changed.ground_target,
        build=replace(changed.ground_target.build, make_command="make -j2"),
    )
    TargetGeneration_Apply(
        changed, builtin_catalog, WorkspacePolicy(workspace_root),
        both.project_root, TargetScope.GROUND,
    )
    assert b"make -j2" in (
        both.project_root / "Ground_Station/Ground_Station.code-workspace"
    ).read_bytes()
    owned = both.project_root / "Ground_Station/Generated/Inc/air_link_config.h"
    owned.write_text("user-owned edit", encoding="utf-8")
    with pytest.raises(ValueError, match="local changes"):
        TargetGeneration_Apply(
            changed, builtin_catalog, WorkspacePolicy(workspace_root),
            both.project_root, TargetScope.GROUND,
        )
