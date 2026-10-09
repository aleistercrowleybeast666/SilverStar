# Complete native classic CDC: isolated first batch

This batch provides **candidate source admission, immutable archival, and a
separate native compilation validator**. It does **not** implement a working
generic Ground runtime backend. Normal Ground generation rejects every project
carrying `native_complete_classic_cdc`, including a forged
`runtime_adapter_enabled=true`. There is no GUI entry or change to daily use.

The branch is `feature/scg-classic-cdc-contract-20261009`, based on daily
`56448bd35736221d7885a26704f2f953b0fe5055`. No integration, push, board access,
flash operation, user project modification, or C071 change is included.

## Interface and ownership boundary

`FccgService.NativeClassicCdcProject_Import(input_path, *, device_facts,
spi_resource, gpio_resources, risk_acknowledged)` returns a **candidate**
`CubeMxImportResult`. It does not update a project model or select an MCU plugin.
The trusted backend caller must supply an independent `NativeDeviceFacts`:
exact part, Cortex core, FPU capability, device define, startup identity and
physical memory banks, together with reviewed evidence identity. Evidence URL
and SHA identify a source; they do not authenticate it. No automatic trusted
device-facts provider has been implemented. Project/IOC/linker claims cannot
self-prove those facts.

The archive retains all admitted native bytes, including Makefile, README,
HAL/CMSIS, startup/linker, clocks/GPIO/IRQ, PCD/PMA/FIFO, middleware and
descriptors. It freezes a canonical contract beside the native tree. Reimport
rejects edited archives/contracts rather than repairing them. Paths, aliases,
case collisions, file/byte limits and portable Windows cache paths are checked.
The native Makefile is treated as inventory data and is never executed.

The candidate checker accepts one literal, closed GNU source/include/define
inventory, one reviewed startup and one literal MEMORY declaration matching
independent banks. Additional assignment operators, unknown memory expressions,
CPU/FPU/ABI mismatches, escaping dependencies, unknown source profiles,
USBX/HS/host/RTOS, non-CDC mode, dynamic USB allocation and unknown callback
markers are rejected. Real SPI handle type/init owner, blocking SPI declaration
variant, GPIO resource/pin inventory and compiled/vector IRQ ownership are
checked in the stated text scope. These checks do not prove GPIO polarity/mode,
clock frequency, timeout progress, allocator capacity or callback semantics.

There are only five implementation/test files:

- `src/silverstar_fccg/hardware/native_classic_cdc.py`: candidate inspection/archive.
- `src/silverstar_fccg/app/service.py`: explicit candidate import operation.
- `src/silverstar_fccg/generator/multi_target.py`: four-line rejection at
  `GroundFiles_Render` entry, plus its diagnostic text.
- `tests/test_native_classic_cdc.py`: real frozen-input admission regressions.
- `tools/validation/native_classic_cdc_compile.py`: separate build validator.

The existing F103/F407 route, model whitelist, platform payloads and C071 files
are unchanged. `multi_target.py` is shared with other work; the new hunk is only
the entry guard of `GroundFiles_Render`. Coordinate any subsequent merge there.

## Compilation and compatibility scope

The validator reconstructs commands from admitted inventory into a new disjoint
output. It compiles every native C/ASM unit and a generated header ABI probe,
checks actual CPP/GAS dependency closure, links the native ARM ELF, and repeats
the C compilation/link with real `-fanalyzer` execution. It checks little-endian
ELF32 ARM, floating ABI, allocated VMA/LMA within independent banks, initial MSP,
actual reset-vector/startup-map ownership and strong external IRQ/vector entries.
The native ST reset entry may be weak **with its real startup body**; an alias to
Default_Handler is rejected. External IRQ strong-owner requirements are unchanged.

Native C uses `-Wall` and errors for implicit declarations, incompatible pointers
and missing returns; the generated probe additionally uses
`-Wextra -Wpedantic -Werror`. This is not a claim that all vendor code has passed
SilverStar's first-party gate or original Power of Ten.

The separately recorded inputs are frozen CubeMX F103C8T6
(`STM32Cube FW_F1 V1.8.7`, Cortex-M3, software float, FLASH64K/RAM20K) and F407VET6
(`STM32Cube FW_F4 V1.28.3`, Cortex-M4, fpv4-sp-d16/hard float,
FLASH512K/RAM128K/CCMRAM64K). Existing reviewed MCU plugin facts supply the
independent test descriptors; no linker-derived physical-memory assumption is
used. All upstream source/license/version bytes are preserved; source inventory,
selected compiler-default dependencies and hashes are in the receipts.

Other STM32 combinations may theoretically satisfy the candidate contract without
a handwritten MCU backend. They are **not tested or qualified by these results**.
C071 native PCD plus its companion is a separate route, not evidence of a
complete native classic CDC input. No new board verification is forced by this
candidate API. Hardware acceptance remains separate and unproved.

## EP0 is an explicit runtime rejection

Reading the actual frozen class/application/core chain confirms why successful
native builds do not establish usable CDC:

- F103 class `usbd_cdc.c:598/602/607/609` passes unbounded `wLength` to Control,
  IN send and OUT receive, and truncates CmdLength to eight bits. Its 512-byte
  control storage can be scheduled for 513 or 65535 bytes by the unsafe path.
- F407 class `usbd_cdc.c:453/457/463/465` clamps data-stage lengths but ignores
  Control's return value. This is not the same F103 overflow finding.
- Both original `USB_DEVICE/App/usbd_cdc_if.c` SET/GET_LINE_CODING branches are
  empty and return OK, so GET does not publish valid current line coding.
- Setup, class, core, I/O and LL return propagation must be reviewed as one
  chain. An LL implementation that currently returns HAL_OK does not justify
  assuming all future native targets do so.

These originals are archived only as rejected runtime candidates. No middleware
is patched blindly or generalized into a working backend. The unconditional
generation guard is the present enforcement boundary. A future runtime adapter
must positively recognize an audited native structure or apply an independently
reviewed SCG-owned copy, and reject everything else. Do not enable this route
after merely adding a CDC include or obtaining a successful build.

GET_LINE_CODING must return the initialized prefix `min(wLength, 7)` for legal
short IN requests; requiring every GET to have length 7 would be wrong. SET must
validate setup and actual payload length before publication. Oversized/malformed
requests and LL failures need ordinary error/stall/cancel paths, not fatal
assertions replacing external-input handling.

The independent review reference is
`C:/Users/chdxm/Documents/Codex/2026-10-09/task-2/c071-ep0-independent/review.md`.
No unreviewed changes from that worktree or C071 commit b90292c are copied here.
Shared EP0 repair is owned by the parent's coordination with that implementation
task; this branch introduces no overlapping USB payload edits.

## Remaining acceptance work

Runtime adapter/source graph integration; recognized EP0 request-chain repair
and end-to-end fault tests; immutable TX ownership/completion/ZLP; receive rearm
and lifecycle/reset/disconnect invalidation; PCD/IRQ ownership propagation;
static class allocator capacity; finite SPI timeout and coherent tick progress;
real GPIO mode/polarity/clock resources; independently justified microsecond
delay without default DWT; single-core PRIMASK restoration; caller-handled LL
status failures; complete manual critical contracts, linked stack/WCET and
hardware evidence are **NOT PROVEN**. Optional register observations must use
`valid=0` where unsupported, never fabricate an `Instance->SR` contract.

No first-party target runtime safety change has been made in this batch. Fresh
legacy-generated architecture/Host/Power10 results are recorded separately from
native compile results and retain the manual critical-contract NOT_PROVEN output.
A tool exit zero does not certify a complete backend or full-suite compliance.

Exact run results, all failures, command logs, tool versions, auditable source
snapshots and artifact hashes are recorded in the evidence receipt beside this
document's evidence directory.

Final recorded results:

| Scope | Result |
| --- | --- |
| Candidate regressions, final `10g` source | 56 passed, zero failures/skips; existing pytest `cache_dir` warning retained |
| F103 native final `10f` | 34 native C + one ABI probe + one ASM, ARM link and real analyzer second build executed; individual commands exit zero; validator exits 1 because two vendor UART analyzer warnings block no-warning acceptance |
| F407 native final `10f` | 43 native C + one ABI probe + one ASM, ARM link and real analyzer second build executed; individual commands exit zero; validator exits 1 for the same two analyzer diagnostics |
| Legacy regression selection `10b` | 41 passed / one existing failure, reproduced on frozen daily HEAD with its actual package path |
| Three freshly generated legacy Ground targets `10b` | Exact emitted architecture-check, host-tests and power10-check exit zero for F103 USB/UART and F407 USB; critical-contract review remains NOT_PROVEN |

The existing failed regression is
`test_one_bmi088_plugin_resolves_mixed_interfaces_without_duplicate_sources`:
F1/F4 SD plugin variants share `(Generic, SD/TF Card, STM32 SDIO)` physical
identity. This batch does not edit that test or the frozen plugin variants.
It is not a full-suite PASS.

The legacy generation snapshot predates the final file-read buffer refinement
in the newly added candidate module and warning-failure refinement in the new
validation script. Its service/generator and all legacy
payload bytes are identical to the final sources; both snapshots are recorded
separately. Final native compile receipts and candidate regressions cover the
final candidate module. Earlier compile/test passes are not substituted for
these runs. Failed ABI probes, serialization/cache errors, the pre-fix Make and
MEMORY acceptance cases, and interrupted tests are retained with explanations.

The final native analyzer diagnostics are potential null dereferences of
`pdata16bits` in `HAL_UART_Transmit` (F1:1183/F4:1180) and
`HAL_UARTEx_ReceiveToIdle` (F1:1657/F4:1662). They require independent review;
this batch does not classify them as false positives, change upstream files,
exclude source units, suppress warnings or claim no-warning acceptance. The
validator records every diagnostic and fails after preserving the completed
compile/link/closure evidence. Earlier commentary claiming no warnings was
incorrect and has been corrected.
