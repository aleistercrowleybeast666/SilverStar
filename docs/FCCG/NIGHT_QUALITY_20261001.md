# Native quality-check checkpoint, 2026-10-01

This follows the P0/P1 source checkpoint `b6c89123a4ac67c61d758fa78b79bfab240b8fa6`. Firmware inputs were unchanged in this phase; only acceptance documentation was edited. No push, packaging, hardware transport, flashing, START/unlock, power/network change or shutdown was performed.

## SCG name and actual entry

The current checkout contains FCCG, GSHC and FLP, not a separate SCG application. `apps/FCCG/pyproject.toml` registers `silverstar-fccg = silverstar_fccg.app.application:main`; the visible title is **SilverStar Flight & Ground Code Generator v0.1.0**. `ui/pages/build.py::_QUALITY_ACTIONS`, `build/runner.py::BuildAction.MakeTarget_Get`, and the generated Makefile consistently map the following five quality controls. No current first-party source/documentation entry named SCG was found (vendor RCC SSCGR register matches were excluded).

The user's SCG reference is therefore interpreted here as the current code-generator quality workflow, supported by the matching five controls. This is an interpretation, not proof of a historical SCG-to-FCCG rename. No legacy checkout was substituted.

The isolated native harness `.work/fccg_native_quality.py` displayed a real Windows Qt window, opened the accepted existing-route project using the real open handler, clicked the Build & Validation sidebar, waited for tool detection, expanded Advanced, and clicked **each quality button with QtTest**. Product workers, BuildRunner, Make and compiler/check scripts ran normally. A delegating completion observer recorded their actual BuildResult command/output/exit before calling the original GUI completion handler. No mock result or direct CLI substitute was used for these five actions. `artifact_check.png` visibly shows four green results and one red Power of Ten result.

## Five real GUI results

Project: `D:\stm32_project\SS_0_5_TEST_4\Flight_Controller`. All commands below were launched by the GUI's BuildRunner. Process-local PATH included Arm GNU14.3.Rel1 and MSYS2 UCRT64; tool detection found Arm GCC14.3.1, GNU Make4.4.1 and host GCC16.1.0 (MSYS2 Rev5), x86_64-w64-mingw32.

| GUI action / Make target | Exit | Seconds | Result |
|---|---:|---:|---|
| Host Tests / `host-tests` | 0 | 252.69 | PASS: 72 executables, 4,393,820 checks, 0 failures, 8 compile-pass cases, 16 expected compile rejections |
| Architecture Check / `architecture-check` | 0 | 12.40 | PASS: 328 checks, 0 failures |
| Power of Ten Check / `power10-check` | 2 | 12.32 | FAIL: checker exit1 becomes Make exit2; 194 meaningful-runtime-assertion coverage findings (Rule5), retained below |
| Static Analysis / `static-analysis` | 0 | 173.63 | PASS: real ARM compile/link with first-party `-fanalyzer` in separate `StaticAnalysis/Release` directory; vendor compiler policy differs as declared in Makefile |
| Firmware Artifact Check / `artifact-check` | 0 | 3.48 | PASS: ELF/MAP/HEX/BIN, section capacities and heap policy checked; no hardware/time/stack high-water measurement |

The common command prefix was `mingw32-make TARGET_PROFILE=SilverStar_F407 CONFIG=Release`; Host Tests additionally passed `HOST_CC=D:/msys64/ucrt64/bin/gcc.exe`. Full command arrays, return codes, durations and raw output files are in `.work/night_quality_native/result.json` and the five named logs. GUI summary logs and screenshots are beside them. Harness exit was0 and its final status `ALL_FIVE_EXECUTED` means execution completed, **not five PASS**.

Artifact report: FLASH312996/524288 bytes, main SRAM101280/131072, CCMRAM55432/65536, reserved heap0 and runtime heap symbols0. Remaining capacities are211292,29792,10104 bytes respectively. Link/static evidence does not establish WCET, minimum CPU frequency, live stack margin or suitability of an untested MCU.

Ground has only a Power of Ten Make target, not these five quality buttons. Its additional `mingw32-make -C D:/stm32_project/SS_0_5_TEST_4/Ground_Station power10-check` was executed **as an explicitly separate CLI check**, exit2, reporting13 Rule5 findings. `.work/night_ground_power10.log` and `.exit.txt` retain it. Neither Ground's five-check GUI coverage nor Ground runtime hardware behavior is claimed.

## Rule5 semantic review and remaining work

All194 Flight and13 Ground failure lines concern functions over20 lines with fewer than two counted meaningful runtime assertions. The checker rejects literal constant assertions and does not count object assertions on an address expression/static object as evidence of two state invariants. This behavior was retained. Null/alignment checks on known object addresses are not substitutes for queue, state, length or protocol invariants. No whitelist or assertion was added to reduce the count.

The following is a bounded source review, **not a completed review of all194 Flight functions** and not proof that a function is fault-free. Ground's13 reported functions were read individually along with their queue/control helpers:

| Ground finding | Reviewed behavior / remaining meaningful contract |
|---|---|
| `Lora_DiagRecordIrq` | Reads flags once, updates diagnostics under critical section; counter rollover and IRQ/state agreement are distinct from object-address validity. |
| `Lora_ClearRuntimeState` | Resets flags, queue indices/counts and control transaction; postconditions should describe empty queues and Idle state, rather than non-null static members. |
| `Lora_TryStartNextTx` | Returns when uninitialized/busy/queue empty; bounded queue helper supplies packet. Packet length, queue occupancy and TX/RX transition agreement are useful contracts. |
| `Lora_Init` | Checks bus errors and invalid chip/status values before declaring initialized/Ready; a useful success postcondition must distinguish verified hardware from a requested configuration. No hardware verification was executed. |
| `Lora_StartRx` | Requires initialization; sets continuous RX while retaining TX status if busy. TX/RX status compatibility needs a specified invariant, not a guessed assertion that TX is always idle. |
| `Lora_IrqProcess` | Distinguishes RX done plus CRC/header errors and TX-vs-RX timeout; valid combinations and completion ordering need explicit state contracts. |
| `Lora_RawIrqProcess` | Consumes pending GPIO IRQ or polls while TX busy, reads/clears IRQ and records it; latch/clear ordering and state eligibility are relevant. |
| `Lora_DiagnosticsRefresh` | Uses unsigned elapsed-time throttle and a critical-section snapshot; chip status and diagnostic flags are observations, so external fault values must be represented rather than asserted away. |
| `Lora_RxCompletionProcess` | Checks payload-read result, uses maximum buffer length and bounded queue insertion; payload length and queue invariants are the meaningful conditions. |
| `Lora_RxErrorProcess` | Consumes timeout/error flags and updates statistics/state; mutually consistent transitions need a documented contract. |
| `Lora_Process` | Returns before work if uninitialized, processes controls/IRQs/completions, then starts next TX or restores RX; call-order/state invariants matter. |
| `Lora_ForceRxContinuousDirect` | Requires initialization, clears flags under a lock and returns to RX; clearing queued TX vs. pending transaction policy must be explicitly reviewed before assertions are added. |
| `Lora_ControlProcess` | Validates Submitted state, enforces elapsed timeout, transitions through Active to Complete/Idle, publishes result under lock; transaction identity and legal state transition are meaningful. |

The SX1281 source uses `s_contexts[instance]` member macros. The assertion on `&s_stats` does not prove that `instance` is in range. Generated facade/resource callers currently supply configured instance indices; whether every public low-level entry should reject an invalid index remains an API-hardening follow-up requiring result/void/callback contracts and negative host tests. This checkpoint does not label that precondition as runtime-validated or add a guessed fail policy.

For Flight, `SystemHealth_OutputSafe`, `SystemHealth_Process`, `SystemStartup_Run`, `SystemStartup_WaitConfigTick`, `SystemStartup_ProcessDevices`, `SystemSensorStatus_SnapshotCapture`, `SystemFlightRecovery_Process`, plus the Ground bridge queue/input/process path were inspected. Existing useful protections include fail-closed health/output status checks, startup timeout and configuration-verification separation, critical sections around published snapshots, bounded descriptor insertion, atomic snapshot publication, and deployment/lifecycle gating. Remaining Rule5 findings are real coverage debt; a semantic guard in a helper does not automatically satisfy the caller's Rule5 count. The successful host tests exercise safety/startup/deployment/radio cases with fixtures, not real actuators or verified board timing. The remaining Flight findings are unreviewed in this checkpoint. No firmware patch was justified solely to force this gate green.

## P0 completion and fault boundaries

The companion NIGHT_ACCEPTANCE report now lists each P0 requirement explicitly. Additional native `.work/fccg_native_default_flow.py` passed a newly confirmed project followed directly by optional Stats-log and Tilt-deployment toggles; Navigation Configuration was never visited to enable INS. Alignment Result/Evidence were checked by default; removing the alignment strategy from a copied model returned the real unavailable-strategy reason. Required records remain locked under the protocol policy, not freely optional.

The same independent process opened an authored old official-core project, migrated/reopened it through the product handler, retained KF6, saved/opened a separate revision and verified the original descriptor hash unchanged. `.work/night_default_flow/result.json` and screenshots retain it. The separate targeted migration/alignment run passed14 tests in6.26s, exit0; `.work/night_p2_migration.log` records the exact test selection.

Early own harness attempts were rejected by the workspace-policy setting-path boundary, then by a premature click while tool detection was running. One exceptional script shutdown deleted signal objects while its detector still ran; that is a harness-lifetime failure with explicit traceback, not proof of the earlier Windows access-violation cause. The corrected harness waits for startup/page-triggered detection, yields the GIL, processes deferred deletion, and waits for its own worker before closing. The default-flow mouse attempt hit a checkbox's blank expanded area; focused Space-key input then exercised actual Qt toggling. These failed attempts and previously created directories were preserved, not overwritten as PASS.

The corrected quality/default-flow processes completed normal startup, real page switching, worker waiting and closing, without another access violation. **The earlier Windows access violation remains unexplained.** No system-wide error-reporting settings were changed; only own test processes used SetErrorMode/faulthandler. No current task command or hardware operation is left running at this checkpoint.

Latest credible quota remains82% at17:20UTC, user-reported; dynamic quota unknown. Creation-request evidence remains gpt-6.1-sol/high. No expensive parallel model task or repeated quota probe occurred. P3 resource/WCET estimation and Python3.7.5 removal remain unattempted; the nightly task is not declared complete.
