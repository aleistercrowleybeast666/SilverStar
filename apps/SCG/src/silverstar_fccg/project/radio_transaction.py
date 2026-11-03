"""Atomic shared-link edits; intermediate endpoint selections are private drafts."""
from copy import deepcopy
from dataclasses import replace

from silverstar_fccg.project.air_link import AirLinkIssues_Get
from silverstar_fccg.project.ground_radios import GroundRadiosConfiguration_Apply
from silverstar_fccg.project.model import DeviceInstance, GroundRadioConfiguration, GroundRadioConfigurations_Get
from silverstar_fccg.project.radio_variants import FlightRadioConfiguration_Apply


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
            candidate.ground_target = replace(candidate.ground_target, resource_assignments={})
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
    return tuple(dict.fromkeys(issues))


def RadioTransaction_Commit(model, catalog):
    if model.air_link.protocol_profile != 'ss_tm.s.0_1':
        raise ValueError('RADIO_PROTOCOL_MIGRATION_REQUIRED: explicitly migrate the legacy profile to SS-TM-S')
    issues = RadioTransaction_IssuesGet(model, catalog)
    if issues:
        raise ValueError('\n'.join(issue.code + ': ' + issue.message for issue in issues))
    return deepcopy(model)
