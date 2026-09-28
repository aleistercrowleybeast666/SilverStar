from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

import tools.import_reference_components as reference_import
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.build.runner import BuildAction, BuildResult
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.view_models import (
    ComponentType,
    ComponentView,
    DeviceInstanceView,
)
from silverstar_fccg.core.workspace import WorkspacePolicy, WorkspacePolicyError
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.log_decoder_profile import (
    LogDecoderPackage_Verify,
)
from silverstar_fccg.generator.render import GeneratedFiles_Render, MetadataFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
from silverstar_fccg.plugins.manifest import PluginManifest_Load, PluginManifestError
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    LoggingProfile_Reconcile,
    LogPolicyLevel,
    ProtocolLogDefinitions_Load,
)
from silverstar_fccg.project.model import (
    DeviceInstance,
    HardwareConfiguration,
    HardwareResource,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.pages.components import DevicesPage
from silverstar_fccg.ui.theme import Stylesheet_Get
from silverstar_fccg.ui.widgets import (
    CollapsibleSection,
    HeaderComboBox,
    LockedCheckBox,
    StandardCheckBox,
)
from tools.import_reference_components import _ProtocolMetadata_Adapt


def test_reference_import_definition_preserves_current_fccg_overlays(
    monkeypatch: pytest.MonkeyPatch,
    workspace_root: Path,
) -> None:
    monkeypatch.setattr(
        reference_import, "_ManifestValues_Get", lambda *_arguments: []
    )
    components = reference_import._Components_Get(
        Path("unused"),
        {"commit": "fixture-commit", "snapshot_digest": "fixture-snapshot"},
    )
    components_by_id = {
        component["manifest"]["id"]: component
        for component in components
    }
    manifests = {
        component["manifest"]["id"]: component["manifest"]
        for component in components
    }

    assert len(manifests) == 65
    assert {
        "silverstar.protocol.telemetry.air_m0",
        "silverstar.protocol.maintenance.serial_0_0",
        "silverstar.protocol.logging.sslog_0_0",
    }.issubset(manifests)
    air = manifests["silverstar.protocol.telemetry.air_m0"]
    assert air["metadata"]["log_compatibility_tag"] == "AIR-NCRC"
    assert (
        "log_compatibility_tag"
        not in air["protocol"]["profiles"]["telemetry"][0]
    )
    board = manifests["silverstar.board.silverstar_0_5"]
    assert board["name"] == "SS0.5"
    assert board["metadata"]["build_symbol"] == "SILVERSTAR_0_5"
    imu = manifests["silverstar.device.imu.jy901b"]
    assert "magnetometer.field" in imu["provides"]
    assert "magnetometer.absolute_vector_qualified" not in imu["provides"]
    assert "imu.software_alignment_qualified" in imu["provides"]
    assert (
        "attitude.external.preflight_alignment_6axis_qualified"
        in imu["provides"]
    )
    assert (
        "attitude.external.preflight_alignment_9axis_qualified"
        in imu["provides"]
    )
    assert (
        "imu.landing_impact_qualified"
        in imu["metadata"]["unqualified_capabilities"]
    )
    assert (
        manifests["silverstar.algorithm.alignment.gravity_mag_triad"]
        ["requires"]["capabilities"][-1]["capability"]
        == "magnetometer.absolute_vector_qualified"
    )
    assert (
        manifests["silverstar.flight_logic.landing.baro_imu_window"]
        ["class"]
        == "landing_common"
    )
    assert {
        "silverstar.flight_logic.landing.stillness",
        "silverstar.flight_logic.landing.impact_then_stillness",
        "silverstar.flight_logic.landing.baro_imu_window_strategy",
    }.issubset(manifests)
    assert {
        "silverstar.device.sensor.input_voltage",
        "silverstar.device.actuator.launch_ignition",
        "silverstar.device.actuator.parachute_pyro",
    }.issubset(manifests)
    core_owned = components_by_id["silverstar.core.0_1_0"]["fccg_owned_files"]
    for relative in (
        "APP/Src/app_tasks.c",
        "System/Inc/system_source_selector.h",
        "System/Src/system_source_selector.c",
        "Tests/Host/Fixtures/MultiInstance/Inc/project_resources.h",
        "Tests/Host/test_source_selector.c",
        "Tests/Host/test_sx1280_hal_multi_instance.c",
        "Tests/Host/test_logger.c",
        "Tools/check_power_of_ten.ps1",
        "Tools/validate_sslog_record_catalog.py",
    ):
        assert relative in core_owned
    context_files = {
        "silverstar.device.imu.jy901b": (
            "Devices/IMU/JY901B/Inc/jy901b_imu_build_capabilities.h",
            "Devices/IMU/JY901B/Adapter/Inc/jy901b_instance.h",
            "Devices/IMU/JY901B/Src/jy901b_device.c",
        ),
        "silverstar.device.gnss.neo_m9n": (
            "Devices/GNSS/NEO_M9N/Adapter/Inc/neo_m9n_instance.h",
            "Devices/GNSS/NEO_M9N/Src/neo_m9n_device.c",
        ),
        "silverstar.device.telemetry.sx1281": (
            "Devices/Telemetry/SX1281/Adapter/Inc/sx1281_instance.h",
            "Middlewares/Third_Party/SX1280lib/sx1280.c",
        ),
    }
    for component_id, relatives in context_files.items():
        owned = components_by_id[component_id]["fccg_owned_files"]
        assert all(relative in owned for relative in relatives)
    assert imu["metadata"]["device_instance_bindings"][
        "SYSTEM_DEVICE_CLASS_IMU"
    ] == {
        "function_prefix": "Jy901bImuInstance",
        "headers": ["jy901b_instance.h"],
        "pass_instance": True,
    }
    assert manifests["silverstar.device.gnss.neo_m9n"]["metadata"][
        "device_instance_bindings"
    ]["SYSTEM_DEVICE_CLASS_GNSS"]["function_prefix"] == (
        "NeoM9nGnssInstance"
    )
    assert manifests["silverstar.device.telemetry.sx1281"]["metadata"][
        "device_instance_bindings"
    ]["SYSTEM_DEVICE_CLASS_TELEMETRY"]["function_prefix"] == (
        "Sx1281TelemetryInstance"
    )
    for component_id in context_files:
        package = component_id.replace(".", "_")
        installed = json.loads(
            (
                workspace_root / "plugins" / "builtin" / package / "plugin.json"
            ).read_text(encoding="utf-8")
        )
        generated = manifests[component_id]
        assert generated["instance_policy"] == installed["instance_policy"]
        for key in (
            "instance_resource_binding",
            "device_instance_bindings",
            "source_origins",
        ):
            assert generated["metadata"][key] == installed["metadata"][key]
    logging_owned = components_by_id[
        "silverstar.protocol.logging.sslog_0_0"
    ]["fccg_owned_files"]
    assert {
        "Protocol/SSLOG/Inc/sslog_protocol.h",
        "Protocol/SSLOG/schema/sslog_parser_metadata.json",
        "Protocol/SSLOG/schema/sslog_schema.json",
    }.issubset(logging_owned)


def test_manifest_reference_provenance_excludes_dynamic_audit_fields() -> None:
    first = reference_import._ManifestReferenceProvenance_Get(
        {
            "path": r"C:\reference-a",
            "branch": "main",
            "commit": "abc123",
            "snapshot_digest": "def456",
            "recorded_at_utc": "2026-08-28T00:00:00+00:00",
            "status": [],
        }
    )
    second = reference_import._ManifestReferenceProvenance_Get(
        {
            "path": r"D:\reference-b",
            "branch": "detached",
            "commit": "abc123",
            "snapshot_digest": "def456",
            "recorded_at_utc": "2026-08-29T00:00:00+00:00",
            "status": ["ignored-for-manifest-lock"],
        }
    )

    assert first == second == {
        "source_kind": "reference_snapshot",
        "commit": "abc123",
        "snapshot_digest": "def456",
    }


def test_fccg_owned_decoder_templates_survive_reference_reimport(
    workspace_root: Path,
) -> None:
    template_root = (
        workspace_root
        / "plugins/builtin/silverstar_core_0_1_0/templates/generated"
    )
    semantics = json.loads(
        (template_root / "project_semantics.json").read_text(
            encoding="utf-8"
        )
    )
    descriptor_source = (
        template_root / "project_log_decoder_profile.c"
    ).read_text(encoding="utf-8")
    importer_source = Path(reference_import.__file__).read_text(
        encoding="utf-8"
    )

    assert semantics["schema_id"] == "silverstar.project-semantics/1.2"
    assert "profile->package_schema_minor = 2U;" in descriptor_source
    for relative in (
        "project_device_instances.h",
        "project_device_instances.c",
        "project_log_config.c",
        "project_log_decoder_profile.h",
        "project_log_decoder_profile.c",
        "project_semantics.json",
    ):
        assert f'"{relative}",' in importer_source


def test_reference_payload_sync_and_environment_templates_are_read_only(
    workspace_root: Path,
) -> None:
    reference = Path(
        r"C:\Users\chdxm\Desktop\stm32-1\Flight_Controller0.5"
    )
    markers = (
        "SilverStar.ssproject",
        "AGENTS.md",
        "Devices/IMU/JY901B",
        "System/User/system_user_capability_validation.h",
        "Targets/SilverStar_F407",
        "Algorithm/Alignment",
    )
    if not all((reference / marker).exists() for marker in markers):
        pytest.skip("read-only reference firmware is not present on this host")

    before = reference_import.ReferenceProvenance_Get(reference)
    if before["working_tree"] != "clean":
        pytest.skip("read-only reference firmware task is still active")
    exact_pairs = (
        (
            "Devices/IMU/JY901B/Adapter/Inc/"
            "jy901b_quaternion_build_capabilities.h",
            "plugins/builtin/silverstar_device_imu_jy901b/payload/"
            "Devices/IMU/JY901B/Adapter/Inc/"
            "jy901b_quaternion_build_capabilities.h",
        ),
        (
            "System/User/system_user_capability_validation.h",
            "plugins/builtin/silverstar_core_0_1_0/payload/"
            "System/User/system_user_capability_validation.h",
        ),
        (
            "Tests/Host/test_build_capability_contract.c",
            "plugins/builtin/silverstar_core_0_1_0/payload/"
            "Tests/Host/test_build_capability_contract.c",
        ),
        (
            "APP/Inc/diagnostic_log.h",
            "plugins/builtin/silverstar_core_0_1_0/payload/"
            "APP/Inc/diagnostic_log.h",
        ),
        (
            "APP/Src/diagnostic_log.c",
            "plugins/builtin/silverstar_core_0_1_0/payload/"
            "APP/Src/diagnostic_log.c",
        ),
        (
            "Generated/Src/project_log_config.c",
            "plugins/builtin/silverstar_core_0_1_0/templates/"
            "generated/project_log_config.c",
        ),
        (
            "Protocol/SSLOG/Inc/sslog_records.h",
            "plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/"
            "Protocol/SSLOG/Inc/sslog_records.h",
        ),
        (
            "Protocol/SSLOG/Src/sslog_records.c",
            "plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/"
            "Protocol/SSLOG/Src/sslog_records.c",
        ),
        (
            ".eide/eide.yml",
            "plugins/builtin/silverstar_environment_vscode_eide_gcc/"
            "templates/reference/.eide/eide.yml",
        ),
        (
            ".eide/files.options.yml",
            "plugins/builtin/silverstar_environment_vscode_eide_gcc/"
            "templates/reference/.eide/files.options.yml",
        ),
        (
            "Flight_Controller0.5.code-workspace",
            "plugins/builtin/silverstar_environment_vscode_eide_gcc/"
            "templates/reference/Flight_Controller0.5.code-workspace",
        ),
        (
            ".vscode/tasks.json",
            "plugins/builtin/silverstar_environment_vscode_eide_gcc/"
            "templates/reference/.vscode/tasks.json",
        ),
    )
    for reference_relative, builtin_relative in exact_pairs:
        assert (reference / reference_relative).read_bytes() == (
            workspace_root / builtin_relative
        ).read_bytes()

    reference_schema = json.loads(
        (reference / "Protocol/SSLOG/schema/sslog_schema.json").read_text(
            encoding="utf-8"
        )
    )
    builtin_schema = json.loads(
        (
            workspace_root
            / "plugins/builtin/silverstar_protocol_logging_sslog_0_0/"
            "payload/Protocol/SSLOG/schema/sslog_schema.json"
        ).read_text(encoding="utf-8")
    )
    assert builtin_schema["records"] == reference_schema["records"]
    reasons = builtin_schema["sensor_source_change_event"]["reasons"]
    assert reasons["5"] == "prestart_primary_unavailable"
    assert reasons["6"] == "gnss_liveness_timeout"
    assert reasons["7"] == "telemetry_consecutive_tx_timeout"
    assert reasons["8"] == "telemetry_init_failure"

    core_manifest = json.loads(
        (
            workspace_root
            / "plugins/builtin/silverstar_core_0_1_0/plugin.json"
        ).read_text(encoding="utf-8")
    )
    source_origins = core_manifest["metadata"]["source_origins"]
    assert source_origins["APP/Src/device_task.c"] == (
        "fccg_optional_protocol_gating"
    )
    assert source_origins["APP/Src/telemetry_task.c"] == (
        "fccg_optional_protocol_gating"
    )

    target_reference = (
        reference / "Targets/SilverStar_F407/Inc/target_system_config.h"
    ).read_text(encoding="utf-8")
    target_builtin = (
        workspace_root
        / "plugins/builtin/silverstar_mcu_stm32f407vet6/payload/"
        "Targets/SilverStar_F407/Inc/target_system_config.h"
    ).read_text(encoding="utf-8")
    assert target_builtin == target_reference.replace(
        "Adapters and SilverStar 0.5 Board services",
        "Adapters and internal hardware services",
    )

    provenance = json.loads(
        (workspace_root / "plugins/builtin/reference_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    for key in (
        "path",
        "commit",
        "branch",
        "working_tree",
        "status",
        "snapshot_digest",
    ):
        assert provenance[key] == before[key]
    inventory = json.loads(
        (
            workspace_root
            / "plugins/builtin/silverstar_environment_vscode_eide_gcc/"
            "templates/reference/inventory.json"
        ).read_text(encoding="utf-8")
    )
    assert inventory["missing_in_reference"] == [
        ".vscode/extensions.json",
        ".vscode/settings.json",
    ]
    after = reference_import.ReferenceProvenance_Get(reference)
    assert {
        key: after[key]
        for key in ("commit", "working_tree", "status", "snapshot_digest")
    } == {
        key: before[key]
        for key in ("commit", "working_tree", "status", "snapshot_digest")
    }
def test_reference_import_normalizes_board_user_visible_names(
    tmp_path: Path,
) -> None:
    staged_builtin = tmp_path / "builtin"
    power_service = (
        staged_builtin
        / "silverstar_device_sensor_input_voltage"
        / "payload"
        / "Devices"
        / "Power"
        / "InputVoltage"
        / "Src"
        / "power_service.c"
    )
    target_config = (
        staged_builtin
        / "silverstar_mcu_stm32f407vet6"
        / "payload"
        / "Targets"
        / "SilverStar_F407"
        / "Inc"
        / "target_system_config.h"
    )
    power_service.parent.mkdir(parents=True)
    target_config.parent.mkdir(parents=True)
    power_service.write_text(
        'name = "SilverStar 0.5 Voltage Input";\n', encoding="utf-8"
    )
    target_config.write_text(
        "Adapters and SilverStar 0.5 Board services\n", encoding="utf-8"
    )

    reference_import._BoardUserVisibleNames_Adapt(
        staged_builtin, WorkspacePolicy(tmp_path)
    )

    assert '"SS0.5 Voltage Input"' in power_service.read_text(encoding="utf-8")
    assert "Adapters and internal hardware services" in target_config.read_text(
        encoding="utf-8"
    )


def test_standard_controls_and_collapsible_visibility(qapp) -> None:
    section = CollapsibleSection("Advanced", expanded=False)
    layout = QVBoxLayout()
    child = StandardCheckBox("Enabled child")
    layout.addWidget(child)
    section.BodyLayout_Set(layout)
    assert section.body.isHidden()
    assert child.isEnabled()

    section.toggle_button.setChecked(True)
    qapp.processEvents()
    assert not section.body.isHidden()
    assert child.isEnabled()
    section.toggle_button.setChecked(False)
    assert child.isEnabled()

    header = HeaderComboBox("headerLanguageCombo")
    assert header.view().objectName() == "headerComboPopup"
    locked = LockedCheckBox()
    assert locked.isEnabled() and locked.isChecked()
    locked.click()
    assert locked.isChecked()
    for theme in ("light", "dark"):
        stylesheet = Stylesheet_Get(theme)
        assert "QCheckBox#standardCheckBox::indicator:checked" in stylesheet
        assert "check_white.svg" in stylesheet
        assert "QToolButton#collapsibleHeader" in stylesheet


def test_protocol_metadata_defaults_required_and_availability(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("LoggingPolicy")
    definitions = LoggingProfile_Reconcile(model, builtin_catalog)
    streams = {stream.record: stream for stream in model.logging_streams}
    assert all(
        streams[definition.record].enabled == (
            definition.level == LogPolicyLevel.REQUIRED
            or definition.default_stream.enabled
        )
        for definition in definitions
        if LogAvailability_Get(definition, model, builtin_catalog).available
    )
    assert all(
        not streams[definition.record].enabled
        for definition in definitions
        if not LogAvailability_Get(definition, model, builtin_catalog).available
    )

    event = next(
        definition
        for definition in definitions
        if definition.record == "FLIGHT_LOG_RECORD_EVENT"
    )
    assert event.level == LogPolicyLevel.REQUIRED
    model.logging_streams = [
        replace(stream, enabled=False)
        if stream.record == event.record
        else stream
        for stream in model.logging_streams
    ]
    assert any(
        issue.code == "logging_required"
        for issue in Project_Validate(model, builtin_catalog).issues
    )

    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.plugin != "silverstar.device.telemetry.sx1281"
    ]
    definitions = LoggingProfile_Reconcile(model, builtin_catalog)
    telemetry = next(
        definition
        for definition in definitions
        if definition.record == "FLIGHT_LOG_RECORD_TELEMETRY_DIAG"
    )
    availability = LogAvailability_Get(telemetry, model, builtin_catalog)
    assert not availability.available
    assert next(
        stream
        for stream in model.logging_streams
        if stream.record == telemetry.record
    ).enabled is False


def test_new_project_mode_and_logging_defaults_do_not_override_later_choices(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("NewDefaults")
    definitions = LoggingProfile_Reconcile(model, builtin_catalog)
    streams = {stream.record: stream for stream in model.logging_streams}

    assert model.modes["deployment"] == [
        "ApogeeVerticalVelocity",
        "Tilt",
    ]
    assert model.modes["calibration"] == []
    assert all(
        streams[definition.record].enabled == (
            definition.level == LogPolicyLevel.REQUIRED
            or definition.default_stream.enabled
        )
        for definition in definitions
        if LogAvailability_Get(definition, model, builtin_catalog).available
    )

    optional = next(
        definition
        for definition in definitions
        if definition.level == LogPolicyLevel.OPTIONAL
        and LogAvailability_Get(definition, model, builtin_catalog).available
    )
    model.modes["deployment"] = []
    model.logging_streams = [
        replace(stream, enabled=False)
        if stream.record == optional.record
        else stream
        for stream in model.logging_streams
    ]
    LoggingProfile_Reconcile(model, builtin_catalog)

    assert model.modes["deployment"] == []
    assert not next(
        stream
        for stream in model.logging_streams
        if stream.record == optional.record
    ).enabled


def test_protocol_can_add_a_record_without_fccg_source_changes(
    tmp_path: Path, workspace_root: Path
) -> None:
    source = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_protocol_logging_sslog_0_0"
        / "payload"
        / "Protocol"
        / "SSLOG"
        / "schema"
        / "sslog_parser_metadata.json"
    )
    data = json.loads(source.read_text(encoding="utf-8"))
    added = dict(data["records"][0])
    added.update(
        {
            "id": "0x7E",
            "enum": "FLIGHT_LOG_RECORD_PLUGIN_ADDED",
            "name": "PLUGIN_ADDED",
            "payload_size": 4,
            "fields": [{"name": "value", "type": "u32", "unit": "count"}],
            "default_stream": {
                "enabled": False,
                "policy": "event",
                "decimation": 1,
                "period_us": 0,
            },
        }
    )
    data["records"].append(added)
    data["fccg"]["records"][added["enum"]] = {"level": "optional", "purpose": "flight"}
    metadata = tmp_path / "extended_sslog_metadata.json"
    metadata.write_text(json.dumps(data), encoding="utf-8")
    definitions = ProtocolLogDefinitions_Load(metadata)
    assert definitions[-1].record == added["enum"]
    assert definitions[-1].level == LogPolicyLevel.OPTIONAL


def test_reference_import_restores_protocol_owned_fccg_metadata(
    tmp_path: Path, workspace_root: Path
) -> None:
    builtin = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_protocol_logging_sslog_0_0"
        / "payload"
        / "Protocol"
        / "SSLOG"
        / "schema"
        / "sslog_parser_metadata.json"
    )
    expected = json.loads(builtin.read_text(encoding="utf-8"))
    reference_copy = json.loads(json.dumps(expected))
    reference_copy.pop("fccg")
    wire_records = json.loads(json.dumps(reference_copy["records"]))
    metadata = tmp_path / "sslog_parser_metadata.json"
    metadata.write_text(json.dumps(reference_copy), encoding="utf-8")

    _ProtocolMetadata_Adapt(
        metadata,
        workspace_root / "tools" / "reference_overlays" / "sslog_fccg_metadata.json",
        WorkspacePolicy(tmp_path),
    )
    adapted = json.loads(metadata.read_text(encoding="utf-8"))
    assert adapted["records"] == wire_records
    assert adapted["fccg"] == expected["fccg"]
    policies = adapted["fccg"]["records"]
    assert policies["FLIGHT_LOG_RECORD_IMU_CORRECTED"].get("default_enabled", True)
    assert policies["FLIGHT_LOG_RECORD_MAG_NATIVE"].get("default_enabled", True)

    schema_path = builtin.with_name("sslog_schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert adapted["records"] == schema["records"]


def test_resource_contract_schema_rejects_unknown_constraints(
    tmp_path: Path, workspace_root: Path
) -> None:
    source = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_device_console_uart"
        / "plugin.json"
    )
    data = json.loads(source.read_text(encoding="utf-8"))
    data["requires"]["resources"][0]["constraints"]["invented_solver"] = True
    package = tmp_path / "invalid_constraint_plugin"
    package.mkdir()
    manifest = package / "plugin.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PluginManifestError, match="unknown fields"):
        PluginManifest_Load(manifest, source="installed")


def test_cubemx_inventory_is_deep_and_has_no_parser_count_limit(
    workspace_root: Path,
) -> None:
    ioc = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_board_silverstar_0_5"
        / "payload"
        / "Flight_Controller0.5.ioc"
    )
    inventory = CubeMxInventory_Parse(ioc.read_text(encoding="utf-8-sig"))
    assert inventory.mcu_part == "STM32F407VET6"
    assert inventory.package == "LQFP100"
    assert len(inventory.uarts) == 3
    assert len(inventory.dmas) == 8
    assert len(inventory.nvic) >= 20
    assert inventory.clocks["RCC.SYSCLKFreq_VALUE"] == 168_000_000
    usart2 = next(item for item in inventory.uarts if item.instance == "USART2")
    assert usart2.settings["baud_rate"] == 921_600
    assert usart2.pins == {"rx": "PD6", "tx": "PD5"}
    assert any(item.instance == "DMA1_Stream5" for item in usart2.dma)
    assert usart2.irq is not None and usart2.irq.enabled
    assert any(
        pin.label == "GNSS_TIMEPULSE" and pin.exti_line == 6
        for pin in inventory.pins
    )

    synthetic = "\n".join(
        ["Mcu.CPN=STM32F407VET6"]
        + [f"Mcu.IP{index}=USART{index + 1}" for index in range(6)]
    )
    assert len(CubeMxInventory_Parse(synthetic).uarts) == 6


def test_cubemx_inventory_covers_all_supported_resource_categories() -> None:
    synthetic = "\n".join(
        (
            "Mcu.CPN=STM32F407VET6",
            "Mcu.Family=STM32F4",
            "Mcu.Package=LQFP100",
            "Mcu.Core=ARM Cortex-M4",
            "Mcu.IP0=USART1",
            "Mcu.IP1=SPI2",
            "Mcu.IP2=I2C1",
            "Mcu.IP3=ADC1",
            "Mcu.IP4=TIM3",
            "Mcu.IP5=CAN1",
            "PA9.Signal=USART1_TX",
            "PA9.GPIO_AF=GPIO_AF7_USART1",
            "PA10.Signal=USART1_RX",
            "PB13.Signal=SPI2_SCK",
            "PB14.Signal=SPI2_MISO",
            "PB15.Signal=SPI2_MOSI",
            "PB6.Signal=I2C1_SCL",
            "PB7.Signal=I2C1_SDA",
            "PB0.Signal=ADC1_IN8",
            "PA6.Signal=TIM3_CH1",
            "SH.S_TIM3_CH1.0=TIM3_CH1,PWM Generation1 CH1",
            "PB8.Signal=CAN1_RX",
            "PB9.Signal=CAN1_TX",
            "PC13.Signal=GPIO_EXTI13",
            "PC13.GPIO_Label=USER_BUTTON",
            "PD2.Signal=GPIO_Output",
            "PD2.GPIO_Label=STATUS_LED",
            "PD2.PinState=GPIO_PIN_SET",
            "USART1.BaudRate=115200",
            "USART1.WordLength=WORDLENGTH_8B",
            "USART1.Parity=PARITY_NONE",
            "USART1.StopBits=STOPBITS_1",
            "SPI2.Mode=SPI_MODE_MASTER",
            "SPI2.BaudRatePrescaler=SPI_BAUDRATEPRESCALER_8",
            "I2C1.Timing=0x20404768",
            "ADC1.NbrOfConversionFlag=1",
            "TIM3.Prescaler=83",
            "TIM3.Period=19999",
            "CAN1.Mode=CAN_MODE_NORMAL",
            "Dma.Request0=SPI2_RX",
            "Dma.SPI2_RX.0.Instance=DMA1_Stream3",
            "Dma.SPI2_RX.0.Channel=DMA_CHANNEL_0",
            "Dma.SPI2_RX.0.Direction=DMA_PERIPH_TO_MEMORY",
            "Dma.SPI2_RX.0.Mode=DMA_CIRCULAR",
            "Dma.SPI2_RX.0.Priority=DMA_PRIORITY_HIGH",
            "NVIC.SPI2_IRQn=true\\:1\\:0\\:false\\:false\\:true",
            "RCC.SYSCLKFreq_VALUE=168000000",
            "RCC.APB1Freq_Value=42000000",
        )
    )
    inventory = CubeMxInventory_Parse(
        synthetic,
        generated_sources=(
            """
TIM_HandleTypeDef htim3;
void MX_TIM3_Init(void)
{
    TIM_OC_InitTypeDef sConfigOC = {0};
    htim3.Instance = TIM3;
    htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
    sConfigOC.OCMode = TIM_OCMODE_PWM1;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
    HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1);
}
""",
        ),
    )
    assert inventory.core == "ARM Cortex-M4"
    assert len(inventory.uarts) == 1
    assert len(inventory.spis) == 1
    assert len(inventory.i2cs) == 1
    assert len(inventory.adcs) == 1
    assert len(inventory.timers) == 1
    assert len(inventory.pwms) == 1
    assert len(inventory.cans) == 1
    assert inventory.spis[0].pins == {
        "miso": "PB14",
        "mosi": "PB15",
        "sck": "PB13",
    }
    assert inventory.adcs[0].pins == {"in8": "PB0"}
    assert inventory.pwms[0].pins == {"out": "PA6"}
    assert inventory.pwms[0].instance == "TIM3_CH1"
    assert inventory.pwms[0].settings["physical_resource"] == "TIM3:CH1"
    assert inventory.cans[0].kind == "can_classic"
    assert inventory.dmas[0].instance == "DMA1_Stream3"
    assert inventory.nvic[0].enabled
    assert inventory.clocks["RCC.APB1Freq_Value"] == 42_000_000
    assert next(pin for pin in inventory.pins if pin.pin == "PA9").alternate_function == (
        "GPIO_AF7_USART1"
    )
    assert next(pin for pin in inventory.pins if pin.pin == "PC13").exti_line == 13


def test_resource_sufficiency_and_exclusive_conflicts_are_reported(
    builtin_catalog,
) -> None:
    missing = ReferenceProject_Create("MissingResource")
    missing.resource_assignments["imu0:data"] = ""
    missing_result = ResourceAssignments_Resolve(missing, builtin_catalog)
    assert any("Unassigned resource requirement" in error for error in missing_result.errors)

    conflict = ReferenceProject_Create("ResourceConflict")
    conflict.board = ""
    conflict.device_instances = [
        DeviceInstance("imu0", "silverstar.device.imu.jy901b"),
        DeviceInstance("gnss0", "silverstar.device.gnss.neo_m9n"),
    ]
    conflict.hardware = HardwareConfiguration(
        mode="custom",
        resources=(
            HardwareResource(
                "SHARED_UART",
                "uart",
                {
                    "physical_resource": "USART1",
                    "baud_rate": 230400,
                    "pins": {"rx": "PA10", "tx": "PA9"},
                    "dma": [
                        {"request": "USART1_RX", "instance": "DMA2_Stream2"}
                    ],
                    "irq": {"enabled": True},
                },
            ),
        ),
    )
    conflict.resource_assignments = {
        "imu0:data": "SHARED_UART",
        "gnss0:data": "SHARED_UART",
    }
    conflict_result = ResourceAssignments_Resolve(conflict, builtin_catalog)
    assert any("Resource conflict" in error for error in conflict_result.errors)


def test_decoder_profile_is_deterministic_data_only(builtin_catalog) -> None:
    model = ReferenceProject_Create("DecoderProfile")
    LoggingProfile_Reconcile(model, builtin_catalog)
    graph = SourceGraph_Resolve(model, builtin_catalog)
    metadata = MetadataFiles_Render(model, builtin_catalog, graph)
    first = metadata["DecoderProfile.ssdecoder"]
    second = MetadataFiles_Render(model, builtin_catalog, graph)[
        "DecoderProfile.ssdecoder"
    ]
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == [
            "README.md",
            "checksums.sha256",
            "manifest.json",
            "project_semantics.json",
            "record_catalog.json",
        ]
        assert not any(
            name.casefold().endswith(
                (".py", ".exe", ".dll", ".pyd", ".ps1", ".sh", ".bat")
            )
            for name in archive.namelist()
        )
        decoder_readme = archive.read("README.md")
        assert b"generic SilverStar_FLP decoder" in decoder_readme
        assert b"SSLOG0" not in decoder_readme
        manifest = json.loads(archive.read("manifest.json"))
        assert LogDecoderPackage_Verify(first) == manifest
        catalog_bytes = archive.read("record_catalog.json")
        semantics_bytes = archive.read("project_semantics.json")
        for canonical in (
            archive.read("manifest.json"),
            catalog_bytes,
            semantics_bytes,
        ):
            assert canonical.endswith(b"\n")
            assert b"\r" not in canonical
            assert not canonical.startswith(b"\xef\xbb\xbf")
            # Punctuation inside a description is data; check the complete JSON
            # canonicalization, not a byte substring that also matches strings.
            assert canonical == (
                json.dumps(json.loads(canonical), ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False) + "\n"
            ).encode("utf-8")
        assert manifest["record_catalog_sha256"] == hashlib.sha256(
            catalog_bytes
        ).hexdigest()
        assert manifest["project_semantics_sha256"] == hashlib.sha256(
            semantics_bytes
        ).hexdigest()
        checksums = {
            line.split("  ", 1)[1]: line.split("  ", 1)[0]
            for line in archive.read("checksums.sha256").decode("ascii").splitlines()
        }
        for name, expected in checksums.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
        semantics = json.loads(semantics_bytes)
        assert [
            (device["instance_id"], device["plugin"])
            for device in semantics["physical_devices"]
        ] == [
            (instance.instance_id, instance.plugin)
            for instance in model.device_instances
        ]
        assert semantics["devices"] == semantics["physical_devices"]
        assert all(
            device["vendor"] and device["model"] and device["descriptor_ids"]
            for device in semantics["physical_devices"]
            if device["plugin"]
            not in {
                "silverstar.device.indicator.system_status",
                "silverstar.device.indicator.gnss_status",
            }
        )
        assert all(
            {
                "descriptor_id",
                "physical_device_id",
                "physical_device_instance",
                "device_class",
                "instance_id",
                "plugin",
                "model",
                "capabilities",
            }.issubset(endpoint)
            for endpoint in semantics["capability_endpoints"]
        )
        assert semantics["raw_channel_id_templates"]["partition_by"] == [
            "source_descriptor_id",
            "instance_id",
            "physical_device_id",
        ]
        assert len(semantics["record_views"]) == len(model.logging_streams)
        assert all(
            "display_names" in view
            and "columns" in view
            and "validity" in view
            and "events" in view
            and "enums" in view
            and "logging" in view
            and "producer_components" in view
            for view in semantics["record_views"]
        )
        assert semantics["modes"] == model.modes
        assert len(semantics["available_records"]) == len(model.logging_streams)
        reference = json.loads(metadata["SilverStar.ssproject"])[
            "log_decoder_profile"
        ]
        assert reference["generation_profile_sha256"] == manifest[
            "generation_profile_sha256"
        ]
        assert reference["package_sha256"] == hashlib.sha256(first).hexdigest()

        generated = GeneratedFiles_Render(model, builtin_catalog, graph)
        header = generated[
            "Generated/Inc/project_log_decoder_profile.h"
        ].decode("utf-8")
        source = generated[
            "Generated/Src/project_log_decoder_profile.c"
        ].decode("utf-8")
        assert "PROJECT_LOG_DECODER_HASH_SIZE 16U" in header
        assert "ProjectLogDecoderProfile_Get(" in header
        assert "ProjectLogDecoderProfile_DescriptorGet" not in header
        assert json.loads(catalog_bytes)["catalog_schema_id"] == (
            "silverstar.sslog.record-catalog/1.0"
        )
        assert generated["Generated/project_semantics.json"] == semantics_bytes
        for digest in (
            manifest["record_catalog_sha256"],
            manifest["project_semantics_sha256"],
            manifest["generation_profile_sha256"],
        ):
            assert f"0x{digest[:2].upper()}U" in source
    corrupted = bytearray(first)
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        info = archive.getinfo("record_catalog.json")
        payload_offset = (
            info.header_offset
            + 30
            + len(info.filename.encode("utf-8"))
            + len(info.extra)
        )
    corrupted[payload_offset] ^= 0x01
    with pytest.raises(ValueError):
        LogDecoderPackage_Verify(bytes(corrupted))


def test_authorized_project_root_is_separate_from_internal_workspace(
    tmp_path: Path, builtin_catalog
) -> None:
    internal_root = tmp_path / "internal"
    external_root = tmp_path / "authorized_project"
    internal_root.mkdir()
    internal_policy = WorkspacePolicy(internal_root)
    output_policy = WorkspacePolicy(external_root)
    assembler = ProjectAssembler(internal_policy, builtin_catalog, output_policy)
    model = ReferenceProject_Create("AuthorizedOutput")
    plan = assembler.Plan(model, external_root)
    assert plan.valid
    assembler.Apply(model, plan)
    assert (external_root / "SilverStar.ssproject").is_file()
    assert (external_root / "AuthorizedOutput.ssdecoder").is_file()
    assert not any(internal_root.iterdir())
    with pytest.raises(WorkspacePolicyError):
        internal_policy.Path_Resolve(external_root)
    with pytest.raises(WorkspacePolicyError) as escape:
        output_policy.Path_Resolve(tmp_path / "escape")
    assert escape.value.code == "error.workspace_policy"
    assert "escapes authorized workspace" in escape.value.technical_detail


def test_other_sensors_are_plugin_driven_and_empty_state_stays_visible(qapp) -> None:
    translator = Translator("en_US")
    page = DevicesPage(translator)
    components = tuple(
        ComponentView(
            component_id=f"fixture.device.sensor_{index}",
            name=f"Sensor {index}",
            component_type=ComponentType.DEVICE,
            version="1.0.0",
            component_class="other_sensors",
            project_max=4,
            same_plugin_multiple=True,
            multi_instance_ready=True,
            options={"device_category": "sensor.temperature"},
        )
        for index in (1, 2)
    )
    emitted: list[tuple[str, bool]] = []
    page.otherDeviceToggled.connect(
        lambda plugin_id, selected: emitted.append((plugin_id, selected))
    )
    instance = DeviceInstanceView(
        "sensor0",
        components[0].component_id,
        components[0].name,
        "other_sensors",
        (),
        (),
        (),
        project_max=4,
        same_plugin_multiple=True,
        multi_instance_ready=True,
    )
    page.Configuration_Set(components, (instance,))
    assert page.device_checks[components[0].component_id].isChecked()
    page.device_checks[components[1].component_id].setChecked(True)
    qapp.processEvents()
    assert emitted[-1] == ("fixture.device.sensor_2", True)
    page.Configuration_Set((), ())
    assert not page.device_checks
    assert not page.other_group.isHidden()
    assert not page.other_empty_label.isHidden()


def test_instance_device_rows_expose_add_and_remove_actions(qapp) -> None:
    translator = Translator("zh_CN")
    page = DevicesPage(translator)
    component = ComponentView(
        component_id="fixture.device.imu.contextual",
        name="上下文化 IMU",
        component_type=ComponentType.DEVICE,
        version="1.0.0",
        component_class="imu",
        project_max=2,
        plugin_max=2,
        class_max=2,
        same_plugin_multiple=True,
        multi_instance_ready=True,
        options={
                "device_selection_style": "instance",
                "device_category": "sensor.imu",
                "device_group": "primary_devices",
            "device_group_order": 20,
        },
    )
    instance = DeviceInstanceView(
        instance_id="imu0",
        plugin_id=component.component_id,
        name=component.name,
        component_class="imu",
        provides=("imu.acceleration", "imu.angular_rate"),
        consumed=(),
        unused=("imu.acceleration", "imu.angular_rate"),
        project_max=2,
        plugin_max=2,
        class_max=2,
        same_plugin_multiple=True,
        multi_instance_ready=True,
    )
    changes: list[tuple[str, str]] = []
    additions: list[str] = []
    page.instanceChanged.connect(
        lambda instance_id, plugin_id: changes.append((instance_id, plugin_id))
    )
    page.instanceAddRequested.connect(additions.append)
    page.Configuration_Set((component,), (instance,))
    try:
        assert "imu0" in page.remove_buttons
        assert "imu" in page.add_buttons
        page.remove_buttons["imu0"].click()
        page.add_buttons["imu"].click()
        assert changes[-1] == ("imu0", "")
        assert additions[-1] == "imu"
    finally:
        page.close()


def test_instance_device_row_can_add_a_different_singleton_model(qapp) -> None:
    translator = Translator("en_US")
    page = DevicesPage(translator)
    options = {
        "device_selection_style": "instance",
        "device_category": "sensor.imu",
        "device_group": "primary_devices",
        "device_group_order": 20,
    }
    first = ComponentView(
        component_id="fixture.device.imu.singleton_a",
        name="Singleton IMU A",
        component_type=ComponentType.DEVICE,
        version="1.0.0",
        component_class="imu",
        project_max=2,
        plugin_max=1,
        class_max=2,
        same_plugin_multiple=False,
        multi_instance_ready=False,
        options=options,
    )
    second = ComponentView(
        component_id="fixture.device.imu.singleton_b",
        name="Singleton IMU B",
        component_type=ComponentType.DEVICE,
        version="1.0.0",
        component_class="imu",
        project_max=2,
        plugin_max=1,
        class_max=2,
        same_plugin_multiple=False,
        multi_instance_ready=False,
        options=options,
    )
    instance = DeviceInstanceView(
        instance_id="imu0",
        plugin_id=first.component_id,
        name=first.name,
        component_class="imu",
        provides=("imu.acceleration", "imu.angular_rate"),
        consumed=(),
        unused=("imu.acceleration", "imu.angular_rate"),
        project_max=2,
        plugin_max=1,
        class_max=2,
        same_plugin_multiple=False,
        multi_instance_ready=False,
    )
    additions: list[str] = []
    page.instanceAddRequested.connect(additions.append)
    page.Configuration_Set((first, second), (instance,))
    try:
        assert "imu" in page.add_buttons
        combo = page.device_combos["imu0"]
        assert combo.model().item(combo.findData(second.component_id)).isEnabled()
        page.add_buttons["imu"].click()
        assert additions == ["imu"]
    finally:
        page.close()


def test_fixed_board_connections_have_ioc_physical_details(
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("PhysicalBoard")
    service.Resources_AutoAssign(model)
    views = service.ResourceRequirementViews_Get(model)
    imu_uart = next(
        view
        for view in views
        if view.key == "imu0:data"
    )
    assert imu_uart.fixed
    assert imu_uart.assignment == "PLATFORM_UART_1"
    assert imu_uart.physical_resource == "USART1"
    assert "RX=PA10" in imu_uart.physical_details
    assert "DMA2_Stream2" in imu_uart.physical_details


def test_message_box_buttons_are_localized(tmp_path: Path, qapp) -> None:
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"), language="zh_CN")
    try:
        box = window._MessageBox_Create(
            QMessageBox.Icon.Question,
            "title",
            "text",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        assert box.button(QMessageBox.StandardButton.Yes).text() == "是"
        assert box.button(QMessageBox.StandardButton.No).text() == "否"
        details_box = window._MessageBox_Create(
            QMessageBox.Icon.Critical,
            "title",
            "text",
            details="technical detail",
        )
        button_box = details_box.findChild(QDialogButtonBox)
        assert button_box is not None
        details_button = next(
            button
            for button in details_box.findChildren(QPushButton)
            if button_box.buttonRole(button)
            == QDialogButtonBox.ButtonRole.ActionRole
        )
        assert details_button.text() == "显示详情"
        details_button.click()
        assert details_button.text() == "隐藏详情"
    finally:
        window.close()


def test_chinese_build_failure_uses_localized_summary_and_keeps_raw_log(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    window = MainWindow(SettingsStore(tmp_path / "build-error.ini"), language="zh_CN")
    shown: list[dict[str, str]] = []

    def message_box(
        _icon,
        title: str,
        text: str,
        _buttons=QMessageBox.StandardButton.Ok,
        _default=QMessageBox.StandardButton.NoButton,
        *,
        details: str = "",
    ) -> QMessageBox.StandardButton:
        shown.append({"title": title, "text": text, "details": details})
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(window, "_MessageBox_Exec", message_box)
    try:
        raw_output = "mingw32-make: *** No rule to make target 'all'. Stop."
        window._Build_Complete(
            BuildResult(
                BuildAction.ARCHITECTURE_CHECK,
                ("mingw32-make", "architecture-check"),
                2,
                raw_output,
            )
        )
        assert raw_output in window.build_page.build_log.toPlainText()
        assert shown[-1]["title"] == "操作失败"
        assert shown[-1]["text"] == "架构检查失败，请查看日志。"
        assert "mingw32-make" not in shown[-1]["text"]
        assert shown[-1]["details"] == raw_output

        window._Error_Show(ValueError("raw internal English exception"))
        assert shown[-1]["text"].startswith("操作失败")
        assert shown[-1]["details"] == "raw internal English exception"
    finally:
        window.close()
        qapp.processEvents()
