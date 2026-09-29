# Target resource plan (Round 4 work in progress)

The target plan uses four separate authorities: memory, peripheral assignment,
CPU/real-time work, and I/O throughput. A successful ARM link alone establishes
none of the latter three. This page records implemented checks and remaining
Round 4 structural work; target WCET qualification belongs to Round 5.

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

## Timing evidence levels

Timing evidence is separate from the static rate/resource facts. The
`TimingEvidence_Assess` interface reports `INVALID` when any required work
bound is missing, `STALE` when a reviewed profile has a different source
fingerprint, and `MEASUREMENT_PENDING` when all structural checks are supplied
but reviewed task/ISR execution bounds are absent. It invokes the existing
fixed-priority response-time calculation only with nonempty reviewed budgets
and a matching source fingerprint. A missing WCET is never treated as zero.
`QUALIFIED_STATIC` requires conservative execution, blocking and ISR budgets
and a passing deadline analysis. This permits Round 4 software work to
continue while Round 5 collects actual target evidence.

## Pending CPU and I/O authority

The repository has actual FreeRTOS priorities and service cadences, but no
reviewed upper-bound task WCET and blocking/ISR interference budget for every
configured target. A 1 ms service loop is not a 1000 Hz full algorithm load.
Host benchmarks and observed target cycles are not WCET. `ResponseTime_Analyze`
implements a bounded fixed-priority recurrence with task execution, blocking,
higher/equal-priority peers, ISR interference and deadlines. It intentionally
has no invented built-in timing budgets. Until qualified target-specific upper
bounds and event rates are supplied to it, the WCET-based result is
`MEASUREMENT_PENDING`; neither F407 nor F103 receives a static schedulability
PASS from this page. This does not block the remaining Round 4 phases.

Peripheral matching validates selected resource kinds and detailed bus/electrical
constraints through the shared FCCG resource planner. Ground radio binding uses
the same physical SPI, GPIO, EXTI and safe-output requirements as Flight radio
binding; exclusive Ground radio pins cannot be assigned twice. The GS_SS1 IOC
topology passes these checks, including its 9 Mbit/s SPI1. Ground UART PC
capacity uses the configured 8N1 baudrate and the canonical GSP framing sizes:
at 230400 baud the theoretical line ceiling is 23,040 bytes/s per direction;
a full 61-byte AIR_RX frame occupies 70 GSP bytes. This upper ceiling excludes
GS_STATUS and ACK traffic. USB CDC has no capacity inferred from its virtual
COM baudrate. An end-to-end I/O throughput budget covering offered radio packet
rate, PC serial framing, storage latency, DMA and bounded queues is still
required for the complete target resource plan.

Ground bridge per-call work now has explicit limits: 64 PC input bytes, four
radio RX packets (including invalid packets), and four queued PC frames per
flush. UART/USB ring reads are capped at 512 bytes per call; the actual bridge
request is 64. USB receive callbacks inspect at most 512 bytes and account for
any discarded remainder. These bounds are covered by host execution tests and
the F103 UART reference still compiles and links. Target execution time remains
`MEASUREMENT_PENDING`.
