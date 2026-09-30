# Post-Round5 source validation and field preparation — 2026-09-30

**Field readiness: NO.** No hardware was flashed, armed or operated. This is source and offline firmware-build evidence, not a qualification signature or public 0.1.0 release. The current KF6 reference has the materials for a controlled human bench session, but the newly exposed Power of Ten Rule 5 findings require a reviewed disposition before treating its software gate as cleared. Hardware identity, safe wiring, actual IMU/GNSS/radio behavior, TF readback, timing and operator observations remain unperformed.

## Repository and environment

- Repository `D:\python_software\SilverStar`, branch `main`; starting HEAD and reference baseline `4a1f3db315aa97fbd591d8ad8001e07f266f1f1d`, clean at start. This audit ran against that commit plus the visible staged/working changes. Final commit is recorded by `git log -1` after submission; no tests below are represented as tests of an earlier frozen ELF/BIN.
- Windows 11 (`Windows-11-10.0.26200-SP0`), AMD64, Asia/Shanghai (UTC+08:00); Python 3.14.0; PySide6 6.10.1; ARM GNU 14.3.1; host GCC from MSYS2 UCRT64; native `mingw32-make`. Local completion times in the durable logs range 2026-09-30 17:16–18:38 +08:00. Python requirements are lower bounds, not a lockfile.
- Persistent ignored logs: `release-evidence/post-round5-source-validation-4a1f3db/`. Disposable generated/build trees: `.work/post-round5/`. They are not committed. An initial MSYS make attempt failed because its POSIX shell interpreted the Windows `MKDIR_P`; native MinGW make then built both projects. An initial clean-snapshot pytest call from the wrong cwd failed two `tools` imports; it was rerun from `apps/FCCG` and preserved as a separate log.
- Machine-readable `validation-runs.json` in that evidence directory records 14 principal commands, absolute cwd, OS/architecture, Python and installed dependency versions, local completion time, exit code, counts/outcome and SHA-256 of each log. `changed-materials-sha256.json` separately records every changed source/document and four new disposable ARM validation binaries. These are current-task hashes, separate from the six frozen hashes and their archive manifest.

## Original frozen evidence, copied without rebuilding

Reference: [FIELD_TEST_REFERENCE.md](FIELD_TEST_REFERENCE.md). Source root: `D:\python_software\SilverStar\.work\round5\final\Round5_Field_Qualification\`. Durable read-only destination root: `D:\python_software\SilverStar\release-evidence\round5-frozen-4a1f3db\`. Every source and destination SHA-256 matched the reference before and after copying. The manifest is `archive-manifest.json` (4,801 bytes, SHA-256 `ef4ff1be64181f86c540fc7bdbbbf9979b92d952e2aebeeddac87c467bb8cc87`).

| Relative path in both roots | Bytes | Reference = source = archive SHA-256 | Status |
| --- | ---: | --- | --- |
| `SilverStar.ssproject` | 71,490 | `cead735fe445f997c3b1b1113715b4344cdc61e517137d01be41ee4d8b9bbad7` | MATCH, read-only copy |
| `Round5_Field_Qualification.ssdecoder` | 140,616 | `5de25f2c2436af09f63fd3518024a88737c6719e249f8f539b10f00da1a8b43f` | MATCH, read-only copy |
| `Flight_Controller/build/FCCG/SilverStar_F407/Release/SilverStar_0_1_0.elf` | 3,212,112 | `2c9e2442c3676d8466ce13db82658bf53bc5f2127f73e2a402a6ec4376734dce` | MATCH, read-only copy |
| `Flight_Controller/build/FCCG/SilverStar_F407/Release/SilverStar_0_1_0.bin` | 312,776 | `623851b3cd4d39932fd598b0c90276c887e8494f1d99fbf1d636a5e207a9a903` | MATCH, read-only copy |
| `Ground_Station/build/ground.elf` | 47,856 | `115e3cc7e4e7d6cb17b625b5616e4643f12557e7785d220b3bd0d5810b3ef596` | MATCH, read-only copy |
| `Ground_Station/build/ground.bin` | 20,860 | `9f140e72b6faadcc9f19b58e4c6fe1c6aab84f26387baa74ca3b17dc1a0b5c45` | MATCH, read-only copy |

These are existing Round5 artifacts. No package, portable app, installer, release archive or new *frozen candidate* was generated. Separate **new disposable validation binaries** were built from changed source: fresh-v2 F407 ELF 3,212,376 bytes SHA-256 `223386f96c0956f42b2aef55ff77327e0d89a20ca64150d61c635209785cfdb2`, BIN 313,000 bytes SHA-256 `bff7dcfdbfa387cd23f0f2b28b4bb49c327a759df32a6f750b55585c2c059854`; fresh F103 Ground ELF 47,856 bytes SHA-256 `115e3cc7e4e7d6cb17b625b5616e4643f12557e7785d220b3bd0d5810b3ef596`, BIN 20,860 bytes SHA-256 `9f140e72b6faadcc9f19b58e4c6fe1c6aab84f26387baa74ca3b17dc1a0b5c45`. Matching Ground hashes do not turn a new build into the original archived file. None of these new binaries belongs in Git or substitutes for the frozen reference.

## Source changes

- Root Apache-2.0 LICENSE and [source license audit](../architecture/SOURCE_LICENSE_AUDIT.md); vendor terms remain separate. Copyright ownership, Semtech source license text and final binary obligations remain unresolved release checks.
- FCCG format-14 schema and current-format docs aligned with serializer; `.ssflp` v3, AIR M0, SSLOG 0.0 and product `VERSION` remain unchanged.
- Tracked the three real `silverstar_fccg.build` Python files through a narrow `.gitignore` exception. The independent HEAD+staged-patch checkout imported `FccgService` and collected 15 runtime safety cases without using the original workspace's ignored source files.
- Repaired Ground generated `<stddef.h>` dependency; Power of Ten path matching and vacuous assertion counting; added focused regressions and defensible runtime state checks. See [the supplemental audit](../FCCG/POWER_OF_TEN_SUPPLEMENTAL_REPAIR.md) for the remaining Rule 5 failures.
- Added a blank [controlled bench session record](FIELD_QUALIFICATION_RECORD_TEMPLATE.md). The frozen KF6 candidate's ESKF15 smoke is `N/A`, not a PASS or a gate for this candidate.

## Validation matrix

Commands used the shown cwd with `.work/` pytest basetemp and offline Qt (`QT_QPA_PLATFORM=offscreen`). `PYTHONPATH=src` was set for FCCG host tests. Full outputs and per-file completion times are in the log directory above. Exit status is shown explicitly.

| Test / command and cwd | Result | Durable log |
| --- | --- | --- |
| From external `%TEMP%/SilverStar-source-validation-4a1f3db`, `python GSHC.py` with event loop intercepted after visible GUI inspection | PASS, exit 0; one window, application version and label 0.1.0 | `gshc-source-gui.log` |
| Same external cwd, `python FLP.py` with equivalent offscreen GUI inspection | PASS, exit 0; one window, label `v0.1.0`; `python FLP.py --version` and `python FCCG.py --version` also returned 0.1.0 | `flp-source-gui.log` |
| `apps/GSHC`: `pytest tests/test_i18n.py tests/test_ui_workflow.py tests/test_air_protocol.py tests/test_navigation_gui.py -q` | PASS, exit 0, 49 passed | `gshc-targeted-pytest.log` |
| `apps/FLP`: `pytest tests/test_version.py tests/test_project_export.py tests/test_gui_smoke.py tests/test_silverstar_project_root.py -q` | PASS, exit 0, 28 passed | `flp-targeted-pytest.log` |
| Root: `pytest tests/integration -q` | PASS, exit 0, 8 passed; root suite does not cover all apps | `integration-pytest.log` |
| `apps/FCCG`: affected schema/checker/generation/runtime/Ground host suite | PASS, exit 0, 53 passed | `fccg-affected-pytest.log` |
| `apps/FCCG`: final targeted runtime/schema/checker/USB rerun | PASS, exit 0, 28 passed | `fccg-final-targeted.log` |
| `apps/FCCG`: `pytest tests/test_gui_smoke.py -q` with Qt offscreen | PASS, exit 0, 15 passed | `fccg-gui-smoke.log` |
| Final independent checkout from `HEAD` plus staged binary patch, cwd `apps/FCCG`: runtime safety and affected host tests | PASS, exit 0, 29 passed; no original untracked or ignored source used | `clean-snapshot-final-rerun.log` |
| New F407 Flight `mingw32-make -j2`, `artifact-check memory-report stack-report` | PASS, exit 0; ARM compile/link, task stack margins positive in latest check | `flight-arm-v2.log`, `flight-static-audit-v2.log` |
| New F103 Ground `mingw32-make -j2` | PASS, exit 0; ARM compile/link | `ground-arm-mingw-fresh.log` |
| Official Flight Power of Ten, fresh-v2 | **FAIL**, exit 1, 194 Rule 5 findings | `flight-power10-v2.log` |
| Official Ground Power of Ten, fresh source | **FAIL**, exit 1, 13 Rule 5 findings | `ground-power10-fresh.log` |
| Python `compileall` on three applications' formal source directories and launchers; unified venv Ruff on changed Python | PASS, exit 0 for both | `final-quality.log`; no claim of full-repo lint |
| Local Markdown relative-link check and final root integration | PASS, 30 local links resolved; integration 8 passed, exit 0 | `integration-final.log` |

The first clean-snapshot pytest invocation from repository root had **2 environment import failures** because the test's `tools` module is relative to `apps/FCCG` (`clean-snapshot-pytest.log`). A second invocation used the correct cwd but placed pytest basetemp outside the clone's authorized workspace, causing **1 policy-path failure** (`clean-snapshot-pytest-cwd.log`). In the final clone, the first invocation lacked an ignored `.work/` parent, causing **27 setup errors** (`clean-snapshot-final.log`); creating that parent and rerunning yielded 29 passes (`clean-snapshot-final-rerun.log`). These infrastructure failures are retained, not described as product failures or deleted. A POSIX-shell Make attempt similarly failed on Windows-specific Makefile directory syntax (`ground-arm-fresh.log`); the native Make result is the build result.

An initial broad `compileall apps/FLP` encountered intentionally invalid Python text in old ignored `.work/pytest-round4-*/repo/src/change.py` cleanup fixtures. The source-only rerun excluded ignored work directories and passed; both commands and exit codes remain in `final-quality.log`.

## Pending gates and dates

- **Current controlled KF6 bench entry:** archived reference identity, source GUI/host tests, fresh ARM compile and blank forms are available. Formal software checker remains FAIL; its 194/13 Rule 5 findings need engineering review and safe fixes or an explicitly justified disposition before the project calls this gate cleared. Physical qualification has not started here.
- **2026-10-05 engineering target:** at risk until Power of Ten review and controlled bench evidence. The date is a planning target, not a waiver.
- **2026-10-12 release target:** blocked by missing physical evidence, target timing, exact license/ownership review and source dependency lock, actual Windows packaged-app and installer tests. No release permission follows from that date.
- **Deferred package-only defects:** source-version readers in `apps/GSHC/config.py` and `apps/FLP/src/silverstar_flp/app/version.py` assume source-tree parent depths; the GSHC installer input path does not match the current `.work/package/GSHC/dist` output; an old `0.0.3` package filename appears in packaging instructions. These were not changed or tested as packaged applications. Source execution from an external cwd passed, which does not prove frozen application startup.
- **Physical data still required:** actual F407 and new SilverStar Ground F103 board integration with safe outputs, JY901B/M9N/radio and TF identities, calibration generations, real log/decoder readback, GSP link behavior, timing and error cases. USB CDC, unselected new devices and ESKF15 have their own later applicable hardware checks and do not become prerequisites for the selected KF6 configuration.
