<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

# FCCG 0.0.12 runtime safety

Package-local implementation note for the FCCG-owned overlay. Current platform
rules live in `docs/platform/details/RUNTIME_SAFETY.md` in the FCCG workspace;
cross-component behavior lives in `docs/AIR_CALIBRATION_CONTRACT.md`.
Actual acceptance snapshots belong to the workspace root `VALIDATION.md`.

This document and `check_task_stacks.py` are FCCG-owned overlays. The importer also
registers the changed Core C/H, Host fixtures and OS hook as FCCG-owned source of
truth. Importing the read-only reference must preserve these repairs. Current
production validation is limited to the STM32F407VET6 / SS0.5 composition.

## Production initialization and indicator

The old `AppTasks_Init()` omitted `SystemIndicator_Init()`. Indicator processing
therefore returned before the GPIO service could write. Production now initializes
Calibration, Alignment and Indicator before creating any task. The Host startup
test calls the real App init and real indicator/GPIO service; it does not add a
test-side Indicator Init. SS0.5 remains GPIO logical ID 6, `IMU_CAL_LED` / PA1,
active-low ON. Neither the Board mapping nor its polarity changes.

## Calibration and command gates

| Procedures in project | Procedure mask | AIR calibration_mode_mask |
| --- | ---: | ---: |
| empty | 0x00 | 0x01 |
| OneFace | 0x02 | 0x03 |
| SixFace | 0x04 | 0x05 |
| OneFace + SixFace | 0x06 | 0x07 |

Bit 0 always advertises NONE/identity. Bits 1 and 2 advertise the compiled
OneFace/SixFace procedures. The header rejects all other procedure bits at compile
time, including bit 0 in the procedure mask. `SystemCalibration_Start()` rejects
unsupported procedures with `SYSTEM_DEVICE_UNSUPPORTED` before source selection
or calibration/alignment invalidation. AIR and Serial retain their existing result
mapping, tokens and ACK framing. Invalid parameters and lifecycle states remain
errors. This is a build gate at the shared C entry, not a GUI-only restriction.

For an empty selection, `SystemCalibration_Init()` establishes NONE, READY and
identity correction directly: zero biases, unit scales and no sampled faces. It
needs neither an incoming command nor a fresh IMU during pre-scheduler startup.
Calling CAL_START from the old App init was premature: Alignment was not yet
initialized, and the source selector could also lack fresh data. CAL_RESET now
restores identity READY for this build and advances the snapshot sequence, so
FlightTask records the effective Required `CALIBRATION_RESULT` again. The real
sampling procedures still lock their physical IMU before collection; ALIGN_START
selects and locks before alignment. There is no in-flight IMU switch.

## Alignment and task ownership

ALIGN_START validates lifecycle, calibration readiness, build/source capability,
the source lock and action availability, initializes the runtime and returns the
existing ACK result. It no longer calls the full `SystemAlignment_Process()`.
FlightTask performs that operation on its existing periodic path. Acceptance means
the operation started, not that alignment has completed. Invalid configurations
are rejected before ACK OK. CAL_START/CAL_FACE/CAL_RESET retain only bounded
validation/reset work; sampling remains in the IMU path, and the calibration solve
remains in FlightTask. The shared estimator-origin reset checks availability
atomically and returns BUSY rather than delaying a communication task.

## Task stacks and fault diagnosis

| Task | Configured words | Configured bytes |
| --- | ---: | ---: |
| Device | 512 | 2048 |
| INS | 768 | 3072 |
| Estimator | 1024 | 4096 |
| Flight | 1024 | 4096 |
| Logger | 768 | 3072 |
| Serial | 1536 | 6144 |
| Telemetry | 1024 | 4096 |
| Idle | 128 | 512 |

Generated Make builds emit GCC `.su` files beside objects under
`build/FCCG/<target>/<configuration>/`. Run `make CONFIG=Release stack-report` and
`make CONFIG=Debug stack-report` (use `mingw32-make` on Windows). The report script
uses the matching compiler tools, `.su` frames, linked ELF disassembly and static
stack-symbol sizes. Every C source in the resolved generated graph must have
a matching .su file; missing reports fail instead of using assembly fallback.
It conservatively adds direct and tail-call frames; assembly
library frames without `.su` use constant push/SP-decrement totals. It closes the
single verified FatFs SD driver callbacks and rejects unresolved indirect calls,
unbounded frames and recursion in task call paths. Every enabled application task
and the RTOS Idle task is covered. A 256-byte Cortex-M4F exception/FPU context
reserve is included, followed by a required 256-byte margin. Nested interrupt
handler work uses the separate MSP stack and still needs hardware qualification.

`stack-budget.json` records the ELF hash, compiler, per-task path, configured
bytes, worst-known estimate and margin. It also checks the production indicator
init closure, deferred ALIGN_START and FlightTask ownership. Root `VALIDATION.md`
records measured build evidence and Release/Debug budgets. A static budget is not
a measured runtime high-water mark or a proof for arbitrary future plugins.

The static fault record retains fault type, task handle, original task-name
address, stable task ID/name, lifecycle state and the last normal stack snapshot's
high-water mark with a validity flag. The overflow hook never dereferences an
untrusted task-name pointer or scans a corrupted TCB. Idle is identified separately;
unknown tasks and unavailable cached HWM are explicitly marked. HWM is cached,
not a fresh measurement at the overflow instant. Stack overflow detection remains
level 2; assertions and HardFault remain fail-stop. No heap or diagnostic I/O is
added to the hook.

<!-- imported-summary -->
FCCG initializes the System Indicator before task creation; SS0.5 retains
logical GPIO 6 (`IMU_CAL_LED`/PA1), active-low ON. Calibration capability is
build-derived: empty/OneFace/SixFace/both advertise `0x01/0x03/0x05/0x07`.
`SystemCalibration_Start()` rejects unsupported procedures before invalidating
state. Empty builds initialize and reset to NONE identity READY, retaining the
Required effective `CALIBRATION_RESULT` snapshot.

ALIGN_START retains immediate parameter/state/capability checks and existing ACK
mapping; the full Alignment Process runs periodically in FlightTask. Calibration
solve work also stays in FlightTask, and origin reset returns BUSY without waiting
in Telemetry/Serial. Task stacks are checked with real Release/Debug `.su` and ELF
call graphs using `make CONFIG=Release stack-report` and `make CONFIG=Debug
stack-report`; the JSON report records configured bytes, estimates and margins.
Overflow diagnostics retain stable task identity, state and valid cached HWM with
no heap/I/O or unsafe TCB/name traversal; fail-stop protections remain enabled.

AIR M0, Maintenance 0.0, SSLOG 0.0 and `.ssdecoder` 1.1 retain their versions and
wire/Record layouts. Continuous SS0.5 testing is still required for boot/blink
polarity, repeated AIR/Serial calibration/alignment/reset commands, all task HWMs,
MSP/interrupt nesting, source locks and effective calibration log snapshots.
