from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

import yaml
from PySide6.QtWidgets import QFileDialog

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.generator.render import (
    _DeviceInstancesHeader_Render,
    _DeviceInstancesSource_Render,
    _MetadataSource_Render,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.capabilities import (
    CapabilityKind,
    CapabilityKind_Get,
    CapabilityResolution_Resolve,
    CapabilitySourceOverrides_Reconcile,
)
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    LoggingProfile_Reconcile,
    ProjectRecordableOutputs_Get,
    ProtocolLogDefinitions_Get,
)
from silverstar_fccg.project.model import (
    PROJECT_FORMAT_VERSION,
    DeviceInstance,
    ProjectModel_Load,
    ProjectModel_Parse,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import ResourceRequirementOptions_Get
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.widgets import LockedCheckBox, StandardCheckBox


def _MultiBarometerCatalog_Create(
    workspace_root: Path,
    installed_root: Path,
    *,
    recordable_magnetometer: bool = False,
) -> PluginCatalog:
    package = installed_root / "fixture.device.sensor.bmp280" / "1.0.0"
    package.mkdir(parents=True)
    (package / "payload" / "Fixture").mkdir(parents=True)
    manifest = {
        "schema_version": 0,
        "id": "fixture.device.sensor.bmp280",
        "name": "BMP280",
        "type": "device",
        "class": "other_sensors",
        "instance_policy": {
            "project_max": 4,
            "same_plugin_multiple": True,
            "multi_instance_ready": True,
        },
        "physical_device": {
            "vendor": "Bosch",
            "model": "BMP280",
            "chipset": "BMP280",
            "driver": "Fixture BMP280 Driver",
        },
        "version": "1.0.0",
        "description": "Test-only declarative physical barometer.",
        "requires": {
            "components": [
                {"id": "silverstar.core.0_1_0", "optional": False}
            ],
            "resources": [],
            "capabilities": [],
        },
        "resources": {"provides": [], "roles": [], "conflicts": []},
        "provides": [
            "barometer.altitude",
            *(["magnetometer.field"] if recordable_magnetometer else []),
        ],
        "build": {
            "sources": [],
            "asm_sources": [],
            "include_dirs": [],
            "defines": [],
        },
        "payload": {"roots": ["Fixture"]},
        "metadata": {
            "device_category": "sensor.barometer",
            "display_names": {"zh_CN": "BMP280", "en_US": "BMP280"},
            **(
                {
                    "recordable_outputs": {
                        "magnetometer.field": {"enabled": True}
                    }
                }
                if recordable_magnetometer
                else {}
            ),
        },
    }
    (package / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    catalog = PluginCatalog(workspace_root / "plugins" / "builtin", installed_root)
    catalog.Scan()
    return catalog


def _MultiInstanceDeviceCatalog_Create(
    workspace_root: Path, installed_root: Path
) -> PluginCatalog:
    specifications = (
        (
            "fixture.device.imu.contextual",
            "imu",
            ("device.imu", "imu.acceleration", "imu.angular_rate"),
        ),
        (
            "fixture.device.gnss.contextual",
            "gnss",
            ("device.gnss", "gnss.position", "gnss.velocity"),
        ),
    )
    for component_id, component_class, capabilities in specifications:
        package = installed_root / component_id / "1.0.0"
        payload = package / "payload"
        source_relative = f"Fixture/{component_class}/contextual_device.c"
        source = payload / source_relative
        source.parent.mkdir(parents=True)
        source.write_text(
            f"void Fixture_{component_class.capitalize()}Process(void) {{}}\n",
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 0,
            "id": component_id,
            "name": f"Contextual {component_class.upper()}",
            "type": "device",
            "class": component_class,
            "instance_policy": {
                "plugin_max": 2,
                "class_max": 2,
                "same_plugin_multiple": True,
                "multi_instance_ready": True,
            },
            "physical_device": {
                "vendor": "Fixture",
                "model": f"CTX-{component_class.upper()}",
                "chipset": "TEST",
                "driver": "Context-safe fixture driver",
            },
            "version": "1.0.0",
            "description": "Test-only context-safe multi-instance device.",
            "requires": {
                "components": [
                    {"id": "silverstar.core.0_1_0", "optional": False}
                ],
                "resources": [{"name": "data", "kind": "uart"}],
                "capabilities": [],
            },
            "resources": {"provides": [], "roles": [], "conflicts": []},
            "provides": list(capabilities),
            "build": {
                "sources": [source_relative],
                "asm_sources": [],
                "include_dirs": [],
                "defines": [],
            },
            "payload": {"roots": [f"Fixture/{component_class}"]},
            "metadata": {
                "device_category": (
                    "sensor.imu"
                    if component_class == "imu"
                    else "sensor.gnss"
                ),
                "display_names": {
                    "zh_CN": f"上下文化 {component_class.upper()}",
                    "en_US": f"Contextual {component_class.upper()}",
                },
                "device_descriptors": [
                    {
                        "order": 1 if component_class == "imu" else 2,
                        "physical_device_id": (
                            "PROJECT_PHYSICAL_DEVICE_ID_FIXTURE_IMU"
                            if component_class == "imu"
                            else "PROJECT_PHYSICAL_DEVICE_ID_FIXTURE_GNSS"
                        ),
                        "class": (
                            "SYSTEM_DEVICE_CLASS_IMU"
                            if component_class == "imu"
                            else "SYSTEM_DEVICE_CLASS_GNSS"
                        ),
                        "flags": "SYSTEM_DESCRIPTOR_FLAG_ENABLED",
                        "capability": (
                            "SYSTEM_CAPABILITY_IMU"
                            if component_class == "imu"
                            else "SYSTEM_CAPABILITY_GNSS"
                        ),
                        "rate": "100U",
                        "driver_hash": "0x12345678UL",
                        "name_hash": "0x87654321UL",
                    }
                ],
                "device_instance_bindings": {
                    (
                        "SYSTEM_DEVICE_CLASS_IMU"
                        if component_class == "imu"
                        else "SYSTEM_DEVICE_CLASS_GNSS"
                    ): {
                        "function_prefix": (
                            "FixtureImu"
                            if component_class == "imu"
                            else "FixtureGnss"
                        ),
                        "pass_instance": True,
                    }
                },
            },
        }
        (package / "plugin.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
    catalog = PluginCatalog(workspace_root / "plugins" / "builtin", installed_root)
    catalog.Scan()
    return catalog


def _MixedSingletonDeviceCatalog_Create(
    workspace_root: Path, installed_root: Path
) -> PluginCatalog:
    capabilities = (
        "device.imu",
        "imu.acceleration",
        "imu.angular_rate",
        "attitude.external",
        "magnetometer.field",
        "barometer.altitude",
        "attitude.external.preflight_alignment_6axis_qualified",
        "attitude.external.preflight_alignment_9axis_qualified",
        "attitude.external.preflight_fallback_qualified",
        "imu.software_alignment_qualified",
        "imu.software_propagation_qualified",
        "imu.landing_stillness_qualified",
        "barometer.landing_window_qualified",
    )
    for suffix in ("a", "b"):
        component_id = f"fixture.device.imu.singleton_{suffix}"
        package = installed_root / component_id / "1.0.0"
        payload = package / "payload" / "Fixture" / suffix
        payload.mkdir(parents=True)
        (payload / "README.md").write_text(
            "Test-only singleton IMU payload.\n", encoding="utf-8"
        )
        manifest = {
            "schema_version": 0,
            "id": component_id,
            "name": f"Singleton IMU {suffix.upper()}",
            "type": "device",
            "class": "imu",
            "instance_policy": {
                "plugin_max": 1,
                "class_max": 2,
                "same_plugin_multiple": False,
                "multi_instance_ready": False,
            },
            "physical_device": {
                "vendor": "Fixture",
                "model": f"SINGLETON-{suffix.upper()}",
                "chipset": "TEST",
                "driver": "Singleton fixture driver",
            },
            "version": "1.0.0",
            "description": "Test-only distinct singleton IMU.",
            "requires": {
                "components": [
                    {"id": "silverstar.core.0_1_0", "optional": False}
                ],
                "resources": [],
                "capabilities": [],
            },
            "resources": {"provides": [], "roles": [], "conflicts": []},
            "provides": list(capabilities),
            "build": {
                "sources": [],
                "asm_sources": [],
                "include_dirs": [],
                "defines": [],
            },
            "payload": {"roots": [f"Fixture/{suffix}"]},
            "metadata": {
                "device_category": "sensor.imu",
                "display_names": {
                    "zh_CN": f"单实例 IMU {suffix.upper()}",
                    "en_US": f"Singleton IMU {suffix.upper()}",
                },
                "device_selection_style": "instance",
                "device_group": "primary_devices",
            },
        }
        (package / "plugin.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
    catalog = PluginCatalog(workspace_root / "plugins" / "builtin", installed_root)
    catalog.Scan()
    return catalog


def test_project_v2_migrates_devices_and_resource_owners() -> None:
    data = ReferenceProject_Create("MigrateV2").Dictionary_Get()
    instances = list(data["components"]["devices"])
    instance_to_plugin = {
        entry["instance_id"]: entry["plugin"] for entry in instances
    }
    data["format_version"] = 2
    data["components"]["devices"] = [entry["plugin"] for entry in instances]
    data["resources"] = {
        (
            f"{instance_to_plugin.get(owner, owner)}:{requirement}"
            if separator
            else key
        ): resource
        for key, resource in data["resources"].items()
        for owner, separator, requirement in (key.partition(":"),)
    }
    data.pop("capability_sources")
    data["generated_glue"].remove("project_capability_routes")

    migrated = ProjectModel_Parse(data)
    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert [instance.instance_id for instance in migrated.device_instances] == [
        "imu0",
        "gnss0",
            "telemetry0",
            "maintenance0",
            "storage0",
            "sensor0",
        "actuator0",
        "actuator1",
        "indicator0",
    ]
    assert migrated.resource_assignments["imu0:data"] == "PLATFORM_UART_1"
    assert migrated.capability_source_overrides == {}
    assert "capability_selections" not in migrated.Dictionary_Get()
    assert "project_capability_routes" in migrated.generated_glue


def test_project_v3_migrates_without_capability_selections() -> None:
    data = ReferenceProject_Create("MigrateV3").Dictionary_Get()
    data["format_version"] = 3

    migrated = ProjectModel_Parse(data)

    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert "capability_selections" not in migrated.Dictionary_Get()


def test_project_v4_removes_legacy_capability_and_build_choices() -> None:
    data = ReferenceProject_Create("MigrateV4").Dictionary_Get()
    data["format_version"] = 4
    data["capability_selections"] = {"imu0": ["magnetometer.field"]}
    data["build"]["configuration"] = "Release"

    migrated = ProjectModel_Parse(data)

    serialized = migrated.Dictionary_Get()
    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert "capability_selections" not in serialized
    assert "configuration" not in serialized["build"]


def test_project_v5_adds_mode_protocol_and_assignment_contracts() -> None:
    data = ReferenceProject_Create("MigrateV5").Dictionary_Get()
    data["format_version"] = 5
    data.pop("mode_parameters")
    data.pop("protocols")
    data["components"]["protocol_bundles"] = [
        "silverstar.protocol.reference_v0"
    ]
    data["hardware"].pop("assignment_fingerprint")
    data["generated_glue"].remove("project_flight_config")

    migrated = ProjectModel_Parse(data)

    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert migrated.mode_parameters["deployment"]["Delay"]["delay"] == 60.0
    assert migrated.ProtocolProfiles_Get()["telemetry"] == "air.m0"
    assert migrated.hardware.assignment_fingerprint == ""
    assert "project_flight_config" in migrated.generated_glue


def test_project_v6_adds_log_decoder_profile_reference() -> None:
    data = ReferenceProject_Create("MigrateV6").Dictionary_Get()
    data["format_version"] = 6
    data.pop("log_decoder_profile")
    data["generated_glue"].remove("project_log_decoder_profile")

    migrated = ProjectModel_Parse(data)

    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert migrated.log_decoder_profile.relative_path == "MigrateV6.ssdecoder"
    assert migrated.log_decoder_profile.package_schema == "1.0"
    assert migrated.log_decoder_profile.container_plugin_id == (
        "silverstar.sslog.container/0.0"
    )
    assert migrated.log_decoder_profile.generation_profile_sha256 == ""
    assert migrated.log_decoder_profile.package_sha256 == ""
    assert "project_log_decoder_profile" in migrated.generated_glue


def test_pre_release_protocol_profile_ids_migrate_to_public_ids() -> None:
    data = ReferenceProject_Create("MigrateProtocolIds").Dictionary_Get()
    data["format_version"] = 7
    data.pop("protocols")
    data["components"]["protocol_bundles"] = [
        "silverstar.protocol.reference_v0"
    ]
    data["protocol_profiles"] = {
        "telemetry": "air.compact.v0",
        "maintenance": "maintenance.v0_0",
        "logging": "sslog0",
    }

    migrated = ProjectModel_Parse(data)

    assert migrated.ProtocolProfiles_Get() == {
        "telemetry": "air.m0",
        "maintenance": "maintenance.serial.0_0",
        "logging": "flight_log.0_0",
    }


def test_reference_capability_resolution_matches_physical_truth(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("CapabilityTruth")
    resolution = CapabilityResolution_Resolve(model, builtin_catalog)
    assert resolution.valid
    assert not resolution.choices
    assert all(route.automatic for route in resolution.routes)
    assert len(
        [instance for instance in model.device_instances if instance.instance_id == "imu0"]
    ) == 1

    jy901b = builtin_catalog.Component_Get("silverstar.device.imu.jy901b")
    raw = {
        capability
        for capability in jy901b.provides
        if CapabilityKind_Get(capability) == CapabilityKind.RAW_DATA
    }
    qualified = set(jy901b.provides) - raw
    assert raw == {
        "device.imu",
        "imu.acceleration",
        "imu.angular_rate",
        "attitude.external",
        "magnetometer.field",
        "magnetometer.physical_unit",
        "barometer.altitude",
    }
    assert qualified == {
        "attitude.external.preflight_fallback_qualified",
        "attitude.external.preflight_alignment_6axis_qualified",
        "attitude.external.preflight_alignment_9axis_qualified",
        "imu.software_alignment_qualified",
        "imu.software_propagation_qualified",
        "imu.landing_stillness_qualified",
        "barometer.landing_window_qualified",
        "barometer.alignment_origin_qualified",
    }
    assert set(jy901b.metadata["unqualified_capabilities"]) == {
        "magnetometer.absolute_vector_qualified",
        "attitude.external.authoritative_6axis_qualified",
        "attitude.external.authoritative_9axis_qualified",
        "imu.landing_impact_qualified",
    }
    assert set(resolution.ConsumedCapabilitiesForInstance_Get("imu0")) == {
        "imu.acceleration",
        "imu.angular_rate",
        "barometer.altitude",
        "imu.software_alignment_qualified",
        "imu.software_propagation_qualified",
        "imu.landing_stillness_qualified",
        "barometer.landing_window_qualified",
    }
    assert {"attitude.external", "magnetometer.field"}.issubset(
        resolution.unused_by_instance["imu0"]
    )
    assert not {"attitude.external", "magnetometer.field"}.intersection(
        resolution.EnabledCapabilitiesForInstance_Get("imu0")
    )
    assert {route.requirement.purpose for route in resolution.routes} == {
        "initialization",
        "runtime",
        "measurement_update",
        "calibration",
        "landing_detection",
    }
    assert not any(
        token in route.requirement.purpose
        for route in resolution.routes
        for token in ("pre_start", "ascent", "recovery")
    )


def test_external_attitude_static_alignment_uses_preflight_qualification(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("HardwareAttitude")
    model.strategies["alignment"] = (
        "silverstar.algorithm.alignment.hardware_quat_6axis_known_yaw"
    )
    resolution = CapabilityResolution_Resolve(model, builtin_catalog)
    routes = [
        route
        for route in resolution.routes
        if route.requirement.capability == "attitude.external"
    ]
    assert resolution.valid
    assert len(routes) == 1
    assert routes[0].provider.instance_id == "imu0"
    assert routes[0].requirement.purpose == "initialization"
    assert not resolution.missing
    assert "attitude.external.preflight_alignment_6axis_qualified" in (
        resolution.EnabledCapabilitiesForInstance_Get("imu0")
    )
    assert "attitude.external.authoritative_6axis_qualified" not in (
        resolution.EnabledCapabilitiesForInstance_Get("imu0")
    )
    assert "phase" not in model.Dictionary_Get()


def test_jy901b_strategy_availability_uses_qualified_capabilities(
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("QualifiedStrategies")
    availability = service.ProjectConfiguration_Reconcile(
        model
    ).strategy_availability

    expected = {
        "silverstar.algorithm.alignment.gravity_known_yaw": (True, ()),
        "silverstar.algorithm.alignment.gravity_mag_triad": (
            False,
            ("magnetometer.absolute_vector_qualified",),
        ),
        "silverstar.algorithm.alignment.hardware_quat_6axis_known_yaw": (
            True,
            (),
        ),
        "silverstar.algorithm.alignment.hardware_quat_9axis": (
            True,
            (),
        ),
        "silverstar.flight_logic.landing.stillness": (True, ()),
        "silverstar.flight_logic.landing.impact_then_stillness": (
            False,
            ("imu.landing_impact_qualified",),
        ),
        "silverstar.flight_logic.landing.baro_imu_window_strategy": (True, ()),
    }
    assert {
        component_id: (availability[component_id].available,
                       availability[component_id].missing_capabilities)
        for component_id in expected
    } == expected

    model.device_instances = [
        instance for instance in model.device_instances if instance.instance_id != "imu0"
    ]
    missing_barometer = service.ProjectConfiguration_Reconcile(
        model
    ).strategy_availability[
        "silverstar.flight_logic.landing.baro_imu_window_strategy"
    ]
    assert not missing_barometer.available
    assert "barometer.altitude" in missing_barometer.missing_capabilities


def test_raw_log_recordability_is_independent_from_algorithm_consumption(
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("RecordableOutputs")
    definitions = {
        definition.name: definition
        for definition in LoggingProfile_Reconcile(model, service.catalog)
    }
    streams = {stream.record: stream for stream in model.logging_streams}
    resolution = CapabilityResolution_Resolve(model, service.catalog)

    assert not any(
        route.requirement.capability == "power.voltage"
        for route in resolution.routes
    )
    assert LogAvailability_Get(
        definitions["POWER"], model, service.catalog
    ).available
    assert streams[definitions["POWER"].record].enabled

    magnetic = LogAvailability_Get(
        definitions["MAG_NATIVE"], model, service.catalog
    )
    assert not magnetic.available
    assert magnetic.reason_code == (
        "logging.unavailable.magnetometer_output_disabled"
    )
    assert Translator("zh_CN").Text_Get(magnetic.reason_code) == (
        "当前所选设备插件未启用可记录的磁场数据输出；"
        "可由启用该输出的兼容磁力计插件提供。"
    )
    recordable, disabled = ProjectRecordableOutputs_Get(model, service.catalog)
    assert "power.voltage" in recordable
    assert "magnetometer.field" not in recordable
    assert disabled["magnetometer.field"] == magnetic.reason_code


def test_recordable_magnetometer_output_can_be_extended_by_another_device_plugin(
    tmp_path: Path, workspace_root: Path
) -> None:
    catalog = _MultiBarometerCatalog_Create(
        workspace_root,
        tmp_path / "installed",
        recordable_magnetometer=True,
    )
    service = FccgService(workspace_root)
    service.catalog = catalog
    model = ReferenceProject_Create("ExtensibleMagnetometerLog", catalog=catalog)
    model.device_instances.append(
        DeviceInstance("magnetometer0", "fixture.device.sensor.bmp280")
    )
    definitions = {
        definition.name: definition
        for definition in ProtocolLogDefinitions_Get(model, catalog)
    }

    magnetic = LogAvailability_Get(
        definitions["MAG_NATIVE"], model, catalog
    )

    assert magnetic.available
    recordable, disabled = ProjectRecordableOutputs_Get(model, catalog)
    assert "magnetometer.field" in recordable
    assert "magnetometer.field" not in disabled

    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.plugin != "silverstar.device.sensor.input_voltage"
    ]
    reconciled = service.ProjectConfiguration_Reconcile(model).model
    assert "voltage_monitor0:input_voltage" not in reconciled.resource_assignments
    definitions = {
        definition.name: definition
        for definition in LoggingProfile_Reconcile(reconciled, service.catalog)
    }
    assert not LogAvailability_Get(
        definitions["POWER"], reconciled, service.catalog
    ).available


def test_landing_selectors_share_one_reference_implementation(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("LandingSourceGraph")
    graph = SourceGraph_Resolve(model, builtin_catalog)

    assert graph.sources.count(
        "FlightLogic/Landing/BarometerImuWindow/Src/flight_landing.c"
    ) == 1
    assert (
        "SYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_BARO_IMU_WINDOW"
        in graph.defines
    )
    assert not any(
        source.startswith(
            (
                "FlightLogic/Landing/Stillness/",
                "FlightLogic/Landing/ImpactThenStillness/",
                "FlightLogic/Landing/BarometerImuWindowStrategy/",
            )
        )
        for source in graph.sources
    )


def test_multiple_providers_default_to_instance_zero_and_save_only_override(
    tmp_path: Path, workspace_root: Path
) -> None:
    catalog = _MultiBarometerCatalog_Create(workspace_root, tmp_path / "installed")
    model = ReferenceProject_Create("AmbiguousProvider")
    model.device_instances.extend(
        (
            DeviceInstance("barometer0", "fixture.device.sensor.bmp280"),
            DeviceInstance("barometer1", "fixture.device.sensor.bmp280"),
        )
    )
    defaulted = CapabilityResolution_Resolve(model, catalog)
    barometer_choice = next(
        choice
        for choice in defaulted.choices
        if choice.capability == "barometer.altitude"
    )
    assert not barometer_choice.requires_selection
    assert barometer_choice.selected_instance_id == "imu0"
    assert {provider.instance_id for provider in barometer_choice.providers} == {
        "imu0",
        "barometer0",
        "barometer1",
    }
    assert all(
        route.provider.instance_id == "imu0"
        for route in defaulted.routes
        if route.requirement.capability == "barometer.altitude"
    )
    assert Project_Validate(model, catalog).valid

    model.capability_source_overrides = {"barometer.altitude": "imu0"}
    reconciled_default = CapabilitySourceOverrides_Reconcile(model, catalog)
    assert reconciled_default.valid
    assert model.capability_source_overrides == {}

    model.capability_source_overrides = {"barometer.altitude": "barometer1"}
    resolved = CapabilityResolution_Resolve(model, catalog)
    assert resolved.valid
    assert all(
        route.provider.instance_id == "barometer1"
        for route in resolved.routes
        if route.requirement.capability == "barometer.altitude"
    )
    assert Project_Validate(model, catalog).valid
    assert model.Dictionary_Get()["capability_sources"] == {
        "barometer.altitude": "barometer1"
    }


def test_current_physical_devices_have_declared_instance_limits_and_are_mcu_neutral(
    builtin_catalog: PluginCatalog,
) -> None:
    for component_id in (
        "silverstar.device.imu.jy901b",
        "silverstar.device.gnss.neo_m9n",
        "silverstar.device.telemetry.sx1281",
    ):
        manifest = builtin_catalog.Component_Get(component_id)
        assert manifest.instance_policy.plugin_max == 4
        assert manifest.instance_policy.class_max == 4
        assert manifest.instance_policy.same_plugin_multiple
        assert manifest.instance_policy.multi_instance_ready
        assert manifest.physical_device is not None
        assert "silverstar.mcu.stm32f407vet6" not in {
            dependency.component_id for dependency in manifest.dependencies
        }

    console = builtin_catalog.Component_Get("silverstar.device.console.uart")
    assert console.instance_policy.plugin_max == 1
    assert console.instance_policy.class_max == 1
    assert not console.instance_policy.same_plugin_multiple
    assert not console.instance_policy.multi_instance_ready
    assert console.physical_device is not None
    assert "silverstar.mcu.stm32f407vet6" not in {
        dependency.component_id for dependency in console.dependencies
    }


def test_context_safe_device_plugin_rejects_fifth_instance(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("BoundedMultiInstance")
    model.device_instances.extend(
        DeviceInstance(f"imu{index}", "silverstar.device.imu.jy901b")
        for index in range(1, 5)
    )
    issue_codes = {issue.code for issue in Project_Validate(model, builtin_catalog).issues}
    assert "device_instance_limit" in issue_codes
    assert "device_class_instance_limit" in issue_codes
    assert "device_same_plugin_multiple" not in issue_codes
    assert "device_multi_instance_not_ready" not in issue_codes


def test_distinct_singleton_plugins_can_share_one_capability_class(
    tmp_path: Path, workspace_root: Path
) -> None:
    catalog = _MixedSingletonDeviceCatalog_Create(
        workspace_root, tmp_path / "mixed-singleton-installed"
    )
    model = ReferenceProject_Create("MixedSingletonProviders")
    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.instance_id != "imu0"
    ]
    model.device_instances[0:0] = [
        DeviceInstance("imu0", "fixture.device.imu.singleton_a"),
        DeviceInstance("imu1", "fixture.device.imu.singleton_b"),
    ]

    issue_codes = {issue.code for issue in Project_Validate(model, catalog).issues}
    assert not issue_codes.intersection(
        {
            "device_instance_limit",
            "device_same_plugin_multiple",
            "device_multi_instance_not_ready",
            "device_class_instance_limit",
            "device_class_multi_instance_not_ready",
        }
    )
    resolution = CapabilityResolution_Resolve(model, catalog)
    acceleration = next(
        choice
        for choice in resolution.choices
        if choice.capability == "imu.acceleration"
    )
    assert acceleration.selected_instance_id == "imu0"
    assert not acceleration.requires_selection


def test_context_ready_mock_devices_support_independent_instances_and_dedup_sources(
    tmp_path: Path, workspace_root: Path
) -> None:
    catalog = _MultiInstanceDeviceCatalog_Create(
        workspace_root, tmp_path / "multi-instance-installed"
    )
    policy = catalog.Component_Get(
        "fixture.device.imu.contextual"
    ).instance_policy
    assert policy.plugin_max == 2
    assert policy.class_max == 2
    assert policy.project_max == 2
    model = ReferenceProject_Create("MultiInstanceModel")
    model.device_instances = [
        DeviceInstance("imu0", "fixture.device.imu.contextual"),
        DeviceInstance("imu1", "fixture.device.imu.contextual"),
        DeviceInstance("gnss0", "fixture.device.gnss.contextual"),
        DeviceInstance("gnss1", "fixture.device.gnss.contextual"),
    ]

    reparsed = ProjectModel_Parse(model.Dictionary_Get())
    assert [instance.instance_id for instance in reparsed.device_instances] == [
        "imu0",
        "imu1",
        "gnss0",
        "gnss1",
    ]
    issue_codes = {issue.code for issue in Project_Validate(model, catalog).issues}
    assert not issue_codes.intersection(
        {
            "device_instance_limit",
            "device_same_plugin_multiple",
            "device_multi_instance_not_ready",
            "device_class_instance_limit",
            "device_class_multi_instance_not_ready",
        }
    )

    requirement_keys = {
        option.key for option in ResourceRequirementOptions_Get(model, catalog)
    }
    assert {"imu0:data", "imu1:data", "gnss0:data", "gnss1:data"}.issubset(
        requirement_keys
    )

    unresolved = CapabilityResolution_Resolve(model, catalog)
    acceleration = next(
        choice
        for choice in unresolved.choices
        if choice.capability == "imu.acceleration"
    )
    position = next(
        choice
        for choice in unresolved.choices
        if choice.capability == "gnss.position"
    )
    assert {provider.instance_id for provider in acceleration.providers} == {
        "imu0",
        "imu1",
    }
    assert {provider.instance_id for provider in position.providers} == {
        "gnss0",
        "gnss1",
    }
    assert acceleration.selected_instance_id == "imu0"
    assert position.selected_instance_id == "gnss0"
    assert not acceleration.requires_selection
    assert not position.requires_selection

    model.capability_source_overrides.update(
        {
            "imu.acceleration": "imu1",
            "imu.angular_rate": "imu1",
            "gnss.position": "gnss0",
            "gnss.velocity": "gnss0",
        }
    )
    resolved = CapabilityResolution_Resolve(model, catalog)
    assert all(
        route.provider.instance_id == "imu1"
        for route in resolved.routes
        if route.requirement.capability
        in {"imu.acceleration", "imu.angular_rate"}
    )
    assert all(
        route.provider.instance_id == "gnss0"
        for route in resolved.routes
        if route.requirement.capability in {"gnss.position", "gnss.velocity"}
    )

    graph = SourceGraph_Resolve(model, catalog)
    assert graph.sources.count("Fixture/imu/contextual_device.c") == 1
    assert graph.sources.count("Fixture/gnss/contextual_device.c") == 1
    assert isinstance(model.strategies["estimator"], str)

    facade_header = _DeviceInstancesHeader_Render(model, catalog)
    facade_source = _DeviceInstancesSource_Render(model, catalog)
    metadata_source = _MetadataSource_Render(model, catalog)
    assert "PROJECT_DESCRIPTOR_ID_IMU_0" in facade_header
    assert "PROJECT_DESCRIPTOR_ID_IMU_1" in facade_header
    assert "PROJECT_DESCRIPTOR_ID_GNSS_0" in facade_header
    assert "PROJECT_DESCRIPTOR_ID_GNSS_1" in facade_header
    assert "PROJECT_PHYSICAL_DEVICE_ID_FIXTURE_IMU_1" in facade_header
    assert "PROJECT_PHYSICAL_DEVICE_ID_FIXTURE_GNSS_1" in facade_header
    assert "case 0U: return FixtureImu_InfoGet(0U, info);" in facade_source
    assert "case 1U: return FixtureImu_InfoGet(1U, info);" in facade_source
    assert "case 0U: return FixtureGnss_LatestSampleGet(0U, sample);" in facade_source
    assert "case 1U: return FixtureGnss_LatestSampleGet(1U, sample);" in facade_source
    assert "PROJECT_DESCRIPTOR_ID_IMU_1" in metadata_source
    assert "PROJECT_PHYSICAL_DEVICE_ID_FIXTURE_IMU_1" in metadata_source
    assert "(*)" not in facade_source
    assert "malloc" not in facade_source


def test_physical_names_and_protocol_versions_are_structured(
    builtin_catalog: PluginCatalog,
) -> None:
    telemetry = builtin_catalog.Component_Get(
        "silverstar.device.telemetry.sx1281"
    )
    assert telemetry.DisplayName_Get("zh_CN") == "E28-2G4M12SX（SX1281）"
    assert telemetry.physical_device is not None
    assert telemetry.physical_device.model == "E28-2G4M12SX"
    assert telemetry.physical_device.chipset == "SX1281"
    assert telemetry.physical_device.driver == "SX1281 Driver"

    console = builtin_catalog.Component_Get("silverstar.device.console.uart")
    assert console.DisplayName_Get("zh_CN") == "串口维护协议 0.0"
    for component_id, category in (
        ("silverstar.protocol.telemetry.air_m0", "telemetry"),
        ("silverstar.protocol.maintenance.serial_0_0", "maintenance"),
        ("silverstar.protocol.logging.sslog_0_0", "logging"),
    ):
        protocol = builtin_catalog.Component_Get(component_id)
        assert protocol.protocol is not None
        assert protocol.protocol.category == category
        assert protocol.protocol.maintenance_protocol_version == "0.0"
        assert protocol.protocol.firmware_version == "0.1.0"
        assert protocol.protocol.documentation_version == "0.1.0"


def test_save_as_copies_full_source_and_excludes_intermediates(
    tmp_path: Path, workspace_root: Path, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    source = tmp_path / "SourceProject"
    destination = tmp_path / "CopiedProject"
    model = service.ReferenceProject_Create("SourceProject")
    plan = service.GenerationPlan_Create(model, source)
    service.GenerationPlan_Apply(model, plan)

    component_source = (
        source / "Devices" / "IMU" / "JY901B" / "Src" / "jy901b_device.c"
    )
    marker = "\n/* MANUAL SOURCE MUST SURVIVE SAVE AS */\n"
    component_source.write_text(
        component_source.read_text(encoding="utf-8") + marker,
        encoding="utf-8",
        newline="\n",
    )
    build_artifact = source / "build" / "Debug" / "firmware.o"
    build_artifact.parent.mkdir(parents=True)
    build_artifact.write_bytes(b"intermediate")
    cache_file = source / ".fccg" / "cache" / "scan.bin"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"cache")
    destination.mkdir()

    actual_replace = os.replace
    transient_locks = 0

    def replace_with_transient_lock(src, dst):
        nonlocal transient_locks
        if Path(dst) == destination / "System" and transient_locks == 0:
            transient_locks += 1
            raise PermissionError(5, "transient directory lock", str(src))
        return actual_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace_with_transient_lock)
    copied = service.Project_SaveAs(model, source, destination)
    assert transient_locks == 1
    copied_source = (
        copied / "Devices" / "IMU" / "JY901B" / "Src" / "jy901b_device.c"
    )
    assert copied_source.read_text(encoding="utf-8").endswith(marker)
    assert not (copied / "build").exists()
    assert not (copied / ".fccg" / "cache").exists()
    assert (copied / ".fccg" / "ownership.json").is_file()
    assert ProjectModel_Load(copied / "SilverStar.ssproject").identity.name == (
        "SourceProject"
    )


def test_gui_save_as_action_switches_to_complete_project_copy(
    tmp_path: Path, workspace_root: Path, qapp, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    source = tmp_path / "GuiSource"
    destination = tmp_path / "GuiCopy"
    destination.mkdir()
    model = service.ReferenceProject_Create("GuiSource")
    service.GenerationPlan_Apply(
        model, service.GenerationPlan_Create(model, source)
    )
    window = MainWindow(
        SettingsStore(tmp_path / "gui-save-as.ini"),
        service=service,
        language="en_US",
    )
    errors = []
    monkeypatch.setattr(window, "_Error_Show", errors.append)
    try:
        window._Project_Open(source)
        assert not errors
        monkeypatch.setattr(
            QFileDialog,
            "exec",
            lambda dialog: (dialog.selectFile(str(destination)), QFileDialog.DialogCode.Accepted)[1],
        )
        window._Project_SaveAs()
        deadline = time.monotonic() + 30.0
        while window._active_worker is not None and time.monotonic() < deadline:
            qapp.processEvents()
            # QTest.qWait() keeps the Python GIL for most of its wait on
            # Windows/Python 3.14, starving the Python-heavy save worker.
            time.sleep(0.01)
        assert window._active_worker is None
        assert not errors, errors
        assert window._project_root == destination.resolve()
        assert (destination / "SilverStar.ssproject").is_file()
        assert (destination / "Devices" / "IMU" / "JY901B").is_dir()
    finally:
        window.close()
        qapp.processEvents()


def test_required_logging_checkbox_is_active_locked_and_model_forced(
    tmp_path: Path, qapp
) -> None:
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"), language="zh_CN")
    try:
        table = window.flight_configuration_page.logging_table
        required_row = next(
            row
            for row in range(table.rowCount())
            if table.cellWidget(row, 0)
            .findChild(StandardCheckBox)
            .property("streamId")
            == "FLIGHT_LOG_RECORD_EVENT"
        )
        check = table.cellWidget(required_row, 0).findChild(StandardCheckBox)
        assert isinstance(check, LockedCheckBox)
        assert check.isEnabled() and check.isChecked()
        assert check.toolTip() == "系统必须日志"
        check.click()
        assert check.isChecked()
        stream = window.flight_configuration_page.Streams_Get()[required_row]
        assert stream.required and stream.enabled
        window._model.logging_streams = [
            replace(item, enabled=False)
            if item.record == "FLIGHT_LOG_RECORD_EVENT"
            else item
            for item in window._model.logging_streams
        ]
        LoggingProfile_Reconcile(window._model, window._service.catalog)
        assert next(
            item
            for item in window._model.logging_streams
            if item.record == "FLIGHT_LOG_RECORD_EVENT"
        ).enabled
    finally:
        window.close()
        qapp.processEvents()


def test_eide_ui_changes_are_preserved_and_build_changes_are_reported(
    tmp_path: Path, workspace_root: Path
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "EideProject"
    model = service.ReferenceProject_Create("EideProject")
    service.GenerationPlan_Apply(
        model, service.GenerationPlan_Create(model, project_root)
    )
    eide = project_root / ".eide" / "eide.yml"
    document = yaml.safe_load(eide.read_text(encoding="utf-8"))
    document["currentTarget"] = "Debug"
    document["targets"]["Release"]["uiState"] = {"expanded": True}
    eide.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
    plan = service.GenerationPlan_Create(model, project_root)
    operation = next(
        operation for operation in plan.operations if operation.target == ".eide/eide.yml"
    )
    assert operation.operation == "UNCHANGED"
    assert not operation.dangerous

    document = yaml.safe_load(eide.read_text(encoding="utf-8"))
    document["targets"]["Release"]["cppPreprocessAttrs"]["incList"].append(
        "Manual/Include"
    )
    eide.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    plan = service.GenerationPlan_Create(model, project_root)
    operation = next(
        operation for operation in plan.operations if operation.target == ".eide/eide.yml"
    )
    assert operation.operation == "MODIFY"
    assert operation.dangerous
    assert "targets.Release.includes" in operation.detail
    service.GenerationPlan_Apply(model, plan, confirm_dangerous=True)
    applied = yaml.safe_load(eide.read_text(encoding="utf-8"))
    assert "Manual/Include" not in applied["targets"]["Release"][
        "cppPreprocessAttrs"
    ]["incList"]
    assert applied["currentTarget"] == "Debug"
    assert applied["targets"]["Release"]["uiState"] == {"expanded": True}
    merged_text = eide.read_text(encoding="utf-8")
    assert "\nsrcDirs:\n  - APP/Src\n" in merged_text
    assert "\n        - APP/Inc\n" in merged_text
    assert (
        "C_FLAGS: -include Targets/SilverStar_F407/Inc/platform_memory_target.h "
        "-include Generated/Inc/project_flight_config.h"
    ) in merged_text
