# Development targets

## Phase 1

- SSLOG0 parser, corruption recovery, complete current Record registry
- FlightDataset, CLI, project model, Overview and Data Explorer
- PySide6 GUI, Light/Dark, Chinese/English, plots and 3D viewers
- Pure INS and KF6 replay, Recorded/Recomputed comparison, What-if parameters
- persistent ReplayResultStore plus Replay-only Recorded/Recomputed/What-if analysis-source
  selection with strict complete-result eligibility
- Overview calibration model, initial alignment, deploy altitude/reason, and event timeline
- consolidated Flight page with separate Recorded Pure INS/KF_6 layers, filter-only read-only
  State Estimation source display, and themed mission-relative rocket/trajectory playback
- Follow UI / ZH / EN standard plot set, segmented trajectory, combined <=60-frame GIF
- partial-failure export manifest
- trusted `LogContainerPlugin` API with the built-in SSLOG0 0.0 container
- exact-only `.ssdecoder` 1.2 import, dynamic Record Catalog decoding, Project Semantics,
  multi-instance raw channels plus stable aliases, mandatory calibration validation, Descriptor
  matching, bounded discovery, and content-addressed cache
- one atomic single-log coordinator shared by GUI import/folder search/drag-drop, CLI, and `.ssflp`
  v3 restore; no production fixed-parser or Descriptor-less fallback
- semantic Overview/Replay/State/Data Explorer pages and audit export manifest with full decoder,
  firmware, calibration, alias, and replay provenance
- current SSLOG0 compatibility: ready NONE identity with nonzero sequence, GNSS online/no-fix and
  configured zero samples, multi-result Alignment/INITIAL_STATE authority, candidate-validated
  bounded corruption recovery, explicit Data Quality, and diagnostic/audit GUI degradation

- FCCG-style project shell: current-project header, toolbar-free File menu, destination-first New
  Project, dirty prompts, relative `.ssflp` references, and project/log-relative export defaults;
  `.ssproject` remains an inert sidecar and Project stays v3

## Phase 2

- validate against real flight logs (including SS0007.BIN when supplied) and frozen firmware C
  golden datasets
- validate the supplied FCCG 0.0.10 package against its matching immutable real log and frozen host
  golden output before changing Pure INS/KF_6 fidelity from `APPROXIMATE`
- retain SS0014 as a hash-locked compatibility/corruption gate; add a separate frozen host-C
  numerical Golden before making any algorithm-equivalence claim
- improve parameter scanning and high-dynamic timing/OOSM analysis

## Future

- ESKF15 Algorithm Plugin
- ESKF24 Algorithm Plugin

No ESKF implementation is part of Phase 1.

## Display and workspace closeout

- Shared semantic array labels with explicit metadata priority.
- Shared event-phase geometry, true-gap preservation, and channel-local cadence diagnostics.
- Explicit startup record drops, missing-ID counts, and independent queue counters.
- Conservative cleanup CLI and regression tests for Git/protected-file/reparse-point boundaries.
- Separate hash-locked current SS0000 display/compatibility acceptance (not a numerical Golden).

## Actual parameter migration and KF6 phase gate

- Package and Semantics 1.2 only, Project v3, actual values and distinct firmware/offline reset.
- Default INS/KF6 dynamic synthetic results match frozen pre-migration Python outputs exactly.
- Real-flight KF6 phase status remains unverified until a matching actual 1.2 log is provided.
- First replay using firmware actual configuration; do not tune Q/R to fit Recorded KF6.
- If lead remains, inspect measurement timestamp, prediction/update order, baro arrival/index,
  P0, first update timing and dt handling in a separately authorized timing task.
- See [validation evidence](Actual_Parameters_Validation.md).

## GUI shell consistency

- File/Plugins/Help menus, project-before-stretch header order, registry-driven Plugin Manager, explicit-trust container install, discovery-only Refresh, and About.
