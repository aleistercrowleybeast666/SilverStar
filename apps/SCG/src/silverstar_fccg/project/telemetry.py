"""Explicit protocol selection/migration; physical link values remain unchanged."""
from copy import deepcopy
from dataclasses import replace

from silverstar_fccg.project.model import ProtocolSelection

TM_COMPONENT = 'silverstar.protocol.telemetry.ss_tm'
TM_PROFILES = ('ss_tm.s.0_1',)


def TelemetryProfile_Apply(model, catalog, profile):
    if profile not in TM_PROFILES:
        raise ValueError('telemetry_profile_unsupported')
    component = catalog.Component_Get(TM_COMPONENT)
    candidate = deepcopy(model)
    candidate.protocols['telemetry'] = ProtocolSelection(TM_COMPONENT, component.version,
                                                       profile, component.ManifestSha256_Get())
    candidate.air_link = replace(candidate.air_link, protocol_profile=profile)
    return candidate


def TelemetryProfile_Issues(model, catalog):
    selected = model.protocols.get('telemetry')
    if selected is None:
        return []
    if selected.component != TM_COMPONENT or selected.profile != TM_PROFILES[0]:
        return [('LEGACY_PROTOCOL_MIGRATION_REQUIRED',
                 'This saved wireless profile is read-only for historical compatibility. Explicitly migrate to SS-TM-S before generating.')]
    issues = []
    if selected.profile not in TM_PROFILES:
        issues.append(('TM_PROFILE_UNKNOWN', 'SS-TM communication profile is unsupported'))
    if model.air_link.radio_family not in ('sx128x', 'sx127x'):
        issues.append(('TM_RADIO_MODE_UNSUPPORTED', 'SS-TM requires an explicitly supported SX1281 or E32-400M20S SPI radio'))
    if model.mcu_family not in ('silverstar.mcu_family.stm32f4', 'silverstar.mcu_family.stm32h7'):
        issues.append(('TM_BOOT_SESSION_UNSUPPORTED', 'This Flight backend has no supported boot-session nonce provider'))
    if model.air_link.packet_mtu < 56 or model.air_link.packet_mtu > 61:
        issues.append(('TM_MTU', 'SS-TM requires a 56..61 byte logical application MTU'))
    if model.air_link.radio_family in ('sx128x', 'sx127x') and selected.profile in TM_PROFILES:
        from silverstar_telemetry.plan import TelemetryPlan_Get
        link = model.air_link
        try:
            for preflight in (False, True):
                plan = TelemetryPlan_Get('S',
                    preflight=preflight, control_ack_hz=(0.5 if link.radio_family == 'sx127x' else 1) if preflight else 0,
                    radio_family=link.radio_family,
                    sf=link.spreading_factor, bandwidth_hz=link.bandwidth_hz,
                    coding_rate=link.coding_rate, preamble=link.preamble_symbols)
                if plan['scheduler_fraction'] >= 0.95:
                    issues.append(('TM_AIRTIME_OVER_CAPACITY',
                        'Selected PHY cannot sustain the telemetry/control plan with margin; choose a supported plan explicitly'))
                    break
        except ValueError as error:
            issues.append(('TM_AIRTIME_UNSUPPORTED', str(error)))
    return issues
