# SilverStar 0.1.0 Round 5 field qualification report

Repository baseline: `9412dd4a39901b601f98bd83134fa9897e18fcac` (`main`, Round 4 completion). Round 5 preserves the 0.1.0 product version and the AIR/GSP/SSLOG wire identities.

## Decision

**SOFTWARE FIELD CANDIDATE READY; HARDWARE ACTIONS PENDING. `FIELD TEST READY: NO`.** The current host has no connected F407 Flight board, F103 GS_SS1 board or debug probe. The enumerated serial ports were Bluetooth virtual ports, not evidence of a SilverStar MCU. No new firmware was flashed, no real TF card was exercised, and no live AIR/GSP or SSLOG capture was made. The [field checklist](../field/FIELD_TEST_CHECKLIST_0_1_0.md) gives the remaining bench actions and evidence format. This report does not authorize connecting live ignition or deployment loads.

The software reference was freshly generated through the FCCG project and multi-target generation APIs under ignored `.work/round5/final/Round5_Field_Qualification/`. It contains `SilverStar.ssproject`, the exact root decoder, `Flight_Controller/`, `Ground_Station/`, each target's VS Code workspace and `Log/`. The [frozen reference](../field/FIELD_TEST_REFERENCE.md) lists all six SHA-256 identities and the actual configuration. Generated project files are candidate evidence in disposable `.work/`, not repository source.

## Automated software evidence

| Gate | Result |
| --- | --- |
| F407 Flight ARM Release build/link, ELF/MAP/HEX/BIN | PASS, ARM GCC 14.3.1 |
| F103 Ground UART ARM build/link, ELF/MAP/BIN | PASS, ARM GCC 14.3.1 |
| Flight `artifact-check`, `memory-report`, `stack-report`, `architecture-check` | PASS; architecture 328 checks, 0 failures; all linked task stacks budgeted |
| Flight `static-analysis` (`-fanalyzer` in isolated build) | PASS on freshly generated final candidate |
| Flight Power of Ten | PASS; 6,946 checks, 108 first-party C files, 2,596 functions, 0 failures |
| Ground Power of Ten | PASS; 455 checks, 15 first-party C files, 145 functions, 0 failures |
| Generated Flight Host tests | PASS; 72 executables, 4,393,820 checks, 0 failures; 8 compile-pass and 16 expected compile-reject cases. Synthetic SSLOG logger-integrity audit passed exact decoder matching. |
| FCCG tests | PASS; all 81 modules in fresh pytest processes, 619 passed, 1 skipped. Six initially failing modules passed in a second isolated sweep after fixes. |
| GSHC full tests | PASS; 435 passed, 3 subtests passed |
| FLP full tests (run from `apps/FLP`) | PASS; 476 passed, 22 skipped. Hardware/log-specific manual tests need explicit actual inputs. |
| Monorepo integration | PASS; 8 tests, including passive GSP capture, its output-path guard and documentation links |
| Ruff | Round 5 production Python, new tools and new integration test PASS under configured rules; repository-wide critical `E4,E7,E9,F` rules PASS. The optional unrestricted rule set still reports pre-existing style debt in older test modules and other unchanged code; those files were not bulk-reformatted. |
| Python compileall | PASS for FCCG, GSHC, FLP, tools and integration tests |
| `git diff --check` | PASS before commit; repeat at final commit |

The Flight analyzer first found paths in first-party magnetometer tombstone load, M9N UBX configuration serialization and bounded vector normalization. The fixes latch the tombstone branch once and initialize bounded local arrays. They add no static RAM, queue, history or task stack. A Host regression checks tombstone state after an active calibration. The storage test harness now writes its log through the actual temporary project policy. The fixes were re-generated into the final candidate before the builds and hashes were recorded.

The FCCG full-suite run revealed that source-package export was traversing the application's ignored `.work/` tree. This could package large generated projects and make the deterministic archive test impractical. The exporter now excludes `.work` at every depth; a small source-package regression verifies generated files are absent. This Python-only fix does not alter the frozen firmware or decoder bytes. FCCG tests also require `--basetemp` within `apps/FCCG/.work/` because some fixtures intentionally apply the application's workspace policy. The two initially failing algorithm tests passed when run with that authorized location; the full suite was restarted there. The production policy was not relaxed.

Two configuration tests still expected Round 4's retired Gravity/Magnetic TRIAD user-facing selection and automatic fallback to Gravity/Known Yaw. The current strategy contract requires explicit reselection when more than one legal strategy remains, and the UI presents Vector Constraints and External Attitude Source. The assertions now check that actual behavior; all nine configuration-reconcile tests passed. No Alignment algorithm or selection policy was changed for this test repair.

A later sweep found tests assuming Generate remained on the Build page, that imported historical source hashes would remain equal to subsequently edited console/SSLOG sources, and that a synthetic format 9 project with the retired device shape would auto-migrate. Those assertions now check target-scoped Build actions, unchanged import provenance, current-format roundtrip/rejection of that old device shape and preservation of conflicting legacy board-owned storage files. The board-MCU test now uses a project-resolved catalog view, so its injected incompatibility reaches the current validator. A single long-lived pytest process stopped making progress after 288 cases, after many GUI/build cases; the 30-case sensor-generation module passed separately. Every FCCG test module was then run in a fresh process with an app-local ignored basetemp and per-module log to avoid cross-module Qt/process state retention. The stalled one-process invocation is not counted as a pass.

That isolated sweep identified a real export-path defect: the UI checked Flight target readiness under `Flight_Controller/`, but the decoder export service still looked for generated descriptors at the Project Root. The service now verifies the target-local descriptors and the canonical root decoder before writing an export, while retaining the direct flat-project service path used by older internal tests. The GUI export regression now creates a current multi-target Project Root and raises immediately on an error instead of opening an unattended modal dialog. Historical reference-import tests were corrected to apply the 35-record legacy overlay only to its matching wire records; the current SSLOG schema has 38 records, including three later evidence records. Other repaired assertions now use the current platform API header, source graph, plugin catalog, device slots and target workspace name. The initial 75 passing modules plus all six repaired modules passed in isolated processes: **619 tests passed, one reference-firmware test skipped because that read-only repository is absent from this host**. No production AIR, GSP or SSLOG wire layout changed.

## Static resource evidence

`BuildAudit_Run` used each selected exact MCU's official memory limits and the final ELF/MAP/`.su` files. No allocator symbols were linked in the Flight artifact.

| Target | Flash | Main SRAM | CCMRAM | `.su` files / largest function frame |
| --- | ---: | ---: | ---: | ---: |
| STM32F407VET6 Flight | 312,776 / 524,288 B | 101,280 / 131,072 B | 55,432 / 65,536 B | 152 / 2,032 B |
| STM32F103C8T6 Ground UART | 20,860 / 65,536 B | 14,128 / 20,480 B | n/a | 37 / 296 B |

All eight Flight linked static task-stack budgets passed: Device, INS, Estimator, Flight, Logger, Serial, Telemetry and Idle. The smallest linked margin is Idle 256 B; the Flight task margin is 496 B. Ground BuildAudit found `.su` evidence for all non-startup objects and no dynamic stack frame; its 296 B figure is a single-function maximum, not a whole-call-chain or ISR-nesting bound. These are compiler/linker audits, not measured on-target stack high-water marks. The Round 5 fixes did not increase first-party static storage. The F103 link prints ordinary newlib-nano syscall stub warnings; the link and exact-MCU audit pass. No board runtime result is inferred from that link.

The frozen JY901B rate plan is raw 200 Hz, mechanization aggregation 2, effective propagation 100 Hz, configured maximum measurement delay 270 ms, and maximum replay 27 steps. The KF6 history requirement is 61 of 144 slots. Physical ODR, observed propagation and replay high-water marks must be checked on the F407 bench.

## Workspace hygiene

The tracked repository is about 29 MiB. The frozen Round 5 candidate, machine-readable audit and test logs remain under ignored `.work/round5/` (about 0.17 GiB). Duplicate Round 5 generation and pytest basetemp directories were removed after their checks completed. Verified older pytest basetemp directories were also removed from `apps/FCCG/.work/`; its remaining roughly 1.72 GiB is ignored earlier-round reference and analysis material that was preserved. No generated firmware, cache, actual log or source fixture was added to Git.

## Hardware evidence levels

| Evidence area | Current status | Required next evidence |
| --- | --- | --- |
| Legacy GS_SS1 PCB topology | **HARDWARE VALIDATED REFERENCE** from GS_SS1 commit `7fe0f61142c7360f7dbae0ac0000036315631320` and its prior board operation | Preserve provenance; this does not validate the new SilverStar Ground binary. |
| New F103 Ground firmware on GS_SS1 | **SOFTWARE VALIDATED; HARDWARE ACTION REQUIRED** | Flash the frozen hash, boot, observe GSP/USART1 and SX128x, exercise radio TX/RX, counters, reconnect and bounded queue pressure. |
| F407 Flight with JY901B, M9N, TF and E28 | **SOFTWARE VALIDATED; HARDWARE ACTION REQUIRED** | Safe-output cold/warm boot, bounded startup, ready/fail cases, calibration/alignment and task diagnostics. |
| JY901B target/factory/legal-candidate startup | **HARDWARE ACTION REQUIRED** | Compare actual read/diff/write/reconnect/sample behavior; verify no default NVM SAVE. |
| M9N target/factory/legal-candidate and NMEA rescue | **HARDWARE ACTION REQUIRED** | Verify UBX identity/NAV-PVT and RAM-only PUBX,41 path on receiver without persistent changes. |
| Real TF mission storage | **HARDWARE ACTION REQUIRED** | Verify START admission, separate mission directories, snapshot/readback/final status and safe card-failure behavior. |
| Flight ↔ AIR ↔ Ground ↔ GSP/UART ↔ GSHC | **HARDWARE ACTION REQUIRED** | End-to-end commands/ACK/status, link loss/recovery, GSP counters and START rejection/acceptance. |
| GSHC magnetometer calibration | **CONDITIONAL HARDWARE ACTION** | This frozen Flight selection has no dedicated magnetometer plugin or magnetic alignment constraint. JY901B's internal field capability exists, but raw field logging is disabled. If a supported calibration stream is selected, obtain physical identity/generation, collect and fit, Apply/Save/Read and wrong-device reject. GSHC software suite passes; it is not physical qualification. |
| Vector Constraints and External Attitude | **HARDWARE ACTION REQUIRED** | Measure known pose, calibration identity, quality record `0x28`; separately smoke JY901B external quaternion and yaw authority if used. |
| Actual SSLOG → FLP | **ACTUAL_LOG_REQUIRED** | Copy original TF log into Project Root `Log/`, open root in FLP with exact decoder, inspect `0x28`/`0x29` and conditional `0x2A`, plots, gaps and export manifest. |
| F407/F103 target timing | **MEASUREMENT_PENDING** | Collect TimingBench/diagnostic service, replay, queue, logger and stack HWM evidence. Observed maxima must not be called formal WCET. |
| USB CDC and unselected BMP280/BMP390/MS5611/MMC5983MA/LIS3MDL | **HARDWARE_UNVERIFIED** | Not dependencies of this UART/JY901B/M9N reference; qualify separately if selected. |

No physical fault injection or real pyro operation was performed. Bench storage and link faults must use safe, reversible setup per the checklist. Software Host tests exercise the underlying bounded and integrity contracts, but cannot substitute for the actual card and radio path.

## Known defects and qualification limit

No P0/P1 software defect is known after the listed gates. The earlier analyzer findings were corrected and rechecked. Remaining `FIELD TEST READY` blockers are missing **new-firmware board integration**, physical JY901B/M9N/TF/AIR/GSP evidence, actual SSLOG→FLP validation, actual calibration generation and target timing observations. Mark each checklist action `PASS` only with timestamped raw evidence tied to the frozen hashes. Any new P0/P1 finding requires a regression, fix, new clean generation, complete affected gates and new hashes.

SilverStar stays at product version `0.1.0`. This is a field-test software candidate, **not a tag, GitHub Release or public v0.1.0 release**.
