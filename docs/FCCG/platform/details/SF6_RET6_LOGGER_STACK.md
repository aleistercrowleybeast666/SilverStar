# RET6 Logger stack closure

This batch follows MPU commit `79eeadad53c70e55a1f52a278f950283d3486227`.
It retains the measured compact E28/MPU6050/BMP280/local-SSLOG reference with
GNSS absent and the saved NONE calibration configuration. It does not integrate
NRF, change GSHC/FLP, access hardware, or alter ordinary profile choices.

## Bounded local lifetimes and coherent final status

`SystemFlightRecovery_FinalStatusGet` reads exactly the five recovery fields
consumed by final mission metadata. All five reads remain inside the existing
recovery IRQ lock/unlock scope; no pointer to internal state is returned. The
complete recovery status layout, existing status API, commit/process behavior
and action ownership remain unchanged. Both F1 and F4 owning storage payloads
use this small local projection. Field order, 48 serialized metadata bytes,
section/version, storage calls and ordinary error results remain unchanged.

The Logger queue record now lives only inside the existing pop/serialize/START
barrier operation. It expires before snapshot maintenance and finalization
storage I/O. Neither queue-pop nor synchronous record serialization retains a
pointer to it. Every business expression and its order is unchanged. No global
scratch, function split, noinline attribute, compiler flag, task allocation
change or margin reduction was introduced.

The exact-input stack provenance set adds only four reviewed source/header
variants. All 298 compiled C dependency graphs remain unchanged; historical
V2 and MPU V3 fingerprints, callback restrictions, source coverage and the
256-byte context plus 256-byte minimum margin remain intact. Input fingerprints
establish identity, not completed semantic or whole-program stack acceptance.

## Executed Host scope and retained failures

The final status byte/result fixture executes both recorded pre-fix owning
sources and current owning sources on F1/F4. Nine cases per version cover normal
state, no mission ID, unavailable recovery state, deployment failure, unavailable
or unhealthy/unmounted storage, atomic-write failure and Logger fault. Both
targets pass the identical independent expected bytes/results. First fixture
attempts failed for Windows COFF unused-symbol linking and a missing target
include; their logs remain, and expectations were not weakened.

After the final lifetime change, the explicit F407 selected Host job invocation
passed six executables and 33,852 checks. It covers real recovery-state projection
against complete snapshots over existing normal/fault transitions, START
durability, snapshot metadata, landing drain/close, diagnostic final-status
failure and uncertain/partial writes. RET6's explicit two-program Logger scope
passed 1,043 checks. These invocations execute the emitted job planner/compiler
and selected-job loop with an absolute project root. They intentionally end
before the unconditional storage suite and do not replace that suite or claim
a full emitted Host wrapper pass. Host scheduling/trap interception is test
only and is not MCU recovery or scheduling-race evidence.

The emitted wrappers remain FAIL: RET6 baro/IMU landing Host capability assertion,
RET6 lifecycle Host missing MPU epoch-provider linkage, and F407 storage stream
configuration rejection (the known `0x07` fixture boundary). The latter two
prevent a wrapper/full-suite success claim. No capability assertion, protocol
validation, baseline expectation or wrapper diagnostic was weakened to remove
these failures. The separate exact-input mutation/binding invocation passed
54 tests again after the final queue-scope fingerprint was added.

## Actual ARM resources and acceptance limits

The pre-fix RET6 gate reported Logger estimate/allocation 3,072/3,072 bytes,
zero spare, FAIL. The projection-only intermediate output reduced the estimate
to 2,936 bytes but left 136 bytes spare, still FAIL. That intermediate result
was not accepted. Final linked results are recorded with the corresponding
ELF, `.su`, complete call chain and unchanged gate below.

Actual final Release images use CM3 softfloat/no CCM for RET6. RET6 Flash load
is 222,620 bytes (+56); linked RAM stays 63,936 bytes, leaving 1,600 bytes. F407
Flash load is 330,528 bytes (+64); linked RAM stays 159,516 bytes. Task stack
arrays are included once in linked RAM; estimated call-path use is not added
again. The RET6 hard linking limit is satisfied, while the 20% RAM-spare goal
still misses by 11,508 bytes.

Critical-contract manual acceptance, main/MSP and ISR nesting, MCU timing,
horizontal inertial drift bounds and hardware/flight qualification remain
NOT PROVEN or NOT RUN. Ordinary F407's existing InputVoltage architecture
violation is retained. The old checker overlay is used by the reference
component importer and needs a separate maintenance synchronization; this
Logger batch does not retroactively claim it was included in MPU commit 79ee.

## Final emitted gate results, 2026-10-06

Both fresh final targets actually compiled/linked under Release and under GCC
`-fanalyzer`, with exit zero. RET6's emitted Power10, architecture, linked
artifact and stack commands all exit zero. F407's emitted Power10, artifact and
stack commands exit zero; its architecture command exits two on the unchanged
InputVoltage dependency. Power10 emits critical-contract review NOT PROVEN on
both targets (RET6: 5,345 checks/664 recommendations; F407: 6,310/813).

| Logger measurement | Before | Projection only | Final |
|---|---:|---:|---:|
| RET6 task allocation | 3,072 | 3,072 | 3,072 |
| RET6 worst-known estimate including context | 3,072 | 2,936 | 2,736 |
| RET6 remaining margin | 0 FAIL | 136 FAIL | 336 PASS |
| RET6 `AppTask_Logger` frame | 480 | 480 | 280 |
| RET6 `FinalStatusWrite` frame | 456 | 176 | 176 |
| F407 worst-known estimate including context | 2,104 | recorded separately | 1,768 |
| F407 remaining margin | 968 | recorded separately | 1,304 PASS |

Final RET6's complete deepest recorded chain starts with `AppTask_Logger` (280),
`LoggerTask_SnapshotMaintain` (24), `SystemMissionSnapshot_Create` (208),
`MissionSnapshot_DevicesWrite` (88), then section commit/persistent object
write/latest/read and FatFs `f_open` (1,128), its directory/allocation/write
path, SD completion and FreeRTOS queue/tick paths. The recorded chain sums to
2,480 bytes plus the unchanged 256-byte context. Every enabled task is budgeted.
No Logger allocation increase was needed. A larger allocation alone would not
close unresolved main/MSP/ISR or hardware stack proofs.
