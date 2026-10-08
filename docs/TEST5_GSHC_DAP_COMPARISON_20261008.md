# 2026-10-08 TEST_5、生产 GSHC 与 DAP 拒绝现场

原始 TEST_5 和当前候选均通过本次有限的生产 GSHC START/接收流程；两者均发生一次 START 重发，并先由 FLIGHT 状态完成事务，随后收到 OK ACK。**较晚 ACK 在旧版也存在，本次不足以归因为新版本回归。** 单独的 DAP 诊断定位到新的 LoggerBus BAD_STATE：已 LANDED、日志 FINALIZED 后，Estimator 仍发布气压融合健康超时事件。此处生命周期与日志发布边界不一致，尚未修复，完整接受仍未完成。

最终 Flight 的完整 512 KiB 主 Flash 与测试前双读备份逐字节相同；当前运行于 PREFLIGHT，断言故障记录为零。恢复后未发送 START，生产串口与调试连接已关闭，Ground 未烧录。TF 上本次新任务的文件尚未取回验收；原 TEST_5 没有强求静置完成 Tilt90 生命周期。

## 授权、版本与范围

本任务原先是软件收尾；随后用户明确授权“再做几个固件测试”，指定旧 TEST_5、GSHC 对比与 DAP 拒绝诊断，并确认“所有执行器均未连接”、TF 已插回并重新上电、设备 +Y 静置。此次只操作指定 Flight DAP（serial `132765403520`）和 Ground 维护串口 COM3；没有转动设备、连接负载或改动部署条件。物理执行器未连接，界面/协议中的 PARACHUTE_DEPLOY 表示固件事件，不能作为实际开伞验证。

开始 HEAD `7711ce72deb92894dc9cffd230f3ab5d5ce71011`，分支 `fix/nightly-user-ready-20261003`。`apps/SCG`、`apps/GSHC`、`apps/FLP` 与源提交 `cac7bd29bf6f6aec5297715ea14893b4b7684953` 的 diff 为空；本交付新增报告和证据、补索引，并为该 evidence 目录添加 `-text` 属性以保持记录字节。没有重新生成、修改算法、运行另一轮完整 ARM/Host/长日志/ESKF 重算。之前的 [000044/000045 实际 TF 文件验收](STATIC_LOG_FILE_ACCEPTANCE_20261008.md) 保留其日期、文件身份和范围。

开始及结束检查未发现其他 Python/OpenOCD/GDB 测试进程或应用源码写入；不能由进程名证明系统上绝无其他活动。CIM 命令行查询遭系统访问拒绝，采用 Get-Process 与仓库状态检查，没有修改权限或终止其他应用。此前 Complete logger checkpoint 的只读审核已结束。三个未跟踪 `work_*_20261006` 文件保持原位、原哈希，列于 [environment.json](evidence/test5_gshc_dap_20261008/environment.json)。

## 确认实际 TEST_5

使用 `D:\stm32_project\SS_0_5_TEST_5` 的既有 EIDE Release ELF/HEX，没有以 28b、临时 R5 或新生成候选代替。原 ELF 经 objcopy 提取出的地址→字节与原 HEX 完全一致；实际烧录原 HEX，随后读回核验全部 321,988 个显式字节。地址跨度为 `0x08000000..0x0804e9d0`（末地址不包含，322,000 B，含 12 B 未指定间隙）。

| 输入 | SHA-256 / 范围 |
| --- | --- |
| TEST_5 ELF | `48cb98777c9dd9a86489f4e09c895ee5c1192a93de01e06fcd7e36b8b103ab27` |
| TEST_5 HEX | `95f5c58e0c8e99b6d3a181a6eef26e0a157c51480a6f6b4ebd258b4ba35f2b4d` |
| TEST_5 decoder | `e162b78bb07ae2a436a04f185da86653db838a89d8488959dcf531bc1f24caaf` |
| 历史 `Log/000028/flight.sslog` | `ea145d3529bc030fdd82883638935ca245da2c56e8bc2cc3be532b572b9e9e93`；与冻结盘点一致，exact decoder 匹配 TEST_5 |
| 当前候选 BIN，331,020 B | `5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3` |
| 当前候选 ELF | `14637f20ac2b83bc4b169b232a364d037013e494444aa23ad246070148ae4cfd` |
| 测试前双读 / 最终完整主 Flash，524,288 B | 均为 `109a4eee42d2ba9189a1fef26559ec5dfcbc0ae7cda54f7dc6a76d6bdd674fba` |

完整输入路径、大小及哈希见 [identity_full.json](evidence/test5_gshc_dap_20261008/identity_full.json)。历史任务 28 的绑定证明命名项目与 decoder 一致，**没有找到原 ELF 与历史源 commit 的精确绑定，也没有历史飞行当天实际烧录 ELF 的独立哈希证据**；这两项保持 NOT PROVEN。历史日志头的 0.1.0 标签与工程 0.1.1 标签分别保留，不能凭标签替代二进制身份。

两工程的 hardware/resources/air_link 字典一致：F407VET6/SS0.5、竖装 JY901B、M9N、SX1281、SD_SDIO；RF 2473 MHz、SF10、800 kHz、CR4/5、CRC、MTU61 等一致。旧工程自动 NONE 校准，CAP mask 1，Tilt90；当前工程 OneFace，CAP mask 3，Delay10。旧工程未启用的 Delay 字段为 60 s。这是有限同硬件/链路对照，校准和部署条件并不相同，不能声称严格单变量实验。

## 备份、切换和恢复

测试前 07:13:15–07:13:39 UTC，不 halt、不 reset，双读完整主 Flash 并读 RAM 诊断；两份完全相同，BIN 前缀精确匹配当前候选。设备 ID `0x10076413`、Flash 512 KiB 均在每次写入前检查。初始已是 PREFLIGHT，符合用户重新上电后的状态。

| 阶段（UTC） | 结果 |
| --- | --- |
| TEST_5 写入，07:18:31–07:18:51 | OpenOCD program/verify/reset exit 0；独立读回全部 HEX 字节一致，sector 7 不变 |
| 当前候选写入，07:19:56–07:20:16 | exit 0；331,020 B 读回与 BIN 相同，sector 7 不变 |
| 独立 DAP 诊断，07:28:06–07:28:48 | 一次 reset/hardware breakpoint；GDB 捕获并 resume/detach；生产会话结束 |
| 最终恢复，07:29:03–07:29:23 | exit 0；BIN 读回相同，sector 7 不变，无随后 START |
| 最终完整只读核验，07:33:20–07:33:32 | exit 0；全部 512 KiB 等于初始备份；CORE 运行 |

仅按镜像范围擦写，没有 mass erase、option bytes 写入或 Ground 烧录。sector 7 保持不变是一项保全检查，不将其臆称为校准区；当前持久配置使用 TF 对象槽。没有 CAL_SAVE、CAL_RESET 或多姿态校准。主 Flash 已完整还原，RAM 经复位处于新 PREFLIGHT，TF 保留新产生的数据，不能声称把 TF/RAM 也回滚到测试前瞬间。

## 实际生产 GSHC 对比

运行真实 `MainWindow`、`Controller`、`SerialWorker`、`ProtocolWorker` 和异步 JSONL logger，使用 COM3@230400。Qt 定时器通过生产公开操作依次推进 CAP、校准 READY（当前）、对准 READY、UNLOCK、START；未修改生产 800 ms ACK 超时、重试上限 3、串口 20 ms 读取超时。每场公开 START 调用一次，AIR 第二次发送由原生产重试管理器产生。ACK 不替代 READY。

本机提供的 Computer Use 技能要求 node_repl；当前工具没有该入口，native UI 控制也未开放。因此这是**可见原生窗口、生产管理器的受控 Qt 自动化验收**，不是鼠标点击或人工 GUI 操作验收。真实窗口截图保存在证据内；测试结束调用生产 shutdown，确认串口/协议 worker 关闭、logger error 为空。没有独立长等待串口 harness 冒充 GUI 验收。

| 未 halt 的基线 | 原 TEST_5 | 当前候选 |
| --- | --- | --- |
| 会话 UTC | 07:19:14.641–07:19:28.373 | 07:20:53.007–07:21:23.097 |
| START 首发→第二发，ms | 876.6333 | 805.8951 |
| 首发→首个 FLIGHT 串口接收，ms | 1384.9834 | 1404.5147 |
| 生产事务以 FLIGHT_STATE 完成，ms | 1394.5578，attempts 2 | 1424.8262，attempts 2 |
| 首发→START OK ACK 串口接收，ms | 1722.7237 | 1740.4309 |
| ACK 接收→协议解析，ms | 0.1823 | 0.3543 |
| MISSION_START | 3 个 STATUS，同一 MCU time 6 ms | 3 个 STATUS，同一 MCU time 3 ms |
| DEPLOY / LANDING | 未诱发、未完成生命周期 | 各 3 个 STATUS，MCU time 10000 / 14009 ms |
| 接收 FLIGHT 数 / 最大 MCU 包间隔 | 27 / 581 ms | 52 / 580 ms |
| 最大主机 FLIGHT 接收间隔 | 885.4017 ms | 581.3054 ms |
| 完整字节观察 | 原场未附加 observer，NOT RUN | 5075 B → 150 GSP / 113 AIR，全部与 JSONL 接收帧一致 |

当前 raw 捕获由 worker 的只读旁观信号取得，离线用原生产 ReceivePipeline 重解析：GSP CRC/parse/resync、AIR parse、剩余 buffer 全为 0。它从记录的 observer 接入时刻起覆盖，不保证此前的字节。旧版保存 88 个已接收 GSP 原帧、全部可校验，但这不能证明原场未捕获的坏字节不存在。详见 [session_audit.json](evidence/test5_gshc_dap_20261008/session_audit.json)。

两版首发 ACK 均未在 800 ms 内抵达；生产事务最终成功且未报告 START failure/timeout。先 FLIGHT 完成后，较晚 ACK 被记录为 STALE_OR_UNMATCHED，不能把该标记误判为 START 失败。三次 MISSION_START STATUS 是接收的重复公告，不能当成三次业务 START，也不能凭此证明 TF 只创建一次任务。ACK 的 MCU time 6/3 ms 是 mission 时间域，不能当作 6/3 ms 端到端处理耗时或持久写入完成确认。

每版仅一场且观测长度/校准条件不同。界面估计损失 8/35 和 11/63 来自按 FLIGHT 时间间隔推算，不是直接测得 RF 丢包率；不能用 AIR 全局 seq 跨消息计数替代导航丢样检查。约 0.2–0.4 ms 的解析延迟不支持“这 1.7 s 主要耗在已接收后的协议解析”解释，但无线/发送排队/重发/驱动与 GUI 调度各段尚无同一时间基准证据。

旧 TEST_5 保持 Tilt90，仅 START 后有限静置观察 6 s，不要求用户转动或为落地改阈值。随后关闭 GSHC、切换镜像复位，终止该未完成的固件任务；没有安全终止命令或 TF 尾部完成证明。这次未完成尾部作为刻意中止的观测边界记录，不归为日志尾部 FAIL，不声称原场完整生命周期 PASS。

## DAP 捕获：新的拒绝记录已定位

这场单独运行当前原 ELF，对 `0x080167e6` 设置硬件断点，在 `LoggerBus_PushStateGet` 已确定 BAD_STATE、尚未递增 state_reject_count 时捕获。现场位于 IRQ 临界区，PRIMASK=1；只读寄存器、RAM 和栈，不调用 target 函数，不增加固件埋点。整场排除于上表时延/最大间隔基线。

实际调用链为 `AppTask_Estimator` → `Estimator_HealthEventsPublish` → `LoggerBus_EventPush` → `LoggerBus_ConfiguredRecordPush` → `LoggerBus_PushStateGet`。见完整 [gdb.log](evidence/test5_gshc_dap_20261008/dap_reject/gdb.log) 和 [ELF 指令核对](evidence/test5_gshc_dap_20261008/breakpoint_disassembly_corrected.log)。

| 现场项 | 实测值 |
| --- | --- |
| task / lifecycle | Estimator / SYSTEM_STATE_LANDED |
| Logger initialized / accepting / boot_disabled | 1 / 0 / 0 |
| finalization | LOGGER_BUS_FINALIZATION_FINALIZED |
| accepted / dequeued / normal / estimator / overflow | 10109 / 10109 / 0 / 0 / 0 |
| state_reject_count | 0，断点在此次递增之前；不是“本场无拒绝” |
| 记录 type / payload_size | EVENT=2 / 12 B |
| payload 前 12 B | `2f 00 00 00 04 05 01 00 d0 07 00 00` |
| event / arg0 / arg1 | NAV_FUSION_STATE_CHANGE=47 / `0x00010504` / 2000 ms |
| evaluation_us / estimator mission_running | 30073252 / 1 |
| EVENT policy | enabled=1，EVENT，decimation=1，period=0；尚未调用 ShouldEmitAt |
| assertion / 断点前 health_flags | active=0 / 130 (`0x82`) |

源码把 arg0 组装为 `group | state<<8 | reason<<16`，故该条是 group 4（barometer）、DEAD_RECKONING=5、超时 reason=1，距上次成功融合 2000 ms。气压组映射见 [Estimator_BarometerHealthPublish](../apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/estimator_task.c#L2660)，2 s 超时见 [SystemNavigationHealth_GroupGet](../apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Src/system_navigation_health.c#L135)。

直接原因是 [HealthEventsPublish](../apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/estimator_task.c#L3318) 只按 `mission_running`/algorithm 决定发布，LANDED 后该标志仍为 1，健康超时计算继续产生改变；而 [日志 finalization](../apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/flight_task.c#L701) 已关闭接收。LoggerBus 在流 policy 判定之前按关闭状态返回 BAD_STATE，符合其防止关闭后写入的边界。该 EVENT 本身已启用，不能解释成“禁用 stream 的计数噪声”，也不是队列满或导航队列溢出。调用者的失败路径会 OR 入 `ESTIMATOR_HEALTH_LOG_EVENT_FAILED`（bit8）；断点前的 `0x82` 尚不包含此位，未另读返回后的 RAM 来证明该位实际置入。

这定位了**本场新发生的一条拒绝**，没有恢复历史未入队 payload，不能给 000044/000045 的原 2/1 条逐条补身份。需要在拥有源码的插件中设计并验证生命周期/日志发布边界修复；不能通过全局把 BAD_STATE 改 OK、抑制计数或隐藏真正运行期间失败来消除现象。此次保持原二进制用于比较，修复、前后 fault regression、fresh power10/analyzer/ARM 和硬件复验均 NOT RUN。

GDB 栈在 FreeRTOS port 尾端提示 `previous frame identical ... (corrupt stack?)`。产品调用帧 0–4 与 ELF 的 `bl LoggerBus_EventPush`/返回点一致；尾部展开仍未证明，不能据提示断言真实栈损坏，也不能由成功展开声称栈安全。七个相关 generated/owning payload 文件逐字节一致，见 [generated_owner_mapping.json](evidence/test5_gshc_dap_20261008/generated_owner_mapping.json)。

## 证据、异常和验收状态

证据保存于 [manifest.json](evidence/test5_gshc_dap_20261008/manifest.json)，包括完整备份/恢复读回、OpenOCD/GDB 命令与日志、三场真实生产 JSONL、窗口截图、观察时间线、raw 接收及离线审核。工具为 Python 3.14.0、PySide6 6.10.1、OpenOCD 0.12.0 (2025-07-10)、Arm GDB 15.2.90/Toolchain 14.3.Rel1。这里记录软件工具运行结果，不扩展成目标 WCET、导航精度或飞行资格。

保留异常详情：主 GDB 已 delete breakpoint、resume/detach，finally 冗余 `rbp` 产生“no breakpoint found / Rcmd C0”，虽然 cleanup 进程 exit 0，不能把该命令本身写成成功删除；随后独立烧录/完整读回和运行状态证明恢复。离线反汇编初次 Windows 路径转义失败，修正为 POSIX 路径后 exit 0，两次日志均保留。没有因此重复硬件 START。

原 DAP 元数据的“no calibration commands”仅适用于 GDB/OpenOCD：编排的 GSHC 会话实际执行了 OneFace CAL_START，operations/JSONL 为准。TEST_5 执行后驱动脚本才添加被动 raw observer，现存脚本是 current/current_diag 使用版本；TEST_5 原 harness 的逐字节快照未另存，保持 NOT PROVEN，不把后来脚本冒充旧场精确快照。上述更正另存 [evidence_notes.json](evidence/test5_gshc_dap_20261008/evidence_notes.json)，原运行证据未覆盖。

| 检查 | 结论 |
| --- | --- |
| 原 TEST_5 ELF/HEX 身份、有限烧录/读回 | PASS；历史源 commit 绑定 NOT PROVEN |
| 两版生产 GSHC CAP/READY/UNLOCK/START/接收 | PASS，在上述各一场有限范围内 |
| 两版首发 800 ms 内 START ACK | 未满足；两版最终事务均成功 |
| 当前未 halt 的 DEPLOY/RECOVERY/LANDED 公告 | PASS；执行器/实际开伞 NOT RUN |
| 当前 raw GSP/AIR 字节重解析 | PASS；旧场完整字节覆盖 NOT RUN |
| 新 BAD_STATE caller/type/policy/lifecycle | PASS，已定位一条；生命周期/日志发布缺陷未修复 |
| 关闭后发布契约完全接受 | FAIL（上述已复现不一致）；旧拒绝身份 NOT PROVEN |
| 最终完整主 Flash 恢复、无后续 START、连接关闭 | PASS |
| 新 TF 文件 strict decode/snapshot/持久确认 | NOT RUN；不由 ACK 或旧 44/45 验收代替 |
| 鼠标 GUI 输入、原 TEST_5 完整 Tilt90 生命周期 | NOT RUN |
| START 分段时延根因、空口容量、最大导航间隔原因 | NOT PROVEN |
| 新源码修复、全套软件/ARM/安全门禁 | NOT RUN，本次原镜像诊断；先前各报告范围保留 |
| ESKF15/F407、F103/NRF 实物、飞行/开伞资格 | 未完成；本次未扩展验证范围 |

离线复核命令（在仓库根目录，不连接硬件）：

```powershell
.venv/Scripts/python.exe docs/evidence/test5_gshc_dap_20261008/audit_sessions.py docs/evidence/test5_gshc_dap_20261008
.venv/Scripts/python.exe docs/evidence/test5_gshc_dap_20261008/verify_archive.py --commit
git diff --exit-code cac7bd29bf6f6aec5297715ea14893b4b7684953 -- apps/SCG apps/GSHC apps/FLP
git diff --check
```

实际硬件命令完整 argv 在 backup/flash/DAP/final read 的各 `command.json`、`result.json` 内。归档硬件脚本保留原 `.work` 执行路径和版本，迁移后未改成新的可执行入口；重新运行任何硬件阶段需要当前连接、原输入和新的明确授权，不能直接重放证据脚本来冒充新验收。`audit_sessions.py` 是只读协议重解析与结果核对，写入的 session_audit 应逐字节不变。

下一轮最小步骤：先在软件侧修复并验证 post-LANDED 发布边界，保留正常错误、活动期真丢样与 finalization 故障路径；取得本次新 TF 文件及其 exact decoder，分清刻意中止的旧 TEST_5 与当前自然结束场；后续另获硬件授权再做有界静态复验。单独捕获 START 的命令处理、出队和 RF 发送时间才能进一步分解 1.7 s，不能以调整算法或长等待掩盖。无需为这些诊断新增限频、采样率或传感器禁选规则。
