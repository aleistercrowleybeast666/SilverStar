# Ground complete CubeMX base and classic USB CDC — 2026-10-09

## Scope and ownership

This change implements the first controlled complete-CubeMX Ground import. The
accepted profiles are STM32F103C8T6 (64 KiB Flash/20 KiB RAM) and STM32F407VET6
(512 KiB Flash/128 KiB main RAM). The exact approved CubeMX/package pairs remain
6.15.0 + CubeF1 1.8.7 and 6.15.0 + CubeF4 1.28.3. Inputs must contain one root
`.ioc`, generated GNU Makefile, copied HAL/CMSIS, matching GNU startup and linker.
The importer reads literal inventory assignments; it never runs the input
Makefile. External dependencies, expressions, wrong CPU/memory/startup, missing
files, RTOS, USBX and unsupported USB layouts are rejected.

`CubeMxProject_Import(..., target="ground")` selects the new policy. Its default
`target="flight"` retains the established import behavior and strict source
ownership. No persisted schema version changes. GUI routing must explicitly
pass `target="ground"`; GUI files are outside this change.

Imported Ground owns HAL, CMSIS, `system_*`, startup, linker and classic USB
middleware under `HardwareGenerated/STM32CubeMX`. SCG owns generic Ground,
PcByteStream and thin Platform adapters. Plugin HAL/startup/linker and old board
include directories are omitted from this Ground source graph. Makefile,
source-graph JSON and EIDE use this resolved inventory. Frozen snapshot artifact
hashes are checked before assembly; changing an imported snapshot requires a
fresh import. Input project files are never changed by the importer.

## USB contract and review

The generated adapter owns a 512-byte RX ring (511 usable bytes) and a 70-byte TX
buffer. It accepts a TX only when the classic class is configured, its class
pointer exists and `TxState == 0`. It copies the caller's bytes before passing
its own static buffer to the stack. `OK` means accepted, not physically delivered;
BUSY retains Ground's queued frame. `TxState` remains authoritative through a
trailing ZLP, supporting both F1's older interface without TransmitCplt and F4's
newer callback structure. No newer USB library is substituted into the F1 base.

Reset/deinit/disconnect hooks clear the RX ring and publish a reset flag. The
main loop consumes the flag and resets the parser and pending PC queue in main
context. Diagnostics remain accumulated. This intentionally aborts old-session
queued traffic; it does not claim delivery or replay. F103 without VBUS sensing
cannot detect physical unplug immediately; reset on reconnect still starts a
new stream session. Electrical behavior requires hardware qualification.

Critical implementation review performed for the changed adapter:

- Write masks interrupts across class state/pointer inspection, bounded copy
  and stack submission, preventing reset or completion from invalidating the
  checked state. Every normal return restores the previous PRIMASK.
- RX has one ISR producer and one main consumer. Read/reset use a bounded
  critical section; producer publishes bytes before head with `__DMB`. This
  assumes one USB FS callback producer, no RTOS and no NMI producer.
- All adapter loops have explicit 512/70 bounds, all buffers are static, and
  overflow accounting saturates. No heap allocation is introduced.
- USB pins PA11/PA12 are reserved in resource conflict checks. The importer
  checks generated interrupt dispatch, PCD module, declared 48 MHz and literal
  HSE/PLL arithmetic, F103 nonoverlapping 512-byte PMA allocation, and F407
  RX/TX FIFO allocation within 320 words. This validates source configuration,
  not the installed oscillator or board wiring.
- Optional classic USB header switches missing from CubeMX configuration get
  their ordinary zero default in build definitions; explicit imported settings
  remain authoritative. First-party conditional-compilation policy is retained.
- Ground alone uses the existing `AIR_LINK_HAL_BUFFER_SIZE=260` SDK option.
  This accommodates the maximum 255-byte radio payload plus command bytes and
  avoids two 4095-byte SDK scratch buffers on F103. Flight settings are unchanged.

This limited review is not complete Power-of-Ten compliance, a complete critical
call-graph review, or MCU timing/recovery acceptance.

## Executed validation

Base commit: `6fe76d87d05de6b7528e74d9c423df6d9217e47f`.
Isolated branch: `codex/f103-ground-usb-20261009`. No push, merge, hardware access,
serial opening, flashing or START was performed. The field project
`D:\stm32_project\SS_0_5_TEST_FINAL` was not modified.

Tools: official CubeMX 6.15.0; Arm GNU GCC 14.3.1 20250623; native Host GCC 16.1.0;
native mingw32-make 4.4.1; existing Python 3.14 environment. Official installed
CubeF1 1.8.7 and CubeF4 1.28.3 supplied their own HAL/CMSIS/classic USB libraries.
CubeMX CLI was run with its bundled Java and `-jar STM32CubeMX.exe -q <script>`;
the scripts use `config load`, `project name/path`, `setCustomFWPath`,
`project toolchain Makefile`, `SetCopyLibrary "copy only"`, and `project generate`.

All three projects were actually generated by CubeMX, imported through the
service with Ground policy, assembled using `TargetGeneration_Apply(GROUND)`,
compiled and linked with ARM GCC, then checked with emitted targets:

```text
mingw32-make -C <Ground_Station> -j2 all architecture-check host-tests \
  artifact-check power10-check static-analysis \
  PYTHON=D:/python_software/SilverStar/.venv/Scripts/python.exe \
  HOST_CC=D:/msys64/ucrt64/bin/gcc.exe
```

| Official CubeMX sample | C sources + startup | text | data | bss incl. stack | RAM unallocated | Result |
|---|---:|---:|---:|---:|---:|---|
| F103C8 USB CDC | 50 + 1 | 36,136 | 380 | 11,992 | 8,108 | all emitted targets exit 0 |
| F103C8 UART DMA | 39 + 1 | 27,264 | 12 | 7,576 | 12,892 | all emitted targets exit 0 |
| F407VE USB CDC | 60 + 1 | 36,488 | 248 | 14,784 | 116,040 | all emitted targets exit 0 |

Sizes are bytes; Flash use is text + data. Linkers reserve 2048 bytes of stack,
zero heap; size's bss category includes the reserved stack section/alignment.
F407's CCM RAM is not used. The build emits map, ELF, BIN, size and `.su` files.
Artifact gates check ELF/BIN identity, memory bounds, required symbols and linked
source inventory. Architecture gates check one main/startup/linker, Ground
initialization and resolved resources, with no Flight task/FatFs startup.

Power10 text gates: F103 USB 495 checks/16 first-party C files/180 functions;
F103 UART 499/16/182; F407 USB 634/21/232. Runtime assertion recommendations remain
informational, and `POWER10_CONTRACT_REVIEW|NOT_PROVEN` remains visible. Actual
static-analysis compilation used `-fanalyzer` on first-party sources with the
strict emitted warnings, compiled vendor sources under their separate policy,
and linked analysis ELFs. Initial analyzer compilation is in
`*-quality-final.log`; final incremental acceptance is in `*-release.log`.

Targeted pytest: **68 passed, 1 deselected** in 132.52 seconds. Covered complete
base parsing, changed-snapshot rejection, missing/unsafe/wrong-MCU inputs,
ambiguous IOC, generated HSE/PLL mismatch, old Flight IOC compatibility, source
graph/targets, CDC ownership/ring/backpressure/reset and UART DMA behavior.
The excluded case is the pre-existing
`test_one_bmi088_plugin_resolves_mixed_interfaces_without_duplicate_sources`:
`sd_sdio_fatfs` and `sd_sdio_fatfs_f1` claim the same physical component identity.
This unrelated catalog issue was reproduced before this implementation and is
not fixed or silently waived. This is not a full-suite green claim.

The generated Host executables also pass separately for each target. CDC tests
cover disconnected BUSY, retained TX bytes after caller mutation, outstanding
TxState/ZLP backpressure, failed/invalid requests, RX overflow/wrap, reset and
PRIMASK restoration. Bridge Host tests verify reset clears queued traffic while
preserving diagnostics. The separate before/after lifetime probe uses the pinned
old renderer: baseline exits 23 after caller mutation; repaired adapter exits 0.
HAL/radio are mocks; none of these results prove MCU recovery or USB enumeration.

Compiler stack frames on USB: PcByteStream_Write 16 bytes, Read and OnUsbReceive
32 bytes each; GroundBridge_Process 192 bytes. Observed direct-call frame sums
include main initialization 600 bytes on F103/616 on F407 and one Process path
464 bytes. These are partial observations, **not upper bounds**: indirect USB
callbacks, library functions without `.su`, tail calls and nested interrupts
remain. Worst-case stack/ISR latency/radio timing are **NOT PROVEN**.

## Evidence and reproducibility

Local evidence root:
`C:\Users\chdxm\Documents\Codex\2026-10-08\task\usb-validation`.
It contains the three `cube-*` IOC inputs/official generated files, exact
`generate-f103.txt`/`generate-regressions.txt` CLI scripts, CubeMX logs,
`generate-ground.py`, generated target ownership/model files,
`generation-results.json` with snapshot/output hashes, `*-release.log`, original
analyzer logs, `relevant-regressions-final2.log`, `tx-lifetime-final.log`,
`reproduce-tx-lifetime.py`, `collect-evidence.py`, `linked-evidence.json`, linked
symbol/disassembly files and all map/`.su` outputs. No vendor cache or full repo
was committed. Only small IOC inputs and validation recipes are retained with
this change's docs.

The recipe deliberately retains installed official `License.md` and
`Package_license.md` in disposable inputs; CubeMX copy-only omitted package-level
notices. F4 USB's component LICENSE.txt is also preserved. Original vendor source
notices remain. F1 classic USB 2.5.3 points to SLA0044 and its package SBOM lists
USB under SLA; F4 classic USB 2.11.4 refers to Package_license/SLA0044 fallback.
Do not label these USB sources BSD based on HAL's separate license.

Earlier failed attempts are retained where available: headless Java is unsuitable
because CubeMX constructs a hidden Swing frame; restricted preference/log writes
prevented initial CubeMX run; MSYS make had sandbox signalpipe/shell problems,
so native mingw32-make was used. Windows long temporary paths affected a snapshot
fixture; a short private pytest temp directory resolved it without weakening
hash checks. An initial Host probe had a stub-symbol mismatch, repaired before
the successful before/after probe. A pytest invocation with the wrong relative
test path ran zero tests and is not counted as validation.

## Remaining acceptance steps

GUI must route the Ground import button to `target="ground"` and be checked with
one complete CubeMX directory and one rejected IOC-only directory. Its separate
GUI commit is not merged into this isolated worktree.

Hardware execution requires separate bench authorization/readiness. After
checking the exact board, HSE, PA11/12 wiring and USB pull-up/VBUS implementation,
qualify enumeration, bounded status transfer, busy backpressure, partial frame
reset, disconnect/reconnect, overflow recovery and invalid-frame rejection.
Measure stack high-water and IRQ latency under worst intended traffic. Use only
the named Ground board and approved test images; do not flash or start Flight
or the field project as part of these software gates. Hardware results remain
pending; no delivery or safety approval is implied by a linked image.
