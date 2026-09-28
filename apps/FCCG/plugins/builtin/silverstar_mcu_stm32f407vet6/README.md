# STM32F407VET6

Declarative SilverStar_FCCG builtin `mcu` plugin.

Reference baseline: `main` at `cc0b377ded690556d037a412a55f87fe334c42d0`. Reference-derived files retain the recorded snapshot provenance; FCCG-owned files are replayed from their declared workspace source-of-truth and identified separately in `metadata.source_origins`. Plugin payload is data and is never executed.

This MCU/Platform plugin declares automatic CubeMX matching, the Platform resource-binding ABI, supported I2C/PWM backends, and a reserved Classic CAN backend. It enforces CubeMX 6.15.0, STM32Cube FW_F4 V1.28.3, and plugin-owned HAL/CMSIS as one exact source policy. Production validation remains limited to STM32F407VET6/SS0.5; software support does not claim electrical verification.
