# InEKF15 then InEKF20: executed host evidence — 2026-10-18

The staged extension is complete within the [frozen host model contract](INEKF_AUGMENTED_MODEL.md).
Both remain unregistered, unselectable and ungeneratable. These are imperfect
bias-augmented invariant references with full 15x15 / 20x20 covariance; they do
not claim strict whole-system group-affinity or exact finite-error log-linearity.

## Staged executions

Both commands ran from `D:\python_software\SilverStar` with existing Python 3.14.0,
NumPy 2.4.0, SciPy 1.16.3 and pytest 9.1.1. No dependencies were installed.

```powershell
python -B apps/SCG/experiments/navigation_0_1_3/verify.py inekf15_20261018_run01
python -B apps/SCG/experiments/navigation_0_1_3/verify.py inekf20_20261018_run01
```

| Stage | Complete result | Interpretation |
| --- | --- | --- |
| [15-dimensional run](evidence/inekf15_20261018_run01/pytest.log) | **196 passed**, zero failed/skipped; pytest 9.55 s | Original 163 cases plus 33 new InEKF15 cases. This completed successfully before the InEKF20 implementation was written. |
| [20-dimensional run](evidence/inekf20_20261018_run01/pytest.log) | **250 passed**, zero failed/skipped; pytest 14.48 s | Includes all preceding 196 cases, 50 InEKF20 cases and four additional isolation-ID rejection cases. This single complete run is the final executable result. |

There were no failed, skipped or selectively rerun cases in this extension.
The original audit failure histories remain intact and are not reclassified.
The original exact-pole/scalar/overflow repairs and their 43 independent audit
tests were not edited. Existing nine-state InEKF, ESKF20 and shared mathematical
implementation files were not edited. The isolation file only gained four
additional unknown-ID probes. The runner gained the two new test files and
captured successful-test output so numerical scenario metrics remain in the log.

Each run directory contains a full pytest log, `run.json`, and inventory.
The JSON records expanded command, working directory, versions, explicit
environment overrides, start time, process exit, source commit and dirty status,
before/after SHA-256 for relevant source/metadata, and excluded validation.
Neither run had any hashed input change during execution. The source commit is
`7896c1d09a7f9138c41cdac35beef38347d94b78`; the working tree is dirty and these
experiments are untracked, so the commit alone is not their source identity.
No binary or result from a different revision is substituted.

The small evidence directory [inekf_augmented_20261018_v1](evidence/inekf_augmented_20261018_v1/)
contains the starting file inventory, snapshots of the three preexisting files
edited by this task, the exact passed stage-15 source/runner, and the final
inventory/integrity report. Documentation was finalized after execution; all
executed Python/config files are checked against final run hashes. Prior logs,
inventories and source snapshots are retained. No cleanup was performed or
authorized; retained evidence and source snapshots are not deletion targets.

## Independent mathematical coverage

- Continuous 15x15 F from independently propagated physical error rates; discrete
  15x15 and 20x20 Phi from central perturbations of true/estimated trajectories.
  Nominal translation uses an independent ODE oracle and SO(3) rotation formula.
- Position/velocity H and all twenty magnetic H columns, using physical
  sensor-frame measurements at five inclinations with zero/nonzero installation.
- Complete group injection and all reset entries from a general matrix exp/log
  oracle. Tests include navigation translation/rotation couplings, bias cross
  terms, installation reset and dense full covariance transformations.
- Physical process-noise impulses, noise-sign mapping, Qd quadrature, density
  scaling and step composition. All twelve densities are squared once; the
  additional five constant parameters have zero process noise.
- Complete 20-dimensional magnetic Joseph/update/reset against a separately
  computed gain and numerical reset; magnetic information reaches bias states
  through full cross covariance rather than a disconnected appended block.
- Common ESKF coordinates: independent error-map derivative, transformed full
  covariance prediction and magnetic H. A finite correction test confirms the
  SE₂(3) translation update actually differs at second order; it is not an ESKF
  function invoked under a new algorithm name.
- Group-affine and finite log-linear counterexamples for the biased product
  model, plus recovery of the known-bias deterministic nine-state property.
  Algebraic left-invariance of the navigation error is tested separately.
- Sensor-axis relabeling transforms A, vector and covariance consistently.
  Exact magnetic-angle derivatives, 60-degree D sensitivity, exactly zero pole
  D sensitivity, near-pole nonzero sensitivity, and a finite static yaw/D gauge.
- Repeated missing observations, explicit wrong-frame/calibration rejection,
  malformed arrays/scalars, immutable copied state, overflow, stored-state
  corruption, NIS/correction rejection and SPD throughout the simulated loops.

## Excitation, missing data and limited convergence evidence

The scenario is fully specified in the new tests: 50 Hz held IMU input,
co-timed position/velocity every fifth sample, known constant ENU gravity,
explicit priors and noise densities, and noise-free synthetic observations
with positive assumed measurement covariance. The 20-state scenario adds
nonzero magnetometer installation and magnetic observations every fifth sample.
The same numerical observability convention is used throughout:
stack `H_k Phi_k:0`, in the declared state units, threshold `sigma_max * 1e-8`.
Ratios below are unwhitened singular-value ratios for these windows only.

| Scenario | Numerical rank | sigma_min / sigma_max | Interpretation |
| --- | --- | --- | --- |
| InEKF15, 13 s rotating/accelerating | 15/15 | 1.68135e-4 | Full local rank for this specified window; all six bias errors decrease. |
| InEKF15, 3.2 s static | 11/15 | 6.60701e-20 | Gyro z error stays near 0.007 rad/s (final 0.00695392); all biases are not identified. |
| InEKF20, 13 s rotating/accelerating | 20/20 | 1.37089e-4 | Full local rank for this specified window; all six bias errors decrease. |
| InEKF20, 3.2 s static | 14/20 | 3.59712e-20 | Multiple unobservable directions remain; horizontal accelerometer-bias errors largely persist. |

Both excited runs start with bias errors:
`bg=[0.008,-0.006,0.007] rad/s`, `ba=[0.035,-0.030,0.025] m/s²`.

| End of 13 s excited window | Gyro-bias error, rad/s | Accelerometer-bias error, m/s² |
| --- | --- | --- |
| InEKF15 | [-2.40309e-6, 1.44629e-6, 4.28666e-6] | [2.71414e-4, -3.78300e-4, -6.57249e-6] |
| InEKF20 | [1.01209e-6, -1.91640e-6, 3.94388e-6] | [2.04634e-4, -1.52152e-6, -2.24578e-5] |

The logs retain full precision. InEKF15 has 1040 explicit missing position/velocity
update calls in the 13 s loop; InEKF20 has 520 missing magnetic calls. Without
any observations, the 15-state filter does not estimate biases. Without magnetic
observations and with an initially independent extra covariance block, the
20-state filter does not estimate installation or field angles or reduce their
covariance. These checks distinguish the selected synthetic conditions from
unqualified parameter-convergence claims. They are not noisy Monte Carlo,
unit-independent conditioning, global observability or all-motion proofs.

At each exact pole, an independent D prior variance of 1e28 is retained unchanged,
with exactly zero D sensitivity. This numerical stress input tests the declared
finite/SPD domain and protects the audit repair; it is not a realistic prior or
evidence that a globally Gaussian angle model is valid. Distances 1e-7 and 1e-10
rad from a pole retain nonzero physical sensitivity.

## Isolation and remaining work

The real catalog, project validation and source graph reject inekf, iekf, inekf15,
inekf20, iekf15, iekf20 and eskf20 probe IDs. Existing None/SF6/KF6/ESKF15 metadata
graphs contain no experimental source. Probe IDs do not assign public algorithm
identities. Device-free metadata models are not full firmware build validation.

No production ESKF15, M9N/GNSS adapter, GSHC, initial alignment or magnetic
calibration code changed. The suspended task and its regressions were not run.
No hardware, push, generated firmware, worktree, project copy or dependency
download occurred. Only this small versioned experiment/evidence directory was
written. Shared validators and exact-pole/physical magnetic derivatives remain
the independently audited implementation.

Remaining **NOT PROVEN**: real sensor calibration/frame provenance and adapter,
real initialization and sensor timing, recorded-data performance, realistic
disturbances/outliers, statistical consistency, global/local observability beyond
the reported windows, safety-critical contract completeness, C firmware port,
Power-of-Ten project gate, static analyzer, ARM compile/link, MCU stack/timing,
hardware accuracy and flight qualification. Passing host tests does not open
selection or generation. No execution blocker remains for the authorized offline
reference scope; production enablement remains a separate decision and task.
