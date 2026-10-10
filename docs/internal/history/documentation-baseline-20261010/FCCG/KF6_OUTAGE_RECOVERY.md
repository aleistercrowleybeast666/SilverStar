# KF6 GNSS outage recovery and vertical measurement noise

Platform 0.0.12, project 12, parameter schema 1.0 and decoder/project semantics 1.2 remain unchanged.
The record catalog, AIR/GSP and SSLOG layouts are unchanged. Exact acceptance results belong in
[VALIDATION.md](VALIDATION.md).

## Availability and return

Each of position EN, position U, velocity EN and velocity U owns an availability timestamp,
outage eligibility, a loss latch, reject/consistency/accepted streaks and bounded inflation attempts.
A quality-valid sample refreshes its own group's clock even when its NIS is rejected. An invalid
velocity never expires a valid position group. Position consistency may require the corresponding
velocity; that is a consistency condition, not a position-availability condition.

A gap **strictly greater than** `gnss_reacquire_outage_ms` permits return confirmation. The default
is 300 ms (a conservative configuration choice, not a measured flight optimum); the accepted
range is 100–10000 ms. At 25 Hz, candidates 160/200/250/300/500 ms represent 4/5/6.25/7.5/12.5
nominal sample periods. A 100 ms scheduling gap remains below every candidate. The firmware does
not need synthetic unavailable samples: the next observed GNSS epoch closes any absent interval.
Present invalid groups advance loss detection, and a long all-source absence is recognized on return.
The existing freshness, source, frozen-origin and START gates run before this tracker.

The returning measurement first takes the normal NIS update. A fused result before activation
clears outage eligibility without inflation. Otherwise, activation requires the true outage,
five consecutive hard rejects and three consistent source intervals. Continuous high-dynamic
rejection with fresh GNSS never authorizes inflation. Duplicate/rollback timestamps clear recovery
streaks and eligibility; timestamp zero disables that epoch's result gate. Finite/positive sigma
validation is group-specific. A new loss clears prior attempt/accept/reject state even during recovery.

Inflation remains `P' = D P D'`, group-selective, with target D=2, at least five rejected epochs
between attempts, at most eight attempts, position variance cap 1e6 and velocity variance cap 1e4.
Three consecutive fused returns end active recovery. Origins, observations, NIS thresholds and Q
are never changed by recovery. An attempt at the variance cap is counted as an attempted
recovery with applied factor one, rather than leaving the attempt counter permanently stuck.

## Independent quality groups and final recovery

The device quality contract has four independent valid bits and four reject masks in the order
Pos EN, Pos U, Vel EN, Vel U. A bad vertical accuracy cannot disable horizontal fusion, and a
missing horizontal velocity cannot disable valid vertical velocity. Fix/liveness requirements
remain common. Freshness uses receive time on the existing MCU axis. The aggregate
`position_usable` remains the strict all-position gate for the pre-START origin and simple status.
It is no longer the in-flight position-fusion gate. An invalid complementary coordinate is
replaced by the frozen origin coordinate only for the ENU conversion; its group is never updated.

Controlled re-anchor is the final group-specific recovery step. It requires a certified true
availability outage, an active recovery, receiver consistency for at least the existing sample
minimum and one second, exhausted bounded inflation attempts, and another complete rejection
interval after the last attempt. A normal or soft accepted update never triggers re-anchor.
Continuous NIS rejection with fresh receiver data is insufficient. Duplicate or discontinuous
receive epochs clear consistency eligibility.

Re-anchor sets only the selected position or velocity block to the receiver observation. The
block receives the positive measurement covariance, while its cross covariance with other
states is explicitly zeroed. The complementary principal covariance block and all other state
components remain unchanged. This block-diagonal construction preserves positive definiteness
when the incoming covariance is valid. Neither attitude, frozen origin nor mission clock resets.

Receive-side consistency start time is stored as immutable replay evidence. The recovery action
executes in the historical KF context during replay, followed by the normal event replay to the
present. Per-group internal diagnostics expose validity/reason, result, outage, consistency,
inflation and re-anchor count. The SSLOG transaction encoding and FLP consumption of these
additional diagnostics are still pending; the current decoder is not an exact replay contract.

## Vertical fusion

The state remains `[pE,pN,pU,vE,vN,vU]`. Barometer observes pU; vU is corrected through P(vU,pU).
GNSS pU remains a separate 1D observation, as does GNSS vU. No bias state, ZUPT, INS/attitude change
or fixed timing compensation is introduced. Current new-project defaults remain GNSS pU sigma floor 2.5 m, barometer
sigma floor 2.5 m, velocity sigma floor 0.15 m/s. Ground-oriented candidates are not flight defaults.

`gnss_velocity_std` retains the shared receiver sigma floor for compatibility.
`gnss_velocity_vertical_scale` (dimensionless actual value, new-project default 1.75, range 1–10) scales only the
vertical **measurement standard deviation** after the receiver uncertainty/floor maximum:

```
sigma_EN = max(receiver_sigma_EN * accuracy_scale, gnss_velocity_std)
sigma_U  = max(receiver_sigma_U  * accuracy_scale, gnss_velocity_std) * gnss_velocity_vertical_scale
R_axis   = sigma_axis * sigma_axis
```

Receiver uncertainty remains dynamic. P0 initialization is unchanged. The new values are declared
by the KF6 manifest, rendered into generated constants and exported in decoder 1.2 actual values.
Old FCCG projects reconcile only missing fields to defaults. FLP recognizes the exact prior
parameter identity and supplies explicit compatibility defaults for these two additions only;
missing previously required parameters remain errors. Old GNSS logs replayed with the new recovery
policy are marked approximate, never advertised as an exact old-firmware reproduction.

## Offline evidence

FLP owns independent per-log weight and velocity-latency experiments. These keep initial state,
P0, Q, attitude and position/barometer timing fixed. Velocity delay scans resample velocity and its
receiver variance on the original GNSS epoch grid over a common interior window, without crossing
source gaps or extrapolating. This is an explicitly approximate analysis, not a firmware timing fix.
Without qualified real logs, retain conservative defaults and report missing evidence rather than
selecting a purported flight optimum. See the FLP repository's field-analysis guide for its CLI.
