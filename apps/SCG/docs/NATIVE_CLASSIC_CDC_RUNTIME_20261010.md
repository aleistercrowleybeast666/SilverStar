2026-10-10 后端普通功能交接结果（北京时间 05:20 前完成验证）

完整 F407/TIM1 单 FS classic CDC 私有 Ground 集成候选已实现并隔离提交：
`9f115f087f12868dd8a5384ca0b1e78edace63e0`，分支 `feature/scg-classic-cdc-contract-20261009`。
这是普通功能与构建候选。普通生成入口仍阻断，未交付通用可用后端，未做正式放行。

已修复独审 P2：UIF 前后均为零时允许合法 CNT=0，保留三次有界采样、实际配置检查、
UIF pending 拒绝、单调性和有界进展检测。独审提供的原模型复放为旧口 `5/5/5`、
修复口 `0/0/0`；该模型的 0.2us 采样设定不是真实 MCU 延迟测量。
P3 已由接手前提交 `05e20169240ec812c988af1017cffc495319ec3c` 补齐两项 F103 证据，
本轮重新核对原清单全部 225 个文件及其哈希。

HAL_Init 与 SystemClock_Config 保持原生次序。TIM1 在两次原生启动时钟配置中先关闭
唯一共享 IRQ、停止/清理旧计时配置和 pending，再初始化、清 pending、启动和启用 IRQ。
实际 HAL_Init/HAL_RCC_ClockConfig 的派生调用者传播 InitTick 错误，main 保留返回检查；
主时钟所有者初始化以后，以及 ISR/PRIMASK 上下文中的重配被拒绝并锁存故障。
私有口仅接受已核对工程的 DIV1 复位相位与 DIV2 最终相位；其他配置拒绝。
这证明软件次序与错误路径，不证明硬件 IRQ 延迟或计时裕量。

F103 有界队列、session、GSP/Ground、已验证 SX1281/M12 和 SPI/GPIO 适配被复用于
F407 原生 indexed CDC ABI。静态单类槽、固定 FS endpoint/FIFO、原生 HAL/CMSIS、
startup、linker、clock、GPIO、IRQ、PCD 与 middleware 所有者均保留；原件不变，
需要修正的已知所有者使用可回放派生与明确源图替换。未知 source/config 拒绝。
同时修复普通初始化中的存储故障锁漏检，防止 Ground 初始化后仍误返回成功。

联合 Host 数据路径实际执行生成的 CDC class、应用回调、PC queue/session、GSP 和
Ground bridge，验证合法 PC→radio、radio→PC、TX 保留/完成、RX rearm、正常
DeInit/Init 重连及旧 session 拒绝。PCD/radio 和已经 READY 的外部运行时在该联合
测试中为 mocks；真实 runtime 初始化/故障、HAL boot caller、timer、LL/FIFO 返回另有
实际函数体 Host 测试。不能把分段/联合 Host 模型视为物理 USB 异步生命周期验收。

| 最终 fresh 14e 记录 | F103 回归 | F407 完整私有 Ground |
|---|---:|---:|
| 实际编译/工具命令 | 333 | 387 |
| C 源 / startup ASM | 53 / 1 | 62 / 1 |
| 编译警告 | 0 | 0 |
| generated 文件哈希 | 114 | 124 |
| build artifact 哈希复核 | 545 | 635 |
| architecture / Host / artifact / 原样 PoT 命令 | 全部 exit 0 | 全部 exit 0 |
| generated Host 程序 | 5 | 5 |
| PoT 文本检查 / first-party 函数 | 507 / 179 | 511 / 181 |
| assertion 建议（非阻断） | 48 | 49 |

最终一次明确普通范围 suite：154 passed，0 skipped，162.05s；现有 pytest
`cache_dir` 配置 warning 保留。所有 294 次 Host 子命令、退出值、
输出、输入/产物哈希已记录，其中 16 次旧实现非零退出是
原失败复现的预期结果。未拼接成未执行的全套或 whole-monorepo PASS。
正常及 analyzer 的实际对象/ELF CPU/FPU/ABI、真实 vector、独立 SDK 完整 IRQn
（含 F407 最末 FPU_IRQn）、已选 clock/USB config CPP 依赖及 strong timer owners 均已核对。
PoT 文本 PASS 的语义 critical-contract review 仍明确 NOT PROVEN。

构建使用基于 05e2016 的 dirty 源快照；逐文件审计证明它与上述代码提交一致
（Git/Windows 仅换行规范化差异），最终普通 suite 在上述代码提交运行。
报告/证据是随后归档，未把结果归属于未执行的后续固件修订。
完整命令、版本、失败尝试、原模型、精确源档、ELF/map/stack 原始报告、清单与哈希见
[本轮证据](evidence/native_classic_cdc_ground_f407_20261010/verification.json)。
完整原生 vendor 输入和完整对象仍位于 receipt 声明的 C 盘隔离输出；归档不重复复制 vendor。

没有集成共享 EP0 修复。b66 的独立安全审查被平台机制中止，没有审查结果，没有重试，
本轮没有运行畸形 USB、owner 表达式研究或该受阻审查。class Setup/EP0 RxReady 只做
文本字节保留核对，不构成审查或接受。EP0/完整异步生命周期、手工 critical-contract
接受、library/indirect-call/recursion、MSP/ISR 嵌套栈、WCET、IRQ 延迟和硬件时序均
NOT PROVEN；这些仍阻止普通入口正式放行。不声称原始 PoT 合规或 NASA 认证。

全程无 DAPLink、串口、烧录或 START。日用 HEAD 仍是 56448bd，GUI、FINAL 与三项
原有用户 untracked 文件未改，没有 push/merge。父线程阶段消息返回 thread not found，
因此阶段说明保留在当前任务，最终结果通过平台完成通知交付。

---

下面是保留的历史 checkpoint 记录；其中对 F407 的限制属于当时版本。

This isolated increment builds a private F103 Ground candidate from the
reviewed complete native source profile: one FS CDC transport, one bare M12
SX1281, actual native clock/startup/linker/USB/HAL/GPIO owners, and no RTOS or
extra LED owners. Normal `GroundFiles_Render` still rejects the capability
marker. No user project, daily branch, GUI, FINAL candidate or board is changed.

The native runtime gates publication until clock/platform/bridge initialization
and the driver's coherent verified-chip postcondition all succeed. A fresh
unmasked clock-progress probe precedes each PC publication. Unknown bridge
results fail closed. Clock and initialization faults reset PC sessions, stop
USB, retire the started radio, hold radio RESET even before platform success,
and retain a permanent fault. Radio/PC transient errors keep ordinary diagnostic
paths; this internal publication state does not substitute for protocol READY.

The radio main owner now samples seven stored timestamps before its existing
critical sections. Its wake-up SPI/Busy operations keep tick/USB IRQs live;
the native DIO ISR only latches a flag. A complete control result is constructed
locally and published under the same lock on timeout and normal completion.
No density assertions, threshold changes or new gate exemptions were added.

Known HAL source derivatives retain the original licensed input and replayable
patches. Used SPI polling paths gain finite bounds while preserving ordinary
timeouts/unlocking; the UART alternate data pointer is checked before access.
The original `_sbrk` is excluded from compilation and a forced strong rejecting
ABI is linked. The normal and analyzer ELFs have no retained dynamic allocation
entry points. Static USB class storage and fixed native ST callbacks remain
controlled vendor exceptions; they are not an authorization for a heap or
runtime callback registry.

The separate CDC bulk derivative checks class initialization, endpoint opening,
application initialization, TX, RX rearming, packet bounds and cleanup results.
An ambiguous LL/close failure retains TX/class ownership, cancels publication
and prevents false successful reinitialization. LL initialization and actual
core/data-stage return paths propagate failure. Original inputs, derived owners,
same-path patches and immutable-byte manifests identify every replacement.

No shared EP0 patch is integrated. Class Setup and EP0 RxReady functions are
byte-identical to the native input, verified as preservation only. The b66 EP0
independent review was interrupted by platform safety; it has no review outcome
and was not retried. Reset/control/complete asynchronous lifecycle acceptance
remains NOT PROVEN. This private compiled candidate is separated from that
unreviewed dependency by the normal generation block and explicit metadata.

The final generated directory and verification manifest record one auditable
source snapshot based on 7c6ae5653c4b9696d9da80a20df5297a92b2deb0. Real GCC ARM
compilation, saved-assembler CPP/GAS dependency closure, normal and `-fanalyzer`
linking, object/ELF attributes, independent IRQ positions and physical section
bounds were executed. Artifact checks rehash both generated files and build
artifacts. Retained library members are taken only from positive-size sections
in physical memory; paths containing spaces and archive digests are preserved,
and loaded/discarded members or wildcard selectors are not called linked code.

The generated Power-of-Ten command is unchanged and run exactly as emitted.
Its text scope is 18 first-party C files and 179 functions, with 507 checks,
126 syntactically eligible runtime candidates and 48 nonblocking recommendations.
Its semantic critical-contract review explicitly remains NOT PROVEN. The
existing text checker excludes imported/derived vendor owners: entry/class/LL
derivative contracts therefore still need explicit manual review. A text PASS
does not prove whole-firmware source coverage, recursion, checked returns,
assertion usefulness or acceptance of those controlled exceptions.

Full current native tests, existing Ground runtime regressions, generated Host
executables, pre-fix runtime failures and all intermediate compiler/test/gate
failures are saved separately in
[the evidence manifest](evidence/native_classic_cdc_runtime_20261010/verification.json).
The final 12c native suite had 164 passes in 241.23 seconds, and the separately
executed existing Ground runtime suite had 83 passes in 55.27 seconds. Neither
suite skipped a case. All five generated Host executables and the architecture,
artifact and unchanged Power-of-Ten commands exited zero. The fresh receipt
records 333 successful commands, zero compiler warnings, 113 generated-file
hashes and 545 build-artifact hashes, all rechecked before evidence copying.
The Host ports use MMIO/USB/radio mocks; terminal-trap interception in the Host
contract harness is test-only, never target recovery. The existing pytest
`cache_dir` configuration warning is retained. This is not a whole-monorepo pass.
Earlier missing `sd_sdio_fatfs_f1` fixture failure and older gate failures keep
their original scope and outcome.

F407 is still rejected for this runtime candidate. Its actual HAL TIM1 timebase
has no implemented native clock contract here; its distinct class/LL profile
also needs review. The earlier strict ABI probe reports missing
`USBD_CLASS_BOS_ENABLED` and `USBD_USER_REGISTER_CALLBACK`. No SysTick substitute,
invented clock, `-Wundef` suppression or new broad default was used.

Whole-program library/indirect-call stack bounds, task/MSP/ISR nesting, STM32
WCET, clock/SPI/radio waveforms and hardware/flight qualification remain NOT
PROVEN. No physical MCU recovery, timing margin or original Power-of-Ten/NASA
certification is claimed. Any failed or unresolved critical contract still
blocks normal publication. No independent review of this runtime increment has
been claimed.


Version note: this report retains its original snapshot scope. The later exact F103/C071 private runtime increment and shared F103 ordinary control integration are recorded in [NATIVE_USB_FIRST_BATCH_RUNTIME_20261010.md](NATIVE_USB_FIRST_BATCH_RUNTIME_20261010.md), tested code `838f148059020b05d0de4a735332abf830f8b953`. Independent USB safety review still has NO PASSED OUTCOME; formal generation remains blocked.
