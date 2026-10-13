# Maintenance 0.1 scope decision — 2026-10-13

**Superseded proposal:** the user replaced the generic variable-directory/watch
plan below with lightweight runtime diagnostics and log management. No generic
watch list, arbitrary symbols, memory access, IDE, breakpoints, SWD or writes are
included. The numbered text is retained as historical planning, not active scope.

The implementation adds a bounded `SYSTEM DIAG` catalog with fixed
task/thread/sensor/storage/communication groups and stable ID/name/state/reason,
source and sample-age fields. Optional counters, units and finite progress use
the shared schema. Same-schema entries render without adding device IDs to GSHC.
Unknown states display UNKNOWN; uninstrumented completion remains unavailable.
One maintenance owner schedules pages, pauses polling during file jobs, and
invalidates observations on disconnect. Legacy FINAL exposes only real 0.0 text
fields and does not acquire LOGFILE capabilities through a desktop update.

Current contract: [maintenance_diagnostics_v1.json](../../../contracts/maintenance_diagnostics_v1.json).
Implementation and evidence: [MAINTENANCE_0_1_20261013.md](MAINTENANCE_0_1_20261013.md).

## Historical proposal (cancelled)

Status: planned follow-up to the verified UART maintenance checkpoint; not a
claim that the new wire operations or GUI variable directory already exist.

1. Preserve the maintenance 0.0 command/response surface, including existing
   device addressing and dangerous operations. Upgrade the default maintenance
   profile to 0.1 with an explicit compatibility declaration and negotiation.
   GUI exposure remains read-only; protocol backward compatibility does not
   authorize execution of START, calibration, configuration, reset or outputs.
2. Add a paged firmware variable directory. Stable field IDs identify typed
   values, unit, source owner, read-only access, required capability and timestamp
   semantics. The registry is declarative and generates fixed direct readers of
   owned RAM snapshots. No arbitrary pointers, symbol lookup or runtime callback
   registration. Query count/line sizes and polling budget are bounded. Unknown
   IDs/capabilities return unavailable, never fabricated zeros. Initial fields
   cover only already reviewed lifecycle, system-health and logger/storage state.
3. Add catalog search and a user-selected watch list to GSHC's fourth page.
   Reconnect invalidates the directory/selection binding and live values; watches
   must match freshly advertised descriptors before polling. One serial owner
   schedules bounded reads and pauses them during file jobs. Display field ID,
   type/unit/source/capability and data age. FINAL uses only its known 0.0 response
   fields with unknown firmware sampling age, labeled as a legacy adapter rather
   than a firmware-advertised directory or a list of all important variables.
4. Verify 0.0 behavior with existing console tests and explicit compatibility
   vectors, then directory paging, malformed/unknown IDs, unsupported capabilities,
   stale/partial snapshots, START exclusion and concurrent file jobs. Generate a
   separately versioned validation project and rerun real Host, ARM, analyzer,
   architecture, artifact and stack gates for the exact new source snapshot.

Version axes remain independent: maintenance **0.1**, file service **1**, SSLOG
container **0.0**, decoder package **1.2**, product **0.1.3**. Wire additions do
not rewrite source logs, frozen releases or the user's FINAL/UNDERLINE artifacts.
The existing LOGFILE subprotocol remains separately negotiated.

Arbitrary C symbols/memory addresses, breakpoints, stepping and variable writes
require a true SWD+ELF backend and matching target identity. They are excluded from
this serial milestone. No probe or port is opened to plan or test this phase.
