# SSGS1.0 Cortex-M0+ exact software stack review — 2026-11-17

Only separately sealed, completely matched Release/Debug cases are admitted.
Capturing a graph or this review text alone is not acceptance. The adapter checks
the complete Ground Make/source graph, all actual objects, CPP and GAS dependency
closure, saved assembler source, all source/header/linker/assembly inputs, ELF/map,
compiler tools/headers/specs and actually linked libraries. Generation receipt
hashes are provenance, not compiler inputs; all remaining target metadata is
sealed. Unknown calls, dynamic SP, recursion or omitted objects fail closed.

## Fixed objects, startup and callbacks

The selected C071 startup assigns `_estack` once using LDR literal / MOV SP,
copies data and clears the linked BSS before calling CRT initialization and main.
There is no RTOS, PSP switching, CONTROL write or application callback registry.
The strict runtime adapter checks that sole MSP assignment and its predecessor,
and rejects other unbounded SP effects. The actual linked CRT weak callbacks
load zero and execute CMP/BEQ-return before BLX. The two initializer loops use
actual preinit/init array endpoints, bounded element count and actual Thumb entry
addresses; malformed endpoints, unknown targets or changed loop code reject.

`Core/Src/usart.c` defines exactly `huart2` (UART_HandleTypeDef, 148 bytes),
`hdma_usart2_rx` and `hdma_usart2_tx` (DMA_HandleTypeDef, 92 bytes each).
Their exact linked BSS addresses and bounds are sealed per configuration and
checked against actual DWARF. `MX_USART2_UART_Init` initializes the concrete UART;
its MSP path initializes DMA1 Channel1 RX and Channel2 TX and installs reciprocal
`__HAL_LINKDMA` hdmarx/hdmatx and Parent links. USART2 IRQ passes `&huart2`, DMA1
Channel1 IRQ passes `&hdma_usart2_rx`, and Channel2_3 IRQ passes `&hdma_usart2_tx`.
No other active UART/DMA handle is introduced or copied wholesale. Generated
pc_byte_stream owns its bounded buffers and calls the selected UART's DMA APIs.

The concrete DMA ABI slots are XferCpltCallback, XferHalfCpltCallback,
XferErrorCallback and XferAbortCallback. Actual retained targets are installed
by UART DMA receive/transmit and abort/error paths. The shared resolver retains
their complete linked constant-target union; no callsite is dropped because
it is rarely reached. UART RxISR/TxISR are zero in startup BSS and set to NULL
by the linked UART configuration path; this profile uses DMA, not HAL IT byte
transmit/receive installers. Those non-NULL IT targets are absent from the linked
ELF. This NULL-only finding is based on the complete selected source/alias and
retained-code review, not on an unrelated SPI struct having fields with the same
spelling. HAL runtime callback registration remains disabled/unreferenced.

The exact callback loads use the DMA parameter, UART parameter or UART hdmarx
child of the correct object type. Actual DWARF offsets, compiler instructions,
reaching definitions, BSS inventory and callback target set must match each case.
The sealed source set covers macro aliases, `.field`/`->field` assignments,
whole-object copies and initialization. Changing these inputs invalidates the
case instead of automatically inferring a new trusted domain.

For independently generated directory roots, the normal Make rules map only
debug paths to `.` and use GCC `-fno-working-directory` for the saved startup
preprocessor output. This suppresses its optional current-directory line marker;
all source names, dependency lines and instructions remain present. The checker
still hashes every saved `.s` byte and does not normalize away a mismatch.
Reference: https://gcc.gnu.org/onlinedocs/gcc/Preprocessor-Options.html

## Cortex-M0+ instruction and exception proof

Thumb1 helper jump tables, literal absolute jump tables and split POP/BX returns
use the shared machine-code analysis with actual guard dominance, read-only table
bytes, target entries, known helper body and LR-slot provenance. The actual
libgcc division implementation is included. This is instruction semantics, not
a function-name whitelist. Unknown shapes remain errors.

The C071 header selects core_cm0plus.h and exactly two implemented NVIC priority
bits. The target is cortex-m0plus, Thumb, soft ABI; there is no FPU. Every nonzero
linked vector is included, including all aliases of the default handler. The
maximum Reset/main path plus all four configurable priority levels, NMI and
HardFault is charged against the linked 4096-byte `_Min_Stack_Size` reservation.
Each exception costs 32 bytes for the basic eight-register frame plus a worst-case
4-byte alignment word: 36 bytes, as described by ST PM0223's exception entry.
No narrower priority-write assumption or tail-chaining saving is used. SysTick,
EXTI2_3, DMA1_Channel1, DMA1_Channel2_3 and USART2 must be strong linked vector
handlers under the independent artifact contract. The minimum margin remains
256 bytes, identical to the existing software stack policy.

Reference: https://www.st.com/resource/en/programming_manual/pm0223-stm32cortexm0-mcu-programming-manual-stmicroelectronics.pdf

This proves only the exact software stack bound under the reviewed ABI and
input contracts. It does not establish interrupt latency, MCU WCET, measured
stack high-water, DMA/electrical correctness, UART/radio timing, or hardware
qualification. The board stays unverified and software candidate.
