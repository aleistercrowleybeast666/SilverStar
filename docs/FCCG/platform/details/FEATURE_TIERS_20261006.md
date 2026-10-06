# Global feature tiers — isolated implementation, 2026-10-06

The first Devices page exposes Global configuration / Feature tier. The tier is
independent of MCU selection. All existing release visibility, source ownership,
protocol, storage, hardware and resource checks remain applicable.

| Tier | Estimators | Active device endpoints | GNSS / maintenance | Local logging / queues |
|---|---|---|---|---|
| Full | All already supported, including pure INS | Existing supported counts | Existing configuration | Existing configuration |
| Standard | SF6, KF6, pure INS; ESKF15 prohibited | Existing supported counts | Existing configuration | Existing configuration |
| Compact | SF6 or pure INS; KF6/ESKF15 prohibited | At most one IMU, GNSS, telemetry and barometer | Configurable, not forced off | Retained log choices with the bounded-tier policy below; normal queue defaults |
| Minimal | Same as Compact | Same, with GNSS inactive | Both off | Minimum replayable local SSLOG; compact slots and queues |

An explicit incompatible switch chooses KF6 for Standard or SF6 for
Compact/Minimal. Pure INS remains selected. Each departed tier saves a
nonrecursive project snapshot; returning restores its device selections,
algorithms, parameters, modes, protocol selections, log choices and bindings.
Current MCU/hardware, paths and tools remain current. These snapshots are
inactive configuration, never source-graph providers. Extra devices are
suspended with a visible notice and restored by returning to their tier.

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
in the departed tier snapshot. Queue capacity is at least the complete startup
descriptor count plus five slots, with a 56-slot floor; stream disablement never
reduces the descriptor count. Existing task/idle/MSP stack sizes are retained.

The user's subsequent logging policy applies to both Compact and Minimal:
TELEMETRY_DIAG is disabled. PURE_INS is disabled when SF6 is selected; when the
estimator is None, PURE_INS is required to retain recorded onboard p/v/q.
Full and Standard keep both records optional. Effective projection and generated
runtime support enforce this policy, including legacy configurations, while raw
choices and tier snapshots remain available for restoration. Disabled records
remain in the complete decoder catalog and startup stream descriptors. No queue,
slot, aggregation or stack sizing changed with this policy. Its effects on FLP
fallback acceleration and stillness replay require separate review; this policy
does not establish that those features are unaffected.

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
