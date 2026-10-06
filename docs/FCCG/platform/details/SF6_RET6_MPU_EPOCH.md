# Compact MPU recovery qualification

This software contract applies only when SCG composition enables compact mode
and selects exactly one MPU6050 IMU. Compact mode remains a configurable size
policy, not a brand restriction. Other IMUs and ordinary configurations retain
their prior sample layouts and admission behavior. Radio selection is separate:
the current compact E28 reference is retained; the later ultracompact NRF24L01+
reference must be integrated and measured independently.

The MPU driver retains its instance, axis mapping and source-selector lock.
Physical recovery retries have no total-attempt limit; each attempt remains
bounded with yielding/backoff. Physical communication recovery does not certify
fresh calibration, alignment, barometric origin or mission readiness.

An IRQ-coherent witness binds the IMU instance/configuration epoch and the CAL
and ALIGN generations. A physical recovery revokes the previous witness and
old queued samples. Fresh CAL, ALIGN and source origins must be obtained before
START. START reserves that witness before backend preparation and validates it
again in the same critical scope as the FLIGHT publication. No backend I/O runs
inside that scope. Generation/revision exhaustion fails closed; it never wraps
into a valid old witness.

Epoch identity and START usability are distinct. Same-epoch clipped fault data
continues through Inertial, ImuSampleBus and the existing INS/navigation-quality
fault latch. A later clean sample cannot erase that navigation fault latch.
Revoked or stale epochs cannot enter that path. Bad external quality remains an
ordinary quality/error path; wrong internal source/configuration invariants use
the established terminal assertion fault publication.

CAL/ALIGN configuration actions acquire a lifecycle reservation under their
module IRQ lock. The reservation checks the current lifecycle and START state
before publishing the action owner. Immediate/queued START admission uses the
same exclusion boundary. An earlier read of READY does not authorize later
configuration after START. Internal START preparation still uses its dedicated
non-configuration actions. After START, MPU recovery masks qualification but
does not reset the running mission, source lock or frozen origin state.

## Calibration policy and reference limitation

The saved RET6 reference has `calibration=[]` (procedure mask zero). Its initial
fault-free CAL_NONE admission remains supported. After a physical recovery,
CAL_NONE cannot supply a fresh calibration witness and stays fail-closed;
ONE_FACE is unsupported in that saved configuration. Unlimited physical
retries therefore do **not** mean complete automatic mission re-admission.

A reference intended to permit preflight re-admission should explicitly enable
the existing ONE_FACE calibration capability in SCG. It must then complete
fresh CAL/ALIGN/origin steps. This is a deliberate configuration choice for a
new/reference project, not an implicit migration of the user's existing
project. This change does not add an automatic calibration command sequence.
The independent Host positive fixture explicitly selects ONE_FACE; production
RAM comparisons preserve the saved NONE configuration.

## Gate and evidence limits

The capability is a generated numeric constant. First-party C uses ordinary
constant branches; the compiler removes disabled paths. The typed headers
select the sample layout and expose explicit single-level accessors. No new
Power10 C conditional exception or other threshold/allowlist extension is used.
New operation boundaries isolate calibration-state initialization, alignment
collection publication, blocking mission preparation and atomic FLIGHT commit;
they are not assertion-density or formatting workarounds.

Host tests use bounded I2C/time inputs and projected non-IMU/storage health.
They execute the real MPU, selector, CAL, INS, barometric collector and lifecycle
code. White-box epoch seeds and a terminal-process-exit interceptor are test
only; they do not enter firmware and do not demonstrate MCU recovery. The
configuration TOCTOU was identified by static task/priority analysis. The
parent's rejected preemption probe was not delegated/re-run; sequential
reservation regressions do not constitute a dynamic scheduling reproduction.

Power10 output remains a textual project gate and must explicitly retain
critical-contract review NOT PROVEN. Actual ARM compilation, GCC analyzer and
linked stack reports have their recorded scopes. The existing RET6 Logger
minimum-margin failure remains open; MSP/ISR nesting, whole-program stack
margin, timing and hardware/flight behavior remain unproven. No RET6 hardware
qualification is claimed.

## Recorded software verification, 2026-10-06

Fresh `sf6_epoch_v4` outputs use the final owning payloads and the explicitly
reviewed `mpu_epoch_20261006_v3` stack input fingerprints. Historical V2
fingerprints and all stack margin/source-coverage requirements remain intact.
The reviewed delta contains 15 input paths and 39 dependency-graph paths; the
only dependency addition for existing translation units is the epoch header.
The previously executed official CubeMX RET6 snapshot is reused unchanged:
this batch did not invoke CubeMX again or replace its IOC with a synthetic file.

| Actual check | RET6 compact | Ordinary F407 regression |
|---|---|---|
| ARM Release compile/link | PASS | PASS |
| GCC `-fanalyzer` compile/link | PASS | PASS |
| Emitted `power10-check` | Text gate PASS; critical review NOT PROVEN | Text gate PASS; critical review NOT PROVEN |
| Emitted architecture gate | PASS | FAIL: existing InputVoltage dependency |
| Emitted linked artifact gate | PASS | PASS |
| Emitted stack gate | FAIL: Logger zero margin | PASS: all eight task budgets |

The final product Host invocation passed all eight tests, including physical
failure before first CAL, the first subsequent recovery, fresh qualification
and successful START. Additional recorded invocations passed 79 configuration
regressions, 51 existing binding regressions and three direct epoch-input
mutation/dependency tests. These are separate executed scopes, not a claim of a
full repository suite pass. The quality pre-fix case runs the sealed earlier
draft, while the final case exercises the real INS quality latch. Sequential
configuration ownership tests do not prove dynamic task scheduling behavior.

RET6 uses CM3 softfloat without CCM/FPU: Flash load is 222,564 bytes and linked
RAM is 63,936 bytes (408 data + 63,528 bss), leaving 1,600 of 65,536 bytes. RAM
increased by 200 bytes relative to the earlier reference. Linking satisfies the
hard capacity limit, but the 20% RAM spare goal is missed by 11,508 bytes. This
measured reference retains MPU6050, E28, BMP280 and local SSLOG, with GNSS absent;
it is not four-module RET6 acceptance. Barometric vertical aiding does not bound
horizontal inertial drift. F407 linked RAM stays 159,516 bytes; its Flash load
increases by 24 bytes to 330,464 bytes.

RET6 map attribution totals 63,936 bytes: platform/device/system/RTOS 10,822;
algorithm/CAL/ALIGN 6,931; logging/storage 18,152; task stack arrays 21,504;
queues/buffers 4,257; main/MSP linker reservation 2,048; padding/unattributed 222.
These categories are a recorded object/symbol attribution, not runtime
measurement. Stack arrays and MSP are counted once; worst-known call-path
estimates are not added again to RAM. Logger's estimate is 3,072 bytes against
its 3,072-byte allocation. A separate Logger batch must close that genuine
failure without reducing the required margin or weakening the checker.

Complete commands, logs, source hashes, compiler dependencies, stack usage,
ELF/map hashes and the final commit identity are retained in the corresponding
small evidence archive. Main/MSP paths, ISR nesting, timing, hardware behavior
and completed critical-contract acceptance remain NOT PROVEN or NOT RUN.
