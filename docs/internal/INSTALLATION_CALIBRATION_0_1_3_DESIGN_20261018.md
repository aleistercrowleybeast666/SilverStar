# 0.1.3 安装标定：六面优先的维护串口设计

日期：2026-10-18。状态：只读源码审查 + 待实施设计，不是功能完成或硬件验收报告。第 1–9 节保留初次只读审查范围；后续获准的隔离 B0/B2a 实验实现及限制见第 10 节。

范围：仅新增本文；不改生产源码、协议合同、稳定 main、SCG 坐标配置或 TF 存储实现，不触碰暂停的 M9N INT32_MIN 任务。审查基线为开发分支 `feature/usb-transport-0.1.3-20261013`，HEAD `7896c1d09a7f9138c41cdac35beef38347d94b78` 加当前未提交工作；不能把这些实现归于该提交本身。下文“已有”指本次读到的源码，不代表已烧录或已实测。

## 1. 决策与当前真实行为

**默认流程保留“磁力计旋转 → 六面 IMU，同时收磁数据 → 自动质量判断 → 验证/应用/TF 保存”。不要求斜放，不要求用户量角。** 六面充分时直接接受；不足时先复用已有数据，再提示“保持指定面朝上，换一个朝向后放稳”。仍不充分就拒绝保存外参；不强行输出解。任意斜姿态无需精确已知角度，但不列入默认步骤或强制补样。

必须分开三个用途：

| 用途 | 当前行为 / 建议边界 |
|---|---|
| 上电静态检查、零偏 | 当前不是统一的“每次上电必做六面”。无采样 procedure 的 build 自动 NONE/Identity/READY；有 procedure 时等待显式选择，也允许 NONE。ONE_FACE 是主动静态采样路径，不可描述成已有全自动启动零偏服务。单次静止不能观测完整 MAG–IMU 外参。 |
| 现有主动六面 | GSHC 的 `CAL_START(SIX_FACE)`、逐面 `CAL_FACE`、停止/重采/Reset 已存在；必须遵守 Capability、真实 PREFLIGHT_STATUS 与 readiness。它得到加计三轴零偏/对角尺度和静态陀螺零偏；代码把 `gyro_scale` 固定为 1，不能称完整陀螺尺度/非正交标定。 |
| 安装标定 | 长期有效的传感器身份、轴系/内参/外参组合；独立会话、质量验收和 TF 保存。上电只加载并检查匹配性；不覆盖当前预飞事务，不因“安装已保存”伪造 Calibration/Alignment/START READY。暂不 SPI Flash。 |

用户每次**实际执行**主动六面时，可以复用同一内部采集服务生成外参候选并验证；该能力目前未实现。第一批仍在维护串口会话中由 PC 求解。未来无线六面可以共用内部采集钩子，但 AIR M0 没有完整配对数据与候选上传通路；参考其 UX 不等于扩展无线帧，也不应偷偷增加 MCU 在线求解或自动持久写入。可合格更新的前提是已显式进入相应会话、内参/身份匹配和验证通过。

## 2. 已实现项与缺口（源码证据）

以下路径以仓库根为准；`C` = `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload`，`S` = `apps/SCG/plugins/builtin/silverstar_device_storage_sd_sdio_fatfs/payload/Devices/Storage/SdSdioFatFs/Adapter`。

| 已核对的实现 | 证据 / 尚缺内容 |
|---|---|
| 维护串口 0.1 兼容 0.0；ASCII 行、请求正文 ≤191 bytes、通用 parser ≤5 tokens；DIAG/LOGFILE 单行 ≤511 bytes | `C/System/Src/system_console.c`；[维护 0.1 文档](../../apps/SCG/plugins/builtin/silverstar_protocol_maintenance_serial_0_0/docs/MAINTENANCE_PROTOCOL_0_1.md)、[LOGFILE 合同](../../contracts/log_file_service_v1.json)。3072-byte 通用响应缓冲不意味着所有客户端支持同样长的行。 |
| `MAG i STREAM START/STOP`、`MAG i CAL [READ]/APPLY <hex>/SAVE/CLEAR` | `system_console.c:3787,4600–4719`。原始物理量磁流最多 20 Hz；84-byte 小端内参对象、CRC32、身份和数值检查已有。CAL READ 只读状态，**没有读出完整参数**。 |
| PC 磁椭球拟合与有界采样 | `apps/GSHC/services/magnetometer_calibration.py`：128–4096 点、八象限各 ≥4、条件数 ≤25、RMS/最大残差 ≤参考场的 0.15/0.50。已有 `MagSampleCollection` 只保留 XYZ 点和最后序号/时间，不保存每点时间/配对/阶段，不能直接充当安装标定原始档案。 |
| 当前 MAG APPLY/SAVE 回滚和身份绑定 | `C/System/Calibration/Src/system_mag_calibration.c`：APPLY 修改 RAM、形成 candidate、generation=0；SAVE 完成才提交代次；失败恢复 committed 并保留失败状态，重试不是已验证的通用幂等事务。新增未提交的 `system_installation_calibration_if.h` 已有 **SSIC schema 1**、32-byte 绑定头；仅实现 `MagEllipsoid`，parent intrinsic CRC 必须为零。不能据此声称已支持外参。 |
| TF 保存 owner 与任务快照 | `S/Src/mag_calibration_storage.c` 经 LoggerTask 单 endpoint/单 pending 服务；`persistent_storage.c` 使用 SSOB 双槽、CRC、sync/关闭后读回，payload ≤512 bytes、代次耗尽拒绝。`mission_snapshot.c` 已记录 IMU correction 全值和 MAG generation/hash 引用；不是每个磁对象及外参的完整独立历史副本。 |
| 六面状态与数学 | `C/System/Calibration/Src/system_calibration.c:405,749,854`；`silverstar_algorithm_calibration/.../imu_six_face_calibration.c:37`。只累计 accel/gyro 静态均值，**没有同步磁采集**；旧六面均值不足以重建缺失的磁配对。 |
| GSHC 控制与串口互斥 | `apps/GSHC/app.py` 的 Controller；`services/state_model.py`；`ui/file_transfer.py:517` 的 `mag_acquire`；`transport/magnetometer_transport.py` 共用 MaintenanceOwner，不另开端口。已有 GUI 侧 MAG/TF job 互斥和停止确认；尚非端到端安装会话锁。 |
| LOGFILE 导出 | `C/System/Src/system_log_file.c`：CAPS/STATUS/ENTER/LIST/META/READ/POLL/CANCEL；最大块 64 bytes、一个 mailbox、30 s 无活动超时。ENTER 是直到重启才解除的维护预约；停止/排空/关闭 writer 后才 Ready。CANCEL ACK 不代表 cleanup 完成，也不退出维护预约。 |

额外边界：已有 MAG EVENT 的 `sample_us` 经 `SystemConsole_TimestampDisplay()` 饱和为 uint32 最大值，约上电 71.6 分钟后不能当作继续递增的采样时钟；新配对记录应使用现有内部 uint64 时间，不改变旧 EVENT。MAG 解码器还严格匹配原有字段集合，不能直接往旧行追加会话字段。

## 3. 数学与坐标契约

软硬磁标定修正零偏和椭球形变，但“变成球”不确定磁坐标相对加计的旋转：球面范数对正交变换不变。固定当前对称正定软磁矩阵约定后，仍需估计外参；也不能把机械小角先验套在任意旋转自由度的内参分解上。

令校正后、归一化的静态加速度方向为 `a_i`，校正后归一化磁向量为 `m_i`，`R_AM` 把磁坐标 M 映到加计坐标 A。重力/比力符号在数据契约中固定，则：

```text
a_iᵀ R_AM m_i = s
min Σ w_i (a_iᵀ R_AM m_i − s)²,  R_AM ∈ SO(3), |s| ≤ 1
```

`s` 是未知场方向与静态重力方向的夹角余弦，不应硬编码为磁场强度或零。若使用传统磁倾角（相对水平），它与上述夹角互为余角，并须处理比力符号。重力和地磁不是同一个空间向量，不能直接解 `R m_i ≈ a_i` 的 Wahba 问题。以上依据 [AM-Align 论文 §II](https://construction-robots.github.io/papers/59.pdf)；论文 §III-A 明确展示四对观测的多解，README 的“四对”不是唯一性保证。[项目入口](https://github.com/JokerJohn/AM_Align) 可供追溯；此次只查阅论文/仓库页面，未下载编译其算法，也不假定页面所述可执行程序已可取得。

以下为项目验收设计及待仿真验证推导，非已实现算法：

- 六面不等于唯一外参。按独立静态窗口加权，不能把同一姿态的数百重复点算成数百种激励。先同时检查磁内参质量、静止性、配对时间和场稳定性，再检查旋转候选、解间距离、残差和激励。
- 在候选处 `v_i=R_AM m_i`，左扰动雅可比 `g_i=v_i×a_i`；消去未知 `s` 后，对加权中心化的 `G` 检查三个奇异值、最弱方向和条件数。局部满秩不证明全局唯一，仍须检查相隔明显的低残差候选。阈值由冻结的噪声/仿真用例确定，不借用磁椭球的条件数门限。
- 留出验证按独立时间窗口/朝向分组，避免相邻点随机拆分泄漏。六面每面的训练/留出窗口可检验重复性，但相同姿态留出不能解除几何多解；若候选仍不分离，自动进入 NEED_SAMPLES，不进入 VALIDATED。
- 补样优先保持一面朝上换朝向。可选 `a` 与 `G` 最弱旋转方向 `u_min` 尽量垂直的面；同面 `a` 不变，`g` 在其垂直平面变化，不能选 `a ∥ u_min` 却宣称修复该弱方向。每补一段重新评估，不保证一次成功，也不要求精确旋转角。
- 六面翻转过程的 gyro/MAG 时间序列可以保留，后续用已验证的陀螺坐标/偏置、时间同步与积分误差模型作额外约束。动态加速度不当作静态重力；本批不靠未经验证的动态约束强行通过，也不把它称作陀螺尺度标定。

轴系明确区分 A（校正后加计）、M（按固定内参约定校正后的磁）、G（陀螺）、B（导航机体）。`R_AM` 不是自动得到的 `R_GM`；若已知 `R_GA`，才有 `R_GM=R_GA R_AM`。若厂家/驱动保证加计陀螺共轴，则把该假设、版本和证据写入快照；未证实则不得宣称完整 IMU 外参。现有接口字段名 `_b` 也不是机械安装校准已验证的证据；必须写清 provider 已做的轴映射，禁止再次重复旋转。

先磁后六面没有必须重做动作的数学依赖：保存未经本次软件校正的原始物理量，六面完成后统一应用最新加计/磁内参、重新归一化并求解外参。磁旋转阶段若同步保留了合格静态停顿，也可重用。内参/轴映射变化使旧外参绑定失效，应重算重验，不能直接沿用旧矩阵。旧文件缺少配对磁数据时明确“不可重算”，不补造样本。

## 4. 模块、采样与状态

GSHC `InstallationCalibrationSession` 持有一次会话、原始档案和纯数据 fit/quality 服务；求解在 worker，GUI 只展示状态。共用 MaintenanceOwner/现有传输抽象，不用第二串口 reader。六面 UI 复用 X±/Y±/Z±、WAIT_FACE/COLLECTING、重采与失败提示；以操作上下文路由至现有 AIR 或维护串口，不能同时发两路控制。

固件新增独立安装会话 owner，复用 `SystemCalibration` 的静止检测/逐面采集逻辑与 source lock，避免复制一个六面状态机；具体共享采集接口须在批次 B1 设计。Device/Calibration 采样 owner 生成有界快照，SerialTask 仅收发和入队，LoggerTask 独占 TF。PC 拟合不进入 ISR/SerialTask。任一关键状态不一致走已有普通错误或有界安全失败路径。

每个原始记录至少包含：

| 类别 | 必须保留的字段 / 规则 |
|---|---|
| 身份 | `session_id`；两个 endpoint 的 class/descriptor_id/instance/physical_device_id、driver/model 标识、安装/配置 digest、IMU source/config epoch；板级 UID 若不可用明确 UNKNOWN，不能拿 COM 名或实例号代替硬件序列号。 |
| 坐标与单位 | `frame_id`、轴向/手性、已做变换和 correction 层；原始计数及单位可用 mask；原始物理 accel m/s²、gyro rad/s、MAG μT、温度及有效性。厂商内部校正无法旁路时标明，不能叫 ADC raw。 |
| 时间与顺序 | 各源 uint32 sequence，uint64 boot-relative sample_us/receive_us；时钟来源/不确定度、pair_id、pair_dt_us、丢包/饱和/gap/重启标志。PC 接收时间仅用于链路诊断，不伪装硬件同步。 |
| 阶段 | MAG_ROTATE / SIX_FACE / SUPPLEMENT / HOLDOUT，face、window_id、attempt、接受/拒绝原因、所用内参 hash。翻面动态记录另标 DYNAMIC，不混入静态样本。 |

静态配对基于时间相容的独立窗口和真实样本，不把两个异步 latest 值直接称同步；窗口内检查运动、方差、场强变化、有效比例、时钟误差。窗口/偏差门限必须显式配置并记录。队列和样本数封顶；满队列计数并停止该窗口，不能静默丢原始数据后宣称完整。磁拟合暂沿用 4096 点上限；IMU/配对/动态段另设 CAPS 宣告的固定容量，不能靠 D 盘或 MCU 无界缓存。

```text
IDLE → MAG_COLLECT → MAG_FIT → FACE_WAIT ↔ FACE_COLLECT
     → SOLVE → NEED_SAMPLES ↔ FACE_WAIT
             → VALIDATED → APPLIED_RAM → SAVE_PENDING → SAVED
任意非提交阶段 → CANCEL_PENDING → CANCELLED
错误 → FAILED；连接/设备身份不确定 → UNKNOWN（不得显示成功）
```

`six_face_mask=0x3F`、`imu_ready`、`extrinsic_validated`、`applied`、`saved` 分别表达；不共用一个 READY。进度分为当前阶段 accepted/required、face mask、拒绝原因和等待原因；总量未知显示阶段而非伪造百分比。质量失败应带 `suggested_face/action`；默认文案为同面换朝向，不出现“必须斜放”。

## 5. 最小兼容命令扩展（提案，不是现有命令）

保持维护协议 **0.1**、AIR **M0**、LOGFILE **v1**、SSLOG **0.0** 现有边界。不因为产品 0.1.3 升级这些版本。现有 `MAG`/`CAL` 命令、84-byte 对象、EVENT 和响应语义原样保留；新会话通过可探测的可选 `INSTALL` 命令族承载缺失的会话/配对/完整对象功能。旧固件返回 BAD_MODULE/UNSUPPORTED 时只提供已有功能，不猜测支持。

首次实施在 `contracts/` 建立唯一机器可读命令/对象合同与 golden，本文不充当第二份 wire 权威。复用现有 ASCII codec、限长检查、单请求 mailbox/POLL 模式；不同 operation 的会话和 mailbox 不能相互冒充。安装对象是新能力需要的有类型数据，不另造“Maintenance 0.2”或全新传输。

| 提案语法（每条 ≤5 tokens） | 行为 |
|---|---|
| `INSTALL CAPS`；`INSTALL INFO <imu>:<mag> <cursor>` | 可选操作、固定容量/最长行/超时；分页 endpoint、坐标、配置和板身份。INFO 返回短期冻结的 binding token，绑定所选两个 endpoint、配置、基准代次；任一变化使 token 失效。未知身份显式报告。 |
| `INSTALL BEGIN <sid> <rid> <binding>` | PC 生成全新非零 128-bit sid（32 hex）；rid 为单调非零 uint32；binding 绑定选定 IMU/MAG、当前配置及预期基准代次，不接受悄悄换源。固件单活动会话。 |
| `INSTALL DO <sid> <rid> <action>` | 有限枚举：MAG_START、MAG_STOP、SIX_START、FACE_XP/XN/YP/YN/ZP/ZN、FACE_STOP、VALIDATE、APPLY、SAVE、CANCEL；参数不以任意字符串脚本执行。六面动作调用同一内部服务。 |
| `INSTALL PUT <sid> <rid> <offset>:<hex>` | 暂存完整候选，单块最多 48 bytes，保证最坏 sid/rid/offset 仍 ≤191 bytes；固定总长度和对象 CRC/内容 digest 随首块头声明。重复相同 offset/bytes 接受，不同内容冲突；不完整时拒绝 VALIDATE。 |
| `INSTALL POLL <sid> <rid>` | 返回匹配 operation/sid/rid 的 PENDING 或终态；受理不等于完成。 |
| `INSTALL STATUS <context> <role>:<cursor>` | context 为活动 sid，或 INFO 返回的 binding token；后者只允许 ACTIVE/SAVED 查询，便于重启后核查。role 固定为 STATE/CANDIDATE/ACTIVE/SAVED；有界分页，含相同 snapshot_seq。对象角色首游标 0 固定快照并返回 snapshot_token、长度、代次、hash；页间变更需重新读，不拼接不同代次。 |
| `INSTALL READ <context> <snapshot_token> <offset>` | 按冻结 token 分页读**完整**对象，返回角色、代次、hash、offset、长度、块 CRC；token 过期或对象变化则 STALE。不得用当前隐式可变状态猜角色。 |

BEGIN binding token 的长度/有效期、PUT 对象字节编码和 CAPS 字段必须在 B0 一并冻结后才能写 parser；两端不得各自猜格式。binding/snapshot token 使用有类型前缀，与 32-hex sid 可区分，长度最多 32；冻结 token 属于当前 context/连接的只读快照，不是可执行文件路径。统一保持 5-token/191-byte 上限。

新样本使用独立 `EVENT INSTALL ...` 或可轮询的有限块，带 sid/pair_id/类型/完整时间；每行 ≤511 bytes，身份常量引用会话的冻结描述页。若拆成 IMU/MAG 两行，按 pair_id 完整重组、校验、超时废弃，不能用“最后一条”补缺失值。普通 EVENT 丢失不影响最终 STATUS；状态序号必须让客户端发现缺口。旧 MAG decoder 不接收新类型，安装 decoder 单独解析。

## 6. 验证、应用、保存、重试与互斥

- **验证**：PC 自动质量门限/留出报告通过后，上传完整候选；固件检查有限值、范围、矩阵 SO(3)、身份/父内参/配置绑定、对象长度/CRC、完整质量报告。无独立目标侧观测验证时，只能称“PC 质量通过 + 目标结构验证”，不能让一个 `quality=PASS` 自证有效。关键验收未证明就拒绝外参保存。
- **应用**：目标原子切换整套 RAM 对象，返回 active_digest；不能先发布部分矩阵再验证。旧 committed 快照保留。安装动作占用配置事务并阻止所有 START 入口；变化使旧 Alignment 失效，必须重新满足原有预飞条件。新安装 owner 不能把旧 MAG APPLY 的现有语义改成“只暂存”。
- **保存**：SAVE 请求绑定 expected_base_generation + candidate_digest。仅 LoggerTask 执行 TF 提交；终态须 `saved=1,pending=0,failed=0`、非零新代次以及完整读回内容一致。已存相同内容返回原代次，不重写。失败恢复旧 committed/明确 RAM 角色，保持失败可见；不能把 ACK 或文件存在当成功。
- **幂等**：单活动会话、每次只允许一个新变更请求；缓存最近 `(sid,rid,operation,payload_digest,result)`。同 key 同参数重放结果，不重复采面/应用/写卡；同 key 异参报 CONFLICT；旧于缓存的 rid 报 STALE，不重执行。已提交对象保存事务键/内容 hash，以便保存 ACK 丢失后用读回确认；rid/代次耗尽拒绝，不循环复用。
- **取消**：停止新采样/上传，等待 owner 清理后才 `cleanup_complete=1`。提交前取消保留旧存档；已经到 TF 原子提交点则报告 `already_committed` 及代次，不能虚报撤销。CANCEL 不等于 CLEAR，不删除原始档案/历史参数，也不取消其他会话任务。
- **断线**：UI 立即 UNKNOWN，停止自动业务重试。设备采样/暂存租约建议复用 30 s 无活动模型，另有总 deadline；过期停止采集、清除未应用暂存、回到已提交状态，清理完成才释放资源。新连接只查询，不自动重发 BEGIN/APPLY/SAVE。
- **重启**：首版不承诺断线或跨重启续会话；固件 RAM sid 消失后返回 SESSION_UNKNOWN。已有 LOGFILE `device_id=unknown boot_id=unknown` 不能证明同一启动。重新 INFO，使用只读 binding context 读取 TF 完整对象/保存事务键，判断一次不确定 SAVE 是否已提交；身份不能可靠确认则要求重新绑定，不自动应用。PC 原始档案保留，可在新会话明确导入并重新验证；旧事件不能使新会话前进。
- **TF/链路互斥**：共用现有串口 owner，并在固件 owner 层互斥 INSTALL、LOGFILE 活动作业、legacy MAG 写入、CAL/ALIGN 配置动作与 START。安装会话内部授权的六面操作走同一 owner；其他入口 BUSY/LOCKED，不允许 AIR 或手工 console 绕过。DIAG 可暂停/低频，控制应答优先于样本流。串口排他和 TF 文件系统排他是两个边界，均须测试。
- **导出模式**：安装 BEGIN 不调用 LOGFILE ENTER；标定保存沿用独立 LoggerTask 存储服务。开始导出前先完成/取消安装并确认清理，再显式 ENTER。若已 ENTER，无论取消/断线/导出完成，都不能从安装页面解除其重启要求。SSLOG 用于事实记录/结果快照，不包含可执行控制命令，不扩展 LOGFILE 为任意路径上传。

## 7. 代次、完整快照及可读错误

复用现有 **SSIC 1 + SSOB**，先检查其 kind 和 512-byte 上限再扩展，不能把仅容纳 MAG 的旧包冒充完整安装对象。快照必须包含：两个 endpoint 与板身份/配置、轴系/变换链、加计 bias/scale（或明确模型）、陀螺静态 bias 与未标定 scale 标志、磁 bias/soft matrix/reference、`R_AM`、`R_GA` 或共轴假设、s、算法/门限版本、质量与留出结果、样本档案 digest、每个父内参 hash/代次、candidate/active/saved 角色及整套 installation generation。

多对象超出 512 bytes 时分成有界不可变组件，最后原子提交 manifest；manifest 绑定每件精确内容 hash/长度/代次，全部读回通过才发布整套新代次。不要分别更新三个“当前文件”然后称为原子安装快照。双槽当前值会被后续写入轮换，任务历史不能仅引用可覆盖槽；任务快照应保留实际使用的完整组件字节或已封存不可变对象，保证未来只拿本次资料也能重建。现有 IMU correction 全值与 MAG hash 引用只是起点；与 TF 并行任务协作落地，本文不改其代码。

已有 SSLOG `CALIBRATION_RESULT`/MAG identity/mission snapshot 记录继续表达真实生效结果；完整对象进入配套不可变快照，控制仍只在维护串口。若后续确需新记录，单独走 contracts 与 `.ssdecoder`/Descriptor 的兼容审查，不修改旧容器版本或用离线默认值填补缺失历史。

| 稳定 code / reason（提案） | 用户看到的含义与下一步 |
|---|---|
| UNSUPPORTED / CAPABILITY | 当前固件没有安装标定能力，保留现有 MAG/六面操作。 |
| WRONG_DEVICE / CONFIG_CHANGED / PARENT_CHANGED | 设备、轴配置或内参已变化；保留数据，重新绑定/重算，不能直接用旧外参。 |
| NOT_READY / NO_STREAM / TIME_UNCERTAIN / SAMPLE_GAP | 数据未到、时间不可靠或丢样；重采该窗口，不冒充同步。 |
| GYRO_MOVING / VARIANCE / FIELD_UNSTABLE | 未放稳或磁环境在变；保持该面放稳、远离干扰后再试。 |
| NEED_SAMPLES / WEAK_EXCITATION / MULTIPLE_SOLUTIONS / HOLDOUT_FAILED | 六面动作已完成，外参未通过；先复用数据，再按提示同面换朝向。 |
| BUSY / TF_TRANSFER / CONFIG_ACTION；LOCKED / REBOOT_REQUIRED | 资源被占用或已进入导出模式；等清理，必要时由用户重启。 |
| CONFLICT / STALE / SESSION_UNKNOWN | 重试参数冲突、基准已变或原会话不存在；查询状态，不盲重放。 |
| STORAGE_ERROR / NO_CARD / FULL / VERIFY_FAILED | TF 不可用或保存失败；仍显示具体 RAM/committed 状态，不称已保存。 |
| CANCELLED / ALREADY_COMMITTED / TIMEOUT / UNKNOWN | 分别表示已取消、取消晚于提交、等待超时、结果待核实；超时不等于目标操作失败。 |

协议保留稳定机器 code、reason、sid/rid/阶段；GSHC 做中英文映射并保留原值。现有 legacy `code=FAILED reason=...` 继续原样接受，不为新文案改旧返回合同。

## 8. 最小实施批次与验收

| 批次 | 最小交付与必要测试 |
|---|---|
| B0 合同/数学冻结 | 明确坐标 owner 与 TF owner 接口；冻结 INSTALL grammar/golden、完整对象/身份/父关系、容量与质量阈值。使用合成已知 R/内参验证六面正常、四对多解、六面退化、共线重力磁场、轴符号/旋转转置错误；验证中心化 G 与同面补样策略。多起点局部优化不得宣称 AM-Align 全局保证。 |
| B1 采集复用 | 从现有六面 collector 边界加可选有界配对 tap，保留原始 per-sample metadata、静态窗口和翻面标签；旧 AIR 命令/面掩码/Stop/Reset/默认 NONE 不变。测试异步速率、掉样、重序、时间饱和/回退、换源/换 epoch、队列满、同一面重采；缺失 MAG 不伪报外参 READY。 |
| B2 PC 会话与求解 | 共用 MaintenanceOwner，复用六面 UX；先磁拟合后六面联合重算、分组留出/候选区分/NEED_SAMPLES。测试原始档案重放、内参更新使旧外参失效、噪声/异常磁场、共轴假设缺失、取消 worker；默认无斜姿态要求。 |
| B3 目标事务 + TF 完整提交 | 实现能力探测、暂存/结构验证、原子应用/保存、幂等与端到端互斥。Host 注入丢 ACK、重复/冲突 rid、每个 TF 写/sync/close/读回断点、满卡/坏 CRC、重启、迟到事件、generation 耗尽和大对象不完整；旧代次仍可恢复，新旧组件不得混合。 |
| B4 整合及证据 | GSHC/固件 golden 对跑，旧 0.0/0.1 MAG/CAL/LOGFILE 回归；实际 fresh generated 工程运行原样 power10-check、相关 Host、真正 analyzer、ARM 编译链接、source graph/architecture 与受影响栈/链接报告。记录源脏快照/工具版本/命令/退出码/全部失败和 skip/产物 hash。硬件、断电卡恢复、同步精度与导航效果需另行授权实测。 |

B1/B3 的固件修改应进入 owning plugin payload/template，不能只改临时生成工程；正常 Generate 保持用户源码所有权。错误路径保持普通可读失败，不用密度断言替代外部坏包/超时处理。未证明关键合同、全程序栈/时序或质量阈值时，报告 NOT PROVEN；工具通过不等于硬件/飞行资格。

### 8.1 可分派的文件集合和依赖

以下是**未来实现的建议写集**，不是本轮已经修改的文件或扩大授权。`+` 表示拟新增，`~` 表示现有文件修改；`G` = `apps/GSHC`，`P` = `apps/SCG/plugins/builtin`；C/S 沿用第 2 节。`S1` 为与 S 相同的 Adapter 路径，但插件名换成 `silverstar_device_storage_sd_sdio_fatfs_f1`。未列出的生产文件不进入该批；若事实证明缺少入口，先由整合负责人更新写集与依赖。一个文件同一时段只给一个实现任务。

**B0：合同与数学验证，优先分派。**

- 范围/依赖：先独立建立失效用例、六面激励/多解与同面补样验证；最终冻结须接收 SCG 坐标任务的 frame/config/identity 契约和 TF 任务的对象/manifest/恢复边界。只定义安装能力及对象 schema，不升级维护串口/AIR/LOGFILE 版本。
- 写集：`+ contracts/installation_calibration_v1.json`、`+ contracts/installation_calibration_v1.golden.json`；`+ G/tests/fixtures/installation_calibration_cases_v1.json`；`+ G/tests/test_installation_calibration_contract.py`；`+ G/tools/installation_calibration_math_check.py`；`~ 本文`。合同文件的 `v1` 是新对象合同自身首次编号，不是新维护协议。
- 验收：双端可用同一 golden 唯一解释字段/轴系/时间/状态/重试/容量；正常六面可通过，已知多解/退化/错误轴系必须拒绝；同面补样确实改善指定弱方向的用例和不能改善的反例均保留。给阈值来源、噪声假设、算法全局性限制和独立留出规则。未冻结不能把后续 prototype 称为端到端实现。

**B1：FC 有界采集服务；拆成独立模块 B1a 和接线 B1b。**

- 范围/依赖：B1a 在 B0 数据模型后可用合成输入开发；B1b 要等坐标/epoch 语义冻结。只采集原始数据、窗口和质量证据，不在 FC 求解 AM-Align、不保存 TF、不自动发无线数据。安装采集默认关闭，由后续 B3 会话启用。
- B1a 写集：`+ C/System/Calibration/Inc/system_installation_capture.h`、`+ C/System/Calibration/Src/system_installation_capture.c`、`+ C/Tests/Host/test_installation_capture.c`。接口使用有原因的 `SystemInstallationCaptureResult`，无运行期 callback registry。
- B1b 写集：`~ C/System/Calibration/Inc/system_calibration.h`、`~ C/System/Calibration/Src/system_calibration.c`（发布同一 face/window 的开始、接受、拒绝、重采事件）；`~ C/APP/Src/imu_sample_bus.c`（未二次校正 IMU tap）；`~ C/APP/Src/device_task.c`（选定 MAG 的有界独立 sequence tap）；`~ C/Tests/Host/test_system_calibration.c`、`~ C/Tests/Host/test_imu_sample_bus.c`。由整合负责人同批串行修改 `~ P/silverstar_core_0_1_0/plugin.json` 与 `~ C/Tests/Host/run_tests.ps1`，注册新源和测试，不让各任务抢写注册表。
- 验收：旧 NONE/ONE_FACE/SIX_FACE 的面掩码、重采、Stop/Reset、READY 与异常行为不变；源切换、epoch 变化、重复/缺样、异步时间、单时钟不可靠、队列满均有确定结果。没有把异步 latest 当同步；重复 MAG sequence 不重复计激励；静态窗口重采使其旧候选失效。新固定 RAM/栈预算和生成源码检查通过。仅 B1a Host 通过不等于 B1 完成，须包含 B1b 新鲜生成/编译与相关门禁。

**B2：PC 纯数据会话/求解可并行；串口和 UI 接线后合并。**

- 范围/依赖：B2a 只依赖 B0，用 fixture/mock 输入，可与 B1 以及当前 TF、SCG 坐标实现并行；B2b 需要 B0 wire golden，端到端验收另等 B3。原有无线 Controller/FlightControllerState 继续管理无线事务，不往其状态中塞安装外参 READY。
- B2a 写集：`+ G/services/installation_calibration.py`（会话/不可变数据/档案）；`+ G/services/installation_calibration_fit.py`（内参复算、外参/质量）；`+ G/services/installation_calibration_protocol.py`（codec）；`+ G/tests/test_installation_calibration_session.py`、`+ G/tests/test_installation_calibration_fit.py`、`+ G/tests/test_installation_calibration_protocol.py`。只调用现有磁拟合与 packet codec，不修改其旧合同。
- B2b 写集：`+ G/transport/installation_calibration_transport.py`、`+ G/ui/installation_calibration_dialog.py`、`+ G/tests/test_installation_calibration_transport.py`、`+ G/tests/test_installation_calibration_dialog.py`；串行整合 `~ G/ui/file_transfer.py`（共用 owner/lease）、`~ G/ui/main_window.py`（入口及现有六面呈现复用）、`~ G/services/i18n.py`（稳定错误文案）。首批不需要改 `G/app.py` 或 `G/services/state_model.py` 的 AIR 事务语义；若为了额外入口确实需要，单独登记，不把它视为无条件写集。
- 验收：档案重放和内参变化后重算可重复；质量失败不允许 Apply/Save；GUI 不阻塞、关闭/取消能收敛、不遗留 worker；未知能力只显示 legacy 功能；同一连接无第二 reader。旧无线六面操作仍由原 Controller 处理，安装页面不会自动发 AIR 命令。单面补样不要求角度，六面完成与外参通过分开显示。

**B3：FC 会话、运行时整套切换和 TF 提交；共享边界必须串行。**

- 范围/依赖：依赖 B0、B1、坐标任务交付的变换顺序/父关系和 TF 任务交付的实际恢复语义。B3a 的纯 parser/状态机可用存储 mock 提前实现；B3b 实际持久化/生效接线不能与 TF、SCG owner 同时编辑下列共享文件。
- B3a 写集：`+ C/System/Calibration/Inc/system_installation_session.h`、`+ C/System/Calibration/Src/system_installation_session.c`；`+ C/System/Inc/system_installation_console.h`、`+ C/System/Src/system_installation_console.c`；`+ C/Tests/Host/test_installation_session.c`、`+ C/Tests/Host/test_installation_console.c`。结构检查和状态机返回 `SystemInstallationCalibrationResult`，状态 file-scope static。能力不能在 B3b 接通前对外谎报为完整支持。
- B3b 会话接线写集：`~ C/System/Src/system_console.c`；`~ C/APP/Src/app_tasks.c`（任务启动前初始化新服务）；`~ C/APP/Src/flight_task.c`（有界处理/租约）；`~ C/System/Inc/system_lifecycle.h`；`~ P/silverstar_flight_logic_cycle_reference/payload/FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c`（所有 START 入口的持续预约）；`~ C/System/Calibration/Src/system_calibration.c`、`~ C/System/Alignment/Src/system_alignment.c`（内部授权/外部冲突动作和失效）；`~ C/Tests/Host/test_lifecycle.c`、`~ C/Tests/Host/test_console.c`、`~ C/Tests/Host/test_runtime_commands.c`。现有配置动作锁有编译分支且是单次动作预约，不能假定它已覆盖整个安装会话寿命；enabled/disabled 两分支均须检查。
- B3b 坐标/生效写集，交坐标 owner 串行整合：`~ C/System/Src/system_source_selector.c`、`~ C/System/Calibration/Inc/system_mag_calibration.h`、`~ C/System/Calibration/Src/system_mag_calibration.c`、`~ C/Interfaces/Inc/system_installation_calibration_if.h`、`~ C/Tests/Host/test_source_selector.c`。当前 canonical MAG 调用在 `system_source_selector.c` 内；在该确定边界接整套 correction，不能再到每个 driver 或生成器私自补旋转。需要全新坐标入口时先修改写集，不能无依据扩展到所有 SCG 生成器文件。
- B3b TF 写集，交 TF owner：`+ C/Interfaces/Inc/system_installation_calibration_storage_if.h`；`+ S/Src/installation_calibration_storage.c` 与 `+ S1/Src/installation_calibration_storage.c`；`~ S/Inc/persistent_storage.h`、`~ S1/Inc/persistent_storage.h`，以及 `~ S/Src/persistent_storage.c`、`~ S1/Src/persistent_storage.c`（追加已审定对象 kind，现实现明确拒绝大于 MISSION_SNAPSHOT 的 kind；保留旧编号，不放宽为任意类型）；`~ S/Src/mission_snapshot.c`、`~ S1/Src/mission_snapshot.c`；`~ C/Interfaces/Inc/system_mission_snapshot_if.h`；`~ C/APP/Src/logger_task.c`；`+ C/Tests/Host/storage_integrity/test_installation_storage.c`。复用已有双槽算法，只有 TF owner 可以整合这些改动，不另开实现者同期修改；若已有 API 无法表达整套提交，由 TF owner 先明确缺口再修订写集。无需更改旧 SSLOG wire record 来承载控制命令。
- 注册/验收接线由同一整合负责人串行处理：`~ P/silverstar_core_0_1_0/plugin.json`、`~ P/silverstar_device_storage_sd_sdio_fatfs/plugin.json`、`~ P/silverstar_device_storage_sd_sdio_fatfs_f1/plugin.json`、`~ C/Tests/Host/run_tests.ps1`、`~ C/Tests/Host/storage_integrity/run_storage_integrity.py`；维护协议文档 `~ P/silverstar_protocol_maintenance_serial_0_0/docs/MAINTENANCE_PROTOCOL_0_1.md` 与 `~ docs/public/SCG/MAINTENANCE_0_1_20261013.md` 仅在真实实现后同步。
- 验收：丢 ACK 重试不重复写卡/增加代次，冲突请求拒绝；保存断电注入每个步骤后只可能读到完整旧套或完整新套，不能混合；CLEAR/取消/提交晚取消有不同语义；无卡/满卡/换设备不伪报 saved；所有控制入口都受同一生命周期锁约束。LOGFILE ENTER 仍锁存到重启；安装结束不得解除它。canonical 数据恰好应用一次完整变换，原始采集不受该变换污染；配置或父内参不匹配立即使外参失效。F407/F1 分别编译验证，不把一套结果冒充另一套。

**B4：整合/生成/验证；不再混入新的功能开发。**

- 依赖：B0–B3 完成，待测源快照冻结；共享 registry 的修改已由各批整合负责人完成。生成使用小型新目录，不覆盖用户最终候选。
- 写集：`+ G/tests/test_installation_calibration_integration.py`；`+ apps/SCG/tests/test_installation_calibration_generation.py`；`+ apps/SCG/tools/validation/installation_calibration_validate.py`；`~ 本文`。证据固定在 `docs/internal/evidence/installation_calibration_0_1_3_20261018/` 的 `commands.jsonl`、`results.json`、`source_hashes.json`、`artifact_hashes.json`、`inventory.json` 和清单所列完整日志；生成物只在 `.work/dev013_installation_calibration_20261018/` 内，inventory 记 owner/purpose/hash/保留证据路径，无清理旧目录权限。
- 验收：同一源快照上的 GSHC/FC golden、相关 Host 与旧流程回归、fresh generated power10/analyzer/ARM/link/architecture/source-graph 检查及受影响栈报告均留全证据；失败/skip 不隐藏，不拼接不同时期的 pass。真实 UART/磁环境/TF 断电/时间同步及导航效果仍标未验证，不能由本批软件结果替代。若发现实现缺陷，退回对应 B1/B2/B3 的登记写集修复并重跑受影响项，不在 B4 扩展需求。

### 8.2 并行安排与实际入口

推荐顺序：**B0 数学用例先行；B0 合同冻结后 B1a、B2a、B3a 可分别以固定接口/mock 工作；B1b、B2b、B3b 按共享文件单 owner 串行整合；最后 B4。** 当前 TF/SCG 任务未交付时，可以独立完成 B0 数学验证和 B2a 原型；合同绑定与验收状态仍标未冻结。不新建第二套存储/坐标权威来躲开依赖。

| 共享边界 | 唯一整合责任 / 并行限制 |
|---|---|
| SCG 坐标任务 `01a14f68-25d8-77d5-adb5-229f176fd0f8` | 接收其 frame、配置 digest、安装映射和 corrected/raw 边界。原始 `system_imu_if.h`/`system_magnetometer_if.h`、项目 sensor installation 配置/生成器不在 B1/B2 独立写集；B3 变换接入由坐标 owner 合并。 |
| TF 任务 `01a14f68-b311-7710-acc2-b5c49c3bd0f4` | 持久化/mission snapshot/LoggerTask/SSIC 接口是共享区；安装任务仅用 mock 和明确接口，等待 TF owner 合入新对象，禁止同期再改双槽实现。 |
| core plugin/test runner/GSHC 既有 manager | 每批一个整合负责人追加注册/入口；新文件实现者不各自编辑 registry。`system_installation_calibration_if.h` 同时涉及坐标与存储，只能指定一个合并人。 |

只读核查到的现有调用链：

```text
G/ui/main_window.py:228 CalibrationDialog
  → G/app.py:2014 send_cal_start / :2030 send_cal_face
  → AIR M0 原有 CAL_START/CAL_FACE
  → C/Modules/Src/telemetry_service.c:660/664
  → SystemCalibration_Start / SystemCalibration_FaceCollect
维护串口 C/System/Src/system_console.c:2086/2126 → 同一 SystemCalibration 服务
DeviceTask → ImuSampleBus_Process → C/APP/Src/imu_sample_bus.c:152
  → SystemCalibration_ImuSampleProcess(:636) → 静止/方向/方差/窗口累计
FlightTask → C/APP/Src/flight_task.c:1189 SystemCalibration_Process → 六面 correction
```

上述行号仅作本次定位，以函数符号为准。缺口不在“缺一套六面按钮”，而是 collector 没有 MAG 通道、时间相容配对、per-sample 原始档案和外参候选/质量状态；不能仅从六面完成事件补出它们。

**计算建议：PC 求磁椭球和 AM 外参，FC 保持现有六面 correction、采集/静止质量、轻量数值/身份验证和运行时固定矩阵运算。** 不把多项式求根、SVD 或多起点优化搬入 MCU/ISR/SerialTask。B0/B1 冻结环形队列槽数、最大记录长度、单周期 drain 和序列化数量；RAM 静态分配，满队列显式失败/计数，无回调注册、无初始化后分配。实测 `sizeof`/链接 map/栈后才接受预算，不能拿“有空闲 RAM”替代栈与时序证明。

初始边界复用：MAG 流最多 20 Hz、拟合 128–4096 点、请求 ≤191 bytes/5 tokens、响应 ≤511 bytes、上传块 ≤48 bytes、LOGFILE 块 64 bytes、单 TF 对象 payload ≤512 bytes。PC 的 IMU/配对/动态容量必须单独冻结；不在 FC 保存整段原始历史。先做静态窗口配对路径；完整翻面 gyro 动态约束列为后续可选能力，只有时间精度、原始数据带宽和积分误差有证据时启用。230400 是可选串口参数，不是所有设备的带宽保证；先计算最坏帧长×速率和控制应答余量，带宽不足降采/拒绝该能力，不增加无界队列。

## 9. 本次审查记录与限制

已读取根 AGENTS、FCCG architecture/runtime safety、GSHC AIR/architecture/calibration 合同、维护 0.1、上表源码与指定论文。根、SCG、GSHC 的 `.agents` 路径均不存在，故无可读取的相关 `.agents/skills`；没有据此跳过现有 AGENTS。环境无 `rg`，改用限定路径的 PowerShell 与 git 查询。

初始技能目录枚举意外触及旧 `.work`，部分历史目录返回 Access denied（例如 `.work/BarometerBackup_20261002/.work/baro_gui7b`、`.work/c/apps/FCCG/.work/k1`、`.work/day_ground_baseline`）；已停止该宽泛枚举，不重试、不读取/清理那些目录。必需源码、文档及两项在线参考均可读取，当前任务无未解决权限/连接阻断。

本次不运行固件/Host/ARM/硬件测试；“已有”是源码核对而非新鲜运行结果。只产生本文，不生成临时项目、不复制仓库/工具链、不清理旧 `.work`；本文 owner 为安装标定设计任务，保留为审查证据。并行任务可能继续修改源码，后续实施必须重新核对下列指纹。

文档静态校核已通过：本地 Markdown 链接存在、UTF-8 无替换字符、无尾随空白；20 项源文件 SHA-256 在写稿前后相同。提案中最坏长度请求样例为 163 bytes、5 tokens，落在现有 191-byte/5-token 边界内；这不替代未来 parser/响应/分包 golden 测试。

后续补充第 8.1–8.2 节时再次核对，20 项中 `system_mag_calibration.c` 已由并行工作改变（当次 SHA-256 为 `8e6bab9c5e378552bdc8cbc2abc466271e040a1122f0caadb9a13fdffbc9fb55`），其余 19 项未变。下表保留初次审查原指纹，不把它改写成后续实现的验收证据；分派 B3 前须以坐标/TF owner 的最终交付重新核对。此次追加仍只改本文。

| 核对文件 | SHA-256 |
|---|---|
| `AGENTS.md` | `d9a9b5339110946aa2a00baf81de47fd0732fc4c0210f02a0c43737bc96edaef` |
| `apps/SCG/plugins/builtin/silverstar_protocol_maintenance_serial_0_0/docs/MAINTENANCE_PROTOCOL_0_1.md` | `53dc84fd4897e60d0e0d5b0af63ff943468c63d725afff489ad531a3c3f18223` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Src/system_console.c` | `c63257064793584772a982b6c596817e1338976ead09d95819223f22cf32c32d` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Calibration/Src/system_calibration.c` | `dc6b5d9089ddb1a94f940e43f162c26f5f2e159920f9cf3f34302c4ea8bf82f6` |
| `apps/SCG/plugins/builtin/silverstar_algorithm_calibration/payload/Algorithm/Calibration/Src/imu_six_face_calibration.c` | `17b15033dbaae411531d40fac4f9c211082ba161af935c1882a4bb8125e0b26a` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Calibration/Src/system_mag_calibration.c` | `c4e30c1e5d9806525877186cfdcaab1722cd1145eb4082949da22b0dafa5b8ca` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Interfaces/Inc/system_installation_calibration_if.h` | `437b5c5b7c4fe32da81e968cc611aac61c671d12cbc0b1eb7e45d499258f9ec2` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Interfaces/Inc/system_magnetometer_if.h` | `95abc1b33b2e2a3d60767bb307d43582b89ad1e1d2b22691ba02eb90311abc49` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Interfaces/Inc/system_imu_if.h` | `ae5f475d1319c813c0efb7d900c90deff1a7b57b4bd15e90d5c867c8c7cdf635` |
| `apps/SCG/plugins/builtin/silverstar_device_storage_sd_sdio_fatfs/payload/Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c` | `6f07dfe3518f1d3191359cdc11aab45674405e34788bbf18979fdd6d1d98e297` |
| `apps/SCG/plugins/builtin/silverstar_device_storage_sd_sdio_fatfs/payload/Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c` | `aae29118d7644bf869437a84ab72d4a7066c71e648e27fc03f7e233103faeb81` |
| `apps/SCG/plugins/builtin/silverstar_device_storage_sd_sdio_fatfs/payload/Devices/Storage/SdSdioFatFs/Adapter/Src/persistent_storage.c` | `b8036b998abeb3029140116df39a117a8b156bf64afc259acc6590032f406271` |
| `apps/GSHC/services/magnetometer_workflow.py` | `a24032fa178922a1e3a44ee24c4c6e1fcbf6a0940a67088aab9c95b12f7de5f0` |
| `apps/GSHC/services/magnetometer_maintenance.py` | `fc91de6703a8519dcbda2b0a706d6bb7b0ec8e397fb8e658534ba0867d70c932` |
| `apps/GSHC/services/magnetometer_calibration.py` | `2350a0460fab03bfed3ca1d98d4b57bca7116ca4c53dd4ecbef65b4f43d03f22` |
| `apps/GSHC/transport/magnetometer_transport.py` | `eedda7243dd7e29b0a5310a14257afc41bb806f352cdf70f70b280a4cd4d2351` |
| `apps/GSHC/ui/file_transfer.py` | `d1cb8792cbb8bd7c87d00981a684bb80565030a4b4fd7c1c2e7382c2d1a39d7a` |
| `apps/GSHC/app.py` | `a3ff5013d688fc330d182f45fbd2125b52ec8b1eb564addc8823e967d964befe` |
| `apps/GSHC/services/state_model.py` | `d29f486d8178ef2f3fc19ef645628dcd80fd6cf3a58420d2a018348d6b68729a` |
| `contracts/log_file_service_v1.json` | `a89dbdc7a197b8f2786e0ded7da8fb79d4f537d0dbda6d1b952fa38f4af624c5` |

## 10. 后续授权：B0 数学验证与 B2a 离线原型

按后续“明确的可以先做”授权，仅新增 [apps/SCG/experiments/installation_calibration_0_1_3](../../apps/SCG/experiments/installation_calibration_0_1_3/README.md) 独立实验文件，并在 `.work/dev013_installation_calibration_20261018/` 保存小型源码快照和证据。没有接入生产 GSHC/固件、SCG 坐标或 TF 区；没有修改维护协议、SSLOG、稳定 main 或暂停的 M9N INT32_MIN。

已实现：不可变带身份/时钟/序号/阶段/采集内参 ID 与代次的原始配对数据、完整 JSON 回放快照、六面加速度对角内参和静态 gyro bias 数学助手、固定 SPD 磁椭球助手、AM 多起点候选、局部激励/多解/水平磁场/普通残差/独立留出门禁、同面换朝向补采排序、内参实际变化后的原始数据重算/候选失效、搜索取消/计算进度。输出统一为不可直接 Apply/Save 的实验候选。

完整最新运行 **run04：33 passed，退出码 0**，命令：`python -B apps/SCG/experiments/installation_calibration_0_1_3/verify.py --run run04`。此前三轮失败日志未删除或覆盖；其中 run02 的反例发现并修复了“用留出数据挑选候选会解除训练多解门禁”的算法问题。训练数据现在独立排序及判断多解，留出数据只验证固定候选；不能用留出偏好宣称唯一。全部命令、工具版本、源码快照/哈希、各轮失败及数值结果见[证据汇总](../../.work/dev013_installation_calibration_20261018/RESULTS.md)。

合成案例明确区分：正常六面可形成候选；物理可实现的对称六面可零残差但局部秩不足；另一组六面可局部满秩但具有多个精确解；粗先验未必排除多解；同面补采示例有效但没有普遍保证。隐藏磁轴反射甚至可满足所有数值门禁，故 `coordinate_evidence=DECLARED_NOT_HARDWARE_VERIFIED` 始终保留。有明确 R_GA 来源才能输出 R_GM，未知时不能将 R_AM 当作磁到陀螺旋转。

这只完成 **B0 合成数学验证范围和 B2a 纯数据原型子集**。B0 wire 合同/golden、真实时间及 gap 语义/容量、完整旋转采集档案、硬件阈值资格、B1 采集、B2 生产 codec/UI/worker、B3 会话/幂等/恢复/互斥/TF 提交、B4 完整生成验证仍未完成。多起点不是 AM-Align 的全局求解证明，`global_uniqueness=NOT_PROVEN_MULTISTART` 始终保留；阈值全为 `PROVISIONAL_SYNTHETIC_ONLY`。静态六面不估计 gyro 尺度；动态 gyro 显式 `NOT_IMPLEMENTED`。本次没有执行固件 power10/Host/analyzer/ARM/链接/栈或硬件验证，也没有以实验测试代替这些证据。

实验 owner 为 `installation_calibration_B0_B2a`；每轮 inventory 标明 purpose/owner/hash/保留路径，`cleanup_authorized=false`。无必要权限/连接阻断；不涉及旧 `.work` 清理。迁入生产服务前仍须和两位并行 owner 的最终合同重新核对。

## 11. 后续夜间授权：B1/B2 隔离采集与协议模型

按继续开发授权，在同一实验目录新增 `capture.py`、`protocol.py`、`session.py` 和 `test_capture_session.py`，并扩展本目录测试 runner。功能、字段及明确缺口见 [B1_B2_OFFLINE.md](../../apps/SCG/experiments/installation_calibration_0_1_3/B1_B2_OFFLINE.md)，逐轮真实运行与空间增量见[本批证据](../../.work/dev013_installation_calibration_20261018/B1_B2_RESULTS.md)。没有生产接入或协议发布。

B1 模型保存冻结的身份/boot/epoch/源轴映射来源/物理单位/校正层/采集内参 ID 与代次；目标侧源时间与接收时间、PC 收包时间分别保留。以声明的源流/stride 和时间不确定度作有界一对一 FIFO 配对；序号 gap、回退、饱和、超时、偏差和容量溢出使窗口失败。原始故障记录在容量允许时保留；失败/取消窗口的旧好配对也不进入数学求解。原始档案可独立导出，磁旋转动态记录不能当作静态重力。

B2 模型实现提案命令 grammar、≤191 bytes/5 tokens 请求、≤511 bytes 响应/独立双部分样本事件、CRC/绑定/配对号重组、有限状态、重复请求/冲突/STALE、POLL、取消受理与清理完成、UNKNOWN/租约/重启不续会话、内参变更失效、候选冻结分页读回，以及 TF/配置 owner 和导出模式锁存的模拟。能力探测按当前 core 的真实 BAD_MODULE/UNKNOWN 模板识别旧固件；未知/缺字段不推断支持。重组超时/冲突/容量错误锁定窗口，迟到部分不能恢复为好样本。

全部输出继续禁止应用；`VALIDATE/APPLY/SAVE` 明确 NOT_PROVEN，`imu_ready/extrinsic_validated/apply/saved` 不由六面采集 mask 或 ACK 推导。完整安装 SSIC 对象头/manifest 尚未冻结：PUT 默认 UNSUPPORTED，仅可测试注入不透明对象的有界暂存/长度/CRC/SHA-256，ACTIVE/SAVED 无持久化模型。候选 READ 为包含完整数学上下文的诊断 JSON，不冒充可提交对象。当前 FACE 命令 grammar 尚缺线上 window/pose/TRAIN/HOLDOUT 选择及补采返回求解语义；本批由采集 API 直接验证这些标签，不声称线上流程已完成。

接入仍需 B1 真实 owner/tap/时钟与降采样契约、B2 生产 worker/单 reader/会话协作、B3 生命周期与 TF 完整事务、`contracts/` 唯一 wire authority/golden 和 B4 固件验证；Python 容量模型不证明 MCU 静态分配、栈或 WCET。未改生产 GUI/固件/TF、SCG 坐标或 M9N INT32_MIN；未接硬件、push、发布或修改稳定 main。没有新增数学唯一性结论，已有 NOT_PROVEN 继续保留。

## 12. 离线契约收尾：窗口分区与完整 SSIC 草案

本轮在原实验目录新增 [CONTRACT_DRAFT.md](../../apps/SCG/experiments/installation_calibration_0_1_3/CONTRACT_DRAFT.md)、`ssic_draft.py`、`test_contract_draft.py`，补齐 WINDOW 显式阶段/面/训练留出/窗口/姿态/尝试号、WINDOW_STOP/WINDOW_CANCEL/CAPTURE_DONE、带长度/CRC/SHA-256 的 UPLOAD/PUT 和 UPLOAD_CANCEL。SIX_FACE 仍为主流程，只有 TRAIN 六面设置 mask，CAPTURE_DONE 明确冻结批次；SUPPLEMENT 仍以同面换朝向优先。原始档案补齐 owner 接收时间、窗口起止和源索引，可验证回放；留出数据不参与内参拟合、外参优化或模型选择。

SSIC 保留 schema 1 / 32-byte 头 / 旧 MAG kind 1，新 kind 2–8 仅为完整安装草案：两个身份、两个来源、两个完整内参、外参、完整质量策略、质量记录与 manifest 共十件，各不超过 512 bytes，实际包长 3628 bytes。完整原始档案与数学输入/TRAIN/HOLDOUT 分别摘要绑定；配置、当前 binding、基准代次和新内参精确字节依赖须一致。新 correction 从未软件校正的 provider 物理量整套替换，不能叠加旧校正。未知 R_GA 不输出 R_GM，所有应用/保存/硬件质量证明仍禁用或 NOT_PROVEN。

取消与断连路径也收尾：窗口取消保留当前原始记录并允许新窗口；上传取消回收暂存；全会话取消受理后，即使断连也可在模型的有界 cleanup deadline 完成清理。协议 kind/对象尚须坐标/TF owner 审核并迁入 `contracts/` 唯一权威，未因此修改生产协议、固件、GUI 或 TF。用户交互仍待决定留出窗口是每面连续独立采集还是收齐后复访；本轮只固定数据/命令能力，不擅自确定默认操作节奏。

整体验证、精确源码快照和精炼接入清单见 [CONTRACT_RESULTS.md](../../.work/dev013_installation_calibration_20261018/CONTRACT_RESULTS.md)。证据直接使用既有任务目录的前缀文件，未新增目录或复制工程/工具链；旧证据不覆盖。

## 13. 2026-10-19 已批准节奏与 GSHC 软件接入

用户已选择方案一，并澄清每面只需一次操作：目标自动连续采 TRAIN→HOLDOUT，再提示换面；不是要求用户启动两个 GUI 窗口或两次采集。两段源样本必须非重叠、标记边界，不能声称相邻数据统计独立。正式会话/样本权威现为 [installation_calibration_v1.json](../../contracts/installation_calibration_v1.json)，维护 0.1/AIR M0/SSLOG 0.0 不变；本节取代此前“留出节奏待决定”和默认手动 WINDOW 的描述。SSIC kind 2–8 仍未正式采纳，UPLOAD/APPLY/SAVE 禁用。

GSHC `services/installation_calibration_*.py` 持有共享数据/数学/codec/计划账本、后端、只读回放和有界 worker；原实验入口委托这些服务，私有包边界避免与 GSHC 既有 protocol 包冲突。新流程必须协商 face_auto/check_only/sample_format/contract 等明确能力，旧固件或旧 WINDOW 不足以开启，绝不回退为 legacy CAL/MAG/ALIGN 控制。未向现有 GUI MaintenanceOwner 注册 live adapter，GUI 布局/第四页/app.py 保持用户当前版本。

每面只有一个 FACE 启动，目标自动两段；POLL 只查询该事务。所有原始部分先保存，完成的 CRC 配对和精确分段数量全部满足后才原子纳入数据集。第三个线上时间槽固定为零，PC 时间由 GSHC 在 batch 出队时记录并明确其诊断来源；不能由 MCU 伪造 PC 时钟。TRAIN 六面单独拟合新加计内参/静态 gyro bias，再用原始物理量重算 AM；HOLDOUT 不参与拟合或候选选择。

已用验证数据一旦影响补采/策略调整，全部旧 HOLDOUT 保留为适应过程历史，永不改标 TRAIN；新增训练使旧候选失效。软件保守门禁要求最后训练之后的新验证覆盖六面，缺少的新证据通过单次 CHECK_ONLY 事务取得，不继续修改拟合输入。验证用途、策略、新训练内参和 context 进入原始档案账本，回放不能恢复成“从未使用的验证集”。没有把该策略宣称为统计独立或硬件阈值资格。

实际实现、最小固件接口与约 6208 B/建议预留 8 KiB 的静态队列预算提案、串口带宽计算见 [GSHC 软件接入说明](../../apps/GSHC/docs/INSTALLATION_CALIBRATION_BACKEND_20261019.md)。这些是待 owner 审查的预算，不是 sizeof/栈/WCET 实测；真实采集固件另批安排，本轮未改 owning firmware、已烧录工程、SCG 坐标或 TF。完整新鲜软件测试与 GUI 指纹见 [SOFTWARE_RESULTS_20261019.md](../../.work/dev013_installation_calibration_20261018/SOFTWARE_RESULTS_20261019.md)，不替代 ARM/Host 固件/power10/analyzer 或实板证据。
