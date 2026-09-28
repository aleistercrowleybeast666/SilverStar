# Display columns, trajectory phases, and Data Quality

## Semantic array columns

`core/semantic_columns.py` supplies audited SilverStar labels during Project Semantics channel
construction. Valid explicit Catalog `columns` always win, even if their labels are numeric.
Stable aliases still reference the exact same immutable TimeSeries as their raw channels.
Flight, Replay, State Estimation, Data Explorer, CSV, and PNG inherit this shared metadata;
GIF and 3D consume the same ENU position and WXYZ attitude channels.

- ENU position/velocity/acceleration: E, N, U.
- Body acceleration/angular rate/magnetic field/increments: X, Y, Z.
- q_nb, q_raw, quaternion_wxyz: W, X, Y, Z.
- Euler: Roll, Pitch, Yaw.
- Audited KF6 state: xE, xN, xU, vE, vN, vU.
- Audited KF6 covariance diagonal: PxE, PxN, PxU, PvE, PvN, PvU.
- Unknown arrays: [0], [1], [2], ...; never infer axes from dimension alone.

KF6 uses **position first**. The current `navigation_kf.c` copies velocity from state[3] and
updates position in state[0:3]. The x symbols here denote the same position coordinates that the
existing offline plugin calls p. A velocity-first label would misrepresent current recorded data;
no numerical reordering or firmware/algorithm change is made. Internal IDs remain language-neutral.

## Shared display geometry

`TrajectoryPhaseSegments_Build` in `core/trajectory.py` creates separate immutable drawing
segments. An event on a sample shares that sample between phases. An event between adjacent,
valid, finite, normally spaced position samples creates a linear timestamp-interpolated drawing
point shared by both phases. Multiple phase events in one interval are supported.

The drawing threshold is `max(2.5 * median(positive timestamp deltas),
trajectory_gap_tolerance_us)` in microseconds; the optional metadata tolerance defaults to zero.
This is a per-series display tolerance, not an algorithm input or global sequence-gap threshold.
An invalid sample, repeated timestamp, or timestamp interval above the threshold breaks the line.
No interpolation crosses that break. Event markers follow the same interpolation guard; the
existing nearest-event scheduling tolerance is allowed only outside valid coverage.

OpenGL, trajectory PNG, and GIF share the builder and phase-value assembler. The GUI caches
segments when preparing a source; per-segment downsampling keeps both endpoints and real breaks.
NaN separator vertices keep distinct continuous runs separate in line strips. GIF frames slice
precomputed shared geometry. Origin subtraction, interpolation, cropping, and downsampling never
write into a source dataset or algorithm result. No quaternion interpolation is introduced.
Normal mission geometry remains bounded by START and Landing; raw exports retain all samples.

## Record integrity and channel continuity

`DataQualitySummary` preserves legacy sequence counters and adds explicit `gap_segments`,
`missing_ids` / `missing_sequence_ids`, immutable `sequence_gaps`, `structural_integrity`, and
`mission_record_continuity`. Overview shows a compact bilingual summary; Data Explorer's existing
diagnostic tab includes expected/actual sequence, missing count, file offset, timestamp, and phase.

Classification uses both adjacent accepted-record timestamps and the START file offset. Only
fully evidenced pre-START gaps receive `before_start`; crossing START, mission gaps, post-Landing
gaps, and insufficient evidence stay distinct. Unknown evidence never becomes a continuous claim.
The container adds adjacent timestamp/offset provenance without changing its decoding or recovery.

Queue values are the maximum observed recorded cumulative STATS/SAMPLE/HEALTH counters; repeated
snapshots are never summed. Missing telemetry yields null / an em dash. Logger event occurrences
remain a separate `logger_overflow_event_count`. Queue counters are not missing sequence IDs and
are not assumed one-to-one with dropped records. Counter reset/wrap is not reconstructed into a
lifetime total. A structurally valid log with only evidenced startup sequence gaps is
`startup_drops` (Valid with startup record drops), not corrupted or unusable.

A global missing record can belong to any producer. It therefore never splits every channel.
Flight reports active-position timestamp gaps, invalid samples, and its break threshold separately.
Export Manifest includes record quality, queue counters, per-gap evidence, column IDs, and
per-exported-channel cadence quality. A record-sequence continuity claim does not prove every
sensor's sample continuity or exact algorithm reproduction.

## Current real-log gate

The opt-in gate `tests/test_current_log_manual.py` locks external `LOG/SS0000.BIN` and its exact
`HARDWARE/SS_0_5_TEST_0.ssdecoder` by SHA-256. See [Testing.md](Testing.md) for invocation.
Expected current facts: 35,617 valid records; zero CRC/length/resync/unknown/decode errors;
3 sequence-gap segments / 12 missing IDs, all before START; Logger queue counter 39; IMU queue
counter 0; ready NONE identity calibration; online/no-fix GNSS; finite ~25 Hz KF6 and ~100 Hz
Pure INS positions with continuous mission coverage. This compatibility/display gate is separate
from the historical corrupted SS0014 gate and from SS0007/SS_TEST_0 numerical Golden gates.
