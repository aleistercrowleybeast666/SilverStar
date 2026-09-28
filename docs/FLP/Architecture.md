# SilverStar_FLP Architecture

## Design boundary

The log input boundary has two user-managed layers:

1. A trusted **Log Container Plugin** implements one incompatible wire container. It owns only
   File/Record headers, CRC, sync recovery, truncation and `RawRecordFrame` production. The
   protected built-in is `silverstar.flight_log.container.0_0`.
2. One declarative **Decoder Profile Package** (`.ssdecoder`) belongs to each generated project.
   Its Record Catalog defines payload layouts and its Project Semantics defines devices,
   partitions and channels. Both documents are pure data in one checksummed ZIP.

Algorithm Plugins remain a separate internal extension point for complete navigation and
state-estimation algorithms. Pure INS and KF_6 are the built-ins. A decoder package describes
recorded data but never supplies executable algorithm behavior. Plotting, export, project
persistence, Data Explorer, deploy replay, landing replay, and GUI code remain Core services.

The production registry contains trusted containers and offline algorithms, not a fixed Record
parser. `LogOpenCoordinator` creates `DecoderProfileParserPlugin` only after an exact package 1.2
and Descriptor match. The historical fixed parser module remains for frozen test fixtures but is
not reachable from GUI, CLI, project restore, or drag/drop.

The GUI never reads byte offsets. It consumes `FlightDataset`, standard channels, algorithm
results, stable diagnostic codes, and metadata.

## Protocol truth and data flow

Record and project meaning comes only from the matched `.ssdecoder`. Offline numerical algorithms
remain audited host implementations based on their documented firmware source/build identity.
AIR frames are deliberately outside the SSLOG container.

```text
read-only SSLOG BIN
  -> trusted SSLOG0 container (CRC plus bounded/validated FLG1 recovery, RawRecordFrame)
  -> mandatory bootstrap Descriptor + exact .ssdecoder 1.2 validation/cache
  -> dynamic Record Catalog parser (raw Records and instance channels)
  -> semantic adapter + mandatory Calibration Result
  -> FlightDataset + DataQualitySummary + DatasetSemanticContext
     (immutable raw data + zero-copy stable aliases)
  -> Algorithm Plugin replay
  -> ReplayResultStore (every Recomputed and What-if run is retained)
  -> AnalysisSource + ChannelResolver
  -> Overview / Flight / State Estimation / Data Explorer
  -> Core export (JSON/CSV/localized PNG/segmented 3D PNG/combined GIF)
```

Every series owns its real timestamp array. No channel is reconstructed from a nominal sample
frequency and unlike-rate records are not forced into one large table. Decoded Records preserve
file order and offsets, while each channel sorts its own timestamps; interleaved producers do not
impose a global monotonic timestamp contract.

Current-SSLOG corruption recovery never trusts magic alone. Each candidate must pass complete
header, bounded length, timestamp, frame-size, and CRC validation within fixed scan/candidate
limits. Invalid frames never reach the dynamic payload decoder. The damaged byte span and bounded
raw hex remain diagnostic evidence; there is no payload repair or legacy parser fallback.

Decoder-profile discovery is bounded by file count, byte count, recursion depth and parent depth.
Matching uses the logged `DECODER_PROFILE_DESCRIPTOR` and requires package/container identity plus
generation-profile, Record Catalog, and Project Semantics hashes simultaneously. There is one
`exact_generation_profile` mode and no ranking/fallback. Manual import validates before copying
into a content-addressed user cache; the source package is never changed. A trusted `.ssplugin` is
discovered only in the configured FLP plugin directory and can instantiate code only through a
host allowlist. A task-directory `.ssdecoder` can never carry or execute container code.

Manual GUI import, folder search, strict drag/drop, CLI, and project restore all call the same
coordinator. They publish a new dataset/project only after the whole operation succeeds.

## Analysis surface

Overview is recorded mission truth: exact decoder/project/firmware identity, file integrity,
START-cropped metrics, configured calibration flow and selected effective Calibration Result,
Initial Alignment/INITIAL_STATE, GNSS configured/online/fix/usability state, actual deploy
event/detail, and the translated event timeline.
Flight owns velocity, position, corrected IMU, attitude, and 3D playback. State Estimation owns
filter internals only. Replay is page two, the source-generation entry point, and the only page
allowed to change the global Analysis Data Source. Flight and State Estimation show that source
read-only.

State Estimation contains no KF6 channel IDs. It resolves the active estimator's
`EstimatorVisualizationSpec`, builds State Group and Measurement selectors, and renders
covariance, innovation, NIS, measurement diagnostics, and a generic update-event table from
`StateGroupSpec`/`MeasurementGroupSpec`. Pure INS has no estimator visualization spec. Future
ESKF_15/24 state or sensor groups are plugin metadata changes, not page changes.

`ReplayResultStore` assigns a unique result/source ID to every run and never replaces a prior
Recorded-configuration, Offline, or What-if result. `ChannelResolver` is the single
Recorded/replay lookup layer used
by Flight, State Estimation, Data Explorer, and export. Only complete results with valid attitude,
velocity, and position can be selected. Recorded Pure INS and Recorded KF_6 navigation are
separate layers. A replay source is plotted with both recorded layers as dashed references;
Recorded mode shows both as primary curves.

## START and attitude authority

`INITIAL_STATE` freezes the START-adopted `q_nb0`. It is WXYZ Hamilton and rotates Body vectors
into ENU. From START onward, the authoritative task attitude is produced only by software:

```text
INITIAL_STATE.q_nb
  + IMU_CORRECTED (GUI authority; recorded INERTIAL_INCREMENT remains internal/CLI)
  + two-sample coning/sculling
  + right-multiplied body rotation increment
  -> software q_nb -> ENU specific force -> gravity compensation -> v -> p
```

`HW_QUAT_NATIVE` remains diagnostic/reference data after START. Recorded Pure INS and estimator
outputs are comparison layers; neither is fed back as normal replay input.

All `ALIGNMENT_RESULT` records remain history. The latest valid-ready result at or before START
provides result provenance, but the latest valid `INITIAL_STATE` at or before START is the
authoritative adopted state and quaternion. A later stale/failed Alignment record does not erase
an earlier valid result.

## Visualization invariants

The attitude view and PNG/GIF export rotate every vertex of the same square-base, 2.2-unit rocket
mesh with `Quaternion_RotateVector`; body axes remain a thinner secondary reference. Trajectory
rendering subtracts a display-only origin interpolated at mission START (or the first valid
post-START navigation sample). The immutable dataset is never rewritten.

Pre-deploy trajectory and Current use red; at and after Deploy both use blue. Deploy is one orange
point and Landing is purple. OpenGL event/current markers use `pxMode=False` and diameters derived
from the E/N/U trajectory extent, so they are world-space geometry rather than fixed screen-pixel
circles. START is represented by the coordinate origin, not a marker, and event names are not
rendered as floating 3D text.
Full-trajectory grid/camera fitting runs only when data/source changes or Reset View is requested;
playback frames never overwrite user zoom or orbit. Plot refreshes allocate at least sixteen
distinct colors and generate additional HSV colors without modulo cycling.

## Firmware algorithm reuse decision

Two options were evaluated:

- a runtime DLL binding to the firmware C sources;
- a faithful Python/NumPy implementation with firmware-order float32 operations and golden
  validation against the same C sources.

The first phase uses the second option. The C units include build-time user configuration and
embedded interface headers; shipping a DLL would either bind FLP to an external firmware checkout
or duplicate that configuration behind an ABI. The Python implementation keeps What-if parameter
editing and PyInstaller distribution straightforward. Operation order, quaternion convention,
two-sample grouping, gravity sign, KF state ordering, Joseph update, NIS gates, and timestamps are
kept aligned with `SILV0008`. Firmware component membership from Project Semantics is independent
of host-plugin availability and recorded output. FCCG 0.0.10 has not passed its matching real-log
host golden gate, so both Pure INS and KF_6 remain `APPROXIMATE` with an explicit warning; neither
the implementation ID nor fidelity is silently upgraded.

## Project and audit boundary

`.ssflp` v3 contains exactly one `log_reference`, decoder source/cache references, complete
package/generation/Catalog/Semantics hashes, container ID/version, exact match mode, replay
settings, notes, and UI state. Old versions are rejected. Save uses a same-directory temporary
file, flush/fsync, and atomic replacement. Restore verifies every stored identity before changing
the current GUI state.

The audit export manifest hashes the source log and records decoder identity, project/firmware/
hardware/protocol metadata, firmware components, effective calibration, alignment provenance,
GNSS usability, parser/Data Quality diagnostics and damaged spans, configured-versus-recorded
stream counts, exported-channel provenance, raw-to-stable aliases, and every replay
plugin/mode/provenance/fidelity/parameter/input-contract set.

## KF6 state convention

The current firmware source is authoritative: KF6 state order is
`[pE, pN, pU, vE, vN, vU]`. Some early design prose listed velocity first; FLP follows the actual
`navigation_kf.c` implementation and SSLOG fields.

## Responsiveness and errors

Parsing, replay, export, and GIF creation accept a cooperative `TaskContext`. The GUI runs them in
worker threads, reports progress, and requests cancellation without terminating Python. A failed
open never clears the current dataset or replay store. Core and plugins emit stable codes; the
i18n layer translates them. Full tracebacks go to the application log while dialogs show concise
user-facing messages.

## Shared display closeout

Semantic columns are assigned during channel construction, before stable alias publication.
Core trajectory phase geometry is shared by OpenGL, PNG, and GIF and preserves channel-local gaps.
Data Quality classification is derived from recorded evidence and never relaxes decoder or replay
contracts. See [Display_DataQuality.md](Display_DataQuality.md) and
[Workspace_Cleanup.md](Workspace_Cleanup.md).
