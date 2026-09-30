# SilverStar 0.1.0 field-test software reference

The six pre-existing files were verified against the hashes below and copied without rebuilding to the Git-ignored durable local archive `release-evidence/round5-frozen-4a1f3db/`. Its `archive-manifest.json` records source and destination paths, byte counts, and SHA-256 values. This archive is local evidence, not a release package; see [the blank qualification record](FIELD_QUALIFICATION_RECORD_TEMPLATE.md) for a future controlled bench session.

The Round5 qualification wording below is a historical software-candidate statement. A later [source-only checker audit](../FCCG/POWER_OF_TEN_SUPPLEMENTAL_REPAIR.md) exposed open Rule 5 assertion-coverage findings. Neither that audit nor a fresh local build changes the six frozen identities or supplies missing physical evidence. Current field readiness remains **NO** pending review and bench evidence.

**Qualification state: SOFTWARE FIELD CANDIDATE READY; HARDWARE ACTIONS PENDING.** This is not `FIELD TEST READY`, a public release, or authorization to use live deployment loads. The hashes below identify the fresh FCCG project generated from the Round 5 repository state and ARM GCC 14.3.1. The ignored local candidate is `.work/round5/final/Round5_Field_Qualification/`; `.work/round5/final-artifacts.json` contains the machine-readable file sizes and exact-MCU BuildAudit output. Copy the chosen firmware/project/decoder together to a durable user project before field work; `.work/` is disposable.

## Frozen software files

| File | SHA-256 |
| --- | --- |
| `SilverStar.ssproject` | `cead735fe445f997c3b1b1113715b4344cdc61e517137d01be41ee4d8b9bbad7` |
| `Round5_Field_Qualification.ssdecoder` | `5de25f2c2436af09f63fd3518024a88737c6719e249f8f539b10f00da1a8b43f` |
| Flight `SilverStar_0_1_0.elf` | `2c9e2442c3676d8466ce13db82658bf53bc5f2127f73e2a402a6ec4376734dce` |
| Flight `SilverStar_0_1_0.bin` | `623851b3cd4d39932fd598b0c90276c887e8494f1d99fbf1d636a5e207a9a903` |
| Ground `ground.elf` | `115e3cc7e4e7d6cb17b625b5616e4643f12557e7785d220b3bd0d5810b3ef596` |
| Ground `ground.bin` | `9f140e72b6faadcc9f19b58e4c6fe1c6aab84f26387baa74ca3b17dc1a0b5c45` |

Re-run `python tools/round5_reference.py generate --project-root .work/round5/<new-empty-directory>/Round5_Field_Qualification` for a new isolated project, build both targets, then run `python tools/round5_reference.py record --project-root <that-root>`. Existing generated firmware sources are project-owned and are never silently replaced by this tool. A different hash requires a new reviewed reference record.

## Selected configuration

| Item | Frozen selection |
| --- | --- |
| Product | SilverStar 0.1.0; project format 14 |
| Flight hardware | SS0.5 Flight PCB; STM32F407VET6, 168 MHz |
| Ground hardware | Ground Station 0.5 / GS_SS1 reference PCB; STM32F103C8T6, 72 MHz |
| Flight devices | JY901B `imu0`; NEO-M9N `gnss0`; SDIO/FatFs `storage0`; maintenance UART; E28-2G4M12SX / SX1281 `telemetry0` |
| Ground devices | E28-2G4M12SX / SX1281 `radio0`; USART1 UART PC interface, 230400 baud, 8N1 |
| AIR and PHY | AIR M0 over SX128x LoRa; 2,473,000,000 Hz; SF10; 800 kHz bandwidth; CR 4/5; 16-symbol preamble; explicit header; CRC on; normal IQ; packet MTU 61 bytes; endpoint TX power 12 dBm each |
| Ground/PC wire | GSP binary over UART; GSHC uses serial backend |
| Flight log | SSLOG 0.0 and exact root `.ssdecoder`; canonical log source is the TF/SD card |
| Navigation | JY901B raw IMU ODR 200 Hz; INS Coning2/Sculling2 aggregation 2; effective propagation 100 Hz; KF6 selected; configured maximum measurement delay 270 ms and maximum replay work 27 steps (history requirement 61 / capacity 144). Values come from `InertialRatePlan_Resolve` on the frozen `.ssproject`; physical ODR and runtime replay remain bench checks. All algorithm parameters are frozen in the hashed `.ssproject` and generated config; an actual mission snapshot still needs TF readback. ESKF15 requires separate smoke evidence if evaluated. |
| Alignment | Vector Constraints, Gravity plus configured +X reference direction at 90° true-north azimuth; physical orientation must be checked on the bench before use. Magnetic constraint is not selected. |
| Magnetometer | No dedicated magnetometer plugin or magnetic alignment constraint is selected. JY901B declares an internal field capability, but its raw field logging is disabled in this project. GSHC magnetometer calibration is not physically qualified by this reference build. |
| Calibration generation | **HARDWARE ACTION REQUIRED:** record actual IMU calibration generation/hash and any selected physical magnetometer generation after board readback. No generation is inferred from a software build. |

## Static candidate evidence

| Target | Exact-MCU memory | Stack evidence |
| --- | --- | --- |
| F407 Flight | Flash 312,776 / 524,288 B; SRAM 101,280 / 131,072 B; CCMRAM 55,432 / 65,536 B | 152 GCC `.su` files; largest single frame 2,032 B; task stack report is a separate required PASS |
| F103 Ground UART | Flash 20,860 / 65,536 B; SRAM 14,128 / 20,480 B | 37 GCC `.su` files; largest single frame 296 B |

These are build and static-resource identities, not proof that either new firmware image has run on its board. The legacy GS_SS1 PCB topology is a hardware-validated reference; the new SilverStar Ground Core awaits its own board test. F407 target timing and F103 service-latency measurements are pending; observed maxima would not by themselves establish formal WCET. USB CDC and unselected new sensor devices remain hardware-unverified.
