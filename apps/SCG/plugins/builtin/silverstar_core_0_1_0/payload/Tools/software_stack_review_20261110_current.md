# Current rotation fix and real PID input, 2026-11-10

This review supplements `software_stack_review_20261110.md` with four exact
`convergence-current-20261110-{h7,research}-{Release,Debug}` cases. It retains
every source/artifact/toolchain check, existing callback resolution rule,
256-byte task context and minimum margin, and complete main/MSP/exception
model. Earlier cases are historical inputs, not substitutes for these builds.
No runtime callback, memory budget, exception domain or stack margin is relaxed.

## Rotation source contract

The H743 input is the same immutable synchronized software CubeMX fixture,
ESKF20, BMI088 SYNC400 I2C and explicitly enabled magnetic rotation. Relative
to the immediately preceding reviewed H743 cases, the sole selected C/header
change is `Algorithm/Installation/MagRotation/Src/mag_rotation_runtime.c`.
The new private `Rotation_HistoryValidate` verifies the stored eight-element
history head and count before the DeviceTask's IMU observation, magnetic
observation or service can index state or publish a transition. DeviceTask is
the only writer of these fields. Maintenance only revokes qualification and
requests an owner reset; it does not race the history fields.

On corrupt bounds the helper first clears valid/qualified and requests reset
under the existing critical section, then enters the existing assertion
fail-stop with INDEX_RANGE or STATE_INVARIANT. It does not recover, overwrite
the corrupt history, call a logger, publish a successful estimate, or convert
bad sensor packets into assertion failures. The normal external-input error
paths remain unchanged. Two actual pre-fix Host executions returned without
the required trap. Post-fix normal/adoption/Stop/full-logger and both corrupt
state cases compile with the real GCC analyzer and pass. Only the terminal
trap is intercepted by the Host-only fault harness to inspect the real record.

Actual Release and Debug object review finds the new assertion call paths in
the existing DeviceTask closure, with no unresolved indirect or unbounded
frame. The maximum remains the existing sensor/fit path: Device spare is
372 B Release and 896 B Debug; MSP spare is 1364 B and 2900 B. H743 still uses
all 16 configurable nesting levels plus the fixed exceptions and extended FP
frames. This bound is static software evidence, not measured board high water.

## Actual applied research configuration

The research case is generated from this task's genuinely completed
Underline-to-TreeDiagram run, followed by SCG preview, explicit Apply and
normal generation. It uses the resulting `research.ssproject`; no substitute
default-disabled model is used. The selected singleton is PID with 10 ms
nominal period, Kp 1.75 and output limit 0.4, explicit research attachment and
`deployable=false`. Imported ordinary INS/KF6 scalars and decoder parameters
remain part of the sealed input closure, separately from this opt-in task.

The existing backend owns timing, input provenance, lifecycle and output.
It consumes the corrected body-Y gyro and ENU Hamilton body-to-navigation
quaternion, checks age/skew/progression/source/calibration and the restricted
planar domain, and publishes one bounded latest requested torque snapshot.
It does not own or invoke electrical actuator drivers. The mission declaration
still owns one stable instance and its interval. Stop/failure remains terminal
within the mission, and the 10 ms anchor is retained without catch-up work.
The reviewed input, scheduled step, publish, Stop, getter and producer contracts
are the existing `software_completion_20261101/control/CONTRACT_REVIEW.md`
boundaries; this input changes concrete imported values, not those operations.

Delivery must verify that the actual linked `AppTask_Flight` closure reaches
`ControlResearch_Process`, `ControlResearchBackend_Step` and `ControlPid_Step`;
mere symbol presence does not satisfy `ControlTask_Verify`. Both configurations
include their actual core/runtime/library and fault paths in the static budget.
The actual A Release/Debug closures satisfy these three calls. Flight spare
is 392 B / 1720 B, and MSP spare is 372 B in both. No unresolved indirect or
unbounded frame remains. Compared with the preceding current F407 case,
changes are seven generated parameter/mission/backend/metadata/decoder files
and four selected PID C/header files. Those four core files equal the prior
reviewed PID inputs byte-for-byte after the existing line-ending normalization.
No HAL, IRQ, RTOS or library source is changed by this applied configuration.

## Independent acceptance and limits

Candidate A uses ordinary service/model/plugin generation and actual ARM
Release/Debug compilation/linking. The old complete-input cases correctly
reject the changed inputs. This document and the exact A source, Make,
compiler/header/library, object, `.su`, `.d`, ELF and map closures are reviewed
before admission. A new normal B generation must independently rebuild and
match every sealed compiled artifact before its emitted strict stack gate can
pass. The checker never enrolls a candidate and no generated B source is patched
to satisfy a case. A diagnostic candidate is not delivery acceptance.

The full HAL object origins, initialization/parent links, NULL-only fields,
disabled callback registration, priority writers and fixed profile tables are
unchanged from their prior source cases; actual linked ABI loads, vectors and
runtime archive instructions are nevertheless resolved per new ELF. The new
rotation helper adds no pointer or registration. The PID backend uses fixed
named core calls, no new RTOS task or indirect dispatch.

The emitted Power of Ten/architecture gates and real static analyzer are
separate evidence. Their text success cannot certify every critical contract.
Physical synchronization and latency, MCU IRQ/preemption behavior, WCET,
DMA/cache, storage/power loss, real stack high water and flight qualification
remain hardware tasks. There is no original-Power-of-Ten or NASA-certification
claim, and the global manual review's NOT PROVEN result is not changed.
