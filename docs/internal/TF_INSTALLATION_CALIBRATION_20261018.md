# TF installation calibration lifecycle (0.1.3 development, 2026-10-18)

Scope: owning SCG firmware payloads; magnetic ellipsoid intrinsics only. No SPI
Flash, IMU group calibration, relative-rotation solver, hardware action, protocol
upgrade, historical-log rewrite, release or push is included.

## Runtime and durable replacement

The existing maintenance `MAGn CAL APPLY <84-byte-packet-hex>` remains the explicit
PC-fit admission boundary. MCU validation checks packet schema/algorithm, packet
CRC, endpoint physical ID/instance, finite values, symmetric positive-definite
matrix, bias bounds, field magnitude, fit residuals/condition, sample count and
octant coverage. A rejected candidate leaves the previous state untouched. The
fit's quality statistics are PC claims checked against bounds, not an MCU refit.

A qualified APPLY replaces the trial correction, independently of the last
durable packet. `SAVE accepted=1` queues one bounded request; it never claims
durability. READ must show `saved=1 pending=0 failed=0` and the expected generation
after the LoggerTask storage service succeeds. A successful save commits the new
absolute bias/matrix. A failed save restores the last committed runtime value,
retains the new candidate for retry, and leaves `failed=1` blocking mission
acceptance. With no committed value the failure restores EMPTY, not zero-valued
valid calibration. CLEAR is also a queued tombstone and rolls back on failure.
Repeated SAVE of an already durable value is idempotent.

`SystemMagCalibration_SampleApply` requires an uncorrected physical body-b vector.
Already-calibrated samples are rejected unchanged. Correction is always
`matrix * (input_b - bias_b)`; old and new matrices/biases are never composed.
Only the correction and identity are copied at the sample boundary; candidate
and durable packet buffers do not grow the sample's stack snapshot.

The existing `PersistentStorage_ObjectWriteAtomic` writes the opposite of the
newest valid slot, syncs/closes through the storage adapter, then reads back and
checks generation, exact length, CRC and complete payload equality. The old slot
is not truncated. `magNN.0` and `magNN.1` alternate in
`0:/system/calibration/`; a third successful calibration reuses the first slot.
The older slot is bounded rollback state, not an accumulating archive. Exhausted
generation fails closed. Malformed slots with no valid survivor now report
VERIFY_FAILED rather than masquerading as an absent calibration.

After a torn write, the surviving complete slot loads. A complete write followed
by failed readback acknowledgement is explicitly uncertain: RAM reports failure
and retains the old value; a restart can select the complete new generation.
Real TF/FAT/controller power-loss guarantees remain unproven: a logical double
slot cannot prove survival of arbitrary filesystem metadata/card failures.

## SSIC v1 storage envelope

The wire fit packet stays at 84 bytes. New TF payloads are 116 bytes:

| Offset | Bytes | Meaning |
|---|---:|---|
| 0 | 4 | `SSIC` |
| 4 | 1 | envelope schema 1 |
| 5 | 1 | kind 1: magnetic ellipsoid intrinsics |
| 6 | 1 | algorithm 1: existing PC ellipsoid packet v1 |
| 7 | 1 | coordinates 1: provider body-b physical microtesla, pre-correction |
| 8 | 2 | generated descriptor ID, little endian |
| 10 | 2 | generated physical-device ID |
| 12 | 1 | endpoint instance |
| 13 | 3 | reserved, must be zero |
| 16 | 4 | `SystemDescriptor_ConfigDigestGet()` |
| 20 | 4 | driver-name hash |
| 24 | 4 | model-name hash |
| 28 | 4 | parent intrinsic content CRC: zero for this intrinsic-only kind |
| 32 | 84 | complete qualified fit packet, including quality metrics/packet CRC |

The unchanged outer SSOB v1 record supplies the monotonic generation and CRC32
over the header plus entire SSIC payload. Intrinsic content CRC is the original
packet's CRC32; status also exposes that CRC and configuration digest. Future
extrinsics must carry the parent intrinsic CRC (or stronger full-content
identity), the parent generation, AND installation configuration identity.
A changed parent/configuration means extrinsics need revalidation. No relative
rotation kind or verified-extrinsics flag is manufactured in this implementation.

The configuration digest is the existing full generation-state fingerprint and
therefore conservatively rejects unrelated configuration changes too. It covers
serialized device mounting/axis/transport state, without changing project schema
or GUI. Endpoint/physical ID, driver/model hash and digest must all match before
loading. These are generated logical identities, not hardware serial numbers.
The current device interface exposes no unique per-chip identity; replacing a
chip with an identical model at the same endpoint/configuration is undetectable.
Operator reprovisioning/recalibration is required in that case; automatic
same-model replacement detection is NOT PROVEN.

An old 84-byte TF payload lacks configuration provenance. Boot refuses it with
InvalidObject and preserves its bytes. Migration is explicit: revalidate the
current source/installation, APPLY a reviewed compatible fit (prefer a new fit),
then SAVE. The opposite slot receives SSIC v1; no legacy file is deleted. The
legacy wire packet cannot itself prove which old coordinate configuration was
used to fit it; APPLY is an explicit operator/PC admission, not automatic rebinding.

## Filesystem ownership and absence

With a selected logging protocol, LoggerTask remains the sole filesystem owner.
One service call runs before log session admission/finalization early returns.
When the logging protocol is absent, SourceGraph omits LoggerTask entirely; the
existing maintenance SerialTask calls the calibration service instead. The two
owners are compile-time exclusive. This does not enable the disabled SSLOG file
service or alter its existing permissions. Each call handles at most one endpoint
load or one pending save. The service initializes storage idempotently before
mounting; it does not depend on a log session or another task finishing startup.
It needs no mission directory. Disabled logging, no ordinary record session and a
finalized logger continue to service maintenance saves. Existing log/file service
operations keep their single-owner ordering; no new task, callback, mutex bypass,
queue or dynamic allocation was introduced. With both logging and maintenance
protocols omitted, neither owner exists; this batch does not claim persistence
service for that configuration, and no maintenance calibration can be submitted.

An absent/unmountable card yields an explicit load/storage fault and completes
the bounded startup attempt. A queued save fails explicitly and clears pending;
it does not silently wait forever or claim saved. Existing boot medium policy
still disallows hotplug recovery after an initial absent/no-filesystem probe.
No-card recovery therefore requires the existing reboot/reinitialization policy.

## Boot calibration and log reproducibility assessment

`SystemCalibration_OneFaceCorrectionApply` currently computes BOTH stationary
gyro mean and one-face accelerometer bias (`mean - direction * gravity`). Thus
the audited implementation is broader than "gyro bias only". SixFace also
exists. These paths update the existing RAM IMU correction and have no calls to
the magnetic TF persistence API. This batch does not change those algorithms or
claim a new persistent IMU installation-calibration store.

The current mission snapshot section 6 already serializes the full runtime IMU
bias/scale correction, but magnetic calibration is represented only by per-device
generation/content hashes. SSLOG/Descriptor bytes are not expanded here. After
several magnetic recalibrations rotate both current slots, the historical magnetic
coefficients cannot be reconstructed from hashes alone. Existing logs must never
be interpreted by reading the latest `0:/system/calibration/` files.

The maintenance magnetic stream reads `ProjectMagnetometerInstance_LatestSampleGet`
directly. Existing active corrections are applied only in the canonical
`SystemMagnetometer_LatestSampleGet` source-selector path; they are not folded
back into this stream's new PC ellipsoid input.

Minimal next contract: capture a complete, immutable calibration-set companion
object per mission/session admission and START, containing each SSIC record plus
its SSOB generation/CRC, actual IMU boot correction, configuration/descriptor
identity and any future extrinsic parent dependencies. Bind the companion's
content identity to that log/session. Preserve this object with the original log
and exact decoder; later TF updates must not mutate it. This needs a narrowly
versioned mission-snapshot/export contract and reader support, not a wholesale
SSLOG/FLP upgrade. It remains unimplemented; this batch does not claim historical
magnetic calibration reproducibility is complete.

## Evidence and outstanding acceptance

Task inventory, dirty-source baseline, commands, versions, exact source snapshots,
failure logs and artifact hashes are retained under
`.work/dev013_mag_tf_20261018_v1/`. Pre-fix double-correction and failed-save rollback
regressions were observed failing; final unit/fault results and generated-project
gates are indexed by the task report. No task-end cleanup is authorized or done.
Local checkout `.agents/` and `.codex/` do not exist; the accessible local Codex
`memories/` directory is empty. No local background skill/memory adds instructions.
The Host suite's previous expectation of zero calibration-service calls while
logging was disabled was changed to exactly one per iteration, retaining the
unavailable-calibration/START gate and zero log-write/snapshot expectations.
The full Host run also exposed an unchanged profile fixture that assumes no MAG
endpoint despite this validation project's explicitly selected MAG capture;
that failure is retained and the full suite is not reported as passing.

Hardware timing, TF power interruption, same-model unique identity, stack/WCET
proof and critical-contract acceptance remain NOT PROVEN where not established
by the recorded scope. Passing project text gates is not original Power of Ten
compliance, useful assertion-density proof or flight qualification.

## Follow-up resource and Host review (v2, same development day)

The dated v1 results above are retained. Follow-up evidence is in
`.work/dev013_mag_tf_20261018_v2/REPORT.md`; it supersedes the earlier Host and
cleanup status only where a later completed run is explicitly recorded.

The storage reader no longer keeps a duplicate 512-byte latest-payload buffer.
It selects the slot using generation/length/CRC metadata, rereads that one slot,
and verifies all three fields plus record validity before publishing any caller
bytes. A selected slot disappearing during this reread is VERIFY_FAILED, not an
empty store. This adds one bounded object read to both calibration and mission
snapshot reads; it does not add a write or change the atomic-write sequence.
F4 and F1 payloads contain the same implementation. The payload remains static;
no 512-byte array was moved onto a task stack.

On the same full-logging KF6 configuration, an actual ARM link with only this
task's pre-change production bytes restored used 103,476 main-SRAM bytes. V1
used 103,940; v2 uses 103,428. The 464-byte candidate/envelope cost is offset by
the 512-byte duplicate-buffer removal, for a net reduction of 48 bytes. The
existing 102,400-byte reviewed budget still fails by 1,028 bytes. The comparison
is a controlled source overlay, not reconstruction of an earlier whole checkout.
The logging-disabled configuration uses 68,880 main-SRAM bytes.

Host fixtures now distinguish a selected MAG profile from a fixture that simply
has no MAG descriptor. Synthetic qualified TRIAD compile coverage is named
explicitly; the actual JY profile's absolute-vector qualification remains zero
and its rejection coverage remains. Optional-start mocks expose the real bounded
storage-service dependencies and derive readiness from the fixture's existing
health state. No failed case was skipped and no production qualification was
enabled to make tests pass.

New fault cases cover selected-slot reread I/O failure, CRC corruption and
disappearance with unchanged caller output. The disappearance case failed before
its fix; the final isolated suite passes 47 cases. Full emitted power10 and
architecture checks, real static-analysis compilation and ARM links were rerun.
The complete emitted logging-enabled Host suite then passed in one run: 86
executables, 5,513,722 checks, zero failures, 12 positive and 17 expected-negative
compile cases, and nine component-inapplicable cases. Python regressions passed
49 tests. Earlier failed runs remain as evidence.
The power10 result explicitly retains critical-contract review NOT PROVEN.
The unmodified stack checker rejects changed frozen callback inputs/dependencies;
conditional graph estimates in the v2 report are not accepted upper bounds or
hardware high-water measurements. Neither budget nor proof fingerprints were
relaxed.

## Candidate resource/contract closeout and authorized flash (v3)

The later completed evidence is `.work/dev013_mag_tf_20261018_v3/REPORT.md`.
The one external candidate remains
`D:/stm32_project/SS_0_5_CAL_TF_CANDIDATE_20261018_01`; no TEST5/FINAL/R04
project was changed. CPU-only MAG state (1,024 bytes) and its envelope (116
bytes) now use the existing zero-initialized CCM section. No address of either
object reaches DMA; the separate 530-byte filesystem record remains in main
SRAM. Stack/queue/buffer capacities are unchanged. The final link uses 102,292
main-SRAM bytes against the unchanged 102,400 budget, and 62,904/65,536 CCM
bytes. This closes the recorded resource gate, not whole-program stack proof.

Two previously discarded internal adapter results are now checked. If its
owned load-fault or save-completion transition cannot be applied, the adapter
enters the existing bounded terminal assertion path. Card absence, torn writes,
bad CRC and readback errors still take their ordinary error paths. The two
new contract cases fail before the change and pass after it; all 49 isolated
calibration cases pass. The fresh complete emitted Host suite again passes
86 executables / 5,513,722 checks with its recorded 12 compile passes,
17 expected compile failures and nine inapplicable cases.

The exact candidate passes emitted power10, architecture, real static-analysis,
ARM link, artifact and task-stack gates. [The input review](TF_STACK_INPUT_REVIEW_20261018.md)
documents revision v21: 29 input versions, 11 dependency graphs and 159 paired
compiler tuples. Unknown sources/headers/graphs and mixed known versions remain
rejected. No prior registration, stack margin, callback exception or analysis
policy was relaxed. Expanded checker regression is **90 passed, 3 failed**:
all three depend on a missing historical F103 `.work/sf6_epoch_v3/ret6` fixture;
they are not reclassified as passing or silently skipped. This is not a full
repository-suite pass or proof for every generated configuration.

Under the subsequent explicit user flash authorization and physically
disconnected-actuator confirmation, the selected candidate was programmed via
Horco CMSIS-DAP `132765403520` on 2026-10-18 16:43 UTC. MCU family/core and
512 KiB flash matched; hardware package/wiring is not inferred from that family
ID. OpenOCD verified the ELF and reset the target. Two readbacks totaling
349,708 bytes match both `.ssdiag` segment hashes. ELF SHA-256:
`7056eac7d4de282eebf2f7b1f637ca1b30948e192eb086167121860d763c2f44`.

The separate read-only GSHC SWD API reconfirmed live firmware identity and a
running core. Its non-atomic snapshot observed `ready=0`, `mission_running=0`,
TF mounted/healthy, and `log_fault=0`; one estimator observation was UNKNOWN
because its writer changed sequence. Probe detach returned OK. The GUI was not
operated, no START or actuator command was issued, and no protection/option-byte
change was made. No serial port was opened by this task.

Physical TF power interruption, real calibration accuracy, sensor B/S revision
and same-model unique identity, historical full MAG snapshot export, complete
MSP/ISR and hardware stack/WCET evidence remain open. The successful flash and
startup observation do not close those items. All earlier failed/partial results
and reports remain retained. Cleanup stays paused.

## Offline historical F103 fixture follow-up (v4)

The three v3 extended-stack regression failures caused by the missing disposable
RET6 directory are resolved by permanent ten-input compiler fixtures. The
original RET6 scenario is reconstructed through its preserved project and a
SHA-pinned normal baseline renderer; a separate RFT6 fixture replays preserved
normal-generation output. Both use actual strict ARM GCC compilation and retain
the original source/header/unknown-dependency rejection assertions. No checker
registration, threshold, callback rule or firmware source changes were made.

The final selected cross-platform checker/provider regression run passes
**116/116**; its F103 file passes 12/12, including actual reproduction of both
RE/RF inputs. An offline recomputation of the unchanged F407 candidate's full
stack calculation also passes, and ELF/BIN/ssdiag hashes remain unchanged.
This is a later scoped result; the v3 90/3 run remains retained as recorded.

Current freshly generated F103 Flight headers remain unreviewed and explicitly
rejected. The fixture work proves historical input integrity and a real epoch
unit compile, not a complete F103 link/task/MSP/ISR stack proof or admission of
new configurations. No hardware or GUI operation occurred during v4.
Full paths, exact programmed hashes, last physical observations, all commands,
failures and retained-input inventory are indexed in
`.work/dev013_mag_tf_20261018_v4/REPORT.md` and `FLASH_EVIDENCE.md`.
