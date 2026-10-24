"""Deliberately narrow E32-400M20S experimental profile; no SX128x defaults."""
SX1278_PLUGIN = "silverstar.device.telemetry.sx1278"
SX1278_MODULE = "e32_400m20s"


def Sx1278Module_Validate(module, power):
    if module != SX1278_MODULE or type(power) is not int or power != 17:
        raise ValueError("Experimental E32-400M20S requires its explicit module and +17 dBm chip setting")


def Sx1278Link_Validate(link):
    expected = {"radio_family": "sx127x", "radio_technology": "lora", "phy_mode": "lora",
                "frequency_hz": 433_000_000, "bandwidth_hz": 125_000, "spreading_factor": 7,
                "coding_rate": "4/5", "preamble_symbols": 16, "header_mode": "explicit",
                "crc_enabled": True, "iq_mode": "normal", "packet_mtu": 61}
    if any(type(getattr(link, field)) is not type(value) or getattr(link, field) != value
           for field, value in expected.items()):
        raise ValueError("SX1278 experimental PHY is 433 MHz/SF7/BW125/4-5/preamble16/explicit/CRC/normal-IQ/MTU61")
    if getattr(link, "nrf24", None) is not None:
        raise ValueError("SX1278 cannot retain NRF24 parameters")


def Sx1278Model_Validate(model):
    from silverstar_fccg.project.model import GroundRadioConfigurations_Get
    Sx1278Link_Validate(model.air_link)
    radios = [item for item in model.device_instances if item.plugin == SX1278_PLUGIN]
    if len(radios) != 1 or radios[0].instance_id != model.air_link.flight_radio_instance:
        raise ValueError("SX1278 experimental profile requires one explicit Flight owner")
    Sx1278Module_Validate(radios[0].module_variant, radios[0].tx_power_dbm)
    if model.ground_target.enabled:
        ground = GroundRadioConfigurations_Get(model.ground_target)
        if len(ground) != 1 or ground[0].plugin != SX1278_PLUGIN:
            raise ValueError("SX1278 requires exactly one matching Ground radio")
        Sx1278Module_Validate(ground[0].module_variant, ground[0].tx_power_dbm)


def Sx1278Header_Render(model, target="flight"):
    if target not in ("flight", "ground"):
        raise ValueError("SX1278 target must be Flight or Ground")
    Sx1278Model_Validate(model)
    return '''#ifndef __AIR_LINK_CONFIG_H
#define __AIR_LINK_CONFIG_H
/* Experimental E32-400M20S. 3.3 V only. HARDWARE_UNVERIFIED. */
#define AIR_LINK_FREQUENCY_HZ 433000000UL
#define AIR_LINK_TX_POWER_DBM 17
#define AIR_LINK_SPREADING_FACTOR 7U
#define AIR_LINK_BANDWIDTH_HZ 125000UL
#define AIR_LINK_CODING_RATE_DENOMINATOR 5U
#define AIR_LINK_PREAMBLE_SYMBOLS 16U
#define AIR_LINK_PACKET_MTU 61U
#endif /* __AIR_LINK_CONFIG_H */
'''
