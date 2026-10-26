"""SX128x LoRa integer airtime model shared with the bounded firmware scheduler.

Matches Lora_PacketAirtimeMs, including SX128x's actual bandwidths and SF5/6
preamble correction. These are model estimates, not RF measurements.
"""
from math import ceil


def LoraAirtimeUs_Compute(length, *, sf=10, bandwidth_hz=800000, coding_rate='4/5', preamble=16):
    bandwidths = {200000: 203125, 400000: 406250, 800000: 812500, 1600000: 1625000}
    if type(length) is not int or not 1 <= length <= 64 or sf not in range(5, 13):
        raise ValueError('airtime_length_or_sf')
    if coding_rate not in ('4/5', '4/6', '4/7', '4/8') or bandwidth_hz not in bandwidths or preamble != 16:
        raise ValueError('airtime_phy_unsupported')
    bits = 8 * length - 4 * sf + 16 + 20 + (8 if sf >= 7 else 0)
    blocks = max(0, ceil(bits / (4 * (sf - 2 if sf > 10 else sf))))
    quarters = 4 * (preamble + 8 + blocks * int(coding_rate[-1])) + (17 if sf >= 7 else 25)
    return ceil(quarters * (1 << sf) * 1_000_000 / (4 * bandwidths[bandwidth_hz]))


def TelemetryPlan_Get(profile, *, landed=False, preflight=False, control_ack_hz=0, **phy):
    if profile not in ('S', 'H'):
        raise ValueError('telemetry_profile_unsupported')
    rates = {'FLIGHT_DATA': 0 if landed else 5 if profile == 'S' else 2,
             'POSITION': 1 if landed or profile == 'S' else 0.5,
             'HEALTH': 0.2 if landed else 0.5}
    sizes = {'FLIGHT_DATA': 56, 'POSITION': 28, 'HEALTH': 16}
    if preflight:
        rates = {'PREFLIGHT_DATA': 1, 'CAPABILITY': 0.5, 'PREFLIGHT_STATUS': 0.5,
                 'POSITION': 1 if profile == 'S' else 0.5, 'HEALTH': 0.5}
        sizes.update(PREFLIGHT_DATA=32, CAPABILITY=24, PREFLIGHT_STATUS=15)
    if type(control_ack_hz) not in (int, float) or not 0 <= control_ack_hz <= 1:
        raise ValueError('telemetry_control_budget_invalid')
    if control_ack_hz:
        rates['COMMAND_ACK'] = control_ack_hz; sizes['COMMAND_ACK'] = 16
    rows = [{"message": name, "length": sizes[name], "hz": hz,
             "airtime_us": LoraAirtimeUs_Compute(sizes[name], **phy)} for name, hz in rates.items()]
    tx = sum(row['hz'] * row['airtime_us'] for row in rows) / 1e6
    # Same max(120ms, ceil(ToA(64B))+4ms) as the physical half-duplex owner.
    grant_us = max(120000, ceil(LoraAirtimeUs_Compute(64, **phy) / 1000) * 1000 + 4000)
    half_duplex = preflight or profile == 'H'
    occupancy = tx + (grant_us * sum(rates.values()) / 1e6 if half_duplex else 0)
    return {'profile': profile, 'rows': rows, 'tx_fraction': tx,
            'scheduler_fraction': occupancy, 'half_duplex_rx_grant_us': grant_us,
            'event_airtime_us': LoraAirtimeUs_Compute(32, **phy),
            'event_opportunities_per_second': max(0, 1-occupancy) * 1e6 /
                (LoraAirtimeUs_Compute(32, **phy) + 4000 + (grant_us if half_duplex else 0)),
            'transient_limits': {'pending_events':16, 'broadcasts_per_event':3,
                                 'event_ttl_s':30, 'maximum_non_start_ack_hz':1},
            'hardware_measured': False}
