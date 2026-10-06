# RET6 remaining Host diagnostic matrix

Recorded 2026-10-06 UTC, source `1bf72f1530f79a04f6dc7ded688d770c421a4072`, previous evidence HEAD `42579c8fd2bdd7606d75b743254f57acc4434d9d`, isolated `codex/sf6-compact-ret6`. Production, GUI, original generated runner and tests are unchanged. No hardware, serial/probe, flashing, merge or push. The official complete runner remains **FAIL**, make exit 2 after 30 executables and the first unselected-JY positive compile failure, as recorded in [fixture closure](SF6_RET6_FIXTURE_CLOSURE.md).

## Diagnostic execution method

The diagnostic script copies the original runner prefix that collects jobs and defines its compiler/assertion functions. It changes only the project-root resolution, private output directory and compiler-observation wrapper, then dispatches every remaining planned job individually through the original functions. Original compiler argv, assertions, expected-rejection checks and native exit behavior are preserved. Each failure is caught to record evidence and continue; it remains a failed matrix row. This script is not an official gate and deliberately returns exit 1 even after all jobs finish. The original runner SHA256 remains `e99b91167552efe0841e545c6d8e2f44b252906aca23c9c2a87894f865c6372b`.

The first diagnostic helper attempt failed during initialization because its observation wrapper was defined too late; it ran no case. That failure log is retained. The corrected attempt completed all **67** remaining jobs, including the original first failure: **43 planned executable cases, 7 positive compile cases, 17 negative compile cases**. There are no remaining unattempted jobs within this original planned set. Sixteen originally excluded jobs with missing unselected component sources are separately listed with exact missing paths; they are not silently considered passes or part of these 67.

| Diagnostic scope | Pass | Fail |
|---|---:|---:|
| Planned executable cases | 32 | 11 |
| Positive compile cases | 3 | 4 |
| Negative compile cases | 14 expected rejections | 3 unexpected successes |
| Total | **49** | **18** |

Of 43 executable cases, 41 built and ran (32 passed, 9 failed or timed out); two failed compilation. Configuration-negative cases deliberately use the original syntax-only compiler test; they are not static-analysis runs. Earlier 30 official executables and these diagnostic passes are not stitched into an official full-suite PASS.

## All failed cases and first source evidence

| Case(s) | Actual result | Evidence and classification |
|---|---|---|
| capability_jy901b_gravity_known_yaw | Compiler 1 | `test_build_capability_contract.c:4` includes missing JY header when TEST_EXPECT_DEFAULT_JY901B_PROFILE is forced. Current primary is MPU6050. Unselected-device fixture assumption. |
| capability_missing_imu_noise, capability_missing_gnss_noise, capability_missing_baro_noise | Compiler 0; negative expectation fails | Original runner `run_tests.ps1:337`; current `project_device_build_capabilities.h:7` selects covariance estimator noise contract=0 for SF6, and `system_user_capability_validation.h:49` conditionally checks it. The negative fixture assumes an enabled covariance contract. No assertion/compile flag was changed by this diagnostic. |
| capability_jy901b_hw_quat_6axis_preflight | Compiler 1 | `system_user_capability_validation.h:106`; selected MPU6050 has hardware-quaternion qualification=0 while the fixture forces HW6. |
| capability_jy901b_hw_quat_9axis_preflight | Compiler 1 | Same qualification conflict, validation header `:113`, fixture forces HW9. |
| capability_jy901b_baro_imu_window_landing, flight_recovery_baro_imu_landing | Compiler 1 | Validation header `:172`; fixture selects alternate BARO_IMU_WINDOW while BMP280 landing-window qualification is 0 at generated capability header `:19`. Actual selected mode is Stillness. |
| source_selector | Native 1; 361 checks/226 failures | First expectation `test_source_selector.c:559`. Fixture defaults to 3 instances (`:22,40–42,92–94`) and also tests 2-instance failover; compact maxima are 1 (`project_device_instances.h:56–61`). Production rejects excess counts at `system_source_selector.c:533,1014,1747`. Failed count contexts and every failed predicate are retained. This does not prove valid single-IMU START locking/recovery. |
| barometer_cold | Native -1073740791 | First assertion `test_barometer_cold.c:110`; fixture supplies 4 barometers and primary2. `system_barometer_cold.c:183` rejects count4 against compact max1. Invalid multi-instance fixture precondition. |
| device_native_log | Timed out; terminated native -1 | Fixture `test_device_native_log.c:10,30–34` supplies2, compact max1. Initial Process statically reaches the contradictory count assertion at `APP/Src/device_native_log.c:114`; this is an inference from code/input, not a printed runtime fault location. Timeout/trap/OS behavior is not proven. |
| system_startup, system_startup_write_verify, system_startup_async_no_explicit_verify, system_startup_no_writes | Native1; each 782 checks/7 failures | First expectation `test_system_startup.c:505`. Mock profile advertises optionalPOWER (`:427–439`) despite implementation_available=0 (`project_flight_config.h:50`). Startup's guarded power initialization (`system_startup.c:549`) leaves it absent; enabled-but-absent optional device becomes degraded (`:718–743`). Power-process calls at test `:713,720` are also correctly excluded by implementation guard. This mock is not the current production profile. |
| optional_gnss_start_explicit_required | Compiler1 | `system_user_alignment_config.h:104` and capability validation `:150`. Runner `:1198` adds requiredmask3 without selecting GNSS: current selectedmask5/GNSSenable0/position0. Correct required-source rejection; positive fixture is inconsistent. |
| logger, logger_estimator_noise_overrides | Native1; each 2106793 checks/421 failures | First expectation `test_logger.c:829` enables excluded GNSS_NATIVE. Covariance (`:957,996`) and ESKF15_BODY_INPUT (`:898`) are excluded by SF6 minimal; StreamConfigure rejects unsupported types (`system_log_policy.c:143–145`). Fairness test uses normaldepth60 (`test_logger.c:892`) against actual56. All failed predicates match between both variants; subsequent checks continue after rejected configuration and cascade. These failures remain FAIL, not a passing replacement for selected logger validation. |

These documented fixture/selection conflicts explain the observed incompatible preconditions and rejections. They do not constitute a complete proof that every failed cascade is harmless, or that valid selected-function recovery, startup and native logging are fully accepted. No new product change or test modification was made to turn any row green. Critical acceptance remains NOT PROVEN.

## Current selected-source coverage obtained

Remaining diagnostic passes include actual SF6 math/backend and cold-pressure backend, SX1281 device/SX1280 HAL and radio instance paths, sensor status/quality, estimator pressure pending and navigation quality, lifecycle and qualified recovery variants, health/telemetry, estimator preparation, no-GNSS optional START, logger snapshot/alignment/streaming and golden serialization. Their exact production source lists, compiler options, check counts and boundaries appear per row in the classified JSON. Many tests use modeled device/time/transport/storage boundaries or alternate compile-time configurations; passing a legacy case name does not prove the named unselected device was exercised.

Two existing independent strict C Host regressions additionally ran at the unchanged current source, **2 passed in 5.71s**: `test_joint_imu_actual_c_mock` executes real MPU6050/core code among its existing eight IMU profiles (ID/reset/readback/SI/clip/epoch/idempotence/error cases); `test_bmp280_core_and_both_bus_adapters_host` executes real BMP280 core and adapter code and compiles both instance transports. Exact compile/run commands and stdout are retained. These are mocked Host sensor regressions, not F1 peripheral or board validation. Existing assertions and compiler-warning settings were retained; these tests' own original options were not relabeled as O2/LTO tests.

Actual storage pressure/FLP results belong to the earlier current-source fixture-closure run, not this prefix diagnostic. No repeated storage run or firmware ARM/analyzer build is claimed here. Production inputs and measured RAM/Flash remain as previously recorded; no RAM, stack, IRQ/HAL, recovery or NRF changes occurred.

## Timeout, permissions and remaining limits

The original `device_native_log` native process failed to return. A diagnostic watchdog was added after detecting the hang, verifying its exact private executable path, PID and start time before termination. Its threshold is60 seconds with5-second polling; this first observed process was already old and terminated after **171.1634852 seconds**, so no 60-second actual run is claimed. The original trap/assertion mechanism was not replaced. A Win32_Process read query was denied; no escalation or permission change was attempted. Only the confirmed own diagnostic executable was terminated. An inaccessible same-name process was left untouched; no user GUI was closed. Other native jobs finished; watchdog exited.

The previously established possible/actual SensorRegister callback evidence is retained unchanged. No call-graph resolver, allowlist, library/frame bound or WCET value was invented. Original stack failure, critical-contract review, IRQ/timebase and bounded recovery/START lock evidence, 20% RAM margin and hardware qualification remain unresolved. Official gate is still FAIL and RET6 acceptance is incomplete.

Full per-case raw matrix, classified matrix, CSV, first-source diagnostics, complete stderr/failed assertion predicates, original-source hashes, timeout identity record, diagnostics scripts and direct sensor-regression logs are under `../evidence/SF6_RET6_diagnostic_continuation/`. All source/GUI changes since checkpoint are zero; only this report/evidence is committed.
