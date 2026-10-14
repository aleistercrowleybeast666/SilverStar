# Minimal official Android build environment

Installed on 2026-10-13 under this D-drive project after the parent explicitly confirmed that existing user authorization covers the actual repository SDK license. No Android Studio, emulator, NDK, platform-tools or release-signing identity was installed. Actual build/test results and current disk use are recorded in [VERIFICATION](../evidence/VERIFICATION.md).

## Toolchain and provenance

Existing Microsoft JDK21.0.12.1 is reused. Gradle8.13 came from [its official distribution](https://services.gradle.org/distributions/gradle-8.13-bin.zip), checked against the official SHA-256 endpoint, extracted into `build/toolchain/gradle-8.13`, and actually ran `--version`. SHA-256: `20f1b1176237254a6fc204d8434196fa11a4cfb387567519c61556e8710aed78`. Compressed 136,983,045 bytes; expanded archive 151,645,130 bytes. The verified archive was removed afterward.

| Installed package | Revision / official archive | Download bytes | Official metadata SHA-1 |
|---|---|---:|---|
| Command-line tools | 23.0 / `commandlinetools-win-16111833_latest.zip` | 154,957,218 | `57d04f2d75eb8e8fffc5000a987e5de4b5a63e9d` |
| `platforms;android-36` | r2 / `platform-36_r02.zip` | 65,878,410 | `2c1a80dd4d9f7d0e6dd336ec603d9b5c55a6f576` |
| `build-tools;35.0.0` | 35.0.0 / `build-tools_r35_windows.zip` | 59,878,107 | `af059bb67cf7786f45ee0db85e2d24985df1b4b6` |

Archive URLs are beneath `https://dl.google.com/android/repository/`. Metadata and installed package revisions come from [Google's official repository](https://dl.google.com/android/repository/repository2-3.xml); copies and installation metadata are under `build/setup`. All selected SDK packages use `android-sdk-license`. SDK archive total is 280,713,735 bytes; Gradle plus SDK archives total 417,696,780 bytes, excluding extracted files and Maven/build dependencies.

AGP8.13.2 [specifies Gradle8.13, Build Tools35.0.0 and minimum JDK17](https://developer.android.com/build/releases/agp-8-13-0-release-notes), and supports compileSdk36. The project targets36, minimum26. Initial build warnings report newer SDK XML metadata and absent platform-tools. SDK components are not installed automatically by the build script.

## License acceptance

The [2019 repository text versus 2026 website comparison](SDK_LICENSE_COMPARISON.md) established the same SDK license ID without additional identified obligations in the older repository text. The parent explicitly confirmed coverage under existing user approval. Accepted at **2026-10-13T05:06:19.522497Z**; exact normalized UTF-8/LF text SHA-256 is `1f8729233617b193fd619213792ae16a41b95d2bbbf525dfe66998252ba68b16`. License ID: **android-sdk-license**; date: **2019-01-16**; source: [official repository XML](https://dl.google.com/android/repository/repository2-3.xml). Full record: [sdk-license-acceptance.json](../evidence/sdk-license-acceptance.json). No other license was blanket-accepted.

The initial local-byte comparison detected CRLF/LF differences, not changed terms; the complete normalized text was subsequently confirmed identical. The historical read-only comparison does not indicate a current pending approval.

## Android CLI metrics incident

Command-line tools23's deprecated `sdkmanager.bat` delegates to the new Android CLI. The first invocation bootstrapped that CLI under `build/android-user/cli`, displayed its default metrics notice, and failed package argument parsing. It is **unknown whether that invocation uploaded metrics**. The notice alone proves neither upload nor absence of upload. Subsequent calls explicitly used `android.exe --no-metrics --sdk=... sdk ...`; no global privacy configuration, account, project credential, `android init`, or cloud service was added. The [official CLI documentation](https://developer.android.com/tools/agents/android-cli) documents `--no-metrics`. Avoid the deprecated wrapper for future setup. Do not perform additional uploads to investigate this historical incident.

## Reproduce the authorized build

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build-android.ps1
```

The script runs `:app:assembleDebug :app:lintDebug :app:testDebugUnitTest` and fails on a nonzero Gradle exit. It sets JAVA_HOME, ANDROID_HOME, ANDROID_USER_HOME, GRADLE_USER_HOME and TEMP/TMP only in its process, using D-drive directories under `build/`. It writes project-local `local.properties`, disables automatic SDK download, and refuses to run without installed SDK/Gradle. Both build types keep `ALLOW_USB=false`. The disposable debug keystore is explicitly at `build/android-user/debug.keystore`; no release key exists.

Robolectric4.17/JUnit4.13.2 local framework tests use generated data and a mock DocumentsProvider. Their runtime JAR is a test dependency, not an emulator image. Test home and dependency cache stay under D. No phone installation, emulator, USB connection or device command is authorized by a successful build. Additional licenses, large components or significant excess over the approved 2–4GiB budget require a new report before installation.
