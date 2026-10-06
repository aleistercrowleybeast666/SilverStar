# Four-tier F1 compile checkpoint — 2026-10-06

Isolated branch: `codex/sf6-compact-ret6`, based on KF6
`7fa06c4155661e40847c0af78f4b23f3659b995d`. Stable and parallel FLP worktrees were
not changed. No serial, probe, hardware, flashing, merge or push actions occurred.
This is a compile checkpoint with failed acceptance gates, not flight acceptance.

The [four-tier matrix](FEATURE_TIERS_20261006.md) is implemented in the first-page
Global configuration group. Full/Standard preserve normal queue configuration;
Compact bounds the four endpoint classes but retains configurable GNSS,
maintenance and all-stream logging; Minimal adds the explicit extreme cropping.
Algorithms, parameters and suspended selections are saved in reversible tier
snapshots. Old incompatible projects retain their original algorithm and need
explicit review. Hidden first-release magnetometer exposure remains unchanged.

## Actual artifacts

Both projects use previously **executed official CubeMX 6.15.0 / F1 V1.8.7**
hardware generation, then SCG import and a normal validated generation plan.
No hand-written IOC substituted for a CubeMX run. RFT6 is the real RFTx/xG
target, 768 KiB Flash / 96 KiB SRAM; RET6 is REx/xE, 512 KiB / 64 KiB. Both use
CM3 `-mthumb -mfloat-abi=soft`, no FPU or CCM, 64 MHz HSI PLL. The same existing
official tools/packages were reused; nothing was downloaded or installed.

| Configuration | ARM source commit | RAM including static stacks and 2 KiB MSP | Spare | BIN load | 20% spare target |
|---|---|---:|---:|---:|---|
| RFT6 Compact: MPU6050 + NEO-M9N + E28-2G4M12SX + BMP280, SF6, maintenance manually off, local all-stream SSLOG | `3ed454c19e66658c502edf302b0044168d26622d` | 97,488 / 98,304 B | 816 B, 0.8301% | 252,832 / 786,432 B | Misses by 18,845 B |
| RET6 Minimal: MPU6050 + E28-2G4M12SX + BMP280, SF6, GNSS/maintenance off, local minimal SSLOG | `184f9ac1a5543da90c9f47f659c53866966894bf` | 63,736 / 65,536 B | 1,800 B, 2.7466% | 218,440 / 524,288 B | Misses by 11,308 B |

Both ARM links exit 0 and produce new ELF/map/BIN. These satisfy the linker hard
limit, not the requested 20% RAM margin or a proven runtime stack margin.
RFT6 data/BSS/MSP = 1,296/94,144/2,048 B; RET6 = 408/61,280/2,048 B.
Task/idle stacks are already in BSS and counted exactly once.
RET6's successful link retains four newlib warnings for unimplemented `_close`,
`_lseek`, `_read` and `_write`; exit 0 does not establish a warning-free firmware.
RFT6's final ARM/analyzer logs contain no warnings. The runtime-library warnings
are preserved, not suppressed or presented as original Rule 10 compliance.

| Disjoint RAM group | RFT6 bytes (% RAM capacity) | RET6 bytes (% RAM capacity) |
|---|---:|---:|
| Algorithm/origin state | 12,119 (12.33%) | 5,383 (8.21%) |
| Sample/log queues | 33,280 (33.85%) | 15,504 (23.66%) |
| Other logging | 5,534 (5.63%) | 2,462 (3.76%) |
| Device state | 9,620 (9.79%) | 5,751 (8.78%) |
| Platform/HAL/RTOS | 4,386 (4.46%) | 2,206 (3.37%) |
| Static task/idle stacks, in BSS | 21,504 (21.88%) | 21,504 (32.81%) |
| Other | 8,664 (8.81%) | 8,664 (13.22%) |
| Alignment fill/unparsed | 333 (0.34%) | 214 (0.33%) |
| Main/MSP reservation | 2,048 (2.08%) | 2,048 (3.13%) |

RFT6 retained text groups: algorithm 29,828 B, logging 23,536 B,
platform/HAL/RTOS 29,220 B, devices 52,920 B, runtime libraries 22,546 B,
other first-party 82,086 B; 12,696 B remains for rodata/vectors/fill/data loads.
Map reports include the largest symbols. SF6's 192-byte core is not a history
buffer removal claim. RFT6 still retains the selected GNSS origin state.

Measured RFT6 difference versus the preserved historical legacy-boolean Compact
checkpoint is +18,408 B RAM and zero BIN difference: restored normal queues
contribute +16,360 B and aggregation +2,048 B. The old 79,080 B result must not be
relabelled as the new Compact tier. RET6 differs from B by +336 B RAM and zero
BIN difference, consistent with the snapshot-capacity correction. Comparisons
across these configurations do not isolate GNSS or algorithm savings.

## Verification and failures

| Check | RFT6 | RET6 |
|---|---|---|
| Actual ARM compilation/link | 0 | 0 |
| Actual `-fanalyzer` compilation/link | 0 | 0 |
| Architecture | 0, 327 checks | 0 |
| Artifact/linked heap check | 0, heap symbols 0 | 0, heap symbols 0 |
| Emitted `power10-check` | Text exit 0; critical-contract review NOT PROVEN | Text exit 0; critical-contract review NOT PROVEN |
| Emitted full Host suite | 2: required JY901B positive compile fails after source pruning | 2: same positive compile failure |
| Stack report | 2: unreviewed `NeoM9nStartup_Init/Tick` startup operation binding | 2: checker discovery/binding gap at `SensorImu_Verify`; its 24 B static frame and ELF symbol exist |
| Hardware/flight/WCET/accuracy | NOT RUN | NOT RUN |

RFT6 text gate: 5,815 checks, 115 first-party C files, 2,490 functions,
755 nonblocking assertion recommendations. RET6: 5,272 checks, 112 files,
2,229 functions, 643 recommendations. Counts do not prove semantic assertion
validity or critical contracts. No gate thresholds, assertion facilities,
protocol checks or stack sizes were weakened to obtain these results.

SCG tier/GUI/schema/DMA selection: **33 passed** at its recorded revision.
Subsequent power-contract test passed. Final small capability/tier selection:
**16 passed, 1 failed, 19 deselected**; failure is the existing reference test
expecting `barometer.altitude` in the JY901B manifest. That manifest is byte-for-
byte unchanged from the KF6 base and does not declare that capability. The test
was not weakened. Three targeted bounded provider/override tests passed after
the consistent projection adjustment. The competing-provider test declares a
synthetic capability fixture and is only a model test, not hardware evidence.
These scoped results are not stitched into an unexecuted full-suite pass.

DMA SRAM bounds caught a real pre-fix RFT6 failure: the F1 backend had a fixed
64 KiB end. The provider now uses exact target bounds, RET6 0x20010000 / RFT6
0x20018000. Boundary/cross-boundary/null/zero/SIZE_MAX Host cases pass. Both
generated/compiled input sets contain the correction. RFT6 retains
`PlatformMemory_IsDmaAccessible` in its final ELF; RET6 discards that unused
36-byte function at link time. Hardware DMA is NOT RUN.

RET6's `SensorImu_Verify` has a compiler `.su` entry of 24 B, `static`, and a
retained ELF symbol. The actual instructions include `blx r3` for the optional
`profile->extra_verify` callback. The checker has not resolved that binding;
this is not absence of a compiler frame, and 24 B is not a total call-path budget.
RFT6's checker also hardcodes a startup caller set containing JY901B; the actual
pruned caller set contains only M9N Init/Tick. Both binding reviews and full
task/library/ISR stack proofs remain NOT PROVEN. No exception was added.

Evidence-only correction after independent review: three historical RFT6 failure
receipts now point to their saved `arm_pre_include.log`, `arm_pre_power.log` and
`analyzer_pre_power.log`, rather than the subsequently overwritten final logs.
Their saved log bytes, SHA-256, exit codes, commands and source revisions are
unchanged. The ZIP manifest is recalculated only for the corrected receipts and
this report; compiled artifacts and product source remain unchanged.

Initial new-Compact ARM compile failed because a power-capability configuration
header was missing; commit `184f9ac` adds the existing owning header. Subsequent
link failed on `SystemPower_*` because a no-power source graph was pruned while
the declaration default stayed enabled. Commit `3ed454c` derives both bounded-
tier power flags from the actual selected endpoint. Full/Standard defaults remain
unchanged, and selected power devices stay supported. All failure logs and the
failed map are retained. A temporary progress message incorrectly attributed the
link failure to RAM overflow; the complete log disproved that, and it was corrected.

The queue regression caught 56 slots being smaller than the full snapshot in a
larger configuration. Minimal now computes at least all descriptors plus five
slots, with a 56-slot floor. Disabled streams remain in the startup snapshot;
there is no descriptor hiding or reduced stack size.

## Provenance and boundaries

The RFT6 normal re-generation after the fix modified 3 managed files and
preserved 568 component payload files. The one owning C include fix was refreshed
only in the disposable validation tree after checking its old repository bytes.
Normal regeneration still preserves user-owned payloads. Subsequent normal Apply
and source identity verification compare **all 1,526 files, including ownership,
with zero mismatches**, and all 151 link-listed C/assembly sources match. The
final generic barometer model adjustment does not alter any RFT6 generated bytes;
no additional ARM rebuild is claimed or needed for that unchanged input set.

RET6 ARM remains attributed to `184f9ac`; its analyzer and later gate commands
record `3ed454c` as host repository HEAD while operating on that saved generated
RET6 tree. The later render change moves identical power declarations between
blocks; it does not retrospectively change the source revision of the RET6 ELF.
The evidence preserves the exact generated headers/model/source hashes used.

Both target Release and StaticAnalysis artifacts, actual compiler stack frames,
commands, times, exit codes, full failure logs, tool versions, official IOC hashes,
source patches and per-entry artifact hashes are bundled. Linked HAL/CMSIS,
FreeRTOS CM3, FatFs, SX128x library and compiler runtime remain third-party scope;
the first-party text gate does not certify their callbacks, recursion, stacks or
timing. Existing controlled exceptions remain unchanged. Unresolved call paths
remain NOT PROVEN. No host setjmp/longjmp interception is MCU recovery evidence.

Light/dark Chinese/English actual Qt screenshots and state receipts demonstrate
the first-page selector and scoped log-control correction. Required available
checks stay locked selected; required unavailable checks are unchecked disabled;
checked/unchecked disabled states remain distinct. Other frozen GUI controls and
GSHC/FLP were not changed. Screenshot font loading is confined to the evidence
harness, using existing Windows font files.

The initial light/English global-group screenshot captured an unsettled layout.
A single replacement observation at the same 1000x550 viewport, after a 350 ms
Qt event-loop settle, shows the complete two-line description: label height and
height-for-width are both 32 px. The original capture is preserved; the added
`global_light_en_US_stable.png` and its state receipt document the stable layout.
No product layout changes or full GUI rerun were made.

The B configuration-intent checkpoint remains saved at `2745c8f` and fail-closed.
Readmission was not implemented. Its real CAL/alignment/startup integration
failures and post-START NOT RUN boundary remain blocking. Neither of these
compile artifacts claims sensor recovery acceptance, stack safety, STM32 WCET,
navigation accuracy or flight qualification. Barometer-only horizontal position
remains inertial dead reckoning and may drift.
