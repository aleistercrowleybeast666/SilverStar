# Ground dependency closure rereview, 2026-10-09

This isolated follow-up closes the remaining dependency P2 against
`b05b3705638660cf79dde47bc3fc96b45819f8ec`. The other five repairs, GUI,
C071 experiment and original FINAL project are unchanged. No push or hardware
operation occurred. This document supersedes only the dependency claims in
`GROUND_USB_REVIEW_REPAIR_20261009.md`; that commit and its evidence remain intact.

The original reviewer reproducer was rerun before editing. An imported header
used `#pragma GCC system_header` followed by `%:include` of a tree-external
header. Import and the compiled `-MMD` dependency gate both accepted it. Changing
the outside constant from 17 to 29 changed the Host result and actual Cortex-M3
instructions from `movs r3,#17` to `movs r3,#29`. Saved evidence is under
`usb-validation/rereview-before-dependency/`; the full reviewer recipe is saved
alongside it as `usb-validation/rereview-before-dependency.py`.

Complete imports now explicitly reject digraph preprocessing tokens and C11
trigraphs. Rejection occurs before comment interpretation and after ordinary
backslash-newline splicing, covering alternate directive markers and escaped
directive names. The conservative profile also rejects those spellings in
comments and string literals; it does not claim general C preprocessor support.
Existing literal include, linker, alias and frozen-file checks remain in force.

The owning Ground Make renderer emits `-MD -MP` for C and preprocessed assembly,
including analyzer compilation. The artifact gate reads every actual C/ASM
dependency list, resolves real paths, and distinguishes copied project inputs
from the selected compiler's default headers. Default header directories are
queried from that exact executable with ambient include/compiler search overrides
removed, must exist inside its resolved installation, and are canonicalized.
Project aliases escaping the copied tree are rejected even when their destination
is an approved toolchain header. Compiler defaults are trusted toolchain inputs;
this does not prove the integrity of the compiler installation itself.

The saved after-fix ARM probe deliberately compiles the original unsafe input
with `-MD` independently of importer rejection. Both 17 and 29 compile, their
objects differ, the actual `.d` files include the system-marked external header,
and the artifact gate rejects both. Objects, dependency lists, commands and
disassembly are in `usb-validation/dependency-probe-after/`. Normal frozen local
system-marked headers and genuine compiler stdint dependencies pass.

Fresh F103 USB, F103 UART and F407 USB targets in `usb-validation/dep9/` execute
`make -B -j2 all architecture-check host-tests artifact-check power10-check
static-analysis`. Every gate exits zero. Actual source/vector/clock identities,
bounded Host normal/fault cases and strict first-party ARM analyzer compilation
remain covered. Boundary tests pass 33 cases, including actual ARM negatives.
The declared backend selection passes 124 tests with one known unrelated
BMI088/SD duplicate-source case deselected. The three separately owned GUI test
files are excluded from this backend selection, not claimed as passing.

Earlier sandbox directory errors and six backend failures with a long temporary
root are preserved. Short Windows paths were used for the successful rerun;
snapshot and path-length checks were not weakened. ELF sizes and RAM use are
unchanged from b05. Complete call graph, stack/ISR bounds, critical-contract
manual acceptance, MCU timing and physical USB/radio behavior remain NOT PROVEN.
Machine-readable hashes, exact recipes and artifact evidence are in
`ground-usb-evidence/dependency-rereview-summary.json`.
