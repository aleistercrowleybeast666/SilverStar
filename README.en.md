# SilverStar

[简体中文](README.md) · English

An open-source toolchain for avionics development on unguided sounding rockets: configure hardware and generate projects with **SCG**, monitor ground telemetry with **GSHC**, and inspect recorded logs with **FLP**.

**Stable release: [v0.1.2 · 2026-10-12](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2)** · [Download for Windows](https://github.com/aleistercrowleybeast666/SilverStar/releases/download/v0.1.2/SilverStar_0_1_2_Windows_Portable.zip) · [Sample logs](docs/public/examples/README.md#english) · [Documentation](docs/public/README.md) · [Issues](https://github.com/aleistercrowleybeast666/SilverStar/issues)

## Download and try it

The portable package runs on **64-bit Windows 10/11** without a separate Python installation. Extract the complete archive and launch `SCG.exe`, `GSHC.exe`, or `FLP.exe`. All three share `_internal`; keep the directory structure intact.

1. **Explore configuration:** open SCG to browse devices, navigation, telemetry, and hardware settings. Generate projects into a writable folder outside the package. Building firmware also requires Arm GNU, Make, and the appropriate hardware resources.
2. **Explore the ground station:** open GSHC while disconnected to browse the interface. Live data requires a matching ground station and communication link.
3. **Open real recorded data:** download static bench record `000044` and its `.ssdecoder` from the [sample page](docs/public/examples/README.md#english). Open the log in FLP, select that decoder, and choose **Recorded** to inspect the original data, mission summary, and charts. Record `000045` provides a second example. No connected hardware is needed.

GSHC defaults to `D:/SilverStar_GSHC_Data`. If that drive is unavailable, or you prefer another location, open PowerShell in the portable package folder:

```powershell
$env:SILVERSTAR_GSHC_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'SilverStar_GSHC_Data'
& '.\GSHC.exe'
```

<details>
<summary>Verify the v0.1.2 download</summary>

File: `SilverStar_0_1_2_Windows_Portable.zip`, **220688183 bytes**. Its SHA-256 matches the value published in the [Release](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2):

```text
3330d83f49a2665c9052ad624719c22c484dde84507b02024868ded4f6ecce8e
```

</details>

## The three tools

| Tool | What it does | Guide |
|---|---|---|
| **SCG** · System Configuration & Generation | Configure sensors, navigation, telemetry, and missions; check pins and peripheral resources; generate STM32 Flight/Ground projects and matching decoder packages | [SCG](docs/public/SCG/README.md) |
| **GSHC** · Ground Station Host Computer | Receive AIR M0 telemetry; display readiness, attitude, trajectories, and mission events; record sessions and export charts and tables | [GSHC](docs/public/GSHC/README.md) |
| **FLP** · Flight Log Processor | Open exact log/decoder pairs, inspect record integrity, trajectories, and filter data, and recompute, compare, and export analysis results | [FLP](docs/public/FLP/README.md) |

SCG offers Full, Standard, Lightweight, and Minimal configuration tiers. Navigation components include Pure INS, SF6, KF6, and ESKF15. Devices and algorithms use declarative plugins. FCCG is SCG's former name; the `silverstar_fccg` package and older entry points remain compatible.

These are **real Qt screenshots captured offscreen using the official v0.1.2 program files**, showing actual project and log opening results. See the [illustrated walkthrough](docs/public/V0_1_2_WALKTHROUGH.md#english) for steps and capture provenance.

### SCG: configuration to generated projects

SCG opens FINAL and displays its actual navigation sources, calibration, and initial alignment settings. This walkthrough does not regenerate or flash the project.

![Real SCG v0.1.2 Qt offscreen capture: FINAL navigation configuration](docs/public/assets/v0.1.2/scg_final_navigation.png)

### GSHC: ground telemetry and status

Post-processing reads an existing JSONL session and completes export while the live connection remains disconnected. Readiness follows actual device reports: an ACK acknowledges a command and does not mean READY.

![Real GSHC v0.1.2 Qt offscreen capture: historical session processing completed](docs/public/assets/v0.1.2/gshc_offline_session_export.png)

### FLP: recorded logs and offline analysis

FLP opens FINAL record `000062` with its exact decoder and displays the **Recorded** summary and integrity information. The [walkthrough](docs/public/V0_1_2_WALKTHROUGH.md#english) also shows the actual velocity chart.

![Real FLP v0.1.2 Qt offscreen capture: Recorded overview for record 000062](docs/public/assets/v0.1.2/flp_000062_recorded_overview.png)

## Samples and documentation

The [hardware-free tour and sample downloads](docs/public/examples/README.md#english) link to two committed historical bench logs and their exact decoder, pinned to the v0.1.2 source tag. Download them separately; they are not included in the Windows portable archive. They were recorded with older firmware and are not v0.1.2 flight tests.

FLP requires an original `.BIN` / `.sslog` and a `.ssdecoder` matching its Descriptor identity. Missing or mismatched packages produce an error. Recorded means values actually recorded; recomputation and What-if are separate analysis results. Preserve the original log and decoder, and export into a new directory.

| Start here | Contents |
|---|---|
| [Three-tool workflow](docs/public/USER_WORKFLOW.md) | Configuration, generation, ground monitoring, offline analysis, and export |
| [Windows package](docs/public/WINDOWS_PACKAGE.md) | Runtime layout, data locations, and external tools |
| [Documentation index](docs/public/README.md) | Application guides, plugins, APIs, and shared contracts |
| [Support matrix](docs/public/SUPPORT_MATRIX.md) | Hardware combinations, configuration starting points, and verification scope |
| [Navigation implementation](docs/public/algorithms/NAVIGATION_IMPLEMENTATION.md) · [Formula PDF](docs/public/math/navigation-models.pdf) | Implementations, coordinates, notation, and assumptions |
| [Release introduction and tutorial](https://www.kechuang.org/t/92068) | v0.1.2 features and recorded examples |

## Stable release and development

Use the [v0.1.2 Release](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2) for downloads and the [v0.1.2 tag](https://github.com/aleistercrowleybeast666/SilverStar/tree/v0.1.2) for exact source. Remote `main` uses that version as its baseline and can receive documentation updates. The **0.1.3 development line is unreleased**; the root `VERSION` identifies the checked-out source version.

The configurations tested for v0.1.2 include an STM32F407 flight controller and an STM32F103 serial ground station, with bench, handheld, and thrown-object recordings. These do not establish rocket flight validation. Native USB CDC paths for F103/C071 remain experimental, with restricted normal generation and no completed verification on the corresponding USB hardware. Magnetometer workflows, IEKF, maintenance protocols, and other 0.1.3 work depend on their individual documentation and acceptance status. Android remains a development application with real USB/control gates; DeviceService is a mock-only prototype. Neither is included in the v0.1.2 desktop package.

The [version and evidence notes](docs/public/shared/VERSIONS_AND_EVIDENCE.md) and [software verification guide](docs/public/SOFTWARE_VERIFICATION.md) describe the scope of individual checks. Software checks do not replace hardware verification. The project's Power of Ten checker is an F Prime-inspired adaptation; manual critical-contract review remains NOT PROVEN.

### Run from source

Download the v0.1.2 source tag for the stable version; development checkouts use their own version and documentation. With Python 3.11+, run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe SCG.py
.\.venv\Scripts\python.exe GSHC.py
.\.venv\Scripts\python.exe FLP.py
```

Each launch command starts one application. Use `tools/setup_venv.ps1` for test and packaging dependencies. Install the firmware toolchain separately; see the [build guide](docs/public/SCG/BUILD.md).

## Feedback and licensing

Report bugs and suggestions through [GitHub Issues](https://github.com/aleistercrowleybeast666/SilverStar/issues). Include the software version, relevant hardware configuration, reproduction steps, and logs. For log parsing issues, also attach the matching `.ssdecoder`.

Original SilverStar source uses the [Apache License 2.0](LICENSE). Third-party code and dependencies retain their own terms. See [third-party provenance and licenses](docs/public/licenses/README.md) for the SX1280 library's origin, modifications, and unresolved licensing matters.
