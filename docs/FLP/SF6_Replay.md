# SF6 offline replay

The Replay algorithm order is Pure INS, SF6, KF_6, ESKF_15. SF6's first parameter
group contains six fixed gains in firmware order `vE,vN,vU,pE,pN,pU`, each with
offline default 0.2 and allowed range [0,1]. Gains are engineering defaults, not
a tuning recommendation. The other groups contain the three measurement delays
and shared INS gravity. SF6 exposes no covariance, innovation, NIS or statistical
confidence parameters. It does not consume magnetometer measurements.

The source authority at the feature base revision is:

- `apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/plugin.json`
- `.../payload/Algorithm/Estimator/SF6/Src/navigation_sf6.c` and its header
- `.../payload/Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c`
- the existing INS mechanization and `system_time.c` measurement timestamp resolver

No firmware file is modified. FLP ports the C fusion core's float32 operations,
fixed-lag replay and transactional updates. Six state elements use velocity-first
order. GNSS horizontal position, GNSS height, GNSS horizontal velocity, GNSS
vertical velocity and barometer are independent groups 0 through 4. GNSS height
and barometer both use `pU` and its one gain, including their deterministic
same-epoch order; there is no extra weighting or separate vertical gain.

Prediction must be contiguous, with valid float32 dt in (0,0.02] and timestamps
consistent with C's rounded microseconds. The core starts at the first actual
increment's start (end minus dt), with INITIAL_STATE adopted velocity and zero
position, rather than inventing propagation from the START event. Interior
prediction gaps reject the replay. Shared corrected-IMU coning/sculling and
mechanization services provide actual increments without resampling. The existing
availability checks require un-decimated corrected IMU (GUI default) or recorded
inertial increments (API), INITIAL_STATE and supported mechanization configuration.
SF6 additionally requires SYSTEM_CONFIG; source logs and decoded records stay immutable.

History retains at most 256 prediction boundaries in a closed 600 ms age window.
There are at most 256 admitted events, including gain-zero events. Measurements
replay from the selected preceding boundary, ordered by epoch and then group.
Each group's measurement epoch and receive epoch must advance; sequence advance
uses the C uint32 wrap rule. Expired, duplicate, invalid, full-capacity or numeric
failure outcomes remain ordinary outcomes, and failed updates do not publish
partial state, event history or last-seen tracking. Gain one does not bypass
float32 numeric failure checking.

Recorded-configuration mode requires exact `.ssdecoder` firmware membership and
the complete SF6 gains/delays plus gravity from the INS component. Offline defaults
never substitute for recorded settings. Logged SF6_STATE gains must agree with
that configuration. Existing LogOpenCoordinator package/Descriptor validation is
unchanged. Recorded SF6_MEASUREMENT supplies resolved measurement epochs, evaluation
epochs, physical admission and observations. If an SF6 what-if changes a delay,
sample timestamp trust evidence must be available; otherwise the operation is
rejected. Trusted native time is used unchanged; untrusted time is receive minus
the configured delay, including delay zero. Future/negative resolved time is invalid.

What-if from KF6 or another recorded algorithm is explicitly a separate SF6 result.
It reuses recorded GNSS/BARO ENU observations and admission evidence, with independent
GNSS group masks where available (legacy records use their recorded flags). It
does not rerun the original sensor quality, source-selection or queue services.
GNSS_NATIVE can supply timestamp trust; when absent, the receive-only assumption is
reported. Missing GNSS is permitted: inertial propagation and any available barometer
updates continue. Missing barometer is also reported. If SF6_MEASUREMENT exists,
it is authoritative instead of mixing alternative estimator observations into it.

Every SF6 replay is **APPROXIMATE**, including recorded-configuration replay. The C
oracle proves the fusion core for tested inputs, not the full firmware's mechanization,
task scheduling, queue, quality, source switching, initialization or logging completeness.
The GUI presents fidelity/warnings, and the result records missing conditions,
actual parameters, initialization policy, windows, capacities, group outcomes and
unapplied observation count. Source_END uses the available replay output end;
landing bounds retain the existing mission policy. Configuration, selected analysis
source and SF6 results use the existing project save/reopen mechanism.

CSV export includes `sf6.state`, `sf6.gain` and standard navigation channels;
`SF6_<result-id>_Replay_Audit_<language>.json` records mode, fidelity, warnings,
actual parameters and full diagnostics/measurement outcomes. The existing manifest
includes the result provenance, source and hashes. These are local artifacts;
they may contain position information and should follow the existing review before
any sharing or publishing.

`apps/FLP/tests/sf6_c_bridge.py` builds the unchanged repository `navigation_sf6.c`
with an actual C compiler (`gcc`, strict warnings, no fast math or contraction)
and a test-only assertion abort adapter. Set `SILVERSTAR_SF6_ORACLE_EVIDENCE` to
retain build commands, tool version, source/header hashes, compiler output and DLL
hash. No oracle DLL ships with FLP. Tests cover three gain boundaries, interleaved
groups, delay/window/capacity, sequence wrap, duplicate/stale/invalid outcomes,
numeric failed publication, initial velocity/epoch, independent admission,
prediction gaps, parameter modes, persistence and exports. These host results
are not ARM compilation, hardware qualification or full-firmware exact replay.
