# SF6 bounded replay software fix, 2026-10-02 UTC

The original affine-forward update is incorrect when a later observation has
already attenuated a state axis. The actual pre-fix Host cases produced pU=9
versus chronological 6.5 (error +2.5 m), and pU=4.25 versus chronological 4.125
(error +0.125 m) for delayed GNSS position and velocity after a newer barometer
update. The assertions were kept unchanged in the corrected runs.

The owning kernel now stores admitted IMU increments and fixed-gain observations.
It recomputes the retained history from its pre-observation oldest-boundary base.
Observations sort by resolved measurement timestamp, then ascending group ID.
The same-timestamp order is GNSS position EN/U, GNSS velocity EN/U, barometer U,
independent of arrival. A complete numerical validation pass precedes a second,
deterministic commit pass; overflow leaves the entire context and admission
metadata unchanged. No covariance or chronological process-noise model is added.

The preceding completed IMU boundary remains the measurement alignment rule.
Original admitted dt is saved and replayed rather than reconstructed from a
rounded microsecond duration. Same-group old/duplicate samples remain rejected;
cross-group late samples are replayed. Expiration advances the saved base and
removes old events. FULL is an ordinary explicit result, and expiry permits
fusion to resume without reset. Prediction/event capacity is 256 each.

For the actual 25 Hz GNSS and max(200 Hz integrated IMU, 200 Hz configured baro)
configuration, closed 600 ms window capacity is conservatively
4*(ceil(.6*25)+1)+(ceil(.6*200)+1)=185 observations and ceil(.6*200)+1=121
prediction boundaries. Owning backend compile-time checks reject configured
rates exceeding these capacities. Hardware exceeding its declared rate still
uses ordinary FULL/STale error handling; this is not an MCU timing proof.

Actual Host context sizeof is 18,592 bytes, versus 8,336 before: +10,256 static
bytes. The final ARM link must confirm bank use and compare all four algorithms;
this fix is not described as the lowest-resource estimator.

Current focused results: kernel 3,745 checks/zero failures; independent scalar
2030-step oracle matches pU and vU after delayed delivery and repeated ring wrap;
two original counterexample errors are zero. Tests also cover fixed timestamp
ties, distinct GNSS group timestamps, duplicate gains, future/old samples,
capacity FULL then expiry recovery, gain endpoints, nonfinite values and atomic
late replay overflow. FCCG 43 passed; GSHC 62 passed plus 3 subtests; exact FLP
v3 log plus legacy regressions 43 passed. Actual backend/INS/clock/queue/codec
export and missing-reference cases: 29,655 checks/zero failures.

FLP fixture repair follows FlightTask_CalibrationResultWrite's NONE/READY identity
record before mission start, using actual LoggerBus/LoggerTask. It does not claim
sensor calibration, and no decoder fallback or altered opening requirement was
added. Earlier v1/v2 rejected fixtures remain immutable. GUI repair keeps the
three original monitoring cards and all translated labels; only the alignment
action arrangement changes. All four 1000x700 language/theme content widths are
638 matching the viewport, versus the original English 856.

SF6 receives the authoritative frozen barometer-reference validity explicitly
through the backend initialization interface; it no longer invents validity.
ESKF accepts the interface argument with an explicit documented discard to
preserve its old behavior/math. SF6 absent initial GNSS reference returns NOT
READY; lost inputs after valid initialization retain bounded INS prediction and
report degradation. GNSS endpoint changes are unsupported until mission reinit.
Barometer provenance currently uses explicit UNKNOWN instead of falsely copying
the GNSS ID. Actual endpoint/epoch wiring awaits the separate Baro commit; no
completed source-contract acceptance or cold-backup support is claimed here.

Old hash discrepancy is reproduced from original bytes: navigation_sf6.c has
209 CRLF and 38 LF-only lines. Its e7be2566 raw-byte SHA256 normalizes exactly to
the committed LF content SHA256 19dab0b2. Git blob object IDs, Git content hashes,
archived working bytes and frozen generated artifact hashes are different
objects and will be reported separately. Historical evidence is not rewritten.

Pending current-source full matrix, authorized JY integration, actual Baro
endpoint contract, and Delay10 freeze with explicit actuator interpretation.
Tool PASS does not establish useful assertion density, whole-program stack/WCET,
hardware recovery or completed critical-contract acceptance (NOT PROVEN).
