"""Documented Ebyte module output points, separate from SX128x chip drive.

Only the nominal PA output point is documented; no linear ladder is inferred.
The AIR PHY remains the existing shared project snapshot.
"""
from dataclasses import dataclass, replace

RADIO_PLUGIN = "silverstar.device.telemetry.sx1281"
LEGACY_MODULE = "e28_2g4m12sx"
FRONTEND_RESOURCES = frozenset({"radio_rx_en", "radio_tx_en"})


@dataclass(frozen=True, slots=True)
class RadioVariantCapability:
    model: str
    nominal_output_dbm: int
    chip_drive_dbm: int
    external_frontend: bool
    manual_id: int
    maximum_spi_clock_hz: int = 10_000_000
    hardware_status: str = "hardware_unverified"


EBYTE_VARIANTS = {
    "e28_2g4m12sx": RadioVariantCapability("E28-2G4M12SX", 12, 12, False, 2049, hardware_status="existing_field_profile"),
    "e28_2g4m12s": RadioVariantCapability("E28-2G4M12S", 12, 12, False, 285),
    "e28_2g4m20s": RadioVariantCapability("E28-2G4M20S", 20, -2, True, 304),
    "e28_2g4m20sx": RadioVariantCapability("E28-2G4M20SX", 20, -2, True, 2217),
    "e28_2g4m27s": RadioVariantCapability("E28-2G4M27S", 27, 0, True, 527),
    "e28_2g4m27sx": RadioVariantCapability("E28-2G4M27SX", 27, 0, True, 1920),
}


def RadioVariant_Get(module_id: str, power_dbm: int) -> RadioVariantCapability:
    capability = EBYTE_VARIANTS.get(module_id)
    if capability is None:
        raise ValueError("Unknown Ebyte radio module variant")
    if type(power_dbm) is not int or power_dbm != capability.nominal_output_dbm:
        raise ValueError(f"{capability.model} supports only documented nominal {capability.nominal_output_dbm} dBm output")
    return capability


def FlightRadioConfiguration_Get(model, instance):
    """Missing per-instance fields retain the original active/global power contract."""
    if instance.plugin == "silverstar.device.telemetry.nrf24l01p":
        return instance.module_variant or "nrf24l01p", instance.tx_power_dbm if instance.tx_power_dbm is not None else 0
    module = instance.module_variant or LEGACY_MODULE
    power = instance.tx_power_dbm
    if power is None:
        power = model.flight_tx_power_dbm
    return module, power


def FlightRadioConfiguration_Apply(model, instance_id: str, module_id: str, power_dbm: int):
    """GUI/backend edit contract: return a copy and retain unrelated instances."""
    from copy import deepcopy
    selected = model.DeviceInstance_Get(instance_id)
    if selected is not None and selected.plugin == "silverstar.device.telemetry.nrf24l01p":
        if module_id != "nrf24l01p" or type(power_dbm) is not int or power_dbm not in (-18, -12, -6, 0):
            raise ValueError("NRF24 module or power is unsupported")
        candidate = deepcopy(model)
        candidate.device_instances = [replace(instance, module_variant=module_id, tx_power_dbm=power_dbm)
            if instance.instance_id == instance_id else instance for instance in candidate.device_instances]
        return candidate
    capability = RadioVariant_Get(module_id, power_dbm)
    if selected is None or selected.plugin != RADIO_PLUGIN:
        raise ValueError("Flight radio instance is unavailable")
    candidate = deepcopy(model)
    candidate.device_instances = [replace(instance, module_variant=module_id, tx_power_dbm=power_dbm)
        if instance.instance_id == instance_id else instance for instance in candidate.device_instances]
    if not capability.external_frontend:
        for requirement in FRONTEND_RESOURCES:
            candidate.resource_assignments.pop(instance_id + ":" + requirement, None)
    return candidate


def RadioManifest_Resolve(manifest, instance):
    if manifest.component_id == "silverstar.device.telemetry.nrf24l01p":
        if instance.module_variant not in ("", "nrf24l01p") or (
                instance.tx_power_dbm is not None and
                (type(instance.tx_power_dbm) is not int or instance.tx_power_dbm not in (-18, -12, -6, 0))):
            raise ValueError("NRF24 module or power is unsupported")
        return manifest
    if manifest.component_id != RADIO_PLUGIN:
        if instance.module_variant or instance.tx_power_dbm is not None:
            raise ValueError("Radio module/power settings require an Ebyte SX128x instance")
        return manifest
    capability = EBYTE_VARIANTS.get(instance.module_variant or LEGACY_MODULE)
    if capability is None:
        raise ValueError("Unknown Ebyte radio module variant")
    declared = manifest.metadata.get("radio_variant_capabilities", {}).get(instance.module_variant or LEGACY_MODULE)
    if declared is None or (declared["chip_drive_dbm"], declared["external_frontend"], declared["maximum_spi_clock_hz"]) != (capability.chip_drive_dbm, capability.external_frontend, capability.maximum_spi_clock_hz):
        raise ValueError("Ebyte manifest capability disagrees with the trusted backend")
    requirements = tuple(
        replace(item, required=True) if item.name in FRONTEND_RESOURCES else item
        for item in manifest.resource_requirements
        if capability.external_frontend or item.name not in FRONTEND_RESOURCES
    )
    binding = manifest.instance_resource_binding
    binding = replace(binding, fields=tuple(field for field in binding.fields
        if capability.external_frontend or field.requirement not in FRONTEND_RESOURCES))
    return replace(manifest, resource_requirements=requirements, instance_resource_binding=binding)


def RadioInstanceMacros_Render(configurations) -> str:
    capabilities = [RadioVariant_Get(module, power) for module, power in configurations]
    if not capabilities or all(module == LEGACY_MODULE and power == 12 for module, power in configurations):
        return ""
    expression = str(capabilities[-1].chip_drive_dbm)
    for index in range(len(capabilities) - 2, -1, -1):
        expression = f"((instance) == {index}U ? {capabilities[index].chip_drive_dbm} : {expression})"
    return ("/* Module output is distinct from chip drive; new variants are hardware unverified. */\n"
            f"#define AIR_LINK_INSTANCE_CHIP_TX_POWER_DBM(instance) {expression}\n")
