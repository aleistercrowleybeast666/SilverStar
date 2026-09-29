# MCU platform layers (Round 4)

Firmware source ownership now has four layers:

1. `silverstar.platform.api` owns the MCU-independent `Platform/Inc` API.
2. `silverstar.mcu_family.stm32f4` owns the STM32F4 Platform implementation, HAL/CMSIS, family resource backends and module providers.
3. `silverstar.mcu.stm32f407vet6` owns the exact part match, Cortex-M4F flags, startup, linker script and F407 target headers. Its effective Platform contract composes the family contract with exact match and build target fields.
4. `silverstar.board.silverstar_0_5` owns the SS0.5 PCB hardware snapshot, connection map and CubeMX-generated board files.

The project records its selected exact MCU and family backend separately. Validation rejects a mismatch. Source graph resolution adds the selected family sources once, while only the exact MCU activates the composed provider contract. Ground generation obtains include paths from that graph; it does not append an STM32F4 path.

The STM32F407VET6 Flight reference still builds. `silverstar.mcu_family.stm32f1` now owns the F1 HAL/CMSIS and UART, SPI, GPIO/EXTI and SysTick backends. `silverstar.mcu.stm32f103c8t6` owns the exact Cortex-M3 software-float flags, startup, linker and official 64 KiB Flash / 20 KiB SRAM limits. `silverstar.board.ground_station_0_5` owns the GS_SS1 PCB IOC and hardware snapshot. The generated F103 Ground UART bridge compiles and links with ARM GCC, with MAP, size and per-source stack-usage output. GS_SS1's legacy hardware result validates its PCB topology; it does not validate the newly generated SilverStar Ground Core on hardware.
