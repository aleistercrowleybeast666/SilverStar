# SSFC1.0 exact software stack review — 2026-11-16

This document accompanies separately sealed Release/Debug cases for the complete
SSFC1.0 H743ZI board example. It does not admit a case by filename, automatically
trust a captured binary, qualify hardware, or change the 256-byte margin.
The gate must match every declaration, selected C/header/assembly/linker input,
compiler tool/header/library input, dependency file, object, `.su`, ELF and map.
The evidence inspector is diagnostic until those manual cases are admitted.

## Concrete ownership and initialization

The board owns `HardwareGenerated/STM32CubeMX/Core` and its fixed IOC; it has no
imported CubeMX snapshot and no user-owned `Board` implementation. Startup clears
the linked BSS before `main`, HAL initialization and the MX functions. The two
`UART_HandleTypeDef` objects are `huart1` and `huart2`; four DMA objects are
`hdma_usart1_rx/tx` and `hdma_usart2_rx/tx`, all defined once in `Core/Src/usart.c`.
The exact linked DWARF, address, size and BSS containment must match the case.

USART1 RX/TX use DMA1 Streams 0/1; USART2 RX/TX use Streams 2/3. Each MX/MSP path
initializes the fixed peripheral and uses reciprocal `__HAL_LINKDMA` child/Parent
links. Their four IRQs pass those concrete DMA objects to HAL_DMA_IRQHandler;
the USART1/2 IRQs pass the corresponding UART object. No runtime handle replacement,
whole-object copy, callback registry or untyped callback installer is introduced.
Existing Platform UART functions reference these fixed resource-table handles;
the NEO-M9N and maintenance clients do not own a second UART handle.

The retained HAL DMA/UART installers assign constant function addresses or NULL.
The review uses the union of actual retained constant targets at each actual
DWARF ABI slot, with linked loads checked against the concrete DMA/UART object
type. A callback whose installer is discarded is not inferred from a different
library version. UART RxISR/TxISR and unused DMA M1 slots start zero in the actual
BSS and have no retained non-NULL installer in this DMA-only profile; source
NULL assignments alone are not initialization evidence. UART callback registration
is disabled in the selected HAL configuration. Unreferenced HAL registration APIs
do not create an application callback registry.

## Other runtime paths

BMI088 uses the existing bounded I2C wrapper and the existing constant driver
callbacks. MMC5983MA uses the existing I2C driver; NEO-M9N uses the selected USART1
resource; E28 uses the existing SX1281 SPI implementation. This does not remove
any linked vendor routine from graph/stack coverage. Polling I2C/SPI, SDMMC IDMA,
FatFs and the selected libgcc/libc paths remain actual graph inputs. The SD original
inputs are hash checked and the selected owning H7 storage replacement remains
the only compiled SD-disk implementation; no new allocator or FatFs callback ABI
is added. No RTOS object is created by renaming a stage.

The selected storage reader includes the current module-1/module-2 SX1278
identity check: the module byte must be exactly 1 or 2 and all other 15 fixed
bytes remain a complete equality comparison. Its bounded reads and length guard
are unchanged. The present SSFC case still selects E28/SX1281; this review does
not reinterpret an E19 receiver as hardware tested or alter a stack edge domain.

The final object-catalog contract also changes the 16-byte generated decoder
profile identity constant. This is retained as an exact source/object/ELF input;
the previous profile bytes are never treated as equivalent or stripped from the
seal. It does not add a callback, stack frame or runtime registration path.

The board TIM6 IRQ explicitly calls HAL_TIM_IRQHandler(&htim6); the main callback
increments HAL tick only for TIM6. This fixes the fresh CubeMX empty-handler
defect and is part of the new exact board input, not an exception to coverage.
The SysTick/SVC/PendSV implementation and static task stacks belong to the existing
H7 FreeRTOS port. Reset MSP, PSP task restore, floating-point save state and the
linked CRT initializer/weak callback tables are checked by the existing runtime
proofs, with no new architecture assumptions.

## Interrupt budget and result boundary

Every nonzero entry in the actual linked vector table is budgeted, including
default/fault handlers, USART/DMA, SDMMC1, EXTI9_5 and TIM6. The H743 has four
implemented priority bits; the bound deliberately charges all 16 configurable
priority levels, plus NMI and HardFault, and 108 bytes per extended FP exception
frame. The existing task context allowance and minimum margin are unchanged.
The actual control-research JSON must match its seal; an absent control task is
not inferred from the GUI display. All unknown indirect calls, SP writes,
recursion or missing stack-usage records remain rejecting conditions.

The PC13 START action in this example is only a status indication. The example's
ESKF20 software mode, identity installation and noise/initial covariance inputs
are explicitly unmeasured assumptions. Even a passing exact software stack case
does not prove HAL timeout timing, ESKF20 WCET, radio/SD timing, measured stack
high water, navigation accuracy, electrical correctness or flight qualification.
