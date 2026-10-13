# Root integration evidence, 2026-10-13

The complete SCG optional-protocol/maintenance-selection/storage-admission run
passed 52 cases and retained four expected negative-scope skips. This is a single
executed three-file suite, not a union of previous passes. Its PowerShell process
returned exit code 0. The focused test separately passed once before the full run.

The prior 51-pass/4-skip/1-failure run remains unchanged in
`../../../apps/SCG/docs/evidence/log_file_service_20261013/`. The failure was a test
searching for a string radio item value. The frozen `c31c13c` component already
stored `(plugin, module)` pairs. The retained old component/test and current test
make that mismatch and the narrow repair reviewable. No SCG UI code changed;
all protocol toggling and logging-disable behavior assertions remain.

`collect.py` reads existing logs without executing tests or touching hardware.
It verifies the frozen tag, firmware source hashes and normal/analyzer ARM
artifacts, plus the final Windows archive CRC, complete entry SHA-256 inventory
and all 16 current source/snapshot bindings. It then captures the integration
metadata and exact test snapshots.
Run it from the repository root using the existing `.venv/Scripts/python.exe`.
The collection command exited 0; the sandbox Python launcher printed its existing
real-location warning, which did not prevent collection.

The metadata HEAD is the code identity at collection, before the later integration
documentation commit. Windows has separate dirty-source bindings and complete
records in `../../../apps/GSHC/docs/evidence/windows_log_transfer_20261013.zip`.
USB and firmware records keep their own distinct configurations and command scopes.

No integrated hardware, whole-repository test, complete stack proof or completed
critical-contract acceptance is claimed. The firmware stack gate remains FAIL.
