# SilverStar Flight Log Processor

## Current SilverStar project folder workflow

Use **Open SilverStar Project Folder** for a project created by FCCG. FLP reads the root `<ProjectName>.ssdecoder`, offers logs under `Log/` for one-at-a-time selection, and checks the exact decoder identity before opening. The default export directory is `Log/<LogStem>_Export/`. Direct `.BIN`/`.sslog` and manually selected `.ssdecoder` remain available. Details: [project folder contract](../architecture/PROJECT_FOLDER_CONTRACT.md).

Current formal logging, fixed-lag replay, single Analysis Source, shared range and paged/GIF
exports are defined in [Field Log Replay](Field_Log_Replay.md). Exact validation is in
[VALIDATION.md](VALIDATION.md). Historical test snapshots below do not supersede that contract.


SilverStar_FLP is a Windows desktop application and command-line toolkit for SilverStar
`SSLOG0` flight logs. It parses the current binary profile, reconstructs the complete Pure INS
and KF6 navigation chains from `START`, compares recorded and recomputed results, visualizes the
flight, and exports timestamp-faithful data products.

Version: **v0.1.0**

> Raw `.BIN`/`.sslog` logs and `.ssdecoder` packages are opened read-only. A `.ssflp` v3 project
> stores one log reference, exact decoder/cache identity, replay settings, notes, and UI state; it
> never embeds or rewrites either source.

See [KF6 field analysis and project paths](KF6_FIELD_ANALYSIS.md) for outage recovery,
independent vertical velocity noise, default project roots and per-log result directories.

## Start here

### 1. Install the shared environment

From the SilverStar monorepo root in PowerShell:

```powershell
.\tools\setup_venv.ps1
```

FCCG, GSHC and FLP use this one root `.venv`.

### 2. Open the application

```powershell
python FLP.py
```

The recommended path is **Open SilverStar Project Folder** and select the FCCG
project root. FLP lists log files only below `Log/` and uses the root decoder.
For standalone analysis, choose **New Project** to select a `.ssflp` location first, then select exactly one flight
log plus its `.ssdecoder` (or run the bounded task-folder search). The project file is written
only after exact-pair validation succeeds. Choose **Import Log / Decoder** for a temporary
session that does not require an immediate project save. You can drag one log with an optional
package onto the window; a log by itself invokes the same bounded exact search. Command-line GUI
startup accepts the explicit pair:

```powershell
python FLP.py D:\logs\flight.BIN --decoder D:\logs\flight.ssdecoder
```

The dark-blue brand header shows the localized application name, `v0.1.0`, developer credit,
compact current-project name (with the absolute `.ssflp` path in its tooltip), then flexible
space, language, and theme. The File menu provides New Project (`Ctrl+N`), Open Project (`Ctrl+O`), Save Project
(`Ctrl+S`), Save Project As (`Ctrl+Shift+S`), Import Log / Decoder, Export (`Ctrl+E`), and Exit.
The adjacent Plugins menu provides Manage, Install, and Refresh; Help provides About. Plugin Manager reads the runtime registry. Install accepts only explicitly trusted `.ssplugin` container packages, never executes archive Python, and requires restart plus a host-allowlisted factory before activation. There is no online store, dynamic Algorithm installer, or duplicate toolbar.
Import and export use focused option dialogs. The five analysis pages are:

1. Overview — mission/file and exact decoder identity, flight metrics, deploy altitude/reason,
   configured calibration flow plus the selected effective model, initial alignment result, and
   GNSS online/fix/usability state, translated event timeline, and explicit Data Quality status.
2. Replay — every installed offline algorithm, independently labeled for firmware membership,
   recorded output, and offline-plugin availability. Recorded Configuration is enabled only when
   every required firmware actual parameter is present in the exact package; Offline defaults and What-if remain distinct. Every run is
   retained. A dedicated **Analysis Data Source** selector begins with Recorded data and exposes
   only complete, successful runs.
3. Flight — START-cropped ENU velocity/position, corrected IMU, authoritative software attitude,
   and a themed 3D attitude/trajectory replay with its own playback controls. Before Deploy the
   path/current point are red; after Deploy they are blue; Deploy is one extent-scaled orange
   world-space point. Recorded Pure INS and Recorded KF_6 remain separately identified, with only the selected source visible
   curve layers.
4. State Estimation — metadata-selected estimator state groups, covariance as 1-sigma or Pii,
   measurement-group innovations/NIS/noise/age, and generic sequential-update results. The page
   contains no KF6-specific channel IDs, so future estimator groups and sensors can be declared by
   a plugin without page-code changes.
5. Data Explorer — searchable raw/stable/capability/algorithm channel groups, Record View and
   logging metadata, configured streams with zero actual samples, unknown raw payload hex, every
   decoded record with file offsets, parser diagnostics/damaged spans, and uniquely named replays.

The Replay page groups What-if parameters into Process Model, Initial Covariance, Measurement
Noise, and Consistency Gating. For onboard algorithms, What-if copies the complete firmware actual configuration;
for algorithms absent from firmware it uses plugin actual defaults. Incomplete firmware
configurations cannot be completed with offline defaults. The form scrolls when taller than the available window.
Every combo box uses a conventional downward popup with at most ten visible rows; longer lists
scroll inside the popup. Flight and State Estimation each provide a page-level **Reset Charts**
button that restores every 2D chart on the page after manual zooming or panning.

Chinese and English interface text and Light/Dark themes are built in. Export language defaults
to **Follow UI**, with explicit Simplified Chinese and English choices. Standard PNG plots,
the deploy-segmented mission-relative ENU trajectory, and the combined attitude/trajectory GIF use
matching `_ZH` or `_EN` filenames and localized titles, axes, and legends. The GUI and export
share the same rocket attitude model, START-relative origin, and deploy/landing/current markers.
For a SilverStar project root, export defaults to `Log/<LogStem>_Export/`.
With a standalone `.ssflp` project, export defaults to `<project-directory>/Result`;
a temporary log defaults to `<log-directory>/<log-stem>_Data`. The destination remains editable, no fixed drive is
used, and FLP does not offer a source-code-package export.

An FCCG `SilverStar.ssproject` may sit beside a log, decoder, and `.ssflp`, but FLP neither parses
it nor treats it as authoritative. The only decoding authority remains the exact match between
the BIN/SSLOG Descriptor and `.ssdecoder` 1.2.

## What the parser supports

The trusted built-in container ID is `silverstar.flight_log.container.0_0`. It supports
SSLOG0's 64-byte file header, 24-byte common record header, payload, CRC-32/IEEE trailer,
resynchronization, truncation handling, and raw-frame diagnostics without knowing any Record
fields or channels.

The firmware/FCCG schema ID `silverstar.sslog.container/0.0` is accepted only as an audited name
for this same built-in wire contract; it does not register or execute a second plugin.

Production opening is exact and configuration-driven. `LogOpenCoordinator` validates one package
schema 1.2, requires a matching 64-byte log Descriptor, imports the verified package into the
content-addressed cache, creates `DecoderProfileParserPlugin` dynamically, parses the Catalog,
then applies Project Semantics and calibration before publishing a dataset. GUI manual import,
bounded folder search, drag/drop, CLI, and project restore use this same atomic path. There is no
Descriptor-less, package 1.0, unsigned, fixed-parser, or filename-based production fallback. See
[Decoder_Profile_Package.md](Decoder_Profile_Package.md).

- Unknown CRC-valid types/versions retain their raw bytes and mark the dataset partial.
- A bad CRC, invalid length, or lost sync performs a bounded scan; a `FLG1` candidate is accepted
  only after header, length, timestamp, complete-frame, and CRC validation.
- Bad frames are excluded without payload repair. Diagnostics retain recovered offsets and a
  bounded raw-hex preview of each damaged byte span.
- An incomplete final record is reported as a truncated tail and ignored.
- Record counts, CRC errors, recoveries, sequence gaps, unknown types/versions, and offsets are
  retained in parser diagnostics.
- Decoded Records retain file order/offset even when interleaved timestamps regress. Each channel
  independently sorts its real `timestamp_us`; unlike-rate sensors are never forced into one table
  and timestamps are never rebuilt from nominal rates.

A ready calibration mode `NONE` is a legal identity model (zero bias, unit scale, zero
sample/reject/retry counts) even when only `SixFace` is configured; its `start_sequence` is
provenance and may be nonzero. A configured/online GNSS with no fix and zero usable fusion
measurements is also legal. These states are reported explicitly instead of being treated as
missing packages or parser failure.

AIR telemetry frames are intentionally not treated as flight logs. See [SSLOG.md](SSLOG.md).

## Navigation replay semantics

At successful `START`, `INITIAL_STATE.q_nb` freezes the adopted WXYZ Hamilton Body-to-ENU
attitude. After that boundary, the mission attitude is propagated entirely in software. The
hardware quaternion remains a diagnostic reference and is never used as the authoritative
post-START replay attitude.

The Replay GUI always uses **Corrected IMU** and does not present an input-source selector. The
algorithm API and CLI retain two explicit, non-interchangeable sources for validation and
advanced workflows:

- **Corrected IMU**: trapezoidal subintervals, two-sample coning/sculling, quaternion propagation,
  Body-to-ENU specific force, gravity removal, velocity, and trapezoidal position.
- **Recorded Inertial Increment**: uses the recorded coning/sculling output and re-runs the same
  quaternion/velocity/position mechanization.

KF6 uses state order `[pE,pN,pU,vE,vN,vU]`, the order in current `navigation_kf.c`. It restores
P0, process acceleration standard deviations, NIS thresholds, and maximum soft-R scale; then it
uses the independent mechanization prediction plus logged GNSS and barometer measurements. It
exports full P, innovations, effective R, NIS, accepted/soft/rejected results, and reacquisition
diagnostics.

Every result is labeled:

- **Recorded** — values actually logged by the flight controller;
- **Recomputed** — replay using the recorded configuration;
- **Offline** — replay using the offline plugin's declared defaults;
- **What-if** — replay with explicitly modified parameters.

Separately, fidelity is `EXACT`, `APPROXIMATE`, or `UNAVAILABLE`. Missing required input never
causes a hidden source switch. Build mismatch, data gaps, missing measurement-application timing,
or decimation lower fidelity with an explicit warning. Input gaps are segmented without silent
interpolation. `EXACT` additionally requires clean source integrity and a matching immutable
host-C Golden reference. See [Replay.md](Replay.md) and
[Architecture.md](Architecture.md).

## Command line

After installation:

```powershell
sslog inspect D:\logs\flight.BIN --decoder D:\logs\flight.ssdecoder
sslog replay D:\logs\flight.BIN --decoder D:\logs\flight.ssdecoder --algorithm silverstar.algorithm.pure_ins --mode offline --source corrected_imu
sslog replay D:\logs\flight.BIN --auto-find --algorithm kf6 --parameter process_accel_std_u=2.5
sslog export D:\logs\flight.BIN D:\exports --decoder D:\logs\flight.ssdecoder --language en_US --theme dark
sslog gui D:\logs\flight.BIN --auto-find
```

`inspect` also prints package/generation identity, semantic context, calibration, firmware
components, and independent algorithm availability. Algorithm IDs are resolved dynamically from
the offline registry. CSV export is one file per channel so every sensor keeps its own timing.

## Tests

```powershell
python -m pytest -q
```

The repository fixtures are generated in memory and are explicitly named **SYNTHETIC**. Tests
cover all current payload layouts, unknown records/versions, CRC recovery, sync recovery,
truncated tails, sequence gaps, stationary Pure INS through both input chains, KF6 covariance and
NIS rejection, calibration/alignment/deploy summaries, replay-result coexistence, active-source
readiness and return-to-Recorded behavior, Flight/State Estimation read-only source displays,
dual Recorded navigation layers, unique plot colors, camera preservation, relative-origin 3D
rendering, rocket PNG/GIF export, the 30 fps combined GIF, partial export failures, project
immutability, and a headless five-page GUI smoke test. Dedicated decoder-profile tests cover ZIP
limits and attacks, checksum/schema validation, the complete scalar whitelist, payload-size
contracts, two IMU instances, canonical channels, same-physical-device capability linkage,
Descriptor hash matching, atomic coordinator opening, mandatory/identity NONE calibration,
including nonzero start sequence and configured-SixFace independence, zero-copy immutable
aliases, online/no-fix GNSS with zero measurements, multiple Alignment/INITIAL_STATE authority,
candidate-validated bounded recovery, per-channel timestamp sorting, CLI integration,
audit-manifest provenance, cache reuse, bounded parent discovery, and trusted `.ssplugin` factory
allowlisting. Package 1.0/1.1 and unsigned layouts are explicit rejection cases.

No real flight log is included. Phase 2 requires frozen real logs and host-C golden vectors from
the matching flight-controller build; this is tracked in [TARGETS.md](TARGETS.md).

## Windows packaging

Install the `packaging` extra and run:

```powershell
.\打包.bat
```

The PyInstaller output appears under `dist\SilverStar_FLP`. Run the test suite before packaging.
PyInstaller preparation is included, but a distributable build is not committed to source
control.

## Design boundaries

Users manage two log-decoding layers:

- trusted Log Container Plugin code for one incompatible container generation;
- one exact data-only `.ssdecoder` 1.2 per generated project.

Internally, Algorithm Plugins remain the separate replay/estimation extension point. A
`.ssdecoder` may describe recorded algorithm streams, but field layout alone cannot implement or
reproduce a new navigation algorithm.

Pure INS and KF6 are the only first-release Algorithm Plugins. Deploy and landing replay are Core
flight-analysis services. ESKF15 and ESKF24 are future targets only; their interface can be added
without changing the standard navigation pages, but neither is implemented now.

## Source of truth and remaining risk

Record/semantic authority comes from the exact matched `.ssdecoder`; algorithm implementation is
still audited host code. The external SS0014 compatibility sample proves current 0.0.10 package
matching, corruption exclusion/recovery, semantic adaptation, GUI degradation, and audit export
when its opt-in gate is run. It is not a numerical host-C Golden. Pure INS and KF_6 therefore
remain `APPROXIMATE` for firmware 0.0.10 and retain build identity `SILV0008`. Never claim
`EXACT` until the matching immutable real-log and host golden gate passes.

## Display quality and workspace maintenance

Arrays now inherit semantic axis labels, and GUI/PNG/GIF share event-point drawing geometry that
keeps true data gaps visible. Overview distinguishes sequence-gap segments, missing IDs, and
recorded queue counters. See [Display_DataQuality.md](Display_DataQuality.md).

Run `python tools/clean_workspace.py --dry-run` to inspect bounded cleanup candidates, then
`--apply` to remove only verified generated files. See [Workspace_Cleanup.md](Workspace_Cleanup.md).
