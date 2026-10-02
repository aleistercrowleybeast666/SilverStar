from __future__ import annotations

from dataclasses import dataclass

from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.manifest import PluginManifest, RadioContribution
from silverstar_fccg.project.model import ProjectModel


@dataclass(frozen=True, slots=True)
class AirLinkIssue:
    code: str
    message: str


def RadioLinkCompatible_Get(link, radio: RadioContribution) -> bool:
    return not RadioCandidateIssues_Get(link, radio)


def _AirLinkProfileIssues_Get(link) -> list[AirLinkIssue]:
    if link.radio_family != "sx128x":
        return []
    if (
        link.spreading_factor not in range(5, 13)
        or link.bandwidth_hz not in {200000, 400000, 800000, 1600000}
        or link.coding_rate not in {"4/5", "4/6", "4/7", "4/8"}
        or link.preamble_symbols != 16
        or link.header_mode != "explicit"
        or not link.crc_enabled
        or link.iq_mode != "normal"
    ):
        return [AirLinkIssue(
            "AIR_LINK_PHY_INCOMPATIBLE",
            "The current SX128x driver supports only its verified PHY profile",
        )]
    return []


def _Radio_Get(
    catalog: PluginCatalog, plugin_id: str, endpoint: str,
) -> tuple[PluginManifest | None, AirLinkIssue | None]:
    if not plugin_id:
        return None, AirLinkIssue("AIR_LINK_NO_RADIO", f"{endpoint} radio is not selected")
    try:
        manifest = catalog.Component_Get(plugin_id)
    except ValueError:
        return None, AirLinkIssue("AIR_LINK_NO_RADIO", f"{endpoint} radio plugin is unavailable")
    if manifest.radio is None:
        return None, AirLinkIssue("AIR_LINK_NO_RADIO", f"{endpoint} plugin has no radio contract")
    return manifest, None


def _PhyIssues_Get(link, radio: RadioContribution, endpoint: str) -> list[AirLinkIssue]:
    issues = []
    if (
        link.phy_mode not in radio.phy_modes
        or link.bandwidth_hz not in radio.bandwidths_hz
        or link.spreading_factor not in radio.spreading_factors
        or link.coding_rate not in radio.coding_rates
    ):
        issues.append(AirLinkIssue(
            "AIR_LINK_PHY_INCOMPATIBLE", f"{endpoint} radio cannot use selected PHY"
        ))
    return issues


def RadioCandidateIssues_Get(
    link, radio: RadioContribution, module_id: str = "", endpoint: str = "Radio",
) -> tuple[AirLinkIssue, ...]:
    """One physical compatibility decision for selection and generation."""
    issues: list[AirLinkIssue] = _AirLinkProfileIssues_Get(link)
    if radio.technology != link.radio_technology or radio.family != link.radio_family:
        issues.append(AirLinkIssue("AIR_LINK_FAMILY_MISMATCH",
                                   f"{endpoint} technology or family differs from AIR Link"))
    if module_id and module_id not in radio.modules:
        issues.append(AirLinkIssue("AIR_LINK_NO_RADIO", f"{endpoint} module is unavailable"))
    modules = ((radio.modules[module_id],) if module_id in radio.modules else
               tuple(radio.modules.values()) if not module_id else ())
    if not (radio.frequency_min_hz <= link.frequency_hz <= radio.frequency_max_hz
            and any(module["validated_frequency_min_hz"] <= link.frequency_hz
                    <= module["validated_frequency_max_hz"] for module in modules)):
        issues.append(AirLinkIssue("AIR_LINK_FREQUENCY_OUT_OF_RANGE",
                                   f"{endpoint} frequency is outside the qualified module range"))
    issues.extend(_PhyIssues_Get(link, radio, endpoint))
    if link.packet_mtu > radio.maximum_payload:
        issues.append(AirLinkIssue("AIR_LINK_MTU_TOO_SMALL",
                                   f"{endpoint} maximum payload is {radio.maximum_payload}"))
    return tuple(issues)


def AirLinkIssues_Get(model: ProjectModel, catalog: PluginCatalog) -> tuple[AirLinkIssue, ...]:
    """Validate one shared AIR snapshot against both physical radio endpoints."""
    link = model.air_link
    issues = _AirLinkProfileIssues_Get(link)
    flight_instance = model.DeviceInstance_Get(link.flight_radio_instance)
    flight, flight_error = _Radio_Get(
        catalog, flight_instance.plugin if flight_instance else "", "Flight"
    )
    ground = None
    ground_error = None
    if model.ground_target.enabled:
        ground, ground_error = _Radio_Get(
            catalog, model.ground_target.radio_plugin, "Ground"
        )
    issues.extend(issue for issue in (flight_error, ground_error) if issue is not None)
    radios = tuple(
        (endpoint, manifest.radio)
        for endpoint, manifest in (("Flight", flight), ("Ground", ground))
        if manifest is not None and manifest.radio is not None
    )
    for endpoint, radio in radios:
        module_id = model.ground_target.module_variant if endpoint == "Ground" else ""
        issues.extend(RadioCandidateIssues_Get(link, radio, module_id, endpoint))
    if flight is not None and flight.radio is not None:
        flight_modules = tuple(flight.radio.modules.values())
        if len(flight_modules) != 1 or model.flight_tx_power_dbm not in flight_modules[0]["supported_tx_powers_dbm"]:
            issues.append(AirLinkIssue(
                "AIR_LINK_TX_POWER_UNSUPPORTED",
                "Flight TX power is not supported by the selected radio module",
            ))
    if ground is not None and ground.radio is not None:
        module = ground.radio.modules.get(model.ground_target.module_variant)
        if module is not None and model.ground_target.tx_power_dbm not in module["supported_tx_powers_dbm"]:
            issues.append(AirLinkIssue(
                "AIR_LINK_TX_POWER_UNSUPPORTED",
                "Ground TX power is not supported by the selected radio module",
            ))

    protocol = model.protocols.get("telemetry")
    minimum_air_mtu = 0
    if protocol is not None and protocol.profile == link.protocol_profile:
        try:
            protocol_manifest = catalog.Component_Get(protocol.component)
            for profile in protocol_manifest.protocol.profiles.get("telemetry", ()):
                if profile.profile_id == link.protocol_profile and profile.transport is not None:
                    minimum_air_mtu = profile.transport.minimum_mtu
        except (ValueError, AttributeError):
            pass
    else:
        issues.append(AirLinkIssue(
            "AIR_LINK_PHY_INCOMPATIBLE", "AIR Link protocol does not match Flight telemetry"
        ))
    # GSP AIR_RX has three wrapper bytes; the GS reference has a 64-byte payload.
    usable_mtu = min(
        (radio.maximum_payload for _endpoint, radio in radios), default=0
    )
    if model.ground_target.enabled:
        usable_mtu = min(usable_mtu, 61)
    if radios and not minimum_air_mtu <= link.packet_mtu <= usable_mtu:
        issues.append(AirLinkIssue(
            "AIR_LINK_MTU_TOO_SMALL",
            f"AIR requires {minimum_air_mtu} bytes and this bridge permits {usable_mtu}",
        ))
    return tuple(dict.fromkeys(issues))


def GroundTargetIssues_Get(model: ProjectModel, catalog: PluginCatalog) -> tuple[AirLinkIssue, ...]:
    if not model.ground_target.enabled:
        return ()
    ground = model.ground_target
    issues = list(AirLinkIssues_Get(model, catalog))
    from silverstar_fccg.project.ground_radios import GroundRadiosRuntimeIssue_Get
    runtime_issue = GroundRadiosRuntimeIssue_Get(ground, catalog)
    if runtime_issue is not None:
        issues.append(runtime_issue)
    board = None
    if ground.board:
        try:
            board = catalog.Component_Get(ground.board)
        except ValueError:
            issues.append(AirLinkIssue("GROUND_BOARD_UNKNOWN", "Selected Ground PCB is unavailable"))
        else:
            role = board.metadata.get("target_role")
            if role != "ground_station" and board.component_class != "ground_station_board":
                issues.append(AirLinkIssue("BOARD_TARGET_ROLE_MISMATCH", "Ground requires a Ground Station PCB"))
    if ground.hardware.mode == "unselected" or not ground.mcu:
        issues.append(AirLinkIssue("GROUND_HARDWARE_UNBOUND", "Ground hardware is not selected"))
    elif ground.hardware.mode == "custom" and not any(
        source.endswith("/Core/Src/main.c") for source in ground.hardware.build_sources
    ):
        issues.append(AirLinkIssue(
            "GROUND_CUBEMX_GENERATION_REQUIRED",
            "Generate the CubeMX source project for the Ground .ioc before firmware generation",
        ))
    if ground.hardware.mode == "custom" and not ground.hardware.snapshot_id:
        issues.append(AirLinkIssue(
            "GROUND_HARDWARE_UNBOUND", "Ground CubeMX snapshot is unavailable",
        ))
    if ground.hardware.mode != "unselected" and ground.mcu:
        from silverstar_fccg.project.clock_plan import ClockPlan_Validate

        try:
            exact_mcu = catalog.Component_Get(ground.mcu)
        except ValueError:
            issues.append(AirLinkIssue(
                "GROUND_MCU_UNKNOWN", "Selected Ground MCU is not in the catalog",
            ))
        else:
            issues.extend(
                AirLinkIssue("GROUND_" + issue.code, issue.message)
                for issue in ClockPlan_Validate(
                    ground.hardware.inventory, exact_mcu.metadata,
                )
            )
    available = {resource.resource_id: resource for resource in ground.hardware.resources}
    if ground.pc_interface == "uart":
        resource = available.get(ground.pc_resource)
        if resource is None or resource.kind != "uart":
            issues.append(AirLinkIssue("GROUND_UART_UNBOUND", "Ground UART resource is unavailable"))
        elif (
            resource.metadata.get("baud_rate") != ground.baudrate
            or resource.metadata.get("word_length") != 8
            or resource.metadata.get("parity") != "none"
            or resource.metadata.get("stop_bits") != 1.0
            or not {"tx", "rx"}.issubset(
                str(key).lower() for key in resource.metadata.get("pins", {})
            )
        ):
            issues.append(AirLinkIssue(
                "GROUND_UART_UNBOUND", "Ground UART must match selected baudrate and 8N1 RX/TX"
            ))
    elif ground.pc_interface == "usb_cdc":
        usb_sources = {source.rsplit("/", 1)[-1].casefold()
                       for source in ground.hardware.build_sources}
        required_usb_sources = {
            "usb_device.c", "usbd_cdc_if.c", "usbd_desc.c", "usbd_conf.c",
            "usbd_core.c", "usbd_ctlreq.c", "usbd_ioreq.c", "usbd_cdc.c",
        }
        if not ground.hardware.inventory.get("usb_cdc") or not any(
            resource.kind == "usb_cdc" for resource in available.values()
        ) or not required_usb_sources.issubset(usb_sources):
            issues.append(AirLinkIssue(
                "GROUND_USB_CDC_UNAVAILABLE",
                "Ground CubeMX hardware lacks USB Device CDC sources or capability",
            ))
    else:
        issues.append(AirLinkIssue(
            "GROUND_PC_INTERFACE_UNBOUND", "Ground PC interface must be UART or USB CDC"
        ))
    from silverstar_fccg.project.model import GroundRadioConfigurations_Get
    configurations = GroundRadioConfigurations_Get(ground)
    exclusive: dict[str, str] = {}
    occupied_pins: dict[str, str] = {}
    pc_resource = available.get(ground.pc_resource) if ground.pc_interface == "uart" else None
    if pc_resource is not None:
        pc_pins = pc_resource.metadata.get("pins", {})
        if isinstance(pc_pins, dict):
            occupied_pins.update((str(pin), "pc_interface") for pin in pc_pins.values() if pin)
    for radio_index, configuration in enumerate(configurations):
        try:
            radio = catalog.Component_Get(configuration.plugin)
        except ValueError:
            radio = None
        if radio is not None:
            from silverstar_fccg.plugins.manifest import (
                ResourceMode, ResourceProvision,
            )
            from silverstar_fccg.project.resources import (
                _RequirementConstraintsErrors_Get,
            )

            if radio.radio is not None and configuration.module_variant not in radio.radio.modules:
                issues.append(AirLinkIssue(
                    "AIR_LINK_NO_RADIO", "Ground radio module variant is unavailable"
                ))
            for requirement in radio.resource_requirements:
                key = f"{configuration.instance_id}:{requirement.name}"
                assigned = ground.resource_assignments.get(key)
                if radio_index == 0 and board is not None and ground.hardware.mode == "board_plugin":
                    role = next((item for item in board.resource_roles
                                 if item.key == f"telemetry:{requirement.name}"), None)
                    if role is not None and role.fixed and assigned != role.default:
                        issues.append(AirLinkIssue("GROUND_BOARD_FIXED_RESOURCE_MISMATCH",
                            f"Ground PCB fixes {requirement.name} to {role.default}"))
                resource = available.get(assigned or "")
                if (requirement.required and resource is None) or (
                    resource is not None and resource.kind != requirement.kind
                ):
                    issues.append(AirLinkIssue(
                        "GROUND_RADIO_RESOURCE_UNBOUND",
                        f"Ground {configuration.instance_id} {requirement.name} needs a {requirement.kind} resource",
                    ))
                    continue
                if resource is None:
                    continue
                for detail in _RequirementConstraintsErrors_Get(
                    key, requirement,
                    ResourceProvision(resource.resource_id, resource.kind,
                                      metadata=resource.metadata),
                    model,
                ):
                    issues.append(AirLinkIssue(
                        "GROUND_RADIO_RESOURCE_CONSTRAINT", detail,
                    ))
                # Ground cold standby uses one task and retires a port before switching.
                shared_ground_spi = requirement.name == "radio_bus" and requirement.kind == "spi"
                if requirement.mode == ResourceMode.EXCLUSIVE and not shared_ground_spi:
                    physical = str(resource.metadata.get(
                        "physical_pin", resource.metadata.get(
                            "physical_resource", resource.resource_id,
                        ),
                    ))
                    previous = exclusive.setdefault(physical, key)
                    if previous != key:
                        issues.append(AirLinkIssue(
                            "GROUND_RESOURCE_CONFLICT",
                            f"{previous} and {key} both use {physical}",
                        ))
                    pins = resource.metadata.get("pins", {})
                    physical_pins = (
                        pins.values() if isinstance(pins, dict) else ()
                    )
                    physical_pins = (*physical_pins,
                                     resource.metadata.get("physical_pin"))
                    for pin in (str(value) for value in physical_pins if value):
                        previous = occupied_pins.setdefault(pin, key)
                        if previous != key:
                            issues.append(AirLinkIssue(
                                "GROUND_RESOURCE_CONFLICT",
                                f"{previous} and {key} both use pin {pin}",
                            ))
    from silverstar_fccg.project.ground_activity import GroundActivityLedIssues_Get
    issues.extend(GroundActivityLedIssues_Get(ground, catalog))
    return tuple(issues)
