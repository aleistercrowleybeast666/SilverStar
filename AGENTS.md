# SilverStar workspace guidance

This repository is the unified SilverStar monorepo. For an application-local task, change the affected application. For an explicitly cross-component contract, version, or integration task, changes across `apps/FCCG`, `apps/GSHC` and `apps/FLP` are permitted. `contracts/` owns shared machine-readable contracts.

Use the repository naming style: noun, underscore, capitalized verb phrase (for example `Lora_TryStartNextTx`). Public operations returning success or failure reasons should use an `UpperCamelCaseResult` enum. New C header guards use `__` plus the uppercase filename with periods replaced by underscores. Keep file-scope state `static` where possible; expose it through an interface. Check whole-file implications of every edit.

FCCG: preserve declarative plugins, source-graph ownership, generated-file boundaries, workspace path safety, storage integrity, interrupt/DMA safety and explicit hardware verification. Imported CubeMX files are not FCCG source. Normal generation must not overwrite user-owned project payloads. Read [FCCG architecture](docs/FCCG/ARCHITECTURE.md) and [runtime safety](docs/FCCG/platform/details/RUNTIME_SAFETY.md) for detailed constraints.

GSHC: AIR M0 and command/controller readiness are authoritative. An ACK does not imply READY. Keep serial/protocol processing off the GUI thread and maintain bounded queues and diagnostics. Read [AIR protocol](docs/GSHC/AIR_PROTOCOL.md) and [GSHC architecture](docs/GSHC/UPPER_COMPUTER_ARCHITECTURE.md).

FLP: source logs and recorded datasets are immutable. Production opening requires the exact `.ssdecoder` and Descriptor through `LogOpenCoordinator`; do not add fallback decoding or treat offline defaults as recorded. Keep trusted container plugins separate from declarative decoder data. Read [FLP architecture](docs/FLP/Architecture.md) and [decoder contract](docs/FLP/Decoder_Profile_Package.md).

`.work/` is disposable test, build, generated-project and analysis space. Cleanup may remove only verified generated files; preserve user inputs, logs, decoder packages, archives, source fixtures and formal evidence. Generated firmware normally belongs to the user-selected external project. Do not treat a synthetic fixture as hardware validation.

## Generated firmware: Power of Ten and evidence

Firmware safety changes belong in the owning declarative plugin payload or generator template. Verify their fresh generated output too. Never patch only a disposable generated copy and present that as a repository fix. Normal regeneration must continue to preserve user-owned source; validation uses a separate, clearly versioned project, not the user's final candidate unless explicitly requested.

Use [Holzmann's original ten rules](https://spinroot.com/gerard/pdf/P10.pdf) as the review baseline:

| Rule | Review requirement |
|---|---|
| 1 | Simple control flow; no goto, setjmp/longjmp, direct or indirect recursion. |
| 2 | Statically bounded iterations; intentional permanent scheduler/fault loops need separate proof. |
| 3 | No dynamic allocation after initialization. |
| 4 | Functions fit about 60 standard-format lines. |
| 5 | Average at least two meaningful, side-effect-free assertions per function, with explicit failure handling. |
| 6 | Keep data at the smallest practical scope. |
| 7 | Validate parameters and check non-void results; justify explicitly discarded results. |
| 8 | Simple preprocessing; avoid token pasting, variadic/recursive macros; justify conditional compilation. |
| 9 | Restrict pointer indirection; no concealed dereferences or function pointers. |
| 10 | Strict warnings without warnings and regular static analysis. |

The existing checker is a project gate, not a complete proof of these rules. Preserve its original thresholds, source coverage and failure expectations. In particular, its Rule 5 requirement of two assertions in functions over 20 code lines differs from the original average across functions; typed-object non-null/alignment counting does not prove useful assertion density. Its direct-recursion/text-pattern checks do not establish an acyclic whole-program call graph, finite `for` bounds, minimum data scope, every checked return, or all header/macro/pointer semantics. Review those separately and record unresolved items as FAIL or NOT PROVEN, never PASS.

Known project policies also differ from strict original compliance: the checker forbids allocation even during initialization, excludes third-party middleware, permits its named permanent task/fault loops, selected protocol/estimator conditionals and the exact FreeRTOS idle-hook double-pointer outputs. Do not enlarge these exceptions without explicit authorization. Maintain upstream licenses and version provenance. Inventory linked third-party code (including HAL, RTOS, libraries and callbacks), document each controlled exception and its consequences for recursion, stack and timing analysis; do not erase its violations or claim whole-firmware original compliance from a first-party gate alone. Host fault-injection harnesses may intercept the terminal trap using setjmp/longjmp; this test-only mechanism must never enter target firmware or be reported as MCU recovery.

Assertions must enforce a real input, stored-state, sequence, capacity, numerical or lifecycle contract at the relevant boundary, before unsafe access or partial publication. Invalid external input should retain the intended ordinary error path. Corrupt internal state must enter the established bounded safe failure/fail-stop path and must not leave stale READY or publish a successful result. Respect task/ISR ownership and critical sections; an assertion based on an incoherent concurrent snapshot is invalid. Do not add constant/tautological assertions, repeat the same check for counts, split or reformat functions merely to evade a threshold, broaden allowlists, hide files, suppress diagnostics, weaken checks, or change tests to turn a genuine failure green. If two meaningful assertions cannot be justified, retain and report the gap instead of manufacturing compliance.

Each safety batch must demonstrate the pre-fix failure and post-fix normal and fault-triggering cases with unchanged safety expectations. Run the unmodified generated `power10-check`, relevant Host regressions, real static-analysis compilation (not syntax-only masquerading as analyzer execution), and actual ARM compilation/linking. Check source-graph/architecture and linked artifact/stack reports when affected. Save commands, tool versions, exact source commit or auditable dirty snapshot, configuration, exit codes, complete failure/skip details, logs and artifact hashes. Use fresh outputs; never attribute an old binary or a result from another revision to a fix. Do not stitch selected passes into an unexecuted full-suite pass.

Any failed gate blocks a claim of compliance. Passing tools establish only their recorded scope. A stack proof must cover actual task paths, libraries, indirect calls, dynamic frames, main/MSP and relevant ISR nesting; unresolved bounds remain unproven. Linked RAM/CCM spare bytes, host execution time and an assertion count do not establish safe stack margin, STM32 WCET, navigation accuracy or hardware/flight qualification. Keep existing fault behavior and record unavailable hardware evidence explicitly. Do not perform hardware actions, publish or push without the user's authorization.
