# InEKF15/20 incremental independent review, 2026-10-18

**Result: no substantive implementation defect found in the reviewed increment.**
No estimator, test, model, validation, registration or runner file was changed.
The existing complete suite was freshly rerun: **250 passed, zero failed/skipped,
13.77 s**. Five separate targeted independent mathematical checks also passed on
their first execution. They are not reported as a single 255-test pytest run.

## Model and source review

Read repository AGENTS.md, both augmented implementations, both new test files,
INEKF_AUGMENTED_MODEL.md and INEKF_AUGMENTED_VALIDATION.md, plus the reused
mathematical contracts from the preceding audit. The originals' limitations are
appropriate: an imperfect bias augmentation does not inherit the unaugmented
finite-error log-linear or strict group-affine claim. The bias-augmentation
discussion and left-invariant coupling matrix agree with the relevant material
in [Hartley et al., sections 7 and 10, equation (34)](https://arxiv.org/html/1904.09251v2#S10),
opened independently during this review. No upstream implementation was copied.

Independent derivation with zeta=b_hat-b_true gives local couplings
F_phi,zeta_g=-I and F_nu,zeta_a=-I, and true bias random walks enter zeta with a
negative sign. Holding estimated biases and measured IMU inputs freezes this
linearized F over one interval; it does not freeze the true random biases or
make the nonlinear augmented error law exactly linear. The 30x30 Van Loan
result is therefore an exact linear SDE discretization within that approximation.

For the magnetic extension, the navigation error uses estimate-minus-truth while
installation uses A_true=Exp(-gamma)A_hat. This yields the same negative
`-[h]x R_hat` magnetic columns for phi and gamma. Resetting the former by the
right group correction gives J_left_SE23; resetting the latter gives J_right_SO3.
Bias reset is additive, as its coordinates remain in the fixed physical IMU
basis. The full matrix product retains all mixed covariance blocks. No sign,
side, omitted mixed covariance, or magnetic-angle formula defect was identified.

## Test common-assumption checks

One coverage weakness was identified, not an estimator defect: the original
InEKF15 Q quadrature obtains F/G from the implementation, so that particular
check alone cannot reject a shared F/G mistake. Other existing finite-difference
tests already independently constrain F and the instantaneous G. This review
added an end-to-end physical impulse calculation without F, G, the reference
retraction/propagator or the ESKF coordinate-conversion helper in its expected Q.
Likewise, the expected full-P calculation uses physical initial perturbations
and general matrix logarithms, not the reference transition matrix.

The complete magnetic Joseph test uses the implementation's H, but a separate
existing physical sensor perturbation test checks every H column. The prior
reset tests independently use general matrix exp/log and SO(3) geometry. They
are complementary checks rather than an independent proof supplied by the
Joseph test in isolation. No test tolerance was changed in this review.

## Five targeted independent checks

All are retained in [check_independent.py](check_independent.py), with complete
metrics in [independent.log](independent.log). Existing NumPy/SciPy only; no
datasets, large arrays, downloads, extra dependencies, or adapters.

| Check | Independence and outcome |
| --- | --- |
| Random-walk cross-covariance closed form | Integrating Brownian bias directly gives Q_phi,zeta_g=-sigma_bg^2 dt^2/2, Q_nu,zeta_a=-sigma_ba^2 dt^2/2, Q_rho,zeta_a=-sigma_ba^2 dt^3/6, plus the diagonal and velocity/position moments. All signs/coefficient blocks agree; maximum absolute error 1.32349e-23. |
| Nonzero-turn physical process-noise impulses | Apply actual gyro/accel impulses and true bias jumps at ten quadrature times, then propagate true motion with the changed bias through independent SO(3)/acceleration quadrature. Read invariant error with a general matrix logarithm. Anisotropic twelve-source Q agrees to maximum absolute error 3.22688e-17. |
| Full 20x20 prediction | Independent finite perturbations of physical rotation/velocity/position/biases produce Phi; combine with the physical impulse Q and a dense prior. All mixed blocks agree; maximum absolute covariance error 5.23460e-13. |
| IMU basis change through prediction and magnetic correction | Rotate the physical IMU axes while keeping navigation and magnetic sensor axes fixed, transforming R, A, biases and full P consistently. Use isotropic noise within each source so the diagonal-noise API is closed under this transformation. Nonzero magnetic correction, installation injection and reset commute with the basis change; maximum covariance difference 1.21431e-17. |
| Inclination boundary reached through cross-P | A position observation updates I through a deliberately correlated prior. An outward correction is rejected with the exact original object/bytes; the inward correction succeeds and changes I by -0.00333333333333341 rad. Rotation limits do not explain this rejection. |

The fresh complete suite also retains the prior exact-pole D-null and near-pole
nonzero sensitivity checks, invalid/missing-data transactions, general group
reset finite differences, full H perturbations, and the declared synthetic
observability/convergence windows. The review did not extend functionality or
inflate the production test list; the five counterchecks are audit evidence.

## Commands and evidence

From `D:\python_software\SilverStar`:

```powershell
python -B apps/SCG/experiments/navigation_0_1_3/evidence/augmented_audit_20261018_v1/run_audit.py
python -B apps/SCG/experiments/navigation_0_1_3/verify.py augmented_audit_20261018_full
python -B apps/SCG/experiments/navigation_0_1_3/evidence/augmented_audit_20261018_v1/finalize_inventory.py
```

[independent_run.json](independent_run.json) and the complete-suite
[run.json](../augmented_audit_20261018_full/run.json) retain actual expanded
commands, environment, UTC start time, exit, Python/dependency versions, source
commit, source hashes before/after and log hashes. All commands exited zero.
Python 3.14.0, NumPy 2.4.0, SciPy 1.16.3, pytest 9.1.1; bytecode disabled,
single-thread numerical libraries and warnings treated as errors. The full
[pytest log](../augmented_audit_20261018_full/pytest.log) records all 250 cases.
No hashed inputs changed during either execution.

The underlying commit is 7896c1d09a7f9138c41cdac35beef38347d94b78 plus the already
dirty, untracked experimental source identified by the hashes. All existing
top-level files match the start of this audit, and every executed Python file
matches the incoming 250-pass revision. [final_inventory.json](final_inventory.json)
records retained paths, bytes, owner/purpose, hashes, historical evidence checks,
and the report's post-test creation. No cleanup, overwriting or source snapshot
copy was needed; all new files are in the two new versioned evidence directories.

## Explicit limits

This review supports the stated local imperfect-model equations and the recorded
synthetic cases. It is not a proof for every input, trajectory, covariance or
floating-point scale. Shared SciPy/float64 infrastructure remains a common
dependency of implementation and oracles. The full-rank scenarios are finite,
unwhitened local numerical observability tests in declared units; their truth-
linearized matrices and noise-free convergence do not prove estimator consistency
or global identifiability. No independent long-window nonlinear observability
proof or NEES/NIS Monte Carlo was performed.

Installation and field angles remain constant parameters with an imperfect local
Gaussian chart; exact-pole D unobservability and near-pole ill-conditioning remain.
Caller-declared magnetic frame/calibration provenance is not independently known.
Online hard/soft-iron calibration, delayed data, real initialization, recording
robustness, physical timing, stack/resource safety and accuracy remain unproven.

Both references remain unavailable for production selection/generation. No
production ESKF15, calibration/alignment, GSHC, M9N/GNSS adapter, registry or
hardware was changed or invoked by the targeted checks. The unchanged full-suite
runner performs its preexisting read-only catalog isolation and FLP pure-math
comparison. Suspended M9N work was not resumed or retried. No firmware generation,
Power-of-Ten acceptance, analyzer/ARM build, hardware/flight qualification, publish
or push occurred. No execution blocker remains for this review.
