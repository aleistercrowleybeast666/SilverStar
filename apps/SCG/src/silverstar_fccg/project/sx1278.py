"""Narrow Ebyte SX1278 module profiles; no inferred PA or SX128x settings."""
from copy import deepcopy
from dataclasses import replace

SX1278_PLUGIN = "silverstar.device.telemetry.sx1278"
SX1278_MODULE = "e32_400m20s"
SX1278_DIO4_MODULE = "e19_433m20s2"


def Sx1278Module_Validate(module, power):
    if module not in (SX1278_MODULE, SX1278_DIO4_MODULE) or type(power) is not int or power != 17:
        raise ValueError("Experimental SX1278 requires a registered module and +17 dBm chip setting")


def Sx1278Manifest_Resolve(manifest, module, power):
    Sx1278Module_Validate(module, power)
    if module == SX1278_MODULE:
        return manifest
    removed = {'radio_rx_en', 'radio_tx_en'}
    requirements = []
    for requirement in manifest.resource_requirements:
        if requirement.name in removed:
            continue
        if requirement.name == 'radio_bus':
            constraints = deepcopy(requirement.constraints)
            constraints['spi']['maximum_clock_hz'] = 1_000_000
            requirement = replace(requirement, constraints=constraints)
        requirements.append(requirement)
    metadata = deepcopy(manifest.metadata)
    metadata['sx1278_module_profile'] = deepcopy(metadata['sx1278_module_profiles'][module])
    metadata['instance_resource_binding']['fields'] = [
        field for field in metadata['instance_resource_binding']['fields']
        if field['requirement'] not in removed]
    for descriptor in metadata.get('device_descriptors', ()):
        descriptor['physical_device_id'] = 'PROJECT_PHYSICAL_DEVICE_ID_E19_SX1278'
        descriptor['name_hash'] = '0xE1943320UL'
    binding = replace(manifest.instance_resource_binding, fields=tuple(
        field for field in manifest.instance_resource_binding.fields if field.requirement not in removed))
    return replace(manifest, resource_requirements=tuple(requirements), instance_resource_binding=binding,
        physical_device=replace(manifest.physical_device, model='E19-433M20S2'), metadata=metadata)


def Sx1278LinkDefaults_Get():
    """The single supported experimental PHY, shared by validation and editors."""
    return {"radio_family": "sx127x", "radio_technology": "lora", "phy_mode": "lora",
                "frequency_hz": 433_000_000, "bandwidth_hz": 125_000, "spreading_factor": 7,
                "coding_rate": "4/5", "preamble_symbols": 16, "header_mode": "explicit",
                "crc_enabled": True, "iq_mode": "normal", "packet_mtu": 61}


def Sx1278Link_Validate(link):
    expected = Sx1278LinkDefaults_Get()
    if any(type(getattr(link, field)) is not type(value) or getattr(link, field) != value
           for field, value in expected.items()):
        raise ValueError("SX1278 experimental PHY is 433 MHz/SF7/BW125/4-5/preamble16/explicit/CRC/normal-IQ/MTU61")
    if getattr(link, "nrf24", None) is not None:
        raise ValueError("SX1278 cannot retain NRF24 parameters")


def Sx1278Model_Validate(model, target="flight"):
    from silverstar_fccg.project.model import GroundRadioConfigurations_Get
    Sx1278Link_Validate(model.air_link)
    if target in ("flight", "all"):
        radios = [item for item in model.device_instances if item.plugin == SX1278_PLUGIN]
        if len(radios) != 1 or radios[0].instance_id != model.air_link.flight_radio_instance:
            raise ValueError("SX1278 experimental profile requires one explicit Flight owner")
        Sx1278Module_Validate(radios[0].module_variant, radios[0].tx_power_dbm)
    if target in ("ground", "all"):
        ground = GroundRadioConfigurations_Get(model.ground_target)
        if len(ground) != 1 or ground[0].plugin != SX1278_PLUGIN:
            raise ValueError("SX1278 requires exactly one matching Ground radio")
        Sx1278Module_Validate(ground[0].module_variant, ground[0].tx_power_dbm)


def Sx1278Header_Render(model, target="flight"):
    if target not in ("flight", "ground"):
        raise ValueError("SX1278 target must be Flight or Ground")
    Sx1278Model_Validate(model, target)
    module = (model.DeviceInstance_Get(model.air_link.flight_radio_instance).module_variant
              if target == 'flight' else model.ground_target.module_variant)
    return f'''#ifndef __AIR_LINK_CONFIG_H
#define __AIR_LINK_CONFIG_H
/* Experimental {module}. 3.3 V only. HARDWARE_UNVERIFIED. */
#define AIR_LINK_SX1278_DIO4_FRONTEND {int(module == SX1278_DIO4_MODULE)}U
#define AIR_LINK_FREQUENCY_HZ 433000000UL
#define AIR_LINK_TX_POWER_DBM 17
#define AIR_LINK_SPREADING_FACTOR 7U
#define AIR_LINK_BANDWIDTH_HZ 125000UL
#define AIR_LINK_CODING_RATE_DENOMINATOR 5U
#define AIR_LINK_PREAMBLE_SYMBOLS 16U
#define AIR_LINK_PACKET_MTU 61U
#endif /* __AIR_LINK_CONFIG_H */
'''
