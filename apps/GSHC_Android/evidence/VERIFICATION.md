# Verification — 2026-10-13

Current result: the independent Android project builds successfully, Android lint completes with **0 errors / 9 warnings**, and **14/14 Robolectric tests pass**. This is a debug APK and host framework validation, not phone, emulator or hardware acceptance. The current machine-readable record is [android-build.json](android-build.json).

Scope: only `D:/python_software/SilverStar_GSHC_Android` was writable by this task. SilverStar remained read-only. No phone installation, hardware connection, device command, device deletion, push, tag or release occurred. Both debug and release source configurations keep `ALLOW_USB=false`.

## Exact delivered artifact

- APK: [app-debug.apk](../app/build/outputs/apk/debug/app-debug.apk)
- Application: `cn.silverstar.gshc`; version `0.1.3-dev.1`; versionCode **1**.
- Size: **2,527,905 bytes**.
- SHA-256: `ebd76cfd2bc0be8c566d47cfec01628aaa150d37d4558bf5ef80e108ebcacd77`.
- APK v2 debug signature: verified with apksigner, exit 0. Debug certificate SHA-256: `f85db72c9e2213b19aa90219cbd0c78e4f5099716f9c56eca456a89fe162a483`.
- Java17 / native Android Views; minSdk26; compile/targetSdk36; AGP8.13.2; Gradle8.13; existing Microsoft JDK21.
- Packaged permissions: foreground service, connectedDevice foreground service, notifications, and AndroidX's internal signature broadcast permission. No INTERNET or broad-storage permission. Cloud backup and device transfer are excluded for app-managed data.

## Executed checks

| Check | Actual result |
|---|---|
| Unified `:app:assembleDebug :app:lintDebug :app:testDebugUnitTest` | **BUILD SUCCESSFUL in 55s**; exit 0 |
| AndroidIntegrationTest | 5 tests, no failures/errors/skips |
| LifecycleRegressionTest | 3 tests, no failures/errors/skips |
| RuntimeRegressionTest | 6 tests, no failures/errors/skips |
| Android lint | 0 errors; 2 GradleDependency and 7 SetTextI18n warnings; no baseline or suppression |
| `tools/test-core.ps1` | 56 protocol/state + 287 LOGFILE assertions PASS |
| `tools/test-pc-compatibility.py` | 152 decoded frames field-for-field; full and raw-only logs each yield 31 simulated flight samples |
| `tools/test-storage.ps1` | 113 generated-input assertions PASS |
| `tools/test-shared-export.py` | 56 shared Draft2020-12/golden assertions PASS |
| Existing `tools/render-layout-previews.py` evidence | 20 HTML cases PASS; 6 retained PNGs visually reviewed; browser-only |

Pure Java compilation uses `--release 17 -Xlint:all -Werror`. Framework tests use Robolectric4.17/JUnit4.13.2 and the Android36 framework on the host. Their generated reports are under `app/build/test-results/testDebugUnitTest/` and `app/build/reports/tests/testDebugUnitTest/`; lint reports are under `app/build/reports/`. No user files were deleted by tests. No new production source edits occurred after the successful unified build.

## Regression evidence

The native Activity tests inflate all four pages and both independent port entries, preserve the application session and page across Activity recreation, reject real USB before permission/claim, and verify SAF picker and mock DocumentsProvider operations through ContentResolver and file descriptors. Unique destination creation, sequential write/close/readback and revoked-provider failure are exercised. This does not establish behavior of every external DocumentsProvider.

Lifecycle tests hold real executor/lock barriers with fake closeable resources. Ground-service destruction returns without blocking the UI; an old lease stays reserved until I/O exits and resources close. Maintenance cleanup also waits for the active exchange to exit. Repeated old cleanup cannot release a replacement lease. Rotation invalidates an old recycle-list/dialog request without resetting the active session. Pure storage tests additionally bind restore to the selected recycle version and reject repeated or stale confirmation.

Runtime tests show that an old background callback cannot stop a new session, while current background and explicit-stop actions retain their intended behavior. Sampling consumes each decoded FLIGHT_STATE event. Fragmented and non-flight input cannot repeat cached points; batches, repeated timestamps and source order are preserved. The same simulation produces 31 identical live and replay points.

Storage checks cover active recording, corrupt/truncated output, changed source, close/readback failures, revoked access, unconfirmed/cancelled cut, cancellation/interruption and simulated ENOSPC during copy/export. Original bytes survive these failures. Successful cut is a separate explicit action after complete ZIP and per-file readback; it moves to the disclosed recoverable internal recycle directory. Permanent purge is not implemented. Share remains copy. SAF selection is explicit before TF download, and no seek, rename or overwrite support is assumed.

Earlier framework failures identified an actual layout feedback loop and an obsolete SAF query call. The layout now calls setMaxLines only when its value changes, and SAF uses the API26+ query overload. The original rotation/idle tests were retained and passed after those fixes. Timers use fixed delay. These were implementation repairs, not removed tests or suppressed lint findings.

## Protocol and desktop boundaries

AIR/GSP and PC parsing references remain frozen at v0.1.2, commit `c31c13cc0686a56a3184d4f207fd3816c5d39696`. The shared export schema is from `cb944b7c5a844da2f277494662801f2179a268ad`; the current read-only LOGFILE policy is separately snapshotted at `f2ce541382589cb606e1f5b21f6fd982357eaa54`.

Device and boot identities remain unknown. Device DELETE and cross-connection resume are disabled. Every TF attempt creates a fresh partial file and starts at offset 0; old partial and complete artifacts remain intact. No resume wire field or decoder identity was invented. The client exposes only CAPS/LIST/META/READ/CANCEL operations, and no real-device operation was performed.

The frozen PC test executes its JSONL reader and flight-data extraction with GUI/plot/preferences imports stubbed. It does not test the PC GUI or imply that the old PC directly opens the new ZIP: extract and open JSONL by its supported path. AIR telemetry cannot recreate missing high-rate TF data. FLP needs native .bin/.sslog plus the exact matching .ssdecoder/Descriptor; SSLOG0.0 and decoder1.2 remain distinct. Generated TF fixtures are synthetic, not valid flight logs. Future identity/resume/delete requirements are design-only in [SHARED_CONTRACTS](../docs/SHARED_CONTRACTS.md).

## Environment, license and disk

The minimal authorized toolchain is installed on D: cmdline-tools23.0, android-36 r2, build-tools35.0.0 and Gradle8.13. No Studio, emulator, NDK, platform-tools or additional SDK component was installed. Recovery checks verified existing archives/key JARs before reuse. The task-owned command-line archive was removed only after its resolved path and exact hash were checked and the installation/build succeeded.

Measured snapshot in [setup-status.json](setup-status.json):

| Component | Bytes |
|---|---:|
| Installed SDK | 430,620,815 |
| Gradle distribution | 151,645,130 |
| Gradle cache | 815,367,393 |
| Robolectric dependency cache | 213,433,269 |
| Android CLI/bootstrap/user data | 243,523,060 |
| Entire project, including code, outputs and caches | **1,923,679,536 (~1.79 GiB)** |

SDK license `android-sdk-license`, dated2019-01-16 from the official repository XML, was accepted under the user's confirmed authorization at **2026-10-13T05:06:19.522497Z**. Its exact normalized UTF-8/LF SHA-256 is `1f8729233617b193fd619213792ae16a41b95d2bbbf525dfe66998252ba68b16`. See [acceptance record](sdk-license-acceptance.json) and [SDK_SETUP](../docs/SDK_SETUP.md). Earlier pending-license and interrupted-build notes are historical, not current blockers.

The initial Android CLI bootstrap displayed a default metrics notice; actual upload is unknown. Later CLI calls explicitly used --no-metrics. The setup record documents this incident without claiming no upload. No global privacy setting or application cloud service was added.

## Remaining validation boundaries

There is no current build blocker. HTML screenshots are a separate design preview, never APK screenshots. The framework tests do not establish native visual/touch/IME/accessibility behavior, real Android26 execution, process-kill recovery, OEM foreground-service behavior, USB Host/OTG power or CDC/USB-UART driver compatibility. USB detach and cleanup are tested with controlled framework/fake-resource inputs, not a physical device. Real external SAF grant persistence/revocation and hardware interoperability require a separately authorized device session. Firmware stack/SRAM/USB acceptance is outside this client result.
