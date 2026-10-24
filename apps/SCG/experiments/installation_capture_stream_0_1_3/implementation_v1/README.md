# Installation capture C candidate — 2026-10-19

This is an isolated, default-OFF implementation for review. It is not registered
with SCG generation and is not a production firmware or a flashable image.
APPLY, SAVE and UPLOAD remain unavailable. No source rate/configuration changes,
driver replacement, TF writes or new protocol version are introduced.

## Implemented boundary

`installation_capture.[ch]` implements the fixed native-stride selector, two
paired sample slots, source sequence/time/epoch checks, session/request identity,
face progress, explicit result enums, resource ownership and cancellation. A
reentrant call returns Busy without spinning. ARM uses a short PRIMASK
save/restore only to acquire the guard; it does not assume CCM supports exclusive
access instructions. Producer calls must process Busy: retry the exact sample
or fail the window. Ignoring Busy cannot preserve native continuity.

`capture_info.c` serializes the complete frozen typed snapshot as canonical JSON:
sensor endpoint identity, coordinate mapping, units, parent coefficients and
generations, time/epoch/native provenance, capture policy and binding. SHA256
covers the exact canonical bytes. INFO regenerates the bounded document for each
48-byte page without retaining a full JSON buffer. This trades CPU time for
memory; STM32 execution time and scheduling acceptance are still NOT PROVEN.

The sample path copies every selected source record, emits the existing sample
format 1 with CRC and the existing INSTALL wire events, and uses a consumer
Peek/Commit lease. Successful Commit means complete-line TX enqueue acceptance,
not confirmed physical delivery. Cancel stops publication, waits for explicit
producer stop and an outstanding consumer lease, and only then allows release.
Source/face/client deadlines and stale/replayed requests are checked in C.
The ten resource entrants are implemented in the C gate; production entrypoints
have not been wired to it.

The real GSHC adapter is
[`InstallationOwnerProvider`](../../../../GSHC/transport/installation_owner.py),
with the existing `MaintenanceOwner` worker in
[`file_transfer.py`](../../../../GSHC/ui/file_transfer.py). It is opt-in and
default OFF. The same QThread and `FileServiceSerialTransport` perform all I/O;
no second reader or serial owner is created. Session work excludes existing
maintenance jobs and idle status exchanges. Replies are correlated by operation,
SID and RID; late replies are quarantined, incomplete cleanup poisons reuse.
The widget/layout AST and the other 18 protected GUI files remain unchanged.

## Memory and integration limits

| Static CCM reservation | Bytes |
|---|---:|
| Two paired slots | 632 |
| Two pending source samples | 176 |
| Complete frozen snapshot/binding | 640 |
| Transaction state | 256 |
| SHA workspace | 128 |
| INFO digest | 32 |
| Guard/resource/control | 96 |
| Total | **1960** |

The isolated ARM link asserts exactly 1960 B CCM and zero `.data`/`.bss` bytes.
Using the preserved candidate's 2632 B CCM spare would leave 672 B. This is a
static reservation result, not a stack, task lifecycle or whole-firmware fit
claim. Caller-owned INFO output (48 B), event scratch (at least 439 B), snapshot
assembly and actual call frames must be accounted for at their owning callsites.
The conservative isolated chains are Configure 520 B, InfoRead 504 B,
SourcePush 120 B, EventPeek 60 B and Cancel 40 B, before caller/context/interrupt
cost. They must not be added blindly to an old task maximum.

Current production interfaces do not yet supply the required capture boundary:

- IMU `NextSampleGet` belongs to the INS consumer; installation must not steal
  its FIFO. MAG currently exposes latest samples, not every native sample with
  proven epoch/gap/time uncertainty. A coherent producer tap is still needed.
- JY901B measurement time is unknown/receive-decode proxy. Profiles 2/3 force
  unknown epoch/continuity/uncertainty and cannot qualify synchronized fitting.
  Profiles 0/1 are explicitly synthetic offline fixtures, not hardware evidence.
- Public active MAG coefficient snapshots are unavailable. Missing parent
  coefficients use generation 0/UNKNOWN and JSON null; identity defaults are
  never represented as recorded calibration. GSHC refuses that fitting binding.
- Immutable profile labels are candidate examples. Generated source identity,
  a coherent full snapshot, the typed ASCII command dispatcher, every target
  resource entrant and producer/consumer lifecycle still require owning-payload
  integration and a separate fresh generated project.
- The isolated assertion trap and `arm_entry.c` are link harnesses only. Production
  integration must use the established terminal failure facility. No global
  task/MSP/ISR stack, IRQ nesting, hardware high-water mark, 500 ms cancellation,
  WCET or critical-contract acceptance has been established.

These gaps stop production enablement and flashing. They are not resolved by
the remaining 672 B, a host test pass or an isolated ELF.

## Reproduce and evidence

From the repository root, use an unused run identifier:

```powershell
python -B apps/SCG/experiments/installation_capture_stream_0_1_3/implementation_v1/run_checks.py r6
```

The driver refuses existing directories, snapshots exact dirty sources, compiles
the actual C DLL, runs strict ARM compilation and real `-fanalyzer` compilation,
links the isolated ARM ELF, derives module/library chains from that ELF and `.su`
files, and runs the C/real-owner/installation/MAG/maintenance/GUI regressions.
The fake serial peer invokes the compiled C implementation; Python is not a
substitute capture state machine. It never opens hardware. Dependencies and
third-party changes are recorded in `third_party/LOCAL_CHANGES.md` and the task
evidence; assertions and warnings stay enabled, and the linked path has no
allocator, printf, snprintf or strtod symbol.

Evidence root: `.work/dev013_installation_c_impl_20261019_v1/`. Earlier r1/r2
were exploratory. r3 preserves the analyzer local-initialization diagnostic;
r4 preserves the upstream unchecked-allocation diagnostic. Failed/partial runs
remain failed/partial, and are not combined into a suite pass. The current
accepted run and any remaining blocker are recorded in `closeout.json`.

The six preserved external candidate artifacts are hash checked before/after
the software run. No repository/SDK/toolchain copy, cleanup, push or main change
was performed. This task's evidence and generated outputs have explicit owner
`installation_c_impl_20261019_v1`; no deletion is authorized.

The separate bounded observation of the existing safe firmware is documented in
[`JY901B_MAG_OBSERVATION_20261019.md`](../../../../../docs/internal/JY901B_MAG_OBSERVATION_20261019.md).
It found no effective 0x54 frames; it did not flash this candidate.
