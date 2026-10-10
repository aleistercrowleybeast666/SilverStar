from pathlib import Path
import json
work=Path(__file__).resolve().parent;root=Path('D:/python_software/SilverStar/.work/ccdi')
manifest=json.loads((work/'evidence-package/verification.json').read_text());code=manifest['code_commit']
dest=work/'report-updates';dest.mkdir(exist_ok=True)
summary=f'''2026-10-10 后端普通功能交接结果（北京时间 05:20 前完成验证）

完整 F407/TIM1 单 FS classic CDC 私有 Ground 集成候选已实现并隔离提交：
`{code}`，分支 `feature/scg-classic-cdc-contract-20261009`。
这是普通功能与构建候选。普通生成入口仍阻断，未交付通用可用后端，未做正式放行。

已修复独审 P2：UIF 前后均为零时允许合法 CNT=0，保留三次有界采样、实际配置检查、
UIF pending 拒绝、单调性和有界进展检测。独审提供的原模型复放为旧口 `5/5/5`、
修复口 `0/0/0`；该模型的 0.2us 采样设定不是真实 MCU 延迟测量。
P3 已由接手前提交 `05e20169240ec812c988af1017cffc495319ec3c` 补齐两项 F103 证据，
本轮重新核对原清单全部 {manifest['p3']['all_f103_prior_manifest_files_checked']} 个文件及其哈希。

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
`cache_dir` 配置 warning 保留。所有 {manifest['ordinary_tests']['host_subprocess_commands']} 次 Host 子命令、退出值、
输出、输入/产物哈希已记录，其中 {manifest['ordinary_tests']['expected_original_program_nonzero_exits']} 次旧实现非零退出是
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

'''
runtime=(root/'apps/SCG/docs/NATIVE_CLASSIC_CDC_RUNTIME_20261010.md').read_text(encoding='utf-8')
(dest/'NATIVE_CLASSIC_CDC_RUNTIME_20261010.md').write_text(summary+runtime,encoding='utf-8',newline='\n')
timer=(root/'apps/SCG/docs/NATIVE_CLASSIC_CDC_TIMER_20261010.md').read_text(encoding='utf-8')
timer_update=f'''2026-10-10 TIM1 普通功能收敛

独审 P2（合法 CNT=0 误拒绝）已修复，代码提交 `{code}`。
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

'''
(dest/'NATIVE_CLASSIC_CDC_TIMER_20261010.md').write_text(timer_update+timer,encoding='utf-8',newline='\n')
print(code,'report updates prepared')
