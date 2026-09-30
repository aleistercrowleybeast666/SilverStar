# Mission snapshot and final status (0.1.0)

The Flight logger owns all mission snapshot FatFs operations. Before it admits
streaming and before `START` can pass its storage gate, it writes a bounded
binary `SSMS` snapshot for the reserved mission directory. The format has its
own schema revision (`2`); it does not change AIR M0, SSLOG 0.0, or the
SilverStar product version.

Each object has an eight-byte prefix: `SSMS`, schema revision, logical section,
entry count, reserved byte. Integers are little-endian. An object is at most
512 bytes and is persisted through `PersistentStorage_ObjectWriteAtomic`,
which syncs, reads back, checks CRC, and commits a dual-slot generation.

| Logical section | Contents |
| --- | --- |
| 0 | Commit header: bank, mission and profile identity, project digest, SilverStar version/build tag, no trajectory plan, IMU ODR/aggregation/propagation rate, selected source instances, calibration identity, AIR PHY, bounded alignment strategy/constraints/yaw/source masks, and each section generation/hash. |
| 1–2 | Selected device descriptors, physical identities, instances, capabilities, rates, and generated driver/model hashes. |
| 3 | Selected algorithm descriptors and configuration digests. |
| 4–5 | Generated actual algorithm parameter keys, types, and binary32/int32 values. |
| 6 | IMU correction values and generation/hash, plus the current magnetometer instance 0 calibration object generation/hash when available. |
| 7 | Best-effort final state: mission/time, lifecycle, landing/deployment, logger/storage faults, health masks, and recovery results. |

The snapshot has two complete banks. Bank A uses object instances `0–6`;
bank B uses `8–14`. Section 7 is the independent final-status object. Updates
write only the inactive bank, then write its section 0 header last. The
previous committed bank remains intact if a section write or readback fails.
The commit header has a monotonically increasing snapshot sequence within a
mission. The logger exposes the committed bank, sequence, and generation in
its diagnostics. A failed required snapshot write blocks `START` as storage
not ready. A failed final-status write is recorded in logger diagnostics and
does not alter Flight or Recovery.

Source priority follows the generated source selector contract: a descriptor
marked primary is tried first, then remaining instances in ascending instance
order. Section 0 records the chosen IMU and GNSS instances, while sections
1–2 retain the descriptors and primary flags needed to reconstruct that
priority. The IMU choice is locked before alignment; the existing GNSS and
telemetry one-way failover policies remain in force.

`project_mission_parameters.c` is generated from selected manifest parameters
and their effective values. Its bounded table is the authority for the
parameter sections. Section 0 also freezes the selected alignment algorithm,
two to six typed constraints (kind, body axis, weight, declination and
true-north azimuth), yaw authority, ENU yaw and selected/required source masks.
The snapshot stores no JSON and does not parse a project file on the MCU.
At START, the logger also emits SSLOG `MISSION_SNAPSHOT_IDENTITY` version 1
(record `0x29`). Its fixed 24-byte payload records the committed mission ID,
commit generation, snapshot sequence, IMU calibration generation,
magnetometer calibration set hash, bank base instance and READY flag. FLP
decodes this identity from the matched log/decoder pair; the authoritative
snapshot contents remain the dual-slot objects on the flight storage medium.
For each configured magnetometer instance, SSLOG
`MAG_CALIBRATION_IDENTITY` version 1 (record `0x2A`) separately records the
physical device ID, instance, active/saved state, load result, persistent
generation and frozen calibration set hash. This preserves per-device
provenance even when alignment uses an external attitude source.
The mission-local object paths are under
`0:/missions/<mission-id>/`; they are distinct from the user-selected project
root and its `Log/` folder.

Evidence: the generated F407 Host suite exercises the START gate and a
final-status failure; the real FatFs Host integrity fixture reads back both
banks and section 7. The F407 ARM Release build and Power of Ten checker also
cover the first-party writer. Physical media failure and target WCET remain
hardware-validation work.
