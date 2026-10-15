# Fusion timing and blocker closeout — 2026-10-15

This batch implements two distinct KF6/ESKF15 execution modes: current-state
updates without numerical history, and the preserved delayed-history replay.
Legacy replay remains the default. SCG and FLP offer the two named choices and
serialize the actual integer parameter. SF6 and PureINS acquire no fake timing
option. Delayed horizon plus output predictor (mode 2) is still rejected.

Source, receive, application and evaluation epochs remain distinct. Current
admission keeps bounded producer watermarks, age/epoch/calibration checks,
packet/group ordering and transactional numerical faults. It does not pretend
that an old observation was sampled at the current epoch. KF6 retains its
receipt evidence and ESKF uses the current calibrated endpoint gyro with the
then-current bias. Existing model-mismatch and fault latches remain effective.

The immutable v2 wire contract is
`contracts/navigation_fusion_timing_records_v2.json`, SHA256
`257f574479bd3fea5cc4564c7afd00504c39f1f66dda6ad793c34e9b7834f5fd`.
GNSS/BARO/ESKF measurement payloads are 212/100/116 bytes. New declarations bind
the component versions and actual mode; old known revisions retain their
documented execution path. Unknown or mismatched semantics do not gain a
numerical fallback. Normal generation preserves user-owned payloads and refuses
an unproven updated identity; validation used separately named fresh projects.
Production FLP opening still requires the exact decoder and Descriptor through
LogOpenCoordinator, and preserves original log/package bytes.

## Storage pressure and stack input binding

The initial emitted startup-burst-overload writer reproduced a late normal-lane
drop (443 to 444 at frame 13810), failing its original safety expectation.
LoggerTask now drains at most four records between outer service/status work,
retaining per-record decoder/start barriers and checked append/error paths.
Every actual subiteration is counted. No queue, assertion or source-rate
expectation was relaxed. The final same scenario holds at 443 after the finite
startup overload and has no later drops. One intermediate diagnostic fix also
failed the original iteration accounting assertion; that failure is retained.

V18 stack input review keeps the old checker rejection and all existing budgets
and callback restrictions. A new negative case exposed source/dependency-version
mixing; complete ordered compiler-input content tuples now bind each source.
Unknown bytes, missing headers, old graph mixes and altered placement reject.
See the separate stack binding fixture and source review. Linked task reports
do not prove main/MSP/ISR nesting or MCU timing.

The later KF6 tuple rejection is also retained. The unselected SX1278 catalog
adds one physical-device ID and shifts three generated IDs; the exact header
already used by ESKF required new reviewed KF6 source/header pairings. One
generated decoder-profile version changes only two identity arrays. The final
22 exact tuples were reviewed without relaxing any source or callback check.
The unselected dirty catalog manifest is archived to make this input explicit;
these runs are not an SX1278 integration or a clean-catalog release result.

## Validation scope

- SCG generator, provenance, GUI and stack tests: 72 passed.
- After the final KF6 tuple registration, all 41 stack tests passed again,
  including the original negative graph-mixing and missing-input tests.
- FLP targeted timing/current/legacy/GUI and real C O0/O2 parity plus both actual
  backend traces: 271 passed. The first closeout invocation had 259 passes and
  12 setup errors because the explicit SCG-root prerequisite was omitted; it is
  retained. No product fallback or test expectation was changed.
- Both emitted ESKF current and legacy complete Host runs passed: 81 executables,
  4,414,064 checks, zero failures, 11 compile-pass, 18 expected compile-fail and
  10 explicit N/A cases per run. These are complete individual runs, not stitched
  selected passes. The earlier selected-only runs are labelled separately.
- Actual ARM compilation/link, linked artifact and source-graph checks are
  recorded per generated configuration. Current ESKF and final KF6 builds also
  executed real first-party GCC -fanalyzer compilation, rather than syntax-only
  checks. Current-mode O0 links and absence of replay/history symbols are in
  the separately committed memory evidence. Legacy KF6 main SRAM fits the
  unchanged 102400-byte reviewed budget after CPU-only queue placement.
- Original replay differential traces remain byte-identical: KF6 10,187,496
  bytes and ESKF15 202,188 bytes. Their old/new binaries, fixtures, commands,
  source receipts and precise comparison scope are retained.
- Actual generated Power-of-Ten text targets exit 0 for the final recorded
  configurations. They explicitly report critical-contract review NOT_PROVEN;
  recommendations and historical failed outputs have not been hidden.

One ESKF build/artifact attempt encountered conflicting output writes; its
failed receipts remain. A serial retry of build/artifact/actual emitted stack
target passed on the same exact source inputs. Driver setup errors (including
an initially nonexistent BuildAction member) are retained and are not reported
as executed checker results. A separately attempted KF6 legacy O0 build
overflows Flash by 1088 bytes; it is not a passing configuration. The required
current-mode O0 links did pass, as recorded in the memory batch.

This is not a full FLP-suite PASS: the known save-dialog hang and six baseline
revision-fixture failures are preserved in prior reports. Current execution and
backend parity retain APPROXIMATE fidelity; no trace establishes flight accuracy.

## Remaining work and acceptance boundary

The delayed fusion horizon/output predictor and active ESKF15 GNSS recovery
policy are NOT IMPLEMENTED by this batch. The covariance congruence utility is
committed separately and is not activated by these timing paths. Horizon
transactions, original KF6 interval-Q semantics, full output-P timing,
versioned records, recovery receive/replay evidence and the outage/fault matrix
still need implementation and validation before either feature can be offered.
The planning documents do not substitute for those results. ESKF20's extra five
states remain unresolved; no empty backend/plugin is registered. Invariant EKF
and iterated EKF are distinct in the interface plan.

Tool success establishes only the recorded source/configuration/artifact scope.
Manual critical-contract acceptance, whole-program recursion/return/data-scope
review, full task/library/indirect/dynamic/main/MSP/ISR stack bounds, STM32 WCET,
navigation accuracy and hardware/flight qualification remain NOT PROVEN. No
serial, DAP, flash, reset/halt, device or actuator operation occurred. No push,
tag, release, frozen v0.1.2 modification or old-workspace cleanup occurred.

Complete commands, versions, exact dirty source snapshots, configurations,
exit codes, all retained failure/skip details, logs and artifact hashes are in
`manifest.json` and `evidence.zip`. The small task inventory retains ownership
and purpose; cleanup is not authorized.
