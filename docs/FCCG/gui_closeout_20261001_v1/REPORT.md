# GUI closeout — stage-one handoff

2026-10-01, CHD Windows workspace `D:\python_software\SilverStar`. Baseline HEAD verified clean at `2175d95f20dbecde96f67fd902ed54d873e39755`; current changes are **uncommitted**, preserved without reset. This is a partial engineering checkpoint requested by the parent task, not full GUI acceptance or FIELD READY. No commands remain running at handoff. No hardware, flashing, START, actuator, push, tag or Release operation occurred.

## Today’s KF6 logging path

Default KF6 configuration can generate isolated Flight/F407 and Ground/F103 targets and both compile/link on ARM GCC 14.3.1. Real `-fanalyzer` compilation/linking also passed for the F407 output. Production FLP opening/replay with the **fresh v2 generated decoder and synthetic SSLOG records**, plus wrong-identity/recorded-configuration rejection, passed in the final FLP selection (the two reported failures are GUI title/string expectations). This establishes a software path, not actual TF logs, serial readiness, bench integration or flight qualification. The user must generate the final field firmware; `.work` outputs are validation candidates only.

The software acceptance blockers at this checkpoint are the full Host rerun after the release restriction, the direct-invocation zero-assertion negative gate test, remaining GUI expectations, and unfinished ordered cold-backup switching. Existing firmware SaveConfig/UART/IMU fixes were not reverted. Real stack/ISR/WCET and hardware evidence remain unproven.

## Implemented changes

- Visible SCG title and compatible `SCG.py` / `silverstar-scg` entry points; FCCG paths, old launcher/CLI and schemas retained. Full meaning: System Configuration & Generation（系统配置与生成）. GSHC/FLP window names aligned.
- Magnetic device choices/capabilities and GSHC calibration tab hidden. Generated descriptors have no magnetic endpoints; generated headers reject enable overrides. Existing implementation and schemas retained. Legacy magnetic configurations are blocked with compatibility errors, without automatic navigation rewrites. Fixed gravity + known-direction pair and external-attitude alignment remain; explicit draft reset requires confirmation.
- PC/interface/UART fields moved into telemetry; independent Ground configuration navigation removed. Ground and Flight hardware pages construct from the same `BoardHardwarePage` class, with Ground-specific data/unsupported controls. IMU precedes GNSS; telemetry label drops the index.
- Checks label, F Prime-inspired PoT information/error distinction, report export via native Save dialog, function/path/line/reason/config/source identities, stale-source rejection and global NOT_PROVEN row. Whole-target zero candidates added as a hard checker protection; other nine rule checks retained. Source hashes use the exact scanned bytes and work without `Get-FileHash`.
- Flash and each RAM region separately display bytes/spare percentage; <10% red, 10–20% inclusive yellow, >20% green, with a green-margin recommendation. This does not certify stack margin.
- FLP publishes project-root identity only after successful log opening, guards busy reentry, keeps prior identity on cancel/failure, and distinguishes saved root from unsaved analysis session with resize elision/tooltips. Strict decoder/Descriptor opening remains through `LogOpenCoordinator`.

## Executed evidence

Every named run has a complete `.log` and command/exit/environment/log-hash `.json` beside this report. Failed attempts and skips remain intact; no combined full-suite pass is claimed.

| Run | Recorded result |
| --- | --- |
| `gui_final` | 36 passed; Windows Qt platform |
| `checker_final` | 106 passed; checker + first-release regression selection before the additional direct zero-target test |
| `generate_v2`, `generate_v3` | Both targets freshly generated in distinct versioned roots |
| `kf6_arm_v2`, `ground_arm_v2` | Exit 0, actual ARM compilation/linking; Ground retains 4 known newlib warnings |
| `kf6_analyzer_v2` | Exit 0, actual first-party `-fanalyzer` compilation and link in separate StaticAnalysis output |
| `kf6_architecture_v2` | Exit 0; 328 checks, zero failures |
| `kf6_pot_v2` | Exit 0; 108 files, 2608 functions, 1595 syntactically eligible candidates, 741 nonblocking recommendations; NOT_PROVEN/manual pending |
| `ground_pot_v2` | Exit 0; 15 files, 148 functions, 106 candidates, 34 recommendations; NOT_PROVEN/manual pending |
| `kf6_host_v2` | Failed at old `capability_future_triad` expected-success case after many prior tests. Template now requires compile failure as explicitly approved; v3 contains the revised test, but full Host rerun has **not** executed. |
| `gui_qa_final` | 26 passed, 1 failed. Native popups, rapid reentry, save/reopen and two-target GUI generation passed. New zero-target negative test called a dot-sourcing probe; checker prints the hard failure but probe exits 0. Must test direct `-File` invocation before accepting the new guard. |
| `gshc_regression` | 116 passed, 2 failed, 107 warnings, 3 subtests passed. Failures expected old four tabs and old title. Windows OpenGL warnings occurred; no claim of 3D visual acceptance. |
| `gshc_ui_final` | 25 passed, 1 failed; remaining English-switch title expectation still uses `SilverStar_GSHC`. |
| `flp_regression` | 10 passed, 1 failed, 6 skipped because explicit generated decoder fixture was absent. This was retained and rerun with an explicit fresh decoder. |
| `flp_final` | 14 passed, 2 failed, 3 deliberately deselected (imported/Pure INS/ESKF scope). Failures: old About window title expectation, and new unsaved-session test uses a different word order from translation. Generated KF6 package production-open/cache/replay and two negative decoding cases passed; records remain synthetic. |

Earlier operator errors used an incorrect test name or basetemp outside the service workspace. They are recorded as failures; workspace safety was preserved and correct isolated test directories used subsequently. v1 PoT failed due missing `Get-FileHash`; the owning template was corrected and v2 rerun successfully. No failing safety expectation was weakened to obtain a pass.

`source_snapshot.diff`, `source_snapshot_sha256.json`, `tool_versions.json`, input configuration and `generated_v2_sha256.json` / `generated_v3_sha256.json` identify the dirty source and generated inputs/artifacts. Later runs also carry their individual source diffs. v2 ARM/analyzer results belong to v2; v3 is generated but has not been built or Host-tested. Do not attribute v2 results to an unexecuted v3 full suite. Reproduction helpers are copied here; copy them back into repository `.work/` to reproduce their original root-relative invocation. Original `.work` v1/v2/v3 candidates are preserved.

## Remaining work and exact continuation

1. Correct only the stale GSHC/FLP title and unsaved-word-order expectations; rerun relevant tests. Fix the new zero-target test to invoke the checker directly, then record baseline/new rejection evidence. No source claim depends on the currently failing probe.
2. Run `host-tests` in `.work/SCG_Closeout_2175d95_v3/Flight_Controller` and resolve genuine regressions. The previous failure log is complete; do not represent the revised expected rejection as a full Host pass.
3. Ordered long-fault IMU/GNSS/barometer cold-backup switching is **not implemented**. Existing selector limitations remain. No multi-radio automatic backup is implemented.
4. Convenient GUI migration for legacy dedicated magnetic selections is unfinished. The model is preserved and generation is blocked; fixed-vector explicit draft migration exists. Finish a deliberate copy/migration workflow and persistence/import regressions.
5. Complete resource/imported IOC/existing hardware regressions and whole-file review; finish memory/artifact/stack-report evidence with existing tools. Artifact/stack reports have not been run in this stage. No new stack-proof tooling was added.
6. Native Qt interaction tests ran, but no mouse-driven screenshot inspection or complete human visual acceptance occurred. Finish visible first-release QA and update About/current documentation wording still referring to the old generator identity. No whole historical evidence rename is intended.
7. Review and locally commit the coherent closeout stage only with honest remaining-failure evidence; no local commit was created in this partial handoff. Quota was unknown and no quota stop was asserted.

See [deferred features](../RELEASE_DEFERRED_FEATURES.md). Parent can immediately continue the authorized work; all current commands exited naturally without cancellation.
