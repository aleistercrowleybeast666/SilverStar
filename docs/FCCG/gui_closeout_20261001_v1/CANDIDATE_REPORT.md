# Single-KF6 GUI candidate checkpoint

2026-10-01, CHD Windows `D:\python_software\SilverStar`. Baseline clean HEAD was `2175d95f20dbecde96f67fd902ed54d873e39755`; no reset or overwrite of user firmware occurred. This report follows, without rewriting, the historical [stage-one report](REPORT.md). The known default single-KF6 software blockers tested below are closed. Ordered multi-instance cold backup remains unfinished. This is not FIELD READY, zero-bug assurance or permission to operate hardware.

## Candidate and changes

Independent output: `.work/SCG_Closeout_2175d95_v4`, with Flight_Controller, Ground_Station and Log directories. The recorded input is `input_configuration.ssproject`: reference F407 KF6/JY901B/NEO-M9N, fixed gravity plus known direction, E28 link and F103 Ground UART. The user must generate their own final external firmware project. v1–v4 validation roots are preserved.

SCG means **System Configuration & Generation / 系统配置与生成**. The visible titles, About text and new `SCG.py`/`silverstar-scg` entry points reflect that identity; FCCG import/schema/paths/CLI compatibility remains. Magnetic selection/calibration/TF calibration persistence entrances are hidden or blocked consistently with generated descriptor/header policy. Retained implementations and December restoration tests are in [deferred features](../RELEASE_DEFERRED_FEATURES.md).

Legacy opening now preserves the loaded model and original descriptor bytes without automatic navigation reconciliation. The explicit migration dialog creates a KF6/fixed-pair copy in a new empty directory outside the original tree. `Compatibility/Legacy_Original.ssproject` preserves exact original bytes; `Legacy_Loaded.ssproject` and `Migration.json` preserve all loaded settings and the declared change. Direction review is required. Source logs and decoder packages stay unchanged in the original tree. Cancel, occupied destination, nested destination, failed save and reopen are covered. Old magnetic overrides cannot silently enable release generation.

The independent Ground Configuration navigation page is removed; PC/UART and Ground radio fields are in telemetry. Both hardware pages share BoardHardwarePage and existing/import/save actions. IMU precedes GNSS, telemetry has no index, and Checks/检测 replaces Advanced. Native reentry, rapid selection, cancel, save/reopen, two-target generation, radio validation and hardware import/resource paths have regression evidence.

PoT uses the F Prime-inspired C adaptation. Entire-target zero candidates is a new hard error; per-function recommendations remain nonblocking. Other nine rule checks and authorized exceptions are unchanged. CSV export uses the native Save dialog, real physical lines/function scopes, full paths, reason and configuration/source identities; cancellation, Unicode, empty findings, write failure and stale report are covered. Exit 0 retains **NOT_PROVEN/manual acceptance pending**. `kf6_report_v4.json` and `.csv` are actual export artifacts from this candidate, not a synthetic successful acceptance record. Ground's complete raw checker output is retained; no Ground JSON/CSV export is claimed (the current GUI report is Flight-targeted, and Ground has no local SilverStar.ssproject).

Flash and each RAM region are separate: <10% spare red, 10–20% inclusive yellow, >20% green, showing bytes and percentages with a green-margin recommendation. Color does not block generation or prove memory safety. FLP identity/reentry changes retain the strict exact decoder/Descriptor production opening through LogOpenCoordinator; no fallback decoding or log mutation was added. GSHC retains protocol/readiness fixes while removing the magnetic tab.

## Executed validation

Each named run has its complete log and command/exit/environment/log hash JSON here. Individual source diffs, the final source hash inventory, exact generated v4 inventory and tool versions provide auditable identity. Results belong to their recorded outputs; no stitched full-suite pass is asserted.

| Run | Actual result |
| --- | --- |
| `generate_v4` | Fresh isolated Flight and Ground generation, exit 0 |
| `kf6_arm_v4`, `ground_arm_v4` | Actual ARM compile/link, exit 0; Ground retains four known newlib warnings |
| `kf6_analyzer_v4` | Real first-party -fanalyzer compilation/link in distinct StaticAnalysis output, exit 0 |
| `kf6_host_v4` | 72 executables, 4,393,820 checks, zero failures; 7 positive compile cases and 17 expected compile failures. Synthetic logger integrity cases passed. |
| `kf6_linked_v4` | Architecture 328 checks/zero failures, linked artifact check and existing stack report, exit 0 |
| `kf6_pot_v4` | Exit 0: 108 files, 2608 functions, 1595 eligible runtime candidates, 741 nonblocking review recommendations; critical-contract review NOT_PROVEN |
| `ground_pot_v4` | Exit 0: 15 files, 148 functions, 106 candidates, 34 recommendations; critical-contract review NOT_PROVEN |
| `candidate_evidence` | Identical zero-candidate fixture: baseline checker exits 0; current direct -File invocation exits 1. Complete before/after logs/hashes retained. Actual KF6 report hashes current sources. |
| `checker_report_final` | 119 passed: checker, export/memory/release, migration, bilingual key parity and scoped rule-8 cases |
| `migration_gui` | 31 passed, including explicit migration, original preservation and supported schema round trips |
| `gui_final` | 36 passed in the recorded Windows Qt selection before later migration/report additions |
| `gui_qa_final` | 26 passed; one erroneous dot-sourcing zero-target probe failed. Correct direct invocation subsequently passed as `zero_direct_final` and before/after evidence. Other GUI QA cases were not represented as a fresh complete rerun. |
| `hardware_regressions` | 38 passed, 2 scoped conditional fixture failures caused by the newly authorized global zero guard. Those fixtures now contain a separate real boundary assertion and all four scoped cases passed in `checker_report_final`; no nine-rule checker weakening. |
| `gshc_ui_corrected` | 26 passed, native Windows Qt. Earlier protocol selection had 116 passes/2 stale UI expectation failures and OpenGL warnings; full all-tests rerun is not claimed. |
| `flp_full_corrected` | 16 passed, 3 deliberate scope deselections; exact generated v2 KF6 decoder production open/cache/replay and negative pairs plus identity/reentry GUI cases |
| `flp_candidate_v4` | 3 passed, 3 scope deselections: exact fresh v4 decoder production open/replay and identity/recorded-configuration rejection; synthetic SSLOG records |

Historical failed attempts, expectation corrections and skips remain available. The old future magnetic-triad success expectation was changed in the owning Host template to the explicitly authorized first-release compile rejection; v3 and v4 full Host runs then passed. No failed safety expectation was hidden. An evidence helper initially attempted a Ground export despite its missing target-local descriptor, failed, and was corrected to export only the actual GUI Flight target; no generated Ground configuration was invented to make that helper succeed.

Linked KF6 memory: Flash 315,444 used / 208,844 spare (39.83%); main SRAM 101,264 used / 29,808 spare (22.74%); CCM 55,432 used / 10,104 spare (15.42%, yellow). Heap reserved and runtime allocation symbols are zero in the artifact check. This differs slightly from earlier firmware's SRAM figure because generated first-release descriptors changed; it does not invalidate or rewrite the earlier evidence. The existing task stack report estimates remain incomplete for full library paths, dynamic frames, indirect calls, MSP and ISR nesting.

Native Windows Qt captures in `native_qt/` cover Chinese/English devices, navigation, telemetry, both hardware pages and Checks. Three Chinese captures were actually inspected. These preceded the final minor translated ordering note/module label correction. There was no mouse-driven complete visual acceptance. At 1180 px width the long Chinese SCG heading can wrap; Ground core identification inherits an MCU part string from existing inventory. These cosmetic/inventory presentation items remain review notes, not a claim of flawless UI. Offscreen subprocess tests are functional tests only.

## Remaining boundary and stop

The ordered cold-backup requirement is **not implemented**. IMU initializes/polls configured sources and locks before alignment; GNSS uses warm-online forward selection; barometer stays primary. Activation/settling, long-fault debounce and stale-source rejection are incomplete. JY901B barometer shares the active IMU UART. See [exact source gap and necessary continuation](COLD_BACKUP_GAP.md). Do not depend on multiple configured sensors as accepted cold backups today.

No MCU/TF/serial bench test, flashing, START, actuator action, field log acquisition or flight qualification occurred. Whole critical-contract review, full stack/ISR/WCET and hardware evidence remain NOT PROVEN. No push, tag or Release occurred. Quota was unknown and was not treated as a quota stop. Known single-KF6 software fixes are checkpointed; new program modifications stop here so multi-instance work cannot indefinitely delay today's single-source logging candidate. All commands finished naturally before handoff.
