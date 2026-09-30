# SilverStar 0.1.0 field-test qualification checklist

Use the [frozen software reference](FIELD_TEST_REFERENCE.md). Record operator, date/time, board serials, TF card identity, exact project/decoder/ELF/BIN hashes, configuration and calibration generations before each session. Keep raw logs, serial captures and measurements outside this repository or under ignored `.work/round5/`; do not commit private user logs.

**Bench safety:** Never connect real ignition or deployment loads during these qualification steps. Use disconnected outputs, a logic probe, LED, or appropriate dummy indicator. Deployment hardware must be handled under the user's existing safety process. Do not run power-interruption or card-removal tests with hazardous loads attached.

For each row, record `PASS`, `FAIL`, or `NOT RUN`, timestamp, exact hardware/firmware identity, measured values, and a link/path to the raw evidence. `NOT RUN` is not a pass. A failure that could affect START, storage integrity, navigation, radio bridge, decoder identity or output safety requires a reproducible software issue before field use.

| Qualification action | Result / time / evidence |
| --- | --- |
| Confirm Flight/Ground PCB identity, power, cables, safe output wiring and firmware SHA-256 | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Confirm Flight TF card writable; JY901B, M9N and E28 wiring; Ground radio and UART; GSHC port | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Ground cold boot and reconnect: GSP `GS_STATUS`, ACK, AIR_RX, RSSI/SNR, error counters | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Ground queue pressure: bounded BUSY, no deadlock, recovery and meaningful counters | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Flight cold/warm boot: dangerous outputs SAFE, bounded DeviceTask startup and Preflight readiness | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| JY901B target/factory/legal-candidate startup, absent-device timeout, fresh sample, no default NVM SAVE | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| M9N target/factory/legal-candidate, passive NMEA/UBX and RAM-only PUBX,41 rescue; exact M9N identity and NAV-PVT | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Storage no-card/mount-failure START rejection, healthy START admission, multiple `/missions/NNNNNN/` directories | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Read back manifest, mission snapshot, `flight.sslog`, final status and calibration identities from actual TF | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Safe power-loss/torn-object and post-START card-failure bench cases; Flight/Recovery remain operational | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Flight ↔ AIR ↔ Ground ↔ GSP/UART ↔ GSHC command, rejection reason, telemetry and link-loss recovery | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| IMU calibration and selected alignment result; compare actual orientation and SSLOG `0x28` evidence | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| If a physical magnetometer is selected: GSHC collection, fit, Apply/Save/Read, power-cycle identity and wrong-device rejection | `NOT RUN — only if reference configuration selects a magnetometer` |
| KF6 representative run and ESKF15 basic smoke; real ODR/aggregation, fresh measurements and replay bounds | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Capture target timing, stack/queue/logger/replay high-water marks and offered-load diagnostics; label observed maxima as measured, not WCET | `NOT RUN — HARDWARE_ACTION_REQUIRED` |
| Copy actual TF log into Project Root `Log/`; FLP opens Project Root with exact decoder and decodes `0x28`, `0x29`, optional `0x2A` | `NOT RUN — ACTUAL_LOG_REQUIRED` |
| Inspect trajectory, velocity, altitude, attitude, state, GNSS, estimator and gap diagnostics; export PNG/CSV/GIF plus manifest to `Log/<LogStem>_Export/` | `NOT RUN — ACTUAL_LOG_REQUIRED` |
| Freeze final hashes, calibration generation and recorded test evidence; review any P0/P1 defect | `NOT RUN — HARDWARE_ACTION_REQUIRED` |

For passive Ground UART evidence after safe board preparation, run `python tools/round5_ground_capture.py --port COMx --seconds 60`. It only reads bounded GSP frames and writes an ignored JSON record. Use GSHC for the active command path; passive capture alone cannot validate radio TX, START semantics or the new firmware/PCB combination. Reconnect and queue-pressure observations need separate operator notes and timestamps.

Before an actual flight, recheck power, TF free space, GNSS, IMU, radio/Ground/GSHC connection, calibration and alignment readiness, storage and START gates, and the frozen hashes. After the flight, preserve the original TF contents, copy logs to `Log/`, open the project root in FLP, export to the per-log directory and review fault diagnostics. A completed bench checklist does not replace the user's deployment safety process.
