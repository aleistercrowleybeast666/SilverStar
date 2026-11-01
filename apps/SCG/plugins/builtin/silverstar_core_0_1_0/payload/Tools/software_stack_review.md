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
