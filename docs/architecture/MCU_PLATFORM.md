# MCU platform layers (Round 4)

Firmware source ownership now has four layers:

1. `silverstar.platform.api` owns the MCU-independent `Platform/Inc` API.
2. `silverstar.mcu_family.stm32f4` owns the STM32F4 Platform implementation, HAL/CMSIS, family resource backends and module providers.
3. `silverstar.mcu.stm32f407vet6` owns the exact part match, Cortex-M4F flags, startup, linker script and F407 target headers. Its effective Platform contract composes the family contract with exact match and build target fields.
4. `silverstar.board.silverstar_0_5` owns the SS0.5 PCB hardware snapshot, connection map and CubeMX-generated board files.

The project records its selected exact MCU and family backend separately. Validation rejects a mismatch. Source graph resolution adds the selected family sources once, while only the exact MCU activates the composed provider contract. Ground generation obtains include paths from that graph; it does not append an STM32F4 path.

The current proven build remains the STM32F407VET6 Flight reference. STM32F103C8T6 and the GS_SS1 PCB will use a distinct STM32F1 family backend and exact part description. Their software and board evidence must be checked separately; the GS_SS1 legacy hardware result does not validate the new SilverStar Ground Core.
