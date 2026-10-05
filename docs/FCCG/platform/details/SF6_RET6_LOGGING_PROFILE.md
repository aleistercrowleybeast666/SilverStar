# SF6 RET6 explicit compact logging checkpoint

Recorded 2026-10-05 22:46 UTC (workspace/CubeMX logs use a local clock approximately UTC+8). Source implementation: `23829514ac5119ad97f1db0fb53ae04ff7e7bf9a`, branch `codex/sf6-compact-ret6`, isolated from base `7fa06c4155661e40847c0af78f4b23f3659b995d`. This is a linked compilation candidate with acceptance blockers. No RET6 hardware, wire transaction, serial/probe, flashing or flight test was performed. Stable, GSHC and FLP were not modified; no merge or push occurred.

The parent-approved SCG logger chain ending at `7000b5c01e4d19f5891d9d3f89bf42d6f794fd99` was cherry-picked through `c046622755c3b2016d36ef5ff5fd5d96657b6b01`. Its nine SCG commits are recorded in the evidence history; four unrelated FLP commits were excluded. Parent F407 results are not attributed to this RET6 build. Platform source remains at the previously reported `e810fd2cf38d6c7ef68aaa2d365dfaaa1f84c4be` checkpoint, as instructed by the parent.

## Configuration and implementation

SCG has a saved, manually selected `build.logging_profile: sf6_minimal` option beside compact mode. It requires compact mode, SF6, logging/storage and the essential IMU/barometer/lifecycle producers. Switching back restores the user's retained all-stream choices. Other estimator algorithms remain selectable; reconciliation restores the all-stream profile. The normal default is still 80/48 slots of 200 B and 4096 B aggregation. Existing compact all-stream settings remain 58/16 slots of 200 B with 2048 B aggregation. Compact's category limit is one IMU/GNSS/telemetry/barometer without a brand restriction.

The final SF6 profile uses **56 normal slots of 168 B, 40 estimator slots of 96 B and 1024 B aggregation**. All 40 stream definitions remain in descriptors and the decoder; the profile enables essential SF6_STATE, SF6_MEASUREMENT, ESTIMATOR_STEP, raw corrected IMU/increments, native barometer/measurements, calibration, alignment, mission identity, events and lifecycle metadata. SF6_STATE retains its 100000 us schema cadence. Disabled larger or unrelated types cannot be enabled through the runtime policy. Already-disabled producer pushes retain ordinary suppression success.

Generated compiler assertions use actual C `offsetof(FlightLogRecord,payload) + sizeof(native_member)` for each enabled type. Queue storage is byte arrays, copies use exact native payload lengths and the complete popped 200 B record is cleared before copying the selected slot. Wrong lane, unknown type, wrong length and oversized types are rejected; incoherent internal geometry or corrupt stored type/lane fail-stop before unsafe access or publication. No truncation, protocol/schema change, assertion disabling, stack shrinking or business return-type change was used. The immutable owned snapshot cursor retains every descriptor and starts through a durable token/barrier ACK. Its 53 metadata records plus four START records exceed the 56-slot normal lane, exercising the cursor rather than assuming all records fit simultaneously.

The tested configuration is **MPU6050 + E28-2G4M12SX/SX1281 + BMP280 + local SSLOG**, SF6, maintenance off, **GNSS removed under the user's fallback authorization**. The earlier four-module ARM link needed 75120 B RAM and failed by 9584 B; the difference across revisions is not attributed solely to GNSS. Barometer-only aiding does not bound horizontal inertial position drift.

Official STM32CubeMX 6.15.0 actually generated `SF6_RET6_Hardware.ioc` and its F1 project using STM32Cube FW F1 V1.8.7. This checkpoint reuses that official output, imports it through SCG, and freshly generates the isolated candidate (1512 added files, zero preserved payloads). Cube scripts, complete generation log, imported inventory and IOC are included; no hand-written replacement IOC was used. Actual target flags are Cortex-M3/thumb/soft float, STM32F103xE, 512 KiB Flash/64 KiB SRAM, no CCM/FPU. HSI/2 PLL yields nominal 64 MHz HCLK; the F1 CM3 FreeRTOS port, startup/vector/linker, TIM6 HAL timebase, I2C and SDIO/FatFs paths are linked. Pin mapping, HSI accuracy, timing and hardware behavior remain unqualified.

## Actual linked resources

| Disjoint RAM attribution | Bytes | Percent of 65536 B |
|---|---:|---:|
| Task/idle static stacks, already in bss | 21504 | 32.812% |
| Sample/log queues | 15168 | 23.145% |
| Algorithm and origin state | 5383 | 8.214% |
| Other logging | 2462 | 3.757% |
| Device state | 5735 | 8.751% |
| Platform/HAL/RTOS state | 2206 | 3.366% |
| Other state | 8592 | 13.110% |
| Alignment/unparsed fill | 214 | 0.327% |
| Main/MSP reservation | 2048 | 3.125% |
| Total | **63312** | **96.606%** |

Actual `.data` = 408 B, `.bss` = 60856 B, MSP = 2048 B. Spare = **2224 B (3.394%)**. The hard link limit passes; the 20% spare target permits at most 52428 B used and remains **10884 B short**. Stacks were counted once and were not reduced. BIN Flash load = **217256/524288 B**. SF6 core still has 192 B state, with no historical buffer removal claimed. Top symbols and artifact hashes are in `ret6_final_map_symbols.json`; raw merged Flash input sections are not summed into a false disjoint per-component Flash total.

The same official no-GNSS configuration with integrated logger but all-stream compact slots failed the actual link at **65896 B**, overflow 360 B. The explicit profile produces a measured net reduction of **2584 B** including the owned request state (`s_request` 832 B and flight start-log object 208 B). The historical pre-logger platform checkpoint used 64856 B. Earlier 64/48 profile trials linked close to the limit; they are retained as intermediate evidence, not substituted for this final map.

## Executed validation and retained failures

| Scope | Actual result |
|---|---|
| Final Release ARM GCC 14.3.1 compile/link | Exit 0; ELF/BIN/HEX/map retained |
| Final emitted `static-analysis` | Exit 0, actual ARM `-fanalyzer` compilation and link; separate analyzer ELF retained |
| Final emitted `artifact-check` | Exit 0, ELF 2535996 B, BIN 217256 B, zero heap symbols |
| Final emitted `power10-check` | Exit 0; 5250 text checks, 112 first-party C files, 2218 functions, 633 recommendations; critical-contract review **NOT PROVEN** |
| Final emitted `architecture-check` | Exit 2, 320 checks, one aggregate failure covering 8 Device-to-System include paths |
| Final emitted `stack-report` | Exit 2, unresolved indirect `SensorRegister_Read`; whole task/library/MSP/ISR nesting proof unavailable |
| Final complete emitted Host run | Make exit 2; jobs 1–7 pass (474 checks), job 8 `system_alignment_explicit_required_gnss` compile fails in the no-GNSS configuration; jobs 9–71 **NOT RUN**, later storage/audit stages not reached |
| Separately selected emitted Host cases | Optional GNSS START 1086/0, logger snapshot 450/0, streaming 590/0; SF6 backend 29940 checks with **4 failures**, process exit 1 |
| Final strict Host fixed-slot regression | Exit 0, 158 checks, zero failures, four genuine corruption traps; host-only terminal interception retains actual FaultCapture |
| Final SCG compact/profile/GUI tests | Exit 0, 16 passed; offscreen explicit GUI/save/restore and category tests |
| Normal all-stream storage/reference compatibility | Separate F407 generated Host project: 15 pytest passes; old ordinary all-stream pressure zero drops, high water 70/80 and 36/48, 244 modeled 20–100 ms stalls plus 300 ms open; separate overload/fault logs retained |
| Final separate SF6 profile storage pressure | Exit 0 for byte integrity, ordinary/fault/overflow cases and both decoder audits; details below |
| Real sensor polling, MCU schedule/WCET, wire IRQ timing, hardware flight | **NOT RUN** |

Both ARM link logs retain upstream nosys `_close/_lseek/_read/_write` warnings. Host LTO warning text is retained. This is not a warning-free whole-firmware or original Power of Ten compliance claim; the unchanged text gate cannot prove useful assertion semantics or completed critical contracts. No allowlist, gate threshold, source coverage or failing expectation was weakened.

The final separate pressure fixture feeds the actual ImuSampleBus correction and barometer native logger, real SF6 backend/core and SystemTime measurement helper, LoggerBus/LoggerTask/LogSink/Storage/FatFs/diskio chain. Sensors, RTOS scheduling, clock and SD media are modeled. It explicitly produces 200 Hz corrected IMU/increments and estimator steps, 20 Hz barometer/measured SF6 updates, and periodic schema-driven state/stats/health. Estimator step/increment/barometer measurement record builders are fixture calls: this is not complete actual AppTask_Estimator/INS or live MPU6050 polling execution.

The ordinary run has **38788 real SF6 predicts, 3878 barometer updates, one durable START ACK, 168 modeled 20–100 ms stalls**, max modeled write 112000 us, sync 88000 us and logger iteration 374120 us including 300 ms open. Normal/estimator high water is **50/56 and 30/40**, zero producer failures, zero drops, zero sequence gaps, matching decoder, zero unvalidated tail bytes. Persisted records include IMU_CORRECTED/INERTIAL_INCREMENT/ESTIMATOR_STEP 38788 each, SF6_STATE 1940, BARO_NATIVE/BARO_MEASUREMENT/SF6_MEASUREMENT 3878 each, calibration/alignment/mission identities, both complete startup snapshots (80 stream descriptors = all 40 entries twice), and lifecycle events. The deliberately overloaded run accounts for **444 capacity rejections/drops**, then resumes; gap audit requires accounted overflow rather than falsely expecting a contiguous sequence.

The initial 48/48 profile with 2048 B aggregation failed this unchanged ordinary stress expectation (**14 drops, 11 producer failures**); its complete failure log is preserved. The final 56/40 and 1024 B selection follows measured pressure rather than blindly making the record lanes smaller. A conditional 112 ms fixture-bound calculation needs approximately 52 normal records (two 200 Hz sources plus 20 Hz barometer and periodic diagnostics), observed peak 50, and about 31 estimator records, observed peak 30. The selected margins are conditional on this saved configuration and model schedule; they are not STM32 WCET, arbitrary runtime cadence, actual TF latency or universal queue-capacity proofs.

SF6 backend's four remaining failures concern prior position/velocity/barometer updates and a fixture expecting native 0.5 m altitude/0.18 m vertical state under the current cold-pressure configuration. They remain failures, not excused passes. A broader earlier Python batch also retains the existing SF6 Ground GUI enabled-state expectation failure. Initial new fixture/runner errors (include setup, stale GUI object, wrong corrupt queue offset, terminal wrapper, CSV `-Only` invocation, missing PYTHONPATH) are included with their corrected runs. An initial terminal-wrapper Host executable could not be safely identified through restricted process inspection; its unified execution session was canceled, and no unidentified process or user GUI was killed.

## Unresolved acceptance boundaries

The parent independently observed a three-byte `DATA_BTF_MASKED3` I2C model transaction at **1806 model us total, 1724 model us with PRIMASK=1**. This supplied observation was not executed here; the platform is frozen for parent review. A per-transaction deadline alone does not prove the requested overall <=2 ms bound or continuous 1 ms TIM6/SysTick accounting. Possible lost timer ticks and IRQ continuity remain **NOT PROVEN and block RET6 acceptance**. No vendor STOP/ACK/timer semantics were silently changed.

Unlimited unattended same-instance recovery with bounded attempts/backoff/yield, START-locked IMU identity preservation across fault recovery, and complete fault/READY publication handling remain **NOT PROVEN** for this generated RET6 configuration. Existing source ownership and ordinary bad-packet/no-fix behavior were not replaced by fatal external-input assertions. This logging batch did not introduce a recovery redesign. F1 UART DMA/GNSS behavior is not demonstrated by the final no-GNSS build. Target stack margins, callbacks/vendor recursion, full linked call graph, dynamic frames, interrupt nesting, physical bus timing, storage latency and SF6 timing qualification are still unresolved. Barometer aiding alone cannot prevent horizontal inertial drift. These are compilation/test evidence, not MCU recovery or flight qualification.

## Evidence and reproducibility

`../evidence/SF6_RET6_logging_profile/logging_profile_evidence.zip` contains the implementation patch from platform checkpoint e810 through source commit 2382951, exact history, current source hashes, generated sources/configuration hashes, actual IOC/Cube commands and logs, generator/validation/import logs, complete test/gate/failure output, immutable ordinary/overflow `.sslog` and exact `.ssdecoder`, both linked ELF/maps/BIN/HEX, complete emitted `.su` records and small symbol report. The adjacent SHA256/manifest identifies the package. One generated RET6 workspace was reused; source logs/packages were archived before regeneration, and previous formal evidence was preserved.

The complete read-only identity comparison checks **1512** current payload/glue/imported official hardware files, including **all 144 linked C/assembly inputs**. Compilation sources, headers, linker/build files and decoder match current source byte-for-byte; two JSON metadata files differ on raw bytes only. Parsed saved `SilverStar.ssproject` equals its current re-render; its serialization/order hash difference propagates to one ownership managed hash. The raw checker exit is retained as **1**, with the full differences and hashes, rather than presented as a blanket byte-identity PASS. The initial 593-file comparison omitted the separately returned hardware mapping; the complete comparison includes it and the initial output is retained. The actual generated-file manifest separately records every relevant source/configuration hash. Final target code is source-identical to committed 2382951 despite generation just preceding the commit; no older binary is attributed to later changed code.

Commands use the official emitted Makefile: `mingw32-make -C .work/generated_ret6 -j4 "GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin" "PYTHON=D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe" <target>` for Release, power10-check, static-analysis, architecture-check, artifact-check and stack-report; complete host-tests adds `HOST_CC=D:/msys64/ucrt64/bin/gcc.exe`. Selected cases use an explicit PowerShell array wrapper, not the failed CSV command. Separate fixture command is `python .work/generated_ret6/Tests/Host/storage_integrity/run_storage_integrity.py --project .work/generated_ret6 --compiler D:/msys64/ucrt64/bin/gcc.exe --sf6-compact`; fixed slots and pytest commands are in the command manifest. Host compiler is MSYS2 GCC 16.1.0, ARM compiler 14.3.1, Make 4.4.1, Python 3.14, PowerShell 7.6.5 plus Windows PowerShell for emitted checks. Exact version output is retained.
