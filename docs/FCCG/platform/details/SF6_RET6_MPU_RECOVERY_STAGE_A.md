# SF6 RET6 MPU recovery stage A: source-side conditional cleanup

2026-10-06. Source commit `f76383e966421a9b755b4b29ccab140b573ed95f`, isolated branch `codex/sf6-compact-ret6`. Parent checkpoint `c1adfc3834bdd9bb396837522c08938d5ec4912b` contains prototype source `018ff76bdb5701541ae7545556a4318bf2203107`. This is the requested A review checkpoint; stage B readmission is **not implemented**. No merge/push or hardware/serial/probe actions occurred.

## Change and behavior boundary

The actual previous emitted Power10 run rejected 21 new compact source conditionals across MPU, selector and startup. This batch replaces them with ordinary C branches on a build constant defined in a small guarded header. Recovery code remains visible in its owning C payload, not moved into headers or excluded from first-party scanning. The original compact macro remains absent in ordinary projects; its defined/undefined semantics are preserved. The checker, source coverage, thresholds and allowlists are unchanged, verified against baseline Git bytes with CRLF-only normalization and exact generated payload hashes.

Prepared state is queried from its owning instance rather than duplicated in the selector. The helper checks the provider result and returns false in ordinary mode before any provider call. Prepared remains an instance lifecycle property; physical recovery does not reconstruct selector/driver, unlock the source or clear revoked qualification. Initial probe/reset results and immutable startup history remain real failures. Fresh physical samples still do not restore READY. The selector initialization function has 55 physical code lines in the emitted scan; the helper owns the prepared query, not a cosmetic threshold split.

## Generation and verification

One existing disposable RET6 validation project was refreshed after verifying every prior changed payload against its recorded raw hash and baseline Git bytes. Three payloads were updated; normal assembler Apply added the new header, modified two generated ownership/model files, preserved 557 component files and replaced no hardware. Normal user-project preservation behavior was not changed.

This reuses the actually executed official CubeMX 6.15/F1 V1.8.7 RET6 snapshot, source id `b582e89bf934a92fce53c2c704e1ede4be4a42417b031c9321ceb6f8130072ee`. No new CubeMX run is attributed to A. Target remains Cortex-M3, Thumb, softfloat, 512 KiB Flash/64 KiB RAM, no CCM/FPU. Configuration remains MPU6050 + E28 + BMP280, authorized no-GNSS fallback, SF6, maintenance disabled, local SSLOG enabled. No additional resource cuts or changes to ordinary configuration were made.

| Fresh generated command/result | Exit |
|---|---:|
| Release ARM `-B -j2 all`, actual compilation/link | 0 |
| Release `-B -j2 static-analysis`, actual ARM `-fanalyzer` compilation/link | 0 |
| architecture-check | 0 |
| power10-check, exactly emitted unchanged checker | 0 |
| artifact-check, linked heap symbols zero | 0 |
| stack-report | **2: unresolved SensorImu_Verify** |
| official complete host-tests runner | **2: missing unselected JY capability header** |
| list-sources | 0 |

Power10 reports 5272 text checks, 112 first-party C files, 2229 functions, 643 nonblocking assertion recommendations, 1390 eligible candidates and informational mean 0.623598. It explicitly reports `POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending`. This is not useful assertion-density proof, original Power of Ten compliance or completed acceptance. Both ARM links retain the four existing newlib `_close/_lseek/_read/_write` stub warnings; warning-free firmware is not claimed.

Focused Host verification: the unchanged 14 compact fault sequences and three ordinary sequences pass, plus the actual joint IMU C mock and adapter compile checks (4 pytest items). Compact/multi-instance generation regression: 12 passed. Baseline ordinary cases 15–17 also pass using exact baseline C bytes. Actual Host and CM3 softfloat ordinary driver/selector objects at O2 and Og retain identical static storage; actual ordinary fixture link text/data/BSS remain 28880/976/336 B before and after. This is not a full ordinary F407 image proof. Host COFF zero-state sections marked `d` are counted with `b`, excluding section aliases. A separate attempted ordinary startup compile fails before and after on the unchanged required-barometer-origin validation; it is retained as a failure, without artificial qualification flags.

Source identity covers 1515 generated/rendered/payload/hardware records and all 144 linked C/assembly inputs, zero mismatches, zero semantic project metadata differences, clean source commit. Evidence contains full commands, versions, exits, logs, source bytes, baseline bytes, current ELF/map/BIN, analyzer artifacts, compiler `.su` files and hashes. Initial command-path/PYTHONPATH failures are retained separately from corrected successful executions.

## Actual resources and unresolved acceptance

Final `.data`408 B + `.bss`60944 B + MSP reservation2048 B = **63400/65536 B**, spare **2136 B (3.259%)**. BIN/load bytes **218336/524288 B**. Net A change against the actual preceding prototype: **−8 B RAM, +72 B Flash**. The link hard bound is met; 20% spare permits52428 B, leaving a **10972 B** target gap.

Disjoint RAM groups: algorithm/origin5383 B, sample/log queues15168 B, other logging2462 B, device5751 B, platform/vendor/RTOS2206 B, static task/idle stacks21504 B, other8664 B, fill214 B, MSP2048 B. Static stacks are already included once in BSS. No stack budget is added to RAM again. Actual map/nm and before/after direct compiler frames are preserved. ELF still contains the unresolved SensorImu_Verify indirect call; no whole-task/library/MSP/ISR stack or WCET proof follows from direct frames.

Critical-contract review, generation-bound preSTART CAL/ALIGN/Origin/Health/START readmission, complete stack/indirect-call closure, F1 IRQ/timebase timing, RF90ms yield behavior and hardware qualification remain unresolved. No qualification clear is added in A. AfterSTART same-instance retry remains physical-only and revoked health remains fail-closed. Missing calibration/origin/alignment is not fabricated. Stage B remains pending parent review of this source/evidence package; acceptance is blocked.

The parent reference Library package `libfile_dc1fd091c3088191a26624616b97b032` returned `download failed` through the regular helper. Its bytes/hash/patch were not obtained or used; no access workaround was attempted. A was independently reviewed and tested from repository source.
