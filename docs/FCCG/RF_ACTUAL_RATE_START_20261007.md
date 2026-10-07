# RF56 actual-rate START storage probe — 2026-10-07

**RF56/16 zero-loss default qualification remains FAIL.** The independent
actual-rate baseline passes, but a single 80 ms START-sync storage delay loses
one SF6_STATE enqueue. The strict test and exact-decoder audit both exit 1.
Critical START metadata and flush-before-durable-ack checks pass in the recorded
Host scope. No default configuration, navigation mathematics, protocol,
assertion policy or product source was changed by this follow-up.

## Scope and configuration

The probe reuses `.work/rf_queue_probe/Flight_Controller` in the single isolated
worktree `.work/kh`, based on `f357d08e0de72ceabbd4e3f2af289c29a0f68f25`.
The daily tree remains `840bc6d7ae881e0601cc368f6e5bcfd11b9352f9`.
The existing generated RF profile selects MPU6050, NEO-M9N, E28-2G4M12SX,
BMP280, local SDIO SSLOG, maintenance OFF, CM3 softfloat and SF6. All 375 inputs
of the previous actual ARM build are hash-checked unchanged. ARM, CubeMX and
hardware were not rerun for this Host-only follow-up. Previous ARM results
remain historical evidence for those unchanged inputs, not a new ARM run.

This explicitly named probe fixes normal/estimator queues at 56/16, 200-byte
slots, 4096-byte aggregation, and the existing selected 21 log streams. It
never searches queue capacities or replaces the original pressure fixture.
The original 200 Hz barometer pressure cases remain FAIL: 56/16 overflow 217
and 64/16 overflow 22. Their logs and failure expectations are preserved.

Actual logical schedules are IMU 200 Hz, increments 100 Hz, barometer 20 Hz
and GNSS 25 Hz. There are 1200 preflight frames and 4800 flight frames, each
5000 us. The flight window is [6336000,30336000) us, exactly 24 seconds.
GNSS has valid fix and all four measurement groups; this is not a no-fix
test. Real SF6 backend/Core produces the output and logging: SF6_STATE 10 Hz;
SF6_MEASUREMENT 120 Hz (four GNSS groups at 25 Hz plus barometer at 20 Hz).
The test calls actual ImuSampleBus, DeviceNativeLog, EstimatorBus, logger,
F1 diskio and FatFs. Increments and sensors are synthetic Host inputs.
Prepared attitude and initial-origin snapshots are declared Host facades;
this is not a test of complete alignment/origin preparation or an INS task.

The actual static Flight owner functions `FlightTask_WriteStartRecords`,
`FlightTask_StartRecordsCapture` and `FlightTask_StartRecordsProcess` execute
through a Host-only inclusion of the unchanged `flight_task.c`. Real LoggerTask
snapshot/profile data supplies the captured START records and identity. Actual
owned LoggerBus request, real f_sync and real LoggerBus_StartDurable execute.
The wrapper checks no ACK before successful matching-generation sync, and
requires 58 START records and 40 stream descriptors before durability ACK.
This is the internal logger durability ACK; AIR/GSP command ACK/READY and the
complete command/lifecycle path are NOT_RUN.

Same logical-source epoch limitation as the existing storage helper:
`SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED=0U` in this Host compilation only.
It supplies no physical MPU interrupt/epoch qualification. Scheduling, time,
medium and SD DMA are deterministic Host models; each modeled DMA transaction
takes 2 ms. A single additional 80 ms delay, chosen before execution and not
retuned, occurs only at the first START f_sync barrier. It models a bounded
storage-service stall; it is not measured SD latency or an MCU WCET proof.

## Executed results

All final fixture/Host compilation and linking completed with no warnings.
The original helper's existing Host warning suppressions remain visible in
the exact command receipt. Only the Host fixture TU uses LTO to discard
unexecuted Flight service references on MinGW. Product callees stay non-LTO
so linker interception checks real calls. No target firmware LTO change.

| Case | Test / strict audit exits | Normal / estimator high water | Overflow | Drain / finalize |
|---|---|---|---|---|
| Actual rates, no additional sync stall | 0 / 0 | 13/56; 6/16 | 0 | accepted=dequeued=11562; finalized |
| Same rates, one 80 ms START sync stall | 1 / 1 | 41/56; 16/16 | 1 | accepted=dequeued=11562; finalized |
| Same stall, real SD DMA start error during f_sync | 0 expected fault / NOT_RUN | not a successful-record run | not zero-loss qualification | ACK=0; pending=1; captured=1; io_fault=1 |

Both normal cases export immutable, separate 1,012,911-byte logs containing
11,614 records. Exact generated `.ssdecoder` hash matching, framing and every
record CRC pass; neither has reordering or an unvalidated tail. Persisted
counts are IMU_CORRECTED 4800, INERTIAL_INCREMENT 2400, BARO_NATIVE 480,
GNSS_NATIVE 600, SF6_MEASUREMENT 2880 and SF6_STATE 240.

The failed enqueue is **SF6_STATE, record ID 43, timestamp 6441000 us,
frame 1221, estimator occupancy 16**. No other record type has a Full result.
The next state is persisted at 6451000 us. Baseline state intervals are
239 × 100000 us; the delayed case has one 110000 us interval and 238 ×
100000 us intervals. The eventual total remains 240 because the failed
cadence attempt retries later; that does not undo the missing attempt or
sequence gap. Strict audit reports one missing sequence, queue overflow 1;
STATS records also retain overflow 1 and health_flags 256
(`ESTIMATOR_HEALTH_LOG_EVENT_FAILED`). This is detectable ordinary record loss.

The separate explicit `--allow-queue-drops` diagnostic audit exits 0 because
this one gap is accounted for. It is not substituted for the strict failing
audit or interpreted as no loss. The wrapper's overall exit remains 1.
No assumption about acceptable ordinary loss is made here; the parent owns
that policy decision and RF56 default acceptance.

Each persisted START block is exactly config 1 + device descriptors 9 +
algorithm descriptors 4 + stream descriptors 40 + mission config 1 +
snapshot identity 1 + initial state 1 + MISSION_START event 1 = **58**.
Readback verifies all 40 unique streams, 21 enabled, configured rates and
56/16 depths, mission/commit generation 1, ready=1, and identical initial
P0 diagonal in SYSTEM_CONFIG and INITIAL_STATE. Critical metadata is not
lost or reduced. Trace ordering in both normal cases is:

```text
RF_START_SYNC_BEGIN generation=1 pending=1 records=58 streams=40 ... ack=0
RF_START_SYNC_END generation=1 sync=1 result=0 ack=0
RF_START_DURABLE generation=1 preceding_sync=1 records=58 streams=40 ack=1
```

The injected sync error instead reports result=1, ack=0 and retains pending
and captured state. No successful log is exported for this fault case.
Host setjmp/longjmp terminates the logger task loop for observation; it does
not enter target firmware or demonstrate MCU fault recovery.

## Reproduction and complete evidence

Run from a generated RF project with the three owning Host probe files
present. The source owner is
`apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/storage_integrity/`.
Normal regeneration preservation remains unchanged; only the two new probe
files were explicitly refreshed in this disposable validation project.

```powershell
& 'D:/python_software/SilverStar/.venv/Scripts/python.exe' -X utf8 `
  'Tests/Host/storage_integrity/run_rf_actual_rates_storage.py' `
  --project . --compiler 'D:/msys64/ucrt64/bin/gcc.exe'
# Expected overall exit 1 while the recorded 80 ms ordinary-loss case fails.
```

The independent readback check accepts the two recorded cases only in its
explicit rates/snapshot/accounting scope; its JSON retains default FAIL.

```powershell
& 'D:/python_software/SilverStar/.venv/Scripts/python.exe' -X utf8 `
  'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/storage_integrity/check_rf_actual_rates_records.py' `
  --project '.work/rf_queue_probe/Flight_Controller' `
  --attempt '.work/rf_queue_probe/Flight_Controller/build/FCCG/Host/Tests/RfActualRates56/Receipts/attempt004'
```

Final execution evidence is in `Receipts/attempt004`: complete compile logs,
all three execution logs, both strict audit logs, diagnostic audit log,
exact argv/cwd/times/exits in commands.json, source_inputs.json, and both
immutable SSLOG files. Additional evidence in `.work/rf_actual_rates_evidence`
records source revisions, unchanged compiled inputs, binary/artifact hashes,
tool versions, readback output and source commit. Library package adds this
follow-up without erasing earlier RF/RET/GSHC evidence.

All four compiler/run attempt receipts are retained: attempt001 fixture compilation fails on
the initial main macro/header setup; attempt002 compilation/linking fails on
MinGW unexecuted Flight service references; attempt003 has successful build,
the same 80 ms loss and expected sync fault, but a mistaken nonexistent audit
script path exits 2. Its printed GNSS counter is 599 despite 600 real records;
the final counter includes the first flight sample. The earlier SF6 guard
setup mistake was a pre-compiler ValueError (numeric 3U versus authoritative
symbol SYSTEM_FUSION_SF6), not a product algorithm failure. That pre-receipt
setup error is recorded in the conversation; no local raw log was captured
before receipt creation began. Prior fixture
bytes and command receipts are preserved. No passes are stitched into an
unexecuted full-suite result.

No ARM rebuild, real static analysis, Power10, stack recomputation, full Host
suite, MCU timing, complete command START, physical sensor epoch, or hardware
execution is claimed for this follow-up. They are NOT_RUN here. Previous
RF first-party gate also explicitly retains critical-contract manual review
NOT PROVEN. The unchanged earlier RF link had Flash 256748 B, RAM 86872/
98304 B, spare 11432 B (11.629%); task stacks 21504 B and MSP 2048 B are already
included in RAM and must not be counted twice. It links but does not meet
20% spare RAM. No additional capacity changes were made to pursue that target.
