# Experimental delayed-primary fusion development snapshot

Owner: /root; local branch feature/usb-transport-0.1.3-20261013.
Base commit: 09615f221163a87e85bca66675db1b7f9c4df50b. Exact dirty source
bytes and hashes are included in evidence.zip. This is development evidence,
not completed manual safety acceptance, original Power of Ten compliance,
NASA certification, board validation or flight qualification.

## Implemented scope

- Separate mode2 delayed primary with independent complete output state/P
  propagation and no output feedback/history replay. Fixed160 raw intervals,
  64 events; work bounds512 KF /832 ESKF. Ordinary late/capacity rejection,
  completion backpressure and faults that preserve committed numerical state
  and withdraw READY remain explicit.
- KF component0.4.0 / ESKF0.3.0 carry the separate horizon identity and typed
  actual lag. Mode0/1 timing layouts remain on their existing wire contract.
  The default remains1. SCG/FLP selectors expose an experimental third choice.
- New request/completion0x2D v1 is148 bytes, including actual prepared R and
  immutable KF receipt certificates. Status0x2E v1 is88 bytes. Frozen v2 records
  were not relabeled. Logs and decoder packages are immutable.
- FLP strictly opens the exact .ssdecoder plus Descriptor using
  LogOpenCoordinator, reconstructs recorded initialization/body inputs and
  distinguishes Recorded from explicit What-if lag/delay changes. Unknown
  receiver/noise recomputation and cross-mode conversion are rejected.
  Source-selection health remains masked unknown rather than inventing READY.
- Trusted contract snapshots ship as application package data, byte-equal to
  contracts/. They are deployment copies, not a second contract authority.

## Fresh representative configuration

Normal SCG generation uses the existing UART reference board with its declared
JY901S no-barometer variant and M9N GNSS, IMU200Hz/two subsamples, propagation100Hz,
lag300ms. Validation models explicitly enable necessary raw/init/full-P streams;
user logging defaults were not changed. An attempted BMI088/BMP280 configuration
was correctly rejected for missing I2C/synchronization bindings; it was not
forced through by remapping fixed pins. Undeclared JY barometer rates remain
RATE_UNPROVEN. This demonstrates software configuration admission, not hardware.

Fresh CPU producers supply10ms intervals, frozen synthetic preflight/calibration
and clock/device ports. Their source0 matches the generated source instance.
They use actual owning backend/task, LoggerBus and SSLOG writers. They do not
exercise the physical INS acquisition, preflight scheduler, UART or board.

## Executed checks and limits

| Scope | Recorded result |
|---|---|
| SCG version/capability/capacity/old0/1 generation and UI | horizon_scg_admission01:41 passed |
| Native generated configuration, CPU5ms stress cases | native_configuration_backend01:48 passed (both algorithms/O0/O2; ESKF synthetic source1 in this older stress fixture) |
| KF memory fix, native config normal/fault cases | native_kf_memory_backend02:24 passed (O0/O2) |
| ESKF source0 fixture normal paths | native_eskf_identity_backend02:2 passed,22 deselected |
| Final exact normal logs, Recorded/What-if, every output/full P | native_horizon_log_final04:2 passed;80 outputs per algorithm |
| Final changed product admission/execution scope | focused_product_regression02:244 passed, no skips |
| Source readability | horizon_format02: Ruff passed; import bindings/nonimport AST unchanged for9 files |
| KF03 mode2 / ESKF02 mode2 emitted Power10 | exit0 /0; critical-contract review explicitly NOT PROVEN |
| Real static-analysis compilation, not syntax-only | exit0 /0; actual emitted commands/logs retained |
| Actual ARM compile/link | exit0 /0; ELF/MAP/BIN/HEX hashes retained |
| Architecture/source graph and linked artifact checks | exit0 /0 for both |
| Stack report | exit2 /2: reviewed Generated/Inc/project_flight_config.h hash mismatch; NOT PROVEN |

The earlier493-test invocation predates product admission edits and is not a
current full-suite result. Earlier interrupted complete Host suites retain
unknown exit status. They were not rerun or counted as passes. The listed
focused invocation is not a whole-repository or full Host suite claim.

## Demonstrated memory defect and correction

The first actual KF native artifact check failed: main SRAM102764 bytes exceeded
the existing102400-byte reviewed logging budget by364. The threshold, event
capacity, log rates, stack reservations and allowlists were not relaxed.
Natural grouping of the private KF event fields removes alignment padding.
Actual ARM objects show152 to144 bytes/event and512 bytes/context saved.
The fresh normally generated KF03 link/check passes at102252 bytes main SRAM,
leaving only148 bytes below that reviewed budget (physical SRAM spare28820).
CCM use51392 bytes. ESKF main SRAM110012 / CCM53232 passes its existing policy.
Spare bytes do not establish safe task/MSP/ISR stack margin.

Before/after exact-package log opens prove six owning body/output/full-P/timing
record types are bitwise identical:534 frames /69304 serialized bytes. No
numerical tolerance, safety expectation or wire field was weakened for this fix.
The pre-fix artifact failure, post-fix output, ARM sizeof sources/objects and
comparison receipt are retained.

## Retained failures and interruptions

- The two environment disconnects left original gate sessions without final
  ARM results. RECOVERED_20261016_0628.json inventories partial artifacts and
  explicitly marks INTERRUPTED/exitUNKNOWN. Completed P10/analyzer receipts were
  kept. Only missing steps were resumed after accessible process checks.
- native_horizon_log_open01:KF passed, ESKF setup failed due to the test's wrong
  plugin ID. The corrected exact opener/actual plugin run passed later.
- focused_product_regression01:240 passed/4 failed from the pre-activation test
  assumption that the global schema rejects the newly implemented lag field.
  The updated test preserves explicit actual values, never inserts missing lag,
  proves metadata immutable and blocks old logs from entering mode2. Its first
  update also retained a stale build-only assertion (post02:2 pass/2 fail);
  post03:4 pass; the final coherent244-case invocation passed.
- Two preliminary ARM sizeof probes failed on omitted include paths. Neither
  was treated as a size proof. The final actual ARM object query succeeded.
- Stack-report failures were preserved. No expected hash/checker was broadened
  to turn them green. Full callback/library/task/MSP/ISR nesting and bounds,
  indirect calls, dynamic frames, WCET and useful critical assertions still
  require review. P10's density recommendations are not acceptance proof.

## Remaining work / acceptance blockers

1. Review actual callback compilation inputs and complete the generated stack
   proof without bypassing the input-hash gate. All critical-contract and
   whole-program/library/ISR bounds that lack proof remain NOT PROVEN.
2. Active ESKF outage recovery is not integrated. The separate frozen draft
   has250 isolated tests, not an integrated recovery result. Its required
   atomic source/native receipt, caller-verified physical/coherent masks,
   configuration/provenance, paired rollback and1/5/30/120s outage/fault matrix
   remain pending. No unapproved physical-coherence thresholds were invented.
3. Fresh complete mode0/1 firmware gates and full Host closure remain pending;
   prior interrupted/older results cannot be attributed to this snapshot.
4. No board, timing, navigation accuracy or flight evidence was collected.

All new generated outputs remain under .work/dev013_horizon01, owned by/root;
the purpose/path/hash inventory is in the manifest/archive. Inputs, original
logs/packages, failed outputs and frozen releases are retained. No cleanup,
hardware, wireless/selector, Android, publish, push or tag operation occurred.
The v0.1.2 object and peeled commit, and three protected root inputs, were
rechecked unchanged immediately before this snapshot.
