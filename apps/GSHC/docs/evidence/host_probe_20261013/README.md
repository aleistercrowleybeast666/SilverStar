# Host probe selection evidence — 2026-10-13

Owner: root integrator. Base commit: `258aaa6eea88b70218e936795035fae2e84ad317`.
The implementation and this evidence are committed together on the existing
local 0.1.3 development branch. Only GSHC and its documentation are changed.

## Scope and observations

The application enumerates Windows present-device metadata, groups composite
interfaces, and stores a host probe selection. It never opens a probe, SWD
session, USB interface or serial port. No hardware command, driver change,
firmware build, flash, reset, halt, push, tag or publication was performed.
The other repository's UNDERLINE debug task was left alone.

`host_inventory04.json` records a real successful inventory at
2026-10-13 13:43:28 UTC, elapsed 1.474 seconds:

- Horco CMSIS-DAP; `FAED:4870`; serial `132765403520`.
- Identity `USB\VID_FAED&PID_4870\132765403520`.
- Windows metadata lists a composite parent, HID interface and WinUSB interface;
  they produce one candidate. PnP status was `OK`.
- This is host visibility only. Probe occupancy, driver-open success, target
  power, debug access and firmware readiness remain unknown.

The later real Windows GUI inventories returned **empty**. The GUI correctly
displayed no probe, and no stale online selection was substituted. This record
does not infer why the host inventory changed. Physical unplug/replug and
multiple attached probes were not exercised by this task.

`host_inventory01.json` and `02.json` retain unsuccessful 10-/20-second trials
of the original PnpDevice query. `03.json` records a successful 14-second Windows
PowerShell CIM trial. The final backend prefers the already installed `pwsh`
and falls back to Windows PowerShell; both have the same read-only method and
20-second deadline. Nothing was installed to obtain the faster runtime.

## Validation

Final regression: **111 passed, five subtests passed, exit 0, 285.26 seconds**,
recorded in `probe_tests03.log` and `probe_tests03.json`.
The run covers probe identity/parser/error bounds, Qt asynchronous selection,
single/multiple/none, retry, simulated removal/replug, stable selection after
reordering, repeated clicks, late completion during close, responsive header,
serial controls/DPI, file-transfer UI, workflow and i18n. All device-facing
test dependencies are synthetic or mocked.

`probe_tests01` retained 38 passing tests and two harness errors: an oversized
bytes parameter became a pytest name larger than the Windows environment
variable limit. Explicit short case IDs corrected the harness without reducing
the payload size. `probe_tests02` retained 105 passes, five passing subtests and
one old navigation-test failure. `baseline_navigation01` reproduced that same
failure with the exact base commit's MainWindow: the tab holds a QScrollArea,
not its MaintenancePage child. The updated test selects the actual tab container
and additionally verifies that it owns the intended MaintenancePage.

The first native GUI trial assumed a probe would still be present; it failed
when the real inventory was empty. Subsequent QA accepts and records the actual
present/empty result. It does not require a synthetic online state to pass.

`gui03` is native Windows Qt QA of the final responsive header with actual host
metadata. Both languages reached 1024 and 1280 logical pixels without clipping
or group overlap; requested width 1920 was constrained by this desktop to 1539
logical pixels and is recorded as such. The earlier `gui02` screenshots and
geometry preserve the minimum-width pinning defect before its correction.
The tested fix prevents the previously wide header layout from pinning the
window minimum size and blocking wrapping.

`gui04_replay` is explicitly labelled **replay**, using the earlier real host
metadata as test data to show a selected probe at 200% offscreen scale. Its
1024/1280/1920 geometry is not a claim of a live attached probe or a native
1920-logical-pixel desktop. Native empty-state and replay selected-state images
were visually inspected. No serial-open call occurred in either QA path.

Python 3.14.0, PySide6 6.10.1, pytest 9.1.1, Windows 11 build 26200;
`versions.json` records the installed runtime locations. Command records include
timestamps, exit codes, environment and SHA-256 hashes of the GSHC Python inputs.
Packaging verifies that final regression input hashes still match the files.
This is an executed selected GSHC regression run, not a full monorepo suite,
firmware safety acceptance, board qualification or a SWD connection test.

## Artifacts and limits

- `evidence.zip`: explicit command records, logs, QA scripts, inventory results,
  screenshots, geometry and an internal SHA-256 manifest.
- `archive.json`: archive size, SHA-256 and base commit.
- `.work/dev013_probe01/inventory.json`: retained local task inventory with
  purpose, owner, size, hashes and no cleanup authorization.

The user's Library screenshot was resolved by identity but could not be
materialized through the required identity-preserving helper on this Windows
runtime (`os.setxattr` unavailable). Its pixels were not inspected. Signed
Library transfer metadata and any helper leftovers are excluded from the
delivered archive. The inspected images are this task's own Qt renders.

No task cleanup was performed. Existing user input files, old `.work` evidence,
frozen releases and the deferred USB development material were preserved.
v0.1.2 still resolves to tag object `942f20ef64df3cb1aa65be7349361c409418aa0f`
and commit `c31c13cc0686a56a3184d4f207fd3816c5d39696`.
