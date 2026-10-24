# 0.1.3 安装标定：自动分段契约与 GSHC 软件接入

2026-10-19；owner：`installation_calibration_software_20261019`。已按用户选择冻结正常节奏：每面放稳后一次 FACE 事务，由目标自动连续采 TRAIN→HOLDOUT，再提示换面，共六次。这里的“窗口”是采样时段，不是 GUI 窗口；不要求用户启动两段，不增加 GUI 页面或布局。两段原始样本不重叠，但不声称相邻数据统计独立。

## 当前软件交付

唯一会话/样本机器契约为 [installation_calibration_v1.json](../../../contracts/installation_calibration_v1.json)。维护仍为 0.1，AIR M0、SSLOG 0.0 不变。完整 SSIC 新 kind 仍处于隔离草案审查，不在本次正式能力中启用；旧 MAG kind/命令不变。正式 codec 默认拒绝未采纳的 WINDOW/UPLOAD/PUT/APPLY/SAVE；隔离实验通过显式 draft 模式继续运行历史回归。

| GSHC 服务 | 职责 |
|---|---|
| `installation_calibration_contract.py` | 读取共享契约，缺失/不兼容直接不可用，不猜默认版本 |
| `installation_calibration_capture_contract.py` | 有界、规范且无重复键的完整 INFO；明确测量时间/接收代理/未知来源；检查冻结的不确定度下界，不建立硬件证明 |
| `installation_calibration_protocol.py` | 有界请求/响应、CRC 样本、配对重组；不打开端口 |
| `installation_calibration_data.py` | 不可变源/坐标/单位/时间/内参来源、有界采集档案与验证回放 |
| `installation_calibration_fit.py` | TRAIN 六面 IMU 内参与 AM 数学候选；SciPy 仅在求解时加载，缺依赖明确返回不可用 |
| `installation_calibration_plan.py` | 每面单事务、分区/原始源去重和验证用途账本 |
| `installation_calibration_backend.py` | 显式能力、绑定、FACE/取消/候选快照、原始记录先写后发布；APPLY/SAVE 硬禁用 |
| `installation_calibration_replay.py` | 只读核对原始分段、原始事件与配对、训练内参/已用验证上下文，不假装重新验证成功 |
| `installation_calibration_worker.py` | 独立线程，单工作/单结果槽、32 个显示进度槽、取消和有界 join |

原实验中 `prototype.py/capture.py/protocol.py` 已变成兼容入口，运行时由以上 GSHC 服务唯一持有，避免保留两份实现。原数值门禁和多解/反射等反例继续覆盖。没有修改 app.py、ui/ 或第四页入口；尚未向现有 MaintenanceOwner 注册 live INSTALL adapter，默认 backend(provider=None) 明确不可用，不会创建第二串口 reader。

## 协商与每面事务

CAPS 必须明确声明维护 0.1、install_contract=1、face_auto=1、check_only=1、sample_format=1 和具体段样本数/容量。普通 0.1、旧 WINDOW、legacy 六面或旧 MAG 支持均不能推断新流程可用；BAD_MODULE/UNSUPPORTED 或缺自动分段能力直接禁用，不替换为旧控制命令。模拟目标还需调用方显式 allow_simulated=True，不能冒充真实连接。

```text
INSTALL FACE <sid> <rid> FIT_CHECK:SIX_FACE:<face>:<attempt>
INSTALL POLL <sid> <rid>
```

只发送一次 FACE 启动，POLL 查询同一事务。目标自行用 rid 的 8 位 hex + T/V 标记两个时段，pose 为 P+同一 rid；时间、序列、face/attempt/binding 全程一致。受理/PENDING 不等于完成；终态 COMPLETE、精确 TRAIN/HOLDOUT 数量、原始 CRC 配对完整、源不重叠全部成立后才原子纳入数据集。丢事件/缺部分/错误计数/换源/超时/取消，保留原始接收事实，整次 FACE 不进入拟合。

原 154-byte 双部分样本草案含“PC 接收时间”槽，此项在真实目标不可能获知。正式契约将该槽固定为零；GSHC 记录本机 batch 出队时刻并注明 `BACKEND_BATCH_DEQUEUE_MONOTONIC_NOT_HARDWARE_CAPTURE`，仅供诊断，不冒充硬件时间或用于源配对。两源 sample_us/target_receive_us 和其时钟来源、不确定度保持独立。

原始记录可在同一个独占创建的 JSONL 文件中按角色/边界区分，已有文件不覆盖。header 冻结契约 SHA、身份/轴映射/单位/内参完整值；接收到的 source_part 原始字节和本机时间先保存，配对后再保存数值行；失败/取消部分仍保留。每次事务完成后才发布原子数据集；没有把控制命令放进 SSLOG。JSONL 的验证用途账本同时保存分析策略、训练所得新内参和验证上下文，以防回放时恢复成“未用过的验证集”。

## 训练、验证与补采

初次六面按已选的 TRAIN→HOLDOUT 连续时段收集；固定动作计划下，所有 TRAIN 可用于对角加速度 bias/scale 与静态 gyro bias，再从原始物理量使用新内参重算 AM 外参。HOLDOUT 不参与任何拟合、优化或候选选择。旧 correction 不再叠加到新 correction 上；MAG 父内参及原始坐标来源按 INFO 精确绑定。

当验证结果已参与补采/调策略决策，旧 HOLDOUT 全部保留为适应过程历史，永不改标为 TRAIN。补采的新 TRAIN 作废旧候选；软件保守策略要求最后一次新训练之后的新 HOLDOUT 覆盖六面。已采到的新验证段可计入，其余面用一次 `CHECK_ONLY:SUPPLEMENT:<face>:<attempt>` 事务只采新验证段，避免边补验证边又改变训练。此为软件防泄漏门禁，不是已验证的统计置信或硬件阈值；缺新证据返回 NEED_FRESH_VALIDATION，不沿用旧验证结果。正常六次操作仍各自自动两段，CHECK_ONLY 仅供改模后的新验证。

改变内参、配置、源、时钟/epoch 或拟合策略会使相关候选失效；原始文件不改。`R_AM` 仅是 mag→acc，未知 `R_GA` 不输出 `R_GM`；静态六面不估计 gyro scale。数值通过仅为 CANDIDATE_ONLY，所有 APPLY/SAVE/upload、START/ALIGN/旧 CAL 控制在新后端均被拒绝。

## 真实采集固件的最小接口（本轮未实施）

以下必须在 owning declarative payload/template 中另批接入，复用既有 Device/Calibration owner，不改已烧录工程：

1. `SystemInstallationCapture_FaceSubmit` 接收 sid/rid、mode、face、attempt、已协商段数量；冻结身份/父内参/源 epoch，一次事务自动转换角色。
2. `SystemInstallationCapture_ImuPush/MagPush` 在现有采样边界传不可变原始快照，保留单位/校正层/源时间/序号；ISR/DMA 只做有界交付，SerialTask 不拟合、不操作 TF。
3. owner `Process` 每周期固定采样/配对预算，完成一个完整 pair 后才转换 TRAIN→HOLDOUT；跨边界源连续且不复用样本。满队列、换源、gap、饱和和超时走普通错误，停止该事务。
4. 有界 `ResultGet/CancelRequest/ReadNextRecord` 为共用维护 owner 提供匹配 FACE/POLL/事件；受理、完成、清理分开。全部 START/CAL/ALIGN/legacy MAG/TF export 入口必须服从真实事务互斥，不能由 PC 模拟 gate 代替。

**原6208 B/8 KiB提案已经被实际资源门禁拒绝**，原分项与停止证据保存在[资源门禁报告](../../../docs/internal/INSTALLATION_CAPTURE_RESOURCE_GATE_20261019.md)。后续隔离两槽布局实测为1960 B CCM、0 B新增主SRAM；它没有实现完整INFO、真实tap和跨任务owner，不能当作采集固件。4096-pair数据集仍在PC，CAPS的pair_capacity表示逻辑FACE记录预算，不表示MCU缓存全部记录。

现有format1为438 B/part、876 B/pair。按20次POLL/s、每回复192 B含CRLF，5 pairs/s下行82.2 kbps，占115200的71.35%；10 pairs/s已经超过115200。5 Hz是待验证输出档位，正常IMU采样率不变，按固定native序号/相位取样，禁止按数值或队列空闲筛选。原始native健康监视、选择后的周期和整体窗口有不同边界，不能只看平均带宽。

2026-10-19后续离线证明加入完整`capture_provenance`快照。新流程拒绝缺字段、重复键、未绑定顶层字段、接收代理/未知测量时间、未知epoch/native连续性；样本不能小报INFO冻结的不确定度。远端清理未知时，即使本地已释放，也不能新开安装会话；超时或取消后返回的回复不再发布成功。历史原始文件保持原字节和记录的契约hash，不能将旧文件重签为新契约证据。具体已证范围、316项回归、ARM分析与停止条件见[离线证明记录](../../../docs/internal/INSTALLATION_CAPTURE_OFFLINE_PROOF_20261019.md)。

## 软件验证与剩余接入

命令：`python -B apps/GSHC/validate_installation_calibration.py --run <未使用前缀>`。执行新后端 mock/回放/worker 测试、原有相关维护/MAG/owner 回归、四页布局及全部历史安装实验。输出固定在已有任务证据目录；每轮使用确认不存在的短测试路径，避免 Windows MAX_PATH，不删除旧目录。准确版本、命令、源快照/hash、失败日志、GUI 指纹和完整结果见 [SOFTWARE_RESULTS_20261019.md](../../../.work/dev013_installation_calibration_20261018/SOFTWARE_RESULTS_20261019.md)。

尚未实现的 live owner adapter、MCU 自动采集与资源证明、打包时正式契约/可选数学依赖交付、目标验证/应用/TF 提交均是明确后续项。没有接硬件、烧录、启动飞控任务、修改稳定 main 或推送发布。没有新增需 Astra 决策的数学唯一性结论；已有全局唯一性、坐标物理来源、阈值/硬件证据继续 NOT_PROVEN。
