# Navigation stack input review v18 — 2026-10-15

Scope: exact compiled KF6/ESKF15 current/legacy development inputs, memory
placement and bounded logger drain. This review updates source/dependency
identities; it grants no new callback, indirect-call, recursion, source exclusion,
library-frame or stack-margin exception. Unknown bytes and graphs still reject.
Whole-program critical contracts and main/MSP/ISR nesting remain NOT PROVEN.

The prior v17 checker predates the selected navigation/logging revisions. Its
rejection is retained, rather than bypassed. Exact candidate inputs come from
the four named generation receipts in `.work/dev013_algorithm_closeout01` and
their real compiler `.d` files. They are archived with per-file hashes; only
compiled input closures are registered. Values are not learned from arbitrary
future projects, user edits or a supplied successful report.

## Reviewed changes affecting the binding

| Input group | Reviewed implication |
| --- | --- |
| KF6/ESKF15 estimator/backend/replay and headers | Direct fixed-dimension numerical/timing paths; no new callback registry or table slot. New transaction and identity state changes frame/object sizes, which must come from the actual ELF and `.su`, not old estimates. |
| INS mechanization | Reused algebraic intermediates; the earlier differential evidence remains its numerical scope. No new indirect edge. |
| Estimator task/bus and fusion timing header | Source/receive/application epochs, bounded receipt state and compile-time mode 0/1 dispatch. Queue is private CPU value storage; memory relocation changes no task entry pointer. |
| SSLOG structs/codec | Versioned v2 records and checked native slot geometry; no function pointer or dynamic dispatch added. Record/stack sizes are evaluated from the compiled selected variant. |
| Logger task | At most four actual drain attempts per service batch, each counted and checked through the existing append/start-barrier failure path. Task scratch ends before snapshot/finalization I/O; new direct frame is included by linked call-graph analysis. |
| Memory headers | Exact F407 zero-covered private section and existing CPU BSS placement. No DMA object is admitted by this source identity review. |
| Generated parameters/configuration | Exact constants, bounded data arrays and checked value getters. Capability routes are uint32 identifiers, not callbacks. Device-instance declarations retain bounded instance counts and existing interfaces. No changed data is silently treated as an old immutable source. |

The six changed compiler dependency closures are retained in full. Added timing
and memory inputs are verified as complete files; includes are not filtered by
suffix. Existing SD_Driver, startup and MPU callback table/register/slot checks
still run on actual linked instructions and reject unreviewed shapes. All other
selected source and dependency identities must continue matching their previous
reviewed versions.

A negative regression exposed that independently approved source and dependency
versions could be mixed: deleting the newly required memory header recreated an
older approved dependency-path list. V18 therefore also binds the complete tuple
of source identity and every ordered compiler input's content identity. Such a
mix must fail even when each individual version was previously reviewed. The
original failing test and earlier draft checker results are retained; only the
final paired-closure run can establish this additional check.

The final KF6 configuration also exposed a catalog-level input difference:
the unselected experimental SX1278 declaration adds physical ID 26 and moves
Power/Storage/Output IDs to 27/28/29. The complete generated header bytes had
already been reviewed for the ESKF configurations. Their combination with the
final KF6/logger inputs was not approved and correctly rejected. Twenty-two
exact complete tuples and one generated decoder-profile source version are
added after comparing the full files; the latter changes only the two identity
byte arrays. No callback body, register, target or stack allowance changes.
The original rejection, exact header/profile and compiler dependency files are
retained. This records the present dirty catalog accurately; it does not admit
SX1278 runtime integration or its still-blocked asynchronous stop lifecycle.

This is a narrow input/callback binding review, not a claim that text searches
prove an acyclic whole program or that every numerical/sequence contract has
completed manual acceptance. Real stack analysis must still reject missing
frames, dynamic frames, recursion, unknown indirect calls and insufficient task
margins. Compiler frames, spare CCM and Host completion are not MCU timing or
hardware stack qualification.
