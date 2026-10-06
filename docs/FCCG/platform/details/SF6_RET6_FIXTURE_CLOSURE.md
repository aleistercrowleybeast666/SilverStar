# SF6 RET6 fixture closure and snapshot identity

Recorded 2026-10-06 UTC. Source `1bf72f1530f79a04f6dc7ded688d770c421a4072`, isolated `codex/sf6-compact-ret6`, follows evidence HEAD `29f0abdd918f1ae038cea8e722aaf9a0946839f9`. Only three Host fixture files changed (38 insertions, 3 deletions); no production firmware, GUI, GSHC or FLP edits. No hardware, serial/probe, flashing, merge or push. This supplements [the combined software review](SF6_RET6_SOFTWARE_FIX_REVIEW.md), preserving prior evidence and its source scope.

## Union contamination: demonstrated and corrected

Before the fix, all 193 periodic ordinary-log STATS records had `imu_queue_overflow_count = increment.interval_start_timestamp_us` low 32 bits and `ins_update_count = increment.interval_end_timestamp_us` low 32 bits. First pair: 7331000/7336000; last: 199331000/199336000. Logger overflow, CRC, sequence and actual sample processing were normal. Formal FLP nevertheless reported source loss from those contaminated IMU counters. The before JSON retains every record and original log/decoder SHA. Its first audit attempt wrongly assumed overload had 194 STATS; corrected evidence records ordinary 194 (193 periodic plus final) and overload 193. No firmware/test expectations were relaxed to correct this analysis-helper assumption.

Every switch from increment to STATS, HEALTH and TELEMETRY_DIAG now clears the full record. STATS uses actual ImuSampleBus overflow, LoggerBus overflow, accepted backend prediction count and current estimator health. The fixture manually feeds backend increments; `ins_update_count` represents that measured fixture update count, not an executed AppTask_Ins. Final STATS uses the same builder. HEALTH copies the fixture's existing modeled SystemHealth snapshot (ready=1, other mocked fields zero). No radio transport executes here, so telemetry is explicitly offline with zero counts. These are Host models, not hardware diagnostics.

All fresh ordinary/overload STATS now report IMU overflow=0. Ordinary final update count=38788; overload's last retained periodic count=38589, with logger overflow=444. All retained update counts increase and stay within the actual 38788 accepted predictions; the overload log does not retain a final STATS record. The original pressure and drop expectations remain unchanged.

`test_logger_alignment.c` already initialized `raw_config={0}` at source 1fcf9b2. This batch additionally stores each stream-query return result, records a failing TEST_CHECK and immediately returns on non-OK before inspecting output. Strict original `-O2 -flto -Wall -Wextra -Werror` settings remain; no O0 pass replaces strict evidence. Current logger alignment reports 326 checks/0 failures; selected runner summary reports 327 total checks/0 failures including its framework check. The compiled source is freshly emitted from the owning plugin.

## Actual current runs

Fresh generation added 1514 files and retained hardware-manual/timing-unqualified notices. Selected logger alignment plus actual storage four stages passed, exit 0. Pressure remains ordinary queues 51/56 and 5/40, drops=0, producer failures=0; overload queues 56/56 and 4/40, drops=444, producer failures=0. Both execute 38788 predictions, 3878 barometer updates and START ACK=1, with finite 20–100 ms injected storage jitter.

The **current complete emitted Host suite was executed**, not represented by historical results: make exit 2, planned 73 executable cases, 30 completed, first failure `capability_jy901b_gravity_known_yaw`, compiler exit 1 because `jy901b_imu_build_capabilities.h` is absent in the selected MPU6050-only project. This compile-positive fixture assumes a generated header for an unselected JY901B component. No skip, synthetic header, broadened allowlist, suppressed warning or modified test expectation was used. The remaining 43 planned executables and later compile cases are NOT RUN; their correctness is unknown. Full Host remains FAIL, even though the selected firmware ARM link from the prior batch passed. Complete console output, failed compiler arguments and completed-case list are retained.

Official unmodified FLP uses LogOpenCoordinator with exact decoder SHA `102d2aaadbed732f49d4eae2dfe6266816191c84ba5e29e8a8511a003fd429a1`, recorded configuration and recorded inertial increments. Both current logs open with `exact_generation_profile` and replay SF6 revision 2: 38788 outputs per channel, seven channels, missing_inputs=[]; fidelity remains APPROXIMATE.

| Current log | Parse and source-loss result |
|---|---|
| Ordinary | Zero CRC/length/decoder errors, sequence gaps/missing=0, IMU/logger overflow=0; **no source_log_has_integrity_or_sequence_gaps warning** |
| Intentional overload | Zero CRC/length/decoder errors, one sequence gap/missing=444, IMU overflow=0, logger overflow=444; **source loss warning remains** |

Both retain other replay warnings: firmware_build_differs_from_reimplementation, host_golden_not_verified, sf6_backend_schedule_not_exact, sf6_defaults_not_tuned and sf6_delayed_measurements_not_compensated. Neither decoder nor FLP warning mechanism was changed. Full parse/replay diagnostics and every STATS counter are retained. HEALTH and TELEMETRY_DIAG each have 193 records per log; health matches the existing model, telemetry remains all zero/offline.

## Snapshot identity: precise read-only cause

The previous snapshot package's normal Windows `Path.is_file()` enumeration omitted two **existing** CMSIS NN test files whose absolute paths are 268/261 characters. Normal paths return false; Win32 extended paths read both successfully and their bytes exactly match the existing official Cube tree. An attempted ordinary-path restore failed before any write; subsequent extended-path inspection showed restoration was unnecessary. No snapshot bytes, ID, permissions or OS long-path setting were changed.

The two paths are:

- `Drivers/CMSIS/NN/NN_Lib_Tests/nn_test/Ref_Implementations/arm_depthwise_separable_conv_HWC_q7_ref_nonsquare.c`
- `Drivers/CMSIS/NN/NN_Lib_Tests/nn_test/Ref_Implementations/arm_fully_connected_mat_q7_vec_q15_opt_ref.c`

The actual canonical source input list contains **920 files**. CubeMxImporter hashes each original relative POSIX path (casefold-sorted), NUL and its SHA256 binary digest. Reading those exact existing snapshot inputs, including both long files, gives **`b582e89bf934a92fce53c2c704e1ede4be4a42417b031c9321ceb6f8130072ee`**, equal to original Cube input digest, directory name, import.json and saved model. The post-import README is written by `_Snapshot_Store` and is not an original source-digest input. Thus the prior package's 919-file STM32CubeMX view (missing two, adding README) rehashes to `0c4d55...`; that was a different file set, not a sorting explanation or post-import I2C/SDIO mutation. All shared original files are byte-identical. Complete 920 ordered path/hash entries and both actual long files are in the identity addendum. Windows normal-path public generation still excludes these two unlinked vendor NN fixtures; this artifact/path limitation was not fixed by a production change in this Host-only batch.

Identity addendum: 54927 B, SHA256 `07ed55b248b54341ea5b89fac8c7b466a67a7dfabeec6a6cf5ba8d4a19b8f700`, Library `libfile_119a24c5864481918e431d754c9fd546`, file `file_000000001a0481f586f6b3fb0f76fc86`. Apply it to the previous official snapshot archive to recover the full original input set; preserve the existing README separately. No invented source identity or new CubeMX invocation is required.

## Stack read-only findings and unchanged acceptance limits

The prior actual Release ELF at source 1fcf9b2 was read from its immutable evidence archive. All **144** current generated linked C/assembly inputs are byte-identical to that build's recorded inputs. Read-only nm and per-function objdump preserve that ELF's SHA; no current ARM/analyzer rerun is claimed for this fixture-only change. Its actual map remains RAM 63384/65536 B, spare 2152 B (3.284%), Flash load 217640 B; task stacks are counted once. The 20% RAM spare target is still 10956 B short.

Known source constructor possibilities for SensorRegister_Read are `{SensorImuAdapter_ReadRegister, SensorImuSpi_Read}`; Write is `{SensorImuAdapter_WriteRegister, SensorImuSpi_Write}`. Selected route is Mpu6050ImuInstance_Init -> SensorImuAdapter_Init -> SensorImuAdapter_InitI2c -> SensorImu_Init copying the bus into driver state. Actual ELF contains only the I2C callbacks/constructor; SPI callbacks/constructor are absent after linking. The real SensorRegister_Read disassembly contains `blx r5` at 0x08024f86. The emitted stack checker marks register-indirect calls unresolved and only has explicit binding logic for its named FatFs/startup tables; it has no SensorRegisterBus points-to resolver.

These observations do not prove invariant callback identity, corrupt-state handling, full call graph, library/dynamic-frame bounds, task ownership, main/MSP or ISR nesting. No numeric bound or new Rule9 exception is introduced; stack acceptance remains **NOT PROVEN** and prior emitted stack gate remains FAIL. IRQ/TIM6 timing, bounded unattended recovery, START source-lock behavior, hardware/accuracy/WCET/flight qualification and the unrelated existing GUI failure remain unchanged and unproven. No full-suite or completed safety acceptance claim is made.

New evidence/source incremental archive is under `../evidence/SF6_RET6_fixture_closure/`, with raw byte SHA identities distinct from Git blobs, before/after immutable logs, decoder, strict/full Host output, commands, exact source delta, canonical snapshot proof and read-only stack evidence. Earlier review archives remain intact.
