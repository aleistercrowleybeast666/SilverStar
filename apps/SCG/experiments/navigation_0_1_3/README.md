# Invariant EKF mathematical reference, 0.1.3 experiment

Status: **HOST REFERENCE ONLY; NOT SELECTABLE; NOT GENERATABLE**.
Revision 1 implements a bias-free, nine-dimensional left-invariant error filter
on SE₂(3). It is not an ESKF15 rename, an iterated EKF, an ESKF20, or a firmware
backend. No production files or algorithm registry are changed.

The separately authorized twenty-error-state ESKF host reference is documented
in [ESKF20_MODEL.md](ESKF20_MODEL.md); it keeps ESKF15's right-local error convention
and adds magnetometer installation and field angles. The sections below continue
to describe only the nine-error-state InEKF. Both remain isolated and unavailable
to production selection/generation. The runner now verifies both models and their
shared catalog isolation; historical run03 covered InEKF only.

The 2026-10-18 extension adds [InEKF15 and InEKF20](INEKF_AUGMENTED_MODEL.md)
after the [independent audit](INDEPENDENT_AUDIT_20261018.md). These are imperfect,
bias-augmented invariant references; their complete systems do not inherit the
bias-free model's strict group-affine/log-linear claim. The audited nine-state
and ESKF20 implementations/tests remain intact. Their stage results, full
cross-covariance checks and limitations are in INEKF_AUGMENTED_VALIDATION.md.

The 2026-10-18 independent audit adds boundary and symmetry checks and fixes
exact-pole magnetic sensitivity and malformed-input transactions. See
[INDEPENDENT_AUDIT_20261018.md](INDEPENDENT_AUDIT_20261018.md) for findings,
failed runs, the final executed scope, and retained source/evidence inventories.

## Primary sources checked on 2026-10-17

- Barrau and Bonnabel, *The invariant extended Kalman filter as a stable observer*,
  [arXiv:1410.1465v4](https://arxiv.org/html/1410.1465v4), sections 2–3, 5 and
  appendix A.2: group-affine criterion, invariant error and SE₂(3).
- Hartley, Ghaffari, Eustice and Grizzle, *Contact-Aided Invariant Extended Kalman
  Filtering for Robot State Estimation*,
  [arXiv:1904.09251v2](https://arxiv.org/html/1904.09251v2), sections 10, 12 and
  appendix A: the left-invariant formulation suits world-frame position outputs.
- Barrau and Bonnabel, *The Geometry of Navigation Problems*,
  [arXiv:2201.04426v4](https://arxiv.org/html/2201.04426v4): bias/body-vector
  augmentation requires a separately justified group construction.

These are original author papers, not third-party tutorials. This implementation
was written independently; no upstream implementation, dataset or package was
downloaded. Installed NumPy/SciPy are host dependencies only. The papers' stability
conditions are not a stability, observability or flight qualification of this code.

## Frozen mathematical conventions

Column vectors; R maps body to navigation ENU. Gravity is an explicit navigation
vector (the tests use [0,0,-9.78] m/s²). Inputs are calibrated body angular rate
in rad/s and specific force in m/s², held constant per interval. No coning/sculling
or attitude feedback is applied before or inside this reference. This ZOH input
contract is different from the production two-half-mean ESKF15 input contract.

The group and its algebra coordinates are

```text
X = [ R v p ]       xi = [phi, nu, rho], each a 3-vector
    [ 0 1 0 ]       xi^ = [phi× nu rho; 0 0 0; 0 0 0]
    [ 0 0 1 ]       Exp(xi) = [Exp(phi×), J_l(phi)nu, J_l(phi)rho; ...]
```

v is ENU velocity (m/s), p is ENU position (m). The error is
`eta = X_true^-1 X_estimate = Exp(xi)`, **estimate minus truth** at first order.
It is invariant under simultaneous left multiplication. P is the full 9×9
covariance of these local log coordinates, ordered `[phi, nu, rho]`; it is not
the production `[dp,dv,dtheta,dbg,dba]` covariance. The group inverse, adjoint,
and exponential couple translation and rotation.

Our derivation from `Rdot=R omega×`, `vdot=R a+g`, `pdot=v` gives

```text
        [ -omega×       0        0     ]
A_L =   [ -a×          -omega×   0     ]
        [  0            I       -omega×]
```

For the ideal deterministic model, `eta_dot=f(eta)-f(I)eta` and
`xi_dot=A_L xi`. The state-independent A and the finite-error log-linear
identity are tested, not just an ESKF small-error approximation. Gravity cancels
from A_L. Noise makes the error equations first-order approximations.

Nominal propagation uses an augmented matrix exponential to integrate held
omega and specific force exactly up to floating-point roundoff. `Phi=exp(A_L dt)`;
the 18×18 block exponential evaluates
`Qd=integral(exp(A_L s) Qc exp(A_L^T s), s=0..dt)` without Euler approximation.
Independent gyro/accelerometer amplitude densities are explicit six-element
inputs, squared exactly once: `Qc=diag(sigma_g²,sigma_a²,0₃)`.
Their units are rad/s/√Hz and m/s²/√Hz. Correlated input noise is unsupported.

Only co-timed complete 3D position or velocity observations at the IMU origin
are supported. For kind position, `r=Rhat^T(phat-y)` and `H=[0,0,I]`;
for velocity, `r=Rhat^T(vhat-y)` and `H=[0,I,0]`. Transform the supplied full
world-frame measurement covariance with `Rhat^T R_measurement Rhat`.
Compute NIS and K using Cholesky solves, then `delta=K r` and
`Xhat_new=Xhat Exp(-delta)`. There is one correction, no iterative loop.

Covariance uses Joseph's form followed by the recentering derivative:

```text
Pj = (I-KH) P (I-KH)^T + K R_body K^T
eta_new = Exp(xi) Exp(-delta)
J_reset = d Log(Exp(delta+e) Exp(-delta))/de at e=0 = J_l_SE23(delta)
P_new = J_reset Pj J_reset^T
```

This recentering is an explicit local uncertainty approximation in this reference,
not a claim of exact nonlinear Bayesian covariance. The complete 9×9 Jacobian,
including translation/rotation cross terms, is checked by finite differences.
It is evaluated as `integral(exp(s ad_delta),s=0..1)`.

## Domain, failure and unsupported cases

- Float64 host implementation; `0 < dt <= 0.02` seconds. Time must advance;
  observations must match the state's explicit time exactly. No delayed replay.
- Rotation matrices must already be SO(3); no silent projection of invalid input.
  Log and correction chart reject angles within 1e-7 rad of pi or beyond.
- Initial/state and measurement covariance must be finite, symmetric and strictly
  positive definite. Zero process densities are permitted. Numerical symmetry
  averaging only removes roundoff; no clipping, jitter or covariance repair.
- API results distinguish OK, invalid input, numerical failure, NIS rejection and
  unsupported observation. Failed steps retain the original state object; arrays
  are copied and read-only on construction. Constructors/helpers raise ValueError
  for malformed mathematical objects. No READY/success placeholder exists.
- Times, time steps, gates and magnetic angles/strengths require finite real
  numeric scalars. Zero-dimensional numeric NumPy arrays are copied to Python
  floats; vectors (including length one), complex values, strings and booleans
  are rejected. Float64 conversion overflow is an invalid input, and validation
  of corrupt rotation/covariance data cannot escape as a floating-point warning.
- Optional NIS gate is explicitly supplied by the caller; None disables it for
  the synthetic experiment. It is not the production admission/quality policy.
- Online biases, lever arms, magnetic/barometric observation models, time offset,
  clock/identity/source changes, lifecycle recovery, log replay, and hardware
  calibration/alignment are **not implemented**. Bias-compensated synthetic input
  is an assumption, not proof that real sensor bias is known or observable.
- A future bias-augmented model needs its own error dynamics, observability and
  group-affine assessment. This result makes no strict group-affine claim about it.

## Isolation and verification

This directory is outside `plugins/builtin`, `plugins/installed`, and Python
package discovery under `src`. It contains no `plugin.json`, algorithm ID enum,
registry entry, source-graph contribution, decoder or generated firmware payload.
The candidate identifiers in isolation tests are rejection probes, not assigned IDs.

`test_mathematics.py` checks maps, group identities, independent ODE integration,
finite differences, finite-error log-linearity, noise quadrature, frame equivariance,
analytic turning motion, full-P SPD and transactional invalid-input rejection.
`test_isolation.py` uses actual SCG catalog, validation and source-graph functions;
it reads manifests but never compiles/executes adapter payloads. Its metadata-only
models have all devices removed; these are not complete flight build validations.
They cover the existing None/SF6/KF6/ESKF15 graph choices and reject manually
entered ESKF20/InEKF/IEKF IDs. No paused GNSS/M9N test or adapter is executed.
`test_independent_audit.py` adds physical noise-impulse quadrature for rotating
ESKF20 covariance, general matrix exp/log InEKF reset, sensor-axis relabeling,
the static yaw/declination gauge, exact/near poles and malformed scalar/overflow
transactions. Its scope remains local synthetic mathematics, not global
observability or a statistical consistency proof.

Run from the repository root with existing dependencies:

```powershell
python -B apps/SCG/experiments/navigation_0_1_3/verify.py my_new_run
```

The explicit pytest config collects only this directory; no SCG test-suite Qt
fixture or default `.work/pytest` destination is used. The runner disables bytecode,
pytest caching and plugin autoload. It retains a small log and JSON evidence under
`evidence/<run-name>/`, refuses overwrite, and records purpose/owner/hashes/commands,
tool versions, source snapshot and all failures/skips. No cleanup is performed.

Passing this suite establishes only its recorded host mathematical and isolation
scope. It does not establish equality to ESKF15, statistical consistency (NEES/NIS
Monte Carlo), all-motion observability, robustness to real recordings, firmware
resource bounds, Power-of-Ten acceptance, analyzer/ARM results, MCU timing, stack
safety or hardware accuracy. Those remain unimplemented/unverified. New firmware
backend and selection enablement require separately authorized work and validation.
