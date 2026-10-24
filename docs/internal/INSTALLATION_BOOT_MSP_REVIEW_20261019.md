# 启动 MSP 与安装采集输入审查（2026-10-19，v8）

本次把 v7 的启动粗包络 **1268 B** 按实际初始化时序拆开。当前 v6 F407 Release 的
条件 MSP 上界为 **844 / 1024 B，模型余量 180 B**；不需要扩大 MSP，也未缩小任何任务栈或借用保留区。
该数字是确切 ELF、复位启动和已列出回调模型下的静态界，**不是硬件测量或全固件安全验收**。

开发分支 `feature/usb-transport-0.1.3-20261013`，HEAD
`7896c1d09a7f9138c41cdac35beef38347d94b78`，保留原脏工作树。
复用的 ELF SHA-256 为 `a972ed93ed27870f7385b5c88861591f9ff79bf5cbf131c0329782182df25b91`。
本次未改固件 C/头、链接脚本或配置；只登记经过实质审查的 checker 输入身份，并相应更新历史门禁测试的版本号。

## 哪些栈不会同时存在

| 实际阶段 | 可达中断、屏蔽和栈存活范围 |
|---|---|
| Reset、构造器、早期 HAL | 空 preinit、唯一 frame_dummy 及其空 TM/弱 hook 沿用 v7 实际字节证明。HAL TIM1 timebase 先 EnableIRQ 再设优先级，所以存在短暂默认 priority 0 窗口；此时 GPIO 尚未初始化，其 16 B 软件链已覆盖。 |
| GPIO/DMA/UART 配置至应用初始化 | Group4。TIM1=15，EXTI=5。`MX_DMA_Init` 仅开时钟和 NVIC；UART 初始化没有打开 RXNE/IDLE/PE/ERR/TC 中断及 DMA 传输。`MX_SDIO_SD_Init` 只填 handle 字段，没有 `HAL_SD_Init`，SDIO NVIC=6 的使能也尚未发生。 |
| `SystemStartup_Run` | 只初始化时间、生命周期、健康、日志策略和安全输出，设置 Console 阶段后返回；串口接收、传感器启动在 Device 任务的 `SystemStartup_ProcessDevices` 中。TF/Card 初始化在 Logger 路径。已对实际 main 的调度前调用闭包检查：无 HAL_SD_Init、UART/DMA 传输启动或 Device processing。 |
| `AppTasks_Init` | 最深 main 链 564 B，来自 PendingEventsFlush→EventWrite→LoggerBus→队列/断言路径。日志入队最深子链受 PRIMASK=1 保护，但此次保守界**仍保留全部 564 B**，不依赖将其减成 532 B。 |
| 首次任务创建至首次 SVC | FreeRTOS `uxCriticalNesting` 初值 0xaaaaaaaa，成对 enter/exit 不会把 BASEPRI 清零；实际汇编使用 0x50。`vTaskStartScheduler` 在 running 标志置位前禁中断；RTOS 15 级 tick 与 main 深链不叠加。 |
| 切到首任务后 | 实际 port 重装 MSP、清 CONTROL，SVC 恢复 PSP，保留 32 B 基本 SVC 帧作为 MSP 基线。PSP 的 208 B 最大上下文仍在每任务 256 B 预留内。PendSV 的手写 MSP push 8 B 继续计入，未误算成 PSP 或漏在 .su=0 中。 |

早期 `SysTick_Handler` 在 scheduler 尚未启动时只调用无栈的状态查询并返回，软件开销 8 B，
不会执行 `xPortSysTickHandler` 的 64 B 运行期链。TIM1 的 16 B 已覆盖同级低优先级最大值。
所有这些结论都针对正常复位进入当前映像；不假定 bootloader/debugger 留下的外设状态已被审查。

## 浮点与异常帧

依据 [ST PM0214 §2.3.7、Figure 12](https://www.st.com/resource/en/programming_manual/dm00046982-stm32-cortexm4-mcus-and-mpus-programming-manual-stmicroelectronics.pdf)，
基本硬件帧 32 B，浮点扩展 72 B，另取每次最多 4 B 对齐。首层取 **108 B**，保留 lazy stacking 尚未写入但已预留的全部空间。

[ARM DAI0298A](https://support.arm.com/documentation/dai0298/a/) §1、§3 Figure 5
说明新 ISR 上下文清 FPCA；低层 ISR 不使用浮点时，嵌套层无需再预留浮点区。
已检查当前 ELF 早期 TIM1、EXTI、SysTick 提前返回、HardFault、NMI 的实际调用闭包：
无 VFP 指令、无 CONTROL 写入、无未解决间接调用；嵌套基本帧因此各取 **36 B**。
使用的是 ARM 原出版物文本的[镜像](https://www.scribd.com/document/665991744/DAI0298A-cortex-m4f-lazy-stacking-and-context-switching)，
官方门户可定位，但直接 PDF 下载未成功；未把第三方教程当架构依据。

| 静态包络 | 算式 | 字节 |
|---|---|---:|
| 调度前正常中断 | main564 + TIM16 + EXTI48 + 首层108 + 嵌套36 | **772** |
| 再含 HardFault、NMI 各一层 | 772 + 36 + 36 | **844** |
| BASEPRI 屏蔽阶段（MSP 重装前） | main564 + 故障首层108 + NMI36 | **708** |
| 任务运行期，沿用 v7 更宽的模型 | SVC32 + 低层96 + SDIO104 + 高层180 + 两个全扩展帧216 | **628** |
| 运行期再含两个全扩展故障帧 | 628 + 216 | **844** |

没有利用 tail-chain、PendSV 的 BASEPRI 作用窗口或更精细对齐扣减来获取额外余量。
HardFault/NMI 的当前终止循环没有软件帧；本界不覆盖任意内存破坏、压栈失败、故障锁死或 MCU 恢复。
运行期 HAL DMA/UART 字段取当前已链接函数中的保守目标并集，仍要求有效 handle/parent/生命周期；
没有把这个独立模型加入 checker 的新回调例外。改 ISR/FPU/优先级/启动方式后必须重新审查。

## 内存与输入身份门禁

链接脚本 RAM=128 KiB、CCM=64 KiB、`_estack=0x20020000`、`_Min_Stack_Size=0x400`、heap=0。
1024 B 是链接预算，不是 MPU 强制栈界。主区项目预算仍为 102292 / 102400 B，只有 108 B；
物理 SRAM 剩余 28780 B 不能直接拿来放宽项目策略。CCM 为 64896 / 65536 B，余 640 B；
八个任务的地址和分配合计 27648 B 未变。此次不扩大 MSP，因而没有新增内存方案或保留区冲突。

42 项现存但未登记的编译输入已进行实质审查，见
[输入审查记录](INSTALLATION_STACK_INPUT_REVIEW_20261019.md)。正式 v22 新增
42 个确切源码/头身份、20 个实际依赖图和 167 个完整配对闭包；AST 对照保留其余规则和 v2–v21 登记。
生成器核对时只发现 checker 文件哈希与 core payload digest 的预期 provenance 变化；其余生成文件和全部固件输入一致。
没有改变递归、动态帧、未知间接调用、库栈或 256 B 任务上下文/最小余量规则。

实际 `make stack-report` 退出 **0**，八个任务保持原配置，含上下文的估计/余量依次为
Device 2144/416、INS 2240/832、Estimator 3356/740、Flight 3648/448、Logger 1984/1088、
Serial 4504/1640、Telemetry 2184/1912、Idle 256/256 B。
**91 项**门禁/历史绑定/生成测试通过；未知源码、未知头、依赖图变化和单独已知旧头的混合配对四类负例全部拒绝。
全部命令及退出码见 `implementation/msp_boot_v8/gates/summary.json` 与完整 stdout/stderr。
新结果只属于 v22，不覆盖旧 `stack_gate_04` 退出 1。v6 的实际 ARM 编译/链接、15 TU analyzer、
CAL/ALIGN/MAG/TF Host 回归和 515+5 项相关 pytest 保持原日期、源码与范围；本次没有重新拼成一次“全套通过”。
本次 make 复用了相同 ELF，只重新导出 HEX/BIN 并执行栈报告；不能称作又一次 C 编译或 analyzer 运行。

## 留存与剩余限制

新增分析放在 `.work/dev013_installation_followup_20261019_v1/implementation/msp_boot_v8/`，
复用原工程、ELF 和反汇编；清单记录所有权、命令、版本、哈希及留存路径。未清理旧产物。
受保护外部候选未写入；默认 OFF、真实 BEGIN 源资格拒绝和 wire APPLY/SAVE 关闭均保持。
未触碰 GUI、暂停的 M9N INT32_MIN 任务、main/tag、推送或硬件。

仍为 **NOT PROVEN**：全固件关键契约接受、HAL 回调生命周期的完整形式化接受、目标机最小 SP/栈裕量与异常覆盖、
WCET、真实传感器原始帧/测量时间/启动身份、标定有效性和硬件/飞行资格。
MSP 模型已无先前的 244 B 数值超额，不能据此开放这些门禁。

连接阻碍：本地 urllib 向 `raw.githubusercontent.com` 下载 ARM PDF 时 DNS 失败（Errno11001），下载未发生，未重试。
网页工具读取原作者资料镜像和本地审查继续完成；不存在权限审查拒绝或待审批硬件动作。
