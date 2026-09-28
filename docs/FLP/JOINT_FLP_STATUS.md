# FLP joint navigation implementation and evidence

> Historical pre-monorepo status. The current product release identity is the root `VERSION` (0.1.0), and the sole machine contract is [the root navigation contract](../../contracts/navigation_v1.json). The 0.0.5 identities and duplicated-copy statements below describe the former FLP workspace.

Baseline commit `c4605f4`; the single FLP runtime version is now **0.0.5**.
The old project/decoder 1.2 and revision-2 KF6 interpretation remain supported.
New generated 35-record decoders require FLP 0.0.5. No original log or decoder
was modified. Pre-existing untracked `tests/.tmp_*` directories were retained.

## Implemented product paths

- The registered ESKF15 plugin contains executable float64 p/v/q/bg/ba and
  15×15 covariance prediction/update, independent finite-difference Jacobian
  checks, calibrated two-subsample coning/sculling, second-order Phi, positive
  Simpson Q, Joseph correction and exact SO(3) right reset. It rejects invalid
  input, hard NIS, large-angle/bias and covariance failures transactionally.
- Body-history replay covers 600 ms with 192 compact body entries and 208
  measurement events; source/generation/epoch/history failures are explicit.
  Historical re-execution does not increment the outer fusion supervisor.
- Quality revision 3 separates physical validity, satellite variance weighting,
  staggered native 10 s / 5 s closure windows, 6 s evidence expiry and effective
  fusion timeouts. Two seconds degrades groups; ten seconds invalidates missing
  required GNSS groups. Model/time faults latch until explicit initialization.
  It does not force invalid observations, invent a recovery origin, inflate
  covariance without evidence, or treat receiver liveness as successful fusion.
- The Replay page offers an explicit **new quality revision 3 What-if** for old
  KF6 logs, with saved configuration and bilingual controls. Old revision 2
  remains the default for matching old logs. Four active window parameters are
  consumed; six old accumulator parameters remain a read-only historical
  snapshot in revision 3. Its parameter audit lists the 30 effective values.
  A variance cap above 4 or a changed retired value is rejected, never clamped.
- ESKF state/bias, five update groups, all 15 covariance diagonals and complete
  P export are connected to the actual analysis-source/plot/export workflow.
  Recorded and What-if sources remain explicit. Navigation health and native
  window diagnostics have separate logical and evaluation clocks.
- Exact ESKF replay requires BODY_INPUT, initialization plus all four initial
  P fragments and consistent algorithm/source/epoch/calibration identity.
  Periodic P fragments are grouped by identity, not adjacency or file arrival
  order. Initial P is mandatory; periodic P is optional only when explicitly
  disabled in the exact decoder, with cross-covariance comparison unavailable.
  Missing enabled/unknown-policy P, duplicated/conflicting P, CRC/framing/gaps,
  wrong identities and recorded-state/update differences prevent FAITHFUL.

The machine contract is `docs/contracts/navigation_v1.json`, distributed also
inside the ESKF package. FCCG owns that contract; the two FLP copies match byte
for byte. Frame is ENU; quaternion is Hamilton scalar-first body-to-navigation;
error is right local, in p/v/theta/bg/ba order. Receiver standard deviation uses
the ESKF contract multiplier 1.0; historical KF6 keeps its own 1.25 profile and
origin uncertainty. These conventions are not silently shared or reinterpreted.

## SSLOG and FCCG work owned by this task

Seven new version-1 records occupy IDs 0x21–0x27, payload sizes
144/144/144/144/100/84/100 bytes: state, full-P part, initial state, initial-P
part, measurement, body input and navigation quality. All old wire identities
and layouts remain intact. Initial state/P, body and measurement are Required
when their producer is selected. Complete-P cadence is evaluated once for all
four pieces; partial queue acceptance remains observable as a missing snapshot
and real drops. Event 0x2F carries actual fusion state changes.

The protocol catalog, codecs, parser metadata, strict importer overlay and FLP
consumer agree. New minimum-version metadata is 0.0.5. The additional FCCG
device-initialization section displays actual fixed-profile defaults, supported
range/rate, filter/FIFO, readback, persistence and hardware evidence in both
languages and themes, without fake editable choices or side effects. New
devices remain explicitly hardware-unverified.

## Executed software evidence

The final complete FLP suite is **426 passed, 9 skipped, 382.54 s**, in
`tests/joint_rework_20260927/final_complete.log`. The nine skips name unrelated
historical manual logs/old golden inputs which were not supplied. All new C
ESKF, native delay/window, new codec and new exact-decoder tests executed.

Actual C versus independent Python covers 2,000 predictions and 1,000 grouped
updates; maximum p/v/q/P differences were approximately
1.032e-5 m / 9.42e-6 m/s / 7.54e-6 / 3.13e-6. Delayed 100 Hz and 250 Hz tests
cover 600 ms, 200 epochs, 18 delayed events and the compressed caller-owned
192-entry C history. The C/Python window comparison covers 750 native samples,
12 completed windows, gaps, duplicates, late epochs, boundary interpolation and
TTL, with maximum variance-scale difference below 4.9e-7. See the JSON evidence.

Actual generated descriptor + C ESKF + C SSLOG codec → production exact decoder
→ FLP plugin produced 659 synthetic records. State, quaternion, both biases,
all P elements and measurement diagnostics matched the declared numerical
tolerances; maximum P difference was 1.64e-6. Both ordinary and deliberately
interleaved C-encoded arrival orders passed in the final full suite. The interleaved
case delivers a periodic P fragment after a newer BODY record. Incorrect
calibration identity, missing P and an injected numerical divergence are
explicit negative tests. This is a synthetic software fixture, never flight
data. The coordinator's separate actual backend/LoggerBus/Storage gates cover
production admission and delivery; this direct codec fixture does not claim to
exercise complete App/Startup/durable bootstrap or target timing.

A separate actual ESKF backend/LoggerBus/LoggerTask bridge with production NONE
calibration and generated descriptor supplies 491 records, 200 BODY inputs and
99 measurements. The exact decoder import and numerical comparison are FAITHFUL;
maximum full-P difference is 7.31e-7. Explicit admission/result comparisons
distinguish unavailable unattempted diagnostics from attempted numeric values.
BODY-only GUI displays both recorded/replayed bias and uncertainty; 361 files
export with zero failures, while two absent legacy-IMU plots are explicitly
unavailable. The synthetic host fwrite/fflush sink does not certify FatFs timing.

The 600 s velocity-bias and 300 s position-drift counterexamples, independent
bad groups/baro, severe-tilt MODEL_MISMATCH, capacity/callback rollback, delayed
three-group arrival permutations and invalid-P cases are in the final suite.
See `tests/joint_rework_20260927/REQUIREMENTS_TO_TESTS.md` for the clause mapping.
Final Ruff, compileall and diff checks pass. The offline 0.0.5 wheel starts from
its extracted package with ESKF resources/plugin present; no install/publish.
The new VALIDATION.md chapter records all exact hashes, results and limitations.

A final independent review also repaired C prediction's history transaction:
failed BODY no longer trims authoritative history before input/numeric rejection.
It uses the existing working scratch, with no extra state/global allocation.
The focused final delta is 20 passed / 18.82 s, including byte-identical rejection
at the 600 ms boundary, multi-prefix success/capacity and original numerical
parities. Full-suite and later-delta results remain separately identified.

## Five real logs: all results retained

`tests/joint_rework_20260927/four_way_comparison/` contains individual reports,
machine-readable outcomes and four-way position/velocity plots for SS0000–4:
A recorded onboard output, B same old-revision KF6 replay, C revision-3 KF6
What-if and D ESKF15 What-if. All five source hashes and the exact decoder hash
were checked before and after. Original operation-resolved times are retained
for C; missing old operations are not fabricated. Both B and C fail SS0002 with
`gnss_origin_unavailable`; no substitute origin was inserted. Where old same-
revision replay cannot meet complete recorded parity it remains APPROXIMATE.

The full D numerical outputs and p/v/q/bias/15-state covariance, windows and
group diagnostics live under `five_logs_contract_final/`. All five have finite
nominal/P output, positive P minimum eigenvalues and quaternion norm error below
2.3e-16; those internal properties are **not flight-performance acceptance**.
SS0000, SS0002 and SS0004 have long rejected-fusion intervals, severe drift and
final INVALID health. SS0001 and SS0003 finish healthy under the algorithm's
available evidence. There is no independent position/attitude truth, so
endpoint differences are outputs, not accuracy errors or proof of improvement.

Old logs lack new raw-body contract evidence, certified actual IMU range and
clip/readback flags, and trusted GNSS iTOW-to-MCU alignment. New algorithms on
these logs are therefore approximate counterfactual analyses. No physical
device initialization, flash, output activation, NVM write, flight or new-sensor
hardware verification was performed by this task. Host run time is not an MCU
real-time or stack budget. Large regression artifacts are retained locally;
small committed evidence includes their SHA256/size rather than binary caches.


The final authorized quality integration supersedes the earlier health snapshot: the four pending product paths are complete and the final full suite passes 483 tests with 9 historical optional skips. Fresh five-log runs preserve all prior non-health numerical arrays; SS0003 ESKF changes from HEALTHY to DEGRADED. SS0001 remains HEALTHY, and SS0000/2/4 remain INVALID. The precise health counts/first times/longest fusion gaps, final bridge and wheel hashes are in the latest VALIDATION.md chapter.
