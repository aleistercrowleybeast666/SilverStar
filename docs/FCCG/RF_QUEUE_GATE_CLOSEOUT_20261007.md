# RF 56/16 gate closeout — 2026-10-07

RF dependency review, static task stack admission and portable single-GNSS Host
binding are complete for the recorded validation scope. **RF 56/16 is not an
accepted default candidate:** its matching real-storage Host pressure run fails
the unchanged non-overflow startup-burst requirement. No daily synchronization
or default queue change is made by this batch.

Base: `ac438cced40939d62fab12549417e860c82fa8fc`. Isolated branch:
`integration/rf56-reviewed-20261007`, reusing `.work/kh`; no new whole-repository
or generated-project copy. All mathematical target sources and parameters are
unchanged. Source/dirty snapshot, exact commands, exit codes, raw logs, input
fingerprints and linked artifact hashes are retained under
`.work/kh/.work/rf_queue_evidence/v9`.

## Priority compatibility finding

Daily `ac438cc` GSHC **cannot consume NRF GSP 0x05**. Its
`apps/GSHC/protocol/common.py` GspType defines only 0x01–0x04;
`protocol/gsp_min.py` dispatches AIR_RX 0x02 and returns None for 0x05;
`protocol/receive_pipeline.py` only decodes GsToPcAirFrame into AIR messages.
The shared `contracts/gsp_air_rx_radio_v1.json` explicitly says old clients
ignore type5 and cannot display NRF AIR data.

“GSHC unchanged” in the previous integration report meant relative to
`cd76d8e0c8ccddb28e823e0f6ab6d47613276f51`; its GSHC tree and daily ac438cc's
are identical. `193ba4c72975784c60b8c32efab9216cebb34f3e` is not an ancestor
of daily. Its ancestor `8dae22c243664aa138f6797fbf0e1da1f8e162d8` adds paired
NRF GSHC support across seven files; 193ba4 itself only corrects Ground CRC
accounting. The seven-file source comparison is included read-only in the
parent evidence package. This batch does not merge that separate implementation.
Daily NRF generation therefore remains functionally incompatible with current
daily GSHC; no end-to-end readiness claim is made.

## Source changes and reviewed gate

Both owning core Host NEO-M9N fixtures now obtain logical UART from
`ProjectNeoM9nResources_Get(0U, ...)`, checking status and valid UART range before
running scenarios. There is no externally injected UART1 shortcut. A missing
resource or invalid UART explicitly fails the fixture. All existing startup,
no-fix, recovery, parsing and adapter assertions remain.

The owning stack checker and reference overlay record review v9:

- All 152 actual C units and 375 transitive compiler-reported project inputs
  remain checked, including .inc and other suffixes.
- 149 complete C source bodies already matched reviewed versions. The three
  remaining C variants are generated log selection and decoder/config identity
  only; two generated headers add the already reviewed physical epoch contract
  and catalog physical identifiers. Exact five-file differences are retained.
- Of 34 unrecognized dependency graphs, 31 add the already reviewed physical
  epoch interface. The remaining three are its reviewed implementation, the
  existing typed mission-radio implementation and the real F1 FatFs/HAL
  persistence dependency chain. Each source body and every included input byte
  is reviewed before registering the exact ordered graph hash.
- No source exclusion, new callback allowance, wildcard fingerprint, pointer
  exception, stack threshold or critical-contract acceptance is introduced.
- Actual source/dependency admission passes for all 152 C units. An added .inc
  dependency, changed reviewed header and changed C-source fingerprint each
  fail closed. All small mutations were restored byte-for-byte. These negative
  checks are scanner/admission tests, not MCU recovery or a mathematical change.

Normal regeneration preserves project-owned payloads. Only proven disposable
RF validation Tools/two Host fixtures were explicitly refreshed from the
selected owning catalog, after changing the owners first; previous bytes are
retained. The target C compilation inputs and mathematical parameters remain
identical to the earlier actual RF link. The emitted v9 stack gate is executed
against that exact ELF/.su/.d set, not an old binary from another revision.

## Actual checks and unresolved failure

| Verification | Actual result |
|---|---|
| RF emitted v9 stack gate | exit 0; all seven tasks meet existing 256-byte margin gate |
| Checker regressions | 51 PASS; existing pytest cache_dir warning retained |
| Selected RF Host, real generated UART1 | nine executables / 76462 checks / zero failures; one compile positive, three specific noise-contract rejections |
| All RF wrapper jobs, queue56/16 | 77 executables / 4436696 counted checks / zero failures; six compile positives, 16 named rejections |
| Four invalid/missing-resource Host injections | both owning fixtures reject both faults before driver scenarios |
| Ordinary F407 generated UART2 regression | two executables / 33839 checks / zero failures; no UART or queue override |
| Original RF storage helper at normal80/est48 | exit 0, real F1 diskio/FatFs/codec and strict decoder audit |
| Same helper with queue56/16, same selected model | exit 1 at startup-burst: ordinary queue 56/56, 217 drops/producer failures |
| Single capacity counterprobe queue64/16 | exit 1 at startup-burst: ordinary queue 64/64, 22 drops/producer failures |

The all-wrapper count includes `barometer_cold`, which reports PASS without a
numeric check count; 4436696 is the sum of actual emitted numeric counts. Named
unselected provider/algorithm rows and unsupported-stream positive portions
retain their NOT_APPLICABLE labels and are not presented as executed positives.

Wrapper jobs and storage were separate actual invocations. The unchanged
single complete Host entry point was not run with automatic queue forwarding;
its storage child currently reads generated default80/48 even when ARM uses
an external56/16 makefile. The explicitly matched independent56/16 run exposes
the real failure. **Do not stitch the passing wrapper and 80/48 storage runs
into a claimed 56/16 full-suite PASS.** No Host/generator gate was weakened to
hide this mismatch or the resulting failure.

The original storage helper's general logical-record stress has a 5 ms producer
epoch and injects BARO_NATIVE each epoch (200 Hz), along with IMU, GNSS, increments
and selected synthetic records. This is heavier on the ordinary queue than the
configured real BMP280 20 Hz, and it does not execute the RF four-group SF6
producer. Its safety expectation still fails and remains recorded; the failure
is not a measured RF hardware overflow. Accepting 56 requires separately
justified actual RF 200/20/25 Hz producer/storage-pressure coverage or a capacity/
storage change that preserves the existing expectations. Neither is claimed
complete here. 64 is only a failing Host capacity probe; no ARM/analyzer/stack
result is claimed for 64, and further capacity searches were not performed.

The real56 storage run first passes disk byte-integrity and bounded timeout/
wrong-transfer/start-transfer/sync fault cases, then passes normal, declared
overflow and startup-overflow writer modes with strict decoder/drop accounting.
It aborts at non-overflow startup-burst; subsequent overload/preflight/diagnostic
modes are NOT_RUN for56. Successful80 runs do not substitute for them. Complete
failure traces and all recorded software-generated logs remain preserved.

Static task estimates / reservations / margins (bytes): Device2112/2560/448;
INS2224/3072/848; Estimator1504/4096/2592; Flight3480/4096/616;
Logger2736/3072/336; Telemetry2168/4096/1928; Idle256/512/256. This actual RF
ELF resolves the historical Logger3072/3072 static budget issue; it does not
prove runtime high-water or whole-program main/MSP/ISR bounds.

## Resource and logging facts available to parent

The Library evidence zip includes `RET_RF_PARENT_REPORT_20261007.md`, its full
JSON/module/resource/40-record tables, actual generated headers, SourceGraph,
two exact decoder packages and raw gate logs. The body lists all20 enabled RET
and all21 enabled RF streams with policy, decimation, period and payload/wire
bytes. Decoder `firmware_commit` and creation time are retained historical model
metadata, not attribution for the current link; current source snapshot and ELF
hashes are provided separately.

RET actual Minimal24/16: Flash209472 / BIN209480 bytes, RAM54208/65536, spare
11328 (17.285%), 20% gap1780. RF actual56/16: Flash256748 / BIN256752 bytes,
RAM86872/98304, spare11432 (11.629%), 20% gap8229. Same-source RF80/48 ARM
control: RAM98072, Flash256756; net56 savings11200 RAM /8 Flash. Task stacks
21504 and MSP2048 are already counted once in those RAM totals. Full linked
symbol attribution is included. Neither target meets20% spare RAM.

RET is MPU6050 + NRF24 + BMP280 without GNSS. RF preserves MPU6050 + M9N +
E28-2G4M12SX + BMP280; both retain local SDIO SSLOG, Cortex-M3 softfloat,
FreeRTOS CM3, vector-constraints alignment, coning2/sculling2 and SF6,
maintenance OFF. The official previously executed CubeMX snapshot is reused;
no new CubeMX/hardware execution is claimed by this gate-only closeout.

Each record has24-byte header +4-byte CRC. Configured nominal items are:
IMU_CORRECTED200Hz*88=17600 B/s; INERTIAL_INCREMENT approximately100Hz*80=8000;
BARO_NATIVE20Hz*80=1600; STATS1Hz*44=44; HEALTH1Hz*68=68; SF6_STATE10Hz*100=1000;
SF6_MEASUREMENT baro group4 nominal20Hz*84=1680. RF adds GNSS_NATIVE25Hz*140=3500
and, only with valid preflight GNSS frame and admitted new samples, four GNSS
groups*25Hz*84=8400. These items total RET29992 and RF41892 B/s under those
conditions, plus landing80*f_L, events40*f_E and calibration/alignment/startup
metadata counts. This is not measured or guaranteed SD throughput. GNSS no-fix
does not itself establish communication failure. Baro-only horizontal position
remains inertial and can drift.

Power10 text gate remains explicitly critical-contract NOT_PROVEN; original
first-party scope, recommendations and other rule thresholds are unchanged.
Full hardware/flight/WCET, runtime high-water, main/MSP/ISR/third-party stack and
complete manual safety acceptance remain NOT_PROVEN/NOT_RUN. Any failed
pressure gate blocks a complete acceptance claim. No hardware action, flash,
publish or push was performed. No default/daily sync follows this failed probe.

All compiler sessions for this batch have exited. A standard process-name check
after the final Host capacity probe found no gcc/cc1/ARM linker/LTO process;
remaining work is evidence/commit/upload only. Parent may continue its approved
cleanup while retaining `.work/kh` validation sources and formal evidence.
