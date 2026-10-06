# Save and open stage progress (2026-10-06)

Scope: FLP save/open feedback only, based on `cd76d8e0c8ccddb28e823e0f6ab6d47613276f51` in the isolated `flp-project-artifacts-20261006` branch. Integration requires the parent's independent review. The stable checkout is not modified by this patch.

## Behavior

The existing background task now reports actual stage boundaries. Save covers preparation/references, dataset and result serialization/compression/writes, verification, recovery history, project JSON/fsync, source checking when applicable, and atomic replacement. Open covers project metadata, exact decoder/Descriptor admission, source hashing, verified dataset cache or strict parsing, semantics, saved results, and publication.

These are stage percentages, not elapsed-time or byte completion estimates. Compression, hashing, large object decoding and verification can stay at a stage percentage while working. There are no timers, artificial increments, busy loops or additional threads. Existing parser progress is mapped into its reserved stage range. A failed cache attempt reserves its range before strict parsing, preventing backwards progress.

Project metadata/path preparation now runs in the existing worker rather than the GUI thread. Widget updates continue through the existing queued GUI slots. Save/open worker reports remain below 100%; the GUI reaches 100% only after a successful result callback returns. Failed or cancelled tasks do not report successful completion. Progress ignores late cancelled-worker signals and cannot decrease within a task. The translated format and tooltip explain the stage percentage in English and Chinese.

`TaskProgress` shares the existing cancellation event across nested ranges. The project commit-stage report and final cancellation check occur **before** `os.replace`. No cancellable progress callback runs after atomic replacement. The existing late-cancellation commit handling and actual worker-return/lifetime protocol are retained.

## Unchanged contracts

No decoder/parser algorithm, numerical algorithm, input selection, GNSS display, firmware, GSHC or SCG code is changed. No cache identity source coverage is weakened. `EngineIdentity_Get` and `ParserIdentity_Get`, all files they cover, artifact encoder/decoder classes, resource limits, path validation, and compression/array loading functions remain unchanged. UI progress is outside those numerical identity inputs, so this patch alone does not invalidate saved numerical results or dataset caches.

Identity hashes depend on actual checkout bytes. The isolated checkout engine/parser identities are respectively `129ceaffa6e8347aabcac9b308f4c0808d532e14dbc106aceb45ad8aa1579b1c` and `7fc0fba80c73576c26debd41107a52e7c91e57a96d0161678aada055974b77c5`, unchanged from its base. They must not be substituted for the stable checkout's different byte hashes.

## Recorded verification

Evidence lives in `.work/evidence/progress-20261006` in the isolated checkout and is included in the small review package. All commands use the shared FLP `.venv` interpreter (Python 3.14.0, NumPy **2.4.1**). No global NumPy interpreter is used.

1. Pre-fix core reproduction on base product sources, with the five new core tests: **4 failed, 1 passed**, exit 1 (`before.txt`, `before-exit.txt`). The saved `tests-before.py` is the unchanged final core test file. Failures show missing reports and the unobserved reported-commit cancellation hook; this is not a claim that base atomic storage itself failed.
2. Intermediate implementation core run: **5 passed**, exit 0 (`core.txt`, `core-exit.txt`). Later stage-label adjustments mean this intermediate run is not attributed to the final commit.
3. Final combined core/offscreen GUI run: **17 passed**, exit 0 (`gui.txt`, `gui-exit.txt`). This includes the five core cases, save with/without persisted data, verified/missing/corrupt parse cache opening, cancelled/closed/failed opening, and all four original save-lifecycle bodies executed unchanged with private test settings. The GUI checks record monotone values, GUI-thread widget updates, metadata and parser work off the GUI thread, valid-cache parser prohibition, automatic replay prohibition, and completion after GUI publication.

Final command, from the isolated worktree (PowerShell):

```powershell
$env:PYTHONPATH='C:/Users/chdxm/AppData/Local/Temp/flp-project-test-deps-20261006;apps/FLP/src;apps/FLP'
$env:QT_QPA_PLATFORM='offscreen'
& 'D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe' -m pytest apps/FLP/tests/test_project_stage_progress.py apps/FLP/tests/test_project_stage_progress_gui.py -vv -p no:cacheprovider --basetemp=C:/Users/chdxm/AppData/Local/Temp/fps-gui26
```

The pre-fix and intermediate commands select only `test_project_stage_progress.py`, use `PYTHONPATH=apps/FLP/src;apps/FLP`, and use `fps-before26` and `fps-core26` as their private basetemp respectively. The tests use synthetic exact-decoder 21-sample PureINS inputs: one reused input per new test module and four inputs from the unchanged original lifecycle cases, six tiny numerical runs in the final invocation. No real mission replay, four-algorithm large ESKF run, user window, user settings, serial port or hardware was used. Test durations in the logs are execution records, not performance benchmarks.

The final check also records source hashes and exact commit, compares unchanged numerical identity source coverage and artifact safety/codec functions against the base, and runs `git diff --check`. This is scoped progress/lifecycle regression evidence; it does not resolve the historical GUI GC root cause, prove large-log responsiveness, certify whole-FLP acceptance, or replace the parent's independent review.
