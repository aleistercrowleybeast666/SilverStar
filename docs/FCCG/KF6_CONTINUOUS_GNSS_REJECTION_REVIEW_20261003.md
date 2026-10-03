# KF6 continuous-valid GNSS rejection review

Read-only source review; no estimator changes or field replay are included.

`NavigationKf_GnssAvailabilityTrack` advances each group's availability clock
on physical validity, independent of the NIS result. It latches an outage only
after a gap exceeds the configured outage threshold. Therefore a continuously
valid physical stream can suffer persistent hard NIS rejection while the
outage/reacquisition counter remains zero. That counter does not measure all
fusion rejection episodes.

`NavigationKf_UpdateVector` rejects a hard-threshold innovation before the
measurement update. `NavigationKf_GnssRejectedProcess` requires a latched outage
and consistent epochs before activating covariance inflation. Reanchor has
additional outage, active-state, elapsed-consistency and bounded-attempt guards.
These are coherent with an outage-only recovery policy. Counting physical
availability from successful fusion would falsely turn rejection into sensor
loss and undermine the separation.

Recommendation: first add a distinct, bounded diagnostic for each physically
valid group's consecutive NIS rejects, elapsed rejection duration, innovation,
NIS and covariance/measurement variance. Retain the existing physical outage
and reacquisition diagnostics separately. Define explicit acceptance criteria
for sustained continuous-stream inconsistency before proposing any new recovery
policy. A future policy should require new, timestamp-monotonic, independent
quality/consistency evidence and cap any group-specific covariance adjustment;
it should terminate explicitly and retain hard gating and covariance validity.

Do not disable NIS, silently accept rejected measurements, reinitialize from a
single PVT, move frozen mission origins, switch sources implicitly or change
attitude/bias states in KF6. KF6 has no attitude/bias error-state estimator, so
its position/velocity correction cannot be treated as a repair for INS attitude
or bias drift. Rejection duration alone does not identify whether the input,
model, covariance, timing or frame transformation is responsible.

Any implementation needs synthetic continuous-valid inconsistent/consistent
GNSS cases, genuine outage cases, duplicates/time reversals, independent group
rejection, bad accuracy/quality, covariance caps and preservation of START/origin
invariants. The current review does not authorize or implement a policy change.
