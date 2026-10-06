# KF6 split-operation and failed replay publication

This FLP-only correction starts at 45778d3. The owning firmware, SCG, GSHC,
SF6, project persistence, cache codecs, deletion and worker code are unchanged.

An original zero-delay combined GNSS operation at 500000 us is changed to
position delay 0 ms and velocity delay 270 ms. The synthetic estimator epoch
starts at 490000 us. Velocity resolves to 230000 us and receives HISTORY_MISS;
position remains at 500000 us and must still be attempted. Previously the first
rejection stopped both parts. Each split part now retains its own replay result,
attempt and commit status. INVALID, HISTORY_MISS and admission OVERFLOW continue
to the other part when the engine is not faulted. Epoch mismatch, discontinuity,
numeric failure, work limit, or a latched engine fault stop later insertion;
skipped parts have no replay result and are explicitly unattempted. An earlier
independently committed part remains distinguishable from a later failure.

FixedLagReplay.Insert clears last_outcome after unsuccessful replay. A position
accepted in a working clone followed by numeric velocity failure, or an incoming
accepted event followed by failure of a later historical event, has not committed
that working x/P. The original implementation retained a partial accepted outcome.
Faithful_Run now admits reporting outcomes only for committed insertions. Failed
transaction rows retain invalid group results and NaN effective variance; snapshot
group codes are not-attempted (5), and fatal aggregate results are NUMERIC_ERROR
(4). The existing diagnostic records add replay_result, operation_attempted and
committed; measurement_operations separately records each actual or skipped
insertion. Original ordinary finite NIS rejection remains an OK replay transaction
with a rejected measurement, never a fatal numeric fault.

Kf6_Create checks all configuration arrays and initial velocity after float32
conversion, including finite host values that overflow that conversion. The R
scale is likewise checked after conversion. Covariance repair checks finiteness
again after the unchanged symmetry arithmetic. Scalar barometer NIS that is
nonfinite is a numeric failure before x/P updates, rather than an ordinary gate
rejection. Valid values, parameter declarations, thresholds, revision selection
and rev2 process-noise arithmetic are unchanged. Direct helpers retain their
existing caller contracts: a failed covariance repair can leave its working
object modified; this patch does not promise rollback of every direct helper.
The fixed-lag engine discards its working filter and latches a fault. Event and
checkpoint bookkeeping is not promised to be rolled back on terminal failure.

Before correction, the initial 33-case regression file reported 28 failed,
5 passed in 1.17 s, exit 1. The full failure log and that exact test file are
retained. The first post-fix four-file targeted run passed 53 cases in 2.36 s.
Three further consumer checks cover barometer numeric/ordinary NIS results and
earlier independently committed position followed by velocity failure. The final
same four-file scope passed 56 cases in 2.57 s, exit 0. Its rev1/rev2 normal
state, full covariance and snapshot fingerprints exactly equal the pre-fix
fingerprints. The unchanged outage regression compares existing recorded C
reference vectors; it does not compile C or establish firmware qualification.

Commands use apps/FLP/.venv/Scripts/python.exe with PYTHONPATH set to
apps/FLP/src;apps/FLP and pytest -vv -s -p no:cacheprovider. The final files are
test_kf6_replay_failure_publication.py, test_fixed_lag_contract.py,
test_kf6_process_model.py and test_kf6_outage.py. Complete commands, versions,
source hashes, normal fingerprints and exit codes accompany the review package.

A tiny 21-sample real Pure INS engine run was saved before the math edit to
exercise the shared project engine boundary. After correction, strict result
load reports artifact_identity_mismatch, preserves every old file and metadata,
and never calls replay. EngineIdentity_Get automatically reflects the actual math
source bytes; no hard-coded revision or Git commit is substituted. Parser identity
is unchanged, and no old result is relabeled or silently upgraded from rev1.
The first baseline save attempt failed with WinError 3 at a generated path over
Windows MAX_PATH; its log and partial output are preserved. The probe succeeded
at a shorter generated test path. Product long-path support was not modified.

All new scenarios are synthetic, small host regressions, including explicitly
injected admission/fault returns. They are not mission 27/28, STM32, timing,
performance or flight evidence. No large ESKF or GUI run is claimed. Multi-GNSS
source ordering remains unresolved: diagnostic quality source labels are retained,
but unknown historic source identity is not inferred or added to event ordering.
Historical GUI GC root cause remains NOT PROVEN and large-result GUI acceptance
remains pending. This branch requires the parent's independent review before
integration into the user's usual checkout.
