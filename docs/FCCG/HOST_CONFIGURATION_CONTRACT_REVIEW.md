# Host configuration contracts, 2026-10-06

Base: `8ce6993ef8b230784055de42711a683373f68ed5`, isolated branch
`codex/scg-legacy-gates`. This batch changes Host inputs/fixtures and reference
import adaptation only. It does not change target algorithms, math, protocol,
qualifications, queue defaults, runtime assertions or Power10 thresholds.

The emitted Host wrapper now uses the actual SourceGraph C_DEFS. Explicit fixture
variants replace matching definitions without duplicate -D arguments. Source,
real JY capability headers and forced fixture inputs are inventoried. Missing
applicable inputs fail; missing unselected payloads are explicitly NotApplicable.
An actual selected-provider compile contract runs in both configurations. The
RET selected/required origin masks stay 0x05; the existing three-interface
Alignment mock remains 0x07 and is labeled separately.

Every expected compilation rejection must contain its named existing diagnostic;
an additional undeclared compiler error fails the case. The initial batch's claim
that all landing/quaternion variants isolate their target prerequisite was too
broad: three RET negatives inherited another false prerequisite. The narrow
follow-up below corrects their fixtures and verifies predicate isolation. Noise
and required-origin variants retain their recorded checks. The fully qualified
JY magnetic fixture retains the existing
generated first-release policy rejection. The actual provider policy is unchanged.

Legacy CAL/ALIGN/lifecycle/preparation mocks provide logical sensor interfaces,
not a physical MPU epoch witness. Only their named fixture rows declare epoch
qualification disabled, with an explicit scope message. Multi-instance selector,
barometer and native-log fixtures use real generated headers/types and ordinary
four-slot bounds; they do not validate the production compact one-slot bound.
The required-GNSS mock declares enabled position/origin collection and the real
100-sample window; the actual GNSS-free RET row retains origin pruning. These
Host flags do not enter target firmware. The separate existing epoch provider
contract test keeps qualification enabled and checks twelve normal/fault cases.
The startup fixture explicitly supplies its Mock Power implementation. The
qualified baro/IMU landing mock declares its qualified window; the actual
selected provider's unqualified compile rejection remains independently tested.
The legacy mission-action row now references its real FlightLogic source/include
owner, so the selected service is tested instead of being mislabeled unselected.

Logger fixtures retain no-data-zero expectations and add invalid retained STATS
context checks for the accepted health-publication contract. Selected records
exercise fairness at actual queue capacities: 16 iterations, maximum run 3,
at least four alternate records. Unselected ESKF and unsupported diagnostic
positives are explicitly NotApplicable and their ordinary rejection is checked.
Codec roundtrips and all selected positive expectations remain in place.

Storage uses actual graph definitions and the real Storage Inc path. Its logger
writer injects logical records and declares that physical epoch is not exercised.
Unsupported profile records must reject configuration; supported records retain
the original positive checks. DMA/timeout, boot-medium, bounded no-hotplug,
overflow, startup-stall/jitter, finalization and exact-decoder checks are unchanged.
The existing SF6 minimal stress is separate from the normal all-stream stress.
Both the wrapper and real storage runner reject zero/multiple authoritative
diskio sources. No diskio cardinality check is skipped to obtain a pass.

The importer recognizes its existing target-profile architecture EIDE patterns
and preserves Host applicability while reconstructing progress output. The
Power10 progress insertion accepts its existing recommendation block without
altering any rule, coverage, threshold or NOT PROVEN output.

Recorded counterexamples include the old RET missing JY header, the old wrapper
accepting a GNSS rejection with an unrelated #error, and the new wrapper rejecting
that extra error. Later full runs exposed incorrect multi-instance bounds,
missing epoch interfaces, missing Storage Inc, unsupported stream enablement and
missing required-GNSS origin storage. All failures remain evidence. A deliberately
misspelled selected case was rejected by the inventory and is also recorded.
The trapped native-log Host child was stopped only after its exact owned path
was verified; no other process or hardware was touched. CIM process inspection
was denied and was not bypassed.

Final fresh projects: `.work/host_f407_verified/Flight_Controller` and
`.work/host_ret_verified/Flight_Controller`. F407 uses the official Q2 model,
KF6 and unchanged parameters. RET reuses the verified official CubeMX snapshot
`cfb83b7fbc30169589aa6a2fc40c44dcbc2e3031f8940b210cf59c024669edd3`;
921 files/35,138,248 bytes matched. No new CubeMX invocation was needed for this
Host-only batch. RET is MPU6050 + BMP280 + NRF24, SF6 minimal, no GNSS, logging on,
maintenance off; this is not an E28/four-module acceptance result.

Final complete emitted wrappers both exited 0, including all four storage stages:

| Configuration | Executables | Checks | Compile positives | Named rejections | Wrapper NA counter events |
| --- | ---: | ---: | ---: | ---: | ---: |
| F407 KF6 | 80 | 4,446,465 | 8 | 18 | 8 |
| RET6 SF6 minimal NRF | 71 | 4,402,031 | 3 | 16 | 29 |

These are the historical complete executions for the initial Host batch, not
full-suite results for the follow-up. The NA column counts wrapper counter events,
including repeated runtime messages; it excludes storage child messages. F407's
entire log contains 71 NA output events: wrapper 8 (7 distinct labels), storage
63 (9 labels, each repeated seven times), total 16 distinct labels. RET's entire
log contains 29 events (27 labels): wrapper 29, storage 0. F407's ESKF-positive
label appears twice; RET's ESKF-positive and telemetry-diagnostic-positive labels
each appear twice. NA output events are neither executable counts nor unique
coverage cases. Exact lines, labels, frequencies and original log hashes are
retained in the read-only supplement.

All seven fresh target gates exited 0 in each configuration: actual ARM
compilation/link, real -fanalyzer compilation, emitted architecture, Power10,
artifact, task-stack and memory. The existing epoch contract and importer
regressions passed (2 pytest tests); the twelve epoch cases include expected
terminal Host process exits, not MCU recovery. Textual input equivalence confirms
all compiled C sources, production headers and SourceGraph stayed unchanged.

| Configuration | Linked Flash | Main SRAM | CCM | Main SRAM spare |
| --- | ---: | ---: | ---: | ---: |
| F407 | 331008 | 112756 | 46760 | 18316 / 131072 (13.974%) |
| RET6 | 209480 | 62224 | 0 | 3312 / 65536 (5.054%) |

Both hard link limits pass; the 20% spare target does not. Task stack storage is
already in these linked RAM totals and is not added again. All reported task budgets
pass; RET Logger estimate is 2736/3072 (336-byte margin), Flight 3480/4096,
Estimator 1440/4096. These remain scoped estimates, not whole-system stack proofs.
Storage overload audits explicitly allow their existing accounted queue drops;
they do not establish loss-free overload, STM32 timing or WCET. The legacy writer
print `slot_bytes=200` describes its common record envelope; actual RET queue slots
are 168/96, also printed by the actual SF6 fixture and confirmed by linked symbols.
The existing F407 auto layout emits a warning that main SRAM exceeds its
historical 100 KiB regression budget by 10356 bytes; physical limits pass under
the existing auto-layout policy. No budget or exception was enlarged here.

The actual entire wrapper includes storage, with no -Only/prefix. Commands,
tool versions, all case names/NotApplicable reasons, full logs, configuration,
auditable dirty source hashes and fresh ELF/map/BIN hashes are retained in
`.work/evidence/host_final_inventory.json` and the per-project evidence directories.
The original full-run receipts mislabeled inherited process cwd as project root;
the inventory explicitly corrects it to this isolated worktree. Inputs are
resolved through the actual emitted wrapper PSScriptRoot.

Critical-contract review and whole main/MSP/ISR stack proof remain NOT PROVEN.
20% main SRAM spare is unmet in both profiles. Hardware, recovery timing and
flight qualification are NOT RUN. NotApplicable is not positive coverage of an
unselected provider, physical epoch, ESKF or compact instance limit. No daily,
GSHC, FLP or GUI edits, merge, push or hardware action were performed.

## Narrow review follow-up, 2026-10-07

Base: `2eff7691618ad59c0f2562b67a24eb3391fb892a`. Only the owning Host wrapper and
this report change. Three shared fixture prerequisite lists explicitly provide
legal positive inputs for hardware quaternion 6/9-axis preflight and baro/IMU
stillness. Each new generic positive and its existing negative differ in exactly
one qualification definition (1U versus 0U). The existing named rejection
diagnostics remain mandatory. No target capability validation or qualification
was changed. This corrects RET test isolation; the corresponding F407 negatives
were already isolated under their selected configuration.

Fresh emitted wrappers in `host_f407_qualifier` and `host_ret_qualifier` each passed
the selected four compile positives (three pairs plus actual selected-provider)
and three named rejections. These are selected compile-contract runs, with the
storage child excluded; they are not full Host executions. Separate isolated
copies of real RET User headers remove only each named assertion's target
conjunct. All three old RET negatives still reject with the named diagnostic,
demonstrating masking. All three corrected negatives instead compile and cause
the expected-rejection test to fail with `Expected host compile failure did not
occur`. Mutation headers are test artifacts only. No product gate was weakened.

Read-only comparison uses retained `host_*_complete` versus `host_*_verified`
projects, not the new qualifier projects. The baseline is 8ce6993 plus the
auditable dirty Host candidate, not a clean-8ce whole-repository snapshot.
F407 has 388 distinct actual C dependency paths; RET has 333. All compared bytes
match, including additional Makefiles, target.mk, startup assembly and linker
scripts. RET's actual dependency `Devices/SensorBus/Src/bmi088_sync_image.inc` is
included as bytes in this supplement. Root prefixes alone are normalized when
comparing recorded compiler argv; flags, definitions, include order, object lists
and linker choices are retained. F407's 155 C/one ASM commands and auto-layout
invocation match in each of Release and analyzer logs. RET's 143 C/one ASM/one
direct-link commands match in each scope. F407's retained auto-layout decisions
also record four actual candidate link argv per scope, including selected index
2; all match. The final repetition uses the same command by retained wrapper
code, but its subprocess argv was not independently logged.

This does not close every compiler input: -MMD omits system/toolchain headers;
startup assembly has no recorded preprocessor dependency graph; historical
external archive/specs/toolchain bytes were not saved as baseline pairs. Those
identities remain NOT PROVEN. Existing newlib `_read`, `_write`, `_close`, `_lseek`
stub warnings remain recorded; seven exit-zero gates do not establish a
warning-free whole-firmware build or original Power of Ten compliance.

For this follow-up, full Host, ARM/link, analyzer, Power10, architecture, artifact,
stack and memory gates are NOT RUN again because production firmware inputs are
unchanged and the authorized scope is narrow Host fixtures plus read-only
evidence. Prior recorded passes retain their original revision and scope.
Whole-system stack, critical-contract review and hardware limitations above
remain unchanged. No merge or push is authorized by this report.
