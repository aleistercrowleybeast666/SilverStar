# SF6 MPU B checkpoint: configuration intent, not readmission

Source: `6be9411baa23dc45ada021e1e9b5ae0e57e34ab1`, isolated
`codex/sf6-compact-ret6`; prior accepted literal contract: `3188bfb3`.
This checkpoint precedes the authorized switch to STM32F103RFT6 as the main
four-module baseline. RET6 remains the separate no-GNSS compact candidate.
Nothing was merged, pushed, flashed or tested on hardware.

## Concrete correction

The actual startup FSM exposed an asynchronous initialization ordering defect.
At 1.040 s, a prepared MPU still had `initialized == 0`. Both selector
configuration operations skipped its provider and returned NOT_READY (2).
Startup recorded that ordinary failure permanently, even though normal physical
initialization subsequently reached a verified epoch and healthy samples.

The only production edit routes ConfigApply and ConfigVerify to an already
prepared compact instance as well as an initialized instance. The existing
provider owns the result: DELEGATED (13), BUSY (15), then ALREADY_MATCHED (1)
after actual reset, configuration readback and fresh acquisition. Neither BUSY
nor DELEGATED becomes READY. Ordinary mode's prepared accessor remains the
literal-zero branch. No startup report, health qualification, protocol, source
lock, calibration policy, algorithm, queue, log or stack allocation was changed.

The targeted new regression failed before the correction at the pending
ConfigVerify assertion. An intermediate fixture incorrectly expected OK after
verification; the existing provider contract is ALREADY_MATCHED. The final
assertion checks that exact result and the successful matched mask. The failed
intermediate execution is retained; no production return contract was changed.
Final pytest: 3 tests pass, covering 14 existing compact sequences, 3 ordinary
sequences and the new configuration-intent sequence.

## Actual B experiment and remaining blockers

The diagnostic harness compiles actual generated MPU and BMP drivers, facade,
Descriptor, selector, inertial bridge, CAL, INS/vector alignment, origin
collector, health and Flight lifecycle/backend. I2C registers, time, output
physical state and unavailable storage are Host inputs. The bounded DeviceTask
barometer projection helper is extracted byte-for-byte, rather than replacing
its pressure-to-altitude policy. Permanent scheduler loops are not run.

The actual optional absent-medium logging admission executes; no snapshot-ready
field is set. Calls to out-of-scope snapshot/sink services abort the Host test.
Consequently this is not successful SD snapshot or local-log qualification.
Selected target logging remains enabled and compiled.

| Observation | Actual outcome |
|---|---|
| Normal startup after routing correction | IMU init/start/config DELEGATED; verify BUSY until 1.320 s, then ALREADY_MATCHED; mission-capable report 1 |
| Failed boot, then physical MPU recovery | Initial failure and timeout remain in the report; live epoch verified but public healthy remains 0 |
| Actual CAL_NONE request | READY with identity correction and generation 2; after warm recovery, explicit new NONE request advances generation to 3 |
| Warm same-instance physical recovery | Owner remains 0; epoch 1 -> 2; fresh physical samples return; public healthy remains 0 |
| Actual new alignment request | Alignment sequence 1 -> 2, but required barometer origin remains NOT_READY in this harness |
| START | Rejected; normal initial alignment/origin baseline is not yet established |
| Actual post-START recovery chain | NOT RUN because the initial START prerequisite failed |

All three integrated diagnostic cases exit 1 (2, 3 and 2 recorded expectation
failures). The barometer-origin failure is unresolved; it may include a harness
scheduling/ownership limitation and is not attributed to an MCU hardware
defect. It has not been bypassed by changing the required-origin mask or by
writing readiness fields. Earlier harness iterations and their failures are
retained, including peripheral-unavailable inputs and an incorrect pressure
projection subsequently replaced by the exact DeviceTask helper.

Optimized Host diagnostic attempts also failed strict warnings in selector
telemetry/GNSS and optional magnetic paths. Their logs are retained. The
unoptimized `-O0 -fno-lto -Wall -Wextra -Werror -pedantic` build executes the
state experiment, with firmware assertions active. It is not an optimized Host
gate pass. The final integrated experiment remains a failing experiment.

Readmission is **not implemented**. Inertial samples still do not carry the MPU
configuration epoch into CAL/ALIGN results; immutable failed startup-device
history also controls alignment capability and health admission. A generation-
bound acceptance transaction would cross these owners and the START/storage
transaction. Non-NONE calibration policies, cross-owner freshness/epoch binding
and START/readmit concurrency are NOT PROVEN. Physical recovery never clears
public qualification or startup error; the existing fail-closed state remains.

## Fresh emitted target checks and resources

Own validation tree `.work/generated_ret6`, exact official CubeMX 6.15/F1 1.8.7
RET6 hardware snapshot retained from the prior actual generation. This batch did
not run CubeMX again. Raw source comparison checks 1514 files, including all 144
linked C/assembly inputs, without mismatches. This byte comparison does not
certify historical saved provenance.

| Gate, emitted command unchanged | Exit / scope |
|---|---|
| ARM `-B all` | 0, actual CM3 soft-float compilation and linking |
| `-B static-analysis` | 0, actual ARM `-fanalyzer` compilation/linking |
| architecture-check | 0 after separately rerunning an interrupted attempt; interrupted log retained |
| power10-check | 0 text checks: 5272 checks / 112 C / 2229 functions; critical-contract review explicitly NOT_PROVEN |
| artifact-check | 0 |
| stack-report | 2, unresolved `SensorImu_Verify`; whole task/library/MSP/ISR stack proof incomplete |
| full host-tests | 2, required positive JY901B fixture is missing its unselected capability header; full suite did not pass |

Four existing newlib syscall-stub linker warnings remain. There is no
warning-free firmware, complete Power of Ten, safe stack margin, STM32 WCET or
flight/hardware qualification claim. Existing F1 IRQ/timebase and RF timing
boundaries remain open. Increasing RFT6 SRAM cannot resolve these boundaries.

RET6 linked RAM: `.data 408 + .bss 60944 + MSP 2048 = 63400` bytes. Spare 2136
bytes (3.259%). Static task/idle stacks, 21504 bytes, are already included once
in BSS. The 20% spare goal still misses by 10972 bytes. BIN: 218440 bytes. Net
versus `3188bfb3`: **RAM 0, Flash +104 bytes**. No further resource reduction was
performed in this checkpoint.

## Preserved provenance and next target

Read-only regular ProjectConfiguration_Reconcile and the normal assembler plan
both retain the historical deleted `Common/Inc/silverstar_build_mode.h` record.
The model file remains unchanged by that check. Normal Apply deliberately keeps
prior payload ownership records; no hash was edited or adopted manually.
The saved model's complete current provenance identity remains NOT PROVEN.

Next work uses a separate single RFT6 generation tree and actual official
CubeMX RFTx output, including its XL startup/defines/linker, then imports and
links all four requested sensors with local logging. RET6 evidence and its
no-GNSS configuration remain intact. Queue/log/stack reduction is paused.

Checkpoint archive: `../evidence/SF6_MPU_B_config_intent/mpu_b_config_intent_checkpoint.zip`
(3,192,141 bytes, 135 entries; SHA-256
`b3700b10899ad56d058757bc6d1f532fc32659cd0fdac4d0d22b65c52123919d`).
Library copy: `libfile_08b6026e013c819198628adde1872261`, version 0.
The archive embeds the report before these archive-identity lines; source commit
and every included artifact hash are recorded in its manifest. Windows extended
attribute synchronization is unavailable; this does not negate the Library upload.
