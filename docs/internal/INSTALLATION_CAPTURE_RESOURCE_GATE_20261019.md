# 安装标定原始采集接入：实施前资源门禁

2026-10-19；owner：`installation_capture_resource_gate_20261019_v1`。

**结论：停在实现之前。** 用户要求资源超预算、时间/身份来源不足或互斥无法证明时停止，不能挤占既有缓冲或放宽门禁。原方案新增静态状态估算 6208 B，当前已烧录候选在既有 legacy 预算下只有主 SRAM 108 B、CCM 2632 B；即使错误地把两区视为可互换，合计 2740 B 仍差 3468 B。尚未形成可供上板的采集候选；没有修改生产源码、模板、live owner、GUI、固件工程或构建物。

## 实际资源及预算修正

只读检查目标是 `D:/stm32_project/SS_0_5_CAL_TF_CANDIDATE_20261018_01`。从其 ELF section 表直接重算，沿用 owning [artifact checker](../../apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_firmware_artifact.ps1) 的 section 求和方法：

| 区域/项目 | 字节 |
|---|---:|
| `.data` | 1140 |
| `.dma_bss` | 10952 |
| `.bss` | 89176 |
| `._user_heap_stack` 既有保留 | 1024 |
| main SRAM gate 合计 / 既有 legacy 上限 | 102292 / 102400 |
| main SRAM gate 余量 | 108 |
| main SRAM 地址跨度 / 对齐空洞 | 102296 / 4 |
| `.ccmram_bss` / 容量 | 62904 / 65536 |
| CCM 余量 | 2632 |

128 KiB 是主 SRAM 物理容量，不是本轮获准使用的新预算。当前 checker 已存在 auto 布局分支，但本轮没有选择该分支、重新布局或把阻断的 legacy 预算改作警告。两个存储区的可达性、DMA、初始化和已有任务栈放置仍需分别成立。

原提案为 IMU 8×96=768 B、MAG 8×64=512 B、pair 16×192=3072 B、上下文/诊断 640 B、RX 192 B、TX 2×512=1024 B，共 **6208 B**，建议独立上限 **8 KiB**。这不是实测 `sizeof`，也未完整计入 INFO 冻结描述/序列化/hash 工作区和幂等回复状态。因此不能把 6208 B 当作完整实现已满足的预算，更不能把新增状态塞入旧队列/缓冲或移到栈上。更小的流式布局尚未设计和证明，不在本轮擅自替换。

已有 `stack-budget.json` 绑定的 ELF hash 与当前 ELF 相同，其历史报告给 Device 任务配置 2560 B、已知路径加 context 2144 B、余量 416 B；Serial 配置 6144 B、已知路径加 context 4944 B、余量 1200 B。原 checker 最小余量为 256 B；这些数值不是允许新代码直接消耗的空间。新增 tap、配对、编码、CRC/hash、嵌套调用栈尚为 **NOT PROVEN**，main/MSP/ISR 嵌套及硬件 HWM 也保留原报告的 NOT PROVEN。本次没有把历史报告记作新栈检查。

## 吞吐与时限

按[正式契约](../../contracts/installation_calibration_v1.json)的 154-byte body、hex 编码、最大 sid/pair/ctx 和 CRLF，实际最大单个 IMU 或 MAG EVENT 为 **438 B**，一对为 **876 B**。以下为每方向的 8N1 计算；上下行全双工分列，不把它们错误相加：

| pairs/s | 样本下行 kbps | 115200 占用 | 230400 占用 |
|---:|---:|---:|---:|
| 5 | 43.8 | 38.02% | 19.01% |
| 10 | 87.6 | 76.04% | 38.02% |
| 20 | 175.2 | 152.08% | 76.04% |

原说明的约 880 B/对只计样本，不能作为整体链路准入。若按每 50 ms 一条最大 511 B 回复加 CRLF 保守预算，POLL 回复另需 **10260 B/s**：10 pairs/s 总下行 **190.2 kbps**，230400 占 **82.55%**、115200 占 **165.10%**；20 pairs/s 下行 **277.8 kbps**，超过 230400。上行请求按最大 191 B 加 CRLF、20 次/s，上界另为 **38.6 kbps**。这是最坏长度预算，不是目标实测输出；精确短状态回复设计可降低开销，但不能未经实现/测量便据此宣布通过。CAPS/INFO、额外终态、串口原始输入和处理时延尚需单列，停止/取消必须优先且有最坏延迟界。

10 秒 FACE 上限还要求 `TRAIN+HOLDOUT` 数量、真正可用对率、稳定检查及排空预算一致。例如协商各 64 对、10 pairs/s，光采样就需 12.8 秒，不能广告为 10 秒内可完成。不能靠放长超时掩盖不一致。

## 来源和互斥仍需闭合

- 当前候选的 IMU 和 MAG instance 0 都经生成 facade 路由到 JY901B。其 MAG adapter 明确注释 0x54 没有测量时间戳；`sample_timestamp_us` 和 `receive_timestamp_us` 同取 `MagTimestampUs`，后者在解析帧时取本地时间。不能写成硬件同步时间，不能填零冒充已知不确定度。当前 MAG interface 没有 sample epoch、计时不确定度或质量/gap 标志字段；需先给接收代理的来源、误差边界、丢样/重启/config epoch 失效路径，才能决定这类来源是否有资格做静态配对。不能用 latest 补缺样。
- 候选编入的 `SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED` 为 0。当前 descriptor/physical/instance/config 可声明配置身份，但不能证明同型号芯片更换或唯一硬件身份；UNKNOWN 必须保留。INSTALL 的 boot、source epoch、parent intrinsic 完整快照目前没有真实冻结接口，不得从 LOGFILE 的 unknown 或 session ID 推断。
- GSHC `MaintenanceOwner` 的 `_claim_lock`/单槽 jobs 保护单次作业；GUI MAG 占用也不是 INSTALL 整会话 owner。idle STATUS/DIAG、TF、普通 console 仍需在同一 reader 上服从安装会话租约。现有 transport 只返回一个匹配行，并在多于 32 条无关行时失败，不能直接拿来接收允许 128 条事件的 INSTALL exchange。应使用显式有界请求/返回类型，保存全部原始部分，满槽即失败，不能丢样换取响应成功。
- target 必须让 INSTALL 与 LOGFILE 活动作业、legacy MAG 修改、CAL/ALIGN 和所有 START 入口共享可审计的控制事务门禁。当前没有 INSTALL owner，因而整会话互斥是 **NOT PROVEN**；不能仅在 PC 按钮上互斥。安装释放不得解除 LOGFILE ENTER 的重启锁存，也不得改变 MAG 的 APPLY/SAVE 或 TF 持久化语义。

## 拟修改模块与恢复实施顺序

以下只是写集提案，未执行：

1. owning core payload 新增 `System/Calibration` 采集服务/头和只读原始接口；DeviceTask 原始生产者 tap，在各 source owner 的一致快照边界发布。保留所有现有 INS/日志队列容量及消费者，不从其队列偷取样本。
2. `System/Src/system_console.c`、`APP/Src/serial_task.c` 及维护 0.1 文档接入显式 CAPS/INFO/BEGIN/FACE/POLL/CANCEL/STATUS。解析长度、事件排空、单周期工作和清理有静态上界；旧维护 0.0/0.1 grammar/响应和 MAG 不变。
3. lifecycle/CAL/ALIGN/MAG/LOGFILE 的 owning 控制入口接共享事务门禁；原始采集不修改校正、READY、安装对象或 TF，不接通 APPLY/SAVE/UPLOAD。
4. GSHC `MaintenanceOwner`（现位于 `ui/file_transfer.py`，只改后台逻辑）及 `transport/file_service_backend.py` 增加 typed 会话租约和有界样本交换；新增 transport adapter 连接既有 installation backend/worker。保持 GUI 布局、第四页及旧固件显式禁用。
5. 只有独立配置/内存布局、完整预算和 source 时间/身份及互斥契约先成立，才做小型独立生成、Host 正常/故障反例、emitted power10/architecture、真实静态分析、ARM 编译链接和实际 artifact/stack 报告。新输入的栈证明必须按原规则审查，不能自动加入 allowlist。

本次未选择关闭现有日志/功能、变更内存布局或缩减任何缓冲。恢复实施需要先明确一个满足上述边界的独立资源方案；本报告不授权该变更。

## 可重放证据及执行状态

命令：`python -B .work/dev013_installation_capture_gate_20261019_v1/audit.py`。它只读候选 ELF/map/ssdiag/历史栈报告和 17 个当前源码/契约输入，重算 section/带宽并比较前后 hash，写本任务自己的 [audit.json](../../.work/dev013_installation_capture_gate_20261019_v1/audit.json) 与 [inventory.json](../../.work/dev013_installation_capture_gate_20261019_v1/inventory.json)。未复制仓库/工具链，未连接串口或探针，未删除历史文件。

6 个保护构建物（ELF、BIN、map、stack-budget 和两个 ssdiag）前后 hash 一致；ELF SHA-256 为 `7056eac7d4de282eebf2f7b1f637ca1b30948e192eb086167121860d763c2f44`，与既有已烧录记录一致。审核命令成功代表只读审查执行成功，**不代表采集实现或固件门禁通过**。本轮未执行新 Host/power10/analyzer/ARM/栈测试；上轮软件 167 passed 的范围和证据不变，不移用为本轮固件验证。

阻断状态：**工程资源门禁停止，目标接入未执行；非权限拒绝、非连接故障、非结果不确定。** 本次重试模型执行正常，没有未完成生产文件操作。后续 live owner/固件候选尚未交付；稳定 main、现有已烧录工程、M9N 暂停任务、GUI 布局、APPLY/SAVE/UPLOAD 均未变。
