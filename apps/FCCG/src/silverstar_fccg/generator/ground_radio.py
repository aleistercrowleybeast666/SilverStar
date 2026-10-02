"""Ground-only radio/LED generation; no changes to AIR M0 or Flight policy."""
import re

from silverstar_fccg.project.model import GroundRadioConfigurations_Get


def GroundRadioConfig_Render(ground) -> str:
    radios = GroundRadioConfigurations_Get(ground)
    identities = [radio.instance_id for radio in radios]
    if not 1 <= len(radios) <= 4 or len(set(identities)) != len(radios):
        raise ValueError("Ground requires 1–4 distinct radio instances")
    if ground.active_radio_instance not in identities:
        raise ValueError("Ground initial active radio is not configured")
    if any(radio.plugin != "silverstar.device.telemetry.sx1281" for radio in radios):
        raise ValueError("Ground runtime requires the existing SX1281 driver")
    if any(radio.module_variant != "e28_2g4m12sx" or
           isinstance(radio.tx_power_dbm, bool) or not isinstance(radio.tx_power_dbm, int) or
           radio.tx_power_dbm != 12 for radio in radios):
        raise ValueError("Ground renderer requires the validated E28-2G4M12SX / 12 dBm configuration")
    pulse = getattr(ground, "activity_led_pulse_ms", 40)
    if isinstance(pulse, bool) or not isinstance(pulse, int) or not 1 <= pulse <= 200:
        raise ValueError("Ground activity LED pulse must be 1–200 ms")
    resources = {resource.resource_id: resource for resource in ground.hardware.resources}
    values = []
    for direction in ("tx", "rx"):
        identity = getattr(ground, direction + "_led_resource", "")
        polarity = getattr(ground, direction + "_led_active_high", False)
        if not isinstance(identity, str) or not isinstance(polarity, bool):
            raise ValueError("Ground LED resource/polarity types are invalid")
        index = 96
        if identity:
            resource = resources.get(identity)
            if resource is None or resource.kind != "gpio_output":
                raise ValueError("Ground LED must bind a configured GPIO output")
            index = resource.metadata.get("fixed_logical_index", resource.metadata.get("logical_index"))
            if index is None:
                token = str(resource.metadata.get("c_id", identity))
                match = re.fullmatch(r"PLATFORM_GPIO_(\d+)", token)
                cast = re.fullmatch(r"\(\(PlatformGpioId\)(\d+)U\)", token)
                index = int((match or cast)[1]) if match or cast else None
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 96:
                raise ValueError("Ground LED logical GPIO index is invalid")
        values.append((index, int(polarity)))
    if values[0][0] == values[1][0] != 96 and values[0][1] != values[1][1]:
        raise ValueError("Shared TX/RX LED requires the same active polarity")
    owner = identities.index(ground.active_radio_instance)
    return f"""#ifndef __GROUND_RADIO_CONFIG_H
#define __GROUND_RADIO_CONFIG_H
#include "platform_gpio.h"

/* Ordered cold replacement only; no aggregation or command replay. */
#define GROUND_RADIO_INITIAL_INSTANCE {owner}U
#define GROUND_RADIO_FAILOVER_HOLD_MS 250U
#define GROUND_ACTIVITY_ENABLED {int(any(index != 96 for index, _ in values))}U
#define GROUND_ACTIVITY_TX_GPIO ((PlatformGpioId){values[0][0]}U)
#define GROUND_ACTIVITY_RX_GPIO ((PlatformGpioId){values[1][0]}U)
#define GROUND_ACTIVITY_TX_ACTIVE_HIGH {values[0][1]}U
#define GROUND_ACTIVITY_RX_ACTIVE_HIGH {values[1][1]}U
#define GROUND_ACTIVITY_PULSE_MS {pulse}U
#endif /* __GROUND_RADIO_CONFIG_H */
"""


def GroundRadioAirHeader_Render(ground, legacy_header: str) -> str:
    GroundRadioConfig_Render(ground)  # Validate values before inserting C tokens.
    radios = GroundRadioConfigurations_Get(ground)
    if len(radios) == 1:
        return legacy_header  # Single-radio PHY/power/HAL capacity remain exact.
    expression = str(radios[-1].tx_power_dbm)
    for index in range(len(radios) - 2, -1, -1):
        expression = f"((instance) == {index}U ? {radios[index].tx_power_dbm} : {expression})"
    return legacy_header.replace("#endif /* __AIR_LINK_CONFIG_H */",
        "/* Ground multi-instance scratch capacity and configured per-port power. */\n"
        "#define AIR_LINK_HAL_BUFFER_SIZE 260U\n"
        f"#define AIR_LINK_INSTANCE_TX_POWER_DBM(instance) {expression}\n"
        "#endif /* __AIR_LINK_CONFIG_H */")
