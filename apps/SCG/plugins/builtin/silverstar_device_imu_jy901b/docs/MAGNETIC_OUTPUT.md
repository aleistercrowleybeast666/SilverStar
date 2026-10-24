# JY901B/S magnetic output (0.1.3, 2026-10-18)

Magnetic collection is an explicit device-profile choice. Select
`jy901b_mag_capture` for B or `jy901s_mag_capture` for S. The ordinary `jy901b`,
`jy901s`, and legacy empty/default profile keep magnetic output disabled. Adding
a separate magnetometer does not enable the JY magnetic frame. No saved project
is silently changed to a capture profile.

The driver has one build-wide `JY901B_MAGNETOMETER_ADAPTER_ENABLE` switch. The
generator already requires every selected JY instance to opt in together; mixed
capture/default JY selections are rejected. B and S capture can coexist at the
shared 200 Hz requested output rate. There is no per-instance magnetic switch
or auto-detection of magnetic hardware. Select the correct physical variant;
these profiles do not authorize a six-axis-only module as a magnetometer.

| Selected profile | Startup RSW register 0x02 | Frames |
| --- | --- | --- |
| default / jy901b | 0x0246 | acceleration, angular rate, pressure/height, quaternion |
| jy901b_mag_capture | 0x0256 | same B frames plus magnetic field |
| jy901s | 0x0206 | acceleration, angular rate, quaternion |
| jy901s_mag_capture | 0x0216 | same S frames plus magnetic field |

Euler bit `0x0008` remains off, as intentionally selected previously. Magnetic
bit `0x0010` is independent of the module's six/nine-axis attitude algorithm;
capture does not switch the attitude algorithm or start module calibration.
Startup compares and reads back RSW along with the other existing configuration
registers. A legacy module configuration missing the requested magnetic bit is
changed in RAM and verified. A refused/mismatched write fails startup. Normal
boot does not issue SAVE. No EEPROM, flash, serial, protection or hardware actions
were performed for this change.

The checksum-verified 11-byte `55 54 ... checksum` frame carries three signed
little-endian 16-bit magnetic words. Every accepted frame increments its own
sequence and is published through the shared IMU owner and generated magnetic
endpoint. Partial or bad-checksum input does not advance the magnetic sample.
No magnetic frame means NOT_READY; another live IMU frame does not make an old
magnetic sample fresh. A magnetic sample older than 100 ms, or from a future
local timestamp after a clock discontinuity, returns TIMEOUT. Disabled capture
returns UNSUPPORTED even if unsolicited magnetic bytes arrive.

The last word of 0x54 is not treated as temperature. The current official SDK
publishes only HX/HY/HZ from that frame, and its Python JY901S example likewise
uses only the three signed words. The magnetic adapter therefore does not
advertise temperature or mark it valid; an unrelated shared temperature cannot
be presented as a magnetic-frame temperature.

## Units, calibration and time limits

B retains the established nominal conversion `0.00667 uT/LSB`. S uses
`0.008333 uT/LSB`, based on the manufacturer's JY901S product specification
(8.333 nT/LSB). These are nominal physical-unit conversions, not a qualified
accuracy, calibrated vector, hardware-revision identification or proof that
all module firmware revisions share the same scale. The currently available
official WT901 listing quotes 6.67 nT/LSB, but does not establish exact JY901B
revision equivalence; the prior B constant has not been requalified here.

`raw[]` means the exact signed words received from the module before SilverStar
conversion/correction. It does **not** prove bypass of the module's internal
hard/soft-iron offsets, filtering or factory calibration. The accessible official
SDK exposes magnetic calibration commands and offset registers, but does not
prove whether 0x54 is before or after each module correction. The full official
protocol on Yuque returned HTTP 403 in this session. Thus the exact B/S internal
calibration ordering remains **NOT PROVEN**. Installed-vehicle calibration needs
stable, documented input semantics and must avoid applying the same correction
twice. SilverStar's current calibration application consumes the provider's
`magnetic_field_b_uT` vector and rejects samples already marked
`SYSTEM_MAG_VALID_CALIBRATED` or `calibration_valid != 0`; it does not consume
the integer `raw[]` array directly. That enforces the SilverStar correction
boundary, but cannot identify or undo an undocumented module-side correction.
No calibration state, offset, algorithm, persistence or read/write
protection setting was changed as part of enabling output. The adapter retains
`calibration_valid = 0` and does not claim absolute-vector qualification.

`sample_timestamp_us` and `receive_timestamp_us` are the same local
receive/decode-time proxy. Frame 0x54 contains no verified measurement timestamp.
Polling/DMA batching, serial transmission, module latency and independent sensor
sampling can shift that proxy. A frame arriving in a 200 Hz stream does not prove
200 independent magnetic measurements per second, simultaneous IMU/magnetic
sampling, PPS discipline or high-precision synchronization. The existing MAG
interface has no timestamp-trust flag; consumers must retain this limitation.

At the required 230400 baud, 8N1 costs 10 line bits per byte. B capture requests
5 x 11 x 200 x 10 = 110000 bit/s (47.74% utilization), with 2.387 ms serialization
per 5 ms output cycle. S requests 88000 bit/s (38.19%), or 1.910 ms per cycle.
The new magnetic frame adds 22000 bit/s (9.55% of the link), or 0.477 ms per cycle.
These are nominal periodic-stream budgets; framing, processing latency and
register responses still need margin and bench verification. At 115200 baud B
capture would use 95.49%; at 9600 baud even one 11-byte 200 Hz frame would not fit.
Low-baud probing is only a bounded startup-identification phase; the configured
stream is normalized/read back at 230400. Do not equate a discovered low-baud
connection with a sustainable capture configuration.

## Official references and validation scope

- [Manufacturer SDK index](https://www.wit-motion.com/SDK.html) links the standard
  TTL/RS232 protocol implementation.
- [Official REG.h, pinned e8f4e3a](https://github.com/WITMOTION/WitStandardProtocol_JY901/blob/e8f4e3afc02263e2ef15052dc758f45efaebe12f/Arduino/Arduino_sdk/REG.h)
  defines RSW=0x02, RSW_MAG=0x10, WIT_MAGNETIC=0x54, RSW_Q=0x200 and RSW_ANGLE=0x08.
- [Official C decoder, same revision](https://github.com/WITMOTION/WitStandardProtocol_JY901/blob/e8f4e3afc02263e2ef15052dc758f45efaebe12f/Arduino/Arduino_sdk/wit_c_sdk.c)
  checks the 11-byte frame and routes the three magnetic words to HX/HY/HZ.
- [Official Python decoder](https://github.com/WITMOTION/WitStandardProtocol_JY901/blob/e8f4e3afc02263e2ef15052dc758f45efaebe12f/Python/Python-WitProtocol/chs/lib/protocol_resolver/roles/wit_protocol_resolver.py)
  preserves the three signed magnetic values in the JY901S example.
- [Official JY901S listing](https://www.wit-motion.cn/ahrs.html) explicitly includes
  magnetic field. Its [product parameters](https://www.wit-motion.cn/proztmz/22.html)
  specify the magnetic resolution and maximum 200 Hz/230400 baud, and list no
  pressure output. The S profile continues to omit pressure/barometer.
- [Current WT901 parameters](https://www.wit-motion.com/Module/84.html) are
  corroborating family information, not exact B-revision certification.

Directed tests use synthetic bytes with the real parser, shared adapter and UART
mock, including both module variants, sign extremes, bad checksum, reserved tail,
missing/stale magnetic frames, opt-out, startup write/readback and refused writes.
Task commands, pre-fix failures, fresh generated firmware, gate outcomes and
hashes are retained under `.work/dev013_jy901_mag_20261018`. Passing software
checks do not establish whole-firmware Power of Ten compliance, completed manual
critical-contract review, physical units on an unidentified revision, magnetic
sampling rate, stack margin, synchronization accuracy or flight qualification.
