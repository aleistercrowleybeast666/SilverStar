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
    return (
        radio.technology == link.radio_technology
        and radio.family == link.radio_family
        and link.frequency_hz >= radio.frequency_min_hz
        and link.frequency_hz <= radio.frequency_max_hz
        and link.phy_mode in radio.phy_modes
        and link.bandwidth_hz in radio.bandwidths_hz
        and link.spreading_factor in radio.spreading_factors
        and link.coding_rate in radio.coding_rates
        and link.packet_mtu <= radio.maximum_payload
    )


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


def AirLinkIssues_Get(model: ProjectModel, catalog: PluginCatalog) -> tuple[AirLinkIssue, ...]:
    """Validate one shared AIR snapshot against both physical radio endpoints."""
    link = model.air_link
    issues = _AirLinkProfileIssues_Get(link)
    if not model.ground_target.enabled:
        return tuple(issues)
    flight_instance = model.DeviceInstance_Get(link.flight_radio_instance)
    flight, flight_error = _Radio_Get(
        catalog, flight_instance.plugin if flight_instance else "", "Flight"
    )
    ground, ground_error = _Radio_Get(
        catalog, model.ground_target.radio_plugin, "Ground"
    )
    issues.extend(issue for issue in (flight_error, ground_error) if issue is not None)
    if issues:
        return tuple(issues)
    assert flight is not None and ground is not None
    flight_radio = flight.radio
    ground_radio = ground.radio
    assert flight_radio is not None and ground_radio is not None

    if (
        flight_radio.technology != ground_radio.technology
        or flight_radio.family != ground_radio.family
        or link.radio_technology != flight_radio.technology
        or link.radio_family != flight_radio.family
    ):
        issues.append(AirLinkIssue(
            "AIR_LINK_FAMILY_MISMATCH", "Flight, Ground and AIR Link radio families differ"
        ))
    selected_frequency = link.frequency_hz
    minimum_frequency = max(flight_radio.frequency_min_hz, ground_radio.frequency_min_hz)
    maximum_frequency = min(flight_radio.frequency_max_hz, ground_radio.frequency_max_hz)
    if not minimum_frequency <= selected_frequency <= maximum_frequency:
        issues.append(AirLinkIssue(
            "AIR_LINK_FREQUENCY_OUT_OF_RANGE",
            "Selected frequency is outside the radio range overlap",
        ))
    issues.extend(_PhyIssues_Get(link, flight_radio, "Flight"))
    issues.extend(_PhyIssues_Get(link, ground_radio, "Ground"))

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
    usable_mtu = min(flight_radio.maximum_payload, ground_radio.maximum_payload, 61)
    if not minimum_air_mtu <= link.packet_mtu <= usable_mtu:
        issues.append(AirLinkIssue(
            "AIR_LINK_MTU_TOO_SMALL",
            f"AIR requires {minimum_air_mtu} bytes and this bridge permits {usable_mtu}",
        ))
    return tuple(issues)


def GroundTargetIssues_Get(model: ProjectModel, catalog: PluginCatalog) -> tuple[AirLinkIssue, ...]:
    if not model.ground_target.enabled:
        return ()
    ground = model.ground_target
    issues = list(AirLinkIssues_Get(model, catalog))
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
        if not ground.hardware.inventory.get("usb_cdc") or not any(
            resource.kind == "usb_cdc" for resource in available.values()
        ):
            issues.append(AirLinkIssue(
                "GROUND_USB_CDC_UNAVAILABLE", "Ground CubeMX hardware has no USB Device CDC"
            ))
    else:
        issues.append(AirLinkIssue(
            "GROUND_PC_INTERFACE_UNBOUND", "Ground PC interface must be UART or USB CDC"
        ))
    if ground.radio_plugin:
        try:
            radio = catalog.Component_Get(ground.radio_plugin)
        except ValueError:
            radio = None
        if radio is not None:
            if radio.radio is not None and ground.module_variant not in radio.radio.modules:
                issues.append(AirLinkIssue(
                    "AIR_LINK_NO_RADIO", "Ground radio module variant is unavailable"
                ))
            for requirement in radio.resource_requirements:
                assigned = ground.resource_assignments.get(f"radio0:{requirement.name}")
                resource = available.get(assigned or "")
                if requirement.required and (resource is None or resource.kind != requirement.kind):
                    issues.append(AirLinkIssue(
                        "GROUND_RADIO_RESOURCE_UNBOUND",
                        f"Ground radio {requirement.name} needs a {requirement.kind} resource",
                    ))
    return tuple(issues)
