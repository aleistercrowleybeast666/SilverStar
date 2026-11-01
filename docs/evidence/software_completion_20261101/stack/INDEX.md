# Strict software stack work: evidence index

The v5 independent B build passed the exact-case software stack gates for five
models and both Release/Debug configurations. See [the final report](v5/DELIVERY_ZH.md)
and [machine-readable results](v5/final-summary.json). Earlier versions below are
retained with their actual scopes; they are not stitched into a final run.
Task context256 bytes and minimum spare margin256 bytes are unchanged.
The F407 main-SRAM review budget remains102400 bytes. No hardware was operated.

| Version | Actual scope and result |
| --- | --- |
| v1 | Initial strict rejection and parser counterexamples. Conditional indirect branches, local BL helpers, assembler FUNC extents and tail-return handling were exercised. `whole-probe-v3.log` contains an **invalid low estimate** caused by mistaken noreturn inference; it must not be used as a bound. The later v4-named diagnostic JSONs in this directory correct that defect but remain unadmitted diagnostics. |
| v2 | Three analysis configurations, Release/Debug: six real ARM builds succeeded; installation Debug artifact gate failed with SRAM102444 over102400. Three emitted Power-of-Ten text gates passed. Architecture gates rejected missing exact generated control owners. Those owners were repaired in the generator. Debug DWARF plus-uconst parsing has a pre-failure and post-regression record. |
| v3 | Same three analysis configurations in two independent directories: twelve real ARM builds and artifact checks passed. Six raw-byte comparisons were identical, with510 F407,540 installation and546 H743 artifacts per configuration. This source epoch precedes the final controller Nm interface change, so it is not final acceptance. Actual candidate runtime/inputs were captured without enrollment. Strict CLI task-only/whole-program-NP counterexample failed before the fix and passed after. |
| v4 | First final-source five-case normal generation completed, then the full source snapshot correctly rejected an overlapping `ground_usb_control.py` modification. No ARM build was started for this version. Keep `generation-a/source-snapshot.json` and `generation-a.log` as source-drift evidence. |
| v5 | Final default F407, installation F407, BMI088/ESKF20 H743, actual10ms PID and actual10ms LQR cases. A and B were normally generated from the current catalog; real delivery bundles used the strict control-task importer. Both source snapshots have no generation-time drift. Ten A/B raw-artifact pairs (5256 artifacts per replica) are identical. B ten normal ARM builds and artifact gates, five architecture/text Power10/real ARM analyzer runs, and ten strict whole-program stack runs all exited0. Seven deliberate mutations were rejected and restored, then the restored positive exited0. The complete14-file stack regression ran252 passes; independent command-receipt repetition also252 passes. Hardware measurement and whole-firmware Power10 critical acceptance remain outside this result. |

`v3/inspection-v1/*.json` are explicitly marked `not_acceptance` and
`requires_manual_case_admission`. The production checker never writes a proof
case. Fixed case enrollment is a reviewed source change. Independent B must
match A's complete object/stack-report/dependency/ELF/map bytes and cannot enroll
or normalize away a mismatch.

The exact legacy user-input CubeMX tree is
`.work/h7_20261025/verified_release/CubeMX_StaticInput`; it is read-only input and
was not edited. New generated projects and analysis scripts are confined to
`.work/0.1.3-software-completion-20261101/stack/{v1,v2,v3,v4,v5}`. Original inputs,
old evidence and inaccessible historical directories are not cleanup targets.
The initial read-only search's permission errors are retained in
`v1/old-candidate-search-permission-errors.log`; access controls were not changed.

No tool result here establishes measured STM32 stack high-water marks, WCET,
interrupt latency, electrical actuator output, navigation accuracy or flight
qualification. The software proof covers its exact selected compiler/source
closure and architectural exception model. Unlisted or modified configurations
remain unproven until separately reviewed; strict CLI returns nonzero for a
whole-program NOT PROVEN result even if legacy task-only fields pass.
