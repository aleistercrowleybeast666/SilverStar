from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import shiboken6

from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.generator.hardware_preparation import (
    HardwareAssignmentFingerprint_Get,
)
from silverstar_fccg.generator.render import GeneratedFiles_Render, MetadataFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    ProtocolLogDefinitions_Get,
)
from silverstar_fccg.project.model import (
    DeviceInstance,
    HardwareConfiguration,
    HardwareResource,
    ProjectModel_Parse,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.ui.committed_spin import EnterCommittedSpinBox
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.widgets import StandardCheckBox


def test_deployment_parameters_and_protocol_profiles_reach_all_outputs(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("FlightConfigurationContract", catalog=builtin_catalog)
    assert model.modes["calibration"] == []
    assert model.modes["deployment"] == ["ApogeeVerticalVelocity", "Tilt"]
    assert model.ProtocolProfiles_Get() == {
        "telemetry": "air.m0",
        "maintenance": "maintenance.serial.0_0",
        "logging": "flight_log.0_0",
    }

    model.modes["deployment"].append("Delay")
    model.mode_parameters["deployment"]["ApogeeVerticalVelocity"][
        "vertical_velocity_threshold"
    ] = -3.25
    model.mode_parameters["deployment"]["Tilt"]["tilt_threshold"] = 72.5
    model.mode_parameters["deployment"]["Delay"]["delay"] = 12.345
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert Project_Validate(model, builtin_catalog).valid

    graph = SourceGraph_Resolve(model, builtin_catalog)
    generated = GeneratedFiles_Render(model, builtin_catalog, graph)
    header = generated["Generated/Inc/project_flight_config.h"].decode("utf-8")
    assert "SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK" in header
    assert "SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ" in header
    assert "SYSTEM_DEPLOY_TRIGGER_TILT" in header
    assert "SYSTEM_DEPLOY_TRIGGER_DELAY" in header
    mask_line = next(
        line
        for line in header.splitlines()
        if line.startswith("#define SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK")
    )
    assert mask_line.split(None, 2)[2].startswith("(")
    assert mask_line.endswith(")")
    assert "SYSTEM_FLIGHT_APOGEE_VZ_THRESHOLD_MPS" in header
    assert "(-3.25f)" in header
    assert "SYSTEM_FLIGHT_TILT_THRESHOLD_DEG" in header and "72.5f" in header
    assert "SYSTEM_FLIGHT_DEPLOY_DELAY_MS" in header and "12345U" in header

    live_model_before_render = model.Dictionary_Get()
    metadata = MetadataFiles_Render(model, builtin_catalog, graph)
    assert model.Dictionary_Get() == live_model_before_render
    written_model = json.loads(metadata["SilverStar.ssproject"])
    assert written_model["component_provenance"]
    summary = metadata["SilverStar_Configuration.md"].decode("utf-8")
    assert "deployment.Delay` (active)" in summary
    assert "delay=12.345" in summary
    assert "AIR Telemetry Protocol M0 (`air.m0`)" in summary
    assert "Serial Maintenance Protocol 0.0 (`maintenance.serial.0_0`)" in summary
    assert "Flight Log Format 0.0 (`flight_log.0_0`)" in summary

    with zipfile.ZipFile(io.BytesIO(metadata["FlightConfigurationContract.ssdecoder"])) as archive:
        profile = json.loads(archive.read("project_semantics.json"))
    assert profile["mode_parameters"] == model.mode_parameters
    assert profile["protocols"] == {
        category: {
            "component": selection.component,
            "version": selection.version,
            "profile": selection.profile,
            "manifest_sha256": selection.manifest_sha256,
        }
        for category, selection in model.protocols.items()
    }
    assert ProjectModel_Parse(model.Dictionary_Get()).Dictionary_Get() == (
        model.Dictionary_Get()
    )


def test_deployment_parameter_ranges_are_manifest_enforced(builtin_catalog) -> None:
    model = ReferenceProject_Create("BadFlightParameter", catalog=builtin_catalog)
    model.mode_parameters["deployment"]["ApogeeVerticalVelocity"][
        "vertical_velocity_threshold"
    ] = 0.0
    result = Project_Validate(model, builtin_catalog)
    assert not result.valid
    assert any(issue.code == "mode_parameter_range" for issue in result.issues)

    model = ReferenceProject_Create("BadTiltParameter", catalog=builtin_catalog)
    model.mode_parameters["deployment"]["Tilt"]["tilt_threshold"] = 181.0
    result = Project_Validate(model, builtin_catalog)
    assert not result.valid
    assert any(issue.code == "mode_parameter_range" for issue in result.issues)


def test_optional_actuators_are_one_way_dependencies_and_generate_safe_off(
    builtin_catalog,
) -> None:
    launch_id = "silverstar.device.actuator.launch_ignition"
    parachute_id = "silverstar.device.actuator.parachute_pyro"

    no_launch = ReferenceProject_Create("ExternalIgnition", catalog=builtin_catalog)
    no_launch.device_instances = [
        instance for instance in no_launch.device_instances if instance.plugin != launch_id
    ]
    no_launch = ProjectConfiguration_Reconcile(no_launch, builtin_catalog).model
    assert launch_id not in no_launch.DevicePluginIds_Get()
    assert "launch_ignition0:output" not in no_launch.resource_assignments
    assert no_launch.modes["deployment"]
    assert Project_Validate(no_launch, builtin_catalog).valid
    graph = SourceGraph_Resolve(no_launch, builtin_catalog)
    resources = GeneratedFiles_Render(no_launch, builtin_catalog, graph)[
        "Generated/Inc/project_resources.h"
    ].decode("utf-8")
    launch_feature_line = next(
        line
        for line in resources.splitlines()
        if "PROJECT_FEATURE_LAUNCH_IGNITION_OUTPUT" in line
    )
    assert launch_feature_line.split()[-1] == "0U"
    assert "PROJECT_RESOURCE_LAUNCH_IGNITION_OUTPUT" in resources
    assert "PLATFORM_GPIO_COUNT" in resources

    no_parachute = ReferenceProject_Create("NoParachute", catalog=builtin_catalog)
    no_parachute.modes["deployment"] = [
        "ApogeeVerticalVelocity",
        "Tilt",
        "Delay",
    ]
    no_parachute.device_instances = [
        instance
        for instance in no_parachute.device_instances
        if instance.plugin != parachute_id
    ]
    no_parachute = ProjectConfiguration_Reconcile(
        no_parachute, builtin_catalog
    ).model
    assert parachute_id not in no_parachute.DevicePluginIds_Get()
    assert no_parachute.modes["deployment"] == []
    assert Project_Validate(no_parachute, builtin_catalog).valid


def test_native_log_availability_is_recordable_not_estimator_based(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("NativeLogs", catalog=builtin_catalog)
    model.strategies["estimator"] = None
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    definitions = {
        definition.record: definition
        for definition in ProtocolLogDefinitions_Get(model, builtin_catalog)
    }
    assert LogAvailability_Get(
        definitions["FLIGHT_LOG_RECORD_BARO_NATIVE"], model, builtin_catalog
    ).available
    measurement = LogAvailability_Get(
        definitions["FLIGHT_LOG_RECORD_BARO_MEASUREMENT"], model, builtin_catalog
    )
    assert not measurement.available
    assert "algorithm.estimator" in measurement.missing


def test_logging_signals_are_deferred_and_widgets_survive_fifty_changes(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    window = MainWindow(SettingsStore(tmp_path / "logging-stress.ini"))
    errors: list[object] = []
    monkeypatch.setattr(window, "_Error_Show", errors.append)
    try:
        table = window.flight_configuration_page.logging_table
        row = next(
            index
            for index in range(table.rowCount())
            if table.cellWidget(index, 0)
            .findChild(StandardCheckBox)
            .property("streamId")
            == "FLIGHT_LOG_RECORD_MAG_NATIVE"
        )
        check = table.cellWidget(row, 0).findChild(StandardCheckBox)
        decimation = table.cellWidget(row, 4)
        assert isinstance(check, StandardCheckBox)
        assert isinstance(decimation, EnterCommittedSpinBox)
        initial_decimation = int(decimation.CommittedValue_Get())

        for index in range(50):
            check.setChecked(index % 2 == 0)
            decimation.setValue(index + 2)
        assert window._logging_refresh_scheduled
        qapp.processEvents()

        assert not errors
        assert shiboken6.isValid(check)
        assert shiboken6.isValid(decimation)
        assert table.cellWidget(row, 0).findChild(StandardCheckBox) is check
        assert table.cellWidget(row, 4) is decimation
        stream = next(
            item
            for item in window._model.logging_streams
            if item.record == "FLIGHT_LOG_RECORD_MAG_NATIVE"
        )
        assert not stream.enabled
        assert stream.decimation == initial_decimation
        assert decimation.CommittedValue_Get() == initial_decimation

        for _index in range(3):
            window._Strategy_Change("estimator", None)
            window._Strategy_Change(
                "estimator", "silverstar.algorithm.estimator.kf6"
            )
            window._OtherDevice_Toggle(
                "silverstar.device.sensor.input_voltage", False
            )
            window._OtherDevice_Toggle(
                "silverstar.device.sensor.input_voltage", True
            )
        assert not errors
        assert shiboken6.isValid(check)
        assert table.cellWidget(row, 0).findChild(StandardCheckBox) is check
    finally:
        window.close()
        qapp.processEvents()


def test_protocol_controls_artifact_gate_and_assignment_fingerprint(
    tmp_path: Path, qapp, builtin_catalog
) -> None:
    window = MainWindow(SettingsStore(tmp_path / "profiles-and-artifacts.ini"))
    try:
        assert set(window.flight_configuration_page.protocol_combos) == {
            "telemetry",
            "maintenance",
            "logging",
        }
        assert {
            category: (combo.count(), combo.currentText())
            for category, combo in window.flight_configuration_page.protocol_combos.items()
        } == {
            "telemetry": (2, "AIR遥测协议 M0"),
            "maintenance": (2, "串口维护协议 0.0"),
            "logging": (2, "飞行日志格式 0.0"),
        }

        project_root = tmp_path / "GeneratedProject"
        window._project_root = project_root
        assert window._FirmwareArtifact_Get(window._model) == (None, "")
        non_artifact = project_root / "build" / "FCCG" / window._model.build.target_profile / "Release" / "notes.txt"
        non_artifact.parent.mkdir(parents=True)
        non_artifact.write_text("not firmware", encoding="utf-8")
        assert window._FirmwareArtifact_Get(window._model) == (None, "")
        artifact = non_artifact.with_name("flight_controller.elf")
        artifact.write_bytes(b"fixture")
        directory, name = window._FirmwareArtifact_Get(window._model)
        assert directory == artifact.parent
        assert name == artifact.name
        window._Project_Refresh()
        assert window.build_page.action_buttons[
            "open_firmware_output"
        ].isEnabled()
    finally:
        window.close()
        qapp.processEvents()

    model = ReferenceProject_Create("Fingerprint", catalog=builtin_catalog)
    fingerprint = HardwareAssignmentFingerprint_Get(model, builtin_catalog)
    model.hardware = replace(model.hardware, assignment_fingerprint=fingerprint)
    unchanged = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert unchanged.hardware.assignment_fingerprint == fingerprint
    unchanged.device_instances = [
        instance
        for instance in unchanged.device_instances
        if instance.plugin != "silverstar.device.sensor.input_voltage"
    ]
    changed = ProjectConfiguration_Reconcile(unchanged, builtin_catalog).model
    assert changed.hardware.assignment_fingerprint == ""


def test_typed_bus_gpio_and_physical_exclusivity_contracts(builtin_catalog) -> None:
    gnss = builtin_catalog.Component_Get("silverstar.device.gnss.neo_m9n")
    gnss_uart = next(
        requirement for requirement in gnss.resource_requirements if requirement.name == "data"
    )
    assert gnss_uart.constraints["uart"]["baud"] == {
        "exact": 921600,
        "configurable": False,
    }
    telemetry = builtin_catalog.Component_Get("silverstar.device.telemetry.sx1281")
    radio_bus = next(
        requirement
        for requirement in telemetry.resource_requirements
        if requirement.name == "radio_bus"
    )
    assert radio_bus.constraints["spi"]["mode"] == "master"
    assert radio_bus.constraints["spi"]["maximum_clock_hz"] == 18_000_000
    launch = builtin_catalog.Component_Get(
        "silverstar.device.actuator.launch_ignition"
    )
    launch_output = launch.resource_requirements[0]
    assert launch_output.electrical_constraints == {
        "mode": "gpio_output",
        "output_type": "push_pull",
        "pull": "none",
        "speed": "low",
        "safe_initial_level": "inactive",
        "active_polarity": "high",
        "startup_glitch_free": True,
    }
    assert ResourceAssignments_Resolve(
        ReferenceProject_Create("TypedValid", catalog=builtin_catalog),
        builtin_catalog,
    ).valid

    invalid_uart = ReferenceProject_Create("BadUart", catalog=builtin_catalog)
    invalid_uart.board = ""
    invalid_uart.device_instances = [
        DeviceInstance("gnss0", "silverstar.device.gnss.neo_m9n")
    ]
    invalid_uart.hardware = HardwareConfiguration(
        mode="custom",
        resources=(
            HardwareResource(
                "GNSS_UART",
                "uart",
                {
                    "physical_resource": "USART2",
                    "baud_rate": 230400,
                    "word_length": 8,
                    "parity": "none",
                    "stop_bits": 1.0,
                    "pins": {"rx": "PD6", "tx": "PD5"},
                    "dma": [
                        {"request": "USART2_RX", "instance": "DMA1_Stream5"}
                    ],
                    "irq": {"enabled": True},
                },
            ),
        ),
    )
    invalid_uart.resource_assignments = {"gnss0:data": "GNSS_UART"}
    uart_errors = ResourceAssignments_Resolve(
        invalid_uart, builtin_catalog
    ).errors
    assert any("uart.baud.exact" in error and "230400" in error for error in uart_errors)

    invalid_gpio = ReferenceProject_Create("BadPyro", catalog=builtin_catalog)
    invalid_gpio.board = ""
    invalid_gpio.device_instances = [
        DeviceInstance(
            "launch_ignition0", "silverstar.device.actuator.launch_ignition"
        )
    ]
    invalid_gpio.hardware = HardwareConfiguration(
        mode="custom",
        resources=(
            HardwareResource(
                "PYRO_GPIO",
                "gpio_output",
                {
                    "physical_resource": "PC0",
                    "output_type": "push_pull",
                    "pull": "none",
                    "speed": "low",
                    "initial_level": "high",
                    "locked": False,
                },
            ),
        ),
    )
    invalid_gpio.resource_assignments = {
        "launch_ignition0:output": "PYRO_GPIO"
    }
    gpio_errors = ResourceAssignments_Resolve(
        invalid_gpio, builtin_catalog
    ).errors
    assert any("electrical.safe_initial_level" in error for error in gpio_errors)
    assert any("startup-safe GPIO" in error for error in gpio_errors)

    duplicate = ReferenceProject_Create("DuplicatePhysical", catalog=builtin_catalog)
    duplicate.board = ""
    duplicate.device_instances = [
        DeviceInstance(
            "launch_ignition0", "silverstar.device.actuator.launch_ignition"
        ),
        DeviceInstance(
            "parachute_pyro0", "silverstar.device.actuator.parachute_pyro"
        ),
    ]
    safe_gpio = {
        "physical_resource": "PC0",
        "output_type": "push_pull",
        "pull": "none",
        "speed": "low",
        "initial_level": "low",
        "locked": True,
    }
    duplicate.hardware = HardwareConfiguration(
        mode="custom",
        resources=(
            HardwareResource("PYRO_A", "gpio_output", dict(safe_gpio)),
            HardwareResource("PYRO_B", "gpio_output", dict(safe_gpio)),
        ),
    )
    duplicate.resource_assignments = {
        "launch_ignition0:output": "PYRO_A",
        "parachute_pyro0:output": "PYRO_B",
    }
    duplicate_errors = ResourceAssignments_Resolve(
        duplicate, builtin_catalog
    ).errors
    assert any("Physical resource conflict: PC0" in error for error in duplicate_errors)
