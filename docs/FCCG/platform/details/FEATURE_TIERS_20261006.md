# Global feature tiers — isolated implementation, 2026-10-06

The first Devices page exposes Global configuration / Feature tier. The tier is
independent of MCU selection. All existing release visibility, source ownership,
protocol, storage, hardware and resource checks remain applicable.

| Tier | Estimators | Active device endpoints | GNSS / maintenance | Local logging / queues |
|---|---|---|---|---|
| Full | All already supported, including pure INS | Existing supported counts | Existing configuration | Existing configuration |
| Standard | SF6, KF6, pure INS; ESKF15 prohibited | Existing supported counts | Existing configuration | Existing configuration |
| Compact | SF6 or pure INS; KF6/ESKF15 prohibited | At most one instance per sensor class and one telemetry instance | Configurable, not forced off | Retained log choices with the bounded-tier policy below; normal queue defaults |
| Minimal | Same as Compact | Same, with GNSS inactive | Both off | Minimum replayable local SSLOG; compact slots and queues |

An explicit incompatible switch chooses KF6 for Standard or SF6 for
Compact/Minimal. Pure INS remains selected. Each departed tier saves a
nonrecursive project snapshot; returning restores algorithms, parameters, modes,
protocol selections and log choices. Device edits, bindings and source overrides
remain current across switches; saved snapshots retain historical device choices
without silently replacing the current devices.
Current MCU/hardware, paths and tools remain current. These snapshots are
inactive configuration, never source-graph providers. Following the 2026-10-08
GUI acceptance correction, extra devices and GNSS remain visible on an
incompatible switch or import. Generation is blocked with a review notice until
the user removes them or chooses Full/Standard. They are never silently removed
to satisfy a tier. Compact/Minimal bound each sensor class independently to one
instance; telemetry is also bounded to one. Minimal prohibits GNSS selection and
addition. Deleting an instance allows one replacement; Full/Standard restore the
ordinary declared limits.

Bounded tiers prefer a dedicated barometer over an embedded endpoint in a
multifunction IMU. The IMU remains active. Two dedicated barometers remain an
error. The first-release magnetometer visibility restriction is unchanged.
This endpoint suppression does not claim that a shared physical driver loses
its internal state or linked RAM.

Project format 17 serializes `feature_tier` as the authority. Legacy
`compact_mode=true` with all-stream logging migrates to Compact; the legacy
`sf6_minimal` combination migrates to Minimal. Opening a legacy incompatible
algorithm preserves its identity and parameters, reports review required and
blocks generation. Dual authoritative fields and contradictory profiles are
rejected. Full projects without tier history retain their earlier dictionary
shape. The old Python `dataclasses.replace(..., compact_mode=...)` idiom is no
longer a tier setter; internal callers use `feature_tier`.

Minimal preserves the existing record IDs and protocol cadence. Metadata,
all stream descriptors, calibration, alignment evidence/results, initial state,
inertial increments, corrected IMU and native barometer records remain; the
selected SF6 or pure-INS output is included. No fictitious native IMU record or
new protocol profile identity is introduced. Original all-stream choices live
in the departed tier snapshot. Following the user's 2026-10-07 decision, Minimal
uses normal/estimator queue depths 24/16 for all MCUs. Its owned startup snapshot
cursor retains every descriptor independently of the ordinary queue, whose FULL
remains an ordinary error. Stream disablement never reduces the descriptor count.
This supersedes the earlier descriptor-count-plus-five / 56-slot-floor default;
the earlier compiled results retain their original queue configuration and scope.
Compact keeps the existing all-stream snapshot capacity contract and normal queue
defaults. Existing navigation queues and task/idle/MSP stack sizes are retained.

The user's latest first-release logging policy applies to all four tiers:
only the selected algorithm's owned output/replay records are eligible. Other
algorithm records, including PURE_INS under SF6/KF6/ESKF15, are unavailable;
there is no extra onboard algorithm comparison or borrowed recorded result.
PURE_INS remains eligible with estimator None, and mandatory in Compact/Minimal
to retain recorded onboard p/v/q. TELEMETRY_DIAG stays optional in Full/Standard
and disabled in Compact/Minimal. Effective projection and generated runtime
support enforce this policy, including legacy configurations, while raw choices
and tier snapshots remain available for restoration. Disabled records
remain in the complete decoder catalog and startup stream descriptors. No queue,
slot, aggregation or stack sizing changed with this policy. Its effects on FLP
fallback acceleration and stillness replay require separate review; this policy
does not establish that those features are unaffected.

Producer ownership was reviewed against the owning payload, rather than inferred
from record names or the generic `algorithm.estimator` capability:

| Record group | Selected producer | Evidence in owning payload |
|---|---|---|
| PURE_INS | None (pure INS) | core `APP/Src/ins_task.c`: both PureRecordWrite call sites require SYSTEM_FUSION_NONE |
| ESTIMATOR, KF6_DIAGNOSTIC, KF6_FULL_P | KF6 | core `APP/Src/estimator_task.c`: backend dispatch returns before the core prediction/LogPush path; LogPush and NavigationSnapshotPush map these records |
| SF6_STATE, SF6_MEASUREMENT | SF6 | SF6 `navigation_sf6_backend.c`: Sf6StatePush and Sf6MeasurementPush |
| ESKF15_STATE, FULL_P_PART, INITIAL_STATE, INITIAL_P_PART, MEASUREMENT, BODY_INPUT | ESKF15 | ESKF15 `navigation_eskf_backend.c`: StateLog/CovarianceLog, MeasurementLog and BodyLog; logger bus maps phase-specific covariance and initial-state IDs |

The backend dispatch evidence above covers normal prediction and initialization.
Existing core rollback/abort paths still call the KF6-shaped LogPush after backend
reset. Those calls do not make the records valid SF6/ESKF15 results: this policy
disables their defaults and runtime support under those algorithms. The common
cleanup implementation is unchanged; no replacement result is manufactured.

ESKF15 body input, measurement and initial records are its own replay contract,
not comparison outputs to remove when ESKF15 is selected. Shared ESTIMATOR_STEP,
GNSS/BARO_MEASUREMENT, GNSS_RECOVERY and NAV_QUALITY retain their existing
availability/profile contracts; they are not added to the exclusive ownership
map. Current core replay diagnostics and dedicated backend diagnostics differ,
so this policy does not certify complete replay availability for every algorithm.
Sensor native/corrected/increments, calibration/alignment, general initial state,
events and lifecycle descriptors are not further pruned. Algorithm/tier rejection
is unchanged: an inactive saved ESKF15 choice never enables it outside Full.

Compact and Minimal retain the earlier reviewed SX128x 260-byte HAL scratch
capacity and bounded device facade, independent of brand. Full/Standard keep
their previous capacity. This is not a runtime-off RAM-savings claim.

The prior RFT6 checkpoint at `ee7a9be` used legacy boolean Compact and reduced
queues. Its 79,080-byte RAM result is historical configuration evidence, not a
measurement of the new Compact tier. A fresh new-tier generation uses the
already executed official RFT6 CubeMX hardware project. The exact RFT6 SRAM
DMA bound is 0x20018000; RET6 remains 0x20010000. Host fault-boundary tests caught
the old RFT6 bound and passed after correction. Fresh ARM results are recorded
separately; no hardware qualification is available.

The B checkpoint remains fail-closed. Readmission is not implemented and its
real CAL/alignment/startup integration failures remain unresolved. This GUI
and compile work does not certify recovery, critical contracts, stack margin,
WCET, accuracy or flight readiness. Barometer-only horizontal navigation remains
inertial dead reckoning and can drift.

Log controls were inspected using actual Qt classes, light/dark themes and both
languages. Disabled checked StandardCheckBox indicators used white checks on a
light surface. The correction is scoped to log controls: grey checked indicators,
disabled-surface unchecked indicators, required available items locked checked,
and unavailable required items unchecked disabled. Disabled palette text stays
consistent with existing controls. Offscreen Qt needed explicit installed-font
loading for readable screenshots; this is an evidence harness detail only.

The 2026-10-06 architecture gate revision checks TELEMETRY_DIAG against the
saved stream plus tier projection: Full/Standard retain the user's enabled
choice; Compact/Minimal emit disabled without overwriting that choice. Policy,
decimation and cadence must still match, with exactly one emitted entry. The
gate recognizes the omitted all_streams serialization default and rejects
mixed tier/legacy authority or contradictory profiles. It no longer requires
an enabled default stream in a tier that deliberately excludes it. Protocol
catalog/schema defaults and the STATS check remain unchanged.

Twenty PowerShell contract cases pass, including incorrect enabled flags,
cadence, decimation, policy, duplicate entries and contradictory configuration.
Actual emitted Release architecture-check passes for RET6 and RFT6. The Full
F407 regression still fails its existing InputVoltage Device-to-System include
boundary; that failure is retained. See `.work/evidence/f103_stack_closure`
for complete failure logs and the separate stack/Host limitations.
