# Explicit research controller task: contract and evidence scope

This work adds an opt-in, singleton PID or LQR research task to the existing
FlightTask; it adds no RTOS task, callback registry or electrical actuator driver.
The normal SCG parameter-import dialog offers an initially unchecked research
task option. Mathematical-core-only imports retain their previous period rules.
Only the explicit task contract requires a 10 ms discrete period.

The mission declaration owns one controller instance and its stage interval.
The generated backend statically names the selected numerical core. Start runs
once, stage transitions preserve its private state, and stop/failure is terminal
for that mission. A newly read mission window and lifecycle are checked together
under the publication critical section. Invalid input, timing failure and a lost
source revoke output and enter the existing ordinary lifecycle FAULT path.
Corrupt internal state enters the existing assertion fail-stop path; fault tests
intercept the actual terminal trap only on Host, never in target firmware.

Inputs are an ENU Hamilton `wxyz` body-to-navigation quaternion and corrected
body-Y gyro in rad/s. The scalar angle is `atan2(body+Z ENU x, body+Z ENU z)` in
radians, with zero reference. The supported research domain is explicitly
planar: |pitch| <= 0.35 rad, |qx| and |qz| <= 0.01, |rate| <= 20 rad/s. Numerical
finiteness, quaternion norm, timestamp age, timestamp/sequence progression,
input skew and calibration/source/epoch identity are checked. This is not a
general three-axis attitude controller or a demonstrated flight envelope.

Provenance is copied from admitted inertial samples through the actual INS
aggregation and prediction queue into the estimator's committed attitude.
The token starts at the actual corrected alignment-window inputs and is cleared
only by an alignment reset. START can invalidate it but cannot reconstruct it
from the current selector. Independent magnetic or hardware-quaternion history
is not represented by this token; such an initial attitude remains unavailable
to this research controller, without claiming that its normal navigation
algorithm is invalid.
The current selector is never used to invent historical estimator provenance.
The selector is locked by the existing START owner for a mission. Unknown input,
source/generation/epoch discontinuity, prediction-queue refusal or invalid
prediction revokes the proof. Already queued older work cannot restore a
latched invalid proof. Estimator health adds bit 11 (input provenance invalid)
to its existing uint32 field; explicit wire codecs and existing bit positions
remain unchanged. This is separate from SS-TM's independently defined health
mapping. Historical decoder bytes are not rewritten.

The output is a bounded, latest-value memory snapshot named
`requested_body_y_torque_nm`: a requested body-Y torque in N*m. The task explicitly
maps each abstract mathematical-core output unit to 1 N*m and limits its research
domain to +/-1 N*m (the selected output limit may be lower). This matches the
TreeDiagram body-Y torque input; it changes neither generic core ABI nor its
parameter units. Old core-only bundles, including 20 ms designs, remain legal;
only explicit task attachment requires 10 ms. It expires after 12 ms and inputs
after 20 ms, with <=10 ms input
skew. Each execution retains the 10 ms schedule anchor and permits <=2 ms
lateness, including computation before publication; it never performs catch-up
iterations. A getter validates a local copy before writing the caller, and
rechecks current source, lifecycle and mission window in one critical section.
Neither READY nor a successful simulation makes this electrically deployable.
Hardware WCET, ISR timing, stack margin in operation, actuator drivers, physical
source qualification and flight validation remain separate gates.

The new raw-sample/provenance values increase queue storage without reducing
queue depths or increasing budgets. Five existing CPU-only INS objects move
to the existing CPU_FAST placement; none is a DMA buffer or exports a DMA
address. Actual default F407, installation F407 and H743 linked memory and
stack results must be recorded by the final build owner; this document does not
substitute estimates for those results.

## Evidence epochs

- `pre-adapter-pytest.log`: the two declarations fail before implementation.
- `getter-pre-v1.log`: four actual PID/LQR failures demonstrate corrupt-snapshot
  partial publication and an asynchronous lifecycle-fault read interleave.
- `task-v4.log`: historical 49-test result, before the getter/publication fixes;
  not final acceptance evidence.
- `producer-v1.log`: retained GCC 16.1 `-fanalyzer`/LTO failure. The trace allowed
  a null-helper early return despite the validated nonnull caller and reported
  an uninitialized alignment flag. The owner now initializes that snapshot
  to explicit unready defaults; no diagnostic was disabled.

Generated projects under the task-specific `.work/.../control` directory are
validation candidates, not user projects.

### Final controller unit epoch (v7b)

`task-v7b.log` records one complete execution: **62 passed in 206.92 s**, exit 0.
It freshly generates both PID and LQR candidates and compiles actual generated
backend, mission engine, calibration math, numerical core and runtime with GCC
`-std=c11 -O2 -Wall -Wextra -Werror -pedantic -fanalyzer`. Sensor/estimator ports
are injected in this task harness; actual producer history has its separate
INS/KF6 queue regression below. The test covers normal execution, all named
fault/interleave cases, explicit declarations, legacy core-only 20 ms PID/LQR
compatibility, and output units/numerics. For 0.01 rad pitch and calibrated
0.002 rad/s body-Y rate, the imported fixtures produce -0.0325199999 N*m (PID)
and -0.0320941508 N*m (LQR).

Command: `D:/python_software/TreeDiagram/.venv/Scripts/python.exe -m pytest
apps/SCG/tests/test_control_research.py -q
--basetemp=.work/0.1.3-software-completion-20261101/control/pytest-v7b`, with
`PYTHONPATH=apps/SCG/src` and `D:/msys64/ucrt64/bin` on PATH. Exact compiler
commands, 36 owning source hashes, compiled sources, binary hashes and actual
torque output are in `task-v7b-receipt.json`; `capture_v7.py` captures that receipt.

`units-pre-v1.log` retains two pre-fix missing-output-contract failures.
`task-v7.log` retains 60 passes and two test-only Windows GBK decoding failures;
the latter were repaired by explicit UTF-8 reads and are not hidden or counted
as a successful full run. No mathematical core C/H was changed by the unit fix.

`host-v6.log` is the earlier fully executed selected emitted-Host command:
`Tests/Host/run_tests.ps1 -HostCompiler D:/msys64/ucrt64/bin/gcc.exe
-Only @('lifecycle_logging','control_provenance','control_research')` on the
fresh v6 PID candidate. It passed 3 executables, 1146 counted checks and the
runner's mandatory storage tail, exit 0. Its seven actual INS/KF6 producer cases
include full/not-ready queue boundaries and initial-alignment source mismatch.
It is a selected historical pre-unit epoch, not a full default/installation
Host pass. Final firmware-wide ARM, resource/stack and complete Host evidence
is coordinated separately; this report does not substitute selected passes
for those full runs.

`boundary-fault-v2` preserves the same three actual stop/schedule/alignment
harness expectations before and after the fixes (3 failures -> 3 passes),
with exact isolated source bytes, compiler commands and receipts.
`queue-boundary-v2` preserves actual full/not-ready admission refusal before
and after the INS fix (2 failures -> 2 passes). The v1 runner/fixture setup
failures remain retained and are not accepted regression evidence.

## Reviewed critical boundaries

| Boundary | Safety contract and executed test scope |
| --- | --- |
| Input read | Real estimator publication and corrected gyro; source/epoch/calibration agreement, valid/health bits, finite values, age and skew. Unavailable external input retains ordinary error handling. |
| Scheduled step | One instance; terminal stop/failure; no catch-up; increasing input sequence/time; exact 10 ms schedule with explicit 2 ms lateness and post-computation deadline check. |
| Publish | Numerical result bounded and finite; one critical section checks lifecycle/window/current provenance, publishes values, and advances the 64-bit schedule. Sequence exhaustion revokes READY before the real assertion. |
| Stop | Capture and clear backend-started flag, update terminal state and revoke output together under the lock; call and check numerical Stop afterwards. A concurrent getter sees a coherent terminal state. |
| Getter | Validate a local copy before writing caller memory; one lock covers lifecycle, window, source and age. Ordinary unavailable returns zero command/READY. Corruption keeps caller sentinel intact and records the actual terminal assertion. |
| INS producer | Copy the provenance of corrected admitted samples, including the initial alignment window. Both full and not-ready queue refusals latch input rejection. No queue depth is reduced. |
| Estimator producer | Only successful numerical prediction carries the admitted increment's history. A latched rejection clears published proof immediately; old queued work cannot restore it. A terminal numerical fault clears proof even on its direct publication path. |

These are manual boundary checks backed by the named Host cases. They are not a
claim that assertion-density text scanning proves useful assertions, complete
whole-firmware critical contracts, MCU timing or hardware safety.

## Complete Host integration: ABI fixture correction and fresh C epoch

The first complete default B Host invocation failed at the owning
`Tests/Host/test_interfaces.c` compile-time assertion. Its old 40-byte base
increment expectation did not include the newly admitted 16-byte provenance;
the ESKF and augmented offsets likewise still described the historical layout.
`full-host-b-default.log`, its receipt and exit file preserve this real failure.
The original wrapper also reported a newly created Python bytecode cache as
source drift. Neither result is described as a complete Host pass.

The correction changes only this owning Host fixture, keeps exact `==` size and
offset assertions, and adds full-width provenance generation/epoch/source checks
and a zero-initialized-invalid runtime check. No production C, header, queue
capacity or memory budget changes. `layout-probe-arm.json` preserves actual
Cortex-M4 ARM GCC 14.3.1 compilation and emitted assembly for the base, ESKF and
augmented selections: provenance size 16, validity offset 12, increment
provenance offset 40; increment sizes 56, 112 and 120 respectively. ESKF gyro,
acceleration and quality offsets are 56, 80 and 104; augmented interval offset
is 112. These measured values are used as exact assertions, not weakened bounds.

`generate_full_host_c.py` creates new default and installation projects through
the normal service/catalog/model/generation path. The captured source snapshot
is commit `e7c42b7c4971fddb02c6d5c60864b50dffaa3f1a` plus the exact fixture diff,
with all owning source hashes unchanged across generation. The historical v7b
36-file receipt remains intact; `OWNED_FILES.txt` now additionally includes this
Host fixture. `full-host-c-vs-b.json` proves the target graphs and all declared
production sources, included headers, forced includes, linker scripts and Make
inputs exactly equal the stack v5 B projects: 481 files for default and 502 for
installation. This establishes which previously compiled ARM inputs are
identical; it does not turn a Host run into a new ARM execution.

`run_full_host_c.py` invokes each emitted `Tests/Host/run_tests.ps1` without an
`-Only` filter and captures complete output. `PYTHONDONTWRITEBYTECODE=1` prevents
new Python caches; source snapshots exclude only the build directory and explicit
bytecode cache artifacts. Both generated-source stability and the relevant
owning controller/plugin/contract hashes are checked. Later unrelated USB Python
owner changes are listed separately and never attributed to this immutable
generated Host epoch.

Both full C commands completed successfully. Default: **77 executables,
5,509,758 checks, 0 failures, 511.72 s**. Installation: **78 executables,
5,509,951 checks, 0 failures, 630.46 s**. Each command records 12 successful
compile-contract cases, 17 expected compile-failure cases and 20 main Host
not-applicable observations. Both mandatory storage tails completed all four
steps. Each full log contains zero compiler warning lines; generated sources
and relevant owning controller/plugin/contracts changed lists remain empty.
These default/installation models have the controller disabled; enabled PID/LQR
evidence remains the separate complete 62-test v7b execution, not these counts.

`full-host-c-summary.json` preserves separate results, all N/A reasons, tool
versions, complete-log hashes and produced Host executable hashes. The storage
sub-runner additionally reports 63 N/A lines per configuration, representing
nine unsupported record positive cases repeated seven times; rejection paths
are exercised. Its counts are not part of the PowerShell main Host counter.
The first audit script incorrectly compared all 83 N/A lines to that main
counter of 20 and failed; `full-host-c-summary.log` and
`capture_full_host_c_v1.py` retain this audit failure. The corrected scope-aware
summary (`full-host-c-summary-v2.log`, exit 0) retains every line and leaves
both actual full runs, test expectations and source bytes unchanged.
