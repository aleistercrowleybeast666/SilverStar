2026-10-10 TIM1 普通功能收敛

独审 P2（合法 CNT=0 误拒绝）已修复，代码提交 `9f115f087f12868dd8a5384ca0b1e78edace63e0`。
UIF 前后清零且 CNT=0..999 均可采样；配置、pending、单调性、停转/进展检查保留。
独审模型在原输入与相同编译器条件下复放：旧口 first/later/status=5/5/5，
修复口 0/0/0。模型时间常量不是真实 STM32 采样延迟。
新增实际原生 HAL boot caller 返回传播与 TIM1 第二次启动/晚期重配测试，保留原失败证据。
runtime 派生先 quiesce 唯一共享 IRQ，再重建 boot timer；只接受实际 DIV1/DIV2 相位，
运行时/ISR/已屏蔽 IRQ 的重配拒绝并锁存，普通 HAL InitTick 错误不会被调用者吞掉。

F407 已从历史的私有 timer probe 前进到完整私有 Ground 正常数据路径候选。
最终 normal/analyzer ARM 构建为 387 条命令、零编译警告；全部四个 emitted gates、
五个 generated Host 程序及明确普通范围 154 项 suite 通过，无 skips。
实际对象/ELF、独立 SDK IRQn、TIM1 strong owners 和 CPP config/clock header 依赖保留。
完整结果及 F103 回归见 [runtime 报告](NATIVE_CLASSIC_CDC_RUNTIME_20261010.md) 与
[证据清单](evidence/native_classic_cdc_ground_f407_20261010/verification.json)。

普通入口继续阻断；EP0 受阻审查无结果且未重试。语义接受、完整异步生命周期、IRQ
延迟/丢失 update、library/indirect-call、MSP/ISR 栈、WCET 及物理硬件时序仍 NOT PROVEN。
本轮没有连接硬件，未改日用/GUI/FINAL，未作正式放行或通用可用声明。

---

以下保留的是 53334df 的历史 probe checkpoint，描述的是其当时范围。

This increment is a private F407 native TIM1 clock/HAL/configuration compilation
probe. It follows the separate F103 runtime checkpoint
`179467265ec32ba79f7fb4bef85a4dfad82f8618`; it does not enable F407 Ground runtime
or normal generation. The ordinary native route in `multi_target.py` remains
blocked, and the existing SysTick runtime validator still rejects timer inputs.
The only new execution route is the explicit validation option
`--native-timer-probe`, with an independent device descriptor and a fresh output.
No user project, daily branch, GUI, FINAL candidate or physical board was changed.

The actual reviewed F407 input has an empty `TIM1_UP_TIM10_IRQHandler`. Its
timebase computes twice PCLK2 even when APB2 uses DIV1, and enables NVIC before
validating the requested priority. The isolated derivatives dispatch the actual
HAL timer IRQ, use PCLK2 for DIV1 and twice PCLK2 for the other admitted divider,
require an integral 1 MHz timer counter with 1000 counts per update, and validate
the initial priority before configuring hardware. IRQ enable follows priority
configuration and successful HAL timer initialization/start. Existing initial
HAL initialization/start failures retain ordinary error returns. This does not
prove safe reinitialization with an already enabled timer IRQ.

Original licensed timebase, IRQ, entry, HAL and linker inputs remain immutable.
Owned derivatives and replayable same-path patches identify every replacement.
The shared IRQ admits no additional core TIM10 owner. The known strong period
callback remains the native TIM1-only increment, and the strong linked IRQ,
HAL_InitTick and callback object owners are checked in both actual ELFs. The
selected F407 device header is pinned to its reviewed bytes, including its actual
timer kernel-clock model. A useful `_Static_assert` checks that the compiled
timer callback registry is disabled; it earns no runtime assertion credit.
This adds no Power-of-Ten preprocessing exception or density assertion.

The counter port samples actual TIM1 CNT, UIF and native HAL tick. It requires
main context with interrupts initially unmasked and validates the actual clock,
prescaler, period, timer mode, state and update IRQ enable. Three bounded snapshot
attempts restore the original PRIMASK. A pending update rejects the sample until
the actual IRQ retires it; the port never synthesizes an extra HAL tick. Failed
samples leave output unchanged. Fractional counter microseconds are represented
in the existing common clock's HCLK-cycle units; no SysTick or DWT replacement
is used. Missed update counts, IRQ latency and hardware timing remain NOT PROVEN.

The native F407 USB header omitted `USBD_CLASS_BOS_ENABLED` and
`USBD_USER_REGISTER_CALLBACK`, previously reported by the strict ABI probe.
A recognized-header derivative explicitly sets both options to zero for this
single-FS-CDC profile. It preserves the static allocator and fixed native class
callbacks, introduces no broad missing-macro default and suppresses no warning.
Actual CPP dependency manifests for every consumer in both normal and analyzer
builds must select the derived USB header. The timer port must also compile its
reviewed actual clock header. Negative gate tests reject selecting the original
USB header, selecting it only in the analyzer build, omitting the clock header
or having no actual USB config consumer.

The probe has one forced strong rejecting `_sbrk` owner. It excludes native
sysmem from compilation, retains the original zero heap linker reservation and
physical regions, and introduces no Ground/radio/platform business payload.
The first probe attempt failed on a header-owner lookup, the second on a duplicate
no-heap source entry, and the third compiled successfully but failed the unchanged
Power-of-Ten preprocessing policy. All of those attempts and early Host compiler
failures remain recorded. The final source graph has unique C/ASM object paths;
no gate threshold, source coverage, warning policy or exception was enlarged.

The final fresh 13d output records 303 successful real ARM compiler/tool commands,
48 C sources plus one startup assembly source, zero compiler warnings, 43
generated-file hashes and 495 build-artifact hashes. It includes normal and
`-fanalyzer` compilation/linking, saved-assembler CPP/GAS dependency closure,
Cortex-M4/FPU/float ABI checks, the independent full IRQ inventory including the
final no-comma FPU enumerator, real vector entries and physical section bounds.
Retained library members have archive identities and positive-size linked
sections; loaded/discarded members are not represented as retained code. This
does not prove their complete recursion, indirect-call, stack or timing bounds.

The generated `power10-check` command and script were run exactly as emitted.
The text scope is six first-party C files and 22 functions: 109 checks, three
eligible runtime candidates and ten nonblocking recommendations. The whole-function
average is informational; critical-contract review explicitly reports NOT PROVEN.
Imported/derived native vendor sources remain outside the existing text scanner's
scope. Entry hooks, timer/HAL derivatives and fixed USB callback/static allocation
exceptions therefore need explicit manual semantic acceptance. The private probe's
generic Ground `host` target deliberately exits one with NOT PROVEN because it has
no Ground Host program. Dedicated tests instead compile and run the actual native
timer bodies and owned counter port against Host MMIO/HAL mocks, with unchanged
normal and fault expectations. They establish no physical timer recovery or
complete Ground Host acceptance.

The final native regression suite has 187 passes in 283.76 seconds with no skips.
Thirteen separately recorded final timer Host fixture executions preserve four
expected original assertion failures, the unchanged original ordinary HAL error
returns, six corrected normal/fault outcomes and the counter-port fault program.
Their exact commands, exit codes, source/executable hashes and diagnostics are
saved independently of the suite summary. Earlier 181-pass and targeted 17-pass
runs keep their earlier source scopes and are not combined into another pass.

The final source snapshot, all test outcomes and intermediate failures, exact
commands, tool versions, configuration, normal/analyzer artifact inventory and
ordinary local review findings are preserved in
[the evidence manifest](evidence/native_classic_cdc_timer_20261010/verification.json).
The evidence addition is later than the compiled dirty snapshot based on the F103
checkpoint; no result is attributed to a later unexecuted firmware revision.
The existing pytest cache_dir configuration warning is retained.

The minimum next runtime work is a separately reviewed F407 indexed CDC class/LL
and data lifecycle contract, plus proof of timer initialization/reinitialization
sequencing and bounded IRQ latency. No shared EP0 patch is integrated. The b66
independent EP0 review was interrupted by platform safety, has no outcome and was
not retried. Full EP0/asynchronous lifecycle, complete source/caller contracts,
library/indirect-call stack, main/MSP/ISR nesting, STM32 WCET and hardware/flight
qualification remain NOT PROVEN. Ordinary local review of this increment is not
an independent review or critical-contract acceptance. Neither original Power
of Ten compliance nor NASA certification nor generic native runtime usability
is claimed.
