# Device startup contract

SilverStar calls `SystemStartup_Run` before the FreeRTOS scheduler. That stage
must only initialize deterministic MCU state, place mission outputs in SAFE,
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

The controller and host tests are present. Integration into
`SystemStartup_Run`, `DeviceTask`, JY901B and NEO-M9N remains in progress.
The current JY901B baud rescue and register configuration still contain
response waits; the M9N identify and configuration paths also contain
synchronous waits. They must be split into request/poll transactions before
the contract can be declared implemented or firmware startup verified.
