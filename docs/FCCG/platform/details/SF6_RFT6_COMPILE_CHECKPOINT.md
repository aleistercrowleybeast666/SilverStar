# SF6 RFT6 compile checkpoint (2026-10-06)

This checkpoint preserves the four-module RFT6 result before the newly authorized
MCU-independent Full / Standard / Compact / Minimal feature-tier work. It uses
the historical compact boolean with `all_streams` logging; it must not be relabeled
as the future Compact tier or used as that tier's resource measurement.

## Exact scope and source

- Isolated branch: `codex/sf6-compact-ret6`; no merge, push, hardware, serial or probe work.
- B checkpoint: `2745c8f1a468b89be7f604c334a0ddc04671298c` and
  [B config-intent report](SF6_MPU_B_CONFIG_INTENT_CHECKPOINT.md).
- ARM/analyzer firmware source: `ee7a9be6086bb640ea369997788ad7bf5f0b1649`.
- Authorized architecture checker revision: `821c12874935db4f3d2077f81a622572a045de8d`;
  that commit changes only the exact target identity and shared CM3 IRQ file check.
- MPU6050 + NEO-M9N + E28-2G4M12SX + BMP280; SF6, maintenance manually disabled,
  full-stream local SSLOG enabled, no TF or physical logging execution.
- STM32F103RFT6: 768 KiB Flash, 96 KiB SRAM, Cortex-M3, no FPU/CCM;
  actual `-mcpu=cortex-m3 -mthumb -mfloat-abi=soft`, `STM32F103xG`, XL startup.

Official CubeMX 6.15.0 actually loaded `STM32F103RFTx` and generated the new
`SF6_RFT6_Hardware` project using STM32Cube FW_F1 V1.8.7. Its own generated
Makefile selects `startup_stm32f103xg.s` / `STM32F103xG`; its own linker specifies
768K Flash / 96K RAM, zero heap and 0x800 MSP. These ST files were copied byte
for byte with licenses into the owning MCU/plugin payload, not produced by
changing a RET6 memory length. The new XL CMSIS header is likewise ST output.
IOC SHA-256: `a5651325193c65b7a4b78c806fdbf4858214c03822c09af827a0e12d16faaa6b`.

Initial Cube generation was a valid seed only. Full generation attempts first
rejected DMA/I2C/UART and then I2C. CLI failed to persist the requested clock
source; only RCC parameters were configured from the existing validated HSI
clock group, retaining the actual RFT6 identity. Official `clock resolution`
then completed actual full generation and exited 0. The final configuration
uses 64 MHz HSI PLL, I2C 100 kHz, USART1 921600 with RX circular/TX DMA,
SDIO four-wire ClockDiv 2/shared DMA, TIM6 HAL tick, separate RTOS SysTick,
EXTI2 E28 and EXTI3 GNSS pulse. Electrical/timing behavior is hardware unverified.
Failed attempt logs and configuration hashes are preserved.

SCG normal importer/Plan/Apply accepted that official output without validation
bypass. Normal regeneration preserved 568 component payload files, including
prior checkers. Only this disposable validation tree's two checkers were then
explicitly refreshed to exact owning templates with verified prior/current
hashes. Normal user-payload preservation was not changed; ownership hashes were
not manually rewritten. The first receipt writer threw after successful Apply
because it assumed an `ApplyResult.applied` property; the actual Apply receipt
and subsequent corrected normal Apply are both preserved.

## Measured linked resources

Actual Release ELF/map/BIN: `.data 1296 + .bss 75736 + MSP 2048 = 79080` bytes RAM.
Hard SRAM spare: **19224 bytes (19.5557%)**. The 20% spare goal permits 78643 bytes
used: this result misses by **437 bytes**. No queue, log or safe-stack reduction
was made to erase that difference. BIN load: **252832 / 786432 bytes**.

| Disjoint RAM category | Bytes | % of 96 KiB |
|---|---:|---:|
| Algorithms and origin state | 12119 | 12.328 |
| Sample and log queues | 16920 | 17.212 |
| Other logging | 3486 | 3.546 |
| Device state | 9620 | 9.786 |
| Platform/HAL/RTOS state | 4386 | 4.462 |
| Static task/idle stacks, already in BSS | 21504 | 21.875 |
| Other | 8664 | 8.813 |
| Fill/unparsed | 333 | 0.339 |
| MSP reservation | 2048 | 2.083 |

Stacks are counted once. They are reservations, not a proof of safe margin.
Retained `.text` groups: algorithms 29828, logging 23532, platform/HAL/RTOS
29220, devices 52920, linked runtime libraries 22546, other first-party 82086;
the remaining 12700 BIN bytes cover rodata/vectors/fill/data load/unparsed bytes.
The map and nm list contain the complete linked source/library inventory;
runtime library, HAL, RTOS and callback stack/timing consequences remain unproven.
The measured total delta from B RET6 no-GNSS / `sf6_minimal` is RAM +15680 and
BIN +34392 bytes. It includes target/configuration/logger/GNSS changes and is
not isolated GNSS savings. SF6's 192-byte core has no removed history buffer.

Historical compact queue geometry here: 59 x 200-byte main slots, 16 x 200-byte
estimator slots, 2048-byte aggregation; initial snapshot requires 54 slots,
including all stream descriptors. This geometry is preserved as historical
evidence, not a license to impose Minimal limits on the future Compact tier.

## Executed checks and failures

Commands use emitted `mingw32-make GCC_PATH=... CONFIG=Release HOST_CC=...` targets;
exact argv, UTC timestamps, exit codes, versions and log hashes are in the archive.
ARM GNU 14.3.1, Host GCC 16.1.0, make 4.4.1, Python 3.14.0, PowerShell 5.1 gate.

| Check | Actual result |
|---|---|
| `-B -j2 all` | 0, actual ARM compile/link, source ee7a9be |
| `-B -j2 static-analysis` | 0, actual `-fanalyzer` compile/link, source ee7a9be |
| architecture-check | 0 at checker 821c128; earlier unknown-target/identity/IRQ-owner failures retained |
| power10-check | 0; 5815 checks, 115 first-party C files, 2490 functions, 755 nonblocking recommendations |
| critical-contract review | **NOT PROVEN**, explicitly emitted despite text-check success |
| artifact-check | 0; exact 96 KiB SRAM/no CCM, zero linked heap symbols |
| stack-report | 2; refuses unreviewed `NeoM9nStartup_Init`/`NeoM9nStartup_Tick` caller set after JY901B pruning |
| full emitted host-tests | 2; required positive JY901B capability fixture cannot find unselected `jy901b_imu_build_capabilities.h` |
| list-sources | 0; 151 selected C/S files |
| source identity | 1526 byte comparisons; all 151 linked sources matched; ownership metadata difference remains |
| SCG related first run | 66 passed; development-time scope, not final full-suite acceptance |
| SCG recorded repeat | 65 passed/1 failed: another local pytest invocation reused `.work/pytest`, removing the SD fixture output directory |
| SD MMIO independent rerun | 1 passed using a distinct pytest base; do not stitch this into an unexecuted 66-pass run |

Source identity's only mismatch was `.fccg/ownership.json`: the historical core
checker hash/payload digest after the explicit validation refresh. Project model
was semantically equal; all linked payload/Cube bytes matched. Complete saved
provenance identity remains **NOT PROVEN**. No checker allowlist, assertion,
protocol contract, source coverage, stack threshold or critical gate was weakened.

## DMA boundary fix checkpoint and remaining work

Post-link review found the F1 runtime DMA guard still capped at RET6's 64 KiB.
The new direct Host regression demonstrates RET6 pass / RFT6 last-byte failure
before the fix. Exact target memory headers now publish 64 KiB / 96 KiB DMA SRAM
bounds; the provider checks those bounds without addition overflow. Both target
cases pass (null/zero/outside/end crossing/oversize/full range/last byte).
Two fixture include-path mistakes are retained as failed diagnostics. This
DMA fix is **Host-tested only in this checkpoint**; the earlier ELF above predates
it. Necessary post-fix ARM/static/gate validation is deferred to the next feature
tier generation, not falsely attributed to the existing binary.

B retains fail-closed behavior; complete real CAL/ALIGN/origin/READY admission,
requalification and post-START chain remain FAIL/NOT RUN as recorded in B.
RFT6 SRAM does not resolve the existing IRQ/timebase/runtime recovery boundaries.
GNSS no-fix is not a communication failure; there is no board, navigation accuracy,
WCET, flight qualification, completed critical-contract or whole-firmware original
Power of Ten compliance claim. RET6's separate generated tree and unique no-GNSS
evidence remain preserved. Next work implements the four global tiers independently
of chip selection, with reversible configuration and unchanged safety expectations.

Archive: `../evidence/SF6_RFT6_compile_baseline/rft6_compile_checkpoint.zip`
(4,026,420 bytes, 302 entries, SHA-256
`5f626aab26474cf64142e2173d043951ac3723ad1bd9d85e3c7463764aa4e414`).
Library: `libfile_0ceff9dda25881919d24111e60bad923`, version 0. The archive
embeds this report before these archive-identity lines. Library upload succeeded;
Windows `os.setxattr` is unavailable, so local version-xattr synchronization failed.
