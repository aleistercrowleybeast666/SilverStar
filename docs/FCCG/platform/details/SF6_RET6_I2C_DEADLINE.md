# SF6 RET6 blocking I2C deadline checkpoint

2026-10-05 UTC. Implementation commit `eaa11484995eb8978f8eac09ace87a7bc0b5edcb`, isolated branch `codex/sf6-compact-ret6`, initial I2C checkpoint `738edb045ad92b94cbe6a9d0267c7db014e1a749`, preceding SDIO fix `3edb2bc830b4ed577a419be656c457b146a983f2`. This is an owning-platform compile/Host checkpoint. Overall acceptance remains BLOCKED; critical-contract review remains NOT PROVEN. No hardware, serial, probe, flashing, merge or push occurred.

The F1 Flight HAL originally waited on BUSY with a hardcoded 25 ms before using the caller's 2 ms address/data timeout. The actual unchanged HAL in the new deterministic Host model returns HAL_BUSY at 26,000 model microseconds, error 0x20. This matches the independent parent review's actual-HAL tick result. The original failure is preserved with unchanged current test expectations; fixture development failures are separate logs.

The owning F1 Flight HAL now places a single per-handle deadline before BUSY and retains it through addressing, memory-register bytes, repeated START, data, final BTF and cleanup. It locks before BUSY; inner memory functions and their shared wait helpers retain the lock until the outer wrapper clears the deadline. Shared helpers retain their original non-memory behavior when no memory deadline is active. The public HAL/Platform result types and wire protocol remain unchanged.

The initial `738edb0` checkpoint could silently take the legacy wait path if its active flag was corrupted to zero. An unchanged new fault case reproduces a successful HAL read under that corruption. `eaa1148` separates blocking-wrapper lock ownership from cycle-clock admission, checks ownership/active/lock consistency, and fail-stops if either owner, active state or the lock is lost. Admission can own the lock while the counter is not yet active; failed admission clears ownership before unlock. Legacy non-memory waits require no memory owner and an inactive deadline. Complete pre-fix and corrected logs are preserved; the initial checkpoint is not the final safety boundary.

The deadline reads Cortex-M3 CYCCNT, including the vendor's IRQ-masked last-three-byte BTF poll. It enables only DEMCR.TRCENA and CYCCNTENA, never resets CYCCNT or installs a callback. A counter that fails to advance at admission is rejected with an ordinary timeout. The deadline uses unsigned wrap subtraction and 90% nominal cycles, under a fixed 1..72 MHz HCLK and a supported finite 1..1000 ms timeout. The actual selected call is 2 ms at nominal 64 MHz: polling cutoff 115,200 cycles (1,800 nominal microseconds). Input validation precedes any transaction. Memory operations reject ISR/PRIMASK-masked entry because the preserved upstream receive sequence re-enables IRQs. Selected MPU/BMP bus operations are Device-task owned; the IMU adapter releases its short processing lock before bus work and publication takes a separate short lock.

All reachable wait helpers check the same deadline on entry, while waiting, and before successful return. The IRQ-masked last-three-byte path retains its original iteration bound as an additional fail-closed limit and checks the same CYCCNT deadline. NACK, bus error, arbitration loss, overrun and timeout remain ordinary error paths. Error cleanup preserves the original ACK/POS setting and releases the deadline/lock. It issues STOP only when still master and not after arbitration loss. A failed read can leave partial caller-buffer bytes, as in upstream HAL; it never returns success for them. The sensor adapter already copies its scratch buffer into published data only on success. HAL_STATE_READY means the handle is available, not device/controller READY. This change does not implement stuck-line recovery or unlimited device restart, and does not reset an IMU instance or its source lock.

Stored deadline lifecycle corruption (active other than 1 during owned polling, zero active budget, a second start while already active, or a lost owner/active/lock) enters the existing SilverStar assertion fail-stop contract. Six Host cases intercept this with a test-only assertion stub that exits failure; this is not MCU recovery or target trap-path execution. There is no density-driven business return change or new event/static-assert padding.

The Host fixture compiles the actual complete owning HAL I2C source and actual deadline helper. Only CPU/peripheral access is modeled: CYCCNT/IRQ instructions, flag transitions and address-clear side effects. It runs 47 transaction cases covering stuck BUSY, first START/address, both register-address bytes, register-end TXE, repeated START/address, TXE/RXNE/BTF and IRQ-masked BTF; normal 1/2/3/4/6/14/24-byte reads and writes, 8/16-bit register addresses, cumulative BUSY+data delays, NACK in multiple phases, BERR/ARLO/OVR, counter wrap, unavailable counter and a subsequent successful transaction after timeout. Normal/error cases check canaries, buffer data, lock, IRQ, ACK/POS, state and deadline cleanup. Additional argument/ISR/masked-entry/busy-lock rejection cases and the six assertion traps are separate from the 47 count. The stuck cases complete at 1,804–1,808 model microseconds. The model is not an electrical bus, scheduler, target instruction timing or MCU WCET model.

The BMP280 startup trim read is 24 bytes with the same 2 ms timeout. At the prior 100 kHz even the approximately 27 nine-bit address/register/data units need about 2.43 ms before software/START/STOP overhead. The official CubeMX 6.15 CLI therefore regenerated Fast mode with `ClockSpeed=350000`, duty 2; no hand-written IOC substituted for generation. The actual vendor HAL initialization is also tested: 32 MHz PCLK1 yields CCR=31, TRISE=10, nominal SCL about 344.086 kHz. A 10% upper allowance gives 378.495 kHz, below 400 kHz. SDIO divider 2 remains in the real IOC. BMP280's official datasheet supports standard/fast mode: https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp280-ds001.pdf . The MPU6050 profile retains its existing TDK register-map provenance; the attempted current TDK datasheet URL redirected to an inaccessible search endpoint, so its current official download was not obtained. Physical bus electrical and oscillator qualification is NOT RUN.

The cycle arithmetic does not prove completion at or below 2,000 real microseconds. At an actual HSI -2% the 1,800 nominal-microsecond polling cutoff is about 1,837 microseconds; cleanup and preemption still need a measured/proven bound within the remaining allowance. DWT availability/continuity, fixed-clock ownership, scheduler latency, long suspension/multiple-counter-wrap assumptions, vendor receive sequencing and interrupt latency remain manual/hardware requirements. No measured RET6 2 ms guarantee, MCU recovery, WCET, stack margin or flight qualification is claimed.

Upstream provenance remains STM32Cube FW_F1 V1.8.7. Original I2C C SHA256 `beb83cfbcbfed8ce30d58f810b3510dfaab584ddb5468c1d0e852b343b98eb9c`; original header SHA256 `ffc3f56f746113bab72283e016999760da95384d815e5e7dd8899cb551c0c84a`. ST copyright/license comments remain. The controlled fork extends the local HAL handle with 12 bytes of deadline context plus 4 bytes of blocking lock-owner state; every fresh F1 Flight client is rebuilt. This ABI is not shared with F1 Ground/F407. Upstream I2C DMA/interrupt callbacks remain vendor exceptions; no runtime registry was added. Vendor code remains excluded from the existing first-party text/analyzer policy, not declared compliant. Linked vendor/RTOS/library recursion, timing and stack proofs remain unresolved as recorded in prior phase reports.

Fresh results for this exact owning-source revision:

| Check | Actual result |
|---|---|
| Unchanged old-HAL failure / corrected Host paths | before exit 1 at 26,000 model us; after exit 0 |
| SDIO, I2C, compact, sensor IMU, BMP core/adapter/generation and cold pytest | one latest run: 20 passed; includes actual BMP/Cold Host `-fanalyzer` compilation |
| Fresh official CubeMX / SCG import/generation | exit 0 / Plan True, 1,508 new files |
| ARM GCC compile/link | exit 0, CM3 softfloat, no CCM |
| Emitted static-analysis | exit 0, real first-party `-fanalyzer` compilation and ARM link |
| Emitted power10-check | exit 0, 5,210 checks, 112 first-party C files, 2,198 functions, 1,368 eligible candidates, informational mean 0.622384, 626 recommendations; critical-contract review NOT PROVEN |
| Emitted artifact-check | exit 0; no heap symbols |
| Emitted architecture-check | make exit 2, same 8 Device-to-System include paths in one aggregate failure |
| Emitted stack-report | make exit 2, unresolved indirect `SensorRegister_Read`; main/MSP/ISR proof also remains unavailable |
| Full emitted Host suite | make exit 2 at job 8 `system_alignment_explicit_required_gnss`; jobs 1–7 pass, 9–70 NOT RUN |
| Logger/storage stress | NOT RERUN for this platform batch; prior 914-drop failure remains, independent logger repair not integrated |
| Hardware / actual wire timing / flight | NOT RUN |

Both ARM link logs retain upstream nosys `_close/_lseek/_read/_write` warnings. First-party strict compiler checks and the unchanged policy are not a zero-warning whole-firmware claim. No selected results are presented as a complete full-suite PASS. All commands, versions, exact canonical SCG source hashes, generated source/configuration hashes, complete pass/failure logs, actual ELF/BIN/map/stack files and parent review input are in `../evidence/SF6_RET6_i2c_deadline/i2c_deadline_evidence.zip`.

Actual linked no-GNSS MPU6050+E28-2G4M12SX+BMP280/SF6/maintenance-off/local-SSLOG resource result: `.data` 408 + `.bss` 62,400 + MSP reservation 2,048 = **64,856/65,536 bytes**, spare **680 B (1.038%)**. Static task/idle stacks remain 21,504 B within `.bss`, counted once. Bin **215,528/524,288 B**. Versus the SDIO checkpoint, Flash grows 912 B and RAM 16 B. Versus the initial I2C checkpoint, the owner-state guard costs another 232 B Flash and 8 B allocated RAM, including alignment changes. The 20% spare target allows at most 52,428 B used, leaving a **12,428 B gap**. SF6 core still has 192 B state; no history-removal saving is claimed. Comparison with the older phase-2 four-module revision includes multiple configuration/source changes and is not a pure GNSS savings attribution.

| Disjoint linked RAM attribution | Bytes |
|---|---:|
| Static task/idle stacks, already in bss | 21,504 |
| Sample and log queues | 16,720 |
| Algorithm/origin state | 5,383 |
| Other logging | 2,654 |
| Device state | 5,735 |
| Platform/HAL/RTOS state | 2,206 |
| Other state | 8,384 |
| Alignment/unparsed fill | 222 |
| Main/MSP reservation | 2,048 |
| Total | 64,856 |

The linked map/symbol report includes its largest symbols and artifact hashes. Flash raw input-section contributions can overlap after GNU string merging, so a disjoint per-component Flash percentage remains NOT PROVEN rather than falsely summing raw sizes.

The independent parent package was obtained through the authorized file transfer tool after the Library helper download failed; its local SHA256 is `2b91136f34183f815db7900f8d8598892724cbbe1fca053eaed3b22386c84792`, 32,531 B, identical to the supplied evidence. No permissions or helper restrictions were bypassed. Library version xattrs were not asserted on this Windows local copy. The original archive remains unchanged in the evidence.

Independent logger candidate `75c48ad` is not integrated pending parent review. Its reported 1,136 B additional static request state would give an **unexecuted estimate** of 65,992 B here, exceeding RET6 RAM by 456 B before any further queue/profile changes. Neither that estimate nor the prior 696 B spare is an executed combined-candidate result. Later explicit compact log profile/capacity work must include the request state, keep all metadata and descriptors, preserve ordinary allstreams 80/48 stress separately, and reject records that cannot fit without truncation. No stack reduction, logger-core edit, queue growth or compact profile implementation was made in this platform batch.
