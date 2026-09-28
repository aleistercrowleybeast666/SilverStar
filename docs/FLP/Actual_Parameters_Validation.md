# Actual parameter migration validation — 2026-09-12

## Scope and contract

Only package/parameter/configuration plumbing changed. Application version stays 0.0.2;
core INS mechanization, KF6 filter equations, SSLOG framing/Record decoding, measurement
scheduling, Calibration/Alignment, Data Quality and trajectory frontend are unchanged.
Package and Project Semantics are 1.2 only; Record Catalog remains 1.0; `.ssflp` is v3.
Old packages and multiplier projects are rejected with no migration.

The final FCCG property is `firmware_algorithm_parameters`; project-side `algorithm_parameters`
is a different map. FLP validated the actually FCCG-generated package
`D:/python_software/SilverStar_FCCG/tests/artifacts/parameters24/final/AlgorithmParametersFinal.ssdecoder`
SHA-256 `cfa1a2125e5346bf2e57930c5dfccff317c7029b9755a2fb3faba62eda68a5ac`:
package minor 2, semantics 65538, KF6 21 values and INS 1 value. It has no matching actual flight
log in the supplied artifacts, so this is package validity evidence only.

Removed relative-default fields: `p0_scale`, `gnss_position_r_scale`,
`gnss_velocity_r_scale`, `baro_r_scale`. There were no other default-relative multipliers in
Pure INS. `nis_max_r_scale` is the real dimensionless soft-weighting limit and remains actual.

## Actual parameter inventory

Pure INS exposes only `gravity_mps2`: default 9.78 m/s², representation `value`, range [1,20].
KF6 declares the following FCCG-compatible defaults; firmware values are loaded independently
from the exact package and may differ. Resolved package values are binary32 and preserved exactly.

| ID | Offline actual default | Unit | Representation |
|---|---:|---|---|
| `gravity_mps2` | 9.78 | m/s^2 | value |
| `p0_position_e` | 4.0 | m^2 | covariance_diagonal |
| `p0_position_n` | 4.0 | m^2 | covariance_diagonal |
| `p0_position_u` | 9.0 | m^2 | covariance_diagonal |
| `p0_velocity_e` | 0.25 | m^2/s^2 | covariance_diagonal |
| `p0_velocity_n` | 0.25 | m^2/s^2 | covariance_diagonal |
| `p0_velocity_u` | 0.25 | m^2/s^2 | covariance_diagonal |
| `process_accel_std_e` | 1.5 | m/s^2 | sigma |
| `process_accel_std_n` | 1.5 | m/s^2 | sigma |
| `process_accel_std_u` | 2.0 | m/s^2 | sigma |
| `gnss_position_std_horizontal` | 1.5 | m | sigma |
| `gnss_position_std_vertical` | 2.5 | m | sigma |
| `gnss_velocity_std` | 0.15 | m/s | sigma |
| `baro_std_m` | 5.0 | m | sigma |
| `nis_1d_soft` | 6.635 | 1 | value |
| `nis_1d_hard` | 10.828 | 1 | value |
| `nis_2d_soft` | 9.21 | 1 | value |
| `nis_2d_hard` | 13.816 | 1 | value |
| `nis_3d_soft` | 11.345 | 1 | value |
| `nis_3d_hard` | 16.266 | 1 | value |
| `nis_max_r_scale` | 10.0 | 1 | value |

Ranges/precision/order and sigma/variance definitions are checked against the frozen FCCG schema
snapshots in `tests/fixtures/parameter_contracts`. No label-based matching occurs. NIS hard must
exceed soft. P0 parameters are covariance floors, GNSS parameters are sigma floors, and barometer
R retains native and origin uncertainty. Static parameters never replace dynamic accuracy.

## Recorded, What-if, Project and Export

Recorded Configuration requires onboard membership plus complete, valid firmware values.
Provenance is exactly `Firmware build configuration from .ssdecoder`; plugin/header defaults
cannot fill missing fields. Onboard What-if clones firmware actual values; absent algorithms use
plugin actual defaults. Reset labels distinguish these origins. Display rounding never changes
an unedited actual value. Project v3 saves run configurations and the unsubmitted draft, validates
plugin/schema identities and provenance, and restores actual values. Export includes firmware
sets, replay actual parameters, metadata/units/representation, plugin version, source and fidelity.

A changed uncertainty floor needs enough recorded information to repeat the original preparation.
Barometer edits use a uniquely matched native sample and the logged origin sigma. GNSS native
uncertainty is matched by audited semantic device/instance, exact sample timestamp and sequence;
missing or ambiguous matches fail. A matching timestamp from another device is never accepted.
When frozen GNSS initialization or a lowered P0 cannot be reconstructed from a floor-clamped
aggregate, replay explicitly reports missing dynamic uncertainty. It does not invent a covariance,
ignore the edit, alter alignment, or tune Q/R to fit recorded curves.

## Numerical regression

The independently matched synthetic 1.2 log/Descriptor passes `LogOpenCoordinator` with mandatory
calibration. It contains 10 seconds of varying 100 Hz corrected IMU and 20 Hz barometer inputs.
Each algorithm produces 500 outputs. Reference outputs were frozen from the pre-migration Git
plugin code before comparison; they are Python regression references, not firmware Host Golden.
All produced channels (including covariance, innovations, NIS and update results) match exactly.

| Algorithm | Position max/RMSE/P95/final (m) | Velocity max/RMSE/P95/final (m/s) | Lag |
|---|---|---|---|
| Pure INS | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 samples / 0 ms |
| KF6 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 samples / 0 ms |

Quaternion components also match exactly. Lag is cross-correlation of varying vertical velocity;
a separate stationary fixture verifies both corrected-IMU and recorded-increment paths bit for bit.
The 1.2 package value override tests prove gravity/Q/P0 are applied and barometer sigma edits
change the solution while preserving all timestamps and recorded inputs.

## Actual-flight limitation and next validation

The historical `SS0000.BIN` used the 1.1 package SHA-256
`d5d208c77215369e613c2df79177c09a46db1d6cff97be96fd1f91d0627f773f`.
At final inspection the external LOG folder instead contained `SS0001.BIN`, SHA-256
`9d94da8736381d8432c4c24b969c54ba8b4faffd9cac3772a959614b88f1575c`.
Its read-only Descriptor check confirmed package 1.1, generation hash prefix
`578c60b6bf6bb6c3183e828b3af88a8f`. Production intentionally refuses 1.1; substituting the
newly generated 1.2 package would break Descriptor identity. FLP did not modify either external
log/package. No claim is made that the real KF6 phase lead has disappeared.

With a matching actual 1.2 flight, first run Recorded Configuration and compare max/RMSE/P95/final
and lag. If lead remains, inspect measurement timestamp, prediction/update order, baro arrival/index,
P0, first-update timing and dt handling. That is a separate timing investigation; no tuning or
algorithm/timing changes were used to mask a phase difference. Fidelity remains APPROXIMATE.

## Verification and workspace

Focused protocol/parameter/UI/cleanup run: 70 passed in 5.96 s (before final additional regressions).
Final full suite: **182 passed, 8 skipped in 33.93 s**. Skips are explicit historical actual-log
opt-in gates. Final focused parameter run: **27 passed in 2.95 s**. The preceding focused
parameter/cleanup/document-link run passed all 32 cases in 5.96 s.
Ruff passed over src/tests/tools; all source files compile; `main.py --version` returned 0.0.2.
Actual parameter UI screenshots were inspected in English/light and Chinese/dark. The offscreen
QA process required explicit system-font registration; application code was unchanged.

Retired 46 audited historical test directories: 2,397 generated files, 86,042,656 bytes, including
mistakenly tracked synthetic artefacts. Source/fixture references were checked before retirement;
source files and actual external logs/packages were preserved. Deletions remain visible in Git.
No shutdown was executed or scheduled in this round.

Automatic approval review refused the broader request to delete `main.zip` and all current
`parameters25` evidence directories, citing potential source-input/evidence loss. Those remain;
subsequent cleanup removed another 86 permitted cache paths using the existing conservative tool
and excluded all current evidence. No
workaround deletion was attempted. Main source changes and historical generated-file removals
remain uncommitted for review.
