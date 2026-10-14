# NIS probability configuration (0.1.3 development)

Status: implemented; selected probability/migration/C regressions verified. Full acceptance remains blocked by the documented historical regression gaps and critical-contract manual review. Baseline: `682b7bccbb404b119a35e85c061495018fb26c42`.

NIS is raw `r^T S^-1 r`, not NIS divided by residual dimension. CDF coverage is the probability mass below a threshold under the chi-square reference model. A larger percentage produces a larger, more permissive threshold; it is not measurement correctness or navigation accuracy. Chi-square interpretation assumes a consistent Gaussian innovation and nonsingular S; this work does not prove those statistical assumptions. State dimensions 6 and 15 are never degrees of freedom.

| Owning implementation | Measurement/update | Residual df | Missing components | Gate comparisons |
|---|---|---:|---|---|
| KF6 C and FLP | GNSS horizontal position E,N | 2 | Whole horizontal group invalid/rejected, never silently reduced to df=1 | soft >; hard >= |
| KF6 C and FLP | GNSS vertical position U | 1 | Independent vertical group skipped/rejected | soft >; hard >= |
| KF6 C and FLP | GNSS horizontal velocity E,N | 2 | Whole horizontal group invalid/rejected | soft >; hard >= |
| KF6 C and FLP | GNSS vertical velocity U | 1 | Independent vertical group skipped/rejected | soft >; hard >= |
| KF6 C and FLP | Relative barometric height | 1 | Invalid observation/variance rejected | soft >; hard >= |
| KF6 parameter/storage API | 3D thresholds | 3 (reserved configuration) | Current product callers use 2+1 groups; no current joint 3D GNSS update | Preserve stored values; not evidence of a 3D runtime path |
| ESKF15 C and FLP | GNSS horizontal position or velocity E,N | 2 | Whole group physically invalid/rejected | soft >; hard > |
| ESKF15 C and FLP | GNSS vertical position or velocity U; relative barometric height | 1 | Whole group physically invalid/rejected | soft >; hard > |
| SF6 | GNSS/baro direct-current-state correction | none | Its existing validity/quality paths | No covariance or NIS; do not invent CDF controls |

The horizontal residual is updated jointly using its innovation covariance; horizontal and vertical groups are sequential updates, not a six-element combined innovation. ESKF15 supports only its five groups (EN position, U position, EN velocity, U velocity, baro); no gravity/ZUPT NIS group exists in this backend. Aggregate position/velocity diagnostic fields may describe multiple sequential groups and do not establish one joint df.

ESKF15's gate-input NIS uses S before robust R inflation. Its C implementation runs `Eskf_InnovationSolve` again after soft inflation and overwrites the reported outcome NIS with the raw quadratic form for the inflated S. FLP ESKF15 retains the gate-input NIS in its result. KF6 retains the gate-input NIS in both implementations. Therefore a recorded ESKF soft-weighted NIS and a FLP recomputed NIS need not represent the same stage. Probability controls describe the gate-input threshold; this task preserves that existing diagnostic difference and does not relabel recorded values as pre-gate evidence.

Source anchors: KF6 `NavigationKf_VectorNisCalculate`, `NavigationKf_GnssGroupRangeGet`, `NavigationKf_VectorSoftScaleApply`; ESKF15 `Eskf_MeasurementLinearize`, `Eskf_InnovationSolve`, `NavigationEskf_Update`; matching FLP KF6 filter and ESKF15 filter/replay. The 3D configuration remains explicitly labelled reserved.

## Configuration boundary

Probability conversion runs only when a configuration or declared residual dimension changes. Firmware receives finite float32 numeric thresholds, preserving defaults, comparisons, variance inflation and validity checks. An untouched legacy numeric threshold remains the authoritative value, including when its CDF rounds to 100%. An edited probability is a versioned primary input, with explicit df and fraction units; require 0 < p < 1. Soft must remain below hard after target rounding. Independent enable controls must be explicit fields, never probability=100 or infinite numeric sentinels.

Recorded logs and decoder packages are immutable. Recorded thresholds and new what-if thresholds remain separate. Historical data without declared NIS df must show numeric thresholds without fabricating a recorded probability; audited plugin residual dimensions describe a new recomputation configuration.

The shared reference contract and vectors are in `contracts/`; runtime conversion has no SciPy dependency. Verification may use installed SciPy as an independent primary implementation. Numerical basis: [NIST chi-square distribution](https://www.itl.nist.gov/div898/handbook/eda/section3/eda3666.htm), [SciPy chi2 CDF/PPF and survival functions](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2.html).

## Verification scope

Host/unit/GUI migrations, authoritative tail vectors, fresh generated ARM links, real static analysis, emitted Power of Ten and Host/source/artifact gates are recorded by exact configuration in the evidence report. No serial, DAP, flash, halt, reset or hardware writes are authorized in this task. No on-board, navigation-accuracy, WCET or flight qualification claim.

## User check

Run `.venv/Scripts/python.exe SCG.py`, then Navigation Configuration → Algorithm Parameters → Advanced. With KF6 or ESKF15 selected, edit the 2D soft CDF coverage to **95%** and hard coverage to **99.9%**. SCG commits spin-box edits with Enter. The read-only values must be **5.99146461** and **13.8155107**, both **df=2**. The generated C thresholds are float32 values 5.991464614868164 (`14babf40`, little-endian) and 13.815510749816895 (`550c5d41`). SCG and FLP edited-probability values have identical target bits.

Run `.venv/Scripts/python.exe FLP.py`, open a source log with its exact matching `.ssdecoder` through the normal log-opening flow, then Replay → KF6/ESKF15 → What-if parameters. KF6 places these controls in Consistency Gating; ESKF15 uses its Process Model parameter group. Apply the same percentages and compare the numeric values/df. Changing language and saving/reopening the project must retain the primary probabilities. Reset must restore the original numeric values, including their original precision. An untouched legacy numeric threshold is never round-tripped through a displayed percentage.

In Recorded Configuration, historical packages lacking a supported raw-NIS/fraction-unit/df declaration show the numeric threshold and unknown df without a fabricated CDF. Recorded thresholds are not replaced by What-if values. An untouched finite threshold of 10000 may display CDF=100%; it remains finite and enabled. Editing to 0% or 100% is rejected. Use the independent soft/hard checkboxes to disable either operation; validity, finite-value and soft/hard order requirements remain.

Actual widget offscreen captures and numerical readouts are retained in the task evidence. They do not replace native GUI or hardware verification. No serial, probe or board action is needed for these software checks.

## Regression boundaries

The pre-NIS `682b7bcc` and current KF6 kernel, with the same GCC 16.1.0, input fixture, generated numeric thresholds and actual shared headers, produce identical 1,109,911-byte (5005-line) default trajectories: SHA256 `4deb49b19d86bd4a8ade8fb35013fb3f9b1e5347bc0b7cde9ace5266ff9525cb`. The frozen expected `ad64bc875b4ec87f0bafdd65e868bb99822b79dfe79fc0debf13ec9484486aa1` remains unmatched; its recorded `b2e05fb` source commit is not resolvable in this repo. The golden was not changed. This scoped comparison proves the NIS change did not introduce that default-trajectory difference, not that the historical golden has been reconstructed.

Seven selected FLP tests still fail on missing KF6 process-model identity in their old synthetic inputs. They were reproduced with exact pre-NIS KF6 modules and the old navigation contract; no fallback/model guessing was added. The selected regression runs are not full-suite passes.

The old Host interface test assumed a 40-byte inertial increment for every estimator. The unchanged product header already appends two gyro/acceleration half-samples and quality flags for ESKF15, requiring offsets 40/64/88 and total size 96. The owning Host test now checks the exact conditional contracts; baseline/current compilation covers both estimator selections and legacy/auto memory modes. Product layout and memory bounds were not relaxed.

ESKF15's legacy memory placement overflows CCMRAM by 1664 bytes in the representative F407 configuration. The existing auto placement links successfully; its RAM spare 13504 bytes is yellow and CCM spare 15328 bytes is green. Spare bytes are not a stack, ISR-nesting, WCET or flight-safety proof. The failed legacy build is retained.

Power of Ten text/static gates retain the F Prime-inspired project adaptation and explicit critical-contract review **NOT PROVEN**. All changes remain first-party-owned; no density/allowlist/source-coverage exception or frozen release was altered. See the formal evidence report for exact run scopes, source/configuration hashes, tool versions, failures and final artifact hashes.
