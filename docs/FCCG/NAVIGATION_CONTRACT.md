# Navigation, quality, time, logging and preparation contract

This is the current cross-component contract for FCCG, FLP and GSHC. The identical
machine-readable copy is [navigation_v1.json](../../contracts/navigation_v1.json).
Numerical defaults belong to plugin parameter declarations; generated C constants,
saved project values and the exact decoder carry their resolved values. Measured
acceptance results, hashes and resource margins belong in [VALIDATION](VALIDATION.md).

## Identity and ownership

Platform 0.0.12, project format 12 and decoder/project-semantics 1.2 retain their
identities. New decoders require FLP 0.0.5. Quality policy revision 3 and ESKF revision 1
are explicit decoder declarations. Original packages and recordings retain their original
revision and cannot silently acquire current behavior. Algorithm IDs are Pure INS/None 0,
KF6 1 and ESKF15 2. Only selected sources enter the generated graph.

`system_navigation_backend.h` is Core's public ESKF boundary. The selected backend owns
its state and workspace. Core does not include ESKF private headers or disguise ESKF as
KF6. `SYSTEM_BUILD_ESTIMATOR_ENABLED` is the legacy KF6 source lock; the fusion selector
is authoritative for the navigation path. `EstimatorTask_SnapshotGet` exposes a bounded
common navigation snapshot. Preparation snapshots do not increment prediction counters.

## ESKF mathematical conventions

Coordinates are East, North, Up. Hamilton quaternion `q_nb = [w,x,y,z]` rotates body
vectors into navigation coordinates. Nominal state order is `[p(3),v(3),q(4),bg(3),ba(3)]`;
the 15-dimensional error order is `[dp,dv,dtheta,dbg,dba]`. Position and velocity errors
are navigation-frame vectors; the attitude error is **right, local/body**:
`q_true = q_nominal * Exp(dtheta)`. Gyro and accelerometer biases are body-frame residuals
after the selected Calibration correction. Gyro units are rad/s; acceleration is m/s²;
gravity is `[0,0,-g]`. Acceleration input is specific force, so level rest is `+g` Up.

Two calibrated body half-interval means drive coning/sculling propagation. Bias is
subtracted separately from each half. Attitude is propagated by a normalized quaternion
exponential; the body increment is rotated using the current nominal orientation.
The continuous error model contains `dp_dot=dv`, `dv_dot=-R[f]x*dtheta-R*dba`,
`dtheta_dot=-[omega]x*dtheta-dbg` and random-walk biases. The implementation builds a
bounded second-order transition and discrete noise covariance for each interval.
Noise parameters are amplitude densities and are squared once into spectral density.
P0 entries are covariance diagonals, not standard deviations; cross terms retain the
corresponding products of state units.

GNSS is partitioned into Pos EN, Pos U, Vel EN and Vel U; Baro U is a fifth independent
group. Position predicts `p + R*lever_b`; velocity predicts
`v + R*((omega-bg) cross lever_b)`. Barometer observes position Up and does not inherit
the GNSS lever arm. The right-local measurement Jacobian includes attitude and gyro-bias
lever-arm terms. Zero and nonzero arms are supported.

Each accepted update uses Joseph covariance form, injects `dq=Exp(dtheta)` on the right,
then applies the SO(3) right-Jacobian reset to every covariance block. q/-q represent the
same attitude. Initialization requires a unit quaternion, finite nominal state and
positive covariance. Invalid input, bad covariance, excessive correction or bias,
nonfinite gain, and failed replay are explicit results. Candidate state/P commit together
only on success; covariance validation never modifies P to obtain a pass. A large attitude
error is not promised to recover through small-angle updates.

## Quality, variance and consistency

Raw presence and physical validity are different. Online/fresh native GNSS with supported
and asserted fixOK, valid fix type, finite values and valid accuracy can qualify for
fusion. Bad CRC/framing never produces a usable driver sample. Invalid/no-fix/stale input
is rejected before the numerical update. Strict preflight-origin collection remains
separate from in-flight soft degradation.

For a physically valid solution with `n` satellites, the satellite **variance** factor is
`min(4, 1 + 0.5 * max(0, 6-n)^2)`. Thus 6/5/4 satellites give 1/1.5/3. Satellite count
alone does not close all groups. Sigma floors are applied first; variance is then multiplied
once by quality, Pos EN consistency and robust factors, in that order. ESKF's receiver
sigma multiplier is 1.0. Historical KF6 retains its independent 1.25 convention. No factor
is squared a second time.

Two constant-memory position/velocity closure windows have 10 s duration and 5 s stagger.
They use receiver-native GNSS time, measured horizontal displacement and trapezoidal
velocity integration, including interpolated boundary portions. Duplicate/late epochs
do not add evidence; source/generation changes, missing native time and gaps restart
warmup. Completed valid evidence has 6 s TTL. Invalid new completion does not refresh
older evidence. A closure threshold of 10 m produces at most fourfold Pos EN variance.
It cannot establish which GNSS quantity is wrong, permanently reject position, reset a
state, or modify the other four groups. Persistent small velocity bias cannot accumulate
across unlimited task duration. Current KF6 exposes enable, gap, threshold and bounded
variance parameters; six historical revision-2 controls are explicitly read-only/retired.

## IMU evidence and timing

Every body interval retains actual endpoints, duration, source, calibration generation
and quality flags. `sample_epoch_us`, `receive_us`, `measurement_us`, `evaluation_us` and
`output_us` are distinct. Calibration generation is the correction's real start/reset
sequence, not a renamed navigation timestamp.

NEAR_RANGE and TIME_UNCERTAIN inflate process **variance** fourfold. CLIPPED,
TIME_DISCONTINUITY, RANGE_UNVERIFIED and PAIR_SKEW are hard evidence: affected propagation
cannot be marked healthy. A lost inertial interval latches INVALID until explicit
navigation reinitialization. A later good sample cannot repair unobserved motion.
HISTORY_RESET identifies lifecycle boundaries. JY901B signs are decoded as signed data;
near-range sign changes are reported, never heuristically flipped. Hardware-reported
attitude used for initialization is distinct from runtime attitude authority.

ESKF replays saved **body input**, not old attitude-rotated ENU delta velocity. Insertion
at the measurement epoch reruns propagation with updated quaternion and biases. The
static history is bounded to 600 ms, with separate position/velocity/barometer delays
limited to 550 ms. The 270 ms velocity default is an experimental configured delay,
not a hardware property of M9N. Continuous source/generation is required. Missing early
history, overflow, duplicates, numerical errors and callback failure are explicit; past
measurements are never applied to the present as a substitute.

The replay engine has bounded body/event counts and a fixed maximum operation count.
It keeps one anchor and one working state, with compact body history, instead of full
15x15 covariance at every IMU epoch. Workspace is static caller-owned CPU memory.
DMA buffers stay in main SRAM. An internal replay never emits live health/recovery side
effects; the outer successful insertion commits those once.

## Fusion supervision and navigation preparation

Each of five groups records receive, physically-valid, attempted, successfully-fused and
recovery times, last result/reason, NIS, effective variance factor and recovery count.
Success means a real committed, admitted, physically valid update with finite positive
gain. Arrival, attempted correction, zero gain and internal replay are not success.
The success clock is the outer update's evaluation time. Identical sequence values from
different physical sources are not mistaken for a duplicate.

Overall health reflects the selected required groups. A recent soft-weighted update,
variance multiplier above one, or physically-invalid latest observation makes overall
health DEGRADED even while another valid update has kept the fusion timeout recent.
Non-required groups do not affect this aggregate. INVALID and all-required-groups dead
reckoning take precedence; a genuine later nominal observation can clear soft degradation.
The reported multiplier includes satellite quality, Pos EN-only consistency and the
actual robust factor exactly once. Zero-innovation updates with finite nonzero gain
remain legitimate fusion; a float32 gain that has become entirely zero is not.

After 2 s without successful fusion a required group enters dead reckoning; after 10 s
it makes navigation INVALID. Ordinary physically valid robust updates continue and a
real later commit records reacquisition. Supervisor timeout never forces invalid data,
inflates covariance arbitrarily or repeatedly reinitializes. KF6's separately bounded
communication-outage recovery retains its own result and event. Pure INS has no required
auxiliary groups and reports dead-reckoning navigation instead of claiming fusion health.

Navigation preparation is an actual firmware transaction: device readiness, supported
Calibration, static attitude, current GNSS fix, collected GNSS origin, barometer origin
and initialized selected kernel must satisfy its declared requirement mask. ALIGN_START
validates synchronously; FlightTask collects samples and initializes navigation. START
checks current preparation and freshness again. The kernel already has valid q/P before
START; starting resets runtime counters/history. Stale origin/attitude snapshots and ACKs
cannot grant readiness. Failure reasons remain visible and SS0002-style premature START
is rejected.

GSHC negotiates navigation extension version 1 with a new nonzero connection nonce.
The AIR frame remains 9 bytes and retains its existing CRC policy. Session, generation,
sequence expansion and per-field freshness prevent replay of old UI state. Preparation
expires after 2 s; current health and slower detail fields have their distinct declared
TTLs. Unsupported older firmware displays unknown/unsupported, not green readiness.
The real gateway hardware path is still unverified this round.

## Log and offline interpretation

The old 28 record IDs and field layouts are immutable. Seven new records use identities
0x21–0x27 for ESKF state, periodic full-P parts, initial state, initial-P parts, body input,
measurement operation and navigation quality. Full P uses four bounded parts; no enlarged
queue slot or oversized single record is introduced. Initial state/P and the actual
body/measurement stream are required when ESKF logging is selected. Periodic full P is
optional and disabled by default. Cadence is applied once to a complete P snapshot.
Group fusion-state changes use event 0x2F through the real producer/codec path.

Logger bootstrap/admission, drop counters, strict CRC and arbitrary byte-stream guarantees
remain governed by [the storage contract](platform/details/STORAGE_AND_FLIGHT_LOG.md).
Different queue streams can interleave; FLP reassembles P by its identity/time/part index,
never by adjacency to the preceding state record. Missing/duplicate/mixed parts, CRC
failures and record gaps remain diagnosable. Logged effective variance and result refer
to the actual operation, not a later display reconstruction.

RECORDED is onboard output; FAITHFUL requires the exact revision, initial conditions and
complete required operation evidence. WHAT_IF changes the offline algorithm/configuration;
APPROXIMATE additionally identifies missing evidence or declared reconstruction. Old JY901B
logs lack the new body-quality/native-time record contract, so an ESKF study of those logs
is not faithful ESKF reproduction. Missing origin is not synthesized silently. Export
captures its chosen source/configuration before background work; GUI selection changes
do not mutate that job. No ground truth means recorded differences, not position error.

## Device maturity and next validation

Device manifests declare real interfaces, consumed qualified capabilities, generated
resources and fixed supported initialization profiles. Generic selection validation keeps
raw and selected qualified capability routes on the same physical instance. A device with
no quaternion/barometer cannot acquire those capabilities from an unselected JY901B header.
The selected MCU emits device-neutral build capability glue from actual selected devices.

Initialization distinguishes attempted write, response, readback match and persistence.
Default startup uses RAM configuration and does not blindly write NVM. Explicit persistence
requires supported storage semantics and its own result; unsupported readback stays
unsupported. New IMU/UBX models are HARDWARE_UNVERIFIED regardless of mock/compiler results.
The current real platform is JY901B + NEO-M9N. Software acceptance is a prerequisite for
a separate controlled bench session, not flight approval. This round does not flash,
drive actuators or establish target WCET, real task HWM or radio-gateway compatibility.
