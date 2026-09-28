# Display/Data Quality/workspace acceptance — 2026-09-12

## Implementation

- Shared semantic columns: ENU E/N/U, body X/Y/Z, quaternion W/X/Y/Z, Euler Roll/Pitch/Yaw.
  Explicit Catalog columns win; unknown arrays use bracketed index IDs. Raw and stable aliases
  remain the same immutable TimeSeries. Audited KF6 uses position-first xE/xN/xU/vE/vN/vU
  (equivalent to the existing plugin's pE/pN/pU/vE/vN/vU), not velocity-first labels.
- Shared `TrajectoryPhaseSegments_Build` / phase assembler feed GUI 3D, PNG, and GIF. Exact
  event samples are shared; normally spaced neighboring positions share a visual linear event
  point. The per-channel threshold is max(2.5 × median positive dt, explicit display tolerance).
  Invalid samples, duplicate times, and true timestamp gaps preserve breaks. Event markers also
  retain the original validity mask. Source TimeSeries and algorithm inputs are never modified.
- Overview/diagnostics distinguish gap segments, missing IDs, recorded cumulative Logger/IMU
  queue counters, event occurrences, structural integrity, and evidenced mission phase. Export
  Manifest includes the same summary plus columns and per-channel cadence diagnostics.
- `tools/clean_workspace.py` defaults to dry-run, uses a bounded generated-file whitelist,
  refuses tracked/input/fixture/source/symlink/junction targets, rechecks before each deletion,
  and removes directories only when empty. `.gitignore` now covers the bounded acceptance and
  historical Codex test/staging directory patterns without globally hiding source data or images.

## Validation

- Ruff: all checks passed across src/tests/tools.
- compileall: passed for src/tests/tools.
- Focused final export/geometry regressions: 46 passed in 14.75 s.
- Final cleanup boundary regressions: 4 passed in 2.35 s, including real Windows junction escape.
- Full final suite: **154 passed, 7 skipped in 104.99 s**. The skips are the separate historical
  SS0007 (3), SS0014 (1), and SS_TEST_0 (3) opt-in real/Golden gates; synthetic tests do not
  satisfy these gates.
- Headless GUI covers the existing pages and language/theme behavior; current-log checks cover
  Chinese/English, Light/Dark 3D geometry and quality cards. This does not claim a live GPU-pixel
  test. The real trajectory PNG and GIF start/middle/end frames were also visually inspected.
- Document links: passed after documentation updates.
- PyInstaller 6.22: formal windowed build and hidden `--version` startup succeeded (exit 0) with
  an isolated build PATH. A tool-injected Poppler ICU initially caused frozen QtCore failure;
  the clean build excludes that incompatible DLL. Source code and formal spec were unchanged.

## Current external real log

Hash-locked `LOG/SS0000.BIN`, 3,298,139 bytes, opened only through LogOpenCoordinator with its
matching exact `.ssdecoder` 1.1. No raw input was changed.

- Log SHA-256: `00a77559dbd44eff8dad0a1523c7e7c9fc1ac0533d4b7687d27884038e6023dd`
- Decoder SHA-256: `d5d208c77215369e613c2df79177c09a46db1d6cff97be96fd1f91d0627f773f`
- 35,617 valid records; CRC, length, resync, unknown and decode errors all 0.
- 3 sequence-gap segments / 12 missing IDs, all before START (30,843,285 µs).
- Logger cumulative queue overflow 39; IMU queue overflow 0. Logger event occurrences are
  separate and are not interpreted as missing record IDs.
- Ready NONE identity calibration; GNSS online/no-fix; finite recorded Pure INS ~100 Hz and
  KF6 ~25 Hz with continuous mission position coverage.
- Deploy lies between normal KF6 samples; the shared drawn phase endpoints match exactly.
- Actual PNG/GIF/diagnostic/CSV/Manifest export completed. This is compatibility and display
  evidence, not a numerical host-C Golden or an EXACT replay claim.

| Expected | Actual | Missing IDs | File offset | Timestamp (µs) | Phase |
| --- | --- | --- | --- | --- | --- |
| 67 | 70 | 3 | 1664 | 7154681 | Before START |
| 79 | 80 | 1 | 2024 | 7154681 | Before START |
| 83 | 91 | 8 | 2144 | 7161729 | Before START |

## Cleanup results

- Result: `applied`; 1884 generated files and 350 empty directories removed.
- Reclaimed file bytes: 1,024,860,509 (977.38 MiB); elapsed 127.93 s.
- All 2506 tracked-file hashes and all 1682 protected log/package/project hashes remained identical.
- 2,397 already tracked historical Codex test/staging outputs were preserved; no tracked file was deleted.
- Virtual environment, source/fixtures/docs/resources, original main.zip, real inputs, unknown files, and reparse targets were preserved.
- Remaining approved cleanup candidates after apply: 0. Nonempty protected/unknown directories remain by design.

| Root directory | Removed paths |
| --- | ---: |
| `.acceptance` | 1714 |
| `.codex_pytest_20260828_a` | 2 |
| `.codex_pytest_20260828_full1` | 3 |
| `.codex_pytest_20260828_full2` | 3 |
| `.codex_pytest_20260828_m` | 3 |
| `.codex_pytest_20260831_phase13_full1` | 5 |
| `.codex_pytest_20260831_phase13_k` | 2 |
| `.codex_pytest_20260831_phase13_r` | 2 |
| `.codex_pytest_20260831_phase13_t` | 6 |
| `.codex_pytest_phase13_full_final_01` | 6 |
| `.codex_pytest_phase13_gui_final_01` | 2 |
| `.ruff_cache` | 10 |
| `__pycache__` | 2 |
| `build` | 19 |
| `dist` | 328 |
| `src` | 86 |
| `tests` | 39 |
| `tools` | 2 |

## Git and core files

The initial working tree was clean. Changes remain uncommitted for review. No other repository
was modified. See [Display_DataQuality.md](Display_DataQuality.md) and
[Workspace_Cleanup.md](Workspace_Cleanup.md) for the contracts and CLI commands.

Core implementation: [semantic_columns.py](../../apps/FLP/src/silverstar_flp/core/semantic_columns.py),
[trajectory.py](../../apps/FLP/src/silverstar_flp/core/trajectory.py),
[diagnostics.py](../../apps/FLP/src/silverstar_flp/core/diagnostics.py),
[dataset.py](../../apps/FLP/src/silverstar_flp/core/dataset.py),
[semantics.py](../../apps/FLP/src/silverstar_flp/decoder_profiles/semantics.py),
[export service](../../apps/FLP/src/silverstar_flp/export/service.py),
[Flight charts](../../apps/FLP/src/silverstar_flp/ui/pages/charts.py),
[Overview](../../apps/FLP/src/silverstar_flp/ui/pages/overview.py),
[Data Explorer](../../apps/FLP/src/silverstar_flp/ui/pages/data_explorer.py), and
[cleanup tool](../../apps/FLP/tools/clean_workspace.py).

Final Git state: 24 modified existing files and 8 new files; no deleted tracked files and no commit made.

## Shutdown decision

Checked Codex task status at 2026-09-12T01:59:17+08:00. Two other current Codex tasks were still active. Per the user instruction, no shutdown was executed or scheduled.
