# SF6 RET6 compact: resource checkpoint for parallel review

2026-10-05 19:23 UTC. Branch `codex/sf6-compact-ret6`, following checkpoint
`2ef7bceb8b1e973f84521cb9c0d3dda585babccc`. **Work remains incomplete; no acceptance
or complete Flight ELF is claimed.** The phase 1 document's date used the host's
2026-10-06 local log date (+08:00); its UTC date should be 2026-10-05. Original
logs and the historical checkpoint are retained.

## Source batch

* Compact-only log queue capacity derives from every device descriptor, four
  generated algorithm descriptors, and every stream descriptor (including
  disabled streams). Current START system snapshot needs 54 records; ordinary
  log queue is 58 slots. A compiled table-size/capacity assertion checks the
  relationship against the actual descriptor arrays and SSLOG_RECORD_COUNT.
* Estimator log queue 48 -> 8, aggregation 4096 -> 1024, IMU sample queue
  64 -> 16 and prediction queue 64 -> 16. Existing ordinary full/error/drop
  handling is retained. This reduces burst tolerance; CM3 scheduling and SD
  latency under sustained logging are unqualified. Normal default sizes stay
  unchanged. No task stack, 100-sample origin window or SF6 core was reduced.
* New F1 GPIO context storage follows the generated logical slot upper bound
  (currently 10 rather than 96). Access and ISR traversal use the same bound.
* F1 SD disk I/O now uses the existing source-owned sector bounce/DMA/queue
  completion implementation, adapted to the R0.11 ABI. Official CubeMX DMA
  mappings, MSP links, HAL and BSP remain authoritative. One 512-byte bounce
  sector prevents borrowing caller buffers after return. DMA completion blocks
  on the static RTOS queue; card-ready retries yield and time out. Uncertain DMA
  completion poisons storage until reset: automatic recovery from that condition
  is **not implemented**. The transplant requires its own fault/byte-integrity
  Host validation and hardware review.
* Power10 linker discovery reads the selected target manifest rather than a
  fixed F407 filename; no thresholds, coverage or exceptions were changed.
  Host target include discovery and the storage harness input paths were made
  target-aware. Full gate results remain failures, below.

## Actual failed-link map comparison

Both rows describe full-entry attempted links, **not accepted ELF resources**.

| Allocation | Phase 1 | Current |
|---|---:|---:|
| data | 1276 B | 1296 B |
| bss, including static task stacks | 94128 B | 71776 B |
| main/MSP reservation | 2048 B | 2048 B |
| RAM span, including alignment | 97456 B | 75120 B |
| overflow beyond 65536 B | 31920 B | 9584 B |

Net RAM-span reduction: **22336 B**. Current exact hard limit is not met. The
20% spare target is at most 52428 B occupied; current span exceeds it by 22692 B.
Dropping GNSS is now an authorized next candidate after this measured four-device
failure, but it has not happened. The embedded GNSS origin/ENU windows still need
real generation-time capability guards; merely disabling GNSS at runtime cannot
remove those retained allocations. Barometer and local SSLOG remain selected.

Current allocation groups from the failed map (static stacks counted once):

| Group | Bytes | % of 64 KiB |
|---|---:|---:|
| Static task stacks already in bss | 21504 | 32.812 |
| Main/MSP reservation | 2048 | 3.125 |
| Sample and log queues | 15120 | 23.071 |
| Algorithm and origin state | 12119 | 18.492 |
| Device state | 9604 | 14.655 |
| Platform/vendor/RTOS state | 4370 | 6.668 |
| Other logging | 1630 | 2.487 |
| Other state | 8384 | 12.793 |
| Alignment/fill/unparsed | 341 | 0.520 |

These groups are a named-object map partition, not stack safety or WCET proof.
The largest estimator task state remains 10232 B; SF6's core remains 192 B with
no history. `map_symbol_distribution.json` contains object owners and symbols.

## Verification and remaining failures

* Normal SCG Plan/Apply again succeeded from the genuine CubeMX import with
  only explicit manual-hardware and unqualified-CM3-timing warnings. Fresh
  generated candidate has 1516 files. The prior generated candidate was removed
  only after exact path and generated ownership verification; failure logs/map
  were preserved. No test-wide repository copies or user inputs were removed.
* Fresh actual ARM GCC compilation with emitted strict first-party warnings
  completed and attempted linking (`ret6_arm_full_04.log`, make exit 2).
  Link still fails with 9584 B RAM overflow **and unresolved SystemPower calls**.
  The generated power-disable default was included too late to override the
  target default. This inclusion-order defect has been identified, not fixed.
* Compact/barometer tests: **20 passed** (31.92 s), including existing cold
  pressure-datum/error-path Host code compiled with `-fanalyzer`.
  Latest compact file including clean-entry refusal, complete snapshot sizing,
  and actual SDIO handle-binding positive/missing/mismatched negatives:
  **10 passed** (12.71 s). These are separate runs, not a full suite.
* Emitted Power10: **FAIL, 4 failure groups**, make exit 2. Selected target
  linker/zero heap checks now pass, but new generated conditional compilation,
  GPIO fallback conditional, the SD card-ready while loop and R0.11 write/ioctl
  conditional blocks are rejected. **No allowlist was enlarged.** Next batch
  must generate optional glue in Python, make the required backend capacity
  explicit, and use a statically bounded yielding wait without weakening the gate.
  Critical-contract review explicitly remains **NOT PROVEN**.
* Emitted Host suite: **FAIL**, make exit 2 at `profiles_kf6`. Target header is
  found now, but its required-barometer-origin static assertion fails because
  the Host harness does not carry the compact source-graph flag. This is not
  evidence that target assertions should be removed.
* Emitted architecture check: **FAIL**, make exit 2: fixed
  `TARGET_PROFILE=SilverStar_F407` still conflicts with RET6. Equivalent target
  checks require adaptation in the owning script.
* Full ARM `ANALYZE=1` static-analysis build, F1 append-seek/close faults, F1
  delayed-DMA byte integrity, SX128x maximum command audit, artifact acceptance
  and stack report: **NOT RUN**. Link acceptance blocks ELF-based reports.
  Earlier 93-pass/1-golden-hash-failure regression remains unresolved.
* Recovery changes remain unimplemented. START source-lock preservation,
  same-instance IMU recovery, concurrency, all critical contracts, third-party
  call/stack/timing consequences and useful assertion semantics require review.
  Hardware, serial, probes, flashing, MCU execution and flight tests: **NOT RUN**.

## Paths, commands and disk

Single isolated worktree: `D:/python_software/SilverStar/.work/sf6_compact_ret6`.
Current candidate: `.work/generated_ret6`.
Official input project: `.work/cubemx_flight/SF6_RET6_Hardware`, with genuine
`SF6_RET6_Hardware.ioc`. Phase 1 retains its exact file and CubeMX logs.
The official command used bundled Java:

```
"C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/jre/bin/java.exe" -jar "C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/STM32CubeMX.exe" -q .work/evidence/cubemx_lfn.script
```

That script loads the actual IOC, sets `_USE_LFN=2`, `_FS_NORTC=1`, runs
`config save` and `project generate`. The complete log explicitly records
`project generate OK`. Installed official FW_F1 V1.8.7 and existing toolchains
were reused. Minimal official CubeMX project and successful ARM link remain at
`.work/cubemx_minimal/SF6_RET6_Minimal`.

Current build/check commands were exactly the emitted targets:

```
mingw32-make -j2 all "GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin"
mingw32-make power10-check
mingw32-make host-tests
mingw32-make architecture-check
```

Current evidence: `docs/FCCG/platform/evidence/SF6_RET6_phase2`, including full
failure logs/maps/compiled ownership in a small zip, JSON symbol distribution,
test outputs and hashes. `.work/evidence` retains all individual failure attempts.

At 2026-10-05 19:23 UTC, `Get-PSDrive D` reported **21365690368 bytes free**
(21.366 decimal GB, about 19.900 GiB). Isolated worktree size measured immediately
before the last build was 773867501 bytes; build growth since is bounded to this
candidate's objects/logs. `Get-Volume` earlier denied access; no permissions were
changed. A subsequent permitted `Get-PSDrive` read succeeded.

The brief environment interruption did not create another worktree. Source
status, IOC and build log were checked after reconnection; current make process
completed and its final exit was retrieved. No active generation/build remains
at this checkpoint. No merge, push, hardware or unrelated GUI actions occurred.
