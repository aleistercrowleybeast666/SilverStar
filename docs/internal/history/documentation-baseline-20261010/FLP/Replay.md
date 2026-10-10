# Replay semantics

The current formal input and execution contract is [Field Log Replay](Field_Log_Replay.md).
KF6 always uses recorded increments plus recorded estimator operation ordering for faithful replay;
the Corrected IMU GUI request also runs independent mechanization verification. It never replaces
faithful inputs with rebuilt increments. Pure INS may run corrected-IMU navigation independently.
Missing formal operation inputs are not inferred. Calibration is not applied a second time.

GNSS is optional according to the KF_6 input contract. A receiver may be configured and online
while reporting no fix, no usable position/velocity, and no `GNSS_MEASUREMENT` Records. Replay
does not manufacture a 0/0 position, does not disable the whole algorithm for that condition, and
continues with available prediction/barometer inputs.

Every run is appended to `ReplayResultStore` with a unique `result_id`, algorithm, mode, input
source, parameter snapshot, fidelity, warnings, time coverage, channels, and diagnostics.
Recomputed and What-if runs from Pure INS and KF6 therefore coexist.

The Replay algorithm list is the desktop registry, not the firmware component list. Each row shows
independent tags for an installed offline plugin, firmware membership, and recorded output. A
future installed ESKF plugin therefore appears immediately and can run when its declared stable
inputs are present, even when the opened `.ssdecoder` says that ESKF was not onboard.

Replay exposes three configuration modes:

1. **Recorded configuration** requires onboard membership, usable inputs and every required
   actual value in the exact `.ssdecoder` 1.2 package. Provenance is
   `Firmware build configuration from .ssdecoder`. No header or plugin-default substitution.
2. **Offline configuration** uses explicit actual plugin defaults.
3. **What-if** copies complete firmware values for onboard algorithms, or actual plugin defaults
   for absent algorithms. Restore firmware configuration and Restore algorithm defaults are
   distinct actions. UI display precision never rounds an unedited firmware value in a request.

Recorded algorithm output is a fourth, separate fact: it may be displayed as a comparison target,
but it neither proves that recorded configuration is complete nor becomes a replay input.

Replay remains a first-class analysis capability even when Recorded and Recomputed happen to be
close. It is the path for running new algorithms on old logs, comparing KF6/ESKF15/ESKF24,
parameter What-if studies, algorithm regression, diagnosing real-time task/timestamp/drop issues,
and comparing firmware algorithm versions. Availability is strict: missing required records or
channels produces `UNAVAILABLE` with explicit missing-input codes rather than a partial result.

What-if controls are generated from `ParameterSpec.group_key`: Process Model, Initial
Covariance, Measurement Noise and Consistency Gating. Each editor shows the actual value/unit,
and its tooltip includes representation/range. P0 uses six covariance-diagonal floors;
process/GNSS/barometer noise uses sigma exactly as FCCG declares. Q squares sigma in the existing
filter; P0 diagonal values are not squared. The old `p0_scale`, `gnss_position_r_scale`,
`gnss_velocity_r_scale` and `baro_r_scale` fields are removed with no migration.

Recorded P0 and measurement R already include dynamic uncertainty. Default replay preserves these
resolved logged values. Changed P0 floors retain evidenced dynamic contributions. Barometer
What-if requires the uniquely matched native sample and the recorded origin sigma; it applies
`max(native variance, sigma²) + origin sigma²`. GNSS What-if keeps the existing 1.25 accuracy
coefficient and source/update timestamps; it requires uniquely matched native uncertainty. Frozen
GNSS initialization and lowered P0 floors can be non-invertible from the recorded aggregate.
Those cases explicitly fail with `parameter_dynamic_uncertainty_missing`; no invented covariance
or silently unapplied edit is reported as a successful replay. Calibration/alignment remain frozen.

See [Actual_Parameters_Validation.md](Actual_Parameters_Validation.md) for the parameter inventory,
actual package checks, default equivalence, dynamic metrics and outstanding real-flight phase gate.

Pure INS and KF_6 remain `APPROXIMATE` for firmware `0.0.10`. Their audited host
implementation retains the `SILV0008` identity and emits explicit build/Golden warnings.
Exact package matching changes input provenance, not algorithm fidelity.

Corrected-IMU cadence is evaluated from recorded sample timestamps within the logged
SYSTEM_CONFIG bounds; stream-descriptor decimation is used when current SYSTEM_CONFIG no longer
contains the historical decimation array. A detected gap clears the coning/sculling history and
starts a new segment. No sample or trajectory point is interpolated across that input gap, and
the result remains `APPROXIMATE`. `EXACT` additionally requires an explicit matching Golden
validation reference and clean source integrity.

The Replay page owns the only editable **Analysis Data Source** selector:

1. Recorded is always the first item and remains selectable.
2. A replay result is listed only when fidelity is not UNAVAILABLE, no required input is missing,
   and attitude, velocity, and position outputs each contain valid samples.
3. Incomplete or failed runs remain visible in Stored Results for diagnosis but cannot become the
   global analysis source.

Flight and State Estimation display the active source read-only. Flight and export resolve it
through `ChannelResolver`. Exactly the selected result supplies navigation, attitude, state
diagnostics, 3D and exports. Recorded KF6/Pure INS are identified distinctly but never overlaid
automatically. Explicit comparisons remain separate. Data Explorer exposes every run under a
unique prefix; selection does not copy or overwrite recorded data.

## Display-only event points

GUI and exported trajectories now share the cadence-guarded phase builder described in
[Display_DataQuality.md](Display_DataQuality.md). It can add an event point to drawing geometry
inside a normal position interval; replay inputs, quaternion propagation, timestamps, and result
TimeSeries are unchanged. Real channel gaps remain broken. Global sequence-gap segments and
missing IDs are record diagnostics, independent of the active position channel cadence.

## Project draft state

Replay draft edits are part of the existing Project v3 `replay_configurations` state. Changing a
draft marks an open project dirty; New Project, Open Project, and Exit offer Save, Discard, or
Cancel before replacing that state. Saving continues to validate actual values and provenance;
the UI workflow does not alter replay timing, ordering, Pure INS, or KF_6 behavior.
