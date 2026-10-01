# SF6 stage 3: first software checkpoint, 2026-10-02 UTC

This is an implementation checkpoint, **not completed acceptance or a frozen hardware candidate**. No serial, probe, reset, programming or actuator command was executed. TEST_4 and `FrozenArtifacts_50cc2d3` remain inputs only.

## Implemented contract

- New declarative owner: `silverstar.algorithm.estimator.sf6`, algorithm ID 3, revision 1. Existing None/KF6/ESKF15 IDs remain 0/1/2. UI appends “SF6算法” after the existing three choices.
- Exactly six dimensionless gains in state order **vE, vN, vU, pE, pN, pU**, each in [0,1], each default 0.2. These are initial engineering defaults, not bench-tuned or optimal. Three existing timestamp-delay settings are also exposed; they are preprocessing settings, not additional gains. Position/velocity/barometer delay defaults remain 0/270/0 ms.
- Reuses existing calibrated coning/sculling increments, quaternion propagation, INS gravity/ENU transformation, common GNSS quality validation, ENU origin, barometer altitude resolution and trusted/untrusted timestamp resolution. Does not alter KF6 or ESKF15 mathematical kernels.
- Prediction: `v_next = v + dv`, `p_next = p + (v + dv/2) dt`. At the matched measurement boundary each observed state uses `x += gain * (observation - x)`. A delayed velocity correction propagates its same-axis position effect forward through `delta_v * elapsed_time`.
- 256 CPU-only history samples, at most 600 ms retained. A delayed observation is matched to the previous completed prediction boundary, **not exact fractional-time Kalman rewind/replay**. Boundary quantization is at most the accepted 20 ms prediction interval. History misses, discontinuities, duplicate/backward measurement/receive times, duplicate/backward serial numbers and nonfinite input are ordinary rejected operations. Sequence wrap is supported inside the forward half range.
- GNSS position EN/U and velocity EN/U are independent observation groups. GNSS groups execute before barometer. Barometer relative altitude and GNSS relative ellipsoid ENU U use the same pU gain, once per new observation. Barometer does not correct vU. Per-observation gains are explicitly frequency dependent.
- Own backend selects `SYSTEM_BUILD_ESTIMATOR_ENABLED=0U`: no KF covariance/replay/integrity workspace and no ESKF workspace is linked. Shared output ABI retains unavailable statistical fields as NaN, and SF6 navigation NIS/R-scale wire metrics return the existing unavailable sentinel.
- New additive SSLOG records 0x2B `SF6_STATE` (72-byte wire payload, states/quaternion/actual gains) and 0x2C `SF6_MEASUREMENT` (56 bytes, actual sample/receive/resolved/evaluation/boundary times and outcomes). No covariance fields. Old IDs and wire layouts remain intact. GSHC/FLP name and recorded-source mappings include SF6; opening still requires the exact decoder and Descriptor.

## Completed checks at this boundary

The exact command and raw logs are in `.work/SF6_20261001_v1`. Standalone actual SF6 kernel compiled with GCC 16.1, C11, strict warnings including `-Werror`, `-Wconversion`, `-Wsign-conversion`, `-Wshadow`, `-pedantic`; linked the actual `silverstar_assert.c`, not a disabled assertion stub. `navigation_sf6_core.exe` returned **1173 checks, 0 failures**. Cases cover gain 0/1 and axis isolation, independent groups, delayed correction, shared pU barometer gain, serial wrap/duplicate, bounded ring, outage prediction, invalid dt, nonfinite observations and gain bounds, unchanged state after rejected operations and reset. This is Host software evidence, not MCU timing or sensor accuracy.

Four fresh projects were generated from a read-only TEST_4 model copy, reconciled, saved and reopened: `PureINS_v4`, `KF6_v4`, `ESKF15_v4`, `SF6_v4`. The save/reopen dictionaries match. TEST_4's F407 board and actual devices/resources, aggregation 2, disabled calibration, vector-constraint alignment, existing logging switches and Tilt deployment mode were retained. These are **not yet the requested 10-second Delay bench configurations**.

First ARM Release links and artifact checks completed at earlier, explicitly named snapshots:

| Project | Flash used / spare | SRAM used / spare | CCM used / spare |
|---|---:|---:|---:|
| KF6_v1 | see original ARM log | 101408 / 29664 | 55432 / 10104 |
| ESKF15_v1 | see original ARM log | 100008 / 31064 | 63456 / 2080 |
| SF6_v3 | 288708 / 235580 | 90584 / 40488 | 44016 / 21520 |

These earlier links **do not certify the current complete checkpoint**: later common routing/catalog edits require a fresh full run. PureINS ARM numbers, four-way final resources/static-stack/real analyzer/Host/PoT results and candidate freezing remain pending. RAM spare does not prove safe stack margin or actual navigation frequency.

## Failures retained and next boundary

1. SF6_v1 first compilation rejected three implicit narrowing conversions and missing barometer/delay declarations. Owning sources/manifest were corrected; SF6_v3 ARM subsequently linked.
2. SF6_v3 Host command failed before execution because new schema records lacked `record_modes`. Added the declarations in the owning schema. Fresh v4 run pending; no full Host PASS claim.
3. SF6_v3 architecture check passed. PoT failed because the common prediction function grew to 61 code lines. Centralized the shared backend ownership decision in `Estimator_NavigationBackendSelected`, reused by initialization/prediction/diagnostics/rollback/abort. This is a shared selection boundary, not an allowlist or threshold change. Fresh emitted v4 PoT pending. Critical-contract review remains NOT PROVEN.
4. SF6 backend/log/queue transaction regression, actual C codec-to-exact-decoder/FLP regression, GUI save/reopen and old-algorithm regression suite still need completion. Internal corruption fault cases and semantic review remain pending.
5. A separate UART1/2 async-transmit hotfix is owned by the parent; it has not been integrated. No `platform_uart` or hardware generator patch was edited here.

After the final four-algorithm gates, create fresh KF6/SF6 bench configurations with a recorded 10-second Delay change, preserve no-actuator bench restrictions, record hashes/commands/source revision, freeze them separately and return. Do not start barometer cold backup or automatic memory-layout work in this slice.
