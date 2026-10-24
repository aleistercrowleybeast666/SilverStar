# 安装标定采集：现有预算内的流式方案评估

2026-10-19；owner：`installation_stream_resource_experiment_20261019_v3`。按本轮授权使用 Astra 做只读底层评审，并运行隔离布局、编码和有限队列实验。基线 HEAD：`7896c1d09a7f9138c41cdac35beef38347d94b78`，分支 `feature/usb-transport-0.1.3-20261013`；工作区已有其他未提交工作，不能把 HEAD 当成本轮完整源码。精确实验输入另存字节快照。

**结论：小缓冲流式方案通过隔离资源模型，但真实 MCU 接入仍为 NOT PROVEN，不得启用。** ARM ABI/link 实测新增 **1960 B CCM、0 B 主 SRAM**；在原候选 CCM 余量 2632 B 内，剩 672 B。它没有完成真实采集、完整 INFO 编码、RTOS 所有权或整机链接；不能据此宣布固件通过全部资源/安全门禁。保留 [前次停止结论](INSTALLATION_CAPTURE_RESOURCE_GATE_20261019.md) 的历史范围，不改预算使原 6208 B 方案变绿。

本轮只新增本报告、隔离实验及证据，没有修改生产源/模板、已烧录候选、GUI、TF/MAG 保存语义或稳定 main，没有硬件操作、推送或发布。APPLY/SAVE/UPLOAD 仍关闭，暂停的 M9N INT32_MIN 任务未触碰。

## 1. 102400 B 是什么预算

STM32F407 的普通 SRAM 为 SRAM1 112 KiB + SRAM2 16 KiB，另有 64 KiB CCM 和独立 4 KiB backup SRAM；不能把这些区域相加后当成任意可互换、可供 DMA 使用的连续空间。[ST DS8626 Rev 12，第 22–23 页](https://www.st.com/resource/en/datasheet/stm32f407vg.pdf)

当前候选 `D:/stm32_project/SS_0_5_CAL_TF_CANDIDATE_20261018_01` 的 linker 普通 RAM 为 128 KiB，CCM 为 64 KiB；heap=0，`_estack=0x20020000`。owning [artifact checker](../../apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_firmware_artifact.ps1) 在物理区域检查之外，对 legacy 布局使用 **100×1024 B** 的项目预算，提示语为 reviewed full-rate logging budget。最早找到的可达基线提交 `2763bb8f6a92973f21c33babd3a0f57a22cbc783`（2026-09-28）已经包含该条件；未找到更早的定量推导。历史原文和提交信息保存在本轮证据中。

| 当前真实 ELF 项目 | B |
|---|---:|
| `.data` / `.dma_bss` / `.bss` | 1140 / 10952 / 89176 |
| `._user_heap_stack`（已有 reservation） | 1024 |
| 主 SRAM section 和 / legacy 门禁 / 余额 | 102292 / 102400 / **108** |
| 主 SRAM 地址跨度（包含 4 B alignment hole） | 102296 |
| `.ccmram_bss` / 物理上限 / 余额 | 62904 / 65536 / **2632** |

128 KiB 与 100 KiB 的 **28672 B** 差额是该策略留下的空间，不是发现了一个硬件保留区，也不是已经证明的 MSP/ISR 栈余量。已有 1024 B reservation 已计入，不得再重复扣除。当前 checker 另有 auto 布局分支将该策略降为 warning，本轮不切换布局、不调阈值、不搬移或缩减既有任务/日志/驱动缓冲。完整候选 ELF hash 为 `7056eac7d4de282eebf2f7b1f637ca1b30948e192eb086167121860d763c2f44`。

## 2. PC 本来就负责拟合；6208 B 是采集缓存

现有 [GSHC 安装后端](../../apps/GSHC/docs/INSTALLATION_CALIBRATION_BACKEND_20261019.md) 已负责原始数据、重放、拟合、激励检查和留出验证。把求解搬到 PC 不是新的省内存动作。原 MCU 预算分解如下：

| 原提案 | B | 最小流式替代 |
|---|---:|---|
| IMU 8×96 | 768 | 单个待配对原始 source 88 B |
| MAG 8×64 | 512 | 单个待配对原始 source 88 B |
| 配对 16×192 | 3072 | 两槽，每槽 2×154 B body + pair/cursor =316 B，共 632 B |
| owner/诊断 | 640 | 完整冻结 metadata 640 +事务 256 +SHA workspace 128 +编码游标 32 +owner/连续性/故障 96 =1152 B |
| 新 RX | 192 | 新增 0；沿用 SerialTask 自有 192 B 行缓冲 |
| 新 TX 2×512 | 1024 | 新增 0；仅在 SerialTask 独占期间使用现有 3072 B response scratch |
| **合计** | **6208** | **1960 B CCM** |

原 6208 B 是估算，也没有充分覆盖 INFO/hash/事务。新布局用 ARM 编译器真实 `sizeof`：冻结 metadata 实际 600/预留 640 B，事务实际 192/预留 256 B，整体 alignment=8，静态上限 2048 B。按上限预留时 CCM 还剩 584 B。两组 bias/matrix 等内参以 double 冻结；pending source 的 float 只对应现有 float provider，不宣称通用 double 源无损。

职责保持清晰：MCU 监视 native 序列、按事先固定规则选择样本、冻结身份/校准代次、做有界配对和分片发送；PC 完整保存**所选样本的原始 body/序号/源时间及收到的原始行**，计算并验证参数。将来 MCU 只接收经过验证的小参数快照、通过已授权生命周期使用 TF 保存并执行运行时校正；本轮不开放这些操作。此处“完整”不是承诺上传驱动全部 native 频率数据，也不是保证断线前所有在途字节均已送达 PC。

## 3. 最小流式事务

1. BEGIN 原子获取全会话 lease，确认 TF export/其他安装或 MAG 写操作空闲，冻结 boot/source/config/内参代次和来源说明；CAPS/INFO 在 FACE 前完成。不可持有指向可变配置的指针来冒充快照。
2. 在源生产点监视 native sequence/epoch/gap，用会话冻结的固定 stride 或时间窗挑选低频样本。禁止轮询 latest 冒充完整序列，禁止队列满后临时降采样。明确记录 source 序号和选择策略，未被选择的帧是有意抽取，native 缺帧是故障。
3. 单 pending IMU +单 pending MAG 有界配对；不满足 skew/uncertainty/连续性条件就失败。pair_id 单调、阶段边界在采集前冻结。TRAIN 完成后转 HOLDOUT，保留各源的边界序号及源时间，PC 从原始记录核对无交叠；不能按主机接收时间分割。连续静止数据的两段不等于统计独立验证。
4. 两槽分别保存完整的 IMU/MAG canonical body。消费者每次只编码一行，用现有 SerialTask scratch；整行被正常 TX ring 接收后才推进该 part 的 cursor，两 part 都接收后才能回收槽。第二 part 暂拒收不重发已经接受的第一 part。并发借用、发布和取消必须有明确握手；顺序模型不证明 RTOS 实现。
5. 满队列、源超时、epoch/config/boot 改变、序列缺口、断线/租约过期均使当前 FACE 失败，保留失败证据，不将残缺数据标 COMPLETE。CANCEL 先禁止新采集/发布，等待 consumer lease 归还并有界清理，再报告 cleanup_complete。
6. `(sid,rid,request digest)` 保持命令幂等：同请求重试返回同一事务状态，不重开 FACE；同 rid 不同 payload 拒绝。小终态缓存不等于无限原始样本重传。缺 part 必须判数据不完整；重新采集应使用新 attempt，不能伪装原请求重放。重连先核对 boot/session，重启后旧 sid 失效并新建会话。

640 B 快照包含两源 descriptor/physical/instance/model/driver/config/epoch/选择策略、内参 bias+matrix、gyro bias、磁参考量、坐标映射、boot/binding/内参摘要/代次和质量策略。常量名称/单位可留在 rodata。**这只是可表达布局，尚未证明当前接口能提供全部字段，或全部动态边界均能放入预留事务。** UNKNOWN 身份不能由配置 ID、型号或 MCU UID 冒充每颗传感器唯一身份。

现有 INFO 上限 8192 B 不应新建同尺寸 RAM：可从不可变快照分 48 B 页生成并增量 hash，冻结 canonical 内容后重复读页。主机目前使用的 sorted-key compact JSON、浮点表示（1/1.0、指数、-0）必须逐字一致；128 B SHA reserve、增量游标和最坏循环/耗时尚未实际实现。禁止每次 POLL 重新做无界完整 hash。

## 4. 维护协议及最坏带宽

沿用维护串口 0.0/0.1 的边界和既有 [installation contract](../../contracts/installation_calibration_v1.json)，旧固件保持 explicit unsupported；不增加维护协议版本，不把控制命令放入 SSLOG。format 1 body=154 B，hex=308 字符，最大 sid/pair/ctx 后 **438 B/行含 CRLF，876 B/对**；本地 NUL 需第 439 B。隔离 C 编码器与 Python CRC/golden 字节一致；这是编码测试，不是有效传感器语义样本。

建议仅对 INSTALL progress/terminal 的有限字段设计 **192 B 含 CRLF** 的上界，不能缩减现有通用响应上限或漏掉 mandatory error code。已通过当前 GSHC codec 的示例长度为 progress164、complete157、error164、cancel86 B；必须继续覆盖全部错误枚举/最大字段，才可将 192 B 作为生产界限。CAPS/INFO 预传不算入 steady-state，但单独限时。

以下假设 8N1、每秒 20 次 POLL、每个响应都占满 192 B，独立全双工方向分别算：

| pair/s | 样本下行 B/s | 加 POLL 下行 kbps | 115200 利用率 | 230400 利用率 |
|---:|---:|---:|---:|---:|
| 2 | 1752 | 55.92 | 48.54% | 24.27% |
| **5** | **4380** | **82.20** | **71.35%** | **35.68%** |
| 10 | 8760 | 126.00 | 109.38% | 54.69% |
| 20 | 17520 | 213.60 | 185.42% | 92.71% |

POLL 上行最大 58 B×20=11.60 kbps，CANCEL 请求 63 B；不得与下行直接相加。若继续按通用 511 B +CRLF 回复预算，仅 POLL 就占 10260 B/s，5 pairs/s 合计 146.4 kbps，115200 不可行。其他日志/错误输出、HAL/DMA 及调度延迟未被这张算术表证明；不能把剩余百分比直接当作实时余量。

可选 base64 把 154 B body 缩到 208 字符，按同一 envelope 为338 B/part、676 B/pair，较 hex 减少22.83%。本轮未实现，且不能悄悄替换 format 1：需要新 sample-format/capability 协商、旧解析器显式拒绝及交叉测试。优先保留 hex，先证明5 Hz目标和短回复；不为节省带宽另造维护0.2。

## 5. 静态采样、时间及用户代价

5 pairs/s 是资源设计起点，不是精度资格结论。静态标定需要足够稳定时间、噪声/重复性、方向激励和留出验证，不要求为了“高频”而上传每个 native 帧。每个 FACE 例如 TRAIN16+HOLDOUT16，在5 Hz下预留6.4 s，另加2 s稳定+条件性0.5 s排空=8.9 s；它只说明10 s预算存在算术可能，**不证明16对足够**。64+64在10 Hz已需12.8 s，不能声称符合10 s上限。

降低输出率的代价是同等样本数需更久稳定；减少样本数必须另做噪声、激励和重复性资格，不能以降低验证质量换预算。需要倾斜补姿态时保留该动作。仍按 [原设计](INSTALLATION_CALIBRATION_0_1_3_DESIGN_20261018.md) 先磁旋转、后六面并复用原始数据重算；不把六面称为完整陀螺尺度标定，不把重力和磁场当同向量 Wahba。

当前已烧录候选的 IMU/MAG instance0 路由 JY901B，epoch qualification=0。[MAG adapter](../../apps/SCG/plugins/builtin/silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B/Adapter/Src/jy901b_magnetometer_adapter.c) 明示0x54无测量时间戳，sample/receive 同取解析时 `MagTimestampUs`。这不是硬件同步，不能填 uncertainty=0 或将接收时间用于通过2 ms skew/1 ms uncertainty。必须证明传感器测量/输出/传输延迟界，或另建可审查的静止时间区间资格；当前接口也未提供完整 epoch/uncertainty/gap 字段。因此真实 capability 继续 unsupported/NOT PROVEN。

还需区分 native source health timeout 与被选样本间隔：5 Hz为200 ms，既有250 ms source timeout若按所选样本触发仅剩50 ms jitter，尚未证明。不得在不区分语义时直接拉长超时。

## 6. 互斥、取消和栈仍是阻断项

**整会话资源互斥：** target 从 BEGIN 到 cleanup 在所有入口原子禁止新 START、CAL/ALIGN、MAG 写、LOGFILE 导出、相关配置变化；不抢占已有业务/TF事务，不冻结 INS/logger/drivers，不借用或缩小它们的缓冲。不能用 LOGFILE ENTER 的冻结机制冒充安装 owner。安全恢复及内部 epoch/config 改变仍可撤销 INSTALL，不能为了会话锁阻止恢复。

GSHC 当前 `MaintenanceOwner` 主要按 job `_claim_lock`，并不是完整 INSTALL 会话 lease；需单 reader 和会话 gate，idle STATUS/DIAG、console 和TF事务不能穿插。现 exchange 单匹配回复/超过32无关行即失败，不足以处理最多128个 sample events。需有界 typed stream dispatch、原始证据保存和显式缺片错误；不是增大无关行丢弃阈值。

**缓冲复用与取消：** 当前 UART write 路径在临界区检查空间、CPU复制整行到普通 TX ring，接受或0；所以 scratch 可在接受后复用，但接受不代表已到主机。HAL start 失败也可能留下已接受队列，必须通过诊断/超时失败。新增 CCM 指针不得直接交给 DMA。现异步 event scratch320 B小于438 B，不能使用。

普通TX ring4096（可用4095），priority1024（可用1023）；DMA最多128 B一次并可在块间重选priority。将 cancel ACK 放 priority 可能插入一个438 B样本行中间，破坏行协议。建议同普通FIFO有序发送并停止新增，直到能证明完整帧仲裁。

115200下排空4095 B+192 B ACK至少372.14 ms；若再计1023 Bpriority则460.94 ms，500 ms只余39.06 ms供RX解析、调度、中断及故障处理。持续priority写入、HAL延迟尚无界。因此 **500 ms cleanup 为 NOT PROVEN**，两槽也不保证任意400 ms主机停顿；已有占用、burst和半发送槽都会缩小余量。队列溢出必须可见失败。

**栈：** 隔离 ELF 的四个实际函数 frame 为16/20/32/24 B；反汇编直接调用路径 `Experiment_Entry → Stream_EncodeEvent → Stream_Bytes` 为76 B，编码器子树52 B。没有 INFO/SHA、真实tap、UART/RTOS调用者和中断，不能拿76 B替代整个新增路径证明。候选历史 Serial margin1200 B、Device416 B只是旧报告的已知路径余额；main/MSP、ISR嵌套、库/间接调用、实际HWM与WCET仍 NOT PROVEN。

## 7. 证据、失败历史与最小后续批次

实验入口：[README](../../apps/SCG/experiments/installation_capture_stream_0_1_3/README.md)。最新完整结果：[v3 results](../../.work/dev013_installation_stream_20261019_v3/results.json)、[补充只读审查](../../.work/dev013_installation_stream_20261019_v3/post_review.json)、[保留清单](../../.work/dev013_installation_stream_20261019_v3/retained_inventory.json)。

- v1：ARM strict/analyzer/link成功；host golden因Windows文本输出额外转换CRLF失败（439 B）。保留原输入和日志，修正仅涉及host stdout二进制模式。
- v2：布局/编码/7类模型检查成功；后续真实codec审查发现错误回复缺mandatory `code` 而失败，完整后续失败说明保留。不得将v2当成所有兼容性通过。
- v3：严格ARM编译、真实 `-fanalyzer` 编译、独立ARM链接、host golden/参数边界、7类有限流模型检查、当前codec的4个回复及POLL解析均成功。原6208 B反例在同隔离free-CCM区链接按预期失败（exit1），不是被忽略的失败。
- 7类模型覆盖正常32对、TRAIN/HOLDOUT固定分界、第二part拒收、不同初始占用溢出、两个part边界取消、20个相位的500 ms停服、3对burst。它们是顺序有界模型，未模拟RTOS/中断或主机真实磁盘吞吐。
- ARM GNU14.3.1，host GCC16.1.0，Python3.14.0；命令、退出码、stdout/stderr、ELF/map/.su、源码完整字节/哈希留存。候选ELF/BIN/map/stack-budget/两个ssdiag共6项前后hash相同。

本轮**没有**运行新生成固件的 power10、完整Host套件、全固件ARM链接或硬件验证。isolated ELF使用固定空闲CCM窗口、没有启动代码，绝不可烧录。迁入生产时必须走 owning payload 和正常初始化、重新生成独立工程；链接新增库/.data可能改变主SRAM，不能沿用这次的0 B结论。

后续最小批次，均以保持现有门禁为前提：

1. **来源资格与完整快照**：先补真实source identity/epoch/时间质量契约和冻结字段清单，验证JY能否满足静态配对；做canonical INFO/hash交叉向量和最大布局。无法证明则继续返回unsupported，不接硬件采集。
2. **有界owner及传输**：两槽tap/配对、双端全会话lease、普通FIFO编码、幂等终态、断线/取消路径；故障注入覆盖源缺帧、参数改变、半片、HAL错误、满队列、TF冲突。验证新增状态≤2048 B CCM、主SRAM实际门禁≤102400，取消时限达标后才能宣称可用。
3. **独立新生成固件验证**：原样运行power10、相关Host回归、真正静态分析及ARM编译链接、source-graph和完整新增栈路径报告；保留NOT PROVEN的硬件时序/HWM。只有另获硬件授权后才测板级延迟/采样质量。APPLY/SAVE/UPLOAD需要单独实现和验收，不能随采集解锁。

推荐继续研究 **5 Hz固定选择 +两槽 +192 B有界短回复 +PC完整存储/求解**；它值得进入下一软件证明批次，尚不是可上板方案。需要用户权衡的是更长稳定等待与标定动作数量，不能承诺更快且同精度。当前停止原因是来源/并发/时限/完整固件证明未闭合，**没有权限拒绝、连接阻断或执行结果不明**。本轮无清理授权，全部版本证据保留；未删除旧`.work`内容。
