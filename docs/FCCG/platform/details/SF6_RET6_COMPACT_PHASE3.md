# SF6 compact RET6: no-GNSS compile candidate, acceptance blocked

Recorded 2026-10-05 20:18 UTC. Implementation commit:
`4d49ab2819e2bd2b5bf34dab09d8ec6d65085645`, isolated branch
`codex/sf6-compact-ret6`, based on KF6 candidate
`7fa06c4155661e40847c0af78f4b23f3659b995d`.

This is a **compilation candidate, not an accepted safety batch**. Four physical
modules failed the real RET6 link in phase 2. The explicitly authorized fallback
retains MPU6050, BMP280, E28-2G4M12SX and local SSLOG, removes physical GNSS,
uses SF6 and disables maintenance. The final candidate links, but logger burst,
architecture and stack gates fail. Critical-contract review remains NOT PROVEN.
The 20% RAM-spare goal is not met. No hardware/serial/probe/flashing occurred;
stable, GSHC, FLP and the parallel FLP worktree were not changed. No merge/push.

## Actual official hardware generation

Official STM32CubeMX 6.15.0, its bundled Java and the installed official
STM32Cube FW_F1 V1.8.7 generated the RET6 project. The input is
`.work/cubemx_flight/SF6_RET6_Hardware/SF6_RET6_Hardware.ioc`.
The final script loads this actual IOC, resets USART1 Asynchronous and PA9,
PA10, PA1 and PA3, waits for clocks, saves and calls `project generate`.
The complete log records successful generation. This was neither a hand-written
mock IOC nor a project assembled without running CubeMX.

The first no-GNSS reset attempt used `set pin ... Reset_State`, which CubeMX
rejected. Its complete failure log is retained. CLI help established the actual
`reset pin` / `reset mode` commands, and the subsequent official run succeeded.
The final import reports no UART enabled. No UART DMA or fallback fake UART is
used. An IOC function-order string still mentions USART1; the actual peripheral
inventory, pins and generated main contain no USART initializer.

```
"C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/jre/bin/java.exe" -jar "C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/STM32CubeMX.exe" -q .work/evidence/cubemx_no_gnss_final.script
```

Actual configuration: STM32F103RET6, 512 KiB flash, 64 KiB SRAM, no CCM/FPU;
64 MHz HSI/PLL, APB1 32 MHz, APB2 64 MHz; Cortex-M3 / `-mfloat-abi=soft`;
I2C1 PB6/PB7, SPI1 PA5/PA6/PA7, SDIO PC8/PC12/PD2 one-bit, PC7 detect;
TIM6 HAL tick independent of the RTOS SysTick; official CM3 FreeRTOS port.
F1 HAL uses a single DMA2_Channel4 SDIO handle linked to both RX and TX, changing
direction per transfer. Source-graph validation requires those actual links,
the actual IOC DMA instance and the combined channel IRQ. Missing/wrong links
are rejected. Card and radio IRQ priorities obey the RTOS ceiling of 5.

## Generation and behavior

Compact remains opt-in and generic: at most one physical IMU, GNSS, telemetry
and barometer, without a brand restriction. Normal configuration serialization,
context bounds and default resources remain unchanged. Normal generation still
preserves user-owned payload; all validation uses the isolated output only.

Compact definitions now precede configuration headers. This prevents a header
from allocating the normal GNSS-origin arrays before seeing the target's
generated capability. A selected GNSS retains 100 samples; absent physical
GNSS has a one-element storage sentinel and no origin-collection execution.
No GNSS core/UART provider is added to the no-GNSS source graph. The existing
SF6 state is 192 bytes; this work does not claim removal of SF6 history.

Absent physical GNSS produces `SYSTEM_DEVICE_UNSUPPORTED` from the GNSS READY
query, with supported/ready/origin/count cleared. Navigation/START readiness is
checked separately. Actual Host lifecycle tests demonstrate IMU+barometer START,
unchanged rejection for barometer/storage faults, no accidental GNSS-origin
publication and no fusion-ready GNSS claim. These use real lifecycle/alignment
code with sensor/storage Host fixtures, not MCU evidence.

An absent POWER implementation is resolved at generation/compilation, rather
than leaving disabled POWER references for the linker or inventing a backend.
The normal default remains available. Source inventories and EIDE agree on the
selected F1 platform and FatFs objects. The old generated polled SD adapter and
unselected alternative FatFs drivers are excluded; selected `ff`, `diskio`,
`ff_gen_drv` and the owned F1 DMA adapter remain in the authoritative graph.

The F1 DMA wait is deadline-bounded and yields; failed/incoherent completion
poisons the adapter until MCU reset so an uncertain transfer cannot reuse its
buffer. R0.11 append checks `f_lseek(f_size(...))`; failed publication/close
retains quarantine semantics. Automatic storage hotplug/recovery is not added.
Unattended infinite retry/backoff and START-locked same-instance IMU recovery
are **not implemented or proven** in this candidate. Existing IMU re-init can
clear internal lock state; this remains a blocking recovery review item.
GNSS no-fix semantics were not redefined as a communication failure.

## Actual linked resource result

Final Release ELF was freshly built from the implementation recorded above.
`arm-none-eabi-size`: text 213908, data 408, bss 64432. The size tool's bss
includes the separately reserved 2048-byte MSP. The map's `.bss` is 62384;
RAM is `408 + 62384 + 2048 = 64840`, not bss plus stacks a second time.
BIN flash load is 214320/524288 bytes (40.878%). RAM spare is 696/65536 bytes
(1.062%). The 20% spare target permits at most 52428 bytes; the gap is 12412.

| Map category | Bytes | % of 64 KiB |
|---|---:|---:|
| Static task stacks, already in `.bss` | 21504 | 32.812 |
| Sample/log queues | 16720 | 25.513 |
| Algorithm and origin state | 5383 | 8.214 |
| Other logging | 2654 | 4.050 |
| Device state | 5735 | 8.751 |
| Platform/vendor/RTOS | 2190 | 3.342 |
| Other state | 8384 | 12.793 |
| MSP reservation | 2048 | 3.125 |
| Alignment fill/unparsed | 222 | 0.339 |

The four-module phase-2 map needed 75120 bytes (9584 overflow) and still had
unresolved POWER references. The final fallback reduces RAM by 10280 bytes;
this is a bundled actual difference including GNSS/platform/capability removal
and the changed log budget, not an isolated claim for the old M9N driver alone.
The intermediate 62016-byte fallback linked but failed logger burst with 2181
drops. Restoring queue/aggregation capacity increased RAM by 2824 bytes and
reduced that failure to 914 drops; it did **not** fix it.

The snapshot has 53 slots: one system record, nine device descriptors, three
algorithm descriptors and all forty stream descriptors, including disabled
streams. The normal queue is 58 records (200 bytes each), estimator queue 16,
aggregation 2048. All startup descriptors fit. Task stacks were not reduced
to force the image into RAM; unresolved call bounds forbid such a claim.

## SX128x scratch capacity audit

Compact selects the existing bounded 260-byte HAL path; normal Flight retains
4095 bytes. Both TX and RX scratch objects therefore occupy 520 actual map
bytes. In the selected `sx1280.c`, fixed write/read commands reach 8/5 payload
bytes; sync words are at most 5, register scalar/CRC/address calls at most 4;
packet-buffer operations accept `uint8_t` lengths at most 255 (2/3-byte headers).
The Intel HEX parser can publish at most 255 data bytes; a count reaching 256
returns failure before the register write. Generic register reads support 256
plus four header bytes, generic writes 257 plus three; larger requests assert
before access or GPIO/SPI publication. IRAM clear writes all `IRAM_SIZE` bytes
in contiguous chunks at unchanged addresses, at most 257 data bytes each.

The existing actual-HAL Host fixture was executed, covering full 255-byte packet
read/write, 256-byte register read, 257-byte register write, zero-length/null,
complete IRAM chunks, oversized command/register, null payload and invalid
instance traps before transfer. Six pytest cases pass. The trap interception
uses Host-only setjmp/longjmp and is not target firmware or MCU recovery.
This establishes the audited transfer-size boundary, not all third-party
parser semantics, radio timing, SPI failure handling or whole-program safety.

## Executed checks and blockers

Commands ran inside `.work/generated_ret6`, with existing ARM and MSYS2 paths
prepended. Python is the existing FLP venv executable only, not a modified FLP
environment. Complete logs, manifest, map, ELF/BIN/HEX and `.su` files are in
`docs/FCCG/platform/evidence/SF6_RET6_phase3/phase3_complete_evidence.zip`.

| Command/scope | Exit/outcome |
|---|---|
| SCG import, validate, Plan/Apply | PASS, 1504 files; manual-hardware and unqualified CM3 timing warnings retained |
| `mingw32-make -j4 all` | 0, actual full ARM compile/link |
| `mingw32-make -j4 static-analysis` | 0, actual ARM GCC `-fanalyzer`, then link; not syntax-only |
| `mingw32-make power10-check` exactly emitted | 0 text checks; critical-contract review NOT PROVEN |
| `mingw32-make artifact-check` | 0, RET6 bounds/no CCM/no heap/addresses |
| `mingw32-make architecture-check` | 2, device/System layer violation |
| `mingw32-make stack-report` | 2, unresolved `SensorRegister_Read` |
| `mingw32-make host-tests` full emitted run | 2 at job 8/70; jobs 1–7 passed; job 8 requires absent GNSS and fails its positive compile expectation; 9–70 NOT RUN |
| Explicit five-job Host selection | PASS, 5 executables/1438 checks; no full-suite claim |
| Four selected pytest files | 0, 21 passed; compact 11, mechanization 3, cold barometer 1, actual HAL capacity 6 |
| Storage integrity full runner | 1; startup-burst genuine drop failure; later cases NOT RUN |
| RET6 hardware/WCET/flight | NOT RUN, no board available |

ARM compilation uses all strict first-party warning flags with `-Werror`.
Both full links nevertheless emit four upstream nosys/newlib warnings:
`_close`, `_lseek`, `_read`, `_write` are unimplemented. This is not a
warning-free whole-firmware result; their reachability/consequences remain
NOT PROVEN. The static analyzer exit is not a proof of critical contracts.

Power10 reports 5188 checks, 110 first-party C files, 2194 functions, 1365
syntactically eligible candidates and 625 nonblocking recommendations. Mean
0.622151 remains informational. It explicitly reports manual acceptance
pending/critical-contract NOT PROVEN. No original Power of Ten/NASA certification
claim follows. No thresholds/allowlists/assertions were weakened.

Architecture reports 320 checks and one aggregated failure comprising eight
device-layer includes of System interfaces/config/version. Expanded emitted
device coverage exposes BMP280/MPU6050/SensorBus/SdStorage paths, rather than
hiding these installed sources. These existing boundaries need an owned
adapter/native-type review before acceptance.

Stack analysis terminates on the actual indirect SensorRegister_Read path.
Its local `.su` frame is not a callee bound. Whole task paths, vendor callbacks,
libraries, dynamic frames, MSP and ISR nesting remain NOT PROVEN; retained task
stack sizes and 696 spare SRAM bytes are not a safe stack margin.

Storage Host run passed 10000 writes/1668166 bytes and 40000 SSLOG records/
3596803 bytes, with byte/sequence/end checks. Seven DMA fault scenarios preserve
no-reuse behavior; timeout read/write are bounded to 30996 ticks, wrong-event
1000, start failures 997 and sync timeout 30997. Initial missing/no-filesystem,
I/O failure and manifest/post-write faults retain ordinary error behavior.
Host timing and `TARGET_BENCH_HOST` are not STM32 timing evidence. The normal
startup-burst then fails at unchanged line 424 with normal 58/58, estimator
16/16, 914 drops and 209 jitter stalls (20–100 ms). This blocks log acceptance.
The following startup-burst-overload and later sparse cases were not executed.
R0.11 Host ABI/format preparation was adapted without changing drop/fault
expectations: fixed 32 MiB Host card uses a 1024-byte FAT16 cluster because the
old 512-byte geometry straddled R0.11's FAT32 threshold. Earlier failures remain
in evidence.

Barometer-only positioning still has horizontal inertial drift. No claim of
nondiverging horizontal position, navigation accuracy, timing qualification or
hardware readiness is made. Minimum useful assertions, call graph acyclicity,
fallible-return review and all nine other manual rule obligations are unresolved.

## Reproduction and provenance

Tools: ARM GCC 14.3.1 20250623, GNU Make 4.4.1, Host MSYS2 GCC 16.1.0,
Python 3.14.0, PowerShell 7.6.5 (emitted gates use Windows PowerShell).
The evidence manifest records complete commands/exits, hashes, implementation
commit and configuration. Generated files are hashed separately from Git source;
the old 62016 image is never attributed to the 64840 configuration.

The repository retains the earlier phase-1/phase-2 reports and dated failures.
The existing first-phase Library package is
`SilverStar_SF6_RET6_f2897b3_review.zip`, 6595258 bytes,
SHA256 `de919c06c5f0675d9fb72b6f9afaa03be629a50ec1361479bef79cbe6aec7289`,
Library `libfile_e0ce9e0dcf208191a8602d4b79284ba7`,
File `file_000000001df481fd9d9ba78f1d1495c0`. It contains all 369 committed
changed/new files and the full 7fa→f289 patch, including official vendor provenance.
The phase-3 review delta is a separate package based on f289; no full-repository,
venv or historical-build clone was made.

At 20:18 UTC the D volume had 21174759424 bytes free. No E drive, disk-wide
scan, permission/driver change, other-user cleanup or GUI shutdown was used.
The isolated candidate and key prior proofs are retained; no hardware or
publish/push action was attempted. Cross-thread forwarding of package IDs/status
was rejected by automatic approval review because direct authorization for that
specific message was absent; no message was sent or bypass attempted.
