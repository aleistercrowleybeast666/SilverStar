# SF6 RET6 compact: phase 1 checkpoint

2026-10-06 UTC. Isolated branch `codex/sf6-compact-ret6`, based on KF6 candidate
`7fa06c4155661e40847c0af78f4b23f3659b995d`. This is an implementation checkpoint,
**not acceptance, hardware qualification, or Power of Ten compliance**.

Only SCG was changed. No hardware, serial port, probe, flash, stable checkout,
GSHC or FLP was accessed or modified. No merge or push was performed.

## Actual evidence

* Official STM32CubeMX 6.15.0 generated STM32F103RET6 projects with the installed
  official STM32Cube FW_F1 V1.8.7 package. The initial minimal Makefile project
  compiled and linked: text 2944, data 12, bss 1572 bytes. This is only a minimal
  platform check, not a Flight firmware resource result.
* The current official CubeMX STM32CubeIDE project contains I2C1, SPI1, USART1
  RX/TX DMA, SDIO/FatFs, TIM6 HAL tick, EXTI and safe actuator GPIO defaults.
  Actual clock is HSI/2 * 16 = 64 MHz. USART1 RX/TX are DMA1 channels 5/4.
  SDIO shares DMA2 channel 4 for RX/TX as emitted by CubeMX; both actual
  `__HAL_LINKDMA` bindings are required by the import check. F1 HAL sets the
  direction for each transfer. This does not establish hardware correctness.
* SCG imported that genuine project and generated the current Flight candidate
  through normal Plan/Apply. RET6 is CM3, soft float, 512 KiB Flash, 64 KiB RAM,
  no CCM/FPU. Maintenance is off. MPU6050, NEO-M9N, E28-2G4M12SX, BMP280 and
  SDIO SSLOG remain selected. Missing CM3 measured timing is an explicit warning
  for this compact compile-only target, following user authorization. Unsupported
  peripherals, proven budget errors and other safety errors remain errors.
* Full ARM compilation reached the real static task entry and attempted linking.
  Link **failed**: RAM overflow **31920 bytes**, plus unresolved SystemPower
  operations caused by a target default enabling an absent power provider.
  The failed map has `.bss = 94128` bytes; static task stacks are already inside
  it and must not be added again. No complete RET6 Flight ELF exists at this
  checkpoint. Earlier raw Cube main results did not reach Flight tasks and are
  explicitly excluded from complete firmware resource claims.
* New compact/rate regression: 10 passed. Scoped selected SCG regression:
  93 passed, 1 failed (algorithm numerical golden hash); failure unresolved.
  The first run used an incorrect pytest temporary root: 87 passed, 7 workspace
  safety failures. The corrected run is a separate result, not a full-suite pass.
* Emitted `power10-check`: failed, 2 linker-path/heap checks because its template
  still assumes F407. It explicitly reported critical-contract review NOT PROVEN.
  Emitted architecture-check failed at its F407 make target. Emitted Host suite
  failed compilation because its include path still assumes F407. No gates were
  weakened to turn these failures green.

## Implementation scope

Compact is opt-in and enforces at most one physical IMU, GNSS, telemetry and
barometer, independent of brand. Normal project serialization omits the new
false option and normal instance bounds remain unchanged. Strict validation and
direct source-graph resolution both enforce the limit. Only the build-page
compact checkbox and related translations were added to the GUI.

RET6, its F1 Flight backend, CM3 FreeRTOS port and FatFs R0.11 storage adapter
are separate declarative plugins. Official vendor licenses are retained.
FreeRTOS CM3 port is the official FreeRTOS-Kernel v11.3.0 GCC ARM_CM3 port.
The R0.11 append adapter opens, seeks to end and checks the result before handle
publication; seek/close fault tests are still required. Long filename support was
enabled by official CubeMX with stack allocation (no heap).

The generated compact entry only integrates an imported clean CubeMX USER CODE
Includes/2 section; it refuses existing application contents and leaves the
import snapshot unchanged. Regeneration continues to preserve user payloads.

SF6 remains its existing 192-byte core with no history. Compact SX128x scratch
uses the existing 260-byte bounded HAL/chunking contract; a complete command
length audit remains required. No logger queue, aggregation, task-stack or GNSS
origin-window reduction has yet been made. No GNSS was dropped at this checkpoint.

## Remaining work and acceptance blockers

1. Correct absent-provider capabilities, evaluate actual map retention and
   compact queue capacities with the complete startup descriptor snapshot.
   Prefer four devices; dropping GNSS is authorized only after actual full
   resource failure. Barometer and local SSLOG are to remain.
2. Adapt emitted target-aware checks without removing coverage or thresholds;
   run fresh ARM link, real `-fanalyzer` compilation, relevant normal/fault Host
   regressions, artifact and stack reports. Neither the link limit nor 20% spare
   RAM has been achieved. CM3 CPU/WCET budget is unknown.
3. Review bounded storage waiting, task/ISR/DMA ownership, and same-instance IMU
   recovery preserving the START lock. Recovery changes have not been made.
   GNSS no-fix semantics and existing protocol checks remain unchanged.
4. Critical contracts, useful assertion semantics, whole-program call graph,
   task/library/ISR/MSP stack bounds and hardware behavior remain NOT PROVEN.
   No board exists for RET6 testing; MCU execution and hardware/flight evidence
   are NOT RUN. Horizontal position remains inertial drift when GNSS is absent.

## Reproduction and evidence location

Current lightweight candidate: `.work/generated_ret6`; official input:
`.work/cubemx_flight/SF6_RET6_Hardware`; scripts and complete success/failure logs:
`.work/evidence`. These belong to this isolated worktree only. Retained small
phase evidence is under `docs/FCCG/platform/evidence/SF6_RET6_phase1`.

Tools: ARM GNU 14.3.1 (`D:/Arm GNU Toolchain/14.3 rel1/bin`), mingw32-make 4.4.1,
host GCC 16.1.0, existing FLP Python environment used read-only for pytest.

Commands (from the generated candidate; each exit retained in its log):

```
mingw32-make -j2 all "GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin"
mingw32-make power10-check
mingw32-make architecture-check
mingw32-make host-tests
```

All four commands above returned make exit 2 at this checkpoint. Static analysis,
artifact acceptance and full stack proof are NOT RUN. Source/component hashes
in the generated ownership metadata identify the compiled dirty snapshot;
the checkpoint commit preserves its owning source implementation for review.
