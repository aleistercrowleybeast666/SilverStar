# Independent host mathematical audit, 2026-10-18

Two substantive defect classes were confirmed and repaired inside this experiment:
false declination information at the exact magnetic poles, and malformed-input
transactions that could escape or retain mutable scalar state. The final single
execution passed **163 tests, zero failures/skips** (120 existing + 43 independent
audit cases), pytest 6.70 s. This is offline float64 evidence only. InEKF remains
the bias-free SE_2(3), nine-error-state model; neither model is selectable,
generatable, firmware, or qualified for flight.

## Findings and minimal fixes

1. **Exact-pole declination information was numerically nonzero.**
   `Magnetic_Field` used the library value cos(pi/2), approximately 6.123e-17,
   where the documented chart endpoint denotes a field exactly independent of D.
   The old pole tests used a small isotropic prior and an absolute field tolerance,
   so both implementation and tests treated that residual as harmless. With a
   diagonal SPD prior diag(1e-6,...,1e-6,1e28), the new physical pole oracle showed
   P_D dropping from 1e28 to 2.28490266497077e27 at either pole in one successful
   update. This stress case exercises the declared finite/SPD domain; it is not
   a realistic magnetic noise/prior configuration or a performance prediction.
   The fix evaluates sin(I)=+/-1 and cos(I)=0 at the exact endpoints, including
   the derivatives. No near-pole interval is clipped. Independent tests require
   exactly zero D sensitivity and unchanged independent P_D at the poles, and
   nonzero sensitivity at distances 1e-7 and 1e-10 rad from a pole.

2. **Input validation was not a complete transaction boundary.**
   A vector containing the finite Python integer 10**1000 raised OverflowError
   before the operational result handling in both references. ESKF20 validated
   a converted temporary for angles/time but stored the original objects; a
   numeric string could survive construction and later trigger TypeError in
   trigonometry. InEKF accepted a length-one time array, and both models retained
   zero-dimensional array aliases for scalar fields. Mutating those arrays
   changed a frozen state. ESKF20 also admitted array/complex timestamps by
   equality, and InEKF's unsupported-kind branch evaluated array truth outside
   its exception boundary. Finally, finite corrupt rotation/covariance entries
   overflowed during validation and escaped as RuntimeWarning under the suite's
   existing warnings-as-errors configuration.
   The shared validator now requires real numeric scalar shape (), stores a
   copied Python float, and converts unrepresentable array values to ValueError.
   Operational boundaries normalize times, dt, gates and field strength before
   use. Labels are actual strings. A mathematically necessary rotation-entry
   bound precedes its products, and covariance-symmetry overflow rejects.
   Original orthogonality/SPD/symmetry tolerances are unchanged. Constructors
   reject; operational failures preserve the original state object and bytes.

Strings, booleans, complex scalars and length-one vectors are deliberately not
scalar inputs. Ordinary numeric scalars and zero-dimensional real numeric arrays
remain supported. The tests cover normal and rejection paths. This is not a
promise to handle arbitrary user-defined Python objects or resource exhaustion.

## Independent mathematical review

| Topic | Result and independent evidence |
| --- | --- |
| InEKF injection/reset | No new formula defect found. For eta=Exp(xi), right correction Exp(-delta) gives the derivative of Log(Exp(delta+e)Exp(-delta)): J_left(delta), including translation/rotation cross blocks. A new general matrix exp/log oracle avoids using the implementation's Lie_Exp/Lie_Log in the expected result. |
| ESKF20 installation convention | No sign/side defect found. R_true=R Exp(theta) and A_true=Exp(-gamma) A imply distinct recentering equations but the same Jr(delta) block for theta and gamma. Existing independent SO(3) finite differences cover full dense reset covariance. A new sensor-axis relabeling check transforms A, m and the full measurement covariance together and verifies the update commutes. |
| Magnetic I/D derivatives | Non-pole expressions agree with physical geometry. The inclination/declination coordinates are physical angles, not unit small-rotation columns; the 60-degree D sensitivity remains 0.5. Exact-pole evaluation was the defect above. |
| Process covariance | No new error found. A new time quadrature propagates twelve physical noise impulses through independently integrated nominal/perturbed trajectories with nonzero angular rate. Expected Q uses neither reference F/G nor its retraction or nominal propagation. Existing tests still cover full Phi, dense cross covariance, noise scaling and Joseph/reset. |
| Unobservability | The attitude/installation ambiguity remains; a new finite static world-yaw/D transformation leaves sensor measurements invariant and its tangent remains invisible through static dynamics and magnetic/position/velocity observation blocks. This is one gauge example, not a proof for all motions or an observability-constrained EKF implementation. |
| Magnetic sample coordinates | Sensor-axis relabeling and full covariance rotation are consistent. Correct sensor-frame and hard/soft-iron-only declarations remain required. Relabeling an already installation-corrected sample as raw sensor data cannot be detected by this mathematical oracle; metadata assertions do not prove external calibration provenance. |

No change to injection, reset, continuous dynamics, time integration, Joseph
form, correction limits, or ordinary NIS rejection was necessary. Production
sample/calibration/alignment contracts were not changed.

## Complete execution history

All commands were run from `D:\python_software\SilverStar` with installed Python
3.14.0, NumPy 2.4.0, SciPy 1.16.3 and pytest 9.1.1:

```powershell
python -B apps/SCG/experiments/navigation_0_1_3/verify.py audit_20261018_pre
python -B apps/SCG/experiments/navigation_0_1_3/verify.py audit_20261018_post01
python -B apps/SCG/experiments/navigation_0_1_3/verify.py audit_20261018_pre02
python -B apps/SCG/experiments/navigation_0_1_3/verify.py audit_20261018_final
```

| Retained run | Actual result | Interpretation |
| --- | --- | --- |
| [pre](evidence/audit_20261018_pre/pytest.log) | 21 failed, 131 passed | Nineteen failures exercise the initial pole/transaction defects. Two additional failures came from overly tight newly introduced roundoff checks; see below. The runner subsequently failed while printing already-saved evidence to the Windows GBK console; pytest exit 1 and complete run metadata had already been saved. |
| [post01](evidence/audit_20261018_post01/pytest.log) | 152 passed | Pole/scalar/overflow-conversion fixes and new roundoff checks. Runner uses explicit UTF-8 child output/console encoding; it still records complete failure output. |
| [pre02](evidence/audit_20261018_pre02/pytest.log) | 4 failed, 159 passed | Added corrupt-state probes reproduced rotation-multiplication and covariance-subtraction overflow escaping as warnings, in both models. Additional gate/strength scalar and normal zero-dimensional-input tests passed. |
| [final](evidence/audit_20261018_final/pytest.log) | 163 passed | One complete final run after all fixes; zero failures/skips. Existing 120 tests were neither edited nor removed. |

The first audit tests set 4e-16 for a gauge cancellation; accumulated SO(3) matrix
products produced 6.66e-16. The test now uses 32 float64 epsilons to account for
those operations. The sensor relabeling NIS differed by 1.69e-14 against a new
1e-14 tolerance due to subtracting nearly equal unit vectors before whitening.
Its new tolerance propagates a 32-epsilon residual error using the lower bound
on innovation eigenvalues supplied by measurement noise. State/covariance
invariance checks remain in place. These were audit-oracle numerical failures,
not repaired estimator defects. Initial tests and their failure logs are retained;
no preexisting test tolerance or safety expectation was weakened.

The initial console failure was `UnicodeEncodeError` for U+FFFD in the GBK output
stream after the subprocess output had been decoded with replacement. The first
log retains those replacement characters; later runs explicitly capture UTF-8.
The encoding repair does not change pytest exit status or test selection beyond
adding the independent audit file.

Each run directory contains its complete `pytest.log`, `run.json`, and inventory.
The records include command, environment, time, versions, exit, source commit
`7896c1d09a7f9138c41cdac35beef38347d94b78`, dirty status, hashes before/after,
and excluded validation. No hashed inputs changed during these runs. The final
result is not assembled from partial runs. The source was already dirty and the
experiment untracked; the commit alone does not identify it.

[Audit inventory](evidence/audit_20261018_v1/final_inventory.json) records original
source snapshots, final files, a baseline-to-final diff, historical-evidence
integrity checks, owner, purpose, paths, sizes and SHA-256. The report and final
inventory were written after the final execution; executed code/tests are checked
against that run's hashes. Prior validation reports and evidence remain historical
records. No cleanup or deletion was performed.

## Remaining limits and boundaries

- Local first-order covariance/reset and synthetic input assumptions remain.
  No NEES/NIS Monte Carlo consistency, all-motion identifiability, realistic weak
  prior behavior, recorded-data robustness, or disturbance rejection is proven.
  Near-pole conditioning and the pole chart's degeneracy remain; zero exact-pole
  sensitivity does not make a Gaussian angle model globally valid.
- Magnetic provenance is a caller contract. There is no production data adapter,
  delayed replay, genuine calibration verification, or online bias state in InEKF.
- Changes are confined to `apps/SCG/experiments/navigation_0_1_3`. Existing full
  verification reads catalog metadata and the preexisting FLP ESKF15 pure-math
  comparison only; no production ESKF15, GSHC, M9N/GNSS adapter, magnetic
  calibration or alignment file was changed. The suspended M9N boundary action
  was not resumed or retried. No hardware, firmware generation, dependency
  installation, project copy, build, publish or push occurred.
- Power-of-Ten, target static analysis, ARM linking, MCU timing/stack, hardware
  accuracy and flight qualification were not run and are not established.
  Acceptance outside these recorded host checks remains **NOT PROVEN**.

No execution blocker remains for this authorized offline audit.
