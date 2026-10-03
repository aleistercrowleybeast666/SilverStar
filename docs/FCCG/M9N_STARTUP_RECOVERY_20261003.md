# M9N bounded startup recovery

Scope: the owning NEO-M9N plugin and synthetic Host regressions. No change to
model/protocol acceptance, UART buffers, the wire protocol, estimator, START,
mission origins, source selection, or any radio/barometer implementation.

## Failure and repair

The original generated C Host counterexample supplies checksum-valid NAV-PVT
at 921600 baud and suppresses MON-VER responses. The full scan fails with
NotPresent at 24200 ms, leaves UART at 576000, and has seen 61 synthetic PVT
frames but no identity. The expected restore assertion fails. This establishes
a software counterexample, not the cause of a hardware observation.

Each instance now remembers the UART baud only at successful UBX checksum
dispatch or successful NMEA checksum parsing. Reading cached PVT or another
instance does not update that value. No valid stream means no restore/retry.
On NotPresent, restore that observed transport; communication does not establish
identity. Raw communication remains visible in native data and I/O diagnostics.
A configured adapter withholds navigation samples and selectable online/healthy
status until startup reaches Ready through the existing complete verification
path. The selector uses online for liveness, so unverified PVT must not block a
verified cold standby. The existing forward-only selection rule is unchanged.

After response/transport failures, the device-task owner schedules at most two
single-baud retries, with 1000/2000 ms backoffs. Each uses strict MON-VER parsing,
the unchanged 23 CFG keys, write acknowledgments, exact readback and a new PVT.
Explicit wrong-model, unsupported-version or malformed-identity rejections stop
retries. All other configuration-stage failures remain failures. Terminal
exhaustion leaves the observed transport restored without scheduling more work.
Runtime transactions return BUSY during recovery. Initial optional-device
failure can complete global startup; the device owner continues finite recovery
without sleeping or changing mission admission.

Original scan candidates and timeouts are unchanged: outer probe 5000 ms;
internal passive/MON-VER/PUBX-settle/rescue waits 200/2200/250/2200 ms.
Recovery does not establish or move mission origins and cannot select a source.
Native recovery diagnostics contain terminal reason, attempt count, saved baud,
last probe result and backoff timing; inspect only from the device owner or an
isolated Host test. Existing wire/log layouts remain unchanged.

## Evidence and limits

Synthetic fault cases cover deferred identity success, permanently silent
identity, wrong model, bad checksum, restore I/O error, unknown protocol and
32-bit clock wrap. Adapter coverage checks online versus healthy, forbidden
navigation samples, runtime BUSY and non-growing terminal error counters.
Multi-instance coverage checks separate saved bauds and CRC/liveness isolation.
Actual estimator/lifecycle tests check late stationary and moving fixes after
an origin-less START. Existing selector tests check recovered old sources do
not reclaim the selected replacement.

Before/after generated candidates, command logs, analyzer reports, source diffs
and ELF/BIN hashes are retained locally under .work/recovery_evidence_* and
apps/FCCG/tests/artifacts/m9_recovery_*. They are excluded from public review.
The work is software-only: no receiver firmware change, target flash, serial
probe, hardware readiness, RF performance or flight qualification is claimed.

## Critical-contract review (Power of Ten adaptation)

Runtime owner: recovery context is mutated by the existing device-task tick;
no new ISR/DMA ownership, heap allocation or blocking wait is introduced.
Loops remain bounded by existing frame budgets, configuration item count and
scan bounds; retries have a hard two-attempt limit, unsigned elapsed timing and
terminal states. Identity and readback guards remain prerequisites for Ready.
Assertions check instance bounds, object contracts, enum range and attempt
invariants. Failure snapshots precede restoration and do not overwrite the
immutable pre-fix counterexample. Host fixtures are not target runtime.

NOT PROVEN: all-runtime NASA Power of Ten compliance, complete interrupt/task
race freedom, target WCET, worst-case DMA discontinuity ordering, composite
stack high-water bounds and hardware recovery. Passing compiler/scanner/analyzer
gates is evidence of those checks, not a proof of these open obligations.

## Reviewed recovery stack binding

Linked Release call path: AppTask_Device -> SystemStartup_ProcessDevices -> SystemGnss_Process -> ProjectGnssInstance_Process -> NeoM9nGnssInstance_Process -> NeoM9nGnssAdapter_Process -> NeoM9nStartup_Tick -> SystemDeviceStartup_Init.

Unchanged DeviceTask reservation 2560 bytes. Real compiler/disassembly worst-known estimate changes 2128 -> 2136 bytes (delta 8); margin 424 bytes. Includes 256 bytes exception/context reservation. These are static budgets, not hardware high-water measurements.

Core Init copies config and adds candidates; it dispatches no callbacks and has no linked path back to native or core Tick. RecoveryBegin is invoked once by the expired-backoff branch, which immediately returns. Native failure preparation is entered only from None/Probing; attempts increment before Init and stop at two. Permanent-timeout fault injection reaches Exhausted and 1000 further ticks emit no additional MON-VER or baud changes. Runtime ConfigApply is BUSY after device-owner activation.

Indirect targets remain exactly the two existing immutable seven-entry JY901B/M9N operation tables; stack analysis conservatively considers both. Unknown caller sets/tables, changed recovery copy provenance or operation pointer, recursion, and unresolved indirect calls remain fatal. Eight binding positives/negatives plus seven existing stack-tool tests passed. Compiler .su frames, linked call chain, Debug object disassembly and full before/after task chains are retained in .work/recovery_stack_review/report.json and adjacent evidence.

Separate pre-existing Debug blocker reproduced on the unchanged base: external SystemNavigationBackend Predict/Initialize/SnapshotGet/Reset references survive -Og in KF6 despite its direct-KF6 source graph. This recovery commit does not fix that build selection or claim Debug linkage passed.
