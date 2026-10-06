# SF6 compact callback stack checkpoint (2026-10-06)

This revision changes the owning core checker and its reference overlay,
not target firmware, task sizes, protocols or failure expectations. It keeps
256 bytes of context allowance and the existing 256-byte minimum task margin.
Dynamic frames, recursion, missing selected-source `.su` reports and unknown
indirect instructions remain failures.

For the selected compact MPU6050 I2C path, the checker verifies the canonical
initialization and dispatch bodies, the selected source graph and direct
initialization callers. The actual linked read-only profile, ARM layout and
getter literal must agree; prepare/frame_read/extra_verify must be NULL in
the ELF. Register read/write dispatch adds the concrete adapter callbacks
and their full PlatformI2c, HAL and deadline descendants. A function name
alone earns no callback exemption. Changed bodies require a gate review.

Startup operation tables come from selected JY901B and/or M9N sources. All
seven callbacks remain covered. M9N recovery retains its immutable operation
table through controller.config, with either its separate or inlined caller
form. The M9N-only RF path no longer requires an unselected JY901B initializer.
SamplePoll's 112-byte frame and the 344-byte GNSS processing frame are nested
with their ancestors, never represented by a zero-cost callback exception.

The selected F1 FatFs provider is `sd_diskio_stm32f1flight.c`, not the unused
CubeMX generic sd_diskio.c. R0.11 declares SD_Driver writable: the checker
does not call it immutable. It verifies the exact fixed five-entry table,
registration/dispatch source fingerprints, source references, direct callers
and actual ELF initializer pointers. This records the existing vendor ABI
exception and does not authorize another callback registry. F4's existing
write/ioctl conditional slots remain supported when their callbacks are linked.
No F4/H7 HAL or RTOS implementation changes.

Real Release ELF results, with GCC 14.3.Rel1 and their complete `.su` sets:

| Target | Device estimate / configured | Logger estimate / configured | Result |
|---|---:|---:|---|
| RET6, SF6 + MPU6050/E28/BMP280/local SSLOG | 1720 / 2560 | 3072 / 3072 | FAIL: Logger margin 0 < 256 |
| RFT6, same plus M9N | 2112 / 2560 | 3072 / 3072 | FAIL: Logger margin 0 < 256 |
| F407, Full reference with JY901B/M9N/KF6 | 2144 / 2560 | 2104 / 3072 | PASS: all eight configured task budgets |

The F1 logger path includes the 1128-byte `f_open` frame and the actual disk
callback subtree. The next firmware batch must supply at least the missing
256-byte task margin without reducing this threshold, and record the real
linked RAM impact. No stack allocation was changed in this checkpoint.
Current RE/RF firmware ELF hashes remain those of ec1bfcd; a changed checker
is not a new firmware binary.

The 34 Host checker cases cover both selected startup sets, callback subtree
depth, changed bindings, non-NULL/writable MPU profiles, unknown callers,
extra indirect calls, recursion, missing frames, SD aliases/initializer
mutations and insufficient margins. These are injected tool-output fixtures;
actual ARM ELF checks are separate. The corrected ordinary MPU fixture now
selects Full tier explicitly; its three tests pass. Earlier compact_mode-only
fixture results did not prove Full behavior under the authoritative tier model.

F407 fresh ARM compilation/link succeeds. The six selected JY901B/M9N,
source-selector and startup Host executables complete, but their runner then
fails the mandatory storage integrity case at its stream configuration
expectation (test_logger_storage.c:372). This is a failed invocation, not a
selected or full-suite PASS. Historical full F1 Host failures remain recorded.

Evidence is `.work/evidence/f103_stack_closure`: complete commands/logs,
checker dirty snapshot, emitted-gate results and ELF-associated stack JSON.
The normal F407 project uses repository board payloads; this small regression
did not run CubeMX or establish hardware evidence. RE/RF reuse the previously
executed official CubeMX projects. Text Power10, real analyzer and ARM results
for unchanged F1 firmware retain their prior ec1bfcd scope; no new full safety
suite result is asserted here.

MSP/main, ISR nesting, runtime high water, timing, library semantic contracts
and the complete manual critical-contract review remain NOT PROVEN. Task
stack PASS alone is not a whole-firmware stack proof or acceptance.

## MPU readmission boundary, still pending

Physical recovery currently leaves qualification_revoked latched. Neither
SystemImuSample nor SystemInertialSample transports the native configuration
epoch. A current IoDetail query cannot prove the epoch of an already copied or
queued sample. Merely clearing healthy after configuration, incrementing
CAL_NONE/ALIGN generations, or ignoring the historical startup failure would
not satisfy readmission.

A safe next batch must review device publication, the inertial bridge and
queue consumers, calibration collection/commit, alignment including barometer
origin, health's historical startup mission_capable gate, and START's final
publication after potentially asynchronous storage work. These are shared
core consumers and require a small normal F407/JY901B/M9N regression. A
compact-only internal sample epoch would change RAM/stack/queue layout and
must be measured; serialized AIR M0/SSLOG record layouts need not change.
No such extension or historical-health bypass was implemented here.

Faults during calibration, alignment, origin collection and each START/storage
boundary must revoke current admission while retaining historical diagnostics.
START source locks must survive; retries must reuse the same device instance.
User-selected calibration/alignment and fresh barometer origin remain required.
GNSS no-fix remains ordinary navigation unavailability. SF6 already excludes
its unused double-window integrity machinery; the approximately 6936-byte
GNSS origin/ENU sample storage is not that machinery and is not removed.


## 2026-10-06 binding-checker correction (after 84b336e)

The previous F407 task PASS is historical output from an incomplete binding
checker; it must not be presented as a closed binding proof. Parent review found
extra startup/disk indirect instructions, a second operations assignment, an
external FatFs registry write, and MPU RuntimeOwnerActivate bus/profile writes
that the old checker accepted. The unmodified old checker accepted all six
initial regression mutations. These are tool trust defects, not observed bad
bindings in the recorded actual ELF files.

The revised `silverstar.reviewed-callback-bindings/2` contract freezes complete
selected C translation units and their complete GCC-reported project headers
and dependency lists from the three recorded builds. Hashes retain macros,
string whitespace and comments; only CRLF normalization follows Python text
reading. This deliberately restricts automated binding acceptance to reviewed
source versions. Unknown builds, changed consumers, headers, write entrances,
dependency graphs or compiler shapes FAIL and require fresh manual review; the
checker does not infer arbitrary C alias or callback provenance. This does not
change algorithm selection, product return contracts, stack allocations, margin
thresholds, or production firmware. Blank translation units have no writes and
may be admitted with their exact one-source dependency rule. Injected ELF unit
fixtures explicitly mock their dependency metadata and are not ARM evidence.

Every reviewed FatFs dispatch function has exactly one linked indirect site,
including BX ip tail calls. Its actual call-register load must select the expected
slot. Both F1 and F4 registration/dispatch implementations, consumers and ABI
headers are checked; the ELF table bytes must identify all five concrete targets.
F1's table remains writable under the upstream R0.11 ABI: this proves reviewed
initialization and write entrances, not resistance to arbitrary RAM corruption.
Startup Release has exactly seven linked Tick callback sites in the reviewed
slot sequence 4,0,8,12,16,20,24. Each selected read-only 28-byte operations table
must contain the exact seven linked callback addresses and appear in its owning
initializer's ELF literal pool. Unsupported Debug/inlining shapes remain NOT
PROVEN. Existing MPU NULL-profile checks, concrete bus edges and exact one-site
checks remain, while complete files now include RuntimeOwnerActivate.

Actual emitted gate rechecks use unchanged linked ELF artifacts, their `.su`
and `.d` files, and the revised owning tools copied byte-for-byte into the three
explicitly disposable projects. RE/RF task gates still FAIL for Logger margin;
F407's eight task budgets pass again within the narrower versioned task scope.
The report explicitly marks whole-program stack acceptance NOT PROVEN for
main/MSP, ISR nesting and hardware evidence. No full-suite pass is inferred.
Evidence is `.work/evidence/sf6_binding_v2_final`, with failed exploratory unit
runs and old-checker escaping counterexamples retained separately in
`.work/evidence/sf6_followup_attribution`.

## Read-only Logger attribution

RE and RF both report 2816 bytes of nested known frames plus one retained
256-byte context allowance, giving 3072 bytes against the actual 3072-byte
Logger allocation. Margin is zero. The 256-byte minimum is a gate threshold,
not additional linked RAM. No budget, allocation or context allowance was changed.
The present bound would need at least 3328 allocated bytes to satisfy that
threshold, conditional on no newly discovered larger paths; this is not a
recommendation to allocate it or a whole-program stack proof.

The exact chain (frame bytes) is:

`AppTask_Logger(480) -> SystemMissionSnapshot_FinalStatusWrite(456) ->
MissionSnapshot_SectionCommit(32) -> PersistentStorage_ObjectWriteAtomic(72) ->
PersistentStorage_LatestGet(64) -> SystemStorage_ObjectSlotRead(136) ->
f_open(1128) -> dir_register(72) -> dir_find.part.0(48) -> dir_next(40) ->
create_chain(24) -> get_fat.part.0(32) -> sync_window(16) -> disk_write(8) ->
SD_write(40) -> SdDiskIo_CompletionWait(24) -> xQueueReceive(40) ->
xTaskResumeAll(8) -> xTaskResumeAll.part.0(48) -> xTaskIncrementTick.part.0(48)`.

This is a conservative graph path, not a demonstrated simultaneous execution:
ObjectSlotRead passes FA_READ, while f_open calls dir_register only under create
mode bits. That named edge combination is infeasible for this caller. Other
write/dirty-window paths remain reachable; this does not justify deleting the
write subtree or replacing the gate with an unproved smaller bound. Also,
xTaskResumeAll restores its 8-byte frame before tail-branching to its part.0
function; conservative nesting counts both. The context allowance covers more
than a non-FP CM3 task context but remains unchanged. ISR/MSP proof is absent.
Full call-site disassembly is saved in the attribution evidence.

The actual f_open prologue saves 36 bytes and reserves 1092, matching GCC's 1128
frame. The selected F1 FatFs header embeds a 512-byte sector union in local DIR
when `_FS_TINY==0`; DIR is 552 bytes here. Stack LFN mode 2 adds a separate
512-byte WCHAR[256], plus short-name and ordinary locals. This is real frame
allocation, not merely duplicated call-graph accounting. It is not two history
buffers and must not be described as such.

The lowest-scope candidate is a coherent small recovery-flags getter, leaving
snapshot section 7's serialized fields unchanged. The current getter copies a
272-byte SystemFlightRecoveryStatus into a 456-byte FinalStatusWrite frame,
but this writer uses only three flag bytes and two results. A reviewed 12-byte
projection could remove about 260 bytes of unnecessary copy capacity without
moving it to BSS; the actual reduction requires before/after ARM compilation.
StorageHealth similarly copies 80 bytes for two flags. These are candidates,
not implemented savings. They need task-owner/coherent snapshot review and F407
regression. Separating the record-drain lifetime is secondary: FlightLogRecord
is 200 bytes, not 432; the 480-byte task frame includes additional compiler
locals/inlining, so no 480-byte saving is promised. `_FS_TINY` or DIR ABI changes
need a separate upstream/ownership/performance review; moving LFN to a static
buffer or blindly truncating names is not authorized by this report.

## Same-configuration baseline attribution

F407's InputVoltage architecture violation occurs under the old ec1bfcd checker
on the same generated configuration and source. Its power_service, log policy,
writer fixture and generation/feature-tier sources are byte-identical between
ec1bfcd and 84b336e. The small Host log-policy replay uses the same actual generated
F407 configuration, repeats the storage fixture's unconditional stream enable,
and compiles ec1bfcd and current policy sources independently. Both compile and
both fail identically at record 0x07: unsupported, result 5. This isolates the
previous StreamConfigure expectation failure; it is not a full storage-suite
pass or permission to weaken that expectation. Initial fixture compilation
errors and their corrections are retained. The replay mocks critical sections
and assertions and does not test their implementation.

## Dependency and empty-source correction after 993a0c5

Independent review found two fail-open paths in the recorded-source contract:
GCC dependency verification ignored inputs without a `.h` suffix, and a generic
empty-source exception allowed any selected C translation unit to be erased.
Four new negative cases demonstrate these failures under the old checker:
changing or removing the reviewed BMI088 `.inc`, emptying its nonempty C owner,
and supplying an unknown empty C file. The old checker accepts all four.

The owning checker and reference overlay now verify every reported compiler
dependency, including the primary C source, against the existing path-specific
reviewed fingerprints. Both generic empty-source and empty-dependency-graph
exceptions are removed. A source originally reviewed as empty is allowed only
when its exact path and empty hash are already in the reviewed contract. The
synthetic ELF fixture declares its test.c empty hash explicitly in test scope;
it does not add a production exemption. No fingerprint lists or task thresholds
were enlarged. All 72 checker/architecture regression cases pass after the fix;
the recorded RE/RF/F407 input sets verify 143/150/153 selected translation units.

This correction changes tools and tests only. Rechecking their recorded ELF and
dependency artifacts is not fresh firmware compilation, analyzer execution,
runtime validation or whole-program stack acceptance. Logger's F1 margin failure,
the F407 InputVoltage architecture failure and the MPU requalification work remain
open. The reviewed contract still is not a general C alias or call-graph analyzer.
