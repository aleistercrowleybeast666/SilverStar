"""NRF24 one-pair contract. Logical MTU is independent of physical payload."""
import re

NRF24_PLUGIN = "silverstar.device.telemetry.nrf24l01p"


def Nrf24Parameters_Validate(parameters):
    if not isinstance(parameters, dict) or set(parameters) != {"data_rate_kbps", "address", "retry_delay_us", "retry_count"}:
        raise ValueError("NRF24 parameters require data rate, 5-byte address and bounded retries")
    rate, address = parameters["data_rate_kbps"], parameters["address"]
    delay, retries = parameters["retry_delay_us"], parameters["retry_count"]
    if type(rate) is not int or rate not in (250, 1000, 2000):
        raise ValueError("NRF24 data rate must be 250, 1000 or 2000 kbps")
    if not isinstance(address, str) or not re.fullmatch(r"[0-9A-Fa-f]{10}", address) or address.upper() in {"0000000000", "FFFFFFFFFF"}:
        raise ValueError("NRF24 address must contain exactly five nontrivial hexadecimal bytes")
    if type(delay) is not int or delay not in range(500, 4001, 250) or type(retries) is not int or not 0 <= retries <= 15:
        raise ValueError("NRF24 retry delay must be 500..4000 us in 250 us steps; retries 0..15")
    return parameters


def Nrf24Link_Validate(link):
    parameters = Nrf24Parameters_Validate(link.nrf24)
    if (link.radio_family, link.radio_technology, link.phy_mode) != ("nrf24", "esb", "esb"):
        raise ValueError("NRF24 requires its ESB family and PHY")
    if type(link.frequency_hz) is not int or not 2400000000 <= link.frequency_hz <= 2525000000 or link.frequency_hz % 1000000:
        raise ValueError("NRF24 frequency must map to integer channel 0..125")
    if not link.crc_enabled or type(link.packet_mtu) is not int or not 50 <= link.packet_mtu <= 61:
        raise ValueError("NRF24 requires CRC16 and logical MTU 50..61 for unchanged AIR M0")
    return parameters


def Nrf24Header_Render(model, target):
    from silverstar_fccg.project.radio_variants import FlightRadioConfiguration_Get
    parameters = Nrf24Link_Validate(model.air_link)
    power = model.ground_target.tx_power_dbm
    if target == "flight":
        instance = model.DeviceInstance_Get(model.air_link.flight_radio_instance)
        if instance is None or instance.plugin != NRF24_PLUGIN:
            raise ValueError("NRF24 Flight owner is unavailable")
        _module, power = FlightRadioConfiguration_Get(model, instance)
    if type(power) is not int or power not in (-18, -12, -6, 0):
        raise ValueError("NRF24 power must be -18, -12, -6 or 0 dBm")
    rf_setup = {250: 0x20, 1000: 0, 2000: 8}[parameters["data_rate_kbps"]] | ((power + 18) // 6 << 1)
    # Address text is written in SPI byte order, identical at both endpoints.
    address = ", ".join("0x" + parameters["address"][i:i+2].upper() + "U" for i in range(0, 10, 2))
    retry = ((parameters["retry_delay_us"] // 250 - 1) << 4) | parameters["retry_count"]
    return f'''#ifndef __AIR_LINK_CONFIG_H
#define __AIR_LINK_CONFIG_H
/* NRF24 physical MTU 32; fragment v1 logical MTU. HARDWARE_UNVERIFIED. */
#define AIR_LINK_NRF24_CHANNEL {(model.air_link.frequency_hz - 2400000000) // 1000000}U
#define AIR_LINK_NRF24_DATA_RATE_KBPS {parameters["data_rate_kbps"]}U
#define AIR_LINK_NRF24_RF_SETUP 0x{rf_setup:02X}U
#define AIR_LINK_NRF24_ADDRESS_BYTES {{{address}}}
#define AIR_LINK_NRF24_RETRY_SETUP 0x{retry:02X}U
#define AIR_LINK_PACKET_MTU {model.air_link.packet_mtu}U
#endif /* __AIR_LINK_CONFIG_H */
'''
