# SF6 RET6 combined software review

Recorded 2026-10-06 UTC. Implementation source is `1fcf9b20fb5250f27367cf6b71e493d197185f45`, branch `codex/sf6-compact-ret6`, isolated from `7fa06c4155661e40847c0af78f4b23f3659b995d`. This supersedes the software results of the preserved [logging checkpoint](SF6_RET6_LOGGING_PROFILE.md); it does not replace its historical evidence. Status: **linked compilation candidate, acceptance blocked**. No hardware, serial, probe, flashing, flight, merge or push was performed. Stable, GSHC and FLP were not changed.

## Configuration and scope

The saved manual compact option permits at most one device per IMU/GNSS/telemetry/barometer category, without requiring a brand. Ordinary defaults and algorithm selection remain available. Tested RET6 fallback is MPU6050 + E28-2G4M12SX/SX1281 + BMP280 + local SSLOG, SF6, maintenance off, GNSS removed under the user's authorization. The earlier actual four-module link required 75120 B RAM and failed by 9584 B. Changes span revisions, so that difference is not a measurement of GNSS removal alone. Barometer-only aiding does not bound horizontal inertial position drift.

Official installed CubeMX 6.15.0 actually generated the STM32F103RET6 IOC/project with FW F1 V1.8.7; SCG imports that output. Current fresh generation added 1514 files. No hand-written substitute IOC was used. The linked target is Cortex-M3/thumb/soft float, STM32F103xE, 512 KiB Flash/64 KiB RAM, no FPU/CCM. F1 Flight includes the CM3 FreeRTOS port, startup/linker/vector, TIM6 HAL timebase, I2C sensor transport and SDIO/FatFs storage. HSI/2 PLL gives nominal 64 MHz. Actual Cube scripts, output logs and IOC remain in evidence; hardware behavior and timing remain unqualified.

SF6 minimal logging retains 56 normal slots of 168 B, 40 estimator slots of 96 B and 1024 B aggregation. All 40 stream descriptors remain present. ESTIMATOR_STEP and BARO_MEASUREMENT are now disabled in this explicitly selected profile because the SF6 firmware branch does not produce them; SF6_STATE/SF6_MEASUREMENT, corrected IMU/increments, native barometer and lifecycle/alignment/calibration metadata remain. Ordinary all-stream configuration is unchanged. The 192 B SF6 core had no historical buffer to remove. Queues copy exact native payload lengths and preserve wrong-type/lane/size rejection and bounded failure behavior.

The parent-approved logger changes `c744bb402460545e8fb2dd18e74dcd06b4d8479a` and `28b168f75e59c92ef2f004ff84d42ba8ac54f5d5` were applied as `027bcc04df318a3ac439705f19ef87fcb7795969` and `562eb3b9dbbce95cc9979247cdcbc3940af2098c`. They retain BOOT alignment evidence, immutable generations/retries and failed-writer identity. Conflict resolution retains both queue geometry validation and the failed-writer rejection. F407 validation is not credited to this RET6 run. A prematurely generated conflicted intermediate was discarded; it was never used for the current build.

## Software defects and boundaries

Device-native BMP280 data no longer includes System interfaces; adapters perform explicit field conversion. Twenty-two System-facing adapter/storage files moved to Adapter directories, with manifests, includes, source graph and reference-import paths updated. Existing projects containing the old owned paths receive an explicit relocation conflict, preserving their source bytes. A fresh project or reviewed migration is required; existing project upgrades are not silently compatible. Ownership and user-payload preservation tests passed.

Host fixes preserve expectations: the required-GNSS positive fixture now explicitly selects its mocked GNSS; the missing-GNSS negative remains a compile rejection. The normal SF6 fixture uses its qualified direct-altitude case, and the separate cold-pressure fixture tests pressure-only admission and four rejection/recovery paths. No algorithm defaults or production protocol checks were weakened.

The storage fixture now retains and initializes its estimator snapshot instead of reading an uninitialized automatic object. It constructs self-consistent NONE calibration, alignment, mission generation and initial-state records, and logs the exact inertial increments supplied to SF6. Old logs reproduce `calibration_result_not_ready`; fresh logs open and replay. This fixture exercises actual ImuSampleBus correction, SF6 backend, barometer and logger/storage paths, but manually constructs backend increments at 200 Hz. It does not exercise the complete production INS two-subsample 100 Hz producer or prove MCU scheduling. START has all 40 descriptors and a durable ACK; storage dispatch now explicitly recognizes the actual F1 diskio path instead of silently omitting its four phases.

## Actual resources

Release map: data 408 B, bss 60928 B, MSP reservation 2048 B; total **63384/65536 B**, spare **2152 B (3.284%)**. Task/idle stacks are included in bss and counted only once. The parent logger correction adds **72 B** over the measured pre-fix 63312 B. Hard link limit passes; the 20% spare target permits 52428 B used and remains **10956 B short**. No task stack was reduced.

| Disjoint RAM group | Bytes | RAM capacity |
|---|---:|---:|
| Static task/idle stacks, already in bss | 21504 | 32.812% |
| Sample/log queues | 15168 | 23.145% |
| Algorithm/origin state | 5383 | 8.214% |
| Other logging | 2462 | 3.757% |
| Devices | 5735 | 8.751% |
| Platform/HAL/RTOS | 2206 | 3.366% |
| Other state, including new logger request bytes | 8664 | 13.220% |
| Alignment/unparsed fill | 214 | 0.327% |
| Main/MSP | 2048 | 3.125% |

Flash BIN load is **217640/524288 B (41.512%)**. Retained disjoint text attribution: algorithm 26384 B, logging 23532 B, platform/HAL/RTOS 22232 B, devices 32496 B, runtime libraries 22286 B, other first-party 80050 B. Remaining 10660 B covers rodata, vectors, fill and data load. Merged string sections are deliberately not summed per object. Full symbol tables, attribution scope and artifact hashes are in the map JSON files.

## Executed evidence and failures

| Scope | Recorded outcome |
|---|---|
| Fresh current generation | Exit 0, 1514 added files; hardware-manual and unqualified timing warnings retained |
| Release ARM GCC 14.3.1 compile/link | Exit 0, fresh ELF/BIN/HEX/map |
| Emitted static-analysis | Exit 0, actual ARM `-fanalyzer` compilation/link in separate build; four upstream nosys linker warnings retained |
| Emitted artifact-check | Exit 0, ELF 2543600 B, BIN 217640 B, zero heap symbols |
| Emitted architecture-check | Exit 0, 320 checks/0 failures; prior eight Device-to-System violations fixed in owning payloads |
| Emitted power10-check | Exit 0, 5254 checks, 112 C files, 2220 functions, 634 nonblocking recommendations; critical-contract review **NOT PROVEN** |
| Emitted stack-report | Make exit 2, unresolved `SensorRegister_Read` indirect call; no new allowlist exception |
| Current selected emitted Host run | Exit 0, 6 executables, 31807 checks/0 failures, 1 expected compile rejection; actual storage four phases passed |
| Current strict fixed-slot Host harness | Exit 0, 158 checks/0 failures, four fault traps; test-only trap interception is not MCU recovery |
| Complete Host suite, prior source 7ab1c7d | Exit 2 after 30 completed executables; first positive capability case requires absent unselected JY901B header. Remaining cases NOT RUN. Complete suite at current source NOT RUN; no combined full-suite PASS claimed |
| Related Python batch before logger integration | 65 passed/1 failed; optional-protocol GUI fixture StopIteration finding SX1281 combo. Isolated rerun also failed; unrelated frozen GUI was not changed |
| Adapter migration/preservation tests | 2 passed/4 deselected |
| Compact/profile Python tests after logger integration at 562eb3b | 5 passed |
| Current source identity | All 144 linked C/assembly inputs byte-identical to current source. 1514 files checked; raw verifier exit 1 for two JSON metadata render identities, not a blanket PASS |

Source identity differences are saved project serialization and its corresponding ownership hash. Saved project semantics compare equal. Initial verifier invocation lacked PYTHONPATH and failed before comparison; its failure log is retained, followed by the corrected invocation. Source archives record actual ZIP bytes separately from Git blob identities; no EOL/encoding explanation is assumed and files were not rewritten to force hashes.

The latest logger fixture compile failures (missing policy header, then potential uninitialized test query output) are retained. Current fixture initialization and explicit include correct those strict-build errors while preserving all suppression/queue/fault assertions. Logger snapshot 450, alignment 326, streaming 590, GNSS positive 297, SF6 normal 30060 and cold-pressure 83 checks all pass.

Storage pressure tests retain 38788 predictions, 3878 barometer updates and START ACK=1. Ordinary normal queue high-water is 51/56, estimator 5/40, drops=0, producer failures=0. Intentional overload reaches 56/56, drops=444, producer failures=0. Injected storage jitter remains 20–100 ms. These are host pressure/fault cases, not STM32 WCET evidence.

## Official FLP opening and replay

Unmodified FLP source at base 7fa06c4 uses LogOpenCoordinator and the exact current `.ssdecoder`, with recorded configuration and recorded inertial increments; no offline defaults or fallback decoder. Both current logs pass opening with `exact_generation_profile` and SF6 revision 2 replay, yielding 38788 outputs in each of seven channels and `missing_inputs=[]`.

Ordinary log: 88019 decoded records, zero CRC/length/decoder errors, sequence gaps=0, no damaged/truncated tail. Overload log: 88074 records, zero CRC/length/decoder errors, one gap/missing 444 matching queue-drop accounting, no damaged/truncated tail. Replay fidelity is **APPROXIMATE**. Both retain warnings: firmware_build_differs_from_reimplementation, host_golden_not_verified, source_log_has_integrity_or_sequence_gaps, sf6_backend_schedule_not_exact, sf6_defaults_not_tuned, sf6_delayed_measurements_not_compensated. The generic integrity warning also appears for the ordinary log despite its zero parser gaps; it is not suppressed. Complete parse and replay diagnostics are retained.

## Acceptance blockers

No whole-program acyclic call-graph, all finite loop bounds, meaningful assertion semantics, complete critical-contract, third-party recursion/timing, task/library/dynamic frame/MSP/ISR stack proof is established. The scanner candidate average 1385/2220 = 0.623874 is informational. Power10 adaptation is not original compliance or NASA certification. Third-party code is linked and its exceptions remain subject to manual review.

The F1 I2C three-byte masked model previously measured PRIMASK=1 for 1724 us in an 1806 us transaction; 1 ms TIM6/SysTick loss and overall timing bounds remain **NOT PROVEN**. Unattended bounded-attempt/backoff recovery and post-START same-instance IMU source lock across all fault paths remain **NOT PROVEN**. No new IRQ/vendor timing or recovery redesign was attempted in this final batch. GNSS no-fix remains distinct from communication failure. No RET6 board is available: hardware, accuracy, WCET, safe stack margin and flight qualification are **NOT RUN/NOT PROVEN**. RAM margin and the complete Host/GUI failures above also block completed acceptance.

## Deliverable identities

Raw source base archive: 429 files, 6526478 B, SHA-256 `e57c563cf2be5bf086c6c4d73276048607b215c9473b4aa7045229a09944a0c3`, Library `libfile_c238fa7daca4819196bd23dc00b2f24f`, file `file_00000000805481fd8e14161e4eacb606`, source 7ab1c7d from base 7fa06c4. Current seven-file addendum is included in the final evidence: 55259 B, SHA-256 `c66febf0092335e21020fc3353e2c8fd4897aac8848df24363cd01365d9343a4`, source 1fcf9b2 from 7ab1c7d. It supersedes the previously uploaded 0bdbb7f addendum. These archives keep raw SHA identities and Git postimages separate.

Final evidence lives in `../evidence/SF6_RET6_software_fix/`: verified ZIP, manifest and SHA sidecar. It includes this report, current gate/Host/FLP logs, complete failures, commands/tool versions, exact configuration, Cube evidence, current artifacts/map/stack files, source identity, immutable logs and decoder, and the final source addendum. Historical failure evidence is explicitly labeled; results are not stitched into an unexecuted full-suite pass.
