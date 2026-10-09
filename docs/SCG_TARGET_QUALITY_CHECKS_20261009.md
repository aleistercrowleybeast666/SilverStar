# SCG Flight / Ground quality checks — 2026-10-09

Base: `3c8cf57ba8d3ec38b1063b69bab555c5b09b948c`. Changes are restricted to
SCG GUI, check orchestration and result provenance. The exact tested dirty
snapshot and complete commands/logs are in
`docs/evidence/scg_target_quality_checks_20261009`. The three pre-existing
untracked `work_*_20261006` inventory files were left untouched. No `.agents`
directory or application-local `AGENTS.md` was present; repository guidance,
FCCG architecture and runtime safety were read.

## Actual coverage before this change

Color is presentation, not coverage. The existing call chain was:
`BuildPage.actionRequested` → `MainWindow._Build_Request` →
`FccgService.Build_Run(... Flight_Controller ..., ensure_buildable=False)` →
`BuildRunner.Run` → the generated Makefile target. All five shared quality
buttons and the displayed persisted quality records used **Flight_Controller**.
Ground selection in generation did not change that path.

| Area | Actual scope before this change |
| --- | --- |
| Toolchain detection | Shared executable discovery/version checks for Arm GCC, make and host GCC; no target firmware acceptance. |
| Configuration resources | Current model configuration/resource resolution and Ground readiness checks; generation checks the relevant target requirements. This is separate from executing generated-code gates. |
| Target Compile buttons | Independent Flight/Ground real make builds and link/artifact audits, with actual work-unit progress. |
| Target ELF shortcut | Checks file existence; explicitly says integrity is NOT CHECKED. |
| Five shared quality buttons | Flight host tests, architecture, Power of Ten, static analysis and artifact gates only. |
| Ground Makefile | Already contains all five entries; the shared quality GUI did not invoke them. |

Ground's existing `Tools/check_ground.py` architecture gate checks declared
source/assembly graph against Make, source/path classification, ownership and
startup separation, selected radio and some resource contracts. Its host gate
executes generated bridge/selected PC-transport harnesses with mocks. Its
artifact gate requires ARM ELF identity, expected symbols, declared memory
regions, linked objects/map and BIN reproduction. Ground static analysis invokes
`ANALYZE=1` with `-fanalyzer` and existing warning policy. Ground Power of Ten
uses the existing emitted `-TargetKind Ground` entry. These coverages and their
limitations remain defined by the existing gates; this UI does not extend them.

## Implemented behavior

The quality area has two sections, Flight and Ground, each with an independent
participation checkbox, progress and five result labels. The shared check
buttons run the selected generated targets sequentially. Default selection is
Flight only. Check selection does not mutate project configuration or generation
selection, implicitly save a project or generate either target.

Missing/malformed generated input or a missing Makefile entry is unavailable.
Unselected targets show not checked this run, even if historical records exist.
Flight descriptor parsing and Ground metadata/graph identity and in-root paths
are checked before execution. Ground uses its own build options with shared
tool-location fallback; explicit Ground tool paths take precedence.

Each target retains results under its own `.fccg/quality-results.json`, with
input SHA256, actual command and full failure/output detail. Reading/invalidation
does not rewrite historical records. Unbound legacy records or records whose
input identity changed show stale, rather than inherited PASS. Fingerprints
include the in-root input tree, ownership/preparation inputs, command, selected
executable bytes, and ELF/BIN/HEX/MAP products for artifact checks. Known build
outputs/caches and the two result/report files are excluded from source input
identity. Links/junction redirects and unreadable trees are rejected. Inputs are
compared before/after execution; concurrent changes block a current result.

This fingerprint is recorded-input provenance, not a proof of all compiler
dependencies, DLL/runtime dependencies or external/system include closure.
Results refer to generated files, as the UI explicitly says. UI draft changes
must be generated before their firmware can be checked. Refresh/re-entry
revalidates recorded identities; this is not a filesystem watch service.

Progress comes from gate events and the existing native make child-completion
tracker. Ground analysis/artifact operations reserve a final unit for successful
gate completion. Unknown phases remain indeterminate. Failure/cancellation and
evidence-save failure do not reach 100%. A failed target does not prevent the
other selected target from running, and it prevents batch success. Power of Ten
automatic result and critical-contract NOT_PROVEN/FAIL remain separate per
target, including historical review detail. No gate threshold, allowlist,
generator template, plugin payload or existing target Compile path is changed.

## Validation and limits

The corrected baseline probe invokes the exact `3c8cf57` request handler on an
isolated window: Ground-only selection still called Flight, producing the
expected assertion `('flight',) != ('ground',)`. The first probe had an
incompatible test-double signature; both logs are retained and only the
corrected probe is root-cause evidence.

The final targeted suite covers Flight only, Ground only, both, neither,
one-side failures, cancellation, missing/corrupt input, source/tool/ownership
and artifact invalidation, historical record preservation, evidence-save
failure, separate NOT_PROVEN/critical FAIL, asynchronous terminal status,
native make progress, and prior GUI/compile-progress contracts. Complete
intermediate failures and reruns are retained, including the 3-failure/65-pass
presentation regression. The final frozen-source invocation passed **71 tests**,
exit 0, in 145.06 seconds, with no failures/skips and the existing `cache_dir`
warning. See `commands.json`, `approved.log` and `source_manifest_approved.json`.

A fresh isolated generated Ground target's architecture gate ran through native
make and reported PASS within its scope and critical-contract/stack/timing
NOT PROVEN. A tiny native host scheduler fixture used real GCC `-fanalyzer`
compilation/linking to verify successful and failed gate progress. Its fake
`.elf` suffix is **not ARM firmware evidence**. Qt offscreen screenshots were
visually inspected for the two sections and localized scope text; displayed
sample statuses in those screenshots are presentation fixtures.

No production Ground host/Power-of-Ten/static-analysis/artifact full-gate batch,
actual ARM build/link or hardware run was performed for this GUI change. No
synthetic result is represented as MCU or hardware validation. Existing CSV
Power-of-Ten export remains Flight-oriented; Ground has its separate persisted
report and full GUI log/detail results.

The USB repair worktree is not merged. Its dependency-closure P2 remains an
external acceptance blocker, and the daily branch does not inherit the other
repair fixes. A Ground automatic PASS must not be represented as closing that
review, completing critical-contract acceptance, stack/WCET proof or hardware
qualification. FINAL, user projects/windows and generated candidates were not
modified; no hardware, flashing, long ARM build, publish or push was performed.
