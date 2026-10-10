# Algorithm actual parameters and decoder 1.2

Platform remains **0.0.12**. Project format is **12**; `.ssdecoder` package schema and
project semantics are **1.2**. AIR M0 / Maintenance 0.0 / SSLOG 0.0 remain independent.
Old record identities and layouts remain intact; independent ESKF15 and navigation-quality
records extend the catalog. New packages require **FLP 0.0.5**. Decoder 1.1 is rejected.

The five pages are Devices → Flight Configuration → **Algorithm Parameters / 算法参数** →
Hardware Connection → Code Generation & Build. The new page shows only selected algorithms
that declare parameters, with actual values, units, localized descriptions, ranges, basic/advanced
disclosures and per-algorithm reset. Save, reopen and Save As preserve these values.

## Meaning and source inventory

Pure INS consumes gravity at `APP/Src/ins_task.c` → `InsMechanization_Init`.
KF6 consumes its gravity at the existing delta-velocity transform in `estimator_task.c`.
These independent navigation inputs leave platform gravity used by Calibration, Alignment,
IMU unit conversion and the legacy SSLOG header unchanged. Decoder parameter sets are the
authority for the two navigation gravity values; the legacy header gravity is not their override.

KF6 P0, process sigma, GNSS sigma floors, barometer sigma and NIS values come from
`System/User/system_user_config.h`, `System/Src/system_estimator_profile.c` and the existing
profile initialization calls in `estimator_task.c`. Their C calculation sites are in
`navigation_kf.c`. P0 entries are actual covariance diagonal **floors**, with E/N/U order;
the existing initial GNSS uncertainty rule may increase P0. They are not squared again.
Process acceleration sigma is per axis; existing prediction squares sigma and retains its
original dt gains. GNSS sigma remains `max(receiver_sigma * 1.25, configured_floor)` and
R is its square. Horizontal E/N share a position floor; velocity U additionally uses the declared vertical sigma scale.
Barometer R is the square of the configured sigma. JY901B recommendation (1.5 m)
is advisory; there is no device sigma floor and no fabricated native variance.
NIS values are dimensionless; hard must exceed soft even after float32 rounding.
The existing NIS maximum R inflation cap is itself an actual dimensionless parameter.

FLP's old default-multiplier vocabulary must not enter the project: P0 scale maps to the six
actual diagonal floors, GNSS R scales to the real firmware sigma-floor parameters, and baro R
scale to actual sigma. There is no invented fixed GNSS R; the declared vertical velocity scale multiplies sigma after its dynamic floor. This does
not emulate arbitrary offline R multipliers: reported receiver uncertainty still participates.
FLP process sigma, gravity and NIS values have actual semantics. FLP separates immutable
Recorded Configuration from Offline What-if, including the selected quality revision.
KF6 state dimension and coning/sculling coefficients retain their meanings. ESKF15 has its own
15-dimensional error state and generated parameters; see [the navigation contract](NAVIGATION_CONTRACT.md).
Measurement timing is extended by the [fixed-lag replay contract](KF6_FIXED_LAG_REPLAY.md). GNSS outage recovery and its two compatible parameter additions are defined in [the recovery contract](KF6_OUTAGE_RECOVERY.md).

## Coning2 + Sculling2 INS

`silverstar.algorithm.ins.coning2_sculling2`

| Parameter ID | Default actual | Unit | Representation |
|---|---:|---|---|
| `gravity_mps2` | 9.78 | m/s^2 | value |

## KF6 Navigation Estimator

`silverstar.algorithm.estimator.kf6`

| Parameter ID | Default actual | Unit | Representation |
|---|---:|---|---|
| `gravity_mps2` | 9.78 | m/s^2 | value |
| `p0_position_e` | 4 | m^2 | covariance_diagonal |
| `p0_position_n` | 4 | m^2 | covariance_diagonal |
| `p0_position_u` | 9 | m^2 | covariance_diagonal |
| `p0_velocity_e` | 0.25 | m^2/s^2 | covariance_diagonal |
| `p0_velocity_n` | 0.25 | m^2/s^2 | covariance_diagonal |
| `p0_velocity_u` | 0.25 | m^2/s^2 | covariance_diagonal |
| `process_accel_std_e` | 1.5 | m/s^2 | sigma |
| `process_accel_std_n` | 1.5 | m/s^2 | sigma |
| `process_accel_std_u` | 2 | m/s^2 | sigma |
| `gnss_position_std_horizontal` | 1.5 | m | sigma |
| `gnss_position_std_vertical` | 2.5 | m | sigma |
| `gnss_velocity_std` | 0.15 | m/s | sigma |
| `gnss_velocity_vertical_scale` | 1.75 | 1 | value |
| `gnss_reacquire_outage_ms` | 300 | ms | value |
| `baro_std_m` | 2.5 | m | sigma |
| `nis_1d_soft` | 6.635 | 1 | value |
| `nis_1d_hard` | 10.828 | 1 | value |
| `nis_2d_soft` | 9.21 | 1 | value |
| `nis_2d_hard` | 13.816 | 1 | value |
| `nis_3d_soft` | 11.345 | 1 | value |
| `nis_3d_hard` | 16.266 | 1 | value |
| `nis_max_r_scale` | 10 | 1 | value |

## Declarative schema and project state

An Algorithm manifest may declare `algorithm_parameters` with `schema_id` equal to
`silverstar.algorithm-parameters/1.0` and a `parameters` array. Each entry requires `id`, `type`,
`default`, `unit`, `representation`, `min`, `max`, `precision`, `step`, `group`, `order`,
`description`, `display_names` and `generated_symbol`. Descriptions/names contain `en_US` and
`zh_CN`; optional `greater_than` names another parameter in the same algorithm (NIS ordering).
Every object rejects unknown properties; the parser also checks unique IDs/symbols, finite
defaults, valid ranges and comparison references. Types are float (binary32) or integer (int32).
No executable plugin code or algorithm-name dispatch is involved.

Project format 12 requires `algorithm_parameters: {component_id: {parameter_id: actual_value}}`.
Selecting an algorithm initializes its declared defaults; deselection removes its parameter set.
Unknown IDs within a retained set stay invalid instead of being silently discarded. Type,
range, NaN/Inf and NIS-order errors block strict generation. Format 11 migration only adds an
empty map; reconciliation initializes selected defaults. Prior earlier migrations are retained.

## Generated configuration and ownership

`Generated/Inc/project_algorithm_parameters.h` is force-included through existing
`project_flight_config.h` by the common Make/Host graph. It emits static numeric macros;
float constants carry `f` and round-trip binary32 with no arithmetic reordered and no heap,
strings or JSON in the target. Prior explicit Host override fixtures keep their override
convention. Normal product generation uses only saved actual values; manual compiler overrides
or edited project-owned firmware require a new independently validated decoder contract.

Parameter changes participate in the existing normalized generation fingerprint. Make, EIDE,
readiness and decoder hashes consume the same state. Reference import preserves declarations,
modified system/task bindings and the numerical Host fixture. First-copy source ownership is
unchanged: normal Apply does not port old project-owned C files. Generate a fresh project or
deliberately port the listed bindings before using parameter configuration in an older output.

## Self-contained `.ssdecoder` 1.2

The same five archive members remain. `project_semantics.json` adds
`firmware_algorithm_parameters`, an array of `{component, schema_id, manifest_sha256, parameters}`.
Each parameter is `{id, value, unit, representation, storage_type, description}`. `value` is the
resolved binary32/int32 value used by emitted C constants, not an unrounded UI decimal and not
a hidden-base multiplier. The English description states per-axis/shared and conversion semantics.
The manifest hash identifies the exact declaring schema; ordinary package checksums and the
generation-profile hash cover the new semantics. The decoder validates ownership, duplicates,
representation and exact target representability without loading plugins or accessing a network.

`algorithms` remains firmware membership, not an offline whitelist. An algorithm absent onboard
has no firmware parameter set. **Recorded Configuration** describes this firmware build's
configured inputs, not changing runtime P/Q/R matrices. **Offline What-if** is a separate analysis
configuration and may use other algorithms; it must not overwrite or impersonate recorded inputs.

## Verification

The frozen pre-change C trajectory exercises two-subsample INS, KF6 prediction and GNSS/barometer
updates, comparing quaternion, position, velocity, state and full covariance output. New defaults
must match its exact binary32 trajectory; changed values must affect generated C results. Prior
Host Golden logs also remain generated by the real C codec. Exact hashes, toolchains, build sizes,
test counts and acceptance results belong only in [VALIDATION](VALIDATION.md).

## Shared parameters and ordering

Selected owners are ordered by `selection.ui_order`, then component ID; owners without a
`selection` follow deterministically. The optional safe-token `shared_key` groups compatible
parameters without algorithm-name branches. Type, default, unit, representation, bounds,
precision and step must match exactly. The GUI renders each selected group once and synchronizes
all per-owner format-12 values; strict validation rejects conflicts, while reconciliation only
inherits an existing value for a newly selected owner.

Pure INS, KF6 and ESKF15 declare `navigation.gravity_mps2`. Their separate generated macros and separate
`.ssdecoder` `firmware_algorithm_parameters` values resolve to the same float32. `shared_key` is
FCCG-only and is not serialized to `.ssdecoder`; FLP does not interpret it. This navigation group
does not include `SYSTEM_LOCAL_GRAVITY_MPS2`, Calibration, or Alignment. Package schema and project
semantics remain 1.2; new packages require FLP 0.0.5. The historical 0.0.4 decoder requirement
is retained in original packages, not rewritten onto new navigation records.

## Fixed-lag parameters and migration

KF6 declares advanced integer `gnss_position_measurement_delay_ms` (0),
`gnss_velocity_measurement_delay_ms` (270), and `baro_measurement_delay_ms` (0).
Values 0–550 ms are supported by the static 600 ms history with 50 ms scheduling
headroom. A measurement outside the actual available history is explicitly rejected,
including startup and reset boundaries. 270 ms is an experimental candidate, not a
NEO-M9N hardware property. All values are emitted into generated constants and decoder
actual-parameter metadata.

`legacy_default` is optional declarative parameter metadata. Reconciliation uses it
only for a missing field in an existing algorithm owner. Previously stored explicit
values always win; new selections and Restore Defaults use `default`. Old KF6 owners
missing new delay fields receive zero delays; missing legacy baro/vertical-scale
fields receive 5.0/1.0. New projects use 2.5/1.75 and velocity delay 270 ms.
Recommendations never participate in shared-parameter contract equality.


## Historical GNSS position self-check, revision 2

This section describes historical decoder revision 2 only. Current firmware emits quality
revision 3 and does not run its permanent cumulative position-rejection state machine.
FLP retains the old implementation for old recordings. The range below is historical;
current revision 3 limits the position variance multiplier to 4 and rejects larger stored
values explicitly. It never silently clamps a project into a different configuration.

The KF6 plugin owns ten actual parameters. Project format 12 stores the resolved
values; generated C constants and the 1.2 decoder package use the same values.
New KF6 projects enable the check. Previously saved owners missing these parameters
receive `legacy_default` and remain disabled. Revision 0 logs use the older
firmware behavior in Recorded Configuration and may enable revision 2 explicitly
in What-if. Revision 1 was a different history-buffer candidate and is rejected
by FLP rather than reinterpreted. These thresholds are conservative software
candidates, not flight-qualified settings.

| KF6 parameter | Type | New default | Legacy default | Unit | Allowed range |
| --- | --- | ---: | ---: | --- | --- |
| `gnss_integrity_enable` | integer | 1 | 0 | 1 | 0–1 |
| `gnss_integrity_max_gap_ms` | integer | 120 | 120 | ms | 40–1200 |
| `gnss_integrity_error_threshold_m` | float | 10.0 | 10.0 | m | 0.1–200.0 |
| `gnss_integrity_recovery_threshold_m` | float | 4.0 | 4.0 | m | 0.1–100.0 |
| `gnss_integrity_suspect_duration_ms` | integer | 2000 | 2000 | ms | 100–30000 |
| `gnss_integrity_reject_duration_ms` | integer | 5000 | 5000 | ms | 100–30000 |
| `gnss_integrity_recovery_duration_ms` | integer | 8000 | 8000 | ms | 100–30000 |
| `gnss_integrity_position_r_scale` | float | 4.0 | 4.0 | 1 | 1.0–100.0 |
| `gnss_integrity_hacc_max_m` | float | 6.0 | 6.0 | m | 0.1–100.0 |
| `gnss_integrity_sacc_max_mps` | float | 1.2 | 1.2 | m/s | 0.01–20.0 |

The firmware compares horizontal displacement from one receiver-native GNSS
solution epoch with trapezoidal integration of GNSS horizontal velocity. A
single monitoring anchor and integral use constant memory. A short invalid
position interval leaves the velocity chain running; velocity invalidity,
sequence/time gap, epoch reset, or source switch clears the chain and anchor.
A new anchor formed after SUSPECT or REJECTED is untrusted and cannot by itself
restore NORMAL.

Closure above the error threshold for the suspect duration enters SUSPECT and
multiplies Pos EN R. Continued abnormal closure for the additional reject
duration enters REJECTED and masks Pos EN while preserving GNSS velocity and
vertical groups. Recovery below the lower threshold requires the original
trusted anchor and a complete recovery duration for each step back to NORMAL.
The integrity module never rewrites the KF state; existing group reacquisition
handles position return. GNSS_NATIVE retains receiver evidence,
GNSS_MEASUREMENT records the actual admitted mask and input R, and EVENT records
state transitions. KF6_DIAGNOSTIC retains its wire type but starts disabled in
new projects. See [VALIDATION](VALIDATION.md) for measured gates.

## Current quality policy, revision 3

The two 10 s windows, 5 s stagger, evidence TTL and per-group supervisor are defined in
[NAVIGATION_CONTRACT.md](NAVIGATION_CONTRACT.md). Four stored KF6 controls remain effective:
`gnss_integrity_enable`, `gnss_integrity_max_gap_ms`, `gnss_integrity_error_threshold_m`
and `gnss_integrity_position_r_scale` (now strictly 1–4). The last is a variance factor.
It applies only to Pos EN and cannot permanently switch that group off.

Six historical fields use generic manifest `lifecycle: legacy_read_only`:
`gnss_integrity_recovery_threshold_m`, `gnss_integrity_suspect_duration_ms`,
`gnss_integrity_reject_duration_ms`, `gnss_integrity_recovery_duration_ms`,
`gnss_integrity_hacc_max_m` and `gnss_integrity_sacc_max_mps`.
They remain in existing format-12 snapshots and decoder parameter metadata so history
is not rewritten. Current GUI presents them read-only with a retirement explanation;
Restore Defaults leaves them unchanged. The declaration `retired_parameter_ids` lets
FLP distinguish the 36 stored KF6 fields from the 30 effective current fields. Historical
revision-2 replay still uses its six fields as originally recorded. No current runtime
decision reads them, and no current editable control advertises a false effect.

## ESKF15 parameters

`silverstar.algorithm.estimator.eskf15` declares 35 actual parameters: gravity, the 15 P0
diagonals, four continuous noise amplitude densities, GNSS position/velocity sigma floors,
barometer sigma, one-/two-dimensional soft/hard NIS limits, bounded robust R multiplier,
three body-frame GNSS lever-arm coordinates and three measurement delays. The exact IDs,
defaults, ranges, units and representations are in its manifest and the identical
`eskf15.parameters` mapping in [the machine contract](../../contracts/navigation_v1.json).

`navigation_eskf_config.h` requires generated values with compile-time errors for missing
symbols. It does not silently substitute a second private default table. Initialization
validates finite/positive noise and NIS ordering; bad configuration cannot mark the kernel
ready. P0 is not squared; noise density and measurement sigma are squared exactly once
at their calculation sites. The velocity delay candidate of 270 ms is configurable and
does not assert a measured receiver hardware delay. Residual biases are applied to saved
body input during every replay, so changing them affects subsequent propagation.
