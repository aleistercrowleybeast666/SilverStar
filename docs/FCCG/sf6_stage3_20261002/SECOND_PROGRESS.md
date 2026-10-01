# SF6 second software checkpoint, 2026-10-02 UTC

Read `FULL_IMPLEMENTATION_REVIEW.md` for the complete, unabridged header,
context, numerical kernel and backend implementation, with source-byte SHA256.
This is review input and an intermediate software checkpoint. It is not a
completed safety acceptance or a frozen bench candidate.

The four-algorithm v6 matrix ran all 24 commands on freshly generated copies of
the actual TEST_4 configuration. ARM artifact/link, architecture, emitted
Power-of-Ten checker, real ARM `-fanalyzer` compilation and memory/stack-report
commands passed for PureINS, KF6, ESKF15 and SF6. PureINS/KF6/ESKF15 Host suites
passed. SF6 Host failed compiling the newly added backend fixture because its
barometer interface header was missing. The owning fixture is now fixed, and
its strict native actual-backend compile/run passed; v6 remains a failed matrix,
not a full-suite pass. Current source changes after generation need a fresh v7
matrix. Power-of-Ten critical-contract acceptance remains NOT PROVEN.

FCCG `test_sf6`, `test_algorithm_parameters` and `test_uart_async_host`: 43 passed.
This includes six gain boundaries, legacy parameter retention, declared-board
GUI edit/save/reopen, strict native kernel normal cases and four terminal fault
cases (capacity, current state, gain, historical state). Existing GUI test page
expectations were updated to the seven-page Ground layout already present on
this branch; no production layout or safety expectations were weakened.

Actual SF6/INS/time/queue/LoggerBus/codec backend fixture: the initial focused
run passed 20,902 checks; the v1 actual LoggerTask export passed 22,013 checks.
These fixtures exercise asynchronous GNSS/barometer samples, packet sequence
wrap, duplicates, dropout, bad/future native times, fallback delay, nonfinite
sensor data, reset, CRC corruption and unavailable statistical fields. These
are Host data, never measurements of MCU rates or hardware recovery.

The v1 export omitted the recorded mission-start/IMU calibration boundary and
was correctly rejected by FLP (`calibration_selection_boundary_missing`). A
new v2 export includes the canonical mission-start event through actual
LoggerBus/LoggerTask; no production decoder fallback was added and v1 was
preserved. The v2 export passed 22,019 native checks, but FLP still correctly
rejects it for `calibration_result_before_boundary_missing`: the fixture also
needs the actual preparation calibration record. FLP run: 42 passed, 1 failed.
Both complete failure logs are retained; no exact-decoder opening pass is claimed.

GSHC readiness/gui/START regression: 60 passed, 2 failed, 3 subtests passed.
The two failures are English light/dark 1000x700 preflight content fit:
content width 856 versus viewport 638. This is the ESKF15 GUI scenario;
its cause and baseline status are not established here. The SF6 change adds
only algorithm ID 3 to the readiness whitelist and preserves rejection of
unknown IDs, missing Capability, incomplete preparation and blocked reasons.
No full GSHC GUI pass is claimed.

Historical-state fault proof: compile both original 548b89f kernel and current
kernel with the same current test and actual assertion implementation using
`-std=c11 -Wall -Wextra -Werror -Wconversion -Wsign-conversion -pedantic -O2`.
Both normal runs exit 0. Corrupt a past ring state then request an update at
that boundary: original exit 3 (ordinary numeric error), current exit
3221225501 (terminal illegal-instruction assertion trap). Complete commands,
logs and hashes are archived. No setjmp/longjmp or target recovery is introduced.

Personal mathematical/interface review remains required: preceding-IMU-boundary
quantization, affine propagation rather than chronological measurement replay,
GNSS then barometer arrival scheduling, shared pU/gain_pu, finite internal health
ABI placeholders versus unavailable published statistics, and GNSS source-change
behavior. Defaults 0.2 are unoptimized/unbenchmarked. Hardware timeout, stack
proof, sustained MCU rate and flight qualification remain unproven.

Pending: fresh current-revision four-algorithm matrix, offscreen SF6 visual QA,
resource/linked-symbol comparison, and separate KF6/SF6 10-second Delay candidate
freeze. Existing action gates require actuator declarations; physically
disconnected bench actuators have not been verified. The clarification remains
open; this checkpoint does not claim firmware GPIO outputs are disabled.

TEST_4, prior frozen 50cc2d3 artifacts and UART frozen artifacts are untouched.
No serial, SWD/DAPLink, reset, flash, unlock or other hardware command was run.
Barometer cold backup, automatic memory layout and JY scanning are separate tasks.
