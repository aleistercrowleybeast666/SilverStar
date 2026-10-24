# ESKF20 and InEKF host experiment verification — 2026-10-17

One complete run: **120 passed, zero failed/skipped**, pytest 7.03 s, runner
8.659 s. This includes **63 ESKF20**, 49 existing InEKF mathematical cases and
8 catalog/validation/source-graph isolation cases. It is not a combined result
assembled from different runs. [Complete log](evidence/eskf20_run02/pytest.log).

Command, from `D:\python_software\SilverStar`:

```powershell
python -B apps/SCG/experiments/navigation_0_1_3/verify.py eskf20_run02
```

Execution started 2026-10-17T17:45:30.162091+00:00; exit 0. Python 3.14.0,
NumPy 2.4.0, SciPy 1.16.3, pytest 9.1.1. Source commit
`7896c1d09a7f9138c41cdac35beef38347d94b78` plus the recorded dirty snapshot.
[run.json](evidence/eskf20_run02/run.json) contains actual expanded command,
environment, versions, dirty status, relevant source hashes before/after,
complete skip/exclusion scope and log hash. No hashed input changed during this
run. [Evidence inventory](evidence/eskf20_run02/inventory.json) records paths,
purpose, owner, sizes and SHA-256. No dependency install or copied workspace.

## What was checked

- Independently perturbed all twenty magnetic Jacobian columns across five
  inclinations and zero/nonzero installation, including all eight sensitive
  columns; central differences use physical sensor measurements from independently
  constructed true states. Exact physical I/D derivatives replace the textbook's
  small field-frame rotation approximation; I=60 degrees gives D sensitivity 0.5.
- Continuous F from physical error rates and discrete Phi from independently
  propagated true/nominal trajectories; nominal flow against independent ODE
  integration. The first fifteen F coordinates and attitude reset were also
  compared against the existing FLP pure-math ESKF15 module. No FLP tests or
  device adapters were invoked.
- Both rotation injections, full 20x20 reset Jacobian and all dense covariance
  cross terms; complete Joseph/update/reset against independent finite differences.
- Noise mapping, density squared once, covariance integral against quadrature,
  time-step composition, and constant additional-state dynamics.
- Nonzero installation through synthetic turning/accelerating prediction and
  co-timed magnetic/position/velocity correction; SPD checks at every step;
  twelve omitted magnetic observations preserve the prior and prediction proceeds.
- Exact/near inclination poles, vanishing D sensitivity, instantaneous rank two
  and an explicit attitude/installation gauge. These tests demonstrate ambiguity;
  they do not establish dynamic identifiability or parameter convergence.
- Wrong magnetic frame/calibration, bad times/shapes/nonfinite/complex values,
  invalid SPD states/noise, NIS rejection, large correction and numeric overflow.
  Rejected operational steps retain the original state object and bytes.
- Real catalog and source-graph rejection of experimental identifiers; existing
  None/SF6/KF6/ESKF15 metadata choices contain no experiment sources. Models have
  all devices removed, so this is not a complete firmware project's validation.

## Full failure history for this extension

| Run | Actual result | Diagnosis and repair |
| --- | --- | --- |
| [eskf20_run01](evidence/eskf20_run01/pytest.log) | 3 failed, 117 passed | Two exact-pole test-oracle failures: generic quaternion rotations left horizontal components around 2.22e-16, giving a 3.03e-16 difference versus the existing 2e-16 assertion. Use the known analytic pole vector in the independent oracle and additionally check the implementation's field at two declinations. The original acceptance tolerance is unchanged. The third test called an ESKF15 instance method as a class method; instantiate that existing pure-math filter before comparison. No ESKF20 implementation change was needed. |
| [eskf20_run02](evidence/eskf20_run02/pytest.log) | 120 passed | Complete rerun after the oracle and call-site repairs, including the original InEKF and isolation tests. |

The original InEKF-only failure/run history remains in [VALIDATION.md](VALIDATION.md)
and evidence/run01–run03. Its older `final_inventory.json` is a historical snapshot,
not a checksum claim for subsequently edited documents or runner. The extension's
current deliverables are listed in `final_inventory_eskf20.json`. No evidence is
deleted, reclassified or overwritten. All inventories are retention records,
not cleanup authorization.

## Remaining limitations

Implemented scope is the offline float64 model in [ESKF20_MODEL.md](ESKF20_MODEL.md).
The existing production magnetic sample already uses body coordinates and its
calibrated contract includes installation correction; it cannot be passed to
this sensor-frame model without a separately designed boundary. Exact error
conventions and magnetic derivatives have independent mathematical checks here;
the book-page transcription was verified by the parent, while this worker's
PDF endpoint retrieval was unavailable.

No production registration, public layout/ID, decoder, GUI, firmware plugin,
alignment or magnetic calibration implementation changed. The separate suspended
M9N/GNSS adapter work and regressions remain untouched. No hardware, push,
worktree, firmware generation or dependency download occurred.

No real-data replay, Monte Carlo consistency, actual-motion observability,
disturbance rejection or performance envelope has been established. C port,
Power-of-Ten project gate, real analyzer, ARM compilation/linking, stack/timing
and hardware/flight evidence are absent. Critical-contract review outside these
specific host checks is **NOT PROVEN**; host test success does not constitute
completed firmware acceptance. Both experiments remain unavailable for selection.
