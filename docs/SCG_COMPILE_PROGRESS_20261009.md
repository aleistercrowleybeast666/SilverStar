# SCG measured compilation progress — 2026-10-09

The user's complaint concerns the looping bar **during compilation**. The two
compile/audit phase events in `191fd3903025d5a41c3d3eb6b12eadc83c279ce3` did not
measure completed objects. The target GUI also bypassed the existing runner's
plan/marker support. This change uses the actual selected target's `make -n`
output to count pending unique compile/link/bin/hex/size units, including
incremental builds. It reserves one additional unit for the real artifact audit.

Flight already emits `FCCG_PROGRESS` completion markers. Ground's unmarked
Makefile is observed with GNU make `--debug=j`: a target earns completion only
after its final winning child is removed. Recipe launch, intermediate successful
commands and failed recipes earn no completion credit. Parallel job events are
tracked by make's child identity and completed units are deduplicated. Native
MinGW make 4.4.1 also emits blank PID fields; the parser supports that format.
No generator template, firmware, assertion policy or USB payload is changed.

The bar starts at fixed zero while planning, then advances from verified units.
Unknown command output reports a processed-line count rather than a fabricated
percentage. No-work builds explicitly report no pending compile tasks and still
perform the artifact audit. Only actual successful task completion sets 100%;
failure/cancellation retains incomplete progress. This is work-unit progress,
not an estimate of elapsed time or a prediction of remaining time.

## Validation scope

Evidence is retained under `.work/CompileProgress_20261009` and the small tracked
`docs/evidence/scg_compile_progress_20261009` directory. The targeted command is:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& ../FLP/.venv/Scripts/python.exe -u -B ../../.work/gui012_20261008/run_pytest.py tests/test_target_compile_progress.py tests/test_ground_gui_acceptance_20261009.py tests/test_build_progress.py tests/test_task_progress_busy.py -q --basetemp=.work/cp9j --tb=short
```

The runner adds the repository source paths, disables pytest's cache provider
and uses the existing normal/isolated Windows path/settings plugins. Python
3.14, PySide6 6.10.1, pytest 9.1.1 and native MinGW make 4.4.1 were used. The
known `cache_dir` configuration warning is retained. Test inputs and fake
object/ELF text files are tiny synthetic scheduler fixtures, **not firmware or
hardware evidence**. GUI cases hold the worker after its first completed object
and verify progress while compilation is still active, then cover success,
failure and cancellation. Native make covers parallel recipes, incremental and
no-work builds, including a recipe failing after creating its output file.

An initial test waited on the worker emission event before Qt delivered the
queued progress signal: both pre/post runs failed (3 each). This test race was
fixed by waiting for the expected GUI state, without changing the expected 20%
value. The corrected baseline loads only the original target GUI entry from
`git show 191fd39:...` into the isolated window. It must fail to reach 20% while
the worker is held. Failed and successful runs are preserved individually;
they are not combined into a claimed unexecuted suite result.
The first added native failure case also exposed make's timestamp granularity:
rapid fixture rewrites were considered up to date (34 passed / 1 failed). The
test now sets only its synthetic object timestamp older than its input, ensuring
the failing recipe actually executes; production completion expectations are
unchanged.

No user's GUI window, project, decoder, log or binary was changed. No hardware,
flashing, serial access, push, cleanup or long firmware build occurred in this
progress stage. USB integration and actual ARM compilation are separate scopes.

Final executed targeted suite: **35 passed**, exit 0, 61.23 seconds. Corrected
pre-fix GUI baseline: **1 failed**, exit 1, 15.87 seconds. The complete final run
is `final2.log`; the earlier 34-pass run predates the additional native failure
and planning-failure checks and does not substitute for this final result.
