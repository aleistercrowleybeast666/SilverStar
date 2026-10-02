# Navigation resource and bounded safety review, 2026-10-01

This is the historical P3 resource checkpoint, not the final candidate report. See [final handoff](NIGHT_FINAL_HANDOFF_20261001.md) for later source/candidate versions and full regression. The storage validation-versus-generation gap described below was subsequently repaired in `18afe8c` through the shared `StorageBinding_Resolve`, without weakening TF/START requirements. The nine tables below retain their original build provenance; the later ESKF15 logging build still has only1240 bytes of CCM spare.

This P3 checkpoint follows [native acceptance](NIGHT_ACCEPTANCE_20261001.md) and [five GUI quality actions](NIGHT_QUALITY_20261001.md). Firmware source checkpoint is `4bc9442` (numeric rejection fix); checker checkpoint is `976caa7`. The final report commit changes documentation only. All final resource projects use the firmware source HEAD and record the INS source SHA256. Existing `SS_0_5_TEST_4`, its imported-hardware revision and old frozen fixtures were not regenerated or modified. Their earlier four PASS builds belong to the P1 source checkpoint; the new fix is present in the isolated P3 projects below. No hardware connection, flashing, START, actuator operation, packaging, push, tag or Release occurred.

## Reproduction and actual configurations

Execution workspace is `D:\python_software\SilverStar`. Evidence is `.work/night_navigation_resources/`, including exact command arrays, tool versions, generated model snapshots, validation results, source HEAD/hash, elapsed times, exit codes, ELF/MAP/BIN paths and SHA256. `summary.json` contains nine completed final builds. Original pre-fix comparison outputs are preserved separately and are not counted as final PASS.

Scripts `.work/navigation_resource_build.py`, `.work/resource_summary.py` and `.work/resource_checks.py` generate and check isolated projects. The build command for each Flight_Controller directory is:

```text
D:/msys64/ucrt64/bin/mingw32-make.exe -j2 CONFIG=Release "GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin" all
```

Compiler is Arm GNU14.3.Rel1, GCC14.3.1 20250623; Make4.4.1. Release uses `-O2`, Cortex-M4, `-mfpu=fpv4-sp-d16 -mfloat-abi=hard`, function/data sections and linker garbage collection, GCC `.su` stack reports, no LTO and no fast-math. HAL/CMSIS/FreeRTOS and target/linker remain the actual F407 platform sources, not host firmware substitutes. Debug information enlarges ELF files but is not Flash occupancy.

All modes retain SS0.5/F407VET6, JY901B IMU/barometer/quaternion capabilities, M9N GNSS, voltage, indicator, launch/parachute device configuration, vector alignment and the same Apogee/Tilt deployment policies. IMU output200Hz, aggregation2 and GNSS25Hz remain unchanged. Action code/configuration is retained for resource comparison; no action was invoked. Mode selection alone is Pure INS/None, KF6 or ESKF15, with stable IDs0/1/2.

| Series | Exact service difference / purpose | Root prefix |
|---|---|---|
| `equal_logs_off` | Strict comparison: logging disabled identically, AIR telemetry and maintenance retained, same devices/resources/Ground configuration | `D:/stm32_project/.resource/20261001/numeric_guard/` |
| `capture_logs_on` | Same baseline SSLOG policy and services; product reconciliation enables the selected backend's mandatory/available records | same prefix |
| `minimum_services` | Actually buildable reduced service profile: logging and maintenance disabled, Ground disabled, maintenance device/resources removed; AIR endpoint and physical storage retained | `D:/stm32_project/.resource/20261001/numeric_guard_supported_minimum/` |

Each root ends in `<series>_<pure_ins|kf6|eskf15>/Flight_Controller`. These are three particular supported complete firmware profiles, **not an exhaustive minimum over configurations or an algorithm-only minimum**. Pure INS still has the shared estimator snapshot/task service and its storage; disabling fusion does not remove every object with an estimator name. Logging-on comparison is explicitly not an identical record list: Pure INS lacks unavailable fusion records; KF6 enables its estimator/measurement/recovery records; ESKF adds mandatory INITIAL_STATE, INITIAL_P_PART, MEASUREMENT and BODY_INPUT evidence. Periodic ESKF_STATE/FULL_P_PART are disabled in this baseline. Full resolved policies are in each JSON/model and exact generated decoder.

Two unsupported minimization probes were retained: removing AIR/radio returned `AIR_LINK_NO_RADIO` and `AIR_LINK_PHY_INCOMPATIBLE` before generation. Current validation evaluates the Flight AIR contract even with Ground disabled; there is no tested no-radio profile here. Retaining AIR but removing storage passed that validation and then generation rejected `Exactly one physical Storage Device must provide service.storage`. This validation-versus-generation diagnostic gap remains a follow-up; no validator or generator was weakened. The supported minimum retains physical storage and its dependency graph instead of claiming those failed probes worked.

## Linked resource results

### equal_logs_off

| Mode | text | data | bss (all RAM domains) | Flash | Main SRAM | CCMRAM | Build exit |
|---|---:|---:|---:|---:|---:|---:|---:|
| pure_ins | 229060 | 1132 | 86408 | 230192 | 46596 | 40944 | 0 |
| kf6 | 257652 | 1132 | 116992 | 258784 | 65916 | 52208 | 0 |
| eskf15 | 245772 | 1132 | 124600 | 246904 | 64508 | 61224 | 0 |

### capture_logs_on

| Mode | text | data | bss (all RAM domains) | Flash | Main SRAM | CCMRAM | Build exit |
|---|---:|---:|---:|---:|---:|---:|---:|
| pure_ins | 279524 | 1136 | 124832 | 280660 | 81952 | 44016 | 0 |
| kf6 | 312308 | 1136 | 155576 | 313444 | 101280 | 55432 | 0 |
| eskf15 | 298420 | 1136 | 163040 | 299556 | 99880 | 64296 | 0 |

### minimum_services

| Mode | text | data | bss (all RAM domains) | Flash | Main SRAM | CCMRAM | Build exit |
|---|---:|---:|---:|---:|---:|---:|---:|
| pure_ins | 176184 | 1132 | 71624 | 177316 | 42820 | 29936 | 0 |
| kf6 | 204860 | 1132 | 102208 | 205992 | 62140 | 41200 | 0 |
| eskf15 | 192872 | 1132 | 109816 | 194004 | 60732 | 50216 | 0 |

Flash is the production artifact check's loaded section accounting (`size` text+data); BIN length can include final alignment bytes and is separately recorded in artifact metadata. Main SRAM includes data, ordinary BSS, DMA BSS and the1024-byte linker MSP reservation. CCMRAM includes its own sections and must not be combined with main SRAM as freely interchangeable capacity. Capacities are Flash524288, main SRAM131072, CCMRAM65536 bytes. Static task stacks are already included in the reported RAM, not additional allocations. Reserved heap0 and runtime heap symbols0.

| Profile / mode | Total reserved task stack bytes | Individual task reservations (bytes) | Lowest static margin |
|---|---:|---|---:|
| equal_logs_off / pure_ins | 24576 | Device:2560/INS:3072/Estimator:4096/Flight:4096/Serial:6144/Telemetry:4096/Idle:512 | 256 |
| equal_logs_off / kf6 | 24576 | Device:2560/INS:3072/Estimator:4096/Flight:4096/Serial:6144/Telemetry:4096/Idle:512 | 256 |
| equal_logs_off / eskf15 | 24576 | Device:2560/INS:3072/Estimator:4096/Flight:4096/Serial:6144/Telemetry:4096/Idle:512 | 256 |
| capture_logs_on / pure_ins | 27648 | Device:2560/INS:3072/Estimator:4096/Flight:4096/Logger:3072/Serial:6144/Telemetry:4096/Idle:512 | 256 |
| capture_logs_on / kf6 | 27648 | Device:2560/INS:3072/Estimator:4096/Flight:4096/Logger:3072/Serial:6144/Telemetry:4096/Idle:512 | 256 |
| capture_logs_on / eskf15 | 27648 | Device:2560/INS:3072/Estimator:4096/Flight:4096/Logger:3072/Serial:6144/Telemetry:4096/Idle:512 | 256 |
| minimum_services / pure_ins | 18432 | Device:2560/INS:3072/Estimator:4096/Flight:4096/Telemetry:4096/Idle:512 | 256 |
| minimum_services / kf6 | 18432 | Device:2560/INS:3072/Estimator:4096/Flight:4096/Telemetry:4096/Idle:512 | 256 |
| minimum_services / eskf15 | 18432 | Device:2560/INS:3072/Estimator:4096/Flight:4096/Telemetry:4096/Idle:512 | 256 |

All nine final artifact inspections and `stack-report` runs passed, exit0. Initially, the three reduced-service Make artifact checks failed because the checker unconditionally required `s_serial_stack` while maintenance was disabled; capacities and static stack checks passed. Commit `976caa7` reads exactly one literal0/1 definition for each logging/maintenance/telemetry switch, requires the enabled task stack in CCM and rejects allocation of disabled task stacks. Missing/ambiguous switch definitions fail closed. Ten tests against copied **real ARM ELF/MAP/BIN/HEX** fixtures passed in14.06s: enabled/disabled matches, opposite maintenance flags, missing, duplicate and illegal definitions. `.work/night_artifact_protocols.log` retains the run; the test requires explicit real artifact inputs and otherwise skips, never fabricates PASS.

Final inspections used the new source checker through PowerShell on separate workspace copies of the nine real artifact sets. `final_artifact_checks.json` records commands, checker HEAD/SHA and original ELF before/after hashes; all hashes stayed unchanged. They are P3 CLI inspections, not new executions of P2's GUI buttons. An attempted normal regeneration correctly preserved the first resource project's existing Tools payload, so no existing payload checker was forcibly overwritten. The failed comparison/three original Make failures remain logged. Existing P1 outputs retain earlier source/checker snapshots: adopting these repairs requires a fresh version project or explicit reviewed payload update, not silently overwriting user-owned source.

Stack evidence is the repository's conservative `.su` plus linked-disassembly call-chain budget, including256 bytes of M4F task context and required256-byte minimum margin; unknown indirect/dynamic/recursive paths fail closed. It is not a measured stack high-water mark. The separate MSP reservation is not a measured nested-ISR maximum. Capture ESKF's narrow CCM margin is1240 bytes; future queues, tasks or plugin additions must repeat domain-specific linking, rather than assuming total RAM spare is usable CCM.

Against Pure INS in the strict equal-services build, KF6 adds28592 Flash,19320 main SRAM and11264 CCM bytes; ESKF adds16712 Flash,17912 main SRAM and20280 CCM bytes. These are whole linked-profile deltas, including selected backends, history/replay and retained common services. They are not intrinsic mathematical lower bounds. Example linked objects include KF6 `s_replay_storage`10368 and `s_replay`19304 bytes; ESKF `s_body_history`12288 and `s_history`16992 bytes. Placement and all other symbols are available in JSON/NM and MAP, so these examples must not be summed as the complete algorithm allocation.

## Frequency and MCU boundaries

No STM32 execution, DWT cycle measurement, interrupt-load measurement or hardware stack snapshot was performed. The existing `tests/joint_rework_20260927/evidence_final/timing/evidence.json` explicitly says target execution NOT RUN; its O2/Og object sizes and host checks do not supply WCET. `TimingEvidence_Assess` returns MEASUREMENT_PENDING for absent work bounds rather than substituting zero. Therefore no numeric minimum CPU frequency is established for any mode, including168MHz.

For a measured bounded task cycle cost `N_i`, bounded frequency-independent wait `W_i`, period `T_i` and deadline `D_i`, use `C_i(f)=N_i/f+W_i` only under verified clock/cache/Flash/FPU conditions. Necessary per-task condition is `C_i(f)<=D_i`; utilization alone is not sufficient. Verify the actual priority response-time recurrence `R_i=C_i+B_i+sum(ceil(R_i/T_j)*C_j)+ISR interference` against deadlines and burst/queue bounds. Include logging/SD stalls, GNSS bursts, delayed replay, worst covariance/measurement branches, interrupt nesting and FPU context. Frequency changes may change memory/peripheral waits and must be measured again. Host wall time and static code size are not STM32 WCET.

The repository has exact MCU descriptions for F407VET6 and F103C8T6. Current Flight projects actually linked only the F407 target. Its M4F and memory domains match these hard-float profiles; ST specifies up to168MHz and192KiB system RAM including64KiB CCM. [ST F407 datasheet, DS8626 Rev12](https://www.st.com/resource/en/datasheet/stm32f407ve.pdf). The F103 descriptor is used for Ground; ST describes M3, up to72MHz,64KiB Flash for C8 and20KiB RAM. [ST F103 datasheet, DS5319](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf). Every measured reduced Flight profile exceeds C8 Flash/RAM; current F407 hard-float/linker files also cannot be transplanted to F103. ESKF's declared qualified timing profile is `cortex_m4f_hardfp`; that metadata is not new board timing evidence. Other STM32 part numbers are unbuilt candidates requiring exact provider, pin/DMA/memory-domain validation and timing measurements. No chip beyond the tested build target is promised to run.

## Bounded navigation review and repair

| Boundary read | Finding and evidence limit |
|---|---|
| Units and frames | Machine contract is ENU, Hamilton wxyz body-to-navigation, right-local/body attitude error; gravity Down and specific force positive Up at rest. JY driver converts configured gyro degrees/s by PI/180 and acceleration range by local gravity; adapters pass rad/s and m/s2. No new frame conversion or filter tuning was introduced. |
| IMU time and cadence | Frontend uses actual timestamp endpoints/trapezoidal samples;200Hz/aggregation2 gives100Hz increments. `Eskf_BodyValidate` requires finite0<dt<=.02, end>start, start matching committed timestamp, source/generation equality, finite half samples and duration agreement within2us. The suspected missing ESKF duration check already exists; it was not patched. |
| Measurement freshness | Reviewed native epoch/sequence, source/generation, physical quality and mapped measurement time; received/measurement/evaluation/output times remain distinct. The270ms configured receiver-delay default remains an explicit estimate, not a measured M9N latency. Closure evidence rejects duplicate/late epochs and expires; successful gain commit, not mere receipt/replay, controls freshness. |
| Initialization, rejection and matrices | ESKF nominal16/error15, at most2 measurement rows per group, static caller workspace; finite/unit quaternion and positive covariance initialization, Joseph update and SO3 right reset, covariance check without modifying P to pass. Candidate state/P commit only on success, NIS/numeric/replay failures explicit. KF6 recovery and Pure INS states remain distinct; replay/history capacities and vector2–6 contract unchanged. |
| Proven numeric defect | Valid accel/gyro flags allowed NaN/Inf through INS sample preparation; finite extreme samples could overflow increments; invalid gravity or overflowed navigation candidates could be committed as valid. Source-level host fault injection reproduced all7 cases failing for each aggregation1/2 before repair. |
| Minimal repair | `ins_mechanization.c` now checks finite accel/gyro before storing the sample, all published body increment forms before increment commit, and positive finite gravity plus finite candidate velocity/position before navigation commit. Overflow increments reset sample history count and return INVALID with INVALID_SAMPLE health. Existing orientation-independent frontend behavior, equations, units, filter settings and safety contracts are retained. |

`tests/fixtures/inertial_numeric_rejection.c` and `tests/test_inertial_numeric_rejection.py` compile the actual generated C with real host GCC `-O2 -Wall -Wextra -Werror`, fault-trigger the seven cases and require invalid output plus preserved navigation state/counter on rejected navigation commit. Pre-fix `.work/night_numeric_before.log` exit1: two parametrized failures, each seven failures. After fix `.work/night_numeric_after.log` exit0: **15 tests PASS in81.56s**, covering numeric rejection, nominal frontend, rate planning, ESKF body cadence, navigation configuration and timing evidence. Native STM32 execution, walking truth data and filter accuracy remain untested. This is a bounded review of key paths, not proof of every numeric expression or all possible finite extreme inputs.

The human navigation contract's stale identity paragraph was corrected to current Core/platform0.1.0, project format14 and required FLP0.1.0, using current constants/plugin metadata. Decoder/project semantics remain1.2; old recordings/revisions remain immutable. No machine identity or saved project migration policy changed.

## Power of Ten risk groups

The final newly generated KF6 capture project ran real `power10-check`: checker failure/Make exit2, **194 Rule5 findings remain**, no new Rule4 or other failure. Ground's unchanged13 findings retain the separately executed P2 evidence. No assertion padding or whitelist was added. `.work/night_navigation_resources/final_kf6_power10.log`, `.exit.txt` and `pot_risk_groups.json` preserve classification/function lists. Group counts below classify the194 findings; they are not individual audits of all functions.

| Group | Count | Most useful contracts and fault tests |
|---|---:|---|
| APP/System orchestration, timing, health/lifecycle |96| Commit sequence/fingerprint agreement; READY distinct from ACK; fail-closed output eligibility; legal startup/recovery transitions; snapshot atomicity. Inject stale/changed generation, timeout, failed config verification and unavailable measurements. |
| Devices/Platform driver, DMA, queue and hardware state |77| Instance range before indexing, queue head/tail/count capacities, payload length, DMA ownership/lifetime, IRQ/TX/RX legal state combinations. Inject full queues, invalid indices/lengths, CRC errors, DMA timeout and late completion using hardware-safe fixtures. |
| Modules telemetry publication/control |21| Encoded packet length<=MTU, bounded status/ACK queue, transaction identity and response eligibility; successful ACK must not create readiness. Inject duplicate/out-of-order replies, queue saturation, malformed payload and stale snapshots. |
| Ground Lora state/queues |13 separate| The P2 report reviews all13 individually. Specify occupancy and TX/RX/control transaction invariants before asserting them; hardware observations/errors must remain representable failure states. |

The INS finite checks are meaningful input/commit guards with real fault-trigger tests. They do not make Rule5 green or establish that all callers contain two runtime assertions. Remaining coverage debt and low-level SX1281 public-index precondition review remain open.

## Independent native Windows lifecycle regression

Three separate Python processes used the actual Windows Qt platform, new settings paths and fresh `.resource/20261001/gui_lifecycle_1..3` roots. QtTest operated actual widgets; no desktop mouse-runtime or fake worker was substituted. Each waited for tool detection, canceled/created a project, checked KF6 and three directories, selected Flight/Ground existing hardware, configured AIR/PC resources, saved, switched all eight pages, waited for real Flight then Ground generation to finish, preserved a user-owned sentinel, reopened and closed with worker=None/window invisible.

| Process | Exit | Seconds | Result |
|---|---:|---:|---|
| PID12884 cycle1 |0|54.90|PASS|
| PID28788 cycle2 |0|53.57|PASS|
| PID22136 cycle3 |0|42.39|PASS|

`.work/night_lifecycle/processes.json` records exact commands/PIDs/timestamps; each cycle has raw log, result JSON and screenshots. A cycle3 hardware-page screenshot was visually inspected. Own-process SetErrorMode/faulthandler suppress interactive error boxes; no system setting changed. Earlier access violation was **not reproduced**, but remains **unexplained, not root-cause resolved**. These cycles cover normal generation-completion close; prior P1 evidence covers busy-close/cancel, popup/vector transitions. None is flight or hardware acceptance.

## Handoff

Nine fresh links, nine artifact checks, nine static stack checks, fifteen relevant pytest cases and three independent native process cycles PASS. PoT194/13 FAIL is retained. No numeric minimum main frequency, target WCET, live stack margin, walking-navigation accuracy or flight qualification is claimed. ESKF capture CCM margin1240 bytes and the missing-storage validation/generation diagnostic gap are concrete remaining concerns. P1 hardware saving was dialog-open/cancel, not full plugin export; field logs, real serial/radio and board execution remain untested as documented in earlier reports.

Latest credible quota is user-reported82% at17:20UTC; dynamic quota remains unknown. Model evidence is creation request gpt-6.1-sol/high, not a UI reading. No repeated quota probe or parallel model task occurred. Python removal/shutdown were not attempted. After final checks all own test/build subprocesses have exited; unrelated apps, remote access and website Cloud task were left untouched. Complete local evidence and projects are preserved for the parent to summarize in the morning.
