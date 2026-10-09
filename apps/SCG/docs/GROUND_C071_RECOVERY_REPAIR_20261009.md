# Ground C071 UART recovery and USB supply correction — 2026-10-09

The C071 UART recovery stall is repaired in its owning standalone recipe. This
report supersedes the recovery-liveness conclusion of
`GROUND_C071_SOFTWARE_COMPLETION_20261009.md`; the earlier report and evidence
are preserved. The C071 USB candidate now advertises the selected mini topology:
USB VBUS supplies a 3.3 V regulator, with no independent supply.

This is a local software change on top of
`761a8f42f3f2c2617e01c7ebce95dc6d8a6372a7`. No GUI, daily checkout, immutable
flight candidate, hardware, schematic, or normal SCG F1/F4 generator was changed.
No push, flash, serial operation or hardware acceptance was performed.

## Reproduced failure and repair

The unchanged C071 UART adapter and bridge from `ssc071-backpressure-run2/uart`
were compiled with the new `recovery-full` harness. A UART error followed by a
temporary RX re-arm failure allowed status/radio frames to fill all four PC
queue slots. Reads then stopped for ACK backpressure; recovery was only called
by reads; writes refused submission while RX was unarmed. Healthy HAL could
therefore never be reached by the normal main loop. The unchanged candidate
fails `rx_calls==calls+1U`, with assertion exit `3221226505`. Its full log is
retained as `unchanged-baseline-recovery.log`.

Only the C071 UART recipe inserts `PcByteStream_Service()` once into the owned
`GroundBridge_Process`, before radio processing and either flush. The service
does not read, advance RX indices, or consume queue capacity. When unarmed, it
makes at most one recovery attempt per main iteration. Reads return unavailable
without retrying; neither flush invokes recovery. Failed recovery remains
unavailable for the next iteration. Abort still precedes releasing TX storage;
session invalidation and publication exclusion are unchanged. Healthy pressure
keeps unread commands in their bounded transport buffer. A reset/error cancels
old-session input/queued replies as before; this is not a promise to deliver
traffic across a failed session.

The two approved `Platform/STM32C0/Src/main.c` files remain byte-identical:

| Profile | SHA-256 |
|---|---|
| USB, loop line 103 | `085ac2c877b7263beb6f2b1073a564d505a0822a6d71e25a4134e51622b10da1` |
| UART, loop line 102 | `26ce79b8166f3eafef5615fc7e00fb41bb36176809e552aca761d5d77650384d` |

The owning Power10 checker, approved hashes, thresholds and exception scope
were not edited. Exact loop checks again pass both profiles and reject all
seven existing mutations, retaining `POWER10_CONTRACT_REVIEW|NOT_PROVEN`.

## Validation and retained attempts

Fresh targets are under
`C:/Users/chdxm/AppData/Local/Temp/ss-c071-recovery-run1`.
The evidence root is
`C:/Users/chdxm/Documents/Codex/2026-10-08/task/uart-recovery-validation`.
The committed receipt is
`docs/ground-usb-evidence/c071-recovery-summary.json`; it records exact commands,
exit codes, source snapshots, log hashes, manifests and release/analysis hashes.

All five fresh targets passed their emitted ARM build, architecture, Host,
Power10 and real `-fanalyzer` analysis targets. F1/F4 also passed their normal
artifact gate; C071 passed its separate actual-vector/ABI/dependency/clock/PMA/
memory gate. The generic F1/F4 artifact gate was not presented as C071 support.

| Target | text | data | bss including reserved stack | Flash text+data |
|---|---:|---:|---:|---:|
| F103 USB | 36544 | 380 | 12008 | 36924 |
| F103 UART | 27640 | 12 | 7584 | 27652 |
| F407 USB | 36892 | 248 | 14808 | 37140 |
| C071 USB | 39628 | 256 | 9704 | 39884 |
| C071 UART | 38068 | 12 | 8160 | 38080 |

Release/analysis BINs match for every target. All three F1/F4 BINs are also
byte-identical to the pre-fix `ssbackpressure-run2` binaries, confirming the
C071-local scope. C071 reserves 2048 bytes for stack and zero heap; its USB/UART
unallocated RAM is 14616/16404 bytes. Those figures do not prove stack margin.

The real C071 UART adapter passes the ten existing pressure scenarios,
transport/session fault tests, and five additional cases: full queue after
failed RX re-arm, failed Abort followed by recovery, eight repeated error cycles
with BUSY/ERROR re-arm failures, another IRQ error after that iteration's service,
and 100 full-queue iterations without consuming eight legitimate commands.
Each process invocation asserts at most one Abort and one RX re-arm. The repeated
case checks stale partial-frame rejection followed by a new command and ACK.

Five compiled mutants are rejected: lost error-session invalidation, premature
TX buffer reuse, omitted independent service, read-triggered extra recovery,
and service consuming RX bytes. The first negative-validator run returned 1:
the consuming-RX mutant correctly failed the final eight-command/ACK assertion,
but the validator expected an earlier queue-capacity assertion. Only that
expected assertion location was corrected. The complete initial log remains;
`uart-negative-final.log` exits 0 and verifies all five intended predicates.
No production input or harness assertion was changed for this correction.

C071's existing `_close/_lseek/_read/_write` libnosys warnings remain visible in
both links. This is not a warning-free whole-link claim. Earlier reachability
review showed their sections discarded; first-party strict/analyzer gates and
linked allocator/stdio restrictions remain intact. Hardware callbacks/timing in
Host tests are mocks. UART does not detect a physical unplug merely from silence.

## USB descriptor and power budget boundary

`USBD_SELF_POWERED=1` advertises self-power and was incompatible with the chosen
pure VBUS-powered mini. The C071 recipe now writes `USBD_SELF_POWERED=0` and an
explicit `USBD_MAX_POWER=0x32` (100 mA in USB 2.0's 2 mA units) into its adapted
configuration header; the frozen official input and F1/F4 profiles are untouched.
The actual compiler macro dump and linked ELF configuration header are checked:
`09 02 43 00 02 01 00 80 32`. `bmAttributes=0x80` has neither self-power nor
remote-wakeup set. The UART alternative has no linked USB PC descriptor.

100 mA is a requested active/configured ceiling and a design target, not a
measured load or a current limiter. A standard USB 2.0 downstream port permits
100 mA before configuration; suspend has a separate 2.5 mA limit.
See [USB-IF suspend-current update](https://compliance.usb.org/index.asp?Format=Standard&UpdateFile=Electrical)
and [Analog Devices USB power explanation](https://www.analog.com/en/resources/technical-articles/the-basics-of-usb-battery-charging.html).

For planning, the E28 manual lists RX 10 mA and TX 45 mA instantaneous current
and recommends supply margin above 30%. These values do not provide a guaranteed
module maximum over conditions. [Ebyte manual, printed pages 3 and 6](https://www.cdebyte.com/pdf-down.aspx?id=2994)
The C071 datasheet's 48 MHz HSI run example gives 3.9 mA typical at 25 C and
4.3 mA characterized maximum at 85 C with peripherals disabled. USB/SPI/CRS,
clocking and GPIO loads must be added; core current alone is not board current.
[ST DS14693, Tables 28 and 35](https://www.st.com/resource/en/datasheet/stm32c071c8.pdf)

An explicit provisional allocation is 15 mA for MCU/clocks/USB/GPIO and 5 mA
for regulator/protection/indicators. With nominal RX this is 30 mA before
configuration; with TX it is 65 mA. Applying 30% module-only margin yields
78.5 mA. The 15/5 mA figures are engineering allocations, not component data or
proof. Final BOM, E28 maximum/transients, LDO quiescent current, capacitive inrush,
startup and active VBUS measurements must stay within 100 mA. USB descriptor
configuration cannot constrain LDO/capacitor charging current. Native startup
puts the radio in RX before USB configuration; ordinary commands arrive through
configured CDC endpoints, but radio startup/physical current remain unverified.

**Known unfinished acceptance item:** `low_power_enable=DISABLE`; suspend only
notifies the USB library. It does not put E28 into sleep or implement a complete
MCU/radio low-power policy. Keeping nominal 10 mA RX alone exceeds 2.5 mA.
Changing the descriptor does not resolve suspend consumption. A reviewed
power-state design plus measured suspend/resume/inrush evidence is required
before claiming complete bus-powered USB compliance or hardware readiness.
No unreviewed clock/sleep/radio behavior was added in this recovery repair.

Complete critical contracts, whole-program stack/WCET, MCU ISR latency,
enumeration/ZLP/reconnect, power and radio hardware behavior remain NOT PROVEN.
The pin contract can still support a reversible mini schematic draft; this
software result is not PCB manufacture or hardware acceptance authorization.
