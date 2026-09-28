# Device startup contract

The required Round 3 design limits pre-scheduler startup to deterministic MCU
state, placing mission outputs in SAFE,
initialize internal objects and create static tasks. Device discovery, UART
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

The controller and host tests are present. JY901B and NEO-M9N have bounded
request/poll startup controllers and Host tests for probe fallback, per-field
read/diff/write, readback, and sample gates. Their older adapter startup paths
still call synchronous operations. `SystemStartup_Run` still executes device
startup and waits before scheduler start; `DeviceTask` does not yet own these
controllers. The contract is therefore **not yet integrated**. Firmware
startup must not be described as asynchronous until the adapter routing and
scheduler-first path are verified together.

Factory UART defaults used for bounded fallback come from the
[WitMotion standard protocol](https://wit-motion.gitbook.io/witmotion-sdk/wit-standard-protocol/wit-standard-communication-protocol)
(BAUD register `0x0002`, 9600 baud) and the
[u-blox NEO-M9N integration manual](https://content.u-blox.com/sites/default/files/NEO-M9N_Integrationmanual_UBX-19014286.pdf)
(38400 baud, UBX input enabled). The other fallback baud rates are the
explicit sets already declared by the SilverStar JY901B and M9N drivers.
