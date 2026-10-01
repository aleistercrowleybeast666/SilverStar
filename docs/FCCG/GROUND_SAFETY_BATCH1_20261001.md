# Ground 第一批源码安全修复（2026-10-01 白天续做）

本批源码提交为 `0e1e5e735914829d32a2f2de2264805f79a432e1`，从干净的 `a0e73d3` 开始。**原 Ground PoT 缺口 13→0；Flight 194→181，仍然 FAIL。** 未改检查器、门禁阈值、白名单或数学算法，未把未执行项目计为通过。此报告接续白天工作，夜间报告及冻结候选保留其原版本结论。

## 实际改动与故障响应

修改共用 `sx1281_device.c`、其公共头文件、原 Host 测试的可复用端口段，并新增可执行 C 故障 fixture 和 pytest 入口。实例参数在索引上下文前检查；仅转发调用的三个包装函数使用内部提交入口的边界检查，没有重复添加断言。无效实例属于生成上下文编号的编程错误，会进入真实故障记录和 fail-stop；正常的空指针、无效包长、队列满和事务参数错误仍使用原返回枚举。

两个环队列在 IRQ 锁内检查索引、计数容量及 `head == (tail + count) % depth`，出队在复制前检查已存包长。损坏的控制操作、状态、ID、超时及自动释放标记，在无线操作分派前拒绝。预期 CRC/header 错误和无线超时不视为断言故障。

确认并修复了真实初始化缺陷：成功初始化后的再次初始化失败，旧代码可能保留 `initialized=1`，继续接受发送。现在在 IRQ 锁内一次清空所拥有的整个上下文，再加载默认调制/包配置；芯片/端口失败保持未初始化，后续正确初始化可恢复正常发送。完整上下文复位也避免未来新增字段漏复位。该初始化函数本身变得简短，未添加恒真后置断言以凑数；没有改小函数的门禁规则。完整清零的临界区是有限的，但其目标执行耗时未测。

| 原 13 项函数 | 实际合同或处理 |
|---|---|
| `Lora_DiagRecordIrq` | 实例边界、无线状态枚举范围，防止错误超时分类 |
| `Lora_ClearRuntimeState` | 实例边界、整个拥有上下文的原子复位；真实简化后少于门禁的 20 行阈值 |
| `Lora_TryStartNextTx` | 实例、初始化/忙标记范围，出队环状态与已存包长检查后才发送 |
| `Lora_Init` | 实例边界、禁止活动控制事务中重新初始化；失败不保留 READY |
| `Lora_StartRx` | 实例边界、LoRa 包参数的类型标签，防止错误联合体配置 |
| `Lora_IrqProcess` | 实例边界、忙标记范围；CRC/header/timeout 仍为正常事件 |
| `Lora_RawIrqProcess` | 实例边界、决定轮询与超时方向的忙标记范围 |
| `Lora_DiagnosticsRefresh` | 实例边界、已初始化前置条件，防止未配置端口访问 |
| `Lora_RxCompletionProcess` | 实例、完成标记范围及底层成功返回的包长上限 |
| `Lora_RxErrorProcess` | 实例、错误/超时标记范围及有错误时的合法错误码 |
| `Lora_Process` | 实例与初始化标记范围；不将损坏的标记当 READY |
| `Lora_ForceRxContinuousDirect` | 实例、LoRa 参数类型，在硬件操作与清标记前检查 |
| `Lora_ControlProcess` | 实例、状态枚举、操作枚举、非零 ID/超时和布尔自动释放标记 |

## 验证与版本

- **修改前复现：**相同入口的初始化失败、TX 头越界、RX 尾越界和控制操作损坏四项均失败；原始日志 `BASELINE_FOUR_FAILURES.log` 保留。最初 fixture 的两次编译问题属于测试 harness，修正后才得到这四项产品/防护失败，未将编译失败冒充产品复现。
- **最终源码专项：**26 个无线正常/故障场景，加 4 个既有 Ground 桥接/PC UART DMA/USB 环测试，合计 **30 PASS**。包含芯片与端口失败后禁用/恢复、双实例隔离、队列满/优先入队/四轮环绕、uint32 时间回绕及正常 CRC/header/timeout。故障场景执行真实驱动、断言判定和故障记录；只把最终 trap 换为 Host 的 `longjmp`，读取真实模块/原因/行号，检查故障后的队列/输出未写入、无线发送/启动计数未增加。这不是 MCU 从 fail-stop 恢复的证明。
- **原 Ground PoT：PASS，退出 0。**460 checks、15 个目录扫描第一方 C 文件、148 个函数，剩余缺口 0。
- **实际 Ground 静态分析：PASS。**原生成图中 14 个选中第一方源逐文件用 ARM GCC `-fanalyzer -c`、原 MCU/优化/严格告警编译到独立对象。分析器 double-free 反例以 `-Werror=analyzer-double-free` 正确退出 1，14 个产品文件均退出 0。早先包含 `-fsyntax-only` 的调用仅记语法检查，不计为分析器执行。
- **最终源码完整 Host：PASS。**正式生成工程 `host-tests` 运行 72 个可执行程序、4,393,820 checks、0 failures，8 个编译正例、16 个预期编译拒绝。更新协调期间一份 Host 日志在第 30 项中断且未留退出码；确认相关进程已不存在后，仅补跑未完成检查。部分日志保留，未与完整结果拼接。两份已完成 ARM 构建未重复启动。
- **ARM 构建：两份新生成工程均退出 0。**Ground 为 F103 Cortex-M3/soft float/`-Os`；Flight 为 F407 Cortex-M4F/hard float/Release `-O2`。工具链 GCC 14.3.1 20250623。Flight 的正式架构、产物与静态任务栈检查也退出 0。没有运行本批 Flight 全源 `static-analysis`，Ground 分析结果不替代它。
- **原 Flight PoT：FAIL，181 个缺口，make 退出 2。**共用无线驱动的 13 项已移除；剩余导航/缓冲/存储/调度等项尚待下一批逐项处理。没有重跑整组 FCCG 688/FLP 521，本批结果不替代夜间完整回归。

新工程可从以下独立目录打开，旧候选未覆盖：

`D:\stm32_project\SS_0_5_TEST_4_versions\GroundSafety_0e1e5e7_20261001\ExistingHardware\SilverStar.ssproject`

它是**第一批验证候选**，不是 Flight 全门禁完成的最终版本。本批只生成已有硬件路线的 Flight/Ground；导入硬件路线本批未重建。旧 `FinalCandidate_ddb73bb_20261001`、原 `SS_0_5_TEST_4`、`FrozenRound5` 和夜间四编译保持历史身份，不计到新提交。

版本目录的 `BATCH1_BUILD_MANIFEST.json` 记录源码提交、配置哈希、精确命令/版本/退出码及 ELF/MAP/BIN/HEX/decoder 哈希。新的 decoder 与原 ddb73bb ExistingHardware decoder **字节完全相同**（聚合仍为 2）；仅无线防护变化，没有修改数学、日志格式或 decoder 契约。本批未新增实录回放/数值一致性验收。

| 产物 | SHA256 |
|---|---|
| Ground ELF | `a69abfea841214951dcf2879bded87f7b43f2b9c8aadb715dcb1ba95652a350b` |
| Flight ELF | `282cb29739c974ceeaa2c77956f0cb86d183b8d7960cf7b414699e7de2561ee7` |
| 实际生成 decoder | `63673624043bfb1064cb6645b8b13837a42c91ea7085162844f035c0d0b217e6` |

## RAM 证据及边界

| 本批实际配置 | Flash（text+data） | Main SRAM | CCMRAM | 容量余量 |
|---|---:|---:|---:|---|
| F103 Ground | 21896 B | 节之和 14124 B；含对齐孔的占用末端 14128 B | 无 | 64 KiB Flash；20 KiB SRAM，保守余 6352 B |
| F407 KF6 Flight | 314748 B | 101280 B | 55432 B | Flash 209540 B、Main 29792 B、CCM 10104 B |

Ground 的 14128 B 已含 1024 B MSP 预留与对齐，不能再把这 1024 B 算一次。Ground 为裸机循环；Flight 静态任务栈共 27648 B，已包含于 CCM 占用。两个 ELF 都未出现 `malloc/_malloc_r/calloc/realloc/pvPortMalloc` 分配入口，链接 heap=0；Flight 配置为静态分配开、动态分配关。此结论只适用于这两个实际链接配置。

本批 Flight task budget 用 152 个 `.su` 和同一 ELF 的反汇编，累加直接调用/跨函数分支，对无 `.su` 的库/汇编累计已知栈操作；未知间接调用、递归、动态栈或未解释 SP 写入在该分析器覆盖的任务路径上失败关闭。每任务另含 256 B 上下文，静态余量分别为 Device432、INS832、Estimator852、Flight496、Logger968、Serial1200、Telemetry1960、Idle256 B。它是已建模路径的静态预算，不是板上高水位。

MSP 仍仅有 1024 B 预留；本批没有证明主循环/启动链与所有可嵌套 ISR 的合成上界。Ground 的单函数 `.su`（如 `Lora_Process`、出队/库调用）也不是整个 MSP 上界。DMA 缓冲的源属性和 Flight `.dma_bss` 地址已按正式产物检查落在 Main SRAM；CCM 是 CPU 数据域，不能拿 CCM 余量补 DMA 或 Main SRAM。插件新增的 DMA 指针别名、未建模 ISR/回调/库路径和实机栈水位仍需独立验证。

因此，**PoT PASS 加链接余量不能直接推出完整内存安全或实时安全**：本批队列负例在仍有大量 RAM 余量时也能触发越界/错误分派风险，空余 RAM 不会让错误索引变正确。断言提供明确合同与故障停机，不能代替其余代码的边界/并发审查。没有执行周期测量，未建立主频下限或飞行资格。历史 ESKF15 日志配置 CCM 仅余 1240 B；本批没有新链接 ESKF，不能把当前 KF6 的 10104 B 余量套给 ESKF，也没有删诊断或栈保护。

## 命名、剩余项和运行状态

当前仍有根入口 `FCCG.py`、包入口 `silverstar-fccg`、产品名 `SilverStar_FCCG`，未找到独立 `SCG.py` 或正式 SCG 应用入口。界面字符串是“SilverStar 飞控与地面站代码生成器” / “SilverStar Flight & Ground Code Generator”；本批读源码核对，没有新开 GUI 窗口验标题，也没有执行改名。历史 SCG 五检查称呼只是夜间报告对用户术语的映射，不证明发生过改名。

下一批优先处理 Flight 剩余 181 项的高风险合同，并运行相应故障测试与新构建；整体软件全套、导入路线最终构建、完整 MSP/ISR 上界、实机栈与周期、步行实录逐点一致性仍未完成。早期 Windows 访问违规仍未解释；本批没有新增原生 GUI 回归。Python 3.7.5 卸载继续后置。

用户新增弹窗回忆：“某个命令引用了某个内存，内存不可写”，目标低地址末尾近 `0x00…0B0`，指令地址未知；该地址未精确确认，不能反推 native frame/module/offset。只核对既存本任务日志 `apps/FCCG/.work/night_20260930/pytest_p0_4.log` 和原验收事件查询结论：日志记录访问违规及规划 worker 的资源扫描 Python 栈，原窄时间查询未找到匹配 Application 事件；PID6980/22116 等保存的 -1 是主动结束码，不是自然崩溃码。该回忆与哪一次弹框同源仍未知，也不能等同旧初对准 sender 销毁的 SIGSEGV。未扫描其他应用事件或伪造 dump。

## 手持步行采集前清单

1. **已解除的软件项：**Ground 原 13 项覆盖缺口、本批初始化失败残留 READY、实例/环状态/包长/控制分派防护已处理并通过上述软件验证。实际导航、日志格式与聚合 2 decoder 未改；本批不是新实机验收。
2. **用户已安排的待验：**本批未刷写，板上固件版本未知。用户外场前自行选择并上板测试版本，核对实际 IMU/GNSS/坐标轴、初对准、无线/PC 端口、存储写入和所选导航/日志配置；以真实 SSLOG、该固件匹配 decoder/Descriptor 读回验证记录导航及轨迹。无需重复催促用户；仍保持无执行器的手持采集范围。
3. **后续软件残余：**Flight 181 项是静态合同覆盖缺口，不等于 181 个已经复现的运行 bug；旧 GUI 访问违规未解释、最终本批全软件套件和导入路线尚未重验。ESKF 的历史窄 CCM 余量不能套给本批 KF6。当前生成/编译和既有聚合 2 FLP 路径没有证明存在阻止基本查看的硬阻断，但这些软件 PASS 不能替代用户上板与真实日志确认，也不能证明导航精度或飞行合格。

最新可信用户额度 77%（02:40 UTC），动态读数未知；未启动其他模型。桌面更新已由用户取消，未更新/重启。未推送、发布、刷写或执行任何硬件操作，未操作网站 Cloud/ToDesk/水母；其他应用未保存状态未知。

完整本批证据见 [证据索引](evidence_ground_safety_20261001/INDEX.json)。所有证据仅是软件/Host/交叉编译，不是实机验收。
