# SX1278 / E32-400M20S experiment — 2026-10-15

The independent wireless payload is in
`apps/SCG/plugins/builtin/silverstar_device_telemetry_sx1278/`.
Its README owns the exact wiring, reference links, document conflicts, finite
software bounds and hardware limitations. `project/sx1278.py` owns the deliberately
narrow profile validator and AIR header renderer.

**Current admission: standalone driver experiment only. Normal SCG generation
integration and complete Flight/Ground target acceptance are pending.** Adding a
catalog entry does not establish working RF communication or a qualified board.
No hardware was connected, flashed or commanded, and no RF transmission occurred
in this task. Existing E28/SX1281 defaults and payloads remain unchanged.

The E32 family includes SPI and UART modules. The selected E32-400M20S is SX1278
SPI with separate RXEN/TXEN and DIO0/RST. This work does not infer the transport,
voltage, frequency or PA behavior of another E32/E19 model. The selected module
is operated at the common documented 3.3 V supply/IO point; contradictory manual
text does not authorize 5 V. The first software profile is 433 MHz, SF7, BW125,
CR4/5, preamble 16, explicit CRC packets, ordinary IQ, MTU61 and +17 dBm chip
drive. Actual RF power, receive sensitivity and interoperability are unmeasured.

The chip layer implements bounded SPI transactions and register readback; the
module layer implements reset sequencing, mutually exclusive RF switch control,
bounded queues, timed TX, RX CRC/length validation, result receipts and recovery
without queued command replay. Both Flight telemetry and Ground radio interface
adapters are supplied. RSSI/SNR remain explicitly unsupported. Version register
0x12 is a bus check, not automatic SX1278/module identification.

Host tests use a register/FIFO simulator and injected IO failures. Real GCC
`-fanalyzer` compilation and ARM compilation/linking use the same payload, with
an IO-failing ABI fixture for the ARM links. Those ELF files are **not complete
Flight Controller or Ground Station firmware**, contain no production HAL/RTOS
closure, and were not executed on an MCU. A checker run over copied payload files
is a partial text scan; it is not a normally emitted whole-project gate run.

Remaining integration requirements are recorded in the task's versioned handoff:
AIR family/profile validation, explicit instance module/power resolution,
family-specific header dispatch, Ground backend ownership/selection, UI selection,
architecture/ground-gate support with negative tests, recorded radio snapshot
identity, fresh full Flight/Ground generation, unchanged emitted power10-check,
whole-source static analysis, actual full ARM links, linked source/stack reports
and hardware evidence. Any failed gate or NOT PROVEN contract blocks acceptance.

Recorded radio profiles need particular care: the historical SX schema 2 contains
LoRa parameter bytes without family identity. SX1278 must not silently be logged
as SX128x. Resolving that shared recorded-data contract is reserved for parent
integration; this isolated task does not change FLP or frozen log schemas.

No original Power of Ten compliance, NASA certification, stack margin, WCET,
flight suitability or hardware qualification is claimed.

The follow-up contract review additionally latched Stop across restart, verified
mode changes and detected uncommanded reset, measured reset phases after GPIO
completion with tick-quantization allowance, prevented stop/completion races,
kept queue expiry independent of nonterminal IRQ flags, retained 64-bit health
timestamps and corrected aggregate error attribution. Internal invariant traps
withdraw published READY before entering the established fail-stop path.

The Flight adapter now returns BUSY until its Process owner confirms physical
quiescence. Shared `system_source_selector.c` currently clears `started` during
Stop and routes pending cleanup through repeated Stop attempts, without servicing
this asynchronous driver owner. That caller lifecycle is an actual integration
blocker, distinct from missing gate/build evidence. The parent integration must
preserve a single owner and drain the pending stop before marking cleanup
complete or starting any replacement. This task does not modify the selector.
