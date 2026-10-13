# GSHC header alignment and connection diagnosis — 2026-10-13

Owner: root integrator. Base: `63445dbf7671541b9ed8bde5d149fc413242414b`.
This is a local 0.1.3 GUI follow-up, not a firmware or USB-stack change.

## Delivered behavior

Probe controls and their status now use one horizontal group. Controls sharing
a row have the same vertical center; status is to the right, and excess gaps
are removed. Chinese detection-button text is exactly `重新检测`. Groups wrap
without hiding controls. Header resizing is re-evaluated after Qt applies the
child geometry, including native desktop width clamping.

The FC serial header is translated initially and after language changes,
connecting, stopping and disconnecting. It distinguishes unopened serial,
opened serial awaiting firmware, a parsed firmware reply, and opened serial
with unavailable status. Unsupported LOGFILE alone does not mean a physical
disconnect. This change does not modify the serial-opening implementation,
wire protocol, firmware readiness or command authorization.

## Real diagnosis and deliberate stopping point

At 15:23:14 UTC, read-only host enumeration found one Horco CMSIS-DAP candidate:
`FAED:4870`, serial `132765403520`, USB instance
`USB\VID_FAED&PID_4870\132765403520`. Its HID/WinUSB/composite metadata was grouped
into one probe. pySerial's host port metadata identifies **COM9** with the same
VID, PID and serial. **COM7 and COM8 are Bluetooth serial ports**.

The native source-GUI QA independently found the same probe. In that fresh
instance, both serial selectors initially showed COM8, the probe selected the
Horco identity, the maintenance owner was absent, and maintenance-open was
false. This reproduces a possible wrong initial serial selection; it is not
inspection of the user's existing GUI. A selected probe does not automatically
select or open the maintenance UART. The application requires an explicit
maintenance serial selection and connection action.

The existing `FileServiceSerialTransport` opens pySerial directly. Inspection
of the installed Windows backend showed serial open applies DTR/RTS via the
DCB/SetCommState configuration. [pySerial's official API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.open)
also documents possible OS/driver activation and glitches during open.
Reset-free wiring and driver behavior were not established. Under the user's
explicit instruction to stop at enumeration in that case, **no COM port was
opened, no control line changed, and no SYSTEM/LOG command was sent**. Port
occupancy was not probed or overridden. No SWD session, halt, reset, flash,
parameter write, calibration, arming, START or actuator operation occurred.

Host USB visibility is established. Serial-open success, the actual UART
connection, flashed firmware identity and firmware responses are NOT TESTED.
The old FINAL USART3 PB10/PB11, 230400 8N1 information remains prior source
evidence; it does not prove today's board wiring or flashed image. Nothing
here claims the power hardware is safe or diagnoses a physical disconnection.

## Validation

- `ui_tests02`: **64 passed, five subtests passed, exit 0**, 137.72 seconds.
  Executed probe/header layout, file-transfer UI, legacy firmware status,
  translation and serial-control/DPI tests; device I/O was synthetic/mocked.
- `ui_tests01`: 46 passes and five passing subtests before the final deferred
  layout fix. It is retained, not substituted for the final run.
- `native02`: native Windows Qt source GUI, live host metadata, no maintenance
  owner or serial-open attempt. Chinese widths 1024/1280/1530 and native-clamped
  1539 remain visible; at 1530 the three control centers are all y=67. English
  wraps where its longer labels require it. Requested 1920 is recorded with
  its actual desktop-constrained width; it is not claimed as native 1920
  logical pixels. Final screenshots were visually inspected.
- `native01` exited zero under the original geometry checks, but visual QA
  **rejected** its English native-clamped frame: buttons were squeezed. The
  final checks additionally enforce group/button minimum widths, and the
  deferred reflow fix removes the squeezing. A tool exit zero did not override
  this visual failure.

Command records include timestamps, command, environment, exit codes and exact
GSHC Python source SHA-256 values. Packaging checks final test and native-QA
input hashes against the committed source files. This is a selected GSHC suite,
not a full monorepo or firmware acceptance run. No firmware build was launched;
the independent UNDERLINE task was not controlled or interrupted.

The requested Library screenshot identity was resolved, but its required
materialization helper failed because Windows Python lacks `os.setxattr`.
Its pixels were not inspected; native Qt renders are the visual evidence.
Private transfers and helper leftovers are excluded from `evidence.zip`.
Unrelated Bluetooth hardware addresses are omitted from the delivered diagnosis
copy; the exact raw observation remains in the retained local task directory.

## Retained artifacts and acceptance

`evidence.zip` contains command logs, source-hash records, the redacted host
diagnosis, native screenshots and geometry, QA scripts, Library failure record,
tool versions and an internal hash manifest. `archive.json` hashes the archive.
Local task inventory: `.work/dev013_probe02/inventory.json`; owner/purpose/hashes
are recorded, and no cleanup is authorized or performed.

Restart from the repository root with
`.venv\Scripts\python.exe apps\GSHC\main.py`. At a wide Chinese window, the three
control groups should align. Check `重新检测`, the right-hand probe status and
Chinese FC serial state, then narrow the window and switch languages. Existing
running windows and old packaged executables do not acquire source edits.
Live serial response acceptance still requires confirmed reset-free wiring
and an available, explicitly identified maintenance port.
