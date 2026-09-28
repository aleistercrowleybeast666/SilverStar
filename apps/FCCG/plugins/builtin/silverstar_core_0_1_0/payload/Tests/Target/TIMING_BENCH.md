# F407 elapsed-cycle and HWM bench

This is an explicit opt-in target tool. The production source graph does not
include these files. No target measurements were made during software validation;
Host samples are injected counters, never reported as CPU measurements.

Use a separate user-selected bench project with the F407, FreeRTOS, monotonic time
and logging components selected. Compile `timing_bench.c`, `timing_bench_f407.c`
and, for the runnable collection example, `timing_bench_example.c`; add this
directory to its includes. These files are preserved by reference import and
source export. Adding them is a deliberate bench change, with its own RAM/stack
budget; they allocate no default production storage and start no task or output.

After scheduler and SystemTime initialization, a normal task calls
`TimingBenchF407_Initialize()` once. It enables CMSIS DWT CYCCNT without zeroing
an already running counter. It does not change clocks, interrupt priorities,
FreeRTOS options, logger rates or queue capacities. Initialization from an ISR or
with interrupts masked fails. No filesystem, flash, GPIO or transport is used.

`TimingBenchExample_Collect(&example)` is a compiled, real integration entry point:
it invokes `Ins_GetLatestSnapshot` and `Estimator_GetLatestSnapshot` through the
measurement wrapper, then obtains the real HWM/queue/Logger diagnostics. Those two
example intervals measure only snapshot getter overhead, **not** whole INS or
estimator work. Inspect the caller-owned `example` through the debugger. The
wrapper executes its work callback exactly once even when timing admission fails.

For full work intervals, place Begin/End calls in a bench copy at these points:

| Interval | Begin and End boundaries |
|---|---|
| INS | `AppTask_Ins` loop processing after wake; end before its `vTaskDelay` |
| Estimator | `AppTask_Estimator` prediction/measurement processing after wake; end before each delay |
| Logger | `AppTask_Logger` drain/append/flush iteration; close every early-return/continue path before its delay |
| ISR | Around the selected HAL IRQ handler/callback in its actual IRQ context, before any return |

For narrowly defined algorithm samples, the precise finite call boundaries in
the current source are `InsTask_Propagate(&sample)` in `APP/Src/ins_task.c` and
`Estimator_PredictionsProcessCycle()` in `APP/Src/estimator_task.c`. The former
includes the actual mechanization/body-input production; the latter drains and
processes the selected estimator's prediction/measurement work. Begin immediately
before the selected call and End immediately after it. For the Logger, select
`LoggerTask_RecordAppend(&record)` (serialization and any resulting write), or
`LoggerTask_PeriodicFlushTry(now_us)` (periodic flush), and label that operation in
the measurement report; do not mix those samples and call them whole-task times.
One concrete peripheral-ISR scope is the actual
`HAL_DMA_IRQHandler(&hdma_usart3_rx)` call in `Core/Src/stm32f4xx_it.c`. The bench
copy places ISR Begin immediately before that call and End immediately after it;
it does not alter the HAL callback routing or claim every ISR was measured.

Keep a stack-local ticket and test Begin's return before End. Do not call an entire
infinite `AppTask_*` function through the wrapper. Never let instrumentation errors
skip application work. The producer calls are deliberately absent from normal
firmware; full INS/estimator/Logger/ISR target timings therefore remain unmeasured.

```c
TimingBenchTicket ticket = {0};
TimingBenchResult begin = TimingBenchF407_Begin(TIMING_BENCH_INS, &ticket);
/* The bench copy executes its original finite work here, unchanged. */
if (begin == TIMING_BENCH_OK) {
    TimingBenchResult end = TimingBenchF407_End(&ticket);
    /* Preserve end in the caller's diagnostic state; errors are not samples. */
    (void)end;
}
```

Each of the four intervals has one active slot. A same-interval nested or
concurrent Begin returns BUSY and preserves the earlier ticket. Different
intervals can overlap, including ISR preemption; measurements are inclusive and
must not be added as CPU utilization. Thread identity is the stable kernel-owned
name **address** of the static FreeRTOS task (the string is never read), whereas
ISR identity is IPSR. End from another owner fails without consuming the original
span; duplicate or stale tickets fail. This tool assumes the project's static
tasks; it does not support task deletion/address reuse during a session. The ISR
slot rejects nested different IRQ owners rather than corrupting their attribution.
PRIMASK is saved/restored for bounded counter-state operations, never held over
the measured callback. Begin and End reject all system exception contexts (IPSR
1–15), including NMI/HardFault/SysTick/PendSV. Only maskable peripheral IRQs may use
the ISR interval. PRIMASK does not serialize NMI/HardFault, and fault paths remain
independent. The portable context guard is also exercised by the Host fixture.

CYCCNT subtraction handles one 32-bit rollover. An independent monotonic timestamp
requires spans at most 5 seconds at 1–180 MHz, well below the cycle rollover period.
Nonmonotonic time, changed clock frequency, disabled/stopped counter, zero cycles,
or a cycle/wall-time mismatch above the 10-us sampling tolerance rejects the span.
Do not include sleep, debugger halts, frequency changes or scheduler delays in a
span. The timestamp source must already be initialized and advancing. Very short
counter stalls within the stated tolerance cannot be distinguished. Counter and
ticket exhaustion never silently wrap: saturation is flagged, the overflowing
sample is rejected, and reinitialization of an active session is disallowed.

`TimingBenchF407_ReportGet` runs only in a normal task with interrupts enabled.
It copies timing statistics, then calls `SystemTaskStack_SnapshotGet`,
`LoggerBus_DiagnosticsGet`, `LoggerTask_DiagnosticsGet`, `ImuSampleBus_StatsGet`
and `EstimatorBus_StatsGet`. Per-provider status is reflected in `valid_mask`;
PARTIAL is not a complete report. The task snapshot's own `valid_mask` distinguishes
unavailable tasks. Stack HWM is free stack **words** (4 bytes on F407); logger queue
HWM is occupied entries. IMU/estimator snapshots provide current queue occupancy
and overflow counters, not an invented lifetime HWM. The capture begin/end times
describe sequential collection, not an atomic global snapshot.

For each interval, completed=0 means no accepted measurement. Otherwise read
minimum/maximum/last cycles and total_cycles/completed; seconds equal cycles /
clock_hz. Rejected and saturated are explicit, with return codes identifying a
failed call. Timing includes interrupt/task preemption and instrumentation
overhead; it is observed elapsed active cycles, **not WCET** or exclusive task CPU
time. Compare representative load, worst observed latency, missed deadlines and
real HWM only after authorized target testing. This software check supplies no
target timing guarantee and no fabricated execution-time result.
