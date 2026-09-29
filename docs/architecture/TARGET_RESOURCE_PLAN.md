# Target resource plan (Round 4 work in progress)

The target plan uses four separate authorities: memory, peripheral assignment,
CPU/real-time work, and I/O throughput. A successful ARM link alone establishes
none of the latter three. This page records the checks currently implemented and
the evidence still needed before the complete Round 4 gate can pass.

## Memory and clock

The exact MCU plugin declares official physical memory regions and maximum HCLK.
The selected CubeMX IOC or board instance supplies its actual HCLK. Generation
rejects a missing or excessive HCLK. After a build, `BuildAudit_Run` reads the
selected linker `MEMORY` block, the ELF sections through `arm-none-eabi-objdump`,
`arm-none-eabi-size`, linked symbols through `arm-none-eabi-nm`, and GCC `.su`
files. It rejects an enlarged linker region, sections outside the exact MCU,
linked `malloc`/`calloc`/`realloc`/`free`/`alloca`, missing C stack-usage files,
and dynamic stack-usage annotations. MAP and ELF are required build artifacts.
The existing Flight stack-report remains responsible for whole-call-chain static
task-stack budgets; a largest individual `.su` entry is not a task-stack proof.
Runtime high-water marks are diagnostics, not generation readiness gates.

The GS_SS1 F103 reference uses the official 64 KiB Flash and 20 KiB SRAM,
with 72 MHz HCLK. The F407 Flight reference uses 168 MHz HCLK and the exact
F407VE memory-region contract. The new SilverStar Ground firmware has passed
ARM compile/link on the F103 reference, but not a PCB smoke test.

## Inertial rate and replay work

The raw IMU ODR comes from the selected physical device's generated runtime
profile. `mechanization_aggregation` is an INS algorithm parameter. Its legal
values are one or two real samples per propagation interval; the current
reference default is two, preserving its existing firmware cadence. The plan
computes `effective_propagation_rate = raw_imu_odr / aggregation` and
`maximum_replay_steps = ceil(maximum_measurement_delay * effective_rate)`.
It also checks that the estimator's fixed history can hold the declared window
at that rate. The one-sample C path was host-tested and ARM-built on F407;
it does not synthesize extra IMU samples. KF6 declares FP32 arithmetic with
Cortex-M3 software-float and Cortex-M4F hard-float timing profiles. ESKF15
currently declares only Cortex-M4F hard-float; Cortex-M3 selection yields
`TIMING_PROFILE_UNQUALIFIED` rather than claiming the algorithm is impossible.

GNSS and barometer measurement admission still depends on fresh measurement
timestamps in the estimator. No sensor is raised to a fictitious IMU cadence.

## Pending CPU and I/O authority

The repository has actual FreeRTOS priorities and service cadences, but no
reviewed upper-bound task WCET and blocking/ISR interference budget for every
configured target. A 1 ms service loop is not a 1000 Hz full algorithm load.
Host benchmarks and observed target cycles are not WCET. `ResponseTime_Analyze`
implements a bounded fixed-priority recurrence with task execution, blocking,
higher/equal-priority peers, ISR interference and deadlines. It intentionally
has no invented built-in timing budgets. Until qualified target-specific upper
bounds and event rates are supplied to it,
the CPU timing portion is unqualified; neither F407 nor F103 receives a
complete static schedulability PASS from this page.

Peripheral matching currently validates selected resource kinds and detailed
bus constraints through the FCCG resource planner. An end-to-end I/O throughput
budget covering radio packet rate, PC serial framing, storage latency, DMA and
bounded queues is still required for the complete target resource plan.
