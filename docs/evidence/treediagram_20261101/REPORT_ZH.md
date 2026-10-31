# SilverStar 本轮实施与验证报告

本报告覆盖用户附件第 4–15 章，以及 TreeDiagram 参数包进入 SCG 的普通 GUI 入口。记录日期为 2026-11-01（Asia/Shanghai）。**这是软件实施和分范围验证，不是完整飞行验收、原版 Power of Ten 合规或硬件认证。** 未通过或未证明的部分见后文，不由其他通过项替代。

## 来源、提交与可追溯性

- 初始分支 `feature/usb-transport-0.1.3-20261013`，本地及远端代码基线 `aaef99f82f0d33617ae82353b0ac760123d56cc0`，初始存在 327 项工作区变更。没有回退这些工作。
- 相干代码整合提交 `4f701b4a7822302dc0f4ac858549f7cc7fa4ba0e` 延续并审阅已有实现，加入本轮确定的修复。完整暂存范围及唯一历史源码夹具 zip 的审查记录在 `code-stage-list.json`。根目录工作清单、未审阅旧证据、用户 AGENTS 修改没有夹带。
- 最终界面/旧工程迁移修复代码提交 `16b258b9f054d9141e3cb233796328c23338d124`，24路径逐文件审阅/hash见`final-code-stage-list.json`；H7存储owner第一代码提交`267e7ad4a5e1b1668dffb2873a89f205f968049c`由其负责人独立审阅。后续正向严格门禁覆盖为`362a4e4d`，整体ownership缺失的fail-closed修复为最终生产提交`09c057a67acfc10e3ff387a4a8821c8ee0e83b0c`。
- 后续算法证据提交 `a5be57c94d178a145852b884e656a636cb6cc96d`、`10e1eb3fd6b9a190946111d1a5a7572ef1965358` 只增加其他负责人的证据。TreeDiagram 数学 SDK 锁定代码提交 `4f701b4`；文档提交不冒充不同数学实现。
- 本目录 `firmware-v1/commands.json` 与 `bundle-firmware-v1/commands.json` 是实际执行命令、退出码和耗时。每个构型使用独立正常生成输出；生成后未修补其代码来伪装仓库修复。`*-retained/generated-inputs.json`、ELF/MAP 清单和正式 JSON 报告绑定各次实际输入与产物。原生候选的 `native-resources/*/compile-receipt.json` 包含真实编译/分析命令、输入 hash 与当时来源快照。
- 原始输入、日志、解码器、旧证据均保留，没有清理旧 `.work`。新生成空间与用途见 `INVENTORY.md`。无硬件访问、无设备动作、此子任务没有推送。H7完整软件证据已独立提交`b20927094f73ec902300b3d31b9612ef6dba6d38`；本目录及最终回导v3/v4将独立归档，公开紧凑副本以来源manifest记录实际证据提交。

## 实际交付的用户路径

SCG 保留三个工作页。硬件页双端并列，公共无线链路居中；“配置共享无线链路”打开同一个私有草稿，同时改两端模块、各自功率和公共 PHY。预设先展示字段变化，最终只发布一次；取消不发布。单目标未配置对端不阻断，已配置冲突仍需解决，旧 H/M0 迁移不能静默发生。

流程页以唯一功能实例为表格行，阶段为列。阶段弹窗只编辑条件和引用；参数按钮打开唯一实例的私有事务。嵌套子编辑应用后，父弹窗取消仍丢弃整个草稿。已修复待提交输入绑定在打开阶段事务时丢失的问题。共享库不再重复每阶段完整功能表单；同一参数 owner 只持有一份实际数值。

构建页展示每端真实配置与产物状态，生成、构建、产物检查为主操作，工程目录、工作区和清理位于折叠区域。未构建或身份不匹配时不显示旧 ELF 为当前成功。资源 JSON、CLI、GUI 共用当前产物身份检查。

功能参数导入入口同时支持原严格 `.ssparameters` / `.ssparams` 与 TreeDiagram `.sstuning.json`。完整读取、身份与 manifest 校验之后预览 owner、参数前后值和共享影响，再一次应用。PID/LQR 控制记录明确标注研究用途；它们的独立正常生成 C 数学配置验证见相邻 `treediagram_algorithms_20261101` 报告，不能推导已接入任务执行器。

最终真实回导以接收端09c057a6执行，见[参数回导v4](../treediagram_algorithms_20261101/v4/README.md)：三条实际tdrun重新核对身份，49+49+45共143/143标量与SCG目标、decoder及编译后C相同；3次真实GCC-fanalyzer编译与3次消费者执行均0，源码前后不变。数学SDK仍锁定4f701b4，与接收端提交分别记录；v4未重跑ARM，不把v1其他参数的ARM证据挪作最终参数的MCU验证。

FLP 修复精确匹配相同解码器副本时使用无序集合造成的随机选源：保持用户目录的确定顺序，优先当前项目内文件；不同内容的真实歧义继续拒绝。错误显式选择不能回退成其他包。

## GUI 操作与图像证据

`capture_scg_gui.py` 在真实 Qt 主窗口上使用正常按钮和模态事务，分别渲染 125% 中文浅色、150% 英文深色，主窗口 1320×900 逻辑像素。每组包含三页、共享无线私有草稿、阶段条件/引用、单个 INS owner 六张 PNG，并记录设备像素比和按钮布局。

- 修复前：`gui-offscreen-125/04-radio-private-draft.png`，字段标题缺失、端点长名称使窄窗口产生水平裁切。
- 最终：`gui-offscreen-125-v8/` 与 `gui-offscreen-150-v8/`。修复标题初始化、端点组合框伸缩、表单换行、中文取消文案、无效阶段跳转和次要构建按钮层级。选择 SX1278 两端和预设后取消，模型逐字典比较不变；共享库重复功能表单计数为零。
- 这些是 **offscreen 平台的真实 QWidget 渲染和 QTest 交互**，不是 Windows 桌面截图。原生桌面视觉/系统缩放结果不能从这些图推导。主任务另外完成 Windows 原生桌面三页、两端自定义未导入时生成禁用、无线两端改 E32 后 Cancel 恢复 E28/12dBm、INS owner Apply/Cancel 可见等操作。截图在 TreeDiagram 的 `docs/evidence/20261101/cross-repository/scg-desktop-*.jpg`。原生观察发现 owner 折叠组间空白过大，增加末尾 stretch 后重启实测修复；`scg-desktop-ins-owner.jpg` 与 `scg-desktop-ins-owner-fixed.jpg` 保留前后对照。这是限定路径的桌面验收，不是所有系统/全路径证明。

## 已完成的验证范围

环境：Windows 11 build 26200、仓库 `.venv` Python 3.14.0 / PySide6 6.10.1 / NumPy 2.4.1 / pytest 9.1.1。实际 ARM GCC 14.3.Rel1（14.3.1），Host GCC 16.1.0（MSYS2）。版本原文在 `python-environment.txt`、`make-version.txt`、固件批次版本日志。GUI 测试 `QT_QPA_PLATFORM=offscreen`。

| 完整执行的范围 | 结果 | 原始证据 |
|---|---:|---|
| SCG 三页、共享流程、MCU 调度 Host、source selector、异步检查、无线/参数导入等 12 个完整测试文件 | 123 passed，863.70 s | `scg-final-v2.log` |
| SCG GNSS、安装 store/capture/baseline、S 调度、NRF 清理、SX1278、严格 stack 负例等 11 个完整文件 | 127 passed，383.01 s | `scg-runtime-v2.log` |
| SCG memory/artifact GUI、编译输入 tamper、storage owner、console 容量等 7 个完整文件 | 46 passed，31.36 s | `scg-resource-v1.log` |
| 无线窗口与 tuning bundle GUI 当前专项 | 8 passed，31.31 s | `entry-v3.log` |
| FLP decoder 目录/精确包、mission snapshot、路径偏好 5 个完整文件 | 75 passed，93.65 s | `flp-v3.log` |
| FLP catalog 1.3、自定义 decoder、受控审查、MAG 路由 4 个完整文件 | 37 passed，21.32 s | `flp-contract-v1.log` |
| 原生 USB F103/F407/C071 生命周期与 F103/F407 正常阻断/私有 ARM build 两个完整文件 | 31 passed，586.73 s | `native-v2.log` |
| 最终冻结09c057a6后的旧schema/能力、严格源图、domain/release迁移三文件 | 38 passed，261.53 s；前后源码树一致、dirty为空 | `capability-v6.log` / `capability-v6-receipt.json` |
| 最后布局变更相关完整 GUI smoke / metadata / i18n | 38 passed，482.12 s | `layout-v3.log` |
| GSHC 全量，正确 capture/active C DLL、短 Windows 输出目录 | 1433 passed，51 subtests passed，2120.33 s | `gshc-full-v5.log` |

测试数不能相加当作无重复的单一全仓库测试总数。本轮 SCG 12 文件组之后的 UI 布局/文字由完整相关 GUI 组、入口组及最后截图验证；随后旧工程迁移修复另由专门兼容组覆盖。不能把多个时间点伪装为一次全仓运行。最终兼容组使用`run_final_compatibility.py`，记录实际命令及运行前后`apps/SCG`/`contracts` Git tree身份；两者完全一致，源码没有在本次结果中漂移。

保留失败历史：SCG 最初 Host 回归存在旧夹具缺少新函数原型、WordConsume 和 active boundary、native 外部环境未配置；修正拥有这些接口的源夹具后完整重跑。最初工作流测试直接访问已迁移到唯一 owner 的旧字段；新路径还实际暴露了待提交源绑定丢失，随后修复并完整重跑。`scg-final-v1.log` 的 5 个失败与 `workflow-v*.log` 均保留。

FLP 首次用系统 Python 缺 pytest-qt，之后正确环境复现无序解码器选择失败；修复后整组通过。GSHC v1 路径导入错误、v2 错误 NumPy/缺 pytest-qt、v3 缺 C DLL、v4 过长 Windows 导出路径的失败/中断原文都保留；它们不是通过的全套结果。最终 GSHC v5 使用相同测试和业务预期，只修正环境与输出目录。Native v1 触及既有 248 字符安全限制，保留该限制并缩短输出路径后重跑通过。

旧兼容组发现两类问题：旧测试把当前模型强行标成旧版本并携带未来字段，已改成冻结的明确旧字段夹具；这些夹具随后暴露 v11 直接跳到 v14、遗漏 AirLink/Ground/alignment 初始化，以及默认协议随新工程漂移的真实迁移缺陷。修复恢复 v11→v12→v13→v14 链，v12 参数保留，Ground保持未配置，旧协议身份固定。`legacy-migration-before-after.json` 用4f701b4实际解析器复现修复前拒绝，并核对当前修复；v2缺显式身份和未来mission字段继续拒绝。夹具是注明来源的合成schema投影，绝不称真实历史硬件工程。历史v3–5迁移默认Delay60/垂速-2/Tilt45与2763bb8f相同；v6/v7显式Delay10保留。首轮EIDE身份拒绝发生在另一个负责人修改core Host时钟夹具期间，实际两处hash漂移记录在`capability-v1-provenance-drift.json`；严格拒绝未修改，使用独立新输出重跑。随后发现旧159源参考图尚未纳入本轮S/mission实现，保留其152+6迁移+7新增原表，另加逐项payload/selection/generator owner的新delta，严格完整集合=166及4个当前排除项；不刷新旧工程来源，也不削弱源图检查。

## 正常生成与固件门禁矩阵

下面的 PASS 只覆盖对应工具的实际范围。Power10 工具为项目适配检查，始终保留关键合同人工审查 NOT PROVEN；没有扩大白名单或降低阈值。

| 构型 | 配置/正常生成 | ARM link | architecture / Power10 / 真实 analyzer / artifact | Host范围/退出码 | 任务 stack 命令 | whole-program / 硬件 |
|---|---|---|---|---|---|---|
| F407 SS0.5 + JY901 + SX1281 + S，默认流程 | PASS | PASS | 全部 0 | 0；76 执行文件、5,508,904 checks、12 compile-pass、17 预期编译失败、20 不适用 | 2，当前生成 metadata 未匹配旧完整输入证明 | NOT PROVEN / 未测 |
| F407 安装 capture + JY901 MAG profile + S | PASS | PASS | 全部 0 | 0 | 2，同类当前输入证明阻断 | NOT PROVEN / 未测；源采集资格不成立 |
| TreeDiagram KF6-PID 束应用后的 F407 | PASS，真实共享 gravity 改值 | PASS | 全部 0 | 0 | 2，当前输入证明阻断 | NOT PROVEN / 未测；PID 不在 mission 执行链 |
| H743ZIT6 + 单 BMI088 + ESKF20 + E28-27SX + S，原导入 SD glue | PASS | PASS | 全部 0 | **2，blocking BSP 无法由 delayed-DMA Host 模型验收** | 0，worst-known 八任务预算；不是整体栈证明 | NOT PROVEN / 未测 |
| H743ZIT6 + 受控 owning DMA SD glue，最终09c057a6 / v6 | 精确导入指纹校验，两份源声明替换，原导入不变 | PASS | 全部0；P10实际138文件含2新owner | 完整storage runner 0，相关51 pytest passed；未重跑完整make host-tests | **2，新的H743编译声明/配置尚未经完整stack审阅** | NOT PROVEN / 未测 |
| SX1278 E32-400M20S + F407 Flight / F103 Ground | 两端正常生成 PASS | 两端 PASS | 两端全部 0 | 两端 0 | Flight命令0；Ground无完整stack target | NOT PROVEN / 未测 |
| 精确 C071FBP6 + E28-12SX + native USB | 普通发布准入仍 BLOCKED；私有候选 API 成功 | 私有 candidate PASS | 真实 ARM analyzer PASS；不是正常发布全门禁 PASS | 生命周期 C 边界在 31 项组覆盖 | 全程序未建立 | NOT PROVEN / 未测 |
| F103C8 / F407VE 原生 USB Ground | 普通发布仍 BLOCKED；两份私有 build receipt | PASS | 真编译/分析凭据，未宣称普通发布通过 | 31 项组覆盖正常阻断和 C 生命周期 | 未建立 | NOT PROVEN / 未测 |

H743 上述失败已在本轮新生成目录重新复现，并非复制历史失败。外部 CubeMX `sd_diskio.c` 调用阻塞 BSP，随后无界等待卡状态；原 BSP callbacks 也未过滤句柄。最终已在H7 owning插件实现有界DMA/隔离scratch，并以声明式source graph替换两份编译输入，**不修改用户导入源、不削弱Host期待**。新构型实际结果在[H7最终v6报告](../h7_storage_20261101/v6/DELIVERY.md)，来源09c057a6。完整storage runner保留原零drop/故障期待；修正Host时钟查询凭空加tick，时间只由明确delay/queue/DMA推进。两份canonical C现在显式归第一方严格warning/analyzer/Power10；缺owner文件或active owner均拒绝。旧构型失败仍保留，新的strict stack也仍FAIL。此修复限定审阅的导入指纹与DCache关闭，不代表通用任意H7输入或硬件资格。

## SS-TM-S 字节、方向与实际软件时序（附件 §19.8）

机器权威仍为 `contracts/ss_tm_v0_1.json`，C 实现为 `silverstar_protocol_telemetry_ss_tm/payload/Protocol/SS_TM/Src/ss_tm_protocol.c`，Python 为 `apps/SCG/src/silverstar_telemetry/codec.py`。本轮从机器合同逐字段计算并检查总长度，生成 [完整逐字节表](ss-tm-wire-v1/WIRE_BYTES_ZH.md)，包括每类消息的 offset / type / 长度 / 单位、POSITION 位、HEALTH 位、未知值和事件编号。没有另造一份独立协议权威。

公共头为 offset0=`version` u8 0x01；offset1=`profile_type` u8，当前 S bit7=0、bits0..6为type；offset2..3=`tx_sequence` u16；offset4..7=`boot_session` u32 非零。多字节 little-endian，f32 为 IEEE-754。事件原始发生时间与重发时间分开，重发保持 event_id/occurred_us。无应用层 CRC，硬件 CRC 仍启用。H 编码仅保留历史兼容；当前生成图不提供 H。

方向状态分开：预飞时两端半双工；飞控本地接受 START 不等于 RF 已完成。最终 START ACK 由真实 TX result 回执确认，或到 2,000,000 µs 有界截止；在途回执仍按有界状态处理，最多 3 次边界发送尝试，不能据此宣称任何硬件条件下恰好 2 s 完成切换。飞控进入 TX-only，地面收到当前任务事实后进入 RX-only。地面启动/重连默认被动，仅接纳有效当前预飞 CAP 后开放预飞双向；本地 UART/USB 维护会话不等于恢复无线任务期上行。源路径为 `telemetry_service.c` 的 ReceiptPoll/ModeProcess/边界事务，以及 `core_ground` 的 `ground_radio_tm.c` 和实际 SX1281/SX1278 backend。

`capture_wire_evidence.py` 核对已编译生成 C/H 与原 compiler receipt 完全一致后重新运行全部 16 个调度场景，全部退出 0；另以真实 GCC `-fanalyzer` 新编译 C codec，与 Python 逐字节比较 **8/8** golden vectors（4 个 active S、4 个历史 H），结果在 [golden-vectors.json](ss-tm-wire-v1/golden-vectors.json) 与 `codec-c-vectors.log`。原回归入口为 `apps/SCG/tests/test_ss_tm_contract.py::test_actual_c_and_python_golden_vectors`、`tests/fixtures/ss_tm_codec_host.c`、`test_ss_tm_scheduler_host.py`、`tests/fixtures/ss_tm_scheduler_host.c`。各实际命令、退出码、binary hash和来源在此子目录 JSON 中。

| 实际 Host 场景 | 首次/最大间隔测量（ms） | 结论范围 |
|---|---|---|
| `start_order` | Host时钟 ACK TX_DONE=183、首次 MISSION_START EVENT=268、首 DATA=385；DATA最大间隔205 | 从1 ms设置START的场景；首次事件在DATA前完成，不是入队先后假定 |
| `start_ack_backlog` | 同为183 / 268 / 385；DATA最大间隔205 | 普通ACK排在前且限速到9000 ms，仍不能饿死关键START ACK |
| `normal` / `long`（长场景60 s） | DATA / POSITION / HEALTH 最大间隔=200 / 1000 / 2000 | long实际297 / 60 / 30帧，387次完成、0发送失败；平均数量和最大间隔分别记录 |
| `burst`（12个普通事件入队） | DATA / POSITION / HEALTH 最大间隔=202 / 1008 / 2002 | 不是仅凭总包数推断未饿死周期流 |
| `landed`（10 s） | 无DATA；POSITION最大间隔1000，HEALTH观测间隔4499 | 该有限场景只有2帧HEALTH，4499是实际观测，不是所有落地条件的数学上界 |
| `sx1278_airtime_events`（15 s） | DATA最大间隔207；5个普通事件首次完成603 / 810 / 1017 / 1605 / 1812；EVENT最大间隔791 | 使用真实生成service/codec及容量1传输端口、SX1278精确PHY ToA，不能称SX1278驱动或硬件时序证明 |

SX1281 场景执行实际 driver 与 adapter，端口按 SF10 / 实际812500 Hz / CR4/5 / preamble16 的 airtime产生模拟TX_DONE；SX1278采用SF7 / 125000 Hz / CR4/5。所有这些数字都是 **Host软件时钟测量**，没有射频实测、覆盖距离、STM32 WCET 或中断负载上界含义。`lost_start_ack`、`start_event_full`、`stage_event`、`stage_scope` 等原始日志保留实际失败注入和断言结果。H743旧存储FAIL、严格栈FAIL不会被这些时序通过抵消。

## 各银行真实用量

完整逐银行数字和程序化派生方式见 [RESOURCE_SUMMARY.md](RESOURCE_SUMMARY.md)、[resource-summary.json](resource-summary.json)、`summarize_resources.py`。包括 used%、物理余量/比例、审阅预算余量、保留字节、地址跨度和尾部；JSON同时保留对应source报告/ELF身份及严格stack失败退出码。

单位为字节。普通构型以当前统一 `memory-report.json` 的 section 有效字节为 used；地址跨度和保留空间另在 JSON 中给出。下表余量为物理容量减 section 字节，不代表可分配连续最大块，更不代表安全动态栈余量。F407 100 KiB 主 SRAM 审阅预算没有提高。

| 构型 | Flash used / capacity | 主 SRAM / AXI used / capacity | CCM 或其他银行 | 审阅预算与备注 |
|---|---:|---:|---|---|
| 默认 F407 | 355892 / 524288 | 102148 / 131072 | CCM 60888 / 65536 | 主 SRAM 预算剩 252；CCM 物理剩 4648 |
| 安装 F407 | 408316 / 524288 | 102316 / 131072 | CCM 63304 / 65536 | 主 SRAM 预算仅剩 **84**；CCM 剩 **2232** |
| 束参数 F407 | 355900 / 524288 | 102148 / 131072 | CCM 60888 / 65536 | 主 SRAM 预算剩 252 |
| 原 SD glue H743 | 369056 / 2097152 | AXI 218096 / 524288 | DTCM 8192 / 131072；D2 0 / 294912；D3 0 / 65536；ITCM 0 / 65536；CCM 不适用 | DTCM 顶端 8192 为 MSP reservation，非实测；未分配银行非立即可用空间 |
| owning SD H743 v6 | 372132 / 2097152 | AXI 218708 / 524288 | DTCM 8192 / 131072；D2/D3/ITCM均0，CCM不适用 | heap0；DTCM为MSP预留，strict stack **FAIL/2**、安全余量未证明 |
| SX1278 F407 Flight | 344268 / 524288 | 92844 / 131072 | CCM 60888 / 65536 | SRAM审阅预算剩9556；整体栈仍NOT PROVEN |
| SX1278 F103 Ground | 17500 / 65536 | 5380 / 20480 | 无CCM | 无完整stack target，未证明动态栈 |
| 私有 C071FBP6 USB | 42276 / 131072 | 10512 / 24576 | 无 CCM | 含 2052 字节 heap/stack section（2048 stack + 对齐）；无动态栈证据 |
| 私有 F103C8 USB | 40300 / 65536 | 11308 / 20480 | 无 CCM | Flash span 40304，RAM span 11312；保留对齐差异 |
| 私有 F407VE USB | 41912 / 524288 | 13976 / 131072 | CCM 0 / 65536 | 私有候选资源，不是普通构型任务栈证明 |

其他已注册 MCU 的容量/未知 section/超限/旧 ELF、Flash LMA + RAM VMA、无 CCM、F103RF 768 KiB 边界由资源负例组验证；这不表示那些 MCU 已具备 S Flight 实现。

F407 严格 stack 输入拒绝保持原样，没有把新 hash 加入历史证明。另执行 `--diagnostic`，退出仍为 2，明确 callback/source closure、main/MSP、ISR nesting 未审阅。H743 原构型静态任务估计（已含 256 字节已选 RTOS 上下文保守项）为 Device 2188/2560、INS 2396/3072、Estimator 4016/5120、Flight 3384/4096、Logger 2344/3072、Serial 4948/6144、Telemetry 2228/4096、Idle 256/512；其 JSON 仍明确整体 NOT PROVEN。没有把 M4/CM7 上下文值套给 M0/M3。

## 按附件章节准确列出的未完成项

| 章节 | 已实现的软件范围 | 仍缺少的完成条件 |
|---|---|---|
| §4 / §15A | 三页、单 owner、私有事务、共享无线、双目标事实、真实 Qt 操作与缩放渲染 | 已完成限定路径的原生Windows观察及125/150% offscreen；所有桌面环境/全路径视觉验收未建立 |
| §5 / §15B | 有界 firmware 模板、真实阶段条件/事件、记录/遥测区间、导航 START owner 和连续状态约束、生成 C Host 消费 | 非支持任意依赖图/延迟重初始化；PID/LQR 尚无任务执行器 adapter，仍研究用途；未完成全 MCU 动态安全资格 |
| §6–8 / §15C | active S、NRF 移除、明确迁移、实际 TX_DONE/队列/方向 Host 回归、SX1278 两端正常生成 | 空口误码、RF 真实 TX_DONE 时延及最长更新空窗、板级引脚/射频开关和方向实测未做；软件模型不能冒充 RF 测量 |
| §9 / §15D | 唯一接收语义、CAP/session/稀疏序号、mailbox顺序、有效接收年龄、健康/最后定位工作流 | GSHC全套软件回归已通过；真实串口/RF断连重连与定位缓存现场验收未做 |
| §10 / §15E | shared maintenance lease、TRAIN/HOLDOUT 工作流、候选与活动记录分离、真实 Alignment/INS/MAG 消费者、原子 Apply/保存/启动加载及 Host 故障边界 | **没有任何实际 IMU/MAG 组合达到严格生产采集资格**：原生 epoch/时间、延迟与不确定度、帧/轴映射来源证据不足；JY901 不能凭接收时刻伪造测量时间，MMC 默认 8 ms 转换不能证明冻结的 1 ms 不确定度。真实六面采集、断电/目标读回/重启验证未做；XYZ 仍仅元数据，无动态杆臂补偿 |
| §11 | KF6 原有 GNSS 恢复与默认开关保留、用户语义 Airborne <4g / 项目枚举 4 → u-blox 8 的生成及 C 测试 | 接收机查询读回未实测；ESKF15 实验恢复门禁仍关闭，不能据 GUI 宣称完成 |
| §12 / §15F | ssdecoder1.3 / 旧1.2严格兼容、catalog/semantics身份、目录GUI、确定性精确匹配、结构化 mission视图 | 当前只声明测试覆盖的记录类型和固定样本；真实飞行日志/硬件活动标定记录端到端验收未做 |
| §13 / §15G–H | 精确 MCU/银行/LMA/VMA/保留空间/身份统一报告，真实 ARM/analyzer 与负例 | F407 当前完整输入 callback binding 人工重审未完成；main/MSP/IRQ嵌套、故障重入、动态帧/库调用覆盖、high-water/STM32 WCET 仍 NOT PROVEN；不是单纯缺硬件一个阻塞 |
| §14 | 旧 USB wLength/生命周期等真实输入回归、F103/F407/C071 私有候选 ARM、H7 自定义身份与cache拒绝保留 | 原生 USB b66 独立发布审查没有通过结果，完整 EP0/async/critical-contract/stack 资格未闭合；H7受控owning软件修复已验证，但仅接受审阅输入指纹；新strict stack仍FAIL。D-cache开启配置继续拒绝，不伪造支持 |
| §15 总体验收 | 本目录完整原始失败/成功日志、命令、具体构型与产物身份 | 任一 FAIL / NOT PROVEN 均阻断“全部验收完成”说法；没有通过若干局部结果拼接成全项目成功 |

## 运行与复现

在仓库根目录使用已有 `.venv`：

```powershell
& .venv\Scripts\python.exe apps\SCG\main.py --lang zh_CN --theme light
```

SCG 第二页选功能实例后使用“导入参数”选择 `.sstuning.json`，阅读预览和研究用途限制，确认后应用。普通独立参数文件仍走原严格入口。FLP 使用 `apps/FLP` 已有启动入口，并在解码器设置中选择有限搜索目录；输入源日志保持只读。

可重放的普通固件生成逻辑在 `run_firmware.py`，C071精确候选入口在 `run_c071.py`，offscreen截图在 `capture_scg_gui.py`。脚本使用 `exist_ok=False` 防止复用旧生成目录；重放应先选择新的任务版本目录，不能删除原始证据后把新的执行冒充这次运行。普通固件 make 命令及环境由各批次 `commands.json` 保存。原生外部输入的精确绝对路径/SDK header hash在 `c071-v1.json` 与 compile receipts 中；缺少这些输入应明确跳过对应原生验证，而非替换假输入。

本轮唯一遇到的权限问题是遍历无关历史 `.work/day_ground_*` 目录被拒绝；已跳过并保留原样，未影响本任务所用输入。完整安全验收尚有上述软件证明和硬件实测缺项，不能记录为权限问题。
