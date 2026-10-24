# ESKF20 host reference, revision 1 — 2026-10-17

Owner: navigation_0_1_3 algorithm experiment. This directory alone contains the
implementation, tests and retained evidence. No plugin registration, firmware,
production interface, log/decoder, calibration or alignment implementation is
changed. ESKF20 remains unselectable and ungeneratable through the current catalog.
The [2026-10-18 independent audit](INDEPENDENT_AUDIT_20261018.md) records later
boundary fixes and added mathematical counterexamples without changing these
error-coordinate conventions or adding a production entry point.

## Authority and provenance

The user selected magnetometer-to-IMU installation deviation (3), magnetic
inclination (1), and declination (1), through the parent task's verified source
transcription. Source: Yan Gongmin, 《捷联惯导算法与组合导航原理》, first-edition revised
final, printed pp. 216–220, sections 7.5.1–7.5.3, and section 4.2.2 p. 90.
[Author download directory](https://www.psins.org.cn/zlxz),
[author PDF endpoint](https://www.psins.org.cn/filedownload/775274).
The parent verified these pages. This worker's web PDF retrieval failed; it does
not claim independent page-image inspection. The user's separate coarse-alignment
images belong to another edition and do not establish this magnetic model.
No textbook text, code or downloaded PDF is copied into the repository.

The book's state convention is not copied unchanged. Its attitude ordering and
left navigation-frame error differ from the project's right IMU-frame error.
Its small field-frame Euler-angle approximation is also distinct from exact
derivatives with respect to physical inclination/declination. The equations below
are this implementation's derivation, independently checked by physical finite
differences; they must not be attributed verbatim to the textbook.

## State, frames and injection

`C^a_b` maps b coordinates into a. `n` is ENU, `b` is the IMU frame, `bm` is the
magnetometer sensor frame. `R=C^n_b`, `A=C^b_bm`. All angles/rates are radians.
The nominal state stores p, v, R, gyro bias, accelerometer bias, A, I, D. Rotations
use 3x3 SO(3) matrices in this float64 oracle; production ESKF15's nominal
quaternion is not enlarged or changed. No extra degree of freedom is counted
from redundant rotation storage.

| Error coordinates | Meaning and true/nominal relation | Units | Injection |
| --- | --- | --- | --- |
| 0:3 dp | p_true = p_nom + dp, ENU | m | p += dp_hat |
| 3:6 dv | v_true = v_nom + dv, ENU | m/s | v += dv_hat |
| 6:9 dtheta | R_true = R_nom Exp(dtheta), IMU local | rad | R *= Exp(dtheta_hat) |
| 9:12 dbg | bg_true = bg_nom + dbg, IMU | rad/s | bg += dbg_hat |
| 12:15 dba | ba_true = ba_nom + dba, IMU | m/s² | ba += dba_hat |
| 15:18 delta_gamma_b | A_true = Exp(-delta_gamma_b) A_nom, residual in IMU components | rad | A = Exp(-delta_gamma_hat) A |
| 18 dI | I_nom - I_true, downward positive inclination | rad | I -= dI_hat |
| 19 dD | D_nom - D_true, east-of-north positive declination | rad | D -= dD_hat |

Book navigation-frame phi corresponds to `R_nom dtheta_b` to first order.
The selected installation is **magnetometer relative to IMU**, not IMU relative
to vehicle. All 400 covariance entries are retained. Initial state, full SPD P,
noise densities, gravity, installation, magnetic angles and reference strength
are mandatory caller inputs; no production defaults or inferred priors exist.

### Mapping to the book's gamma

The book's gamma is the small magnetometer-to-IMU installation misalignment,
defined by the **component map** `B_inst=C_b^bm ≈ I+[gamma_book]x`; its reverse
is `A=C_bm^b ≈ I-[gamma_book]x` (first-edition revised final, printed p. 218,
section 7.5.2, equation 7.5.10). It does not describe IMU-to-vehicle alignment.

The code's error-coordinate label `gamma_b` denotes the local **residual**
`delta_gamma_b=Log(B_nom^T B_true)`, where `B_nom=A_nom^T`. Thus
`B_true=B_nom Exp(delta_gamma_b)` and `A_true=Exp(-delta_gamma_b) A_nom`.
At identity nominal installation, delta_gamma_b agrees with gamma_book to first
order, with the same sign. If both total installations are small,
`gamma_book_true ≈ gamma_book_nom + delta_gamma_b`; at finite nonzero nominal
installation, simple subtraction of total rotation vectors is not this residual.
No unexplained global sign flip or finite Euler sequence is implied.

A_nom is the total nominal sensor-to-IMU component map, including a known fixed
installation once and its accumulated estimated correction. Input remains in
the original magnetic sensor frame. Do not premultiply the input by that fixed
installation and then apply the same factor through A_nom again. IMU-to-vehicle
orientation remains the user's mechanical installation/alignment convention;
there is no additional online state. See [the definition audit](GAMMA_BOOK_AUDIT_20261018.md)
for finite-map examples, independent tests and source qualifications.

## Dynamics and reset

Nominal strapdown equations: pdot=v, vdot=R(am-ba)+g, Rdot=R[wm-bg]x;
both nominal biases, A, I, D are constant during prediction. The last five
error dynamics and their driving noise are zero. Gyro/accelerometer bias random
walks remain explicit inputs. F's top-left 15x15 exactly matches the existing
pure ESKF15 reference; all additional F blocks are zero:
`F_pv=I`, `F_vtheta=-R[a]x`, `F_vba=-R`,
`F_thetatheta=-[w]x`, `F_thetabg=-I`.

Noise amplitude-density order is accel(3), gyro(3), gyro-bias RW(3), accel-bias
RW(3); square each once to obtain the spectral density. G has R in v/accel,
-I in theta/gyro and I in the two bias/RW blocks. As in the existing reference,
the accelerometer driving-noise sign convention is positive; independent white
noise is symmetric and there are no cross-source noise terms here.

Nominal propagation uses exact zero-order-held corrected IMU input and constant
ENU gravity. This reuses the isolated InEKF's nominal SE_2(3) flow, not its error
coordinates or covariance equations. The oracle integrates `Phi_dot=F(t)Phi`
and `Q_dot=F(t)Q+QF(t)^T+G(t)QcG(t)^T` along R(t), via SciPy DOP853 with
rtol=2e-11, atol=2e-13. dt must lie in (0,0.02] seconds. This is a numerical
host reference, not a bounded MCU integrator or parity claim for ESKF15's
two-sample coning/sculling and second-order covariance approximation.

Posterior P uses Joseph form before full reset `Pnew=J Preset J^T`.
The dtheta and delta_gamma_b reset blocks are both `Jr(delta)=integral_0^1 Exp(-s[delta]x)ds`;
other blocks are identity. They come from different equations:
`theta_new=Log(Exp(-delta_theta)Exp(theta))` and
`delta_gamma_new=Log(Exp(-delta_gamma_hat)Exp(delta_gamma_b))`.
The latter is the same principal-chart expression as the previously documented
`-Log(Exp(-delta_gamma_b)Exp(delta_gamma_hat))`; no reset formula was changed.
Finite differences check each complete 20x20 map and dense cross covariance.

## Magnetic observation and exact derivatives

`h^n(I,D)=[sin(D)cos(I), cos(D)cos(I), -sin(I)]`.
The input vector is a magnetometer-frame measurement after hard/soft-iron
correction only, in microtesla, with an explicitly supplied known reference
strength B. Divide vector by B and covariance by B². Do not normalize by the
observed sample norm: radial noise is allowed and the full 3D covariance is SPD.
This experiment does not estimate B, hard/soft-iron parameters or disturbances.

Physical measurement: `m^bm=A_true^T R_true^T h_true + noise` (after B scaling).
Residual: `z=R_nom A_nom m - h(I_nom,D_nom)`; `z≈H error + noise_n`.
The only nonzero H blocks are:

- `H_theta=[h]x R`, `H_delta_gamma=-[h]x R`;
- `H_I=-h_I`, where `h_I=[-sinD sinI,-cosD sinI,-cosI]`;
- `H_D=-h_D`, where `h_D=[cosD cosI,-sinD cosI,0]`.

These **exact magnetic-angle derivatives are implementation derivations**, not
the book's small field-frame rotation columns. In particular `||h_D||=|cosI|`:
at I=60 degrees it is 0.5, while the book's corresponding unit small-rotation
column has magnitude 1. Copying that column would double the local sensitivity.
The tests perturb all twenty coordinates, including all eight magnetic-sensitive
columns, with nonidentity R and nonzero nominal A.

Noise is rotated by `R_nom A_nom`. Synthetic co-timed position/velocity updates
at the IMU origin also exist, to test cross covariance; they have no device,
protocol or log adapter, and no lever arm, barometer or delayed-measurement model.

## Input boundary and observability limits

The production `SystemMagnetometerSample.magnetic_field_b_uT` is already required
to use the system body frame. `MAGNETOMETER_INTERFACE.md` also requires hard-iron,
soft-iron **and installation** calibration before its calibrated flag is set.
`SystemMagCalibration_VectorCorrect` applies a generic matrix to field-minus-bias.
Consequently this oracle cannot consume that interface directly: applying A
again could double-compensate installation. Input must explicitly declare
`frame=magnetometer_sensor`, `calibration=hard_soft_iron_only`, and a matching
timestamp. Existing body-frame/calibrated-production labels are rejected.
No current calibration flow is modified; a future distinct measurement contract
requires separate design and evidence with its owner.

One magnetic vector has instantaneous rank two. H_theta and H_delta_gamma have a
shared null direction; a repeated static vector does not identify individual
attitude, installation or field angles. At inclination ±pi/2, D has zero
sensitivity; near the poles it becomes poorly conditioned. Runtime diagnostics
report instantaneous H rank and D sensitivity only, not dynamic observability.
I stays in [-pi/2,pi/2]; an injection leaving this chart is rejected. D is an
unwrapped finite angle; wrapping would introduce an unnecessary reset seam.
Parameter convergence or declining covariance does not prove identifiability.
No trajectory-wide observability, consistency, accuracy or flight claim is made.
At the two exact chart endpoints, the field is evaluated with sin(I)=+/-1 and
cos(I)=0 exactly, including its angle derivatives. A library cos(pi/2) roundoff
residue must not create false D information through a large prior covariance.
No tolerance band snaps nearby I values to a pole. The polar chart is still
degenerate; this correction does not make D observable or remove the existing
out-of-chart correction rejection.

## Failures and experimental acceptance

State arrays are copied/read-only. Operational functions return a new state only
on success. Invalid shapes, complex/nonfinite values, non-SO(3) matrices,
non-SPD covariance, stale/future samples and wrong magnetic provenance reject
ordinary inputs. Numeric overflow, integration or Cholesky failure returns a
numeric failure. Optional positive NIS gating and a 0.35-rad attitude/installation
correction guard reject large corrections. Missing magnetics return NO_OBSERVATION;
prediction continues with no artificial magnetic observations. No jitter, PSD
clipping or silent coordinate repair is used. A rejection returns the exact
original state object, including when nominal computation preceded a later fault.
Scalar angles, times, time steps, field strength and gates must be finite real
numeric scalars. Accepted zero-dimensional NumPy values are copied to immutable
Python floats; strings, booleans, complex numbers and non-scalar arrays reject.
Unrepresentable vector values and overflow during stored-state validation also
reject before any numerical update, including with warnings treated as errors.

This host model is not Power-of-Ten acceptance, C analysis, ARM linking, stack
proof or hardware qualification. Production registration remains forbidden until
separately authorized and verified. No M9N/GNSS adapter or its suspended tests
are read for implementation, compiled, invoked or copied by this experiment.
