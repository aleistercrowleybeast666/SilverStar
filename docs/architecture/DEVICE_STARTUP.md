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

## Round 4 M9N rescue (software path)

NEO-M9N startup now walks the driver's finite supported UART baud set:
project target, factory 38400, then 4800, 9600, 19200, 38400, 57600,
115200, 230400, 460800, 576000 and 921600, with duplicates removed.
Each probe first listens passively, then sends UBX-MON-VER. The NMEA parser
counts only sentences with a valid checksum. If a candidate has at least two
valid sentences but no MON-VER response, the M9N plugin sends the documented
`PUBX,41` UART1 command to enable UBX input and UBX/NMEA output at that
candidate baud, then retries MON-VER. The normal RAM-only VALGET, diff,
VALSET, reconnect, readback and fresh NAV-PVT sequence follows. A MON-VER
response with the exact `MOD=NEO-M9N` and supported `PROTVER=27.` identity
is still required before configuration or READY. Generic NMEA receivers do
not use this vendor rescue path.

The [u-blox M9 interface description](https://content.u-blox.com/sites/default/files/u-blox-M9-SPG-4.04_InterfaceDescription_UBX-21022436.pdf)
specifies `PUBX,41`; the [NEO-M9N integration manual](https://content.u-blox.com/sites/default/files/NEO-M9N_Integrationmanual_UBX-19014286.pdf)
specifies the factory UART settings. Host tests cover recovery, invalid
checksums, wrong identity and a failed PUBX write. Physical receiver behavior
remains **HARDWARE_UNVERIFIED**.

The bounded probe window allows two valid NMEA sentences one second apart;
with no stream, each candidate advances after its MON-VER wait. Exhausting
all declared candidates reports device absence rather than retrying forever.

## Generic NMEA receiver (Round 4 software path)

`silverstar.device.gnss.generic_nmea` is a separate, read-only receiver
plugin. It accepts GGA, GNS, RMC, VTG and GST with a strict checksum and a
96-byte sentence bound. Each `Process` call consumes at most 256 bytes and
8 sentences. A new `$` resynchronizes a malformed stream. No vendor commands
are sent, including during startup or failover. The source selector skips
configuration for read-only instances while still configuring other selected
GNSS instances.

The parser assembles fields within one UTC epoch and publishes at the next
epoch boundary, with receive time marked as an untrusted measurement time.
RMC-only 2D fixes never claim vertical position or velocity. GGA/GNS altitude
is MSL; an ellipsoid estimate is filled only when a valid geoid separation is
also present. GST metric standard deviations are published only when present;
GSA DOP is not substituted for metric accuracy. The existing strict preflight
origin gate still requires horizontal and vertical position, while the
per-group quality mask allows horizontal-only data to be represented honestly.
The UART baud and receiver output mode remain user-configured external facts.

The [NMEA 0183 owner](https://www.nmea.org/nmea-0183.html) describes the
standard and warns that informal sentence lists can be inaccurate. The
[u-blox interface description](https://content.u-blox.com/sites/default/files/ZED-F9T-10B_InterfaceDescription_UBX-20033631.pdf)
is the public primary reference used for the supported sentence fields.
Host parser, source selector and startup tests and an F407 ARM compile/link
smoke cover software behavior. Physical receiver operation remains
**HARDWARE_UNVERIFIED**.

## BMP280 barometer (Round 4 software path)

`silverstar.device.barometer.bmp280` owns one physical chip definition with
I²C and four-wire SPI interface variants. The first I²C profile uses the
SDO-low `0x76` address. Both variants run the same bounded forced-mode state
machine: chip ID, calibration trim, filter read/diff/write/readback, fresh
conversion and compensated pressure/temperature. Each DeviceTask tick performs
at most one bus transaction; a conversion has a finite timeout and failure
removes the device from readiness. No persistent sensor settings are written.

The device publishes pressure and temperature only. The existing common
barometer layer derives altitude from pressure before estimator and recovery
consumption; the chip does not claim a native altitude or variance. Device
startup and steady-state processing now dispatch all selected physical
barometer and magnetometer instances, including JY901B's shared logical
adapters without replaying its UART parser. The Bosch
[BMP280 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp280-ds001.pdf)
is the register, compensation and 10 MHz SPI limit authority. Official
compensation-vector, timeout, I²C/SPI mock, variant/source-graph and strict
ARM compile tests pass. The full existing F407 Flight reference still links.
The new physical BMP280 path remains **HARDWARE_UNVERIFIED**.

## MS5611 barometer (Round 4 software path)

`silverstar.device.barometer.ms5611` has one physical chip identity and I²C
and four-wire SPI interface variants. The bounded `osr4096_20_hz` profile
resets the device, reads all eight PROM words, checks CRC4, and commands fresh
temperature and pressure conversions. Each process tick performs at most one
bus transaction. A missing response, invalid calibration CRC or conversion
timeout fails startup; the first compensated sample gates readiness. No
persistent configuration is written. The chip supplies pressure and
temperature only; the common barometer layer derives altitude.

The [TE Connectivity MS5611-01BA03 datasheet](https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocFormat=pdf&DocLang=English&DocNm=MS5611-01BA03&DocType=Data+Sheet&PartCntxt=MS561101BA03-50)
is the command, compensation, CRC and SPI limit authority. Host tests cover
the datasheet compensation vector, bad PROM CRC, conversion timeout, both bus
adapters and generated variant bindings. Board behavior remains
**HARDWARE_UNVERIFIED**.

## BMP390 barometer (Round 4 software path)

`silverstar.device.barometer.bmp390` uses one physical chip identity with
I²C and four-wire SPI variants. Its separate BMP390 core verifies chip ID
`0x60`, reads the 21-byte trim block, and compares, writes only differences,
and reads back the oversampling and filter settings. Forced pressure and
temperature conversion is bounded by a 40 ms timeout; the first fresh,
compensated sample gates readiness. A process tick performs at most one bus
transaction. SPI reads account for the BMP390 dummy byte. The device reports
pressure and temperature; the common barometer layer derives altitude.

The [Bosch BMP390 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp390-ds002.pdf)
is the register, compensation, conversion-time and 10 MHz SPI authority.
The current 20 Hz profile uses pressure ×8 and temperature ×1 oversampling.
Host compensation, timeout, I²C/SPI mock and variant/source-graph tests pass.
The physical device remains **HARDWARE_UNVERIFIED**.

## LIS3MDL magnetometer (Round 4 software path)

`silverstar.device.magnetometer.lis3mdl` supplies I²C and four-wire SPI
variants from one physical plugin. Its bounded startup verifies WHO_AM_I,
reads all five control registers, writes only differences and reads them back.
The current 20 Hz, ±4 gauss profile enables temperature and block data
update. A new XYZ status bit gates the eight-byte magnetic/temperature burst;
the driver reports raw counts and uncalibrated µT, without claiming a
calibrated absolute vector. No persistent sensor settings are written.

The [ST datasheet](https://www.st.com/resource/en/datasheet/lis3mdl.pdf)
defines identity, controls, 6842 LSB/gauss sensitivity and 10 MHz SPI limit;
[AN4602](https://www.st.com/resource/en/application_note/an4602-lis3mdl-threeaxis-digital-output-magnetometer-stmicroelectronics.pdf)
defines the nominal temperature conversion. Host tests cover signed XYZ,
identity, readback, fresh status gating and both bus variants. The device
remains **HARDWARE_UNVERIFIED**.
