# SilverStar 0.1.0 Round 4 device and navigation report

This is a pre-release software integration report. No public 0.1.0 release, tag, or firmware hardware acceptance is implied. The Round 4 checkpoint range starts at `8fa581f` (following the Round 3 baseline) and ends at the commit containing this report. Product version remains `0.1.0`; AIR M0 and SSLOG 0.0 wire identities remain independent.

## Platform and target resources

- The [MCU platform](MCU_PLATFORM.md) separates the SilverStar Platform API, STM32F4/STM32F1 family backends, exact STM32F407VET6/STM32F103C8T6 descriptions, and PCB instances. Ground generation derives its sources and include paths from the selected exact MCU and family. The F407 Flight and F103 Ground UART reference projects compile and link with ARM GCC.
- The [PCB workflow](PCB_INSTANCE_WORKFLOW.md) accepts an existing instance, CubeMX IOC, or generated CubeMX project. A saved custom instance is `LOCAL / UNVERIFIED`. The GS_SS1 Ground Station 0.5 topology is a **HARDWARE VALIDATED REFERENCE** based on the legacy board and firmware; the new SilverStar Ground firmware is **SOFTWARE VALIDATED**, awaiting a board smoke test.
- The [target resource plan](TARGET_RESOURCE_PLAN.md) checks official memory regions, actual HCLK, peripheral bindings, inertial ODR/aggregation/effective propagation rate, fixed-lag replay bounds, ELF/MAP/size and `.su` evidence. It forbids linked heap allocation. Structural work bounds pass. Target WCET qualification remains `MEASUREMENT_PENDING`; no unmeasured task/ISR budget is presented as a schedulability PASS. Ground UART throughput has a theoretical 8N1 ceiling and bounded bridge work; an end-to-end offered-load budget still needs target evidence.

## Devices and radio

NEO-M9N startup has a finite supported baud list, passive NMEA/UBX detection, bounded PUBX,41 rescue, an exact M9N UBX identity gate, and bounded polling phases. Module manifests drive validated frequency and endpoint TX-power limits. Startup does not scan arbitrary baudrates or save receiver settings automatically.

| Device | Current software support | Physical validation |
| --- | --- | --- |
| Generic NMEA GNSS | Bounded, read-only GGA/RMC/VTG/GNS parser with checksum and granular measurement capabilities; missing fields are not synthesized | Pending |
| BMP280, BMP390, MS5611 | Manifest variants, bounded startup, shared `SystemBarometer` units, timestamps and health | Pending |
| MMC5983MA, LIS3MDL | Manifest variants, shared `SystemMagnetometer` identity, instance, raw/physical sample and calibration state | Pending |

Generated source graphs, device host tests and ARM compilation provide software evidence; none of these new devices has been promoted to hardware-validated status. Estimator measurement updates require a fresh timestamp and do not reuse an old sample as new evidence.

## Storage, calibration and alignment

- [Persistent Storage](PERSISTENT_STORAGE.md) uses bounded dual-slot objects with generation, sync, readback and CRC verification. The [mission snapshot](MISSION_SNAPSHOT.md) commits bounded binary sections through an inactive bank and a final commit header. It freezes device/algorithm configuration, effective inertial rate, source priority, calibration generations and hashes, AIR/radio profile and alignment configuration. A failed required snapshot blocks START as storage not ready. Final mission status is best effort: post-START storage failure does not stop Flight or Recovery. `trajectory_plan` is explicitly absent for the uncontrolled 0.1.0 sounding rocket.
- GSHC's [Magnetometer Calibration](../GSHC/MAGNETOMETER_CALIBRATION.md) page uses Maintenance Serial for bounded 10–20 Hz raw collection, 3D coverage and ellipsoid fit. Apply validates the instance and physical device ID; Save waits for a confirmed persistent generation after dual-slot write/readback. AIR M0 is unchanged. The page now keeps its point cloud visible while the controls scroll.
- The Navigation Configuration page owns source, calibration, alignment, INS, estimator and resource/rate sections. Vector Constraints binds the existing bounded pair/TRIAD and quaternion-mean solver; External Attitude Source binds JY901B quaternion evidence with explicit yaw-authority handling. A six-axis yaw is not treated as absolute heading. Generated configuration, preflight binding and the mission snapshot retain the selected strategy and constraints.

SSLOG retains its existing record layouts. New version-1 records `0x28` (alignment quality), `0x29` (committed mission snapshot identity) and `0x2A` (per-magnetometer calibration identity) carry evidence for the exact decoder. FLP decodes these records alongside the new sensor measurements and keeps the Project Root / `Log/` / root `.ssdecoder` workflow. The authoritative mission snapshot objects remain on flight storage; a log identity is not a copy of those objects.

## Validation evidence

All generated projects and logs used here are in ignored `.work/` locations. No generated firmware was added as repository source.

| Gate | Result |
| --- | --- |
| F407 Flight ARM Release | Compile/link PASS; text 311,620 B, data 1,136 B, BSS 155,576 B. BuildAudit PASS: Flash 312,760 / 524,288 B; RAM 101,280 / 131,072 B; CCMRAM 55,432 / 65,536 B. 152 `.su` files; static task-stack report PASS. |
| F103 Ground UART ARM | Compile/link PASS; text 20,844 B, data 12 B, BSS 14,112 B. BuildAudit PASS: Flash 20,860 / 65,536 B; RAM 14,128 / 20,480 B. 37 `.su` files. |
| Generated F407 Host suite | 72 executables, 4,393,820 checks, 0 failures; 8 compile-pass and 16 expected compile-rejection cases; real FatFs byte/logger integrity PASS. |
| Architecture / Power of Ten | Flight architecture 328 checks, 0 failures; Flight Power of Ten 6,946 checks across 108 first-party C files, **0 failures**. Ground Power of Ten 455 checks across 15 first-party C files, **0 failures**. |
| Python application and integration | FCCG targeted batches: 73, 54, 11 and 3 passed. GSHC: 435 passed and 3 subtests passed. FLP: 476 passed, 22 skipped for unavailable optional real-log/C-golden inputs. Monorepo integration: 6 passed. Ruff, compileall and `git diff --check` PASS. |

The Ground USB CDC software path retains capability gating, bounded receive accounting and nonfatal transmit BUSY backpressure. It was not built against a real board's complete CubeMX CDC output in this round; it remains **HARDWARE_UNVERIFIED**. New Flight sensor wiring, TF media fault behavior, Maintenance Serial calibration save, alignment source quality, and new Ground firmware on GS_SS1 also remain hardware-unverified.

## Round 5 physical qualification

1. Flash the new F103 Ground image onto GS_SS1; smoke UART GSP, SX128x radio, ACK/status, queue pressure and RSSI/SNR with a Flight peer. Independently test USB CDC on a board with generated CubeMX middleware.
2. Test F407 Flight with real TF/SD media, interrupted writes, reboot recovery, START snapshot admission and post-START fault handling. Compare frozen calibration identities with persisted objects.
3. Exercise each new GNSS/barometer/magnetometer device, its bus variant and multiple instances on hardware; verify fresh timestamps, physical units, health and missing-capability behavior.
4. Measure target task/ISR WCET, blocking, DMA/serial offered load and stack high-water marks, then qualify conservative fixed-priority response-time profiles. Keep runtime measurements separate from the existing static memory and bounded-work gates.
5. Validate magnetometer collection/save/readback and Vector Constraints / JY901B external attitude on the target, including non-authoritative yaw and calibration/device mismatch rejection.
