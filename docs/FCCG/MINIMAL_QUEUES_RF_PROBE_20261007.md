# Minimal queue default and isolated RF resource probe (2026-10-07)

The user authorized an MCU-independent Minimal logging queue default of
24 ordinary records / 16 estimator records. The owning generator now emits
these constants. Full, Standard and Compact retain their previous defaults;
navigation queues, task stacks, algorithms, protocol and descriptor contracts
are unchanged. Minimal retains its owned startup snapshot cursor, all 40 stream
descriptors, 168/96-byte slots, 1024-byte aggregation and 16/16 navigation queues.
The tested RET model has 53 owned startup records, independently drained from
the 24-record ordinary queue. The GUI/model still requires `sf6_minimal` for
Minimal; an incompatible `all_streams` configuration remains invalid.

Base source commit: `63d038c580e4eeb229a10b010772f383c31f8512`. The auditable
dirty snapshot, exact commands, configs, log hashes and linked artifact hashes
are in `.work/minimal24_evidence` and `.work/rf_queue_evidence` in the isolated
`.work/kh` checkout. No hardware, serial, probe, flashing or push was performed.

## Actual resources

| Actual linked configuration | Flash sections | BIN | RAM / capacity | Spare | 20% RAM target gap |
|---|---:|---:|---:|---:|---:|
| RET Minimal 24/16, MPU6050 + NRF24 + BMP280, no GNSS | 209472 | 209480 | 54208 / 65536 | 11328 (17.285%) | 1780 |
| RF Compact isolated 56/16, MPU6050 + M9N + E28 + BMP280 | 256748 | 256752 | 86872 / 98304 | 11432 (11.629%) | 8229 |
| RF same-source, same logging control 80/48 | 256756 | 256760 | 98072 / 98304 | 232 (0.236%) | 19429 |

Units are bytes. RF 56/16 has an actual same-source net reduction of 11200 RAM
and 8 Flash bytes. Historical RF RAM 97488 belongs to another revision/config;
it is not the control for this experiment. Both configurations link within their
hard capacities; neither reaches the requested 20% spare-RAM target.

RF uses the previously executed official CubeMX RFT6 snapshot
`41b9462f09870adb8f1dce829007ee06cea4f353516bcc050a78cad866db5828`;
921 reused files / 35145312 bytes were individually hashed. No new CubeMX run
is claimed. Actual compilation uses Cortex-M3, `STM32F103xG`, soft float,
FreeRTOS CM3, F1 Flight UART/I2C/timebase/SDIO, and no FPU/CCM. The official
RF linker reserves 768 KiB Flash and 96 KiB RAM. The artifact checker currently
reports a conservative hardcoded 512 KiB Flash capacity even for RF; this
discrepancy is recorded without changing the checker. The candidate fits both.

RF 56/16 is an external experiment-only makefile override, not a new Compact
default. It preserves 200-byte slots, 4096-byte aggregation, 64/64 navigation
queues and all task stacks. Its selected log records are existing Minimal
records plus GNSS native; no new record type was introduced. All 40 stream
descriptors remain. The startup descriptor contract requires 54 ordinary queue
slots (1 configuration + 9 device + 4 algorithm + 40 stream descriptors);
56 satisfies that necessary bound. Actual snapshot and lifecycle Host cases
exercise successful START admission, preemption, full queues, sync/write
failures and retained descriptor publication. Hardware storage throughput and
runtime drop rates were not measured.

## Linked RAM attribution

Groups are nonoverlapping actual B/D symbols attributed to input objects in
the linked map. Navigation queue groups include their control structures;
algorithm state includes navigation/origin state, not just SF6's 192-byte core.
Percentages below are of used RAM. Full symbol inventories are in `resources.json`.

| Group | RET bytes (%) | RF 56/16 bytes (%) |
|---|---:|---:|
| Algorithm/navigation state | 3795 (7.001) | 10531 (12.122) |
| Ordinary/estimator logger queue storage | 5568 (10.272) | 14400 (16.576) |
| Other logger/storage/control state | 5933 (10.945) | 9005 (10.366) |
| Navigation queues/control | 2155 (3.975) | 8299 (9.553) |
| Platform/HAL state | 1849 (3.411) | 4029 (4.638) |
| Other named state | 11110 (20.495) | 16690 (19.212) |
| Task stack reservations | 21504 (39.669) | 21504 (24.754) |
| MSP linker reservation | 2048 (3.778) | 2048 (2.357) |
| Padding/unnamed | 246 (0.454) | 366 (0.421) |

Task stacks and MSP are already included once in the linked RAM total; they
are not added again as extra RAM consumption.

## Verification and failures

- Generator regression: initial selected 4 tests PASS; all feature-tier tests
  16 PASS. Stack checker regressions 51 PASS. Existing pytest unknown
  `cache_dir` warning remains recorded.
- RET actual ARM compile/link, real GCC analyzer compilation, architecture,
  emitted Power10, artifact and memory gates exit 0. Selected emitted Host:
  four executables, 1521 checks / zero failures, one selected-provider compile
  positive. Storage child and full Host suite NOT_RUN for this batch.
- RET stack initially exited 2 on changed `project_flight_config.h`. Review
  proves its sole differences from an already reviewed header are 58->24 and
  40->16. Gate revision v8 records only that exact normalized SHA256
  `afca623011a2d5e7b7adc28d580adca0925b9b701ad0f38d23c71b05c08c281b`;
  thresholds, callback bodies and dependency coverage are unchanged. Owning
  payload and reference overlay are identical. Normal regeneration correctly
  preserves project-owned Tools and refuses a missing installed payload. The
  recorded failed attempt is retained. This disposable validation tool was
  explicitly refreshed from the selected owning catalog payload; no user
  project was updated. The exact refreshed gate then exits 0.
- RET static task estimates / reservations / margins: Device 1604/2560/956;
  INS 2224/3072/848; Estimator 1440/4096/2656; Flight 3480/4096/616;
  Logger 2736/3072/336; Telemetry 2168/4096/1928; Idle 256/512/256 bytes.
- RF 56/16 actual ARM, real GCC analyzer, architecture, emitted Power10,
  artifact and memory gates exit 0. RF stack exits 2:
  `Changed compiled callback dependency graph: APP/Src/device_task.c`.
  No RF binding fingerprints or stack limits were broadened. Current RF task
  bounds and historical Logger zero margin are NOT_PROVEN resolved; old
  estimates are not attributed to this new ELF.
- RF unadapted selected Host exits 1: `neo_m9n_device` 2177 checks / 1739
  failures. Its single-receiver mock defaults to logical UART2, whereas the
  actual generated RF resource is logical UART1. Original failure is retained.
  A separately labeled fixture explicitly matching generated UART1 passes nine
  executables / 76458 checks / zero failures, one compile positive and three
  specific expected noise-contract rejections. Original test expectations were
  unchanged. This does not establish an unchanged emitted Host-suite PASS.
  The prior unselected JY provider case is explicitly NOT_APPLICABLE; it is not
  presented as executed. Storage child / complete RF Host suite NOT_RUN.
- RF 80/48 control executes ARM compile/link only. Other control gates NOT_RUN;
  control results cannot be stitched into a full-suite PASS.

Commands are fully captured by `gates.json`, Host receipts and supplemental
receipts. Main make invocation uses `GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin`
and `CONFIG=Release`; RF candidate additionally uses `-f Makefile -f queue56_16.mk`.
Targets executed are `all`, `static-analysis`, `architecture-check`,
`power10-check`, `artifact-check`, `stack-report`, `memory-report`; the RF
control overrides only `BUILD_ROOT=build/FCCG/SilverStar_F103RF/Queue80Baseline`.
Tool versions: ARM GCC 14.3.Rel1/14.3.1, Host GCC 16.1.0, GNU make 4.4.1,
Python 3.14. Full raw logs, warnings, original failures, source/config and ELF/
MAP/BIN hashes are retained locally; no build or source logs were removed.

Power10 text PASS still explicitly reports critical-contract review NOT_PROVEN.
Whole-system main/MSP/ISR nesting, every third-party/indirect path, WCET, runtime
stack high-water, flight accuracy and hardware qualification remain unproven
or NOT_RUN. No complete safety/compliance acceptance is claimed. The existing
GSHC NRF frame-0x05 reception gap also remains; RET compilation does not imply
NRF end-to-end reception in the current daily GSHC.
