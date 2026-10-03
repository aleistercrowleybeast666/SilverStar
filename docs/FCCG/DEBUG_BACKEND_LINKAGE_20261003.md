# Debug backend linkage

The unchanged 6047ec7 baseline fails KF6 Debug linkage with undefined
SystemNavigationBackend_Predict, Initialize, SnapshotGet and Reset. The generated
source list is the same for Debug and Release. KF6 links its actual KF6 kernel;
the external navigation backend sources belong to selected SF6/ESKF15 builds.
The runtime ownership helper returns a constant build decision, but -Og retains
the external calls that -O2 eliminates. Correct linkage must not depend on that
optimization.

Compile the external-backend wrappers and their prediction, initialization,
rollback and abort call sites only when the selected plugin declares
SF6/ESKF15 linkage capability. ESKF15 already declares its marker; SF6 now
declares SYSTEM_BUILD_SF6_ENABLED=1U. A C static assertion checks that these
numeric capabilities agree with the typed build ID and rejects mismatches.
Algorithm IDs are enum constants, so they must not be compared by the
preprocessor. This matches the existing ownership helper and generator graph. Retain real backend implementations and unchanged runtime
checks in selected builds. KF6/Pure INS retain their existing direct paths.
No empty symbols, fake backend, estimator math, NIS policy, origin or attitude
changes are introduced. This build fix is committed separately from M9 recovery.

Rule-8 review: the explicitly requested preprocessing repair adds only the
exact SYSTEM_BUILD_NAVIGATION_BACKEND_ENABLED != 0U condition to
APP/Src/estimator_task.c. Header capability derivation uses the selected SF6
marker or existing ESKF15 marker; a typed C assertion rejects graph/ID mismatch.
The six guarded call sites must be absent for KF6/Pure INS and present for
selected real SF6/ESKF15 backends, independently of optimization. The authorized
gate revision retains source coverage, thresholds, unknown-path/flag rejection,
all other nine rules, and mandatory NOT PROVEN reporting. Positive path tests
and new negatives for lookalike paths, inverted/changed constants and arbitrary
flags exercise this narrow reviewed condition; no generic preprocessing waiver.


Validation of the isolated generated candidate:

- KF6 Debug and Release: all, architecture, Power of Ten, real compiler static
  analysis, linked artifact/memory checks and compiled stack reports passed;
  full Host suite passed 75 executables, 4,430,924 checks, zero failures, seven
  compile-positive and seventeen expected compile-negative probes.
- SF6, ESKF15 and Pure INS: fresh generated C, real ARM Debug and Release
  builds, linked artifact checks and stack reports passed (six builds, j2,
  unchanged legacy memory layout). SF6/ESKF15 source graphs and linked ELF
  symbols contain the real Initialize/Predict/SnapshotGet/Reset implementations;
  Pure INS links none of these external-backend symbols.
- Contradictory KF6-with-SF6-capability and SF6-without-capability actual ARM
  task compilations fail the typed static assertion. The narrow preprocessing
  checker suite passes 97 tests, including lookalike paths and changed flags.
- Comparison of the pre-fix and post-fix KF6 Release estimator task object
  disassembly and relocations finds 154 changed immediate loads. Each binds to
  the moved line number of an otherwise identical SILVERSTAR_ASSERT source
  line. There are no other disassembly changes, added/removed sections, or
  changed readonly constants in this object. Eight raw text/readonly sections
  are byte-identical. This is scoped object evidence, not whole-program
  equivalence; the Release BIN hash changes and is not claimed identical.
- Release DeviceTask compiled estimate remains 2,136 of 2,560 bytes (424-byte
  margin). Debug estimate is 1,712 bytes (848-byte margin). Static bounds are
  not measured hardware peaks. All configured task budgets pass.

Candidate hashes (SHA-256, local deliverables; no firmware artifacts published):

- Debug BIN: `dd0b877c6b7b87902d029c7178fc0bab62d741ca02fa2bc740d4405f08ed7b9c`
- Debug ELF: `cb278805cfe0aee26250920306716a51225ed45c4725f9ad8058b92d9e123484`
- Release BIN: `cea0a70b7bced07f4ea0cfa1d61b3e7b35a0528607d524e052c6426271d9577e`
- Release ELF: `9fd277a5dd8b331046c01eb49d527d5102c10e2c39363c2d3eb87c80f73c54d1`

Failed baseline and intermediate candidates/logs remain separate locally.
No hardware access or flash was performed. Identity/configuration readback,
CRC, KF6 NIS/covariance, mission origin and coordinates remain guarded.
Critical whole-system contracts remain NOT PROVEN; actual-board acceptance
and final source review belong to the parent integration task.
