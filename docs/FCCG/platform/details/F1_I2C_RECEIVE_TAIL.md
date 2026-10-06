# F1 Flight blocking-memory receive tail

This change owns only the `silverstar_mcu_family_stm32f1_flight` HAL payload.
F1 Ground, F4 and other MCU-family payloads are unchanged. The public I2C,
sensor, AIR M0 and SSLOG interfaces are unchanged.

For more than two received bytes, every path retains the final three bytes for
one sequence: wait for BTF with IRQs enabled, clear ACK, mask IRQs, read N-2,
request STOP, read N-1, enable IRQs, then wait for RXNE and read N. The old
second BTF wait inside PRIMASK is removed. The bulk-read shortcut must not
consume N-2 outside that sequence. The single-byte ADDR/STOP and two-byte
POS/ADDR/ACK and STOP/N-1 sequences retain their interrupt protection.

The ordering follows [AN2824 rev 4, section 1.2.1 and figures 1/2](https://www.st.com/resource/en/application_note/cd00209826-stm32f10xxx-ic-optimized-examples-stmicroelectronics.pdf).
The entire N-2/STOP/N-1 interval remains masked as required by
[ES0340 rev 17, section 2.9.2 workaround 2](https://www.st.com/resource/en/errata_sheet/es0340-stm32f101xcde-stm32f103xcde-device-errata-stmicroelectronics.pdf)
for RE silicon markings Z/1/Y/2/3/X (REV_ID 0x1001/0x1003), and
[ES0346 rev 7, section 2.9.2 workaround 2](https://www.st.com/resource/en/errata_sheet/es0346-stm32f101xfg-and-stm32f103xfg-xldensity-device-errata-stmicroelectronics.pdf)
for RF markings 1/A (REV_ID 0x1000). No silicon revision was read from hardware.

STOP completion is observed outside PRIMASK under the remaining whole-operation
DWT budget. Original ACK/POS are restored only after STOP clears. A stuck STOP
returns timeout, keeps diagnostics and releases HAL ownership; HAL READY means
the software handle is available, never that the bus/device is healthy. The
existing guard forbidding abort STOP after ARLO or without local master
ownership remains. No new timeout budget, unconditional reset, GPIO recovery
or software I2C implementation is added. ES0340/ES0346 section 2.9.7 BUSY filter
lock remains an ordinary bounded failure, not a claimed successful recovery.

The Host MMIO regression compiles the actual owning HAL and DWT helper with
flag, volatile DR and CPU register interception. It models two independently
phased 1 ms timers with one pending bit each, merged expirations, a pending TIM6
tick and delayed service. Old 2f26b01 fails: second BTF fault masks for 1726
model microseconds and merges 2 TIM6 / 1 SysTick expirations. The corrected
sequence has no masked peripheral/deadline polling; normal sizes 1/2/3/4/6/14/24,
1000 independent tick phases, final RXNE timeout/error, stuck STOP, arbitration
loss, buffer guards and stored-owner corruption checks pass.

Model microseconds and instruction counts are not MCU WCET. Prior interrupt
latency, flash/APB stalls, physical timing and bus noise are not proven. An
already overdue pending tick can still merge with a subsequent expiration;
this patch removes the I2C polling contribution, not every system latency.
Hardware wire timing, tick latency, stack high water and physical recovery are
NOT RUN / NOT PROVEN. The Power10 manual critical-contract review remains
NOT PROVEN, and unrelated failed gates continue to block acceptance.
