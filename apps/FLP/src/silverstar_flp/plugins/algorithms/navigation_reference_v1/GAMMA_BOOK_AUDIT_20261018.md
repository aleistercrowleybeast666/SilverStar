# Book gamma definition audit — ESKF20 and InEKF20

Scope: the isolated float64 experiment only. The user chose the book's
magnetometer-to-IMU installation definition and retained mechanical IMU-to-vehicle
alignment, with the chosen installation axis kept as close to the nose-cone axis
as practical. No IMU-to-vehicle online state or physical alignment procedure is
added. This statement records intent, not a measurement of mechanical accuracy.

## Source and terminology

The parent verified the author's **first-edition revised final**, not the second
edition, of 《捷联惯导算法与组合导航原理》:
[author PDF](https://www.psins.org.cn/filedownload/775274), printed p. 218,
section 7.5.2, equation (7.5.10), and p. 219, section 7.5.3, equation (7.5.15).
The supplied transcription defines b_m as the magnetometer's orthogonal sensitive
axis frame and b as the IMU frame, with `C_b^bm ≈ I+[gamma_book]x` mapping **b
components to b_m components**. Its reverse has the minus sign. Gamma is their
small installation misalignment, not a vehicle attitude error.

The parent also verified the [author's dataset description](https://www.psins.org.cn/newsinfo/7829784.html),
which distinguishes prior gyroscope/accelerometer calibration inside the IMU
from IMU–magnetometer installation calibration. This worker's attempted reads of
both URLs timed out before reconnection. Source transcription/provenance above
comes from the parent; this audit does not claim independent PDF-page inspection
or a new direct reading of the dataset page. No source PDF or dataset was copied.

## Exact internal mapping; no global sign reversal

Use `B_inst` for the b→b_m component map and `A=B_inst^T` for b_m→b. This B_inst
is a rotation matrix, not the scalar magnetic field strength used elsewhere.
For a nominal installation, the implemented error at indices 15:18 is

```
delta_gamma_b = Log(B_nom^T B_true)
B_true = B_nom Exp(delta_gamma_b)
A_true = Exp(-delta_gamma_b) A_nom
```

The logarithm is a local SO(3) rotation vector, in IMU components. Internal code
calls this coordinate `gamma_b`; the model documents now explicitly label it
`delta_gamma_b` (residual). When B_nom=I, its first-order value and sign agree
with gamma_book. When both total installation rotations are small,
`gamma_book_true ≈ gamma_book_nom + delta_gamma_b`. There is no reason to
negate every gamma coordinate.

For finite test fixtures only, we explicitly define total rotation-vector
coordinates `g_nom=Log(B_nom)` and `g_true=Log(B_true)`. Then
`g_true=Log(Exp(g_nom)Exp(delta_gamma_b))`; it is generally not
`g_nom+delta_gamma_b`. Its local derivative is `Jr(g_nom)^-1`. This is our
declared matrix/logarithm chart, **not a finite Euler-angle convention supplied
by the book**. Ordered x/y/z factors used to construct known test matrices are
likewise explicit fixtures; their angle tuple is never substituted for gamma.

The sensor axes expressed in IMU coordinates are the columns of A. This passive
component map must not be conflated with actively rotating a vector while
holding its coordinate frame fixed. Signed-axis tests use literal matrix entries
and basis-vector components to establish the book's direction independently.

## Injection, reset and magnetic sensitivities

For an estimated residual correction c, both references use
`A_new=Exp(-c)A_nom`, hence `B_new=B_nom Exp(c)`. Holding the physical true
installation fixed, the new residual is
`Log(Exp(-c)Exp(delta_gamma_b))`. Its derivative at delta_gamma_b=c is Jr(c),
as already implemented. The prior document's equivalent expression
`-Log(Exp(-delta_gamma_b)Exp(c))` used the same local branch. No reset sign or
formula change is indicated by this algebra.

For raw sensor-frame m after hard/soft-iron-only correction and reference-strength
scaling, `m=B_true R_true^T h_true`. The experimental residual is
`z=R_nom A_nom m-h_nom`. Its installation block is
`H_delta_gamma=-[h]x R_nom`. The attitude blocks differ because the two filters
use different attitude errors: ESKF20 has `H_theta=+[h]x R_nom`; InEKF20 has
`H_phi=-[h]x R_nom`. That attitude-coordinate difference does not flip installation.

The last two coordinates remain physical `dI=I_nom-I_true` and
`dD=D_nom-D_true`, with exact derivatives -h_I and -h_D. They are not substituted
for attitude or installation coordinates. The book's additional five coordinates
are gamma(3) plus magnetic-inclination/declination error coordinates δη_x/δη_z;
the experiment's already documented physical-angle derivative adaptation is
retained, including the cos(I) dependence of declination sensitivity. No new
unverified identification of finite magnetic Euler errors with physical angles
is introduced. Exact-pole evaluation and the earlier audit fixes remain intact.

Distinct state variables do not imply independent information from one magnetic
vector: the instantaneous magnetic H still has rank two. Individual retraction
tests distinguish R, A, I and D; full H finite differences verify all their
columns. Cross-covariance-mediated updates of several states are legitimate and
must not be mistaken for either state aliasing or a proof of identifiability.

## Fixed installation and residual correction: apply each factor once

The supported input stays in the original magnetic sensor frame. Initialize
A_nom with a known fixed sensor-to-IMU rotation A0, if available; subsequent
residual corrections update that total nominal matrix. R_nom A_nom m then applies
the known installation exactly once. If m has already been premultiplied by A0,
also multiplying by the same A0 in A_nom double-compensates it. A residual-only
input path would need a separately specified frame/interface and is not added.
The existing body-frame/installation-calibrated labels remain rejected. A caller
can mislabel data, so metadata checks are not real calibration-provenance proof.

## Review finding and executable checks

The initial review found a **documentation ambiguity**, not an established
arithmetic defect: a bare gamma label could be read as the book's total small
installation angle even with nonzero nominal installation. The mapping above
resolves that ambiguity. Estimator implementation changes are not presumed
necessary; independent tests decide whether the current equations satisfy it.

`test_gamma_book.py` adds literal signed-axis component fixtures, explicitly
constructed combined rotations, nonzero nominal installation, corrected zero
residual, wrong-sign/Euler-tuple/naive-subtraction counterexamples, one-time fixed
installation, independent magnetic H finite differences, installation reset from
book-direction recentering, and separate injections of attitude/A/I/D. The
existing full experiment suite is also run. Exact results and before/after hashes
are recorded in this task's evidence after execution; no old 250-pass result
substitutes for this audit.

The earlier execution disconnect was resolved by a read-only recovery check:
the baseline inventory and four snapshots existed; the new test did not exist;
the runner was unchanged. All 23 baseline-file hashes matched. This established
that no partial test/runner write needed replacement or rollback.

## Executed result and before/after conclusion

The single complete post-reconnection run was:

```
python -B apps/SCG/experiments/navigation_0_1_3/verify.py gamma_book_20261018_run01
```

It started at 2026-10-18 12:26:46.349790 UTC and exited 0: **299 passed,
0 failed, 0 skipped**, including the existing 250 cases and 49 new cases.
Pytest reported 18.01 s; the runner's elapsed time was 20.1250507 s. The new
tests passed on their first executed run; no estimator formula, tolerance or
old test was changed to obtain this result. The earlier disconnect prevented a
write attempt and was not a mathematical test failure.

| Subject | Before this audit | After this audit |
| --- | --- | --- |
| Gamma naming | Bare gamma could suggest the total book angle even at nonzero nominal installation | Explicit local `delta_gamma_b`, its book-direction map and finite-chart limits |
| Nominal A, injection, reset, H | Existing mutually consistent formulas | Same formulas, independently checked by signed fixtures and finite differences |
| Fixed installation | A already represented the total sensor-to-IMU rotation | Documented and tested one-time application; no new input path |
| Attitude, installation, inclination and declination | Distinct stored quantities | Independent injection tests confirm separation; instantaneous rank two is retained |
| IMU-to-vehicle alignment | Mechanical installation | Still mechanical; no added online states or accuracy claim |

The examined scope therefore contains a corrected **documentation ambiguity**;
this audit did **not** find an arithmetic/sign/reset/H defect requiring an
estimator change. All five pre-existing estimator/shared-math Python files and
all six pre-existing test files remain byte-identical to the audit baseline.
Only three model/candidate documents and the test runner changed among the 23
baseline files; the new files are this report and `test_gamma_book.py`.

The recorded environment was Python 3.14.0, NumPy 2.4.0, SciPy 1.16.3 and
pytest 9.1.1. The source commit was
`7896c1d09a7f9138c41cdac35beef38347d94b78`, with a dirty workspace; that commit
alone does not identify the executed source. The run records exact source hashes
before and after execution and reports no changes during execution. Final
inventory checks match every current experiment Python/configuration file to
that executed source. This report's result section was completed after the run.

Retained evidence:

- `evidence/gamma_book_20261018_run01/pytest.log`: complete 299-case output.
- `evidence/gamma_book_20261018_run01/run.json`: command, environment, versions,
  commit, dirty status, source hashes and exit code.
- `evidence/gamma_book_20261018_v1/baseline_inventory.json` and `source_before/`:
  original identities and four small snapshots.
- `evidence/gamma_book_20261018_v1/changes.diff` and `final_inventory.json`:
  exact baseline edits, preservation checks and final deliverable identities.

The result is limited to this isolated host mathematical experiment. Actual
sensor frame/calibration provenance, mechanical alignment accuracy, general
identifiability, noisy recorded-data performance and hardware performance remain
NOT PROVEN. No C/firmware port, ARM build, Power-of-Ten acceptance or hardware
qualification is claimed. Production selection/generation remains unchanged.
The suspended M9N/GNSS work and its regressions were not resumed, and no GSHC,
production alignment/calibration, logs or protocol implementation was changed.
No cleanup, download, hardware operation or push occurred. Execution is restored;
there is no remaining execution blocker for this completed audit.
