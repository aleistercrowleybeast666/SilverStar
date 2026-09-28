# FLP closeout: table stretch, 3D markers, measurement timing

## Changes

- `ui/pages/replay.py`: keep the comparison header in ResizeToContents / final-column
  Stretch mode at construction and after each result refresh. Previously a global
  resizeColumnsToContents pass replaced the intended persistent sizing policy.
- `ui/pages/state_estimation.py`: apply the same policy to sequential updates.
- `ui/pages/data_explorer.py`: apply it after dynamic channel/record columns are populated.
  Other tables are unchanged. Horizontal scrolling remains AsNeeded.
- `core/visual_semantics.py`: shared 3D diameters are Deploy = 0.035 * extent,
  Landing = 0.030 * extent, Current = 0.010 * extent. Extent retains its existing
  finite/minimum-one handling. Deploy grows 2.5x and Landing 3x. No 2D marker or
  trajectory line width changes. GUI and 3D exports consume the shared definition.
- `ui/pages/charts.py`: obtain initial marker sizes from that shared definition.
- `plugins/algorithms/kf6/plugin.py`: reconstruct measurement application from
  availability instead of a decimated ESTIMATOR snapshot.
- `tests/test_closeout.py`: endpoint/inter-step/delayed-receipt scheduling, GNSS-first
  ordering, once-only consumption, out-of-range measurement exclusion, empty input,
  and four consecutive table refreshes including final-column geometry.
- `tests/test_flight_state_pages.py`: verify new permanent marker diameters and
  unchanged Current size using the existing GUI/geometry regression coverage.

## Timing evidence

Old behavior built sequence -> first ESTIMATOR (or KF6_STATE) timestamp dictionaries.
A matching sequence used that snapshot timestamp; only unmatched sequences used the
first inertial endpoint >= sample time. Decimated snapshots therefore delayed some
updates, with a different policy for sequences omitted by snapshot downsampling.

New behavior uses the first inertial endpoint >= max(sample_timestamp_us,
receive_timestamp_us). Updates still execute after a successful Predict, GNSS then
Baro, and are consumed once. No snapshot timestamp or fixed offset is used. Timing
remains reconstructed/inferred; this is not a claim of exact host task scheduling.

Read-only FCCG template evidence (not a claim that this is SS0002's exact build):
`plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/estimator_task.c` copies
GNSS receive time at line 1423 and Baro receive time at line 1833. Future sample
checks precede updates. Prediction processing calls Predict, GnssUpdate,
BarometerUpdate, then SnapshotPublish. The JY901B barometer adapter assigns both
sample and receive from PressureTimestampUs; the NEO-M9N adapter assigns both
from lastUpdate_us. Measurement ages are computed at update from state time minus
sample time and later copied into the published snapshot; they must not be
subtracted from an arbitrary later snapshot timestamp as though newly recomputed.

The deterministic case has 10/20/30/40 ms endpoints, a Baro sample available at
13 ms and a referencing ESTIMATOR snapshot at 40 ms: application is 20 ms.
A sample received exactly at 20 ms applies there; one sampled at 21 ms but received
at 31 ms applies at 40 ms. GNSS received at 19 ms precedes Baro at the 20 ms step.

## Validation limits

No SS0002.BIN was found in the current workspace, including hidden files. No online
search was performed. **SS0002 actual-log regression was not executed**, so there
are no real-log before/after KF6 RMSE/max/mean numbers and no claim of phase-error
elimination. Pure INS source and its math are unchanged; existing frozen baseline
and replay tests provide synthetic regression evidence only.

Remaining actual-flight residuals, if any, require a matching log/package and may
involve float32 rounding, operation order, covariance symmetry/truncation, or finer
receive/task scheduling. None of those were changed in this patch. Protocols,
parameters/defaults, Q/R/P0, NIS, calibration, Data Quality, source trajectories,
project format, version and external repositories are unchanged.


## Executed checks

Focused algorithm/actual-parameter/flight/replay tests: 49 passed in 10.11 s.
Final closeout scheduling/table tests: 2 passed in 1.48 s.
Full suite: 190 passed, 8 skipped in 61.53 s. Skips require explicitly supplied
historical actual logs. Ruff over src/tests/tools and git diff --check passed.
The patch is uncommitted; test outputs remain under ignored .acceptance/closeout,
with no release, version directory, or generated output added to Git.
