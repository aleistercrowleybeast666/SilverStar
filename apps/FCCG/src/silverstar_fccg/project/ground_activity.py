"""Ground LED bindings; no defaults select hardware or reserve a pin."""
from __future__ import annotations

import re


def GroundActivityLedOutputResources_Get(ground):
    return tuple(resource for resource in ground.hardware.resources
                 if resource.kind == "gpio_output")


def _ResourceClaims_Get(resource):
    claims = {"resource:" + resource.resource_id,
              "resource:" + str(resource.metadata.get("c_id", resource.resource_id))}
    pins = resource.metadata.get("pins", {})
    values = list(pins.values()) if isinstance(pins, dict) else []
    values += [resource.metadata.get("physical_pin"), resource.metadata.get("physical_resource")]
    for value in values:
        if value:
            normalized = re.sub(r"[^A-Z0-9]", "", str(value).upper())
            normalized = re.sub(r"^GPIO([A-K])", r"P\1", normalized)
            claims.add("pin:" + normalized)
    return claims


def GroundActivityLedIssues_Get(ground, catalog=None):
    from silverstar_fccg.project.air_link import AirLinkIssue
    if not ground.enabled:
        return ()
    issues = []
    if catalog is not None and (ground.tx_led_resource or ground.rx_led_resource):
        core = catalog.Component_Get("silverstar.core.ground.0_1_0")
        if core.metadata.get("ground_activity_leds_ready") is not True:
            issues.append(AirLinkIssue("GROUND_LED_RUNTIME_UNAVAILABLE",
                                      "Activity LEDs require the integrated Ground runtime/generator"))
    if type(ground.activity_led_pulse_ms) is not int or not 1 <= ground.activity_led_pulse_ms <= 200:
        issues.append(AirLinkIssue("GROUND_LED_PULSE_INVALID", "LED pulse must be 1..200 ms"))
    available = {resource.resource_id: resource for resource in ground.hardware.resources}
    occupied = set()
    identifiers = set(ground.resource_assignments.values())
    if ground.pc_interface == "uart":
        identifiers.add(ground.pc_resource)
    elif ground.pc_interface == "usb_cdc":
        identifiers.update(resource.resource_id for resource in ground.hardware.resources
                           if resource.kind == "usb_cdc")
    for identity in identifiers:
        if identity in available:
            occupied.update(_ResourceClaims_Get(available[identity]))
    selected = []
    for role in ("tx", "rx"):
        identity = getattr(ground, role + "_led_resource")
        polarity = getattr(ground, role + "_led_active_high")
        if not identity:
            continue
        resource = available.get(identity)
        if resource is None or resource.kind != "gpio_output":
            issues.append(AirLinkIssue("GROUND_LED_OUTPUT_UNBOUND", role.upper() + " LED needs a writable GPIO output"))
            continue
        claims = _ResourceClaims_Get(resource)
        if claims & occupied:
            issues.append(AirLinkIssue("GROUND_LED_RESOURCE_CONFLICT", role.upper() + " LED conflicts with a radio or PC interface"))
        selected.append((identity, polarity, claims))
    if len(selected) == 2 and selected[0][2] & selected[1][2]:
        if selected[0][1] != selected[1][1]:
            issues.append(AirLinkIssue("GROUND_LED_POLARITY_CONFLICT", "Shared TX/RX GPIO requires matching polarity"))
        elif selected[0][0] != selected[1][0]:
            issues.append(AirLinkIssue("GROUND_LED_RESOURCE_CONFLICT", "Shared TX/RX GPIO must use one canonical resource ID"))
    return tuple(issues)
