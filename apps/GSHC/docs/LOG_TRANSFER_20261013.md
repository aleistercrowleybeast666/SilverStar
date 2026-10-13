# Windows log transfer, 2026-10-13

## Current maintenance 0.1 follow-up

The fourth page is now **Runtime / Logs** (运行诊断 / 日志). Its FC RAM diagnostics
are independent of the labeled Ground/AIR summary. Maintenance 0.1 adds the bounded
`SYSTEM DIAG` schema; see the shared [contract](../../../contracts/maintenance_diagnostics_v1.json)
and [validation record](../../../docs/public/SCG/MAINTENANCE_0_1_20261013.md).
There is no generic variable directory/watch list or SWD backend.

The shared Refresh button is left of Ground COM and enumerates once for both
selectors while preserving independent selections. Both baud boxes have the same
editable candidate list, positive-integer validation and 230400 default; 250000
and other representable custom values are not rejected merely for missing from
the candidates. Actual support still depends on the selected serial driver.
Ground COM, FC maintenance COM and optional SWD are three roles, not three COMs.
SWD is explicitly unavailable and cannot be connected by this build.

Old FINAL supports only its actual SYSTEM INFO/STATUS/CAPABILITIES and LOG STATUS
fields. The UI labels unknown MCU sample age and missing task-work instrumentation;
unsupported diagnostics/file service stays unavailable. Opening its UART does not
make LIST/META/READ appear. New firmware's diagnostics and file capabilities are
negotiated separately; one serial owner suspends diagnostics during file work.

Launch from this checkout with `.venv\Scripts\python.exe apps\GSHC\main.py`. Opening the
application does not authorize connecting a port. Existing packaged/frozen builds
do not include these source changes.

The sections below describe the earlier local-export/file-transfer checkpoint;
statements that diagnostics were only Ground/AIR or a LOG INFO skeleton are
historical and superseded by this follow-up.

## User flow

The original three pages remain; the fourth **Debug / Maintenance** page contains
all file-transfer controls. **Export to another connected device** opens **Copy export**
or **Cut export**. Disconnect telemetry and finish other data tasks first. Select
closed source files, then select a Windows filesystem directory or mounted device.
Copy retains the original bytes. External imports support copy only. Cut supports
one closed managed `fc_session_*.jsonl` at a time. The target is a new unique
directory; existing destination files are never overwritten.

The worker closes and flushes every destination, reads it back through SHA-256,
and writes/closes/reads back `manifest.json`. Only then does cut display a default-No
confirmation. Before unlinking, it checks the managed source identity, activity,
source hash, destination hash, manifest hash, and declared package contents again.
Declining, cancellation before the final deletion, changed files, missing files or
failed verification retain the source. The final single-file unlink is a commit
boundary; cancellation cannot undo a completed deletion. Partial or failed copies
remain identifiable at the unique output path and never authorize deletion.

This adapter supports filesystem paths. A Windows MTP phone is not a normal mounted
path: there is no MTP cut/delete adapter in this release. Use a reliable filesystem
destination or a separate copy/share workflow. No physical device was connected or
deleted during implementation or tests.

The top bar has separate **Ground port** and **FC debug port** selectors, baud rates
and connection states. Wide layouts place them side by side; narrower layouts wrap.
Open the debug port explicitly, then use **FC maintenance log service (UART / USB)**
→ **Download closed logs automatically** on the fourth page to download available closed
mission logs while preserving all device sources. It uses the Console `LOGFILE`
service in [the shared v1 contract](../../../contracts/log_file_service_v1.json),
not AIR/GSP or the low-rate telemetry link. The firmware remains authoritative for
lifecycle and active-writer refusals. List/META/READ errors abort ordinarily.

Each download asks for its target directory before submitting a file job. Cancelling
the chooser submits no transfer. The fourth page displays the last directory that
passed a background write/flush/fsync probe, stored in the independent QSettings key
`maintenance/tf_download_directory`. This is separate from local export and the GSHC
data root. The selected directory contains a new unique `SilverStar_download_*`
package; existing packages and same-name files are never silently overwritten.
Chinese and space-containing filesystem directories are supported. The remembered
location is a chooser hint, not a permanent assertion that the directory is writable.

After META, free space must cover a complete new file plus metadata allowance.
Write, flush, fsync, readback and publication errors are still handled because a
precheck cannot prevent later permission revocation or a full disk. Unfinished data
uses a unique visible `.partial` file with a `.partial.json` diagnostic checkpoint:
`bytes_written`, `verified`, status, expected size and token, unknown device/boot
identity and `resume_allowed=false`. Checkpoints update at most once per second and
on handled failure/cancellation. They never authorize continuation or deletion.
If storage also rejects the final checkpoint write, the last checkpoint can lag the
partial; the error is reported and the remote source is retained. After verified
publication, only that download's own sidecar is removed. A cleanup failure reports
failure while preserving the verified file and remote source.
Failure messages include the exact output directory so retained complete files and
partials can be found without guessing the generated package name.

The debug port remains owned by one background thread until explicit disconnect,
unplug or shutdown. Port-open state is distinct from LOGFILE CAPS support. Old firmware
or a negotiation timeout leaves the serial port open with file operations disabled.
The fourth page shows the closed-log list, progress, verification result and disabled
remote deletion. The same COM port cannot be used for both routes (including case
and `\\.\COM007` aliases). Different interfaces are not collapsed by USB serial number.
Unplug invalidates the selection; explicit reconnect negotiates CAPS again. Neither
route silently falls back to the other; mission commands retain the Ground route.

Read-only diagnostics use existing Ground/AIR state and are explicitly not bound to
the independent debug port's device identity. The two routes may reach different FCs.
Self-test/readiness use the actual PREFLIGHT_STATE receive timestamp. Sensor snapshot
time is only the latest sensor-frame time; individual acceleration/gyro update times
remain unknown and samples do not prove online status. Mission tracking and receive
error counters are local host data. Unknown firmware fields show unavailable; storage
diagnostics remain a labeled LOG INFO skeleton. A separate read-only details window
groups these values and their freshness. No new variable protocol or listener is added.

An optional DAPLink VCP can bridge this same maintenance UART: the computer uses
one USB cable to the probe; SWD plus separate TX/RX wires connect the probe to the
FC. Support depends on the actual probe model/firmware. Do not assume every
DAPLink exposes CDC/VCP; its MSC drag-and-drop drive is not the flight controller's
TF card. No RTT support or device connection is added here. The generic native USB
kit is experimental and is not automatically bound to the FC Console. Native CDC
requires an explicit project Console binding; the implemented service currently
uses the existing maintenance UART, directly or through an optional VCP bridge.

## Versions and integrity

New `SESSION_START` JSONL records include `log_format=silverstar.gshc-jsonl` and
`log_format_version=1`. Existing JSONL is immutable and remains
`legacy-unversioned`; AIR/GSP raw bytes and existing record layouts are retained.
Product version 0.1.3 does not change SSLOG container 0.0, AIR M0 or decoder package
schema 1.2. Export uses the shared
[session-export v1 manifest](../../../contracts/session_export_v1.schema.json).
Local SSLOG labeling requires its actual magic/profile/layout and header CRC;
unrecognized files remain opaque attachments. Header recognition is not full log
validation. Export does not provide or infer a matching decoder. FLP production
opening still requires the exact `.ssdecoder` and embedded Descriptor through its
existing coordinator; a GSHC JSONL is not a TF SSLOG.

Downloads serialize requests, bind PENDING/POLL responses to operation/request ID,
and validate file ID/token/offset, 64-byte chunk length/CRC, final size/full CRC and
local SHA-256 readback. Only a closed, verified local file is published. A second
META detects size/CRC changes, not device identity. CRC tokens are change detectors,
not authentication or collision-resistant identities.

LOGFILE v1 has no defined stable device/boot identity. Automatic resume and remote
delete are therefore disabled for all v1 peers, including peers that put arbitrary
non-unknown text in identity fields. After cancellation, timeout or reconnect,
download restarts at offset zero in a new partial file and preserves earlier
partials. The disabled delete menu communicates this limitation. A future identity
contract and a fresh explicit confirmation are required before remote deletion can
be enabled; a successful download never authorizes it.

Response timeout defaults to two seconds per exchange. Responsive PENDING operations
can continue until completion or cancellation; the firmware's 30-second idle timeout
is not a 30-second whole-file hashing limit. The first POLL is immediate, followed by
5–50 ms bounded backoff for repeated PENDING replies. Large files can be slow with
64-byte chunks, ASCII framing and storage hashing; physical throughput has not been
measured. Byte progress is mapped to a 0–1000 Qt range to support uint32 file sizes.

## Threading and validation boundary

Disk copying, hashing, Console I/O, parsing and serial close run in dedicated worker
threads. GUI owns selection, confirmation and status only. The persistent maintenance
owner has a bounded one-job queue and serializes all I/O. Export/download are mutually
exclusive with data migration, processing, simulation and active missions. Local export
requires the Ground session to be closed. Maintenance reads may coexist with a live
Ground session on a different port; starting a mission is blocked until the file job
ends and received mission-start state cancels a running file job.
An outstanding START_MISSION transaction also prevents new file jobs and cancels
an existing file job before the mission-start snapshot arrives. Other data-tool
policies are unchanged.
Cancel interrupts protocol waits and chunk boundaries. Closing the window requests
cancellation and keeps the live QThread/window alive; close again after it finishes.
An OS disk/driver call that does not return can delay cancellation. A close failure
is reported before success is emitted.

Tests use temporary samples and an in-memory LOGFILE peer; no real COM port or
device enumeration is used by the new tests. Real offscreen Qt widgets exercise
copy, an actual QMessageBox cut confirmation, declined cut, cancellation/close,
mock download, menu translation, large progress and transport-close failure.
Final screenshots and commands/logs/source hashes are in `.work/gshc_xfer_evidence_v4/`.
The final error-output-path addition has its own scoped follow-up in
`.work/gshc_xfer_evidence_v5/`. The pending-START exclusion defect has a recorded
pre-fix failure in `_v6_before/`, a test-call correction recorded in `_v6/`, and
final focused regressions in `_v7/`; do not
report the earlier full run as having executed those later additions.
Earlier evidence remains in `.work/gshc_xfer_evidence/`, `_v2/` and `_v3/`.
The retained [verification evidence archive](evidence/windows_log_transfer_20261013.zip)
contains final command/version/source-hash records, complete test output, real Qt
screenshots and the relevant earlier failure/baseline logs. Archive entries preserve
their original bytes; its internal inventory records each entry's SHA-256.

The expanded eight-file run before the mock compatibility repair recorded
73 pass / 17 fail: 11 existing mock-controller integration failures and six existing
header DPI geometry failures. The 11 mock cases are covered again after repair.
The unchanged baseline UI independently reproduced all six header failures
(`COM1@230400`, text width 144 versus available width 110). The new dual-port header
now corrects that layout and reruns all six DPI cases without exclusions. Historical
baseline results and full earlier failure output remain in the first evidence folder;
do not combine historical runs into a full-suite pass. Final scoped results appear in
the v4 `verification.json` (129 passed). The preceding v3 combination passed 123 tests before the
additional directory/partial-metadata requirement. No real hub, multiple USB devices, driver unplug, throughput,
TF storage or hardware behavior has been validated.

Sandbox attempts initially failed because Windows strict path resolution denied
access even to test-created workspace directories; the successful verification uses
the existing `.venv` outside that sandbox with TMP/TEMP confined to `.work`.
`tests/requirements.txt` records the added JSON Schema validation dependency.
