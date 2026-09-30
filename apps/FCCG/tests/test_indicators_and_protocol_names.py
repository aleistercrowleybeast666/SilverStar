from __future__ import annotations

import json
from pathlib import Path

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.view_models import ToolchainToolView
from silverstar_fccg.generator.render import GeneratedFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.model import (
    DeviceInstance,
    HardwareConfiguration,
    HardwareResource,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.ui.main_window import MainWindow

SYSTEM_INDICATOR_ID = "silverstar.device.indicator.system_status"
GNSS_INDICATOR_ID = "silverstar.device.indicator.gnss_status"


def test_indicator_devices_match_ss05_physical_truth(builtin_catalog) -> None:
    model = ReferenceProject_Create("IndicatorTruth", catalog=builtin_catalog)
    assert model.DeviceInstance_Get("system_indicator0") == DeviceInstance(
        "system_indicator0", SYSTEM_INDICATOR_ID
    )
    assert GNSS_INDICATOR_ID not in model.DevicePluginIds_Get()
    assert model.resource_assignments["system_indicator0:output"] == (
        "PLATFORM_GPIO_6"
    )

    board = builtin_catalog.Component_Get(model.board)
    assert "unsupported_optional_devices" not in board.metadata
    role = next(
        item
        for item in board.resource_roles
        if item.key == f"{SYSTEM_INDICATOR_ID}:output"
    )
    assert role.fixed and role.default == "PLATFORM_GPIO_6"
    connections = json.loads(
        (board.package_root / "connections.json").read_text(encoding="utf-8")
    )
    gpio6 = connections["resources"]["PLATFORM_GPIO_6"]
    assert gpio6["physical"] == "IMU_CAL_LED"
    main_header = (
        board.payload_root / "Core" / "Inc" / "main.h"
    ).read_text(encoding="utf-8")
    assert "IMU_CAL_LED_Pin GPIO_PIN_1" in main_header
    assert "IMU_CAL_LED_GPIO_Port GPIOA" in main_header
    indicator_service = builtin_catalog.Component_Get(
        "silverstar.flight_logic.indicator.gpio_status_service"
    )
    service_source = (
        indicator_service.payload_root
        / "FlightLogic"
        / "Indicator"
        / "GpioStatus"
        / "Src"
        / "indicator_service.c"
    ).read_text(encoding="utf-8")
    assert "PROJECT_RESOURCE_SYSTEM_INDICATOR" in service_source
    assert "0U : 1U" in service_source

    software_indicator_ids = {
        manifest.component_id
        for manifest in builtin_catalog.Type_Get("device")
        if manifest.component_class == "indicator"
    }
    assert software_indicator_ids == {SYSTEM_INDICATOR_ID, GNSS_INDICATOR_ID}
    assert all("power" not in value for value in software_indicator_ids)


def test_indicator_generation_disable_and_gnss_conflict(builtin_catalog) -> None:
    model = ReferenceProject_Create("IndicatorGeneration", catalog=builtin_catalog)
    graph = SourceGraph_Resolve(model, builtin_catalog)
    files = GeneratedFiles_Render(model, builtin_catalog, graph)
    flight_config = files["Generated/Inc/project_flight_config.h"].decode()
    resources = files["Generated/Inc/project_resources.h"].decode()
    assert "SYSTEM_INDICATOR_SYSTEM_ENABLE                   1U" in flight_config
    assert "SYSTEM_INDICATOR_GNSS_ENABLE                     0U" in flight_config
    assert "PROJECT_RESOURCE_SYSTEM_INDICATOR          PLATFORM_GPIO_6" in resources
    assert "PROJECT_FEATURE_GNSS_STATUS_INDICATOR      0U" in resources

    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.plugin != SYSTEM_INDICATOR_ID
    ]
    model.resource_assignments.pop("system_indicator0:output")
    files = GeneratedFiles_Render(
        model, builtin_catalog, SourceGraph_Resolve(model, builtin_catalog)
    )
    assert "SYSTEM_INDICATOR_SYSTEM_ENABLE                   0U" in files[
        "Generated/Inc/project_flight_config.h"
    ].decode()

    conflicting = ReferenceProject_Create(
        "IndicatorConflict", catalog=builtin_catalog
    )
    conflicting.device_instances.append(
        DeviceInstance("gnss_indicator0", GNSS_INDICATOR_ID)
    )
    conflicting.resource_assignments["gnss_indicator0:output"] = (
        "PLATFORM_GPIO_6"
    )
    resolution = ResourceAssignments_Resolve(conflicting, builtin_catalog)
    assert not resolution.valid
    assert any("Resource conflict" in error for error in resolution.errors)


def test_gnss_indicator_requires_gnss_and_an_independent_gpio(
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    model = service.ProjectDraft_Create("CustomIndicator")
    model.board = ""
    model.device_instances = [
        DeviceInstance("gnss0", "silverstar.device.gnss.neo_m9n"),
        DeviceInstance("system_indicator0", SYSTEM_INDICATOR_ID),
    ]
    model.resource_assignments = {}
    model.modes = {slot: [] for slot in model.modes}
    model.hardware = HardwareConfiguration(
        mode="custom",
        source_kind="manual_import",
        provider="silverstar.hardware_provider.stm32_cubemx",
        resources=(
            HardwareResource("UART_GNSS", "uart"),
            HardwareResource("GPIO_GNSS_RESET", "gpio_output"),
            HardwareResource("GPIO_SYSTEM_LED", "gpio_output"),
            HardwareResource("GPIO_GNSS_LED", "gpio_output"),
            HardwareResource("GPIO_GNSS_TIMEPULSE", "gpio_interrupt"),
            HardwareResource("TIME_MONOTONIC", "time"),
        ),
    )
    model = service.ProjectConfiguration_Reconcile(model).model
    assert service.DeviceSelectionAvailabilities_Get(model)[
        GNSS_INDICATOR_ID
    ].available

    model.resource_assignments = {}
    model.hardware = HardwareConfiguration(
        mode="custom",
        source_kind="manual_import",
        provider="silverstar.hardware_provider.stm32_cubemx",
        resources=(
            HardwareResource("UART_GNSS", "uart"),
            HardwareResource("GPIO_GNSS_RESET", "gpio_output"),
            HardwareResource("GPIO_SYSTEM_LED", "gpio_output"),
            HardwareResource(
                "GPIO_GNSS_LED",
                "gpio_output",
                {
                    "physical_resource": "PA2",
                    "output_type": "open_drain",
                    "pull": "up",
                    "speed": "high",
                    "initial_level": "low",
                    "locked": False,
                },
            ),
            HardwareResource("GPIO_GNSS_TIMEPULSE", "gpio_interrupt"),
            HardwareResource("TIME_MONOTONIC", "time"),
        ),
    )
    invalid_gpio = service.DeviceSelectionAvailabilities_Get(model)[
        GNSS_INDICATOR_ID
    ]
    assert invalid_gpio.available
    assert invalid_gpio.reason_code == ""

    without_gnss = service.ProjectDraft_Create("NoGnssIndicator")
    without_gnss.device_instances = [
        instance
        for instance in without_gnss.device_instances
        if instance.plugin != "silverstar.device.gnss.neo_m9n"
    ]
    availability = service.DeviceSelectionAvailabilities_Get(without_gnss)[
        GNSS_INDICATOR_ID
    ]
    assert availability.available
    assert availability.reason_code == ""


def test_indicator_group_and_protocol_names_are_localized(
    tmp_path: Path, qapp
) -> None:
    window = MainWindow(SettingsStore(tmp_path / "indicator-ui.ini"))
    try:
        assert window.devices_page.indicator_group.title() == "指示灯"
        system = window.devices_page.device_checks[SYSTEM_INDICATOR_ID]
        gnss = window.devices_page.device_checks[GNSS_INDICATOR_ID]
        assert system.isChecked() and system.isEnabled()
        assert not gnss.isChecked() and gnss.isEnabled()
        assert "第二个指示灯GPIO" not in gnss.toolTip()
        assert set(window.flight_configuration_page.protocol_combos) == {
            "telemetry",
            "maintenance",
            "logging",
        }
        assert all(
            combo.count() == 2
            for combo in window.flight_configuration_page.protocol_combos.values()
        )
        assert {
            category: combo.currentText()
            for category, combo in window.flight_configuration_page.protocol_combos.items()
        } == {
            "telemetry": "AIR遥测协议 M0",
            "maintenance": "串口维护协议 0.0",
            "logging": "飞行日志格式 0.0",
        }

        window.Language_Apply("en_US")
        assert {
            category: combo.currentText()
            for category, combo in window.flight_configuration_page.protocol_combos.items()
        } == {
            "telemetry": "AIR Telemetry Protocol M0",
            "maintenance": "Serial Maintenance Protocol 0.0",
            "logging": "Flight Log Format 0.0",
        }
    finally:
        window.close()
        qapp.processEvents()


def test_gnss_indicator_firmware_uses_position_usable(workspace_root: Path) -> None:
    source = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_core_0_1_0"
        / "payload"
        / "System"
        / "Indicator"
        / "Src"
        / "system_indicator.c"
    ).read_text(encoding="utf-8")
    assert "SystemIndicator_GnssModeResolve" in source
    assert "sample.position_usable" in source
    assert "sample.fix_type" not in source


def test_build_page_tool_roles_and_missing_tool_gates(tmp_path: Path, qapp) -> None:
    window = MainWindow(SettingsStore(tmp_path / "tool-roles.ini"))
    page = window.build_page
    try:
        page.Targets_Set(
            flight_generated=True, ground_enabled=False, ground_generated=False
        )
        assert not hasattr(page, "toolchain_status")
        assert not hasattr(page, "tool_path_combo")
        assert not hasattr(page, "browse_button")
        assert set(page.tool_status_labels) == {"compiler", "make", "host_gcc"}
        page.Tools_Set(
            (
                ToolchainToolView(
                    "compiler", "Arm GNU Toolchain", "arm-none-eabi-gcc",
                    "C:/arm/bin/arm-none-eabi-gcc.exe", "14.3.1", "found",
                ),
                ToolchainToolView(
                    "make", "GNU Make", "mingw32-make",
                    "C:/make/mingw32-make.exe", "4.4", "found",
                ),
                ToolchainToolView(
                    "host_gcc", "Host GCC", "gcc", "", "", "not_found"
                ),
            )
        )
        assert "generate_apply" not in page.action_buttons
        assert page.action_buttons["flight_build"].isEnabled()
        assert not page.action_buttons["ground_build"].isEnabled()
        assert page.action_buttons["static_analysis"].isEnabled()
        assert not page.action_buttons["host_tests"].isEnabled()
        assert not page.install_guide_button.isHidden()
        assert "-fanalyzer" in page.action_buttons["static_analysis"].toolTip()
        assert "不是形式化证明" in page.action_buttons["power10_check"].toolTip()

        page.Tools_Set(
            (
                ToolchainToolView(
                    "compiler", "Arm GNU Toolchain", "arm-none-eabi-gcc",
                    "", "", "not_found",
                ),
                ToolchainToolView(
                    "make", "GNU Make", "mingw32-make",
                    "C:/make/mingw32-make.exe", "4.4", "found",
                ),
                ToolchainToolView(
                    "host_gcc", "Host GCC", "gcc",
                    "C:/host/gcc.exe", "14.2", "found",
                ),
            )
        )
        assert "generate_apply" not in page.action_buttons
        assert not page.action_buttons["flight_build"].isEnabled()
        assert not page.action_buttons["static_analysis"].isEnabled()
        assert page.action_buttons["host_tests"].isEnabled()
    finally:
        window.close()
        qapp.processEvents()
