# Ground GAS dependency closure repair, 2026-10-09

This follow-up repairs the remaining dependency P2 in
`92d6a64c52361f172ff5cb8daff67a279f91096d`. GCC `-MD` records preprocessor
inputs, but does not record files opened later by GAS `.include` or `.incbin`.
A GAS macro can construct these directives; C adjacent string literals can
construct equivalent inline assembly. Both bypass a literal import scan.
The pinned old gate accepted real ARM objects containing external bytes that
changed from 17 to 29. Import success alone did not establish dependency closure.

The owning Ground Make renderer and plugin gate now collect and validate both
compiler stages. Every C source is compiled to its exact per-object assembly
file with its original warning policy, stack report and, when selected,
`-fanalyzer`. The first GCC `.file` label is qualified to the declared source
path before assembly: GAS also lists this label in its dependency output even
though it does not open it. This avoids an ambiguous basename-only dependency
without discarding any dependency or permitting missing files. GAS then emits
a separate `.gas.d`. Preprocessed assembly retains `-save-temps=obj` and emits
both `.d` and `.gas.d`.

For each declared object the gate requires matching manifest targets, the
original CPP source, the exact saved assembler input, existing allowed inputs,
and an object no older than its dependencies. Object-path collisions and
aliased evidence paths fail. Assembly-label preparation rejects absolute paths
and parent traversal before writing and is confined to `build/` outputs.
Only that object's saved assembly may be a build
output dependency; there is no general temporary-directory exception. The
existing narrowly discovered compiler-default header roots remain trusted
toolchain inputs. Ambient compiler/include search overrides are unexported.

The gate runs after each compilation and again before linking, including on
an otherwise up-to-date ELF and in `build/analysis`. Make includes a safely
rendered, validated union of CPP and GAS prerequisites, not raw manifests.
Assembler asset changes therefore rebuild the object. A rejected newly
compiled object is removed by Make's `.DELETE_ON_ERROR`, and another invocation
retries rather than reusing it. Unsupported Make filename metacharacters are
rejected. Static import checks still do not evaluate the entire assembler
language; successful build acceptance requires this actual compiled closure.

No firmware runtime source, imported HAL/CMSIS/startup/linker/USB configuration,
Flight generation default, GUI file, C071 experiment, Power10 threshold or
exception was changed. Normal project regeneration still preserves user-owned
payloads. Validation used three new projects and reused the existing immutable
CubeMX snapshots without overwriting prior candidates or copying entire vendor
packages. No serial/probe, hardware, EDA or push operation occurred.

## Executed evidence

The final backend selection passed **144 tests, 1 deselected, 0 skipped**. The
deselection remains the existing
`test_one_bmi088_plugin_resolves_mixed_interfaces_without_duplicate_sources`.
The separately owned `test_ground_board_recovery.py`,
`test_ground_radio_editor.py` and `test_ground_activity_configuration.py` were
excluded, not counted as passing. This is not a full monorepo test claim.

New actual ARM tests cover C inline assembly and GAS macros for both directives,
nested local includes/incbin, external nested bytes, ordinary and analysis
outputs, missing/mismatched evidence, wrong saved inputs, unexpected build/Temp
inputs, stale objects, colliding objects, asset-driven incremental rebuild,
missing evidence on an existing ELF, and failure before linking. Eight retained
ARM objects provide a direct comparison: the pinned old gate accepts all eight,
the repaired gate rejects all eight, and each external 17/29 pair changes its
object. Compiler commands and raw manifests are retained.

Each fresh target executed the complete emitted invocation, with explicit
Python/Host compiler paths:

```text
mingw32-make -B -j2 all architecture-check host-tests artifact-check power10-check static-analysis
```

All three invocations exited zero; these are complete runs, not stitched passes.
Actual ARM assembly/linking, strict first-party analyzer compilation, Host
normal/fault regressions, source ownership, linked strong IRQ vectors, effective
clock/MCU macros, paired dependencies and the emitted Power10 gate are covered.

| Fresh target | C + ASM sources | Text / data / BSS bytes | Full gate exit |
|---|---:|---:|---:|
| F103 USB | 50 + 1 | 36440 / 380 / 12000 | 0 |
| F103 UART | 39 + 1 | 27536 / 12 / 7576 | 0 |
| F407 USB | 60 + 1 | 36788 / 248 / 14800 | 0 |

All three fresh release `.bin` hashes equal the recorded `92d6a64` binaries;
the evidence records both the new artifacts and this explicit comparison.

The first exploratory test run had 45 passes and four failures: one real
basename-label rejection and three Windows fixture path-replacement mistakes.
Those logs are preserved. After repair, 49 targeted tests passed; the final
144-test selection includes the four subsequent additional tests. The first
complete 142-test/three-target run also passed; after adding the final write-path
guard, all three targets and the complete backend selection were rerun using
another fresh output set. Both runs remain saved. One shell
flag experiment failed PowerShell parsing before any compilation and was
rerun correctly. No failed run is reported as a pass.

The auditable source snapshot, exact commands, tool versions, configurations,
complete logs, dependency/assembler/object hashes, linked artifact hashes and
partial stack observations are indexed in
[`ground-usb-evidence/gas-dependency-repair-summary.json`](ground-usb-evidence/gas-dependency-repair-summary.json).
Small local evidence is in
`C:/Users/chdxm/Documents/Codex/2026-10-09/task-2/gas-evidence2`;
eight real ARM probe cases are in the adjacent `gas-proof2` directory.
Fresh build outputs are in `C:/Users/chdxm/AppData/Local/Temp/ssgas-run2`.

## Acceptance limits

The compiler installation is trusted. Dependency manifests and timestamps are
build evidence, not tamper-proof receipts against a concurrently hostile
filesystem. The conservative filename/assembler-label profile may reject
otherwise valid unusual GNU build inputs rather than silently broadening its
acceptance contract.

Power10 still explicitly reports critical-contract manual acceptance NOT
PROVEN. Complete call graph, task/main/MSP/ISR stack bounds, MCU WCET, physical
USB reset/disconnect/reconnect, radio behavior and hardware/flight qualification
remain NOT PROVEN. Linked spare RAM and partial `.su` frame sums are not safe
stack margins. Software passes do not establish original Power of Ten
compliance, certification or hardware acceptance. This follow-up is ready for
the separately planned integration review; it is not that independent review.
