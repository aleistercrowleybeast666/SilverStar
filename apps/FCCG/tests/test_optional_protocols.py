from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from itertools import product
from pathlib import Path

import pytest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.generator.log_decoder_profile import (
    LogDecoderPackage_Verify,
)
from silverstar_fccg.generator.render import (
    GeneratedFiles_Render,
    MetadataFiles_Render,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.generation_state import ProjectDigest_Get
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    ProtocolLogDefinitions_Get,
)
from silverstar_fccg.project.model import (
    PROJECT_FORMAT_VERSION,
    PROTOCOL_CATEGORIES,
    DeviceInstance,
    ProjectModel_Parse,
)
from silverstar_fccg.project.protocols import (
    ProtocolProfileAvailabilities_Get,
    ProtocolResolution_Resolve,
)
from silverstar_fccg.ui.main_window import MainWindow

TELEMETRY_DEVICE = "silverstar.device.telemetry.sx1281"
STORAGE_DEVICE = "silverstar.device.storage.sd_sdio_fatfs"


def test_default_protocol_wire_sources_match_read_only_reference_hashes(
    workspace_root: Path,
) -> None:
    provenance = json.loads(
        (workspace_root / "plugins/builtin/reference_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    payload_sources = {
        "Protocol/Src/air_protocol.c": (
            "plugins/builtin/silverstar_protocol_telemetry_air_m0/payload/"
            "Protocol/Src/air_protocol.c"
        ),
        "Protocol/SSLOG/Src/sslog_protocol.c": (
            "plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/"
            "Protocol/SSLOG/Src/sslog_protocol.c"
        ),
    }

    for source, payload_relative in payload_sources.items():
        digest = hashlib.sha256(
            (workspace_root / payload_relative).read_bytes()
        ).hexdigest()
        assert digest == provenance.get("fccg_protocol_source_sha256", {}).get(
            source, provenance["protocol_source_sha256"][source]
        )


def _DeviceInstancesForPlugin_Get(model, component_id: str) -> list[DeviceInstance]:
    return [
        instance
        for instance in model.device_instances
        if instance.plugin == component_id
    ]


def _ProtocolModel_Get(
    service: FccgService,
    telemetry: bool,
    maintenance: bool,
    logging: bool,
):
    model = service.ReferenceProject_Create(
        f"Protocols_T{int(telemetry)}_M{int(maintenance)}_L{int(logging)}"
    )
    for category, enabled in zip(
        PROTOCOL_CATEGORIES,
        (telemetry, maintenance, logging),
        strict=True,
    ):
        if not enabled:
            model.protocols[category] = None
    return service.ProjectConfiguration_Reconcile(model).model


def test_project_format_11_round_trips_null_protocols_and_preserves_v10(
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    original = service.ReferenceProject_Create("ProtocolMigration")
    original_selections = deepcopy(original.protocols)
    legacy = original.Dictionary_Get()
    legacy["format_version"] = 10

    migrated = ProjectModel_Parse(legacy)

    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert migrated.protocols == original_selections
    assert all(migrated.protocols[category] is not None for category in PROTOCOL_CATEGORIES)

    disabled = migrated.Dictionary_Get()
    disabled["protocols"] = {category: None for category in PROTOCOL_CATEGORIES}
    disabled["log_decoder_profile"] = {
        "relative_path": "",
        "package_schema": "",
        "container_plugin_id": "",
        "generation_profile_sha256": "",
        "package_sha256": "",
    }
    reparsed = ProjectModel_Parse(disabled)

    assert reparsed.Dictionary_Get()["protocols"] == {
        "logging": None,
        "maintenance": None,
        "telemetry": None,
    }
    assert reparsed.ProtocolComponentIds_Get() == ()
    assert reparsed.ProtocolProfiles_Get() == {}
    protocol_components = {
        selection.component
        for selection in original_selections.values()
        if selection is not None
    }
    assert protocol_components.isdisjoint(reparsed.ComponentIds_Get())
    assert ProjectDigest_Get(reparsed) == ProjectDigest_Get(
        ProjectModel_Parse(reparsed.Dictionary_Get())
    )


def test_device_removal_clears_protocol_and_readding_does_not_restore(
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("ProtocolDeviceTransitions")
    telemetry_instances = _DeviceInstancesForPlugin_Get(model, TELEMETRY_DEVICE)
    storage_instances = _DeviceInstancesForPlugin_Get(model, STORAGE_DEVICE)
    assert len(telemetry_instances) == len(storage_instances) == 1

    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.plugin != TELEMETRY_DEVICE
    ]
    reconciled = service.ProjectConfiguration_Reconcile(model)
    model = reconciled.model
    assert model.protocols["telemetry"] is None
    assert any(
        notice.code == "configuration.protocol_transport_removed"
        and notice.slot == "telemetry"
        for notice in reconciled.notices
    )

    model.device_instances.extend(telemetry_instances)
    model = service.ProjectConfiguration_Reconcile(model).model
    assert model.protocols["telemetry"] is None
    assert _DeviceInstancesForPlugin_Get(model, TELEMETRY_DEVICE)

    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.plugin != STORAGE_DEVICE
    ]
    reconciled = service.ProjectConfiguration_Reconcile(model)
    model = reconciled.model
    assert model.protocols["logging"] is None
    assert any(
        notice.code == "configuration.protocol_transport_removed"
        and notice.slot == "logging"
        for notice in reconciled.notices
    )

    model.device_instances.extend(storage_instances)
    model = service.ProjectConfiguration_Reconcile(model).model
    assert model.protocols["logging"] is None
    assert _DeviceInstancesForPlugin_Get(model, STORAGE_DEVICE)


def test_maintenance_endpoint_is_declaratively_added_and_removed(
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("MaintenanceEndpoint")
    maintenance_selection = model.protocols["maintenance"]
    assert maintenance_selection is not None
    internal_manifests = tuple(
        manifest
        for manifest in service.catalog.Type_Get("device")
        if manifest.metadata.get("auto_managed_protocol_category")
        == "maintenance"
    )
    assert internal_manifests
    internal_plugins = {manifest.component_id for manifest in internal_manifests}
    managed_instance_ids = {
        instance.instance_id
        for instance in model.device_instances
        if instance.plugin in internal_plugins
    }
    assert managed_instance_ids

    model.protocols["maintenance"] = None
    model = service.ProjectConfiguration_Reconcile(model).model
    graph = SourceGraph_Resolve(model, service.catalog)
    remaining_ids = {
        instance.instance_id
        for instance in model.device_instances
        if instance.plugin in internal_plugins
    }
    assert not remaining_ids
    assert not any(
        key.partition(":")[0] in managed_instance_ids
        for key in model.resource_assignments
    )
    assert "APP/Src/serial_task.c" not in graph.sources
    assert "System/Src/system_console.c" not in graph.sources
    assert "System/Src/system_console.c" in graph.exclude_sources

    model.protocols["maintenance"] = maintenance_selection
    model = service.ProjectConfiguration_Reconcile(model).model
    graph = SourceGraph_Resolve(model, service.catalog)
    endpoints = [
        instance
        for instance in model.device_instances
        if instance.plugin in internal_plugins
    ]
    assert len(endpoints) == 1
    assert endpoints[0].instance_id == "maintenance0"
    assert any(
        key.startswith("maintenance0:") for key in model.resource_assignments
    )
    assert "APP/Src/serial_task.c" in graph.sources
    assert "System/Src/system_console.c" in graph.sources
    assert "System/Src/system_console.c" not in graph.exclude_sources


def test_protocol_availability_supports_ordered_telemetry_transports(
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("ProtocolAvailability")
    selection = model.protocols["telemetry"]
    assert selection is not None
    key = ("telemetry", selection.component, selection.profile)

    availability = ProtocolProfileAvailabilities_Get(model, service.catalog)[key]
    assert availability.available

    without_transport = deepcopy(model)
    without_transport.device_instances = [
        instance
        for instance in without_transport.device_instances
        if instance.plugin != TELEMETRY_DEVICE
    ]
    availability = ProtocolProfileAvailabilities_Get(
        without_transport, service.catalog
    )[key]
    assert not availability.available
    assert availability.reason_code == "protocol.unavailable.transport_missing"

    ambiguous = deepcopy(model)
    ambiguous.device_instances.append(DeviceInstance("telemetry1", TELEMETRY_DEVICE))
    availability = ProtocolProfileAvailabilities_Get(ambiguous, service.catalog)[key]
    assert availability.available
    assert availability.reason_code == ""
    resolution = ProtocolResolution_Resolve(ambiguous, service.catalog)
    assert resolution.valid
    binding = next(
        item for item in resolution.bindings if item.category == "telemetry"
    )
    assert binding.transport_selection == "ordered_failover"
    assert binding.candidate_instances == ("telemetry0", "telemetry1")


@pytest.mark.parametrize(
    ("telemetry", "maintenance", "logging"),
    tuple(product((True, False), repeat=3)),
)
def test_all_protocol_combinations_render_exact_sources_and_artifacts(
    workspace_root: Path,
    telemetry: bool,
    maintenance: bool,
    logging: bool,
) -> None:
    service = FccgService(workspace_root)
    model = _ProtocolModel_Get(service, telemetry, maintenance, logging)
    graph = SourceGraph_Resolve(model, service.catalog)
    generated = GeneratedFiles_Render(model, service.catalog, graph)
    metadata = MetadataFiles_Render(model, service.catalog, graph)
    sources = set(graph.sources)

    for source in (
        "APP/Src/telemetry_task.c",
        "Modules/Src/telemetry_service.c",
        "Protocol/Src/air_protocol.c",
    ):
        assert (source in sources) is telemetry
    assert (
        "Devices/Telemetry/SX1281/Adapter/Src/"
        "sx1281_telemetry_adapter.c"
    ) in sources
    for source in (
        "APP/Src/serial_task.c",
        "System/Src/system_console.c",
        "Devices/Console/UART/Src/console_uart_device.c",
        "Devices/Console/UART/Adapter/Src/uart_console_adapter.c",
    ):
        assert (source in sources) is maintenance
    for source in (
        "APP/Src/logger_task.c",
        "System/Src/system_log_policy.c",
        "Devices/Storage/SdSdioFatFs/Src/log_sink_service.c",
        "Protocol/SSLOG/Src/sslog_protocol.c",
        "Generated/Src/project_log_config.c",
        "Generated/Src/project_log_decoder_profile.c",
    ):
        assert (source in sources) is logging

    if logging:
        definitions = {
            definition.record: definition
            for definition in ProtocolLogDefinitions_Get(model, service.catalog)
        }
        assert LogAvailability_Get(
            definitions["FLIGHT_LOG_RECORD_STATS"], model, service.catalog
        ).available
        assert (
            LogAvailability_Get(
                definitions["FLIGHT_LOG_RECORD_TELEMETRY_DIAG"],
                model,
                service.catalog,
            ).available
            is telemetry
        )
        streams = {stream.record: stream for stream in model.logging_streams}
        assert streams["FLIGHT_LOG_RECORD_STATS"].enabled
        assert (
            streams["FLIGHT_LOG_RECORD_TELEMETRY_DIAG"].enabled
            is telemetry
        )

    assert bool(_DeviceInstancesForPlugin_Get(model, TELEMETRY_DEVICE))
    assert bool(_DeviceInstancesForPlugin_Get(model, STORAGE_DEVICE))
    maintenance_ids = {
        instance.instance_id
        for instance in model.device_instances
        if service.catalog.Component_Get(instance.plugin).metadata.get(
            "auto_managed_protocol_category"
        )
        == "maintenance"
    }
    assert bool(maintenance_ids) is maintenance
    if not maintenance:
        maintenance_instance_id = str(
            service.catalog.Component_Get(
                "silverstar.device.console.uart"
            ).metadata["default_instance_id"]
        )
        assert not any(
            key.partition(":")[0] == maintenance_instance_id
            for key in model.resource_assignments
        )

    header = generated["Generated/Inc/project_flight_config.h"].decode("utf-8")
    for name, enabled in (
        ("TELEMETRY", telemetry),
        ("MAINTENANCE", maintenance),
        ("LOGGING", logging),
    ):
        assert re.search(
            rf"^#define SILVERSTAR_PROTOCOL_{name}_ENABLED\s+"
            rf"{int(enabled)}U$",
            header,
            re.MULTILINE,
        )
    expected_tag = (
        "{0x41U, 0x49U, 0x52U, 0x2DU, 0x4EU, 0x43U, 0x52U, 0x43U}"
        if telemetry
        else "{0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U}"
    )
    assert re.search(
        r"^#define SILVERSTAR_LOG_TELEMETRY_COMPATIBILITY_TAG\s+"
        + re.escape(expected_tag)
        + r"$",
        header,
        re.MULTILINE,
    )

    semantics = json.loads(generated["Generated/project_semantics.json"])
    assert {
        "capability_endpoints",
        "capability_routes",
        "canonical_channels",
        "component_locks",
        "device_descriptors",
        "enabled_capabilities",
        "physical_device_ids",
        "physical_devices",
        "protocol_bindings",
        "resource_assignments",
    } <= set(semantics)
    for category, enabled in zip(
        PROTOCOL_CATEGORIES,
        (telemetry, maintenance, logging),
        strict=True,
    ):
        assert (semantics["protocols"][category] is not None) is enabled
    project_descriptor = json.loads(metadata["SilverStar.ssproject"])
    assert project_descriptor["format_version"] == PROJECT_FORMAT_VERSION

    decoder_path = f"{model.identity.name}.ssdecoder"
    decoder_files = {
        "Generated/Inc/project_log_decoder_profile.h",
        "Generated/Src/project_log_decoder_profile.c",
        "Logs/Golden/expected.json",
        decoder_path,
    }
    rendered_paths = set(generated) | set(metadata)
    if logging:
        assert decoder_files <= rendered_paths
        decoder_manifest = LogDecoderPackage_Verify(metadata[decoder_path])
        assert decoder_manifest["package_schema"] == {
            "id": "silverstar.ssdecoder.package-schema/1.2",
            "major": 1,
            "minor": 2,
        }
        assert decoder_manifest["protocols"]["logging"] is not None
        assert (decoder_manifest["protocols"]["telemetry"] is not None) is telemetry
        assert (decoder_manifest["protocols"]["maintenance"] is not None) is maintenance
    else:
        assert decoder_files.isdisjoint(rendered_paths)
        assert semantics["available_records"] == []
        assert all(
            not stream["enabled"] for stream in semantics["logging_streams"]
        )
        assert project_descriptor["log_decoder_profile"] == {
            "relative_path": "",
            "package_schema": "",
            "container_plugin_id": "",
            "generation_profile_sha256": "",
            "package_sha256": "",
        }


def test_disabling_logging_removes_only_stale_managed_decoder_outputs(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "LoggingDisabled"
    model = service.ReferenceProject_Create("LoggingDisabled")
    service.Project_Save(model, project_root)
    managed_decoder_outputs = (
        project_root / "LoggingDisabled.ssdecoder",
        project_root / "Generated/Inc/project_log_decoder_profile.h",
        project_root / "Generated/Src/project_log_decoder_profile.c",
        project_root / "Logs/Golden/expected.json",
        project_root / "Logs/README.md",
    )
    assert all(path.is_file() for path in managed_decoder_outputs)
    manual_log = project_root / "Logs/manual-flight.sslog"
    manual_log.write_bytes(b"user-owned-log")

    model.protocols["logging"] = None
    service.Project_Save(model, project_root, confirm_dangerous=True)

    assert all(not path.exists() for path in managed_decoder_outputs)
    assert manual_log.read_bytes() == b"user-owned-log"
    assert model.log_decoder_profile.relative_path == ""
    assert service.ProjectReadiness_Get(model, project_root).ready
    exported = project_root / "disabled.ssdecoder"
    with pytest.raises(FccgError) as error:
        service.LogDecoderProfile_Export(model, project_root, exported)
    assert error.value.code == "error.log_decoder_profile_logging_disabled"
    assert not exported.exists()


def test_protocol_combos_and_logging_disabled_state_are_stable(
    tmp_path: Path,
    qapp,
) -> None:
    window = MainWindow(SettingsStore(tmp_path / "optional-protocols-ui.ini"))
    try:
        window.show()
        qapp.processEvents()
        assert set(window.flight_configuration_page.protocol_combos) == set(
            PROTOCOL_CATEGORIES
        )
        for combo in window.flight_configuration_page.protocol_combos.values():
            assert combo.count() >= 2
            assert combo.itemData(0) is None
            assert combo.itemText(0) == "不使用"

        telemetry_combo = next(
            combo
            for combo in window.devices_page.device_combos.values()
            if combo.findData(TELEMETRY_DEVICE) >= 0
        )
        telemetry_instance_id = next(
            instance.instance_id
            for instance in window._model.device_instances
            if instance.plugin == TELEMETRY_DEVICE
        )
        assert window.devices_page.device_combos[telemetry_instance_id] is (
            telemetry_combo
        )
        telemetry_combo.setCurrentIndex(0)
        qapp.processEvents()
        assert window._model.protocols["telemetry"] is None
        telemetry_combo = window.flight_configuration_page.protocol_combos[
            "telemetry"
        ]
        assert telemetry_combo.currentIndex() == 0
        telemetry_item = telemetry_combo.model().item(1)
        assert telemetry_item is not None and not telemetry_item.isEnabled()
        assert "兼容" in telemetry_item.toolTip()

        telemetry_combo = next(
            combo
            for combo in window.devices_page.device_combos.values()
            if combo.findData(TELEMETRY_DEVICE) >= 0
        )
        telemetry_combo.setCurrentIndex(
            telemetry_combo.findData(TELEMETRY_DEVICE)
        )
        qapp.processEvents()
        assert window._model.protocols["telemetry"] is None
        telemetry_item = window.flight_configuration_page.protocol_combos[
            "telemetry"
        ].model().item(1)
        assert telemetry_item is not None and telemetry_item.isEnabled()

        logging_combo = window.flight_configuration_page.protocol_combos["logging"]
        logging_combo.setCurrentIndex(0)
        qapp.processEvents()
        assert window._model.protocols["logging"] is None
        page = window.flight_configuration_page
        assert not page.logging_table.isEnabled()
        assert not page.logging_select_all_button.isEnabled()
        assert not page.logging_required_only_button.isEnabled()
        assert not page.log_decoder_export_button.isEnabled()
        assert not page.logging_disabled_label.isHidden()

        del telemetry_item
        del telemetry_combo
        del logging_combo
        del combo
        window.Language_Apply("en_US")
        qapp.processEvents()
        for combo in window.flight_configuration_page.protocol_combos.values():
            assert combo.itemText(0) == "None"
        assert window.flight_configuration_page.protocol_combos[
            "logging"
        ].currentIndex() == 0
    finally:
        window.close()
        qapp.processEvents()


def test_logging_protocol_reopens_after_storage_is_restored_and_survives_refresh(
    tmp_path: Path,
    qapp,
) -> None:
    window = MainWindow(SettingsStore(tmp_path / "logging-reopen-ui.ini"))
    try:
        window.show()
        qapp.processEvents()

        storage_check = window.devices_page.device_checks[STORAGE_DEVICE]
        assert storage_check.isChecked()
        storage_check.click()
        qapp.processEvents()
        assert window._model.protocols["logging"] is None

        storage_check = window.devices_page.device_checks[STORAGE_DEVICE]
        assert not storage_check.isChecked()
        storage_check.click()
        qapp.processEvents()
        assert window._model.DeviceInstance_Get("storage0") is not None

        logging_combo = window.flight_configuration_page.protocol_combos["logging"]
        assert logging_combo.currentIndex() == 0
        logging_index = next(
            index
            for index in range(1, logging_combo.count())
            if logging_combo.model().item(index).isEnabled()
        )
        selected_logging = logging_combo.itemData(logging_index)
        assert isinstance(selected_logging, (list, tuple))
        assert len(selected_logging) == 2
        logging_combo.setCurrentIndex(logging_index)
        qapp.processEvents()

        page = window.flight_configuration_page
        selected = window._model.protocols["logging"]
        assert selected is not None
        assert (selected.component, selected.profile) == tuple(selected_logging)
        assert page.logging_table.isEnabled()
        assert page.logging_table.rowCount() > 0
        assert page.logging_table.rowCount() == len(page.Streams_Get())

        telemetry_combo = page.protocol_combos["telemetry"]
        telemetry_combo.setCurrentIndex(0)
        qapp.processEvents()

        assert window._model.protocols["logging"] is not None
        assert page.protocol_combos["logging"].currentIndex() > 0
        assert page.logging_table.isEnabled()
        assert page.logging_table.rowCount() > 0
    finally:
        window.close()
        qapp.processEvents()
