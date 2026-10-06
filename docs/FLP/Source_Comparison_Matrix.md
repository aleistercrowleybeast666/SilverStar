# FLP optional secondary source coverage

Comparison is display-only. Result identity includes run index and stable source ID;
the primary remains the sole export source. Solid primary and dashed secondary traces
use real timestamps relative to dataset START, with no interpolation or gap filling.

| View | Comparable roles | Admission / unavailable behavior |
| --- | --- | --- |
| Navigation position, including U/height | E,N,U in metres | Standard ENU role; recorded decoder `length` maps narrowly to `position`. Explicit origin/frame/mission differences reject. |
| Navigation velocity | E,N,U in m/s | Published velocity role, same columns and units. |
| Attitude quaternion and Euler derived from it | WXYZ, Hamilton body-to-ENU | Recorded standard quaternion `dimensionless` maps narrowly to `quaternion`; wrong convention/order/frame rejects. |
| P diagonal / standard deviation | Plugin state groups and own indices | KF6 six states map to ESKF15's common position/velocity blocks. Other ESKF15 groups remain primary-only when no equivalent secondary exists. |
| Recorded legacy KF6 P | Own KF6 recorded source only | Exact six columns PxE/PxN/PxU/PvE/PvN/PvU, exact group units/indices and recorded KF6 identity are required for both primary and secondary. |
| Innovation / NIS | Same published measurement group, dimension, axes, units | Different observations never compare by shape alone. Missing attempt/input or nonoverlap yields an unavailable note. Primary thresholds stay primary. |
| Measurement sigma and effective R | Same observation role | Narrow KF6 variance units `m^2`/`(m)2` and ESKF15 mixed-storage variance roles normalize using the owning group. Unknown units/quantities reject. |
| Receive age / fixed-lag latency | Same observation role in ms | Narrow `fixed_lag_latency`/`latency` mapping for builtin KF6/ESKF15. |
| Barometric observation diagnostics | Barometric altitude scalar in metres | Explicit KF6 Baro ↔ ESKF15 U mapping in that group only; it does not map arbitrary equal-width channels. |
| ESKF15 bias/state estimate | Matching own plugin role, if provided | No KF6/INS/SF6 bias substitute. |
| Raw device IMU, sensor quality, recovery/audit tables | Shared recorded evidence | No independent algorithm secondary; no borrowed onboard estimator diagnostics. |
| Playback / 3D / horizontal trajectory / event markers | Existing primary presentation | Secondary comparison covers the physical time-series views. These presentations and complete 2D exports retain the primary source. |

PureINS and SF6 publish no filter P/innovation/NIS. Their unavailable filter views
stay empty; they cannot borrow recorded KF6. Selecting the primary as secondary clears
the secondary selector. A genuinely missing saved result retains its unavailable ID.

TimeSeries rejects decreasing timestamps. Duplicate timestamps, invalid/nonfinite
samples, cadence gaps and explicit discontinuities break plot connections. Reset
epochs cannot enter as a decreasing TimeSeries or be interpolated into a common clock.

## Evidence scope

The existing legal 41-input-sample four-algorithm artifacts were reused, without
parsing or recomputing. The 16 directed combinations cover all twelve distinct-algorithm
directions plus comparisons to a second PureINS run. Position/velocity/quaternion/Euler
already produced 3/3/4/3 secondary traces before the fix; this does not reproduce a
blank velocity view in the user's full project. The prior loss of secondary selection
on project reopening is addressed by persistence, and recorded metadata and diagnostic
role mismatches are reproduced separately with narrow fixtures.

The reused tiny fixture has barometric attempts but lacks GNSS attempts. Its GNSS
diagnostic cells are explicitly unavailable, while populated published-role fixtures
verify GNSS innovation/NIS and own state indexing. Recorded-role fixtures verify both
primary/secondary directions, and negative cases verify unit/frame/origin/task/column
and coverage rejection. Real mission 27/28 full project validation is deferred to the
user as instructed; these tests are not hardware or full mission acceptance.
