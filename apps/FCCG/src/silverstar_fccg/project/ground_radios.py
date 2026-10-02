"""Existing Ground radio configuration contract; no implicit resource copying."""
from dataclasses import replace

from silverstar_fccg.project.model import (
    GroundRadioConfigurations_Get, GroundRadioSelection_Apply, ProjectModelError,
    DEVICE_INSTANCE_ID_PATTERN,
)


def GroundRadiosConfiguration_Apply(ground, radios, active):
    radios = tuple(radios)
    identifiers = tuple(radio.instance_id for radio in radios)
    if not 1 <= len(radios) <= 4 or len(set(identifiers)) != len(radios):
        raise ProjectModelError("Ground radios require 1..4 unique instances")
    if any(not DEVICE_INSTANCE_ID_PATTERN.fullmatch(identity) for identity in identifiers):
        raise ProjectModelError("Ground radio instance ID is invalid")
    previous = {radio.instance_id: radio for radio in GroundRadioConfigurations_Get(ground)}
    removed = previous.keys() - set(identifiers)
    removed |= {radio.instance_id for radio in radios if radio.instance_id in previous
                and previous[radio.instance_id].plugin != radio.plugin}
    assignments = {key: value for key, value in ground.resource_assignments.items()
                   if key.split(":", 1)[0] not in removed}
    return GroundRadioSelection_Apply(replace(ground, radio_instances=radios,
        resource_assignments=assignments), active)


def GroundRadiosRuntimeIssue_Get(ground, catalog):
    from silverstar_fccg.project.air_link import AirLinkIssue
    if not ground.enabled or not ground.radio_instances:
        return None
    if len(ground.radio_instances) == 1 and ground.radio_instances[0].instance_id == "radio0":
        return None
    core = catalog.Component_Get("silverstar.core.ground.0_1_0")
    if core.metadata.get("ground_radio_instances_ready") is True:
        return None
    return AirLinkIssue("GROUND_RADIO_RUNTIME_UNAVAILABLE",
        "Multiple Ground radio instances require the integrated runtime/generator")
