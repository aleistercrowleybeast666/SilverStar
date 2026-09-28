# Changelog

## Unreleased

- Finalized the FCCG-style project shell: added the compact current-project header, New/Open/Save/
  Save As/Import/Export/Exit menu and shortcuts, removed the duplicate toolbar, and added minimal
  dirty-state Save/Discard/Cancel handling.
- New Project now reserves a user-selected `.ssflp` destination but writes it only after exact
  log/decoder validation. Export defaults to the adjacent `Result` folder for projects or the
  log-adjacent `<stem>_Data` folder for temporary sessions; the fixed D-drive default is removed.
- Kept Project v3 and relative source references. `.ssproject` remains an unparsed sidecar and no
  source-code-package export was added.

- Migrated to exact package/Project Semantics 1.2, independent Catalog 1.0 and Project v3.
- Replaced four relative-default KF6 controls with FCCG actual parameter metadata; recorded
  configuration comes only from firmware resolved values. Added distinct What-if reset origins,
  exact unedited value preservation, draft save/restore and actual export provenance.
- Added strict parameter contract checks, frozen default equivalence and matching dynamic
  synthetic replay tests. Core INS/KF6 equations and measurement timing remain unchanged.
- Retired 46 historical test-run directories (2,397 mistakenly tracked generated files) at the
  user's explicit request; ordinary cleanup keeps conservative input/link protections.

- Unified semantic array columns with explicit Catalog metadata priority and bracketed unknown
  indices, preserving raw/stable zero-copy aliases and audited position-first KF6 order.
- Unified GUI/PNG/GIF event phase geometry with shared visual event points and channel-cadence
  breaks; source samples remain immutable and true gaps are never interpolated.
- Split Data Quality sequence-gap segments/missing IDs, cumulative queue counters/event counts,
  structural integrity and mission phase evidence; added bilingual per-gap diagnostics and
  per-channel cadence/column export provenance.
- Added a conservative dry-run/apply workspace cleanup tool, generated-directory ignore rules,
  safety regressions, and a separate hash-locked current SS0000 compatibility/display gate.

- Adapted exact `.ssdecoder` 1.1 opening to the current FCCG 0.0.10 Record Catalog and Project
  Semantics without adding legacy/package/fixed-parser fallbacks.
- Accepted ready identity `CALIBRATION_RESULT mode=NONE` independently of configured one/six-face
  procedures, allowed nonzero `start_sequence` provenance, and selected the latest valid result
  before START while retaining all attempts.
- Added candidate-validated, byte/candidate-bounded current-SSLOG0 recovery with CRC/length/
  resynchronization counts, damaged-span offsets/raw hex, corrupt-frame exclusion, and no payload
  repair.
- Added explicit immutable Data Quality, GNSS online/fix/usability and configured-zero-sample
  semantics, per-channel timestamp ordering, multi-Alignment history with `INITIAL_STATE`
  authority, and current SYSTEM_CONFIG/stream-descriptor cadence compatibility.
- Extended the existing five-page GUI in its original style with GNSS/Data Quality cards and a
  Data Explorer diagnostics inner tab; decoded records now expose file offsets and configured
  zero-sample streams.
- Extended algorithm input-contract metadata, approximate gap handling, CLI inspection, and
  export manifests with alignment/GNSS/integrity/configuration/channel provenance.
- Added synthetic regression coverage and a hash-locked, opt-in, read-only SS0014 compatibility
  gate. The sample is not a numerical Golden, so FCCG 0.0.10 replay remains `APPROXIMATE`.

## 0.0.2

- Added complete SSLOG0 profile 0 parser and all current record layouts.
- Added immutable multi-rate FlightDataset and parser integrity diagnostics.
- Added complete Pure INS replay from corrected IMU or recorded inertial increments.
- Added KF6 prediction, GNSS/barometer updates, P/NIS diagnostics, and What-if parameters.
- Added deploy/landing analysis, recorded/recomputed comparison, and automatic overview.
- Added five-page PySide6 GUI, fixed product title/version, dark-blue brand/side/tool bars,
  light-blue selected states, global tab styling, top-bar language/theme controls, modal
  import/export options, conventional scrolling combo boxes, larger 3D views, and Replay scrolling.
- Fixed GUI Replay input to corrected IMU while retaining recorded-increment support internally.
- Added a Replay-only Analysis Data Source selector with Recorded fallback and complete-result
  eligibility; Flight and State Estimation now show the source read-only.
- Kept Recorded Pure INS and Recorded KF_6 as distinct chart/export layers with non-repeating
  colors.
- Added the GSHC-style quaternion-rotated rocket mesh, mission-relative trajectory origin,
  point-only deploy/landing/current markers, reset/lock controls, and camera-preserving playback.
- Localized the Header display name and developer credit, added the `v` version prefix,
  brand-colored Windows caption, readable blue Header dropdowns, and accent-blue navigation.
- Reordered File/toolbar actions, added safe Project Save As, standardized the Chinese term
  `工程`, and added page-level reset controls for every 2D chart page.
- Synchronized the six rocket face colors with GSHC; segmented the trajectory/current point into
  red pre-deploy and blue post-deploy phases; and replaced the fixed pixel Deploy symbol with one
  orange, trajectory-extent-scaled world-space point in the GUI, PNG, and GIF outputs.
- Added estimator visualization metadata for state/measurement groups, generated the State
  Estimation page without KF6-specific channel IDs, and covered future ESKF-style state and
  magnetometer declarations with a test-only plugin.
- Grouped What-if parameters by engineering role, exposed parameter IDs and physical tooltips,
  added a modified indicator, and made Reset restore recorded SYSTEM_CONFIG/header values.
- Kept File-menu actions contiguous, including no separator between Save Project As and Open
  Project.
- Added reference-only projects and independent-language CSV/JSON/PNG/GIF export.
- Added CLI, synthetic integration tests, and PyInstaller preparation.
- Split SSLOG0 framing/CRC/recovery into the trusted
  `silverstar.flight_log.container.0_0` container plugin; the production registry now constructs
  only an exact package-driven parser after Descriptor validation.
- Added strict, non-executable `.ssdecoder` loading with bounded ZIP validation, checksum and
  schema enforcement, container compatibility, whitelist-only Record decoding, instance-aware
  project semantics, raw unknown-Record retention, Descriptor hash matching, bounded task-folder
  discovery, content-addressed caching, and a protected `.ssplugin` trust boundary.
- Enforced package/project-semantics schema 1.1, exactly five signed members, mandatory Descriptor
  and Calibration Result, and exact generation-profile matching; removed 1.0, unsigned,
  Descriptor-less, filename, and fixed-parser production fallbacks.
- Added one atomic single-log coordinator for manual pair import, bounded folder search, strict
  drag/drop, CLI, content cache, and `.ssflp` v2 restore with full decoder identity checks.
- Added immutable `DatasetSemanticContext`, zero-copy raw-to-stable aliases, typed event names,
  authoritative NONE/one-face/six-face calibration selection, and semantic GUI pages while
  preserving the established GUI style and five-page navigation.
- Separated firmware component membership, actual recorded outputs, complete recorded parameters,
  and offline plugin availability. Added Offline mode and retained `APPROXIMATE` plus explicit
  warning for unproven FCCG 0.0.10 Pure INS/KF_6 equivalence.
- Expanded audit export/CLI inspection with log/package hashes, project/firmware/hardware/protocol
  metadata, calibration, aliases, and replay provenance.
- Added synthetic dual-IMU, same-physical-device multi-capability, strict rejection, coordinator,
  calibration, CLI, project v2, immutable-alias, and audit-manifest regression coverage.

### GUI shell consistency closeout

- Added FCCG-aligned File/Plugins/Help menus, project-before-stretch header ordering, bilingual registry-driven Plugin Manager and About dialog.
- Install/Refresh use only explicit-trust `.ssplugin` container discovery; unsupported algorithms are rejected and activation requires restart plus a host-allowlisted factory.
