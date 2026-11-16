# STM32F103C8T6 E19 Ground software stack review, 2026-11-17

Scope: the exact Ground cases named by `ground_stack_inputs.json`, their complete
selected C/ASM/headers/linker/Make inputs, actual Release/Debug ELF and objects,
and Arm GNU 14.3.Rel1 compiler/header/library closure. This is not a hardware,
timing, radio or flight qualification. Other configurations remain unreviewed.

This image has no RTOS and no FPU. Reset uses the hardware vector's initial MSP;
the complete linked graph has no MSP/PSP/CONTROL switch or unresolved SP write.
The startup owns one readonly `.isr_vector` section of 0x10c bytes. The exact
STM32F103xB CMSIS definition ends at USBWakeUp IRQ 42: 59 hardware slots. The
seven following zero words and fixed BootRAM 0xf108f85f word are checked as the
documented startup boot trailer, never discarded as unknown IRQ handlers.
All nonzero hardware slots must resolve to actual linked Thumb function entries.
SysTick, EXTI0, DMA1_Channel4, DMA1_Channel5 and USART1 must be strong, unique
startup entries pointing to their actual linked handlers. This explicit sealed
review supplements the legacy source graph's absent complete-import inventory;
it does not declare arbitrary legacy imports verified.

The linker is the owning `silverstar.mcu.stm32f103c8t6` payload, with unchanged
physical 64 KiB Flash / 20 KiB SRAM and no heap. It reserves 8192 bytes for MSP.
The former 1024-byte reservation was insufficient: actual old-image finite
projections were 3912 Release and 3424 Debug bytes. The new linked bank audit
must still accept actual static data plus the reservation; spare RAM alone is
not a stack proof. The bound charges main/reset, all 16 implemented configurable
priority levels, NMI and HardFault, each with a conservative 36-byte basic frame.
The unchanged minimum margin is 256 bytes. No IRQ priority, callback, library
path or frame is omitted to make the bound pass.

The Cortex-M3 CRT initializer's exact linked instruction shape is checked
separately from M0+/M4/M7: zeroed finite counter, actual start/end array literals,
four-byte postincrement loads, two exact BLX sites and exact loop branches.
Every array word must point to an actual Thumb function entry. Weak clone
callbacks reuse the original shared LDR-zero / CBZ-to-BX-LR proof including
unique predecessor checks; the other architectures' accepted shapes are unchanged.

HAL closure: `huart1` is the sole 72-byte UART object, and RX/TX DMA handles are
68-byte BSS objects. `MX_USART1_UART_Init` and its MSP path bind DMA1 Channel5 RX
and Channel4 TX through reciprocal `__HAL_LINKDMA` Parent links to that same UART.
The selected IRQ translation unit passes those fixed objects. `pc_byte_stream`
uses `&huart1`, never another UART, whole-object assignment or a runtime registry.
Startup clears BSS; initialization and deinitialization follow the selected HAL.

Actual callback bindings are UART DMA complete/half/error/abort constant targets.
F1 DMA slots are complete 40, half 44, error 48 and abort 52 bytes; UART parent
child loads are checked against actual DWARF and linked reaching definitions.
There are five `(caller, PC, ABI slot)` bindings per configuration: Release
combines three DMA slots at one instruction (three distinct PCs total), while
Debug has five distinct PCs. Source and linked installer evidence must match
the actual case; no generic function-name allowance grants acceptance.

`USE_HAL_UART_REGISTER_CALLBACKS` is zero. The retained image has no UART/DMA
register/unregister path, asynchronous Abort* API or object replacement. The
retained `HAL_UART_AbortReceive` clears callbacks; `HAL_UART_IRQHandler` installs
only `UART_DMAAbortOnError`. Completion, half and error pointers come from the
retained Transmit_DMA/StartReceive_DMA constant assignments. All linked calls,
including libc/libgcc, must close; recursion or unresolved/dynamic frames reject.

E19-433M20S2 uses the existing SX1278 backend and explicit module identity 2,
preserving the 16-byte radio profile contract. Radio retry/error paths remain
ordinary bounded errors. This review grants no RF certification, device access,
actuation or physical verification. The C071 cases and their 4-level basic-frame
rules remain independent and byte-for-byte preserved in the shared Ground index.
