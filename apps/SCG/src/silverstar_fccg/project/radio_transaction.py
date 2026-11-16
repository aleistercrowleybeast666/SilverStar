"""Atomic shared-link edits; intermediate endpoint selections are private drafts."""
from copy import deepcopy
from dataclasses import replace

from silverstar_fccg.project.air_link import (
    AirLinkDefaults_Get,
    AirLinkIssues_Get,
    RadioCandidateIssues_Get,
)
from silverstar_fccg.project.ground_radios import GroundRadiosConfiguration_Apply
from silverstar_fccg.project.model import (
    DeviceInstance,
    GroundRadioConfiguration,
    GroundRadioConfigurations_Get,
    GroundRadioSelection_Apply,
)
from silverstar_fccg.project.radio_variants import (
    FlightRadioConfiguration_Apply,
    FlightRadioConfiguration_Get,
    RadioManifest_Resolve,
)


def RadioTransaction_ChoicesGet(link, catalog):
    """Use the generation contract for both endpoint selectors."""
    return tuple((manifest.component_id, module_id)
        for manifest in catalog.Type_Get('device') if manifest.radio is not None
        for module_id in manifest.radio.modules
        if not RadioCandidateIssues_Get(link, manifest.radio, module_id))


def RadioTransaction_EndpointClear(model, catalog, endpoint):
    """Clear an explicit selection without discarding unrelated hardware bindings."""
    candidate = deepcopy(model)
    if endpoint == 'flight':
        identity = candidate.air_link.flight_radio_instance
        candidate.device_instances = [item for item in candidate.device_instances if item.instance_id != identity]
        candidate.resource_assignments = {key: value for key, value in candidate.resource_assignments.items()
                                          if not key.startswith(identity + ':')}
    elif endpoint == 'ground':
        ground = candidate.ground_target
        identity = ground.active_radio_instance
        remaining = [item for item in GroundRadioConfigurations_Get(ground)
                     if item.instance_id != identity and item.plugin]
        assignments = {key: value for key, value in ground.resource_assignments.items()
                       if not key.startswith(identity + ':')}
        if ground.radio_plugin:
            manifest = catalog.Component_Get(ground.radio_plugin)
            legacy = {item.name for item in manifest.resource_requirements}
            assignments = {key: value for key, value in assignments.items() if key not in legacy}
        ground = replace(ground, resource_assignments=assignments)
        if remaining:
            candidate.ground_target = GroundRadiosConfiguration_Apply(ground, remaining, remaining[0].instance_id)
        else:
            candidate.ground_target = replace(ground, radio_instances=(), active_radio_instance='radio0',
                                             radio_plugin='', module_variant='')
    else:
        raise ValueError('RADIO_ENDPOINT_INVALID')
    return candidate


def RadioTransaction_BandSet(model, catalog, family):
    """Explicit band changes restore its supported PHY and remove incompatible radios."""
    candidate = deepcopy(model)
    candidate.air_link = AirLinkDefaults_Get(candidate.air_link, family)
    choices = set(RadioTransaction_ChoicesGet(candidate.air_link, catalog))
    removed = []
    for item in tuple(candidate.device_instances):
        manifest = catalog.Component_Get(item.plugin)
        if manifest.radio is None:
            continue
        module, _power = FlightRadioConfiguration_Get(candidate, item)
        if (item.plugin, module) not in choices:
            removed.append('flight:' + item.instance_id)
            candidate.device_instances.remove(item)
            candidate.resource_assignments = {key: value for key, value in candidate.resource_assignments.items()
                                              if not key.startswith(item.instance_id + ':')}
    for item in GroundRadioConfigurations_Get(candidate.ground_target):
        if item.plugin and (item.plugin, item.module_variant) not in choices:
            removed.append('ground:' + item.instance_id)
            candidate.ground_target = GroundRadioSelection_Apply(candidate.ground_target, item.instance_id)
            candidate = RadioTransaction_EndpointClear(candidate, catalog, 'ground')
    return candidate, tuple(removed)


def RadioTransaction_EndpointSet(model, catalog, endpoint, plugin_id, module_id, power):
    """Return a draft without checking it against the old shared PHY."""
    manifest = catalog.Component_Get(plugin_id)
    module = manifest.radio.modules.get(module_id) if manifest.radio else None
    if (module is None or type(power) is not int
            or power not in module['supported_tx_powers_dbm']):
        raise ValueError('RADIO_MODULE_UNSUPPORTED: select a registered module and output power')
    candidate = deepcopy(model)
    if endpoint == 'flight':
        identity = candidate.air_link.flight_radio_instance
        previous = candidate.DeviceInstance_Get(identity)
        selected = replace(previous, plugin=plugin_id, module_variant=module_id, tx_power_dbm=power) if previous else DeviceInstance(
            identity, plugin_id, module_variant=module_id, tx_power_dbm=power)
        if previous:
            candidate.device_instances = [selected if item.instance_id == identity else item
                                          for item in candidate.device_instances]
        else:
            candidate.device_instances.append(selected)
        if previous and previous.plugin != plugin_id:
            candidate.resource_assignments = {key: value for key, value in candidate.resource_assignments.items()
                                              if not key.startswith(identity + ':')}
        candidate = FlightRadioConfiguration_Apply(candidate, identity, module_id, power)
    elif endpoint == 'ground':
        ground = candidate.ground_target
        identity = ground.active_radio_instance
        radios = [GroundRadioConfiguration(identity, plugin_id, module_id, power) if item.instance_id == identity else item
                  for item in GroundRadioConfigurations_Get(ground)]
        candidate.ground_target = GroundRadiosConfiguration_Apply(ground, radios, identity)
        if ground.radio_plugin and ground.radio_plugin != plugin_id:
            # Legacy single-radio assignments have no instance prefix.
            legacy = {item.name for item in catalog.Component_Get(ground.radio_plugin).resource_requirements}
            candidate.ground_target = replace(candidate.ground_target, resource_assignments={
                key: value for key, value in candidate.ground_target.resource_assignments.items() if key not in legacy})
        resolved = RadioManifest_Resolve(manifest, GroundRadioConfiguration(identity, plugin_id, module_id, power))
        unused = {item.name for item in manifest.resource_requirements} - {
            item.name for item in resolved.resource_requirements}
        candidate.ground_target = replace(candidate.ground_target, resource_assignments={
            key: value for key, value in candidate.ground_target.resource_assignments.items()
            if key not in unused and key not in {identity + ':' + name for name in unused}})
    else:
        raise ValueError('RADIO_ENDPOINT_INVALID')
    return candidate


def RadioTransaction_IssuesGet(model, catalog):
    """Validate every configured peer, regardless of the next generation scope."""
    issues = []
    if model.DeviceInstance_Get(model.air_link.flight_radio_instance) is not None:
        issues.extend(AirLinkIssues_Get(model, catalog, target_scope='flight'))
    if model.ground_target.radio_plugin:
        issues.extend(AirLinkIssues_Get(model, catalog, target_scope='ground'))
    if model.DeviceInstance_Get(model.air_link.flight_radio_instance) is None and not model.ground_target.radio_plugin:
        # Empty editing states may be saved, but still obey the shared PHY and
        # protocol contract. Actual generation continues to require its radio.
        issues.extend(issue for issue in AirLinkIssues_Get(model, catalog, target_scope='all')
                      if issue.code != 'AIR_LINK_NO_RADIO')
    return tuple(dict.fromkeys(issues))


def RadioTransaction_Commit(model, catalog):
    if model.air_link.protocol_profile != 'ss_tm.s.0_1':
        raise ValueError('RADIO_PROTOCOL_MIGRATION_REQUIRED: explicitly migrate the legacy profile to SS-TM-S')
    issues = RadioTransaction_IssuesGet(model, catalog)
    if issues:
        raise ValueError('\n'.join(issue.code + ': ' + issue.message for issue in issues))
    return deepcopy(model)
