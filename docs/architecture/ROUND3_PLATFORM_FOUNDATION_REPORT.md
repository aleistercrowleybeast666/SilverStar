# SilverStar 0.1.0 Round 3 platform foundation

This is a pre-release implementation report. No public 0.1.0 release has been made.
Product version remains 0.1.0. AIR M0, GSP, SSLOG, decoder and navigation
contract identities were not changed.

## Phase A — FCCG configuration and build workflow

FCCG navigation now has exactly seven user pages: Flight Devices, Flight
Configuration, Navigation Configuration, Telemetry Configuration, Flight
Hardware, Ground Station Hardware, and Build & Validation. Flight radio and
AIR protocol belong to Telemetry; existing alignment, INS, KF6, ESKF15 and
manifest-driven algorithm parameters remain accessible in Navigation.
Engineering numeric fields commit on Enter or editing finished. Flight and
Ground TX power are endpoint values; frequency and PHY remain shared AIR
Link values. Each hardware page offers its own one-step prepare-and-generate
action. Build & Validation places lightweight toolchain detection first, then
separate build, clean, workspace and artifact actions for each generated
target. Ground disabled does not block Flight operations.

## Phase B — project folder and FLP

FCCG's user-facing save creates `SilverStar.ssproject` and `Log/` in the
selected project root. Flight and Ground generation independently write to
`Flight_Controller/` and `Ground_Station/`. Each target has its own Makefile,
build tree and `Flight_Controller.code-workspace` or
`Ground_Station.code-workspace`. Successful Flight logging generation
atomically updates the canonical root `<ProjectName>.ssdecoder`; stale root
decoder identity is removed when no valid decoder is generated.

FLP's Open SilverStar Project Folder action discovers only root decoder
packages and logs below `Log/` to a bounded depth, offers one-log selection,
then applies exact decoder matching. Project-root exports default to
`Log/<LogStem>_Export/`. Standalone logs and decoders still work. See the
[project folder contract](PROJECT_FOLDER_CONTRACT.md).

The legacy direct `FccgService.Project_Save` API still materializes a
buildable Flight snapshot at the path explicitly passed to it; the current
FCCG GUI uses `ProjectRoot_Save` and target-scoped generation for the new
folder contract. Its existing lifecycle tests remain useful for that direct
API and now expect the renamed Flight workspace file.

## Phase C — Ground firmware

The Ground UART and USB CDC choices use one bounded PC byte stream and one
GSP implementation. USB requires imported CubeMX USB Device CDC capability,
callback, descriptors, middleware and HAL PCD/USB LL sources. Receive-ring
overflow is counted; `USBD_BUSY` retains a queued frame for a later retry.
GSHC continues to use pyserial for both UART adapters and USB virtual COM.
Flight SS0.5 no longer appears as a Ground production board; the GS_SS1
F103 board remains a read-only hardware and behavior reference, not a
verified F407 target. See [Ground Station](GROUND_STATION.md).

No matching real CubeMX USB CDC generated project was available for this
round. USB CDC schema, renderer, callback injection and buffer tests are
software checks. USB CDC firmware compile/link and board operation are
**HARDWARE_UNVERIFIED**.

## Phase D — device startup

`SystemStartup_Run` now performs only internal time, lifecycle and health
initialization plus early SAFE output setup before the scheduler. DeviceTask
advances console, logical devices, configuration, other adapters and bounded
communication checks after scheduling. It waits for delegated configuration
verification before completing the report and entering preflight. A failed
required device blocks mission readiness. JY901B and NEO-M9N adapters now
own their bounded startup controllers through their normal `Process`
callbacks; controllers probe target, factory and declared candidates, read
current configuration, write differences with communication changes last,
reconnect, verify and wait for a new sample. No automatic JY SAVE or u-blox
BBR/Flash write occurs. Debug log records each state change and failure code.
Other device adapters keep their bounded immediate post-scheduler startup.
Source selector ordering and in-flight locking were not redesigned.

The startup tests cover candidate fallback, timeout, read-before-write,
write-only-differences, reconnection, verification, sample gate, pre-scheduler
device exclusion and delegated configuration waiting. ARM compile/link checks
software integration; physical timing, UART electrical behavior and sensor
configuration remain **HARDWARE_UNVERIFIED**. See [device startup](DEVICE_STARTUP.md).

## Validation

Validation artifacts are created below ignored `.work/` directories.

- FCCG Round 3 UI, target, lifecycle, domain and startup controller tests:
  **35 passed**. The two lifecycle expectations updated in this round used
  the obsolete per-project workspace filename; generation already emitted
  `Flight_Controller.code-workspace`.
- FLP project-root and export tests: **17 passed**.
- GSHC AIR plus shared GSP and monorepo integration tests: **20 passed**.
  GSHC export and offscreen GUI tests touched by lint cleanup: **5 passed**.
- Generated Flight startup Host tests: **4 executables, 244 checks, 0
  failures**, including delegated startup with explicit verify disabled.
- Existing JY901B/M9N device and adapter, multi-instance, source selector and
  runtime startup Host regressions: **8 executables, 1,205 checks, 0 failures**.
- A fresh generated Flight reference project compiled and linked with ARM
  GCC to `SilverStar_0_1_0.elf`. A fresh Ground UART reference project
  compiled and linked to `ground.elf`. The Ground UART fixture reuses Flight
  SS0.5 hardware only inside ignored test output; it is not a production
  Ground board selection.
- Python `compileall`, relevant Ruff E4/E7/E9/F checks and `git diff --check`
  passed. Root launcher and documentation integration checks are included
  in the monorepo suite.

The long historical storage stress suite and real board/radio tests are
outside this round's software gate. USB CDC firmware compile/link remains
unverified for lack of a real matching CubeMX CDC generated project.

## Workspace audit

At the final audit, source outside `.git`, `.venv`, caches and ignored work
areas was about **25.2 MB**. There were 1,518 tracked files; the largest
tracked file was a vendor CMSIS header at about **1.19 MB**. No nested `.git`
or `.venv` appeared in any application. Ignored work areas held approximately
**1.02 GB** in root `.work/`, **1.29 GB** in `apps/FCCG/.work/` and **4.8 MB**
in `apps/FLP/.work/`, including generated firmware snapshots and pytest
evidence. The largest root work directory was an earlier Round 3 reference
project at **214 MB**; the final Flight/Ground build snapshot was **38 MB**.
These ignored artifacts were retained for inspection; no recursive cleanup
was performed. They are not tracked source or release content.

## Round 4 prerequisites

Validate JY901B and NEO-M9N startup on a real Flight board, including wrong
saved baud, partial configuration, device absence and power cycle. Import a
real F407 Ground USB CDC CubeMX project and verify enumeration, sustained GSP
traffic, BUSY recovery and RX overflow on hardware. Add new hardware only
with verified manifests and driver evidence. The planned Alignment,
magnetometer calibration and Persistent Storage changes remain separate
Round 4 work.
