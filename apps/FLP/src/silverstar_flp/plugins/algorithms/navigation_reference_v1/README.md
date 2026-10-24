# Navigation host reference v1

This package provides actual ESKF20, InEKF15 and InEKF20 float64 host replay
implementations. InEKF means **invariant**, not iterated. InEKF15 has no magnetic
state or magnetic prerequisite. No InEKF9 filter is registered. Existing INS,
SF6, KF6 and ESKF15 IDs and implementations remain unchanged.

These implementations are independently versioned copies of the audited
`apps/SCG/experiments/navigation_0_1_3` Python models. The historical experiment
files remain intact. Relative imports make this package self contained; two
nominal-flow functions are copied into `navigation_flow.py`, without exposing
the old nine-state filter. The adjoining historical model notes describe the
mathematics, not proof of recorded input readiness or firmware equivalence.

## Entry points

FLP's ordinary algorithm registry, `Replay_Execute`, cancellation/progress,
`ReplayResultStore`, and immutable project artifact codec are reused. The three
new plugins keep empty `firmware_component_ids`: SCG parameter conversion
does not imply Recorded readiness without complete initial-state and input
operation contracts. Their descriptions
and labels identify offline host references. MCU/float32 parity is NOT_PROVEN.

For a headless run from the installed FLP environment:

```text
python -m silverstar_flp.plugins.algorithms.navigation_reference_v1.cli --log input.sslog --decoder exact.ssdecoder --configuration explicit.json --model inekf15 --cache decoder-cache --output new-derived.json
```

Use `--mode what_if` for explicit vector or magnetic observations or changed
initial attitude. Output must be a new JSON file. Its companion immutable
artifact generation contains the result; it is not a recorded SSLOG. The input
log is opened through `LogOpenCoordinator` with the exact package and Descriptor.
Manifest and result retain source log, package and configuration hashes,
original integer input timestamps, selected calibration evidence, engine/model
identity and `Derived/user configuration` provenance.

## SCG actual-parameter conversion

For the three new firmware manifests, `FirmwareConfiguration_WhatIfBuild`
reads actual parameters from the exact opened decoder package and returns a
What-if ReplayRequest. It checks the packaged manifest fingerprint, complete
field set, units, representations, storage types and exact binary32 values.
No defaults fill missing fields. The conversion requires software-validation,
initialization and GNSS/IMU-colocation confirmations. It preserves canonical
noise order, error-state-order diagonal P0, biases, installation quaternion,
I/D and observation gates. The source actual parameter group and input
identity remain in `configuration_origin` and the resulting diagnostics.

Supply explicit `initial_navigation` with `q_nb_wxyz`,
`origin_velocity_enu_mps` and `provenance: "user_configuration"`. As in the C
backend, these inputs are converted to binary32; the quaternion is normalized
after checking squared norm in [0.5, 1.5], and local-origin position is zero.
This is a supplied initial condition, not a recovered complete recorded
snapshot. Observation rows retain explicit user time/source/frame provenance;
gate and magnetic field limits come from the actual parameters and conflicting
overrides are rejected. Hard/soft calibration and trusted event timing are
still explicit What-if inputs. InEKF15 needs no magnetic fields.

The CLI accepts `--scg-initialization supplied.json --mode what_if` instead
of `--configuration`. The supplied JSON has exactly `initial_navigation`
and `observations`, with optional explicit `body_input_assumption`. It never
converts native GNSS/MAG records automatically.
The optional `configuration_origin` extension is accepted only when the
configuration agrees with the full conversion, and it requires What-if mode.
No recorded-configuration claim follows from firmware membership: complete
augmented initial state/P/input-operation records are still absent, and
20-state magnetic installation/calibration/time evidence is not fully bound.

All nonzero IMU quality flags remain unsupported, including near-range and
unknown bits; importing firmware parameters does not relax body-input gates.

## Body input evidence and half intervals

The three new algorithms use their own thin body adapter; the legacy four
retain their existing readers. Even-duration `ESKF15_BODY_INPUT` can use its
recorded source/generation/quality and matching frozen initial snapshot. Odd
legacy body intervals are rejected because their original half boundary was
floored; there is no recorded proof that these are equal-half means.

`IMU_CORRECTED` reconstruction supports subsample counts 1 and 2. Count 1
uses the endpoint producer arithmetic in binary32. Count 2 integrates the
piecewise-linear samples at their actual relative microsecond times over
two equal physical halves, then rounds each mean to binary32. Absolute
uint64 clocks stay integers. Nonpositive or over-20-ms intervals and all
nonzero quality flags are rejected. This is not firmware parity.

The source-end bound comes from the selected body/corrected input records,
independent of other output channel cadence. Recorded landing still truncates
the replay. The selected recorded SYSTEM_CONFIG must specify aggregation.

Current `IMU_CORRECTED` record version 0 has source/validity/correction but
no quality flags or calibration generation. Missing evidence blocks
ordinary Offline replay. To request a What-if reconstruction explicitly, add
`body_input_assumption: {"provenance": "user_configuration", "quality_flags": 0,
"calibration_generation": N}` with N equal to the selected frozen calibration
start_sequence. Neither CLI nor converter supplies this object. It cannot
override recorded bad quality, missing source, or inconsistent generation.
The result retains it as Derived/unverified user assumption and never exact
recorded body input. Mean integration correctness does not prove those
missing observations or the operation sequence.

## Explicit configuration contract

The only plugin parameter is the complete JSON string `configuration_json`.
Its empty value is intentionally invalid: there are no invented priors or
recorded defaults. JSON duplicate keys, nonfinite numbers and documents over
4 MiB are rejected. Schema `silverstar.navigation.host-reference/1` requires the
following fields. Optional `body_input_assumption` is What-if only; the SCG
conversion also carries `configuration_origin`:

- `schema`: the literal identifier above.
- `initial`: `rotation` (3x3 SO(3), body to ENU), `position` (ENU m, IMU
  origin), `velocity` (ENU m/s, IMU origin), `gyro_bias` (rad/s), `accel_bias`
  (m/s²), and full symmetric positive definite `covariance` (15x15 or 20x20).
  ESKF20 and InEKF20 additionally require `installation` (3x3 SO(3), magnetic
  sensor to selected IMU), `inclination` and `declination` (rad). These are
  explicit offline user configuration, never recorded installation proof.
- `gravity_enu`: three components in m/s². No gravity value is guessed.
- `noise_density`: four named length-three arrays:
  `gyro_radps_per_sqrt_hz`, `accel_mps2_per_sqrt_hz`,
  `gyro_bias_rw_radps2_per_sqrt_hz`, `accel_bias_rw_mps3_per_sqrt_hz`.
  They are canonical gyro, accelerometer, gyro-bias random walk,
  accelerometer-bias random walk order. The ESKF20 adapter explicitly swaps the
  first two blocks for its historical kernel; InEKF uses canonical order.
- `observations`: list, possibly empty, at most 4096 explicit What-if rows.

Covariance error order is ESKF20 `[p,v,theta,bg,ba,gamma,I,D]`, InEKF15
`[phi,nu,rho,zeta_g,zeta_a]`, InEKF20 the latter plus `[gamma,I,D]`.
The full covariance is retained and exported. Without magnetic measurements,
20-state filters do not synthesize an observation; existing cross-covariance
can still change extra states during a supplied vector update.

Each observation has exactly `kind` (`position`, `velocity`, or `magnetic`),
`epoch`, `source`, `calibration`, `sample_us`, `receive_us`, `sequence`,
`time_basis` (`explicit_cotimed_assumption`), `provenance`
(`user_configuration`), `value`, `covariance`, and positive `gate` (NIS).
Identities and sequence are uint32; clocks are uint64 microseconds. Every
position/velocity row in this schema **means IMU-origin ENU position in metres
or velocity in metres/second**, with 3x3 measurement covariance in squared
units. SCG antenna lever arms are not applied. Native GNSS antenna positions
must not be relabelled as these values. The complete schema fixes this meaning
without asking users to manufacture an additional recorded proof field.

Magnetic rows also require `stage` (1: physical sensor sample),
`hard_iron_uT`, symmetric positive definite `soft_iron`, positive
`reference_strength_uT`, and explicit `[lo,hi]` `ratio_bounds`. The adapter
computes `S(raw-bias)` and `S R S^T`, applies the amplitude check before NIS,
and applies installation A only inside the model. It rejects other stages to
prevent silent double correction. InEKF15 rejects magnetic rows altogether.

## Readiness and time

The adapter reuses ESKF15's body-input reader and selected frozen IMU
calibration contract. Missing semantic context, parse identity, INITIAL_STATE,
START, correction validity, source identity, calibration evidence, continuity
or finite body vectors blocks execution. Exact body records must agree with
their frozen ESKF15 initial state's source/generation. Corrected-IMU fallback
reports the selected calibration snapshot generation honestly; it does not
claim absent per-record fields were logged. Nonzero body quality flags are
currently unsupported rather than silently reusing unported scaling.

Each complete IMU pair spans 1..20000 integer microseconds. Two calibrated
half means are propagated for equal `(end_us-start_us)/2e6` seconds, including
fractional half-microseconds. State publication is transactional for the pair;
the integer endpoint anchors model time once. Output has an initial row and
one row per pair at the original endpoint, with an explicit row-to-input
interval map. No floating-point timestamp equality or rounded midpoint is
used to admit observations.

Only co-timed endpoint observations are supported. Delayed data returns
`DELAYED_UNSUPPORTED`; future, duplicate, reversed and identity-mismatched
events are not fused. Valid NIS/field/correction rejections consume once.
Each observation group has an independent ledger with a fixed bound source
and calibration identity. Bounded replay and multisource arbitration are
separate future capabilities, not hidden receive-time retiming.

MAG_NATIVE currently lacks sufficient hard/soft-only and measurement-time
provenance for automatic admission. A `field_b` name is not frame/calibration
proof; GSHC coarse installation is not silently applied. Native GNSS and MAG
records therefore are not automatically converted into trusted observations.
Explicit supplied rows are What-if assumptions only and preserve their
original sample/receive timestamps and provenance in the result.

The JSON text editor has been statically checked but no GUI was launched.
Headless tests exercise exact opening, the engine lifecycle, persistence and
the CLI. Neither those tests nor synthetic model results qualify firmware,
hardware timing, flight accuracy or calibrated magnetic readiness.
