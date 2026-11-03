"""Shared in-memory hardware edit actions for the main view and private drafts.

These actions never save, import, generate or construct another window. The host
provides reconciliation, display and error presentation at its own boundary.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from silverstar_fccg.ui.main_window import _ProjectDisplayState
from copy import deepcopy
from dataclasses import replace
from PySide6.QtCore import QTimer
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.core.view_models import ComponentType
from silverstar_fccg.generator.hardware_preparation import HardwareAssignmentFingerprint_Get
from silverstar_fccg.project.air_link import GroundTargetIssues_Get, RadioCandidateIssues_Get
from silverstar_fccg.project.configuration import ModeOptionAvailabilities_Get
from silverstar_fccg.project.feature_tiers import FeatureTier_Apply
from silverstar_fccg.project.radio_variants import RADIO_PLUGIN, FlightRadioConfiguration_Get, FlightRadioConfiguration_Apply, RadioManifest_Resolve
from silverstar_fccg.project.model import RAW_IMU_MOUNT_PLUGINS, DeviceInstance, GroundRadioConfigurations_Get, HardwareConfiguration, HardwareResource, ProjectModel
from silverstar_fccg.project.ground_radios import GroundRadiosConfiguration_Apply
from silverstar_fccg.project.protocols import ProtocolProfileAvailabilities_Get
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.ground_activity import GroundActivityLedEnabled_Get


class HardwareEditingActions:
    def _BoardPage_Refresh(self, display: _ProjectDisplayState) -> None:
        model = display.model
        custom_selected = model.hardware.mode == "custom"
        self.board_hardware_page.Boards_Set(
            display.boards,
            model.board,
            custom_available=bool(display.hardware_provider),
            custom_selected=custom_selected,
            custom_ready=custom_selected and bool(model.hardware.snapshot_id),
            prepared=(
                self._project_root is not None
                and self._service.Project_HardwarePrepared_Is(
                    model, self._project_root
                )
            ),
            hardware_mode=model.hardware.mode,
            assignment_confirmed=bool(
                model.hardware.assignment_fingerprint
            ),
        )
        self.board_hardware_page.Platform_Set(display.platform_match)
        self.board_hardware_page.Resources_Set(
            display.resources,
            display.resources_valid,
            hardware_selected=model.hardware.mode != "unselected",
        )
        self.board_hardware_page.I2cPullupEvidence_Set(
            display.i2c_pullup_evidence
        )

    def _OptionalResource_Change(self, name: str, enabled: bool) -> None:
        if name not in ("magnetometer_enabled", "maintenance_log_export_enabled"):
            return
        def mutate(model: ProjectModel) -> None:
            model.build = replace(model.build, **{name: enabled})
        self._ProjectConfiguration_Change(mutate)

    def _FeatureTier_Change(self, tier: str) -> None:
        notes = []
        def mutate(model: ProjectModel) -> None:
            notes.extend(FeatureTier_Apply(model, tier, self._service.catalog))
            choice = self._logging_transport_choice
            if (tier == "compact" and model.protocols.get("logging") is None and choice is not None
                    and self._selection_restore_project == (self._project_root, self._model.identity.name)):
                availability = ProtocolProfileAvailabilities_Get(model, self._service.catalog).get(
                    ("logging", choice.component, choice.profile))
                if availability is not None and availability.available:
                    model.protocols["logging"] = deepcopy(choice)
                    if self._logging_transport_streams is not None:
                        model.logging_streams = deepcopy(self._logging_transport_streams)
                    notes.append("logging:restored_transport_choice")
        result = self._ProjectConfiguration_Change(mutate)
        if result is not None:
            text = self._translator.Text_Get("feature_tier.changed",
                tier=self._translator.Text_Get("feature_tier." + tier))
            if notes:
                text += " " + self._translator.Text_Get("feature_tier.saved_choices") + " " + "; ".join(notes)
            self.devices_page.FeatureTier_NoticeSet(text)
            self.status_label.setText(text)

    def _DeviceInstance_Change(self, instance_id: str, component_id: str) -> None:
        if self._displaying_model:
            return
        def change(candidate: ProjectModel) -> None:
            existing = candidate.DeviceInstance_Get(instance_id)
            if component_id:
                replacement = DeviceInstance(instance_id, component_id)
                if (existing is not None and
                        self._service.Plugin_Get(existing.plugin).component_class ==
                        self._service.Plugin_Get(component_id).component_class):
                    # Model/interface replacement at the same physical instance
                    # does not silently discard its measured structural position.
                    replacement = replace(replacement, position_body_m=existing.position_body_m)
                if existing is None:
                    candidate.device_instances.append(replacement)
                else:
                    candidate.device_instances = [
                        replacement if item.instance_id == instance_id else item
                        for item in candidate.device_instances
                    ]
            else:
                candidate.device_instances = [
                    item
                    for item in candidate.device_instances
                    if item.instance_id != instance_id
                ]
                if candidate.air_link.flight_radio_instance == instance_id:
                    remaining = next((item.instance_id for item in candidate.device_instances
                                      if self._service.Plugin_Get(item.plugin).component_class == "telemetry"),
                                     "telemetry0")
                    candidate.air_link = replace(candidate.air_link, flight_radio_instance=remaining)

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )

    def _DeviceVariant_Change(
        self, instance_id: str, interface: str, profile: str
    ) -> None:
        if self._displaying_model:
            return

        def change(candidate: ProjectModel) -> None:
            candidate.device_instances = [
                replace(instance, interface=interface, profile=profile)
                if instance.instance_id == instance_id else instance
                for instance in candidate.device_instances
            ]
            candidate.resource_assignments = {
                key: value for key, value in candidate.resource_assignments.items()
                if not key.startswith(instance_id + ":")
            }

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )

    def _Jy901bOrientation_Change(self, instance_id: str, orientation: str) -> None:
        if self._displaying_model or orientation not in ("horizontal", "vertical"):
            return

        def change(candidate: ProjectModel) -> None:
            candidate.device_instances = [
                replace(instance, installation_orientation=orientation)
                if instance.instance_id == instance_id and
                instance.plugin == "silverstar.device.imu.jy901b" else instance
                for instance in candidate.device_instances
            ]

        self._ProjectConfiguration_Change(change)

    def _RawImuMount_Change(self, instance_id: str, nose_axis: str) -> None:
        from silverstar_fccg.project.model import RAW_IMU_NOSE_AXIS_MAPS
        if self._displaying_model or nose_axis not in RAW_IMU_NOSE_AXIS_MAPS:
            return

        def change(candidate: ProjectModel) -> None:
            from silverstar_fccg.project.model import RawImuAxisMap_Get
            existing = candidate.DeviceInstance_Get(instance_id)
            x_axis = existing.mount_x_axis if existing is not None else ''
            try:
                RawImuAxisMap_Get(nose_axis, x_axis)
            except ValueError:
                x_axis = ''  # The user changed the nose direction; show the legacy mapping explicitly.
            candidate.device_instances = [
                replace(instance, mount_nose_axis=nose_axis, mount_x_axis=x_axis)
                if instance.instance_id == instance_id and
                instance.plugin in RAW_IMU_MOUNT_PLUGINS else instance
                for instance in candidate.device_instances
            ]

        self._ProjectConfiguration_Change(change)

    def _RawImuXAxis_Change(self, instance_id: str, x_axis: str) -> None:
        def change(candidate):
            from silverstar_fccg.project.model import RawImuAxisMap_Get
            existing = candidate.DeviceInstance_Get(instance_id)
            if existing is None or existing.plugin not in RAW_IMU_MOUNT_PLUGINS:
                raise ValueError('Raw IMU instance is not configured')
            RawImuAxisMap_Get(existing.mount_nose_axis, x_axis)
            candidate.device_instances = [replace(item, mount_x_axis=x_axis)
                if item.instance_id == instance_id else item for item in candidate.device_instances]
        QTimer.singleShot(0, self, lambda: self._ProjectConfiguration_Change(change))

    def _InstallationReference_Adopt(self):
        from silverstar_fccg.project.sensor_installation import SensorInstallationConfiguration
        QTimer.singleShot(0, self, lambda: self._ProjectConfiguration_Change(
            lambda candidate: setattr(candidate, 'sensor_installation', SensorInstallationConfiguration(schema_version=2))))

    def _SensorPosition_Change(self, instance_id: str, position: tuple | None) -> None:
        from silverstar_fccg.project.sensor_installation import (
            SensorInstallationConfiguration, SensorPosition,
        )
        if self._displaying_model:
            return
        def change(candidate: ProjectModel) -> None:
            existing = candidate.DeviceInstance_Get(instance_id)
            if (existing is None or self._service.Plugin_Get(existing.plugin).component_class
                    not in ("imu", "gnss")):
                raise ValueError("Installation position requires an IMU/GNSS instance")
            candidate.sensor_installation = (candidate.sensor_installation or
                                              SensorInstallationConfiguration())
            candidate.device_instances = [
                replace(item, position_body_m=SensorPosition(*position) if position is not None else None)
                if item.instance_id == instance_id else item for item in candidate.device_instances
            ]
        self._ProjectConfiguration_Change(change)

    def _FlightRadioSelection_Change(self, identity: str, plugin: str, module: str) -> None:
        if not plugin or plugin not in {RADIO_PLUGIN, "silverstar.device.telemetry.sx1278"}:
            self._DeviceInstance_Change(identity, plugin)
            return
        manifest = self._service.catalog.Component_Get(plugin)
        powers = tuple(manifest.radio.modules.get(module, {}).get("supported_tx_powers_dbm", ()))
        if not powers:
            self._Error_Show("Selected radio module has no supported output power")
            return
        def change(candidate):
            existing = candidate.DeviceInstance_Get(identity)
            if existing is None:
                candidate.device_instances.append(DeviceInstance(identity, plugin))
            elif existing.plugin != plugin:
                candidate.device_instances = [
                    DeviceInstance(identity, plugin) if item.instance_id == identity else item
                    for item in candidate.device_instances]
                candidate.resource_assignments = {key: value
                    for key, value in candidate.resource_assignments.items()
                    if not key.startswith(identity + ":")}
            edited = FlightRadioConfiguration_Apply(candidate, identity, module, powers[0])
            candidate.device_instances = edited.device_instances
            candidate.resource_assignments = edited.resource_assignments
            if candidate.DeviceInstance_Get(candidate.air_link.flight_radio_instance) is None:
                candidate.air_link = replace(candidate.air_link, flight_radio_instance=identity)
        self._ProjectConfiguration_Change(change, logging_availability_changed=True)

    def _FlightRadioPower_Change(self, identity: str, value: int) -> None:
        def change(candidate):
            instance = candidate.DeviceInstance_Get(identity)
            if instance is None:
                raise ValueError("Flight radio instance is unavailable")
            module, _power = FlightRadioConfiguration_Get(candidate, instance)
            edited = FlightRadioConfiguration_Apply(candidate, identity, module, value)
            candidate.device_instances = edited.device_instances
            candidate.resource_assignments = edited.resource_assignments
        self._ProjectConfiguration_Change(change)

    def _DeviceInstance_Add(self, component_class: str) -> None:
        candidates = sorted(
            (
                component
                for component in self._component_views
                if component.component_type == ComponentType.DEVICE
                and component.component_class == component_class
                and not component.options.get("internal", False)
            ),
            key=lambda item: item.name,
        )
        if not candidates:
            return
        selected = [
            instance
            for instance in self._model.device_instances
            if self._service.Plugin_Get(instance.plugin).component_class
            == component_class
        ]
        class_max = max(
            (component.class_max or component.project_max for component in candidates),
            default=1,
        )
        from silverstar_fccg.project.feature_tiers import FeatureTier_DeviceClassLimitGet
        class_max = FeatureTier_DeviceClassLimitGet(self._model.build.feature_tier, component_class,
            str(candidates[0].options.get("device_category", "")), class_max,
            self._model.build.magnetometer_enabled)
        if len(selected) >= class_max:
            return
        plugin_counts: dict[str, int] = {}
        for instance in selected:
            plugin_counts[instance.plugin] = plugin_counts.get(instance.plugin, 0) + 1
        available_candidates = [
            component
            for component in candidates
            if plugin_counts.get(component.component_id, 0)
            < (component.plugin_max or component.project_max)
        ]
        if not available_candidates:
            return
        selected_plugins = {instance.plugin for instance in selected}
        preferred = next(
            (component for component in available_candidates
             if component.component_id in selected_plugins),
            available_candidates[0],
        )
        instance_id = self._DeviceInstanceId_Next(component_class)
        template = None
        if component_class == "telemetry":
            template = next((item for item in selected
                             if item.instance_id == self._model.air_link.flight_radio_instance),
                            selected[0] if selected else None)
        self._ProjectConfiguration_Change(
            lambda candidate: candidate.device_instances.append(
                replace(template, instance_id=instance_id) if template is not None
                and template.plugin == preferred.component_id else DeviceInstance(instance_id, preferred.component_id)
            ),
            logging_availability_changed=True,
        )

    def _OtherDevice_Toggle(self, component_id: str, selected: bool) -> None:
        manifest = self._service.Plugin_Get(component_id)
        def change(candidate: ProjectModel) -> None:
            if selected:
                if any(
                    instance.plugin == component_id
                    for instance in candidate.device_instances
                ):
                    return
                previous_availability = ModeOptionAvailabilities_Get(
                    candidate, self._service.catalog
                )
                preferred_instance_id = str(
                    manifest.metadata.get("default_instance_id", "")
                )
                used_instance_ids = {
                    instance.instance_id
                    for instance in candidate.device_instances
                }
                instance_id = (
                    preferred_instance_id
                    if preferred_instance_id
                    and preferred_instance_id not in used_instance_ids
                    else self._DeviceInstanceId_Next(
                        manifest.component_class or "sensor",
                        model=candidate,
                    )
                )
                candidate.device_instances.append(
                    DeviceInstance(instance_id, component_id)
                )
                availability = ModeOptionAvailabilities_Get(
                    candidate, self._service.catalog
                )
                for base_component_id in candidate.base_components:
                    selection = self._service.Plugin_Get(
                        base_component_id
                    ).selection
                    if (
                        selection is None
                        or selection.kind.value != "mode"
                        or candidate.modes.get(selection.slot)
                    ):
                        continue
                    restored = [
                        option
                        for option in selection.default
                        if (
                            availability.get((selection.slot, option))
                            is not None
                            and availability[(selection.slot, option)].available
                            and not previous_availability.get(
                                (selection.slot, option),
                                availability[(selection.slot, option)],
                            ).available
                        )
                    ]
                    if restored:
                        candidate.modes[selection.slot] = restored
            else:
                candidate.device_instances = [
                    instance
                    for instance in candidate.device_instances
                    if instance.plugin != component_id
                ]

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )

    def _DeviceInstanceId_Next(
        self, component_class: str, *, model: ProjectModel | None = None
    ) -> str:
        prefix = "maintenance" if component_class == "console" else component_class
        prefix = prefix.replace(".", "_").replace("-", "_") or "device"
        selected_model = model or self._model
        used = {instance.instance_id for instance in selected_model.device_instances}
        for index in range(64):
            candidate = f"{prefix}{index}"
            if candidate not in used:
                return candidate
        raise FccgError(
            "error.device_instance_limit",
            {"device": component_class},
            f"No free instance id for device class {component_class}",
        )

    def _BoardSelection_Change(self, board_id: str) -> None:
        board = self._service.Plugin_Get(board_id)
        def change(candidate: ProjectModel) -> None:
            candidate.board = board_id
            candidate.hardware = HardwareConfiguration(
                mode="board_plugin",
                source_kind=(
                    board.board.source_kind if board.board else "third_party"
                ),
            )
            candidate.resource_assignments = {}

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )

    def _CustomHardware_Select(self) -> None:
        provider = self._service.HardwareProviderForMcu_Get(self._model.mcu)
        if not provider:
            self._Error_Show(self._translator.Text_Get("board.no_provider"))
            return
        def change(candidate: ProjectModel) -> None:
            candidate.board = ""
            candidate.hardware = HardwareConfiguration(
                mode="custom",
                source_kind="manual_import",
                provider=provider,
            )
            candidate.resource_assignments = {}

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )

    def _TargetPages_Refresh(self, model: ProjectModel) -> None:
        radios = []
        module_availability = {}
        radio_contracts = tuple(
            manifest.radio for manifest in self._service.catalog.Type_Get("device")
            if manifest.radio is not None
        )
        self.air_link_page.RadioOptions_Set(radio_contracts)
        for candidate in self._service.catalog.Type_Get("device"):
            if candidate.radio is None:
                continue
            for module_id in candidate.radio.modules:
                module_issues = RadioCandidateIssues_Get(
                    model.air_link, candidate.radio, module_id, "Ground")
                if model.air_link.packet_mtu > 61:
                    module_issues = (*module_issues,
                                     "AIR_LINK_MTU_TOO_SMALL: Ground GSP bridge permits 61 bytes")
                module_availability[(candidate.component_id, module_id)] = (
                    not module_issues, "; ".join(
                        f"{issue.code}: {issue.message}" if hasattr(issue, "code") else issue
                        for issue in module_issues))
            selected_module = (
                model.ground_target.module_variant
                if candidate.component_id == model.ground_target.radio_plugin else ""
            )
            issues = RadioCandidateIssues_Get(
                model.air_link, candidate.radio, selected_module, "Ground",
            )
            if model.air_link.packet_mtu > 61:
                issues = (*issues, "AIR_LINK_MTU_TOO_SMALL: Ground GSP bridge permits 61 bytes")
            technology = "LoRa" if candidate.radio.technology == "lora" else "Packet Radio / Other"
            radios.append((
                f"{technology} · {candidate.DisplayName_Get(self._translator.language)}",
                candidate.component_id,
                not issues,
                "; ".join(
                    f"{issue.code}: {issue.message}" if hasattr(issue, "code") else issue
                    for issue in issues
                ),
            ))
        boards = tuple(
            (manifest.DisplayName_Get(self._translator.language), manifest.component_id)
            for manifest in self._service.catalog.Type_Get("board")
            if manifest.board is not None
            and (manifest.metadata.get("target_role") == "ground_station" or manifest.component_class == "ground_station_board")
            and any(identity in {item.component_id for item in self._service.catalog.Type_Get("mcu")}
                    for identity in manifest.board.compatible_mcus)
            and (manifest.board.verified or manifest.source == "installed")
        )
        selected = model.ground_target.radio_plugin
        try:
            manifest = self._service.catalog.Component_Get(selected) if selected else None
        except ValueError:
            manifest = None
        if manifest is not None:
            try:
                manifest = RadioManifest_Resolve(manifest, DeviceInstance(
                    model.ground_target.active_radio_instance, selected,
                    module_variant=model.ground_target.module_variant,
                    tx_power_dbm=model.ground_target.tx_power_dbm))
            except ValueError:
                pass
        requirements = {
            "module_availability": module_availability,
            "radio_contracts": {candidate.component_id: candidate.radio
                                for candidate in self._service.catalog.Type_Get("device")
                                if candidate.radio is not None},
            "radio_chipsets": {
                candidate.component_id: candidate.physical_device.chipset
                for candidate in self._service.catalog.Type_Get("device")
                if candidate.radio is not None and candidate.physical_device is not None
            },
            "fixed_resources": {
                role.key.removeprefix("telemetry:"): role.default
                for board in self._service.catalog.Type_Get("board")
                if board.component_id == model.ground_target.board
                and model.ground_target.hardware.mode == "board_plugin"
                for role in board.resource_roles
                if role.fixed and role.key.startswith("telemetry:")
            },
            "modules": tuple(
                (str(item.get("display_name", item.get("model", identity))), identity)
                for identity, item in (manifest.radio.modules.items()
                                       if manifest is not None and manifest.radio is not None else ())
            ),
            "resources": tuple(
                (requirement.name, requirement.kind)
                for requirement in (manifest.resource_requirements if manifest is not None else ())
                if requirement.required
            ),
        }
        if model.ground_target.radio_instances:
            resources = []
            for radio in GroundRadioConfigurations_Get(model.ground_target):
                try:
                    instance_manifest = self._service.catalog.Component_Get(radio.plugin)
                    instance_manifest = RadioManifest_Resolve(instance_manifest, DeviceInstance(
                        radio.instance_id, radio.plugin, module_variant=radio.module_variant,
                        tx_power_dbm=radio.tx_power_dbm))
                except ValueError:
                    continue
                resources.extend((f"{radio.instance_id}:{requirement.name}", requirement.kind)
                                 for requirement in instance_manifest.resource_requirements if requirement.required)
            requirements["resources"] = tuple(resources)
            requirements["fixed_resources"] = {"radio0:" + key: value
                                               for key, value in requirements["fixed_resources"].items()}
        flight_instance = model.DeviceInstance_Get(model.air_link.flight_radio_instance)
        try:
            flight_manifest = (
                self._service.catalog.Component_Get(flight_instance.plugin)
                if flight_instance is not None else None
            )
        except ValueError:
            flight_manifest = None
        flight_module_id, flight_power = (FlightRadioConfiguration_Get(model, flight_instance)
                                        if flight_instance is not None and flight_instance.plugin in {RADIO_PLUGIN, "silverstar.device.telemetry.sx1278"}
                                        else ("", model.flight_tx_power_dbm))
        flight_module = (flight_manifest.radio.modules.get(flight_module_id)
                         if flight_manifest is not None and flight_manifest.radio is not None else None)
        ground_module = (
            manifest.radio.modules.get(model.ground_target.module_variant)
            if manifest is not None and manifest.radio is not None else None
        )
        active_modules = [item for item in (
            flight_module,
            ground_module,
        ) if item is not None]
        frequency_range = None
        if active_modules and flight_module is not None:
            low = max(item["validated_frequency_min_hz"] for item in active_modules)
            high = min(item["validated_frequency_max_hz"] for item in active_modules)
            if low <= high:
                frequency_range = (low, high)
        self.air_link_page.RadioConstraints_Set(
            frequency_range,
            tuple(flight_module["supported_tx_powers_dbm"]) if flight_module else (),
            tuple(ground_module["supported_tx_powers_dbm"]) if ground_module else (),
            ground_module is not None,
        )
        from silverstar_fccg.project.radio_transaction import RadioTransaction_IssuesGet
        self.air_link_page.Configuration_Set(
            model.air_link, RadioTransaction_IssuesGet(model, self._service.catalog)
        )
        self.air_link_page.EndpointPowers_Set(
            flight_power, model.ground_target.tx_power_dbm,
            ground_module is not None,
        )
        self.ground_target_page.Configuration_Set(
            model.ground_target, boards, tuple(radios), requirements,
            GroundTargetIssues_Get(model, self._service.catalog),
        )
        ground = model.ground_target
        platform = self._service.PlatformMatchView_Get(
            replace(model, mcu=ground.mcu, board=ground.board,
                    hardware=ground.hardware), self._translator.language)
        if ground.hardware.inventory.get("timebase", {}).get("kind") == "systick":
            platform = replace(platform, timebase_status="SysTick / HAL_IncTick")
        self.ground_target_page.Platform_Set(platform)

    def _GroundRadios_Change(self, radios, active: str) -> None:
        def change(candidate: ProjectModel) -> None:
            ground = candidate.ground_target
            if radios:
                updated = GroundRadiosConfiguration_Apply(ground, radios, active)
                previous = {radio.instance_id: radio for radio in GroundRadioConfigurations_Get(ground)}
                obsolete = set()
                for radio in radios:
                    old = previous.get(radio.instance_id)
                    if old is None or (old.plugin, old.module_variant) == (radio.plugin, radio.module_variant):
                        continue
                    manifest = self._service.catalog.Component_Get(radio.plugin)
                    resolved = RadioManifest_Resolve(manifest, DeviceInstance(
                        radio.instance_id, radio.plugin, module_variant=radio.module_variant,
                        tx_power_dbm=radio.tx_power_dbm))
                    names = {requirement.name for requirement in resolved.resource_requirements}
                    obsolete.update(radio.instance_id + ":" + requirement.name
                                    for requirement in manifest.resource_requirements
                                    if requirement.name not in names)
                candidate.ground_target = replace(updated, resource_assignments={
                    key: value for key, value in updated.resource_assignments.items() if key not in obsolete})
                return
            removed = {radio.instance_id for radio in GroundRadioConfigurations_Get(ground)}
            # Clearing the final selection uses the existing empty legacy state.
            # Hardware, AIR settings, PC and unrelated assignments remain owned.
            candidate.ground_target = replace(ground, radio_instances=(),
                active_radio_instance="radio0", radio_plugin="", module_variant="",
                resource_assignments={key: value for key, value in ground.resource_assignments.items()
                                      if key.split(":", 1)[0] not in removed})
        self._ProjectConfiguration_Change(change)

    def _GroundActivityLed_Toggle(self, enabled: bool) -> None:
        def change(candidate: ProjectModel) -> None:
            ground = candidate.ground_target
            if enabled:
                if ground.tx_led_resource or ground.rx_led_resource:
                    candidate.ground_target = replace(ground, activity_led_enabled=True)
                    return
                binding = self.ground_target_page.ActivityLedCandidate_Get(ground)
                if binding is None:
                    candidate.ground_target = replace(ground, activity_led_enabled=True)
                    return
                resource, active_high = binding
                candidate.ground_target = replace(
                    ground, tx_led_resource=resource, rx_led_resource=resource,
                    tx_led_active_high=active_high, rx_led_active_high=active_high,
                    activity_led_enabled=True,
                )
            else:
                candidate.ground_target = replace(ground, activity_led_enabled=False)
        self._ProjectConfiguration_Change(change)

    def _GroundTarget_Change(self, field: str, value: object) -> None:
        if field == "enabled" and value is False:
            # Current GUI offers both targets; only generation scope is optional.
            # Do not enable stored/legacy models during a display refresh.
            self._Project_Refresh()
            return
        if field == "board":
            self._GroundBoard_Change(str(value or ""))
            return
        def change(candidate: ProjectModel) -> None:
            ground = candidate.ground_target
            updates = {field: value}
            if field == "radio_plugin" and value != ground.radio_plugin:
                radio = self._service.catalog.Component_Get(str(value)) if value else None
                modules = radio.radio.modules if radio is not None and radio.radio is not None else {}
                # Flight also adopts the only declared module. Multiple choices
                # remain explicit; shared AIR settings and power are preserved.
                updates["module_variant"] = next(iter(modules)) if len(modules) == 1 else ""
                updates["resource_assignments"] = {}
            if field == "pc_interface" and value != ground.pc_interface:
                updates["pc_resource"] = ""
            if ground.radio_instances and field in {"radio_plugin", "module_variant", "tx_power_dbm"}:
                selected_fields = {"plugin" if key == "radio_plugin" else key: selected
                                   for key, selected in updates.items()
                                   if key in {"radio_plugin", "module_variant", "tx_power_dbm"}}
                radios = tuple(replace(radio, **selected_fields)
                               if radio.instance_id == ground.active_radio_instance else radio
                               for radio in ground.radio_instances)
                candidate.ground_target = GroundRadiosConfiguration_Apply(ground, radios, ground.active_radio_instance)
            else:
                candidate.ground_target = replace(ground, **updates)
        self._ProjectConfiguration_Change(change)

    def _GroundBoard_Change(self, board_id: str) -> None:
        if not board_id:
            self._ProjectConfiguration_Change(
                lambda candidate: setattr(
                    candidate, "ground_target", replace(
                        candidate.ground_target, board="", mcu="",
                        hardware=HardwareConfiguration(
                            mode="custom", source_kind="manual_import",
                            provider="silverstar.hardware_provider.stm32_cubemx",
                        ), resource_assignments={}, pc_resource="",
                    )
                )
            )
            return
        from silverstar_fccg.project.resources import (
            BoardHardwareInventory_Get,
            BoardResourceProvisions_Get,
        )

        board = self._service.catalog.Component_Get(board_id)
        if board.metadata.get("target_role") != "ground_station" and board.component_class != "ground_station_board":
            self._Error_Show("PCB target mismatch: select a Ground Station board")
            return
        inventory = BoardHardwareInventory_Get(board)
        if board.board is None or inventory is None:
            self._Error_Show("Ground board has no CubeMX hardware inventory")
            return
        mcu = next(
            (component_id for component_id in board.board.compatible_mcus
             if component_id in {item.component_id for item in self._service.catalog.Type_Get("mcu")}),
            "",
        )
        if not mcu:
            self._Error_Show("Ground board has no installed MCU platform")
            return
        hardware = HardwareConfiguration(
            mode="board_plugin", source_kind=board.board.source_kind,
            mcu=inventory.mcu_part, source_label=board.DisplayName_Get(
                self._translator.language
            ),
            inventory=inventory.Dictionary_Get(),
            resources=tuple(
                HardwareResource(item.resource_id, item.kind, item.metadata)
                for item in BoardResourceProvisions_Get(board)
            ),
            source_digest=str(board.metadata.get("reference", {}).get("snapshot_digest", "")),
        )
        def change(candidate: ProjectModel) -> None:
            ground = replace(candidate.ground_target, board=board_id, mcu=mcu,
                             hardware=hardware, resource_assignments={}, pc_resource="")
            if GroundActivityLedEnabled_Get(ground) and not (ground.tx_led_resource or ground.rx_led_resource):
                binding = self.ground_target_page.ActivityLedCandidate_Get(ground)
                if binding is not None:
                    resource, active_high = binding
                    ground = replace(ground, tx_led_resource=resource, rx_led_resource=resource,
                                     tx_led_active_high=active_high, rx_led_active_high=active_high)
            candidate.ground_target = ground
        self._ProjectConfiguration_Change(change)

    def _GroundAssignment_Change(self, requirement: str, resource: str) -> None:
        def change(candidate: ProjectModel) -> None:
            assignments = dict(candidate.ground_target.resource_assignments)
            key = requirement if ":" in requirement else f"radio0:{requirement}"
            if resource:
                assignments[key] = resource
            else:
                assignments.pop(key, None)
            candidate.ground_target = replace(
                candidate.ground_target, resource_assignments=assignments
            )
        self._ProjectConfiguration_Change(change)

    def _Resources_AutoAssign(self, *, silent: bool = False) -> None:
        if self._model.hardware.mode != "custom":
            return
        result = self._ProjectConfiguration_Change(lambda _candidate: None)
        if not silent and result is not None:
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.resources_assigned"
                    if result.resource_resolution.valid
                    else "status.resources_incomplete",
                    count=len(result.resource_resolution.errors),
                )
            )

    def _ResourceAssignment_Change(self, key: str, resource_id: str) -> None:
        if self._model.hardware.mode != "custom":
            return

        def change(candidate: ProjectModel) -> None:
            if resource_id:
                candidate.resource_assignments[key] = resource_id
            else:
                candidate.resource_assignments.pop(key, None)

        self._ProjectConfiguration_Change(change)

    def _HardwareAssignments_Validate(self) -> None:
        if self._model.hardware.mode != "custom":
            return
        result = ResourceAssignments_Resolve(
            self._model, self._service.catalog, auto_assign=False
        )
        if not result.valid:
            self._Project_Refresh()
            self._Error_Show(
                self._translator.Text_Get(
                    "error.manual_hardware_validation_failed",
                    count=len(result.errors),
                ),
                "\n".join(result.errors),
            )
            return

        def confirm(candidate: ProjectModel) -> None:
            candidate.hardware = replace(
                candidate.hardware,
                assignment_fingerprint=HardwareAssignmentFingerprint_Get(
                    candidate, self._service.catalog
                ),
            )

        applied = self._ProjectConfiguration_Change(
            confirm,
            status_key="status.manual_assignment_confirmed",
        )
        if applied is not None:
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.manual_assignment_confirmed"
                )
            )

    def _I2cExternalPullup_Change(
        self, resource_id: str, confirmed: bool
    ) -> None:
        if self._displaying_model or self._model.hardware.mode != "custom":
            return

        def change(candidate: ProjectModel) -> None:
            bindings = {
                key: dict(value)
                for key, value in (
                    candidate.hardware.i2c_external_pullup_confirmations.items()
                )
            }
            if (
                confirmed
                and candidate.hardware.source_digest
                and candidate.hardware.snapshot_id
            ):
                bindings[resource_id] = {
                    "source_digest": candidate.hardware.source_digest,
                    "snapshot_id": candidate.hardware.snapshot_id,
                }
            else:
                bindings.pop(resource_id, None)
            candidate.hardware = replace(
                candidate.hardware,
                i2c_external_pullup_confirmations=bindings,
            )

        self._ProjectConfiguration_Change(change)
