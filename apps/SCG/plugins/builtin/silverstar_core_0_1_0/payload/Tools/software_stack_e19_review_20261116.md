# Software stack input review, 2026-11-01

## Authority and acceptance boundary

This review describes the source/object reasoning required by each explicitly
enrolled case in `software_stack_inputs.json`. An empty case list accepts no new
firmware. The checker never creates or updates a case. A case is admitted only
after source review and real compiler/linker execution of candidate A. Delivery
acceptance additionally requires a second normal generation B in a different
directory, a real independent rebuild and equality of every sealed artifact.
B contains the frozen proof manifest and validates it; B never enrolls itself.
The case seals
all selected C sources, project headers, assembler/linker inputs, Make declarations,
compiler tools, installed C ABI headers, actual linked archives/CRT objects,
every selected object and `.su`/`.d`, and the complete ELF/map. This document's
actual bytes are checked against the case's SHA-256. The manifest's actual bytes
are checked against the owning checker's explicit constant.

Builds use `-ffile-prefix-map="$(CURDIR)"=.` for C and assembly. Nothing strips
DWARF, executable sections, symbols or relocations to make artifacts match.
Project configuration fingerprints exclude component/reference provenance and
decoder packaging metadata; proof files therefore do not recursively change
the compiled project configuration. The final evidence records raw hashes and
the results of independent real builds. Compiler installation paths are an
explicit environment boundary of these cases, not silently normalized data.

This is a conservative software stack bound, under the normal C object model and
Cortex-M exception semantics. It is not a proof against arbitrary memory
corruption, hostile changes to vector/TCB memory, malfunctioning silicon, stack
high-water measurement, interrupt latency, WCET or flight qualification. Those
hardware observations remain separate requirements. No memory budget, stack
margin, source-coverage rule or callback-registration policy is weakened here.

## Direct code, libraries and dynamic frames

The analysis uses actual ELF `FUNC` extents. NOTYPE assembler labels inside reset
or libgcc routines do not terminate an enclosing function. Overlapping libgcc
entries each retain their shared suffix; equal local names at distinct addresses
are distinct entries. A source `.su` frame is combined with the linked machine
frame using the larger value, including naked and inline-assembly functions.
Positive stack-growth loops, recursive local BL helpers, unknown SP assignments,
unresolved indirect sites and recursion in a reachable call graph reject proof.

Conditional calls and indirect PC writes are included. GCC switch tables require
the actual local bound, non-bypassable guard and every linked table target. A
tail branch to a returning function is a returning path: it must not mark an
initializer noreturn and erase the task's permanent business loop. This defect
was reproduced and corrected before any new case was accepted. The invalid
early diagnostic is retained as failed analysis, not a smaller accepted budget.

The budgets conservatively add complete function frames even for tail calls;
they do not subtract caller frames to manufacture margin. Selected newlib/libm
and libgcc instructions are analyzed alongside application code. Their exact
archives and linked executable bytes are sealed. Library routines unreachable
from reset, enabled tasks and actual vectors are inventoried outside those
entry closures; they do not establish an execution path merely by being linked.

## HAL handle objects and callback origins

The exact F407 selected input declares UART `huart1`/`huart2`/`huart3`, six
`hdma_usart{1,2,3}_{rx,tx}` objects in `Core/Src/usart.c`, and
`hdma_sdio_rx`/`hdma_sdio_tx` in `Core/Src/sdio.c`. The H743 imported input
declares `huart1`/`huart2` and four `hdma_usart{1,2}_{rx,tx}` objects under
`HardwareGenerated/STM32CubeMX/Core/Src/usart.c`. H743 SDMMC uses its internal
DMA and does not add an external DMA handle. Each case records the linked BSS
address/size and declaring source for every object. Acceptance additionally
requires the object to lie wholly inside actual `_sbss`..`_ebss` initialization
boundaries. The selected reset assembly clears that interval before `main`.

The CubeMX MSP initializers assign peripheral instances and use `__HAL_LINKDMA`
to bind UART/SD `.hdmarx`/`.hdmatx` and the reciprocal DMA `Parent` pointer.
Selected IRQ wrappers pass the corresponding global handle address directly.
The platform UART resource tables contain those same handle addresses; receive,
transmit and abort pass that typed handle into the HAL. The selected SD BSP uses
the one SD handle. These handles are not copied as structures, filled from
packets, replaced by arbitrary pointers, or passed through a runtime registry.
Handle field writes and whole-object references were reviewed together, including
direct `.field` assignments, macro expansion and copy/memory functions; the
callback-assignment regex alone is explicitly not this alias/object proof.

In `HAL_DMA_IRQHandler` and `HAL_DMA_Abort_IT`, callback loads are from the DMA
handle parameter. `HAL_UART_IRQHandler` loads RxISR/TxISR from its UART handle,
and an abort callback from its typed `.hdmarx`/`.hdmatx` child. Thus identical
numeric offsets in different types are not accepted merely as an ABI match.
Actual linked DWARF member offsets, all reaching register definitions at each
indirect instruction, linked addresses and target domains must match the case.

UART DMA start installs fixed transmit/receive/half/error callbacks; UART error
abort installs the fixed `UART_DMAAbortOnError`. F407 SD DMA start installs its
fixed SD transfer/error callbacks. The case includes the union of each linked
field's possible targets across handles, deliberately overestimating paths.
No fixed callback target is dropped just because a particular hardware status
would usually avoid that branch. Direct weak HAL callbacks remain ordinary
linked call edges.

DMA M1 completion fields start at BSS zero and have no linked non-NULL setter
in these single-buffer configurations. The H743 DMA-only UART input similarly
keeps RxISR/TxISR zero: interrupt-mode start/install routines and their target
handlers are absent from the linked executable; abort/error cleanup may clear
them again. HAL guards NULL before calling. The selected HAL configuration
disables UART runtime registration. DMA registration APIs that accept an
arbitrary callback are not linked or referenced by selected application C.
These facts, the real initialization interval and the complete source/ELF
closure establish NULL-only fields. A NULL assignment in an unrelated or
unlinked deinitializer is never sufficient evidence on its own.

## Existing fixed application and FatFs bindings

The existing exact `SD_Driver` table, linked read-only callback bytes, sole
`MX_FATFS_Init` registration and dispatch slots remain checked. The H743 owned
diskio/BSP replacement does not authorize another registry. Selected immutable
device-startup operation tables retain their existing caller, table-byte and
M9N recovery binding checks. F407 cases use JY901B; the H743 ESKF20 case uses
the existing exact BMI088 raw-I2C profile proof in `BmiCallbackBindings_Resolve`,
including its fixed preparation/frame-read callbacks, body hashes, linked
profile bytes and initialization callers. MPU6050 remains a separate exact
proof. None of these profiles is granted a new callback domain by this review.
Changed headers are only admitted by the complete new sealed input case;
old callback tests and their negative cases retain their historical gate.

## RTOS stacks, startup, constructors and terminal paths

`APP/Src/app_tasks.c` creates its seven fixed application task entries with
`xTaskCreateStatic`, matching their actual static stack symbols. The selected
FreeRTOS configuration has no software timer task or dynamic task creation.
The scheduler creates its fixed idle task through the established idle storage
hook. Task entry pointers are stored by the sealed FreeRTOS initialization path,
not dispatched through a new runtime registry. Every enabled entry and actual
stack allocation is budgeted; unexpected task entries/allocations reject.

The enabled PID/LQR cases additionally seal the generated control runtime JSON
and require the actual `AppTask_Flight` transitive closure to contain
`ControlResearch_Process`, `ControlResearchBackend_Step`, and the selected real
`ControlPid_Step`/`ControlLqr_Step`. A linked but unreachable kernel is not proof
of scheduled control. Disabled cases reject a linked control math kernel. The
largest reported task chain may still be alignment; this explicit closure
check prevents that presentation from hiding a missing control path.

Actual reset code loads `_estack`, initializes data/BSS, invokes the bounded
linked initialization arrays and calls `main`. CRT preinit/init endpoints and
all array pointers are read from the ELF. `frame_dummy`'s weak clone-registration
target is linked NULL, guarded by CBZ before BX, with no guard bypass. This is
not an assumption that arbitrary constructors are stack-free. The selected
`main`/reset terminal loops do not call CRT finalization; any new reachable
constructor/finalizer changes the sealed code and requires review.

The actual FreeRTOS CM4F/CM7-r0p1 port instruction sequences are checked.
`prvPortStartFirstTask` reloads MSP from VTOR and enters SVC; the sealed initial
EXC_RETURN is `0xfffffffd`, selecting task PSP. SVC restores the controlled task
context. PendSV saves r4-r11/LR and possibly s16-s31 on PSP, uses exactly its
observed MSP local frame for the scheduler call, then restores PSP. The port's
SP writes are admitted by those exact instruction contracts, not a blanket
unknown-SP exception. Task allowance remains 256 bytes: hardware core+FP104,
software100 and possible alignment4, rounded upward. The minimum spare margin
also remains 256 bytes.

Assertions/fault loops are terminal machine paths, not recovery or recursive
re-entry. The call graph still includes the assert/failure frame before the
terminal instruction. Host setjmp/longjmp interception never participates in
this target graph. Arbitrary repeated hardware faults that cause architectural
lockup are not reported as MCU recovery.

## Main/MSP and exception nesting

The full linked `g_pfnVectors` table is read and sealed. Its initial MSP and
reset entry must match `_estack` and actual `Reset_Handler`. Every nonzero vector
must resolve to an actual linked function; every such entry is budgeted,
including default terminal handlers. NMI and HardFault are accounted separately.
The selected STM32 device headers define four implemented priority bits.

H743 uses all 16 configurable architectural priority levels conservatively.
F407 uses the reviewed complete raw-priority domain `{0,5,6,15}`: zero is the
reset/default and SVC/fault priority, CubeMX assigns DMA/UART/EXTI 5 and SDIO 6,
HAL tick uses `TICK_INT_PRIORITY=15`, and PendSV/SysTick use 15. HAL tick's
temporary enable-before-priority-write state is therefore included at zero.
`uwTickPrio` is initialized by HAL_InitTick from that constant and subsequent
RCC/tick-frequency paths reuse it. The port's interrupt-priority probe writes
0xff (implemented priority15), then restores the original member of this
domain. Its SHPR writes set PendSV/SysTick15 and SVC0. HAL's priority grouping
and a reset grouping cannot create more distinct preemption levels than these
four raw values. Selected sources contain no other NVIC/SHPR/IPR/AIRCR priority
writer or externally selected interrupt priority. The case's complete input
and executable identities bind this source-level review; it is not a universal
regex inference for arbitrary firmware.

Each configurable nesting level is charged the maximum call-chain cost of
**any** configurable vector, plus 108 bytes (32 core + 72 FP + 4 alignment).
NMI and HardFault each add their actual call chain and another108 bytes.
The maximum reset/main call chain is added too, even where startup resets MSP
before task scheduling. Charging the first task interrupt's hardware frame to
MSP as well as to task context is conservative. Equal-priority interrupts do
not preempt each other. No reduction is taken for disabled IRQs, tail chaining,
BASEPRI masking, mutually exclusive device traffic or lazy FP savings.

References: ST PM0214 Rev10 sections2.3.5-2.3.7 (priority, grouping and exception
entry), https://www.st.com/resource/en/programming_manual/DM00046982-.pdf ;
Arm Cortex-M4 lazy stacking AN298,
https://documentation-service.arm.com/static/5f0352c0cafe527e86f5bc66 ;
Arm Cortex-M7 Devices Generic User Guide DUI0646C,
https://documentation-service.arm.com/static/61efd8352dd99944d05142d1 .


## 2026-11-16 Logger startup publication delta

The new F407 Release/Debug cases retain every selected source and header of
convergence-20261110-f4 except APP/Src/logger_task.c. The six-line delta checks
the completed immutable startup report before the first serialized event or
array access: device_count must not exceed SYSTEM_STARTUP_DEVICE_COUNT,
completed must be one and passed must be boolean. DeviceTask owns construction;
SystemStartup_ReportFinalize publishes completed after all fields, and the
startup controller stops changing the report after completion. NULL/incomplete
reports remain ordinary unavailable results. A legitimately failed device report
(passed=0) is serialized; sink I/O errors remain ordinary latched errors.

These checks add existing SilverStarAssert_Check/fail-stop calls to the Logger
path, with no new pointer target, interrupt registration, mutable alias, task,
stack allocation, dynamic frame, or priority writer. The actual new objects,
.su, .d, ELF/map, compiler and archive bytes are independently captured. The
existing 256-byte context/minimum-margin, full priority domain, all exception
frames, reset/main and callback provenance rules are unchanged. Candidate A
failed the old exact source seal as required; separate normal generation B must
rebuild and match every captured artifact before its emitted strict gate passes.

The owning full translation unit and real codec/assertion were executed with
Host GCC -fanalyzer, normal, device-failure, incomplete, NULL and I/O cases plus
capacity/completed/passed corruption. The old source failed all three corruption
cases. The oversized pre-fix case stops at the first injected sink failure,
before traversal, and does not rely on an out-of-bounds Host access. Only the
terminal trap is intercepted in Host to inspect the fault record and unchanged
publication state. This is not target recovery, MCU timing or hardware proof.

Evidence: docs/evidence/platform_finish_20261116/contracts/ in SilverStar. The
sealed cases describe exactly F407 reference configuration; they neither enroll
the new H7/C071 boards nor certify all first-/third-party critical semantics.


## 2026-11-17 E19 persistent profile consumer delta

The final F407 cases additionally include the root owner's narrow
Devices/Storage/SdSdioFatFs/Src/mission_radio_profile.c change. TypedRead
retains its length >= 4 + 16 check before any SX1278 read. Module byte 1
(E32) or 2 (E19) is accepted explicitly; the other fifteen bytes retain
exact memcmp matching. Other module values still fail. Read uses a local
candidate and publishes once only after the entire frame validation.
No callback, task, dynamic frame, pointer target or IRQ priority is added.

The real old consumer rejected E19 module 2 in three storage owners; root
recorded three failed / one passed before the change, followed by the
240-case actual Host/analyzer/ARM ABI group. This case admission separately
rebuilds the selected F407 target, reviews the complete source/object delta,
and recomputes every task and MSP/ISR/library bound. Earlier logger-only
case identities and evidence remain unchanged. Independent normal
generation D must reproduce C objects and pass the emitted strict gate.

The common parser now recognizes actual guarded Thumb1 helper and absolute
switch tables plus exact saved-LR split returns. This F407 target does not
acquire a C071 runtime/ISR grant: the complete machine graph and original
F407 exception/context/reserve values are still validated.


## Final object-catalog identity delta and E reproduction

The persistent-object catalog legitimately gains the E19 module identity.
ssdecoder schema 1.3 includes this exact catalog in its generation-profile
hash. C-to-D changes only the sixteen read-only initializer bytes of
Generated/Src/project_log_decoder_profile.c. No executable expression,
parameter, type, copy length, callback, stack allocation or branch changes.
Both actual configurations were fully rebuilt; all function instructions and
.su values retain their previous bounds. The strict C seals rejected D as
required. Fresh D diagnostics separately match every actual source, object,
ELF, toolchain and runtime callback/exception input; no literal mask is used.
The final cases now require independent normal-generation E to match D,
rather than treating D's actual identity failure as success.

The ordinary getter copies fixed arrays with their original sizes after
checking its output object; this new constant does not select code. Hardware
qualification, global critical semantics, minimum margin and every unknown
indirect/recursive/dynamic-frame rejection remain unchanged.


## Final E19-433M20S2 custom software fixture

This exact pair selects the independently implemented SX1278 driver with
AIR_LINK_SX1278_DIO4_FRONTEND=1, three distinct NSS/reset/DIO0 GPIO resources,
and unused RXEN/TXEN sentinels. It does not reuse the E28 case or grant every
SX1278/custom CubeMX project. The source graph removes SX1280lib and its
SX1281 adapter, adds the three SX1278 translation units, and retains every
remaining selected source, header, library, object and runtime path.

The synthetic input maps the previously reviewed F407 board Core/FATFS sources
under HardwareGenerated/STM32CubeMX. A text comparison of every corresponding
file found only: main.h adds two original E32 GPIO labels; gpio.c initializes
those unused outputs low and configures radio reset open-drain with pull-up;
spi.c changes SPI1 prescaler 16 to 128. Core main, reset/timebase, interrupt
handlers, all UART/DMA initialization and reciprocal Parent links, storage
callbacks and NVIC writes are otherwise identical. This comparison does not
replace the new exact case's complete raw/normalized source and object seals.
The unused GPIOs are not E19 bindings. The physical wiring is synthetic,
not evidence of an E19 PCB or electrical/antenna qualification.

The three UART handles (huart1/2/3), their six RX/TX DMA objects, and the two
SDIO RX/TX DMA objects retain the exact same C initializers and IRQ ownership
as the prior F407 board. All eleven actual BSS objects and the retained union
of SD/UART completion, half-completion, error and abort targets are checked;
unused M1 callback slots remain zero with no retained non-NULL installer.
The actual linked
DWARF, BSS containment, slot loads and union of retained constant installers
are rechecked from this ELF. Registration remains disabled. No new callback
registry, whole-handle copy or runtime target installation is introduced.
The IRQ path only accumulates the existing GPIO hint; the owning task consumes
DIO0 and polls status. It does not call the radio chip from the ISR.

The chip layer uses fixed 62-byte TX/RX arrays, validates length/register
extent before copying, and only publishes read output after successful SPI
and NSS release. Its 23-register initialization loop has a literal bound.
The DIO4 helper is a direct bounded sequence of checked read/write/readback
operations, preserves other mapping bits, and introduces no indirect call.
The device state machine processes at most one bounded step, uses fixed
2-frame queues/4 receipts, and retains explicit reset/timeout/fault paths.
No recursion, VLA, dynamic allocation or new asynchronous stack is added.
Real generated ELF edges, library implementations and .su frames determine
its budget; these source observations alone do not prove a bound.

The adapter originally mislabeled this selected E19 as E32. The final owning
fix selects NameGet/device_name/model_name from the same generated frontend
constant while keeping old E32 strings and hardware-unverified status.
Root recorded the real failed identity case then all 249 final Host cases,
including both identities, bad instance/no publication, DIO4 transactions,
mode/fault paths and three profile readers. The old mislabeled ARM/Host epoch
is not the admitted final binary. The identity fix changes no callback ABI.

All four F407 priority values remain exactly 0/5/6/15, with grouping and
startup/RTOS/ISR code reviewed unchanged. This case still charges the complete
actual vector table, NMI/HardFault and 108-byte extended FP frames with the
original 2304-byte MSP and 256-byte minimum margin. The actual control JSON
is sealed (disabled research task), not inferred from UI. Actual Release and
Debug candidates must be separately inspected and independently reproduced
by a second normal generation before delivery acceptance.

This is an exact static software-stack result. SPI prescaler, fixed timeouts,
Host duration and an SX1278 version register do not prove RF switch timing,
module identity, MCU WCET, measured high-water marks or hardware readiness.
