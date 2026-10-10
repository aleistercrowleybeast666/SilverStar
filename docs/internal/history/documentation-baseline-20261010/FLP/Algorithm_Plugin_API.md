# Algorithm Plugin API

An `AlgorithmPlugin` declares stable identity/version metadata, required and optional records and
channels/semantic roles, cadence and gap-tolerance contracts, parameter-source provenance,
coordinate/frame convention, a typed parameter schema, standard outputs, and diagnostic outputs.
`availability()`
returns supported input sources, missing input codes, warnings, and `EXACT`, `APPROXIMATE`, or
`UNAVAILABLE`. `run()` receives a `ReplayRequest` and returns an immutable `AlgorithmResult`.

Standard output IDs such as `attitude.q_nb`, `navigation.velocity_enu`, and
`navigation.position_enu` let shared Navigation views work with future ESKF15/24 plugins. Plugin
specific channels such as `kf6.nis.position_horizontal` remain discoverable by Data Explorer and
diagnostic views without changing the common page.

Recorded, Recomputed, and What-if are provenance labels. Fidelity is separate: it describes input
and implementation completeness, never whether a curve merely looks close.

## Firmware, recorded data, and offline execution are independent

`project_semantics.json.algorithms` is normalized from the current 1.2 `list[str]` into immutable
firmware component references. It answers only whether an algorithm component was built into the
flight-controller project. It is never an allowlist for desktop plugins.

`AlgorithmMetadata` and `AlgorithmConfigurationAvailability` keep four facts separate:

- `firmware_component_ids` / `firmware_member`: the package says the component was onboard;
- `recorded_output_roles` / `recorded_output_available`: this log actually contains a recorded
  output that the plugin knows how to present;
- `recorded_parameters` / `recorded_available`: the package contains every required firmware configuration
  value, the component was onboard, and the replay inputs are available;
- `offline_default_parameters` / `offline_available`: the installed desktop plugin can run from
  the available semantic inputs, regardless of firmware membership.

These flags must not be inferred from one another. In particular, an installed Pure INS, KF_6, or
future ESKF plugin stays visible and can run offline when its component ID is absent from the
firmware list. Conversely, a firmware component without a compatible visualization plugin remains
visible as package metadata and its raw records remain available in Data Explorer.

`ReplayMode.RECORDED_CONFIGURATION` requires complete firmware actual values from
`project_semantics.json.firmware_algorithm_parameters`. `ReplayMode.OFFLINE` uses actual plugin
defaults. Onboard What-if copies Recorded Configuration exactly and can restore firmware values;
absent algorithms start from their plugin defaults and can restore algorithm defaults. Missing
firmware parameters never fall back. Matching uses IDs, units and representation, never labels.

`ParameterSpec` declares id, type, actual default, unit, representation, min/max, precision,
step, order/group, required status and optional greater-than constraints. Schema identity is a
SHA-256 of the declared metadata. `Parameters_Resolve` rejects unknown, missing, wrong-type,
non-finite and out-of-range values. A true mathematical NIS soft-weighting limit remains a
unitless actual parameter; it is unrelated to removed relative-default controls.

The desktop Replay page always constructs `ReplayRequest(input_source="corrected_imu")`. Plugins
must retain explicit availability checks and must not silently fall back. The internal API may
continue to accept `recorded_inertial_increment` for CLI, validation, and golden-vector work.

Required and optional inputs are not interchangeable. KF_6 prediction requires the adopted
initial state, recorded system configuration, and one declared inertial source. GNSS and
barometer measurements are event-driven optional roles; a configured GNSS stream with zero
usable measurements remains a legal prediction-only/other-measurement flight. Cadence checks use
recorded timestamps and stream descriptors. Input gaps are segmented and reported—never silently
interpolated.

Each user-editable parameter supplies stable `label_key`, `group_key`, and `tooltip_key` values,
plus unit/range/step metadata. The GUI translates those keys, keeps the raw `parameter_id` in the
tooltip, and builds the What-if group selector without parameter-specific branches.
`recorded_parameters(dataset)` returns only firmware actual values in the matched package. It must not
fill missing firmware values from `ParameterSpec.default`. The What-if reset baseline uses explicit
complete firmware actual values for onboard algorithms, or plugin actual defaults for absent
algorithms. Warnings remain stable raw codes in algorithm
results and are translated only at the GUI/export boundary.

`EXACT` requires both clean inputs over the claimed interval and a matching immutable
firmware/host Golden validation reference. Exact decoder-package matching establishes schema and
input provenance only. The built-in Pure INS and KF_6 implementations for firmware `0.0.10`
therefore report `APPROXIMATE`: they retain the audited `SILV0008` host-implementation
identity and emit explicit build/Golden warnings. Package adaptation does not upgrade their
fidelity claim.

## Estimator visualization metadata

An estimator plugin may set `AlgorithmMetadata.estimator_visualization` to an
`EstimatorVisualizationSpec`. Pure INS deliberately leaves it as `None`, because it has no
covariance, innovation, NIS, or measurement-update diagnostics. State Estimation considers only
plugins that provide this spec.

Each `StateGroupSpec` declares:

- stable `group_id` and translated `label_key`;
- component names and state-domain unit;
- a covariance-diagonal channel and the component indices owned by the group;
- an optional stable export `file_stem`.

The GUI creates the State Group selector from these entries. It plots only the selected group and
offers standard deviation (`sqrt(Pii)`, default) or variance (`Pii`) display. Adding ESKF position,
velocity, attitude-error, gyro-bias, or accelerometer-bias groups therefore does not require a GUI
change. Standard Export consumes the same entries and writes one engineering plot per group as
`sqrt(Pii)` in that group's physical unit; it never combines state groups with different units.

Each `MeasurementGroupSpec` declares:

- stable measurement-group ID, translated label, dimension, and component names;
- innovation, NIS, update-result, R-scale, and optional age/uncertainty/effective-R channels;
- vector-column indices and optional attempt-mask/dimension channels;
- optional soft/hard NIS threshold parameter IDs;
- the measurement-domain unit and optional stable export `file_stem`;
- generic participation evidence: SYSTEM_CONFIG field names/provider indices, measurement record
  names, and an optional validity channel.

Innovation, NIS, Measurements, the generic Update Event Table, and Standard Export all consume
this metadata. A measurement group that is configured but has no valid updates still gets
Innovation, NIS, and `sqrt(R)` standard plots with an explanatory message. A group for which
configuration evidence is explicitly present and disabled is not plotted and is recorded in the
export manifest as `measurement_not_configured`; data values (including all-zero diagnostics) are
never used to infer participation.
Dimensions may be 1, 2, 3, or N. A future ESKF plugin can add Magnetometer, Dual-GNSS Heading,
Air Data, Star Tracker, or another measurement group without modifying State Estimation or the
exporter.

An estimator that exposes full covariance sets `EstimatorVisualizationSpec.full_covariance` to a
`FullCovarianceSpec`. The spec owns the stable upper-triangle/full-matrix channel ID, output file
stem, ordered state symbols, physical state units, storage layout, and optional initial-record /
initial-diagonal field metadata. Export reconstructs NxN
from this metadata; KF_6 is 6-state today, while ESKF_15/24 require no exporter dimension branch.
The keyframe TXT uses only the last valid P whose timestamp is not later than START,
PARACHUTE_DEPLOY, or LANDING. If LANDING is absent, analysis end is the third event time. P is
never interpolated and a future sample is never substituted. When START precedes the first full-P
sample, the declared initial diagonal (KF_6: `INITIAL_STATE.p0_diagonal`) supplies the diagonal
P0. The raw full-P time-series CSV stays available. Batch Export creates only defined engineering
plots and does not mirror selected CSV channels into generic `Channel_*.png` files.

KF_6 currently declares Position and Velocity state groups plus GNSS Position, GNSS Velocity, and
Barometric Altitude measurement groups using its real recorded/recomputed channels. A new
estimator remains unavailable when any `required_records` or `required_channels` input is absent;
the GUI must report the missing inputs and must not manufacture a result.

## Plugin boundary

`builtin_registry()` remains the only discovery mechanism and registers the audited SSLOG0
container plus the Pure INS and KF_6 offline algorithms. It does not register a fixed record
parser: `LogOpenCoordinator` constructs `DecoderProfileParserPlugin(container, verified_package)`
for each accepted log. Future container or algorithm modules are added explicitly. This API does
not implement a plugin store, entry-point discovery, online installation, signatures, hot reload,
or dependency management.

## GUI installation boundary

Plugin Manager enumerates runtime-registered Algorithm Plugins, so future registrations appear without dialog changes. Install Plugin intentionally does not accept dynamic Algorithm packages or execute archive Python/entry points.
