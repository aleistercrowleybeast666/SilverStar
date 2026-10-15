# RAM watch / summary evidence — 2026-10-15

Scope: GSHC GUI, local JSON CLI/API, shared ELF/DWARF catalog, and shorter atomic
TF checkpoint temporary filename. No firmware algorithm changes in this batch.
Sources are archived in execution.zip against the base commit in manifest.json;
the archive contains full command/environment/exit records, failures and compiler
fixture sources/ELFs. No target interface was opened. Read-only host PnP inventory
reported no probes; it is not target verification.

## Executed results

- `watch_final03`: **141 passed**, final watch/ELF/session/guard/Qt tests in one invocation.
- `gshc_final01`: **274 passed, 5 subtests passed, 1 failed**: the subprocess guard
  could not import test_swd_session because the runner omitted the tests directory
  from PYTHONPATH. Runner fixed; `guard02`: **24 passed** without changing the test.
- `gshc_final02`: **274 passed, 5 subtests passed, 1 failed**: the existing owned
  Python pipe child was reaped with exit 1 instead of expected 0. Its close code
  is unchanged and allows bounded host-process termination after 300 ms.
  `pipe_recheck01`: **1 passed**; final session suite also passed. Load sensitivity
  is suspected, not proven. No timeout or assertion was weakened.
- `gshc_full01` (intermediate source, before final watch refinements):
  **833 passed, 15 subtests passed, 9 failed**. It is not a final-source full pass.
  Five failures expect the obsolete three-page layout (the runtime/log page
  already existed at base); two concern English header geometry; one concerns
  missing touch scrolling on an existing QListWidget; one is the runner import
  problem above. Complete failures remain in the archive.
- `baseline_ui01` imports changed modules from HEAD in memory, without a checkout:
  **33 passed, 7 failed**. It reproduces the five three-page expectations and
  existing touch coverage failure; also one English small-window layout failure.
  The two full-run header failures did not reproduce in this subset. Their cause
  remains unresolved; the affected header code was not changed.
- `gshc_baseline03`: **210 passed, 5 subtests passed, 2 failed** before the TF
  filename fix. Both fail on the long checkpoint temporary path. `watch_tests03`
  (watch plus entire file-transfer UI file): **32 passed, 5 subtests passed** after
  the fix. Both final GSHC runs passed the entire TF client/UI files.
- Earlier runner, temporary-path, fixture compilation and intermediate rate-limit
  failures are retained, not omitted from the claimed outcome.

## Coverage and limits

Real ARM compiler-produced ELF tests cover file statics with duplicate names,
nested constant members, integer/enum/bool/float/double, unsupported pointers/
arrays/bitfields/locals, missing DWARF, member escape, runtime RAM boundary checks,
short reads, unknown selection, identity, reset invalidation, nonfinite JSON,
rate/byte limits, cancellation, paused lifetime expiry, GUI add/remove/pause and
touch coverage for the new controls. Target memory/probe objects are synthetic.

Offline existing ESKF15 firmware ELF SHA256
`1a4094d22186f39b4f25ab88af609c29fd44a1366a6076ec09a3fb21690c7fb9`:
2110 catalog entries, 1543 usable, including 147 binary32 fields. That old ELF is
input to a parser test, not a newly compiled fix or current target identity.
Chinese/English offscreen screenshots were inspected. OpenGL/real display scaling,
actual variable reads and STM32 timing remain unverified.

Python 3.14.0, PySide6 6.10.1 and pinned existing pyelftools 0.33 runtime were used;
complete tool version output is retained. No dependency installation was needed.
The standalone version query initially missed isolated pyelftools metadata;
`tool_versions02` uses the same existing dependency resolver as production.

Overall GSHC full-suite status remains **FAILED / unresolved**, despite focused
feature tests passing. No hardware acceptance, whole-program safety proof, NASA
certification or original Power-of-Ten compliance is claimed. User inputs, frozen
v0.1.2 tag/release and external FINAL firmware are unchanged. No cleanup/push/tag.
