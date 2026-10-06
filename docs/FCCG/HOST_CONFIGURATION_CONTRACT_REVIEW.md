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
an additional undeclared compiler error fails the case. Noise, landing,
quaternion and required-origin variants explicitly provide their other positive
prerequisites. The fully qualified JY magnetic fixture retains the existing
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

| Configuration | Executables | Checks | Compile positives | Named rejections | NotApplicable |
| --- | ---: | ---: | ---: | ---: | ---: |
| F407 KF6 | 80 | 4,446,465 | 8 | 18 | 8 |
| RET6 SF6 minimal NRF | 71 | 4,402,031 | 3 | 16 | 29 |

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
