# SilverStar 0.1.0 second-round multi-target report

This is a pre-release implementation report. No public 0.1.0 release has been made.

## Baseline and reference

The clean monorepo baseline was 2763bb8f6a92973f21c33babd3a0f57a22cbc783 at product version 0.1.0. GS_SS1 main was checked read-only at 7fe0f61142c7360f7dbae0ac0000036315631320. Its formal UART↔GSP↔radio↔AIR bridge was the behavior reference. No GS_SS1 hardware tree, startup, BSP, Makefile, build output, or repository history was imported.

## Device names and variants

The malformed “路 SPI” labels were removed. SPI is an interface, not a physical chip model; BMI088_SYNC400 is an operating profile, not a chip model. BMI088's four I²C/SPI and raw200/sync400 combinations now resolve from one BMI088 plugin. BMI323, ICM42605, ICM42688P, ICM45686, LSM6DSV320X, LSM6DSV32X, MPU6000, MPU6500 and MPU9250 duplicate interface packages were also merged into their physical-chip plugins. The unrelated malformed SD/TF Card label was corrected. Internal Sensor register bus and UBX support libraries had a false duplicate physical identity; they are now internal Core support components. No chip model was renamed into another.

The manifest's device_variants mapping contains only variant IDs, interface/profile identity, and limited overlays for differing resources, sources, includes, defines, display names and initialization metadata. Variant overlays cannot change physical_device. The project stores plugin ID, interface and profile per Device instance. The project catalog resolves each instance and unions shared source files without duplication. Project format is 13; no public format-12 compatibility commitment exists. AIR M0, SSLOG 0.0, decoder, navigation, FreeRTOS, CubeMX package, board and MCU identities were not version-bumped.

## Targets and AIR Link

The existing Flight configuration and generator remain the Flight Controller target. Ground has independent MCU/board/CubeMX hardware, radio resource assignments, PC interface and build options. The project-owned AIR Link provides one AIR profile and SX128x LoRa PHY snapshot to both outputs. Readiness validates radio family, PHY, frequency range, MTU, Ground radio resources and PC interface before generation. Current verified M12 parameters are constrained to the known 2473 MHz, SF10, 800 kHz, CR 4/5 profile. The radio manifest separates SX128x family data from the verified E28-2G4M12SX module variant; no M20/M27 parameters were guessed.

The FCCG navigation adds AIR Link and Ground Station pages. The Build page offers Generate Flight Controller, Generate Ground Station, and Generate All. Outputs are isolated FlightController/ and GroundStation/ directories below the user-selected project root, with one SilverStar.ssproject. Repeated generation checks file content and shared link consistency.

## Ground firmware and PC interface

The Ground Core uses the GS_SS1 GSP parser/CRC behavior and a small transparent AIR bridge with bounded queues, ACK, GS_STATUS, radio counters and RSSI/SNR forwarding. It reuses the existing SX1281 driver and has a Ground adapter instead of copying a Flight driver. Ground does not interpret AIR commands or Flight state.

UART PC Interface requires an inventory UART with matching baud, RX/TX and 8N1. USB CDC requires CubeMX USB Device CDC inventory and generated callback/middleware; both feed the same GSP C core through PcByteStream_Read/Write. The MCU platform plugin now includes the matching STM32Cube FW_F4 V1.28.3 HAL PCD/USB LL sources; CubeMX retains ownership of USB Device middleware and descriptors. GSHC continues to use pyserial for either COM-port type. contracts/gsp contains the shared wire definition and golden vectors used by Ground C and GSHC Python. The GSP wire format remains unchanged.

## Validation and limits

Formal tests cover physical-chip variant resolution, per-instance interface/profile persistence, AIR compatibility failures, UART/USB capability gates, target output separation and deterministic rendering, shared GSP C/Python vectors, and existing Flight-focused behavior.

- Round 2 target and variant tests: 7 passed.
- Existing sensor generation tests: 25 cases plus 7 Round 2 target cases passed together (32 passed); sensor library tests: 39 passed.
- FCCG hardware/generator/target focused run: 17 passed. FCCG GUI smoke: 14 passed, with the new Ground configuration UI test also passing separately.
- GSHC AIR/receive and shared C/Python GSP golden tests: 24 passed.
- Monorepo integration, including documentation links and root launchers: 6 passed.
- ARM GCC Ground UART generation: custom CubeMX snapshot 51 C + 1 assembly, verified SS0.5 board 54 C + 1 assembly; both compiled and linked. Flight-only and Flight+Ground test projects were generated under ignored .work/ directories.
- git diff --check, Python compileall and relevant ruff E4/E7/E9/F checks passed.

No real board, over-the-air radio, or USB host-device behavior was tested. A CubeMX-generated USB CDC project with matching MCU and middleware is still needed for a full ARM USB link and hardware smoke. A standalone .ioc imports as pending hardware; GROUND_CUBEMX_GENERATION_REQUIRED blocks generation until CubeMX supplies application callbacks and, for USB, descriptors. The Flight runtime model preserves its existing field API for the first migration-safe implementation and can be nested after its generation invariants are fully covered.

Next round should validate Flight/Ground on hardware, expand verified board and radio-module profiles only from measured specifications, and then consider device initialization and persistence work separately. No third-round feature was implemented here.
