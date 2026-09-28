# Device startup contract

The Round 3 implementation limits pre-scheduler startup to deterministic MCU
state, places mission outputs in SAFE, initializes internal objects and
creates static tasks. Device discovery, UART
baud or protocol search, response waits, configuration readback, SD mount and
sample readiness belong to `DeviceTask` after the scheduler starts.

## States and ownership

Each configured device moves through `UNINITIALIZED`, `PROBING`, `IDENTIFIED`,
`READING_CONFIG`, `APPLYING_CONFIG`, `RECONNECTING`, `VERIFYING_CONFIG`,
`WAITING_SAMPLE`, then `READY` or `FAILED`. A DeviceTask tick advances at most
one stage operation. Each wait has a monotonic deadline; probe candidates have
a fixed upper bound. The device adapter owns all I/O and buffers. Startup
diagnostics remain local to debug, maintenance serial and suitable SSLOG
records; AIR M0 only carries existing readiness and sensor status.

`NONE` persistence tries its known bootstrap. `PERSISTENT` tries project
target, factory bootstrap and explicitly declared legal candidates, skipping
duplicates. It never scans an integer baud range. A successful probe reads
actual configuration, computes differences, writes only those differences,
changes communication settings last, reconnects, reads back and waits for a
valid sample. Startup does not issue SAVE, write BBR or write Flash by default.

The reusable bounded controller is in
`System/Inc/system_device_startup.h` and `System/Src/system_device_startup.c`.
Its callbacks must be nonblocking; returning `Pending` yields until the next
DeviceTask tick. A bounded controller alone does not make a blocking driver
callback asynchronous.

## Integration status

`SystemStartup_Run` now initializes time, lifecycle, health and SAFE outputs
before `vTaskStartScheduler`. `DeviceTask` advances console, physical adapter
startup, configuration and communication checks after scheduling begins.
It waits for delegated configuration verification before marking the startup
report complete and entering preflight. The Flight task cannot enter READY
while lifecycle remains in self test. The configuration and communication
waits are bounded, and an unfinished required device blocks mission readiness.

JY901B and NEO-M9N adapters run their request/poll startup controllers from
their `Process` callbacks. Both use target, factory and declared candidate
bootstrap profiles; read current settings before writing differences; change
baud last; verify by readback; and require a new sample. Their production
paths do not issue SAVE, BBR or Flash writes. Older synchronous adapter paths
are compiled only by legacy host regression tests. Other existing device
adapters continue their bounded immediate task startup as a transition path.
The host controller and system startup tests and an ARM compile/link smoke
verify software integration. Device timing and electrical behavior remain
**HARDWARE_UNVERIFIED** until tested on a board.

Factory UART defaults used for bounded fallback come from the
[WitMotion standard protocol](https://wit-motion.gitbook.io/witmotion-sdk/wit-standard-protocol/wit-standard-communication-protocol)
(BAUD register `0x0002`, 9600 baud) and the
[u-blox NEO-M9N integration manual](https://content.u-blox.com/sites/default/files/NEO-M9N_Integrationmanual_UBX-19014286.pdf)
(38400 baud, UBX input enabled). The other fallback baud rates are the
explicit sets already declared by the SilverStar JY901B and M9N drivers.
