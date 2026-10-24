# InEKF reference verification, 2026-10-17 (historical run03 scope)

The subsequent ESKF20 implementation has its own model and verification record;
this file preserves the original InEKF run and its historical scope.

Final executed suite: **57 passed, zero failed/skipped**, 10.28 seconds reported by
pytest in [run03/pytest.log](evidence/run03/pytest.log). This is one complete run
of both experiment test files, not passes combined from separate executions.
There are 49 mathematical cases and 8 catalog/source-graph isolation cases.

Command from `D:\python_software\SilverStar`:

```powershell
python -B apps/SCG/experiments/navigation_0_1_3/verify.py run03
```

Python 3.14.0; NumPy 2.4.0; SciPy 1.16.3; pytest 9.1.1. No dependency installation.
[run.json](evidence/run03/run.json) retains the expanded command/environment, exit
code, timestamps, version/commit identity, dirty status, and before/after hashes of
experiment source, SCG Python source and declarative plugin JSON inputs.
[inventory.json](evidence/run03/inventory.json) identifies the evidence owner,
purpose, retained paths, sizes and hashes. These are retained evidence, not cleanup
targets. No workspace copy, worktree, compiled binary, bytecode cache or firmware
output was created by this task.

## Executed failures and repairs

| Run | Actual outcome | Diagnosis and change |
| --- | --- | --- |
| [run01](evidence/run01/pytest.log) | 35 failed, 16 passed | Dense 5×5 expm produced nonzero roundoff in mathematically fixed bottom rows; strict group validation rejected its output. Replaced it with direct SE₂(3) block construction using SO(3) exp and the left Jacobian. Did not relax group validation or test tolerances. |
| [run02](evidence/run02/pytest.log) | 1 failed, 50 passed | The fixed 1e-6 finite-difference step subtracted metre-scale positions; one transition entry differed by 1.046e-9 against 1e-9 absolute tolerance. Changed the independent central-difference oracle to the documented cbrt(epsilon) × state-scale step. The acceptance tolerance is unchanged; finite-error log-linearity and independent ODE integration are checked separately. |
| [run03](evidence/run03/pytest.log) | 57 passed | Full rerun after those changes, with six additional initial/stored-state, nonadvancing-time and numerical-overflow rejection cases. |

The tests establish deterministic group-affine/log-linear identities for the
implemented bias-free model, map/reset/observation derivatives, full covariance
discretization and SPD on the stated synthetic cases, and the tested rejection
transactions. They do not establish every possible input or numerical condition.

Isolation checks scan real catalog metadata, reject manually entered experimental
IDs, and construct device-free metadata graphs for existing None/SF6/KF6/ESKF15
choices. No GNSS/M9N adapter implementation or regression runs. They do not claim
a full flight project's build or runtime validation.

## Boundaries and pending work

- **Reference implementation:** complete for the nine-error-state, no-online-bias,
  co-timed 3D position/velocity synthetic scope in README; remains unregistered.
- **Firmware implementation:** absent. No production ABI, parameter, log, decoder,
  UI, alignment, magnetic calibration, or existing algorithm implementation changed.
  Power-of-Ten, analyzer, ARM compilation/linking and resource acceptance were not run.
- **Hardware validation:** absent. No timing/stack, recorded-data, sensor accuracy,
  statistical consistency or flight-readiness claim.
- **ESKF20 at run03:** the parent had relayed the selected physical quantities,
  while book/source conventions were pending and no ESKF20 code existed. The
  later authorized implementation is described in ESKF20_MODEL.md. Run03 is not
  evidence for that implementation or the subsequently extended runner.

All earlier evidence remains intact. Further changes need their own fresh run;
none of these results authorizes opening a production selection option.
