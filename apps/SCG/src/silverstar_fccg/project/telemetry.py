"""Explicit protocol selection/migration; physical link values remain unchanged."""
from copy import deepcopy
from dataclasses import replace

from silverstar_fccg.project.model import ProtocolSelection

TM_COMPONENT = 'silverstar.protocol.telemetry.ss_tm'
TM_PROFILES = ('ss_tm.s.0_1', 'ss_tm.h.0_1')


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
    if selected is None or selected.component != TM_COMPONENT:
        return []
    issues = []
    if selected.profile not in TM_PROFILES:
        issues.append(('TM_PROFILE_UNKNOWN', 'SS-TM communication profile is unsupported'))
    if model.air_link.radio_family != 'sx128x':
        issues.append(('TM_RADIO_MODE_UNSUPPORTED', 'SS-TM currently requires SX1281; NRF auto-ACK simplex is not qualified'))
    if model.mcu_family not in ('silverstar.mcu_family.stm32f4', 'silverstar.mcu_family.stm32h7'):
        issues.append(('TM_BOOT_SESSION_UNSUPPORTED', 'This Flight backend has no supported boot-session nonce provider'))
    if model.air_link.packet_mtu < 56 or model.air_link.packet_mtu > 61:
        issues.append(('TM_MTU', 'SS-TM requires a 56..61 byte logical application MTU'))
    if model.air_link.radio_family == 'sx128x' and selected.profile in TM_PROFILES:
        from silverstar_telemetry.plan import TelemetryPlan_Get
        link = model.air_link
        try:
            for preflight in (False, True):
                plan = TelemetryPlan_Get('S' if selected.profile == TM_PROFILES[0] else 'H',
                    preflight=preflight, control_ack_hz=1 if preflight or selected.profile == TM_PROFILES[1] else 0,
                    sf=link.spreading_factor, bandwidth_hz=link.bandwidth_hz,
                    coding_rate=link.coding_rate, preamble=link.preamble_symbols)
                if plan['scheduler_fraction'] >= 0.95:
                    issues.append(('TM_AIRTIME_OVER_CAPACITY',
                        'Selected PHY cannot sustain the telemetry/control plan with margin; choose a supported plan explicitly'))
                    break
        except ValueError as error:
            issues.append(('TM_AIRTIME_UNSUPPORTED', str(error)))
    return issues
