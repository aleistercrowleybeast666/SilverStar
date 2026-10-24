# InEKF15 / InEKF20 host reference contract — 2026-10-18

Both names count **error degrees of freedom**, not redundant nominal matrix or
quaternion components. These are experimental, bias-augmented invariant EKFs,
not iterated EKFs. The existing nine-dimensional InEKF and conventional ESKF20
remain separate references. No firmware, public ID, plugin, GUI, production
parameter, decoder or generation path is introduced.

## Model selection and original sources

Hartley et al., [Contact-Aided Invariant Extended Kalman Filtering for Robot
State Estimation, arXiv:1904.09251v2](https://arxiv.org/html/1904.09251v2),
sections 7 and 10, treats IMU biases as Euclidean parameters alongside the group
state and calls the resulting model an imperfect InEKF. The left-invariant
formulation is appropriate to world-frame position observations. Its equation
(34), with contact states removed, supplies the bias coupling pattern used here.
We retain the existing experiment's estimate-minus-true convention and derive
all observation and reset signs for that convention.

Barrau and Bonnabel, [The Invariant Extended Kalman filter as a stable observer,
arXiv:1410.1465v4](https://arxiv.org/html/1410.1465v4), sections 2–3, relates the
group-affine condition to autonomous error and exact log-linear dynamics.
Those conclusions require that condition; they do not automatically transfer
to a bias-augmented product-state filter.

Both original-author sources were opened on 2026-10-18. No external code or
dependency was downloaded. We use the conventional imperfect augmentation
described above, not a newly invented equivariant group, bias removal, or an
ESKF relabeling. We make no universal impossibility claim about other group
constructions or other observers. All equations below specify this implementation
and its independently tested local approximation.

| Property | InEKF15 | InEKF20 |
| --- | --- | --- |
| Navigation error invariant under common left multiplication of true/estimated X | Exact algebraic identity | Same navigation identity |
| Joint SE₂(3) navigation retraction and Lie reset | Retained, including translation/rotation cross blocks | Retained, plus installation reset |
| Navigation-state independence of first-order process F | F does not depend on R, v, p; it does depend on estimated biases through corrected IMU input | Same F with five constant rows/columns |
| Full augmented dynamics group-affine on the simple product used here | False: explicit counterexample tested | Not claimed; inherits the bias counterexample |
| Finite-error exact log-linearity with unknown bias errors | False: explicit counterexample tested | Not claimed |
| Known equal biases, deterministic nine-state subsystem | Previous exact log-linear property retained | Same restricted subsystem |
| State-independent position/velocity H in invariant coordinates | Yes, co-timed 3D world observations at IMU origin | Yes |
| State-independent magnetic H / whole-filter world-frame equivariance | No magnetic observation in this stage | Not claimed: H depends on R, I, D; additive physical angle errors do not furnish a general world-rotation invariant parameterization |
| Universal convergence, observability or superior performance | Not established | Not established |

## Fifteen-dimensional coordinates

Let `X=[R v p; 0 1 0; 0 0 1]`, with R mapping IMU frame b to ENU n.
Define `eta=X_true^-1 X_hat`, `xi=Log(eta)=[phi,nu,rho]`, and
`zeta_g=bg_hat-bg_true`, `zeta_a=ba_hat-ba_true`.
The complete error order is `[phi3,nu3,rho3,zeta_g3,zeta_a3]`.
The nominal state contains X and the two IMU-frame biases. All initial nominal
values and the entire SPD 15x15 covariance must be supplied explicitly.
Units are rad, m/s, m, rad/s, m/s², respectively.

For corrected inputs `w=wm-bg_hat`, `a=am-ba_hat`, nominal dynamics are
`Rdot=R[w]x`, `vdot=Ra+g`, `pdot=v`; nominal biases hold constant.
The first-order continuous error matrix, in 3x3 blocks, is

```
F15 = [ -[w]x     0       0      -I      0
        -[a]x   -[w]x     0       0     -I
           0      I    -[w]x     0      0
           0      0       0       0      0
           0      0       0       0      0 ]
```

This is not a finite-error law. For example the exact rotation-error equation
contains the product of gyro bias error and the rotation error; those mixed
terms are absent from this first-order F. F is constant over one held-input
interval because estimated biases hold constant, even though nominal R evolves.

Noise amplitude-density order is `[gyro3, accel3, gyro-bias-RW3, accel-bias-RW3]`.
`G_phi,gyro=I`, `G_nu,accel=I`, `G_zeta_g,bgRW=-I`, `G_zeta_a,baRW=-I`;
all other blocks are zero. True biases follow additive independent random walks.
The twelve input densities are squared exactly once. No additional source
cross-noise covariance or post-initialization noise adaptation is implied.

Nominal propagation reuses the audited exact held-input nine-state flow.
`Phi=exp(F dt)` and Qd use a 30x30 Van Loan exponential. This is exact for
the frozen **linearized** SDE, not for the nonlinear biased error distribution.
`Pminus=Phi P Phi^T+Qd` retains all 225 entries. dt is explicitly in (0,0.02] s.

For position/velocity y in the world frame, residual is
`r=R_hat^T (x_hat-y)`. H selects rho for position and nu for velocity; Rnoise
is rotated from world into IMU coordinates. Cholesky solves compute gain/NIS.
Correction is `delta=K r`, followed by
`X_hat <- X_hat Exp(-delta_xi)`, `bias_hat <- bias_hat-delta_zeta`.
Velocity/position corrections use the joint group exponential, not independent
Euclidean addition. The posterior covariance first uses Joseph form, then
`J=diag(J_left_SE23(delta_xi),I6)`, with the full transform `J Ppost J^T`.
The reset follows `xi_new=Log(Exp(xi)Exp(-delta_xi))`; bias reset is additive.

## Twenty-dimensional magnetic extension

Append `[gamma_b3,dI,dD]`, giving the full order
`[phi,nu,rho,zeta_g,zeta_a,gamma_b,dI,dD]`. A maps magnetometer sensor frame bm
into IMU frame b. The physical model and signs match the independently audited
[ESKF20 contract](ESKF20_MODEL.md):

```
A_true = Exp(-gamma_b) A_hat
dI = I_hat-I_true       (inclination positive downward)
dD = D_hat-D_true       (declination positive east of north)
h_n = [sin(D)cos(I), cos(D)cos(I), -sin(I)]
```

The extra five nominal/error quantities are constant during prediction and have
zero driving noise. `F20=diag(F15,0_5)`, `Phi20=diag(Phi15,I5)`,
`Q20=diag(Q15,0_5)`, but P is a complete 20x20 matrix, never block-separated.
Navigation propagation therefore evolves its cross covariance with the five
additional quantities. The constant-parameter assumption is explicit, not an
identifiability assertion or a model of magnetic disturbance.

Input is **hard/soft-iron-only corrected sensor-frame microtesla**, plus full SPD
sensor covariance and explicit reference field strength B. Divide by B and B²,
respectively; do not normalize each measured vector by its own magnitude.
Samples must declare `magnetometer_sensor` / `hard_soft_iron_only` and the exact
current timestamp. The production body-frame, installation-calibrated magnetic
sample cannot be used directly; metadata supplied by a caller is not proof of
real calibration provenance. No adapter or calibration implementation is added.

For `m=A_true^T R_true^T h_true + noise` after B scaling, residual is
`z=R_hat A_hat m-h_hat`. Nonzero H blocks for this invariant coordinate order:

```
H_phi   = -[h]x R_hat
H_gamma = -[h]x R_hat
H_I     = -[-sinD sinI, -cosD sinI, -cosI]
H_D     = -[ cosD cosI, -sinD cosI, 0]
```

The attitude sign is opposite the conventional ESKF20 H because
`theta_ESKF=-phi` to first order. These physical I/D derivatives are the
previous implementation derivation, **not the textbook's field-frame small-angle
columns**. We import the audited `Magnetic_Field` without modifying it: exact
poles have cos(I)=0 and exactly zero D sensitivity; nearby inclinations retain
their small physical sensitivity. I=60 degrees still gives `||h_D||=0.5`.

Apply the same group/bias injection, then `A<-Exp(-delta_gamma)A`,
`I<-I-delta_I`, `D<-D-delta_D`. The reset is
`diag(J_left_SE23(delta_xi),I6,J_right_SO3(delta_gamma),I2)`; the entire
400-entry covariance is transformed, including every mixed block.
World magnetic noise is rotated by `R_hat A_hat`. Position/velocity updates use
the same invariant residual as stage 15 and may update the added parameters
through genuine prior cross covariance.

## Common coordinates and interpretation of tests

The first-order transform into the project's ESKF error coordinates is
`dp_n=-R rho`, `dv_n=-R nu`, `dtheta_b=-phi`,
`dbg_true-hat=-zeta_g`, `dba_true-hat=-zeta_a`, with gamma/dI/dD unchanged.
Covariance comparisons use `P_ESKF=T P_InEKF T^T`, including all mixed terms.
The conventional reference's accel/gyro density ordering is explicitly permuted.
Matched propagation and H agree in those common coordinates. Finite corrections
are not identical: group translation retraction produces a measured second-order
mean difference. No comparison claims one model has superior accuracy.

Local numerical observability tests stack `H_k Phi_k:0` at the synthetic truth,
using radians/metres/seconds and a relative singular threshold of 1e-8.
They are finite-window, first-order, unwhitened numerical tests in those declared
units, not unit-independent conditioning bounds or nonlinear global proofs.
The tested 13-second rotating/accelerating window with co-timed position/velocity
observations (and magnetics for stage 20) has full numerical rank and reduces
all six bias errors. Static windows are rank-deficient. The synthetic samples
are noise-free realizations with explicit positive assumed measurement/noise
covariances; these are deterministic regressions, not NEES/NIS Monte Carlo.
Missing data never synthesizes an observation. With an initially independent
extra block and no magnetic observations, the installation/field parameters
and their covariance remain unchanged. Correlated priors can legitimately share
information, which must not be confused with new sensor observability.

## Failure and acceptance boundaries

Initial states are validated, copied and read-only; scalar fields are immutable
Python floats. Operational rejection preserves the caller's original state.
The audited scalar/rotation/covariance validators are reused unchanged. Invalid
shapes, nonfinite/complex/unrepresentable numbers, scalar aliases, wrong labels,
timestamps, covariance or dt reject. Optional gates must be finite and positive.
Rotation corrections over 0.35 rad and I injections outside [-pi/2,pi/2] reject;
D remains an unwrapped finite angle. Overflow, Cholesky or reset failure returns
NUMERIC_ERROR without partial publication. No jitter, PSD clipping or silent
repair is introduced. Missing-data operations still validate stored state.

The default gate remains caller-explicit; no real sensor quality policy is
invented. Out-of-sequence fusion, lever arms, sensor identity switching,
disturbance detection, online hard/soft-iron calibration, initialization and
real-data replay are absent. Neither augmented reference has a proven global
Gaussian chart, statistical consistency, hardware accuracy or flight readiness.
Power-of-Ten project acceptance, C static analysis, ARM link, stack and timing
proof remain **NOT PROVEN** and are not claimed by these host tests.
