# KF6 health namespace and fault publication review

2026-10-06 UTC. Isolated branch `codex/kf6-health-publication`, based on
`f8ae48f5922abca10a665db026cbc9041f57a234`. This batch changes the first diagnosed
KF6 application defect only. No hardware, serial, probe, flashing, merge or push.
GSHC/FLP, algorithms, M0 layout and thresholds, NAV_STATUS, ESTIMATOR wire/ownership,
normal queue capacities, navigation capacities and task stack reservations are unchanged.

## Behavior and consumers

The core's historical `INVALID_INPUT`, `MATRIX_NOT_SPD`, `NUMERIC_ERROR` and
`COVARIANCE_RECOVERED` bits belong to a separate namespace. They no longer enter
application health through a naked OR. The raw flags remain in the core context.
Ordinary invalid measurements, NIS rejection and a recovered covariance followed
by a successful prediction do not manufacture queue overflow, unavailable origins
or an active fatal fault. Only the replay terminal-fault certificate maps to the
existing application numeric-fault bit; unknown internal core bits fail-stop.

A terminal prediction or measurement replay fault atomically republishes the
last successful snapshot as invalid. Its successful timestamp and update sequence
stay unchanged. Later predictions cannot make it available again without an
explicit mission reset. Attitude propagation failure uses the same invalid
publication. The attitude/prediction operation owns its failure handling in one
internal helper; the existing math and operation order are preserved.

`Estimator_GetLatestSnapshot` already copies the snapshot for a non-NULL caller
and returns its validity. Flight recovery already rejects getter failure; the
Flight telemetry stream already skips it. INS diagnostics now clear validity
instead of retaining healthy pure-INS fields after a selected-navigation fault.
The existing STATS builder retains invalid-snapshot health bits and the last
sequence. Its existing period and queue/storage limits remain: this does not
promise immediate or durable logging. The narrow Host fixture executes the real
getter, INS diagnostic application and STATS builder; the Flight and telemetry
consumer behavior also has source review and existing finite Host regressions.

Rollback now clears the owning origin-valid fields before KF6 publication, while
retaining warm origin windows. Correction to the earlier f8 review: SF6 and ESKF
define `SYSTEM_BUILD_ESTIMATOR_ENABLED=0U`; their compiled rollback/abort paths
cannot reach that KF6 publish branch. This batch makes no contrary claim.

## Fresh evidence

Both projects use the same reconciled F407VET6 KF6 configuration, JY901B, M9N,
E28/SX1281, local SSLOG, maintenance enabled and automatic memory layout. They
reuse the verified F407 board/CubeMX input from `Q2F407_7fa06c4`; CubeMX was not
invoked again for this application-only repair. These are F407 CM4F hard-float
builds, not RET6 or hardware validation. Of the 155 compiled C inputs, only the
three application files differ; generated algorithm parameters are byte-identical.
Fresh `before` and final `accepted` outputs, commands, exit codes, logs, input
hashes and binaries are retained under the isolated worktree's `.work/evidence`.

| Check | Final recorded result |
| --- | --- |
| Fixed 23-scenario Host fixture | Baseline 21 fail / 2 pass; final 23 pass |
| Per-core-bit combinations | All 16 masks: healthy publication, then real replay model failure and invalid publication; raw flags retained |
| Other fixture cases | Actual covariance recovery, invalid GNSS component, hard NIS rejection, prediction/measurement terminal replay faults, rollback, genuine bus overflow counter |
| Finite emitted Host jobs | 11 selected jobs passed; original arguments/assertions retained; full Host suite not run |
| Repository pytest | 18 passed (4 publication/binding tests and 14 stack tests); final expanded fixture rerun 4 passed, overlapping, not additive |
| ARM Release | Fresh compile and link exit 0; strict warnings retained |
| Actual static analysis | Fresh `-fanalyzer` ARM compilation and link exit 0; not syntax-only |
| Power10 as emitted | Exit 0, 6,329 checks, 111 first-party C files, 2,761 functions, 815 nonblocking recommendations |
| Critical-contract acceptance | **NOT PROVEN**, explicitly emitted by Power10 |
| Architecture | **FAIL**, exit 2: unchanged InputVoltage device includes `system_power_if.h`; identical failure in fresh baseline |
| Artifact / memory | Exit 0; historical SRAM budget and <=20% spare warnings retained |
| Stack | Exit 0 for recorded task budgets; whole-program MSP/main/ISR nesting and hardware margins **NOT PROVEN** |

Host jobs: `navigation_kf_replay`, `kf6_process_model_revision2`,
`estimator_barometer_pending`, `navigation_quality_supervisor`,
`flight_recovery_all_triggers`, `flight_recovery_baro_imu_landing`, `telemetry`,
`estimator_preparation_actual`, `optional_gnss_start_actual`,
`logger_snapshot_actual`, `logger_streaming_actual`. The emitted wrapper's
unconditional storage-integrity runner was excluded; no full-suite pass is claimed.
The optional-GNSS Host job emitted an LTO serial-compilation warning but passed.

The initial application implementation failed the unchanged 60-line rule
(prediction function 65 lines). The final helper has 27 physical code lines and
the orchestration function 45. Initial fixture setup/incorrect aggregate-GNSS
expectations were corrected before fixing the final common pre/post expectations;
those setup errors are not presented as firmware failures. An attempted refresh
of an existing disposable generated project required review and did not apply;
the final project was generated into a new destination. No refusal was bypassed.

Stack gate revision `kf6_health_f407_20261006_v6` adds exact reviewed variants of
the three changed application bodies, eight existing freshly generated F407
inputs and two F407 storage dependency graphs. Historical variants stay intact.
No thresholds, source coverage or callback exceptions change. Owning payload and
reference overlay are identical. Whole-source and dependency mutation tests
remain rejecting unknown inputs; no interim estimator body is accepted.

## Actual resources

Arm GNU 14.3.Rel1 GCC 14.3.1, Host GCC 16.1.0 (MSYS2 Rev5), Make 4.4.1,
Python 3.14.0. Same Release configuration and source graph on both sides.

| Quantity | Baseline | Final | Delta |
| --- | ---: | ---: | ---: |
| ELF flash load | 330,456 B | 331,000 B | +544 B |
| BIN length | 330,468 B | 331,012 B | +544 B |
| Main SRAM | 112,756 B | 112,756 B | 0 |
| CCM | 46,760 B | 46,760 B | 0 |
| ELF file including debug | 3,323,564 B | 3,326,512 B | +2,948 B |

Main SRAM spare is 18,316 / 131,072 B (13.97%); the 20% target is unmet, though
the physical linker limit passes. CCM spare is 18,776 / 65,536 B. Spare memory
does not prove stack/timing margins. Static named-symbol groups are unchanged:
KF6/application contexts 41,568 B, logger record queues 25,600 B, selected other
logger storage 9,056 B, SX128x scratch 8,190 B, stack arrays 27,648 B, other symbols
46,132 B. They total 158,194 B; the remaining 1,322 B is anonymous/padding/linker
accounting. Stack arrays appear once in RAM; stack estimates are not added again.
These ownership groups are neither a complete subsystem cost model nor accuracy
evidence. Estimator recorded stack estimate stays 3,260 / 4,096 B (836 B margin).

Baseline ELF SHA256 `910c3f7baf20bc796fb2ed35548cf47c048ec10104b025927e054b6340e32e8a`.
Final ELF SHA256 `5f7f82269749de08e2fc5c1ceff30607b487b67ac3d2bdcf334ca4c2899f7ea8`.

The architecture failure blocks a claim that all project gates or acceptance are
complete. Common lifecycle/status recording remains pending the user's choice;
this repair does not fill that evidence gap. No MCU recovery, sensor navigation
accuracy, RET6 link result, hardware high-water mark, WCET or flight qualification
is claimed by this F407 Host/build batch.
