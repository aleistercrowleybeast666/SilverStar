# FLP fusion timing boundary and barometer timestamp evidence — 2026-10-15

This batch fixes ESKF15 barometer delay interpretation and introduces a strict,
data-only timing declaration. It does not enable current fusion in firmware or
FLP. New current implementations and the separate v2 wire contract are later work.

The fix uses a trusted recorded sample epoch directly; otherwise it subtracts the
configured delay from receive time, matching the real C SystemTime resolver.
An explicit What-if delay override on old ESKF records requires unique recorded
BARO_NATIVE trust evidence. Missing or ambiguous evidence is rejected. Recorded
Configuration keeps the recorded measurement epoch; input bytes are unchanged.

New declarations reject unknown modes, mismatched owners and contradictory timing
semantics. Absent declarations preserve existing legacy admission rules. The
initial implementation introduced seven old-package import failures; they were
fixed without changing old packages or golden outputs. A later full-suite attempt
found one additional missing-raw_metadata context exception; it was fixed and the
original aggregation refusal test now passes.

## Executed evidence

| Run | Outcome and scope |
| --- | --- |
| bt01 | Initial Host stub link failures retained; no defect claim |
| bt02 | 56 failed / 9 passed against the original barometer implementation; pre-fix behavior |
| bt03 | 65 passed, actual complete C SystemTime source compiled at O0/O2 |
| bt04 | 102 passed / 10 failed; contains the superseded new timing import failures |
| before_integration01 / after_integration01 | 20 failed / 14 passed and 12 failed / 105 passed; intermediate boundary implementation records |
| timing_repair01 | Invocation error (nonexistent test path), no tests; retained |
| timing_repair02 / 03 | Each 197 passed / 7 failed; the same seven nodes fail under committed-module baseline |
| timing_baseline01 | 96 passed / 7 failed, exact read-only module overlay from 08e76ec5 |
| timing_repair04 | Final focused run: **217 passed / 7 failed**; includes the repaired aggregation case and four new metadata-context checks |
| flp_full_timing01 | **INCOMPLETE**: 950 outcomes printed from 1,290 collected tests, then blocked in test_path_preferences at an unmocked save modal dialog; interrupted, no final pytest summary |
| flp_modal_baseline01 | Same test under committed-module baseline: 15-second stack capture shows QDialog.exec in _SaveOptions_Select; diagnostic process exits 1 |
| flp_failed_current01 | All 46 failed nodes inferred from the original progress order reproduced with full tracebacks before the final context fix |
| flp_failed_baseline01 | 44 outcomes reported (43 failed, aggregation case passed), then teardown stalled; interrupted, not a completed subset pass |
| flp_optional_baseline01 | Remaining two nodes independently fail with kf6_algorithm_revision_missing |

The seven final focused failures are the existing recorded-export source failure
and six KF6 revision/identity-related failures. Wider failures also include stale
schema/golden expectations, UI expectations and sandbox path permissions. A matching
failed node is evidence of baseline failure, not proof of an identical root cause.
The complete current traceback, partial baseline outcomes, modal stack and exact
commands are retained. No unrelated expectations or guards were relaxed.

The full attempt does not establish the status of its remaining 340 tests. These
results must not be combined into a full-suite pass. New source files retain strict
current-unavailable behavior until actual firmware/runtime record support lands.

## Provenance and limits

`manifest.json` binds every archived byte to a SHA256 and includes the exact final
eight-file dirty snapshot on base 5af1efa1. `execution.zip` includes original and
final plugin sources, test sources, commands, failure logs, C compiler receipts and
the real SystemTime source. `receipt.json` binds the archive. The read-only baseline
loader compiles committed module bytes while retaining their normal module paths;
traceback source-line display can therefore show a current file line, while the
recorded module hash identifies the code actually executed.

No generated target firmware is changed by this batch; no ARM or hardware result
is claimed for Python metadata/barometer handling. Later concurrent firmware work
is outside this snapshot. No source log, decoder package, user input, v0.1.2 release,
tag or hardware was changed, and no cleanup was performed.
