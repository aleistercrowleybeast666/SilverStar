# Joint rework execution status

Execution date: 2026-09-27. This is a work log, not an acceptance certificate.

## Authorization and inputs

The user explicitly requests implementation in FCCG, FLP and GSHC. The subsequent
instruction authorizes committing and pushing all three repositories. The latest
instruction cancels shutdown: do not shut down the computer. The push authorization
overrides the attached task book's older prohibition of push. Flashing, physical
outputs, publishing and alteration of source logs remain
prohibited. SS_0_5_TEST_3 is a read-only firmware/log reference, not an output directory.

Task book and supplied audit reports were extracted without overwriting existing files
to `tests/joint_rework_20260927/inputs/`. Actual logs are in
`D:/stm32_project/SS_0_5_TEST_3/LOG`; decoder/project are in `HARDWARE`.

## Baselines and ownership

- FCCG: d013ae1, application/platform 0.0.12. Coordinator owns common contracts,
  estimator/quality/replay integration, protocol producers, importer and acceptance.
- FLP: c4605f4, application 0.0.4. flp_navigation owns FLP implementation and tests.
- GSHC: cbee51e, application 0.0.3. gshc_readiness owns GSHC implementation and tests.
- sensor_library owns FCCG sensor packages and dedicated sensor tests. Core and
  generator changes are coordinated; shared files have one writer.

Pre-existing untracked FCCG test runs are preserved and excluded from task commits.
No tracked baseline changes were observed. No reset/clean is authorized.

## Contract decisions

- ENU, Hamilton scalar-first q_nb, body to navigation, right-local attitude error.
- ESKF algorithm `silverstar.algorithm.estimator.eskf15`, revision 1;
  nominal p/v/q/bg/ba, error order dp/dv/dtheta/dbg/dba, dimension 15.
- New quality/consistency/supervisor policy revision 3; legacy revision 2 must retain
  its recorded semantics. Application and unrelated wire identities stay independent.
- Calibrated body SI samples precede residual bias subtraction and attitude rotation.
  Coning/sculling compensation has one owner. Historical replay repropagates body data.
- Five aid groups: position EN, position U, velocity EN, velocity U, barometer U.
  Physical validity, quality, admission and update result are distinct facts.
- R is variance: receiver/profile floor first, quality and consistency bounded
  multipliers next, robust multiplier last. No square of a variance multiplier.
- GNSS origin readiness remains stricter than in-flight admission. ACK means accepted;
  READY requires current-session/current-generation fresh authoritative evidence.
- No target timing or new-sensor hardware claims from Host/mock execution.

## Current phase

Latest checkpoint (2026-09-27): all six generated configurations passed their full
Release/Debug build, resource, stack and quality gates. Final C review fixes also
passed all six configurations and affected real Host fixtures; generated source
audit found no differences. The no-logging checker validates actual selection and
absence, with negative probes and unchanged checks for selected logging.
BMI088 Sync400 I2C/SPI is implemented with its licensed configuration image,
explicit synchronization wiring and IRQ/pairing rejection cases. All new drivers
remain HARDWARE_UNVERIFIED; exact results belong in VALIDATION and the sensor report.
GSHC final GUI and package validation is complete. FCCG full Python regression passed.
An opt-in target DWT timing tool passed real ARM and Host checks alongside task/queue
HWM collection. It remains outside the default production graph; target timing
remains unmeasured until a separately authorized bench session.
The user explicitly authorized continuing FLP edits after the earlier automatic
approval rejection. All revision-3 gain/health call sites are now integrated.
Fresh five-log runs for both algorithms, the final actual bridge and the final
483-pass FLP suite have completed. Numerical non-health arrays match the old
results; SS0003 ESKF health correctly ends DEGRADED. Old evidence and original
inputs remain unchanged. Software implementation and gates are complete; new
hardware and field validation remain outstanding. Final Git delivery is verified
against the actual three repository commits and remote heads.

The older entries below are chronological work notes, not current acceptance results.

Implemented shared quality/window/supervisor, real preflight estimator initialization,
ESKF15 pure C plus body-history delayed replay and selected production backend,
ESKF record producers and plugin parameters. Strict ARM target build is in progress;
no target acceptance is claimed until the full resource and stack gates pass.
The first independent C/Python parity cases passed. FLP finished the five original
log imports/replays without source hash changes; SS0002 missing origin remains a failure.
GSHC first complete suite passed 420 tests, with follow-up extended health fields underway.
Generated KF6 Host suite passed 69 executables / 4,387,441 checks. These are interim
results, not the final validation snapshot; exact final commands belong in VALIDATION.md.
Current JY901B quality/readback fixes and new IMU/UBX adapters are being verified in
Host tests. All new devices remain NOT_HARDWARE_VALIDATED.

## Execution environment

Default Windows sandbox process creation fails with `setup refresh had errors`.
Read-only and workspace-local operations use explicitly escalated exec commands;
no system setting, PATH, registry or permission policy is modified.

## Acceptance

IMPLEMENTATION_IN_PROGRESS. FINAL_FLP_VALIDATION_IN_PROGRESS. The user resolved
the earlier four-file approval blockage. NOT_FIELD_VALIDATED.
GSHC has a validated local commit; FCCG/FLP commits and all three pushes await the
final ESKF log comparison. No physical operation or shutdown has occurred.

## Integration checkpoint — 2026-09-27

- ESKF Release and Debug linked ELF, memory, task-stack, artifact, architecture
  (311 checks) and Power of Ten (6240 checks at that snapshot) passed. GCC
  `-fanalyzer` Release passed after explicit initialization of linearization
  temporaries; no warning or resource threshold was disabled. Final regeneration
  and rechecks are still running as sensor and GUI integration finishes.
- The actual ESKF backend test exposed a 144-slot/4 ms history overflow at step
  145. History now stores lossless two-half body input in 64 bytes, with invariant
  source/generation and contiguous start epoch derived from its anchor. 192 slots
  use 12,288 bytes, below the old 12,672 bytes. The 600 ms time window remains;
  bounded trimming handles changing dt. The unchanged 250 Hz/200-step real
  backend fixture passed 1536 checks. Current supported IMU low-g ODR max is
  240 Hz; no target WCET claim follows from these Host results.
- NAV_QUALITY is produced after actual KF6/ESKF updates. New 0x2F events report
  live group state transitions even without successful fusion. Actual update
  commit time owns last_successful_fusion_us; rejected/zero-gain/history replay
  cannot refresh it. 2 s -> DR, 10 s -> INVALID. Unqualified P inflation is not
  used. A later real positive-gain update records reacquisition; the existing
  KF6 controlled outage recovery remains separately logged.
- Hard IMU quality evidence latches INVALID until lifecycle reinitialization;
  subsequent good samples cannot erase a lost inertial interval. Current flight
  consumers now honor invalid navigation without changing action thresholds.
- Real preflight fixtures initialize all three kernels without START (KF6 233,
  Pure INS 226, ESKF 230 checks), plus 1811 quality/supervisor checks. Newest
  backend includes production LoggerBus, EstimatorBus, quality/time interfaces.
- Calibration generation is the real calibration start/reset sequence, separate
  from navigation epoch. Shared JSON has all 35 ESKF parameters, including the
  three actual delays; ESKF receiver sigma multiplier is 1.0, independent of
  legacy KF6 profile scaling. New quality is revision 3; historical revision 2
  retains its old decoder and replay meaning.
- FLP minimal version increment 0.0.4 -> 0.0.5 is required for newly generated
  35-record decoder packages. Original SS_0_5_TEST_3 decoder remains unchanged.
  Actual C producer -> generated exact decoder -> product FLP replay passed
  659 records, maximum full-P difference 1.63e-6. Final five-log regression is
  ongoing and retains divergent/INVALID cases rather than selecting good ends.
- GSHC full suite 425 + 3 subtests and packaged offline startup passed. Sensor
  library work continues on FIFO timing and model-specific initialization.
  Automatic review rejected an extra 320-byte software queue; it was not
  applied. Real Device/INS loops are nominally 1 ms, so the safer implementation
  uses the existing hardware FIFO and SampleBus; target timing remains untested.
- Root complete FCCG pytest is active; its intermediate failures are not waived.
  No commits/pushes/shutdown have occurred yet. They are user-authorized only
  after implementation, validation and review are finished. No physical output,
  flashing, original-log modification or release publishing has occurred.
