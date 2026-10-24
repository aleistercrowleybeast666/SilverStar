# Maintenance 0.1 runtime diagnostics — 2026-10-13

This is a local development increment on the verified UART maintenance checkpoint
`e1c40c5b91935cb19ed39999038bff181ba6b60d`. Frozen v0.1.2, FINAL and UNDERLINE
projects/packages are not modified. USB callback expansion is deferred; no port,
probe, flash, reset, actuator, publication, push or tag operation was performed.

## Behavior and compatibility

The fourth GSHC page is **Runtime / Logs / 运行诊断 / 日志**. The firmware adds
`SYSTEM DIAG` capabilities and `SYSTEM DIAG <cursor>` read-only RAM pages while
retaining maintenance 0.0's command parameters, responses and error paths. Both
profiles remain selectable; new projects default to 0.1. The unchanged component
ID `silverstar.protocol.maintenance.serial_0_0` is a package identity containing
both profiles, not a claim that the wire version remains 0.0.

| Independent axis | Value |
| --- | --- |
| Product | 0.1.3 development |
| Maintenance | 0.1, backward compatible with 0.0 |
| Diagnostic schema | 1 |
| LOGFILE service | 1, separately negotiated |
| Recorded container | SSLOG 0.0 |
| Decoder package | 1.2, exact package and Descriptor still required |

The [shared contract](../../../contracts/maintenance_diagnostics_v1.json) bounds
the catalog to 16 entries and each ASCII response to 511 bytes excluding CRLF.
The current firmware has seven direct readers in five fixed groups:

| ID | Observed meaning / limit |
| --- | --- |
| task.lifecycle | Current lifecycle; never START authorization |
| task.preparation | Cached SystemHealth state, blocking reason and full masks |
| thread.logger | Successful complete sink-write count/time; not fsync/durability |
| thread.estimator | Existing prediction counter and state-data age; not task completion |
| sensor.ins_solution | Existing solution validity/data age; not physical sensor online proof |
| storage.tf | Existing storage RAM health, write attempts, syncs and errors |
| communication.console | UNKNOWN: useful-work completion not instrumented |

Stable ID/name/state/reason/source/age fields drive a generic grouped tree.
Unknown optional fields are ignored; incompatible critical schema/access/bounds
fail explicitly. Unknown states display UNKNOWN. Finite progress requires a valid
done/total pair; periodic tasks have no invented percentage. The only new work
instrumentation advances after a full successful Logger sink write, not after an
attempt or scheduler iteration. No arbitrary variable registry, watches, symbols,
addresses, callback registry, IDE or SWD operations are present.

One background serial owner performs all status/file exchanges. Diagnostic
enumeration advances one bounded page per idle scheduling step, with at least a
one-second interval between completed cycles. The firmware does not enforce a
client request rate. File jobs discard partial diagnostic scans, clear the display
with a paused message and suspend polling. Disconnect invalidates all observations.
Unknown MCU sample age remains unknown; host receive age and known work/data ages
continue aging and become stale after three seconds. Independent entries are not
one atomic whole-system snapshot. Byte limits and PC timeouts are not MCU WCET.

The top Refresh button is left of Ground COM and updates both selectors from one
enumeration, retaining independent selections. Baud candidates, custom positive
integer validation and 230400 defaults are shared; candidates do not gate custom
values. Ground COM, maintenance COM and optional SWD are independent roles. SWD is
explicitly unavailable, never a third assumed COM or a fabricated connection.

Old FINAL supports only its real SYSTEM INFO/STATUS/CAPABILITIES and LOG STATUS
responses. GSHC preserves these fields, labels unknown sample age and missing task
instrumentation, and disables unavailable file capabilities. Static FINAL USART3
PB10/PB11 at 230400 8N1 is prior source evidence, not flashed identity, wiring or
an observed connection. See the [baseline record](UART_MAINTENANCE_20261013.md).

## Source and safety review

Production changes are in the owning core payload and maintenance-profile metadata,
plus SCG profile defaults and GSHC. Separate generated validation project
`.work/dev013_maint01/project01` began as 623 files / 16.5 MB. Exact-hash inventory
checks govern validation-only refreshes; normal generation preserves user-owned
payloads. No workspace, virtual environment or Cube SDK copy was made. No cleanup
of old work or user inputs is authorized.

New Logger fields are private CPU-owned state. Publication and retrieval copy the
whole RAM snapshot in the existing critical section; no incoherent shared
64-bit timestamp is read directly. The getter handles null/unpublished snapshots.
Successful counters wrap as unsigned observations, not identity or rate guarantees.
New console readers use direct bounded selection with no dynamic allocation,
recursion, runtime callbacks, disk access or START side effects. Existing formatting
helpers bound writes to the supplied buffer; initializers/unknown/error branches
return explicit unavailability. The existing terminal-fault and ordinary storage
error behavior is unchanged. Host fault interception remains test-only.

The first diagnostic PoT run rejected a 62-line command-admission function. The
module-aware read-only classification was moved into its existing inspection helper,
leaving the flight admission boundary and all legacy branches intact. No function
was split to evade counting; no threshold, assertion-density credit or exception
was broadened. The earlier UART pre-fix START/window failure, normal cases and
fault cases remain in the baseline evidence, with their original scope and date.

Stack binding review `maintenance_diagnostics_20261013_v17` adds exactly six full
input identities, retaining v2-v16. Four are Logger/snapshot/console sources; the
two generated changes are only configuration/semantics identity bytes. The retained
`identity-review.diff` verifies that fact. None of the compiler dependency graphs
changed, and no new indirect-call exception or callback site was introduced.
Unknown-input rejection, source coverage, context reserve and minimum margins are
unchanged. Actual linked HAL/FreeRTOS/FatFs/libc/libm paths and controlled exceptions
remain represented by the existing stack report; no third-party violation is erased.

## Validation and retained evidence

Commands, environments, full logs (including failures), tool versions, exact dirty
source snapshot, generated configuration/inventories, ARM/analyzer ELF/map/stack
outputs and screenshots are retained in
`apps/SCG/docs/evidence/maintenance_0_1_20261013/evidence.zip` with SHA-256 manifest.
The task workspace is `.work/dev013_maint01`; SCG Qt preferences additionally use
the owned `apps/SCG/.work/dev013_maint01` path to obey application WorkspacePolicy.
No broad workspace-policy exception was added for tests.

| Run | Result |
| --- | --- |
| arm02 | Actual F407 ARM compile/link, exit 0 |
| analyzer02 | Actual ARM `-fanalyzer -c` and link in separate output, exit 0 |
| gates04 | Single emitted command: power10-check, architecture-check, artifact-check, stack-report; exit 0 |
| host05 | 80 executables, 4,446,532 checks, zero failures; 11 compile-pass, 18 expected compile failures, 8 not applicable; separate storage-integrity normal/fault modes also pass |
| gshc_tests04 | 74 passed, 12 subtests passed, mock ports only; CN/EN images and DPI probes |
| scg_tests08 | 93 passed, 4 conditional skips, exit 0; full applicable six-module invocation, 364.24 s |

The four architecture negative cases are conditional: three missing-scope cases
require a selected Console owner, and one present-unselected-source case requires
disabled maintenance. Exact skip reasons are retained; they are not reported as
executed passes. This is the named applicable suite, not the entire monorepo suite.

`compiled-reuse.json` verifies all **391 actual compilation inputs / 157 C sources**
match the successful ARM, analyzer and final gate records byte for byte. Later
edits were tests/docs only; the same binary is not attributed to different firmware.
Release ELF SHA-256:
`6df46dab0bf44394e1e980088960b3843add90c3481583412ec7695dbac12e62`.
FLASH 343184 bytes; main SRAM 101892 (508 below the 102400 project budget);
CCM 59176. Heap symbols: zero. Task stack margins in bytes: Device 416, INS 832,
Estimator 844, Flight 448, Logger 1280, Serial 1200, Telemetry 1944, Idle 256.

PoT reports 6447 text checks, 113 first-party C files, 2813 functions and 847
nonblocking assertion recommendations. Architecture reports 356 checks. Critical
contract review remains **NOT PROVEN**; whole-program stack acceptance remains
**NOT PROVEN** for MSP/main, ISR nesting and hardware margins. These tool passes
are neither original Power-of-Ten compliance, certification, WCET proof nor
hardware/flight qualification. F1/other STM32 targets were not compiled or tested
on hardware in this increment; USB expansion remains outside this acceptance.

Historical failures retained: gates01 function length; incomplete gates02 after
execution-channel loss (no completion/exit claim); gates03 sandbox strict-path
denial; SCG tests01 interrupted without Qt offscreen, tests02 four failures,
gui04 missing parent directory, tests05 one old profile-count expectation. The
new tests06 compatibility test initially omitted the renderer's graph argument;
its corrected call passes the independent contract07 run. Host04's one-record
write-fault injection was accepted into FatFs RAM and failed only on later sync:
the unchanged-success-counter assertion correctly rejected that test setup.
Host05 crosses the sector cache using 32 bounded queued events, proves an actual
append/write fault, unchanged completed count/time, maintenance FAILED and no
file-service authorization. Original normal and final-status-fault cases remain.
All failed logs are retained. The
transport-MTU test now mutates the actually selected cached variant view, preserving
the insufficient-MTU rejection. The quality-record test checks existing provenance
fields and their actual roundtrip values. The final suite is rerun as one invocation.

## Reviewable startup

From `D:\python_software\SilverStar` run:

```powershell
.venv\Scripts\python.exe apps\GSHC\main.py
```

Open the fourth **运行诊断 / 日志** page. This starts the application without
connecting hardware; port connection remains an explicit UI action. The source
checkout is the deliverable, not a rebuilt frozen executable. For offline review,
the evidence screenshots show both old FINAL-compatible fields and a simulated
0.1 catalog, including a previously unknown entry/state. They are clearly mock
QA, not evidence of a physical target connection or a flashed firmware update.


## 2026-10-17 本地维护源码合入

完整命令、字段、状态机、整行背压和软件/硬件证据边界见 [维护协议 0.1 完整实现说明](../../../apps/SCG/plugins/builtin/silverstar_protocol_maintenance_serial_0_0/docs/MAINTENANCE_PROTOCOL_0_1.md)。普通源码入口为仓库根的 `python apps/GSHC/main.py`。本次未发布、未再次连接硬件；原 R04 实板结论只覆盖原精确镜像，不能移用于含当前导航/USB 源码的新生成固件。
