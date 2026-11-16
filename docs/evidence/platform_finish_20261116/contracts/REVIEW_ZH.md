# 2026-11-16/17：限定关键合同复核

基线 `d52854c4a7b12c79dbb06cf967006e599103d24e`。本目录不是全固件安全认证，
也不把旧报告的“所有第一方/第三方关键语义 NOT PROVEN”改写成 PASS。
本次只对下表写明的边界给出源码、调用者、故障和实际构建证据。
后续无线 reader 修改有独立来源；构型 A/B 只证明修改 reader 前的字节，不能代替最终构型。
reader 的原始三失败和 240 项通过分别保留在
[修复前](../radio/reader-prefail.log)、[修复后](../radio/e19-post.log)，复制来源和 SHA 见
[reader-log-copy.json](../radio/reader-log-copy.json)。该业务证据与本目录的完整编译/栈证据分开。

| 有限合同 | 核对边界及结果 | 当前软件证据 |
|---|---|---|
| Logger 完成报告发布 | `LoggerTask_StartupReportWrite` 原来在验证 count/布尔域前发第一条 SELF_TEST_COMPLETE；损坏状态可能已部分发布。新容量上界与 completed/passed 域检查位于首次序列/缓冲修改之前；不是断言设备全部成功 | 旧真实 owning TU 的三种损坏用例 3 failed / 5 passed；相同期待下修复 8 passed。NULL、未完成、设备失败和 sink I/O 失败仍走原来普通路径 |
| Source selector 选择及就绪 | 核对 IMU/GNSS/telemetry count/order/candidate/result、失败候选不得重启成成功、异步停止保持推进；GNSS active/position 在同一锁内发布。只审这些入口，不把所有设备驱动错误语义一并接受 | 新执行原 41 个正常/损坏/超时测试；实际生成 source_selector Host 389 checks，日志全部保留 |
| Mission 状态、事件和运行时错误传播 | 状态 getter 的阶段计数、布尔域、ready 位、终止时间及事件顺序在同锁内校验；配置错误不写调用者。Runtime 仅 Unavailable 表示排空；动作失败立即 FAULT；日志 FULL/BUSY/BAD_STATE 保留游标有界重试，其余错误 FAULT | 新执行 13 个原状态/窗口测试；独立对 B 实际生成的 runtime 以原十个未改测试体运行，含真实 GCC `-fanalyzer`。旧修复前结果仍在 software_completion_20261101/critical，未改日期/结论 |
| SPSC 元数据及发布 | Push/Pop 的容量、各自 cursor 和无符号序号距离先于 memcpy；FULL/EMPTY 仍普通结果。实际 LoggerBus 的两块数组尺寸与 slot/depth 一致，push/pop/排他 reset 用既有 IRQ 锁；Count 只作有界快照，不当预留。该 volatile/fence API 不声称可移植的 C 多线程队列 | 原 navigation/queue 20 项本轮执行，其中六项直接覆盖队列元数据/正常路径；实际生成 logger Host 含非 2 次幂容量及序号回卷，2,106,422 checks。未把 Host 的执行时间当 MCU 时序 |
| 增广估计器生成依赖 | ESKF20/InEKF15/InEKF20 依赖 augmented.common，`navigation_journal.c` 无条件消费 LoggerBus/SSLOG；logging=None 的旧工程校验能通过，随后 ARM 缺头失败。新校验与直接 source-graph 入口都精确拒绝不支持组合，在输出写入前结束，模型不变 | 新负例旧代码 3 failed / 4 passed；修复后相同七项进入 125/159 项通过组。KF6 日志开关未被强制开启；数学 C、参数 ABI、TreeDiagram SDK 均未修改 |

## Logger 所有权与失效行为

本次只增加六行 owning payload C。`SystemStartup_Run` 在调度前初始化；
正常 DeviceTask 调用 `SystemStartup_ProcessDevices` 构造报告；Finalize 写完字段后发布
completed，Complete 分支不再改报告。F407 实际 Release 的 Finalize 反汇编中，timestamp
STRD 后才写 offset21 的 completed；并非只凭源码注释推断当前编译结果。
Logger 对不可用的报告返回等待；合法 `passed=0` 继续序列化真实设备失败；
I/O 失败继续既有锁存错误，不能被改成“设备失败即 fatal”。

新检查允许 `device_count <= SYSTEM_STARTUP_DEVICE_COUNT`，不强制等于容量。
旧超量 count 的前失败测试在第一条事件触发预设 sink 失败并停止，已观察到不应有的发布，
没有借助真正的越界 Host 访问。完成标志和 passed 域损坏旧版实际写出记录且未触发故障。
新夹具包括整个 logger TU、真实 codec/decoder 与真实断言 fault record；仅外设、时间、
报告来源和最终 trap 在 Host 替换。setjmp/longjmp 只用于检查终止后状态，不进入 MCU。
它不证明任意 RAM 损坏、指针篡改、任意运行中 report reset 或跨内核可见性安全。

## 栈分析新增能力及拒绝边界

Flight `StackGraph_Load` 继续选择原完整 source graph、目标及配置。共享
`StackGraph_LoadInputs` 只构造真实 `.su` 和 ELF 图；它本身从不输出准入 PASS。
根 build 及子目录可作为输入，外部目录、缺源、缺 `.su`、重复/绝对/穿越源路径均拒绝。
Ground 必须另以完整 Make/source graph、每个对象与工具链封印证明覆盖；不得只传一个
方便的源子集。Ground adapter 与新板的完整结果由 boards 报告独立负责。

实际 C071 ELF 暴露两种 Thumb-1 switch 和一种 split POP/BX 返回路径；旧解析器
13 项真实机器码夹具全部拒绝。本次按以下条件补齐，而不是按函数名排除：

* `__gnu_thumb1_case_uqi` 必须匹配实际九条指令/位置/宽度；调用处必须有支配整个地址序列的
  范围检查；表的每个字节、完整目标集合及本函数指令边界全部验证。真实 helper 的 4-byte
  栈帧仍保留为调用边，不把它当零开销。
* `MOV pc,Rn` 绝对表验证实际 shift/index/base/literal、范围和所有目标。
  表来自同一 ELF；`.rodata` 必须具备 CONTENTS/ALLOC/LOAD/READONLY/DATA，且完整字节范围
  与 section header 一致。MOV PC 按 Arm 语义清最低地址位，不套用 BX 的状态切换规则。
* split POP/BX 必须恢复 entry prologue 保存 LR 的同一栈槽，所有 CFG 路径的 SP 高度一致，
  中间没有旁路、目标寄存器改写、未知 SP 操作或可见的该槽直接覆盖，最终 SP 为入口值。
  其证明范围与普通 `POP {pc}` 相同：ABI 控制/栈形状；不声称任意指针写入的内存安全。
* 缺 guard、错误索引、旁路、缺表字节、越界目标、变更 helper/base、错 LR 槽、寄存器写入、
  直接槽覆盖、未知 SP、可写或不完整 section 都有拒绝用例。原 recursion、动态帧、
  非法间接调用、库归属、完整编译输入及每个真实产物的门槛没有降低。

依据：[GCC lib1funcs.S](https://github.com/gcc-mirror/gcc/blob/releases/gcc-14.3.0/libgcc/config/arm/lib1funcs.S)、
[Arm Cortex-M0+ Generic User Guide](https://documentation-service.arm.com/static/5f04aadfdbdee951c1cdc957)、
[AAPCS32](https://github.com/ARM-software/abi-aa/blob/main/aapcs32/aapcs32.rst)。
验收依据仍是本机实际 Arm GNU 14.3.Rel1 ELF/库及原始 bytes，不能拿文档版本替换实际机器码。

## 明确仍未证明的范围

全固件每个第一方/第三方函数的语义、任意外部缓冲区别名/生命周期、所有库异常路径和
所有受支持配置仍未完成穷举人工审计。本轮只有上述有限合同及精确 sealed 构型可以给出结论。
Power10 原样继续输出 critical-contract review NOT PROVEN，启发式推荐不能被写成认证。
HAL/FreeRTOS/FatFs/libgcc 等第三方仍按实际 source graph 和完整工具链/对象封印计入栈；
没有把其原规则差异删掉，也没有增宽例外。

真实任务/ISR 时序、MCU WCET、高水位、物理 UART/RF、DMA/cache、断电与重启读回、
同步接线、传感器精度和飞行资格需要硬件。严格静态栈通过只证明对应字节下保守软件界限；
RAM/CCM 余量、Host checks 数量、Host 耗时均不能补足这些硬件证据。
