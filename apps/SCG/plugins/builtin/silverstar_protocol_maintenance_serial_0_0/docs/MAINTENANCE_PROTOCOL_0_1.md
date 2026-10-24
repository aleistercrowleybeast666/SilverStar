# SilverStar 维护串口协议 0.1 — 本地开发工作区完整实现说明

文档日期：2026-10-17。状态：源码／测试镜像验收资料，未发布。维护协议为 **0.1**，兼容 **0.0**；诊断 schema 为 **1**，LOGFILE 文件服务为 **1**，SSLOG 容器仍为 **0.0**。这些版本彼此独立，也不等于产品固件版本 0.1.3。

本文对应 2026-10-17 合入的本地开发源码：GSHC、共享 ELF 诊断库、维护固件 owning payload 和生成器。开发分支基点为 `7896c1d09a7f9138c41cdac35beef38347d94b78`，含已记录的维护合入差异；不是新的发布版本。根 `contracts/` 仍是共享机器可读合同的权威来源，本文不建立第二份合同。下文测试身份示例来自已实测 R04；普通生成没有该测试身份时，不应凭示例补造这些可选字段。

## 1. 协议边界与能力判定

本协议是飞控 System Console 上的文本行协议。地面站 AIR M0、Ground GSP、SSLOG 二进制记录和 SWD 调试协议均有独立边界，不得将它们的帧、ACK 或状态混用。USB 虚拟串口、DAPLink UART 桥或其他被工程选中的 byte stream 只承载字节，不改变本协议。

0.1 保留 0.0 命令、参数和既有错误路径，新增标准化 `SYSTEM DIAG [cursor]` 只读诊断。LOGFILE v1 单独通过 `LOGFILE CAPS` 协商，不能从“支持 0.1”推断“支持存储下载”。0.0／0.1 profile 仍可配置；实际命令可用性以当前固件返回的能力和明确错误为准，不仅依据 profile 文件名。当前 core 内有 DIAG 实现；不要自行断言选择 0.0 profile 就一定移除了它。

只读查询可以发现未支持的能力；`UNSUPPORTED` 必须如实展示。命令被 parser 识别也不等于所选 Device 实现了操作，更不等于已获得执行许可。以下控制／写入语法用于完整说明，本轮实板未执行 START、解锁、执行器、配置写入、校准或对准启动。

## 2. 字节、长度和数值规则

| 项目 | 当前实现 |
|---|---|
| 编码 | metadata 为 `utf8_line`；正式命令和当前 DIAG／LOGFILE 采用 ASCII 子集，关键字大写 |
| 分隔 | token 以空格／制表符分开；CR、LF、CRLF 结束一条命令；推荐 CRLF |
| 请求容量 | 192 字节缓冲含 NUL，最多 191 字节命令正文；通用 parser 最多 5 token |
| 通用响应 | System Console 缓冲容量 3072 字节；部分 legacy DETAIL 为多段／多行。不能误套 511 字节为全部 0.0 响应上限 |
| DIAG／LOGFILE 客户端边界 | 单行最多 511 字节；LOGFILE 响应容器 512，worker DONE 文本缓冲 256，READ 最长正文 255 字节加 NUL |
| Console 单周期输入 | 当前最多 8 个 32-byte chunk；SerialTask 不在此执行 FatFs 文件读写 |
| 串口参数 | 工程／连接选择决定；本次实测 COM9，230400，8N1。230400 不是协议固定唯一波特率 |

普通非负整数为十进制；实例号范围 0..255；LOGFILE 文件号 1..999999；请求号为非零 uint32。CRC 为 8 位大写十六进制。位掩码通常为 `0x...`。浮点字段的单位由字段名／本节及响应模板说明。`UNSUPPORTED`、`INVALID`、`UNKNOWN`、缺失和 `4294967295` 年龄哨兵不能转换成有效的零。

超长行返回 `ERR SYSTEM PARSE code=BAD_FORMAT reason=LINE_TOO_LONG`。RX discontinuity 后丢弃未结束半行，后续必须从完整新命令开始，不能把残片拼成另一条命令。链路可能有 prompt、命令回显、`LOG ...` 或 `EVENT ...` 异步行；客户端只接受匹配操作的完整响应，必须有长度／数量／等待预算，不能从零散字段拼造成功。

## 3. 通用请求、响应与设备寻址

```text
<CAPABILITY> LIST
<CAPABILITY> <instance> <COMMAND> [SUBCOMMAND] [EXTRA]
<SYSTEM_MODULE> <COMMAND> [SUBCOMMAND] [EXTRA]

OK <CAPABILITY> <instance> <COMMAND> key=value ...
ERR <CAPABILITY> <instance> <COMMAND> code=<CODE> reason=<REASON>
OK <SYSTEM_MODULE> <COMMAND> key=value ...
ERR <SYSTEM_MODULE> <COMMAND> code=<CODE> reason=<REASON>
```

有实例号的 capability 为 `IMU GNSS BARO MAG ATTITUDE TELEMETRY POWER`；System module 为 `SYSTEM ESTIMATOR KF INS CAL ALIGN OUTPUT LOG TIME`。`LOGFILE` 有第 8 节的专用 grammar。`INS 0 STATUS`／`KF 0 STATUS` 不合法，实例号不能套用到 System module。

`IMU 0` 表达加速度和角速度，不能隐含 BARO／MAG／ATTITUDE。同一物理器件可提供多个 capability endpoint；`descriptor_id`、`instance_id`、`physical_device_id` 分别表示描述、类内实例和物理归属，不能混同。数量、型号和 ID 均由生成配置决定，不是协议常量。

```text
IMU LIST
OK IMU LIST count=1 DATA instance=0 descriptor_id=1 physical_device_id=1 shared=1 device=JY901B model=JY901B
```

LIST 可有多个 DATA 段。`IMU STATUS` → `BAD_FORMAT/INSTANCE_REQUIRED`；`IMU -1 STATUS`／`IMU X STATUS` → `BAD_INSTANCE/FORMAT`；`IMU 256 STATUS` → `BAD_INSTANCE/RANGE`；合法但未生成的实例 → `NOT_PRESENT/INSTANCE`。未提供 `HELP`、`SYSTEM HELP` 或通用 `TF STATUS/TEST/SYNC/FORMAT` 命令。

## 4. 0.0 兼容命令完整索引

`i` 为实例号；下表列语法及实际语义，具体字段模板见附录。只读状态不替代 Health／生命周期许可。

| 模块 | 语法 | 响应与行为 |
|---|---|---|
| SYSTEM | `INFO` | project/version/profile 及当前 build 身份；不是芯片精确料号证明 |
| SYSTEM | `STATUS` | state、ready、block、warn、attitude |
| SYSTEM | `CAPABILITIES` | compiled/enabled/present/healthy 四个 mask |
| SYSTEM | `PROFILE` | profile id、frozen |
| SYSTEM | `READY` | ready/block、attitude、GNSS 原点／融合许可、calibration/alignment 与 selected-source ready 字段 |
| SYSTEM | `START` | 向生命周期 owner 提交请求，`state=PENDING request_id=...` 仅为接收；有实际控制影响 |
| SYSTEM | `START RESULT` | PENDING 或 COMPLETE，含 request_id/result/reason/timestamp_us；只取 console 来源最近请求 |
| SYSTEM | `STARTUP [IMU\|GNSS\|TELEMETRY]` | 启动总报告或对应端点启动／配置诊断 |
| SYSTEM | `STACK` | valid_mask 和各 Task 的 high_water/allocation，`unit=words`；当前 ARM word 为 4 字节；不是完整栈证明 |
| SYSTEM | `FLIGHT` | 只读部署触发／landing／baro／impact 诊断；没有本命令的 START/FINISH 子命令 |
| SYSTEM | `CONSOLE IO [CLEAR]` | Console I/O 快照／相对统计基线；CLEAR 不重启链路或 DMA |
| IMU i | `INFO`、`STATUS`、`CAPABILITIES`、`SAMPLE`、`IO [CLEAR]`、`CONFIG SHOW` | 当前端点／物理 owner 缓存、字段 mask 和样本 |
| GNSS i | 上述基本查询，另 `SAMPLE DETAIL`、`CONFIG READ`、`CONFIG VERIFY`、`CONFIG APPLY`、`NAV SAT`、`MON RF` | READ/NAV/MON 为有界 Device owner 事务；VERIFY/APPLY 是否实现取决于 Device；APPLY 为写操作 |
| BARO i | 基本查询，另 `SAMPLE DETAIL` | 压力、温度、高度、mask、freshness 与明确状态 |
| MAG i | 基本查询，另 `STREAM START`、`STREAM STOP`、`CAL [READ]`、`CAL APPLY <hex>`、`CAL SAVE`、`CAL CLEAR` | 第 6 节的采集／校准事务；是否存在 MAG 由工程决定 |
| ATTITUDE i | `INFO`、`STATUS`、`CAPABILITIES`、`SAMPLE`、`IO [CLEAR]`、`CONFIG SHOW` | 硬件姿态 capability，与软件 INS 独立 |
| TELEMETRY i | `INFO`、`STATUS`、`CAPABILITIES`、`IO [CLEAR]` | 只读 TelemetryTask 缓存，不在 Console 操作 SPI |
| POWER i | `INFO`、`STATUS`、`CAPABILITIES`、`SAMPLE`、`CONFIG SHOW` | 电源采样与配置缓存 |
| ESTIMATOR | `STATUS`、`GNSS`、`BARO` | 估计器／融合／原点／门控诊断 |
| KF | `STATUS` | 当前选定 KF 汇总；能力随算法配置变化 |
| INS | `STATUS` | 初始化、启动、软件传播及四元数／速度／位置有效性 |
| CAL | `STATUS`、`DETAIL`、`START NONE`、`START ONE_FACE`、`START SIX_FACE`、`FACE X+\|X-\|Y+\|Y-\|Z+\|Z-`、`STOP`、`RESET` | 状态查询及有控制影响的校准事务 |
| ALIGN | `STATUS`、`DETAIL`、`START`、`STOP`、`RESET` | 动态 selected-source 对准状态及事务 |
| OUTPUT | `STATUS` | 输出状态只读摘要；不提供本协议任意执行器驱动命令 |
| LOG | `INFO`、`STATUS` | Storage Device 名及 initialized/mounted/open/healthy/writes/syncs/errors；不是文件服务 |
| TIME | `STATUS` | 时基／UTC 诊断 |

所有 capability 都支持无实例号的 `<CAPABILITY> LIST`，即使选定实例数为零。公共 `CONFIG SHOW/READ/VERIFY/APPLY` 语法的识别不能当作每个 Device 的实现承诺：SHOW 是缓存；READ 不支持时返回 `UNSUPPORTED/HARDWARE_READ`，不能回退缓存冒充硬件回读；VERIFY/APPLY 无实现时为 `UNSUPPORTED/DEVICE_OPERATION`。`LOG IO`／`LOG IO CLEAR` 当前不支持。

`SYSTEM SELFTEST`、`SYSTEM PARAM ...` 和 Device SELFTEST／PARAM 属于明确拒绝路径，返回 UNSUPPORTED；未知模块 BAD_MODULE，未知命令 BAD_COMMAND，冗余 token BAD_FORMAT。`SYSTEM STATUS EXTRA`、`GNSS 0 STATUS DETAIL` 等不能被宽松接收。

### 4.1 重要字段解释

- `GNSS i SAMPLE DETAIL`：supported_mask/valid_mask、fix、位置／高度／精度、age_ms、position_usable、速度 mask、拒绝 mask 与 quality_degraded。没有值时按 mask 显示 INVALID／UNSUPPORTED。
- `BARO i SAMPLE DETAIL`：supported/present/configured、field masks、freshness、pressure/temperature/altitude，状态可为 UNSUPPORTED/NOT_PRESENT/NOT_CONFIGURED/NOT_READY/STALE/INVALID/FAILED/OK。
- `ESTIMATOR STATUS`：state、initialized、started、mode、attitude_source、position_source、imu_prediction_count、last_state_timestamp；数据时间不是任务完成心跳。
- `ESTIMATOR GNSS`：冻结的 fusion_enabled/origin、位置／速度更新、接受／拒绝及门控诊断；GNSS 原点未在 START 前形成时，本次任务不能由飞行中后续 fix 自动补建许可。附加 NIS、innovation、有效 std、P 对角、reject streak、reacquire 字段属于观测，不能据此宣称精度验证。
- `ESTIMATOR BARO`：原点采集／冻结、相对高度、variance、innovation、NIS、接受／软化／拒绝／跳过计数。WAIT_STATE_CATCHUP 为等待惯性状态追上样本时间，不自动表示失败。
- `KF STATUS`：当前维度、预测／更新／拒绝及 reacquire 摘要；按当前构建返回，不把 KF6 固定为所有工程的唯一算法。
- `INS STATUS`：ready/validity/propagation；兼容名 bias_ready/bias_samples 实际来自 SystemCalibration，不能将它误作旧的独立 bias 模块。
- `LOG STATUS writes` 是写尝试；`syncs` 历史计数和单次 write 成功都不单独证明当前日志已持久化或关闭。

### 4.2 生命周期与许可

生命周期数值：0 BOOT、1 SELF_TEST、2 PREFLIGHT、3 READY、4 FLIGHT、5 RECOVERY、6 LANDED、7 POSTFLIGHT、8 FAULT。Parser 的 inspection 白名单和各 owner 的状态／互斥检查共同决定执行；FLIGHT／RECOVERY 不放开配置写入、校准或对准操作。某些已识别命令可到达 owner 后返回 BUSY／BAD_STATE／LOCKED，不能仅凭 parser 识别判断执行成功。

正式依赖为 Calibration READY → Alignment READY → START READY；AIR Capability ACK 属会话条件，不改变本机 Health ready，console START 与 AIR 入口也不能互相冒充。START 接收、CAL／ALIGN 的 accepted=1、文件 ENTER ACK 均不表示相应动作完成。

## 5. 0.0 有界事务、IO 与异步事件

GNSS CONFIG READ/NAV SAT/MON RF 向 Device 单槽事务提交请求，DeviceTask 保持 IMU 正常处理并每周期推进有限步骤；Console 不调用 SystemGnss_Process 驱动事务。事务有 transaction_id，第二个请求 BUSY；NAK、checksum、畸形响应、超时和 RX discontinuity 使事务结束。无关 NAV-PVT 不能完成 VALGET／NAV-SAT／MON-RF。

CONFIG READ 依次读取 UART、protocol、NAV-PVT、rate、dynamic-model、signals，组失败后的逐 key 回退也跨周期推进；部分成功仅由 valid_mask 表达，不能用缓存补齐。典型响应：

```text
OK GNSS 0 CONFIG READ source=HARDWARE read_result=<result> valid_mask=<mask> ... transaction_id=<id> detailed_result=<detail>
```

IO CLEAR 只保存当前物理 owner 的累计快照为新基线，显示 uint32 相对增量；不清原始计数、断流序号、Parser、DMA 或健康。共享 physical_device_id 的 BARO/MAG/ATTITUDE/IMU 视图共用对应 owner 的基线。时间与事务超时由选定设备实现决定，不套用 LOGFILE 的 30 秒 mailbox 空闲规则。

CAL STATUS／DETAIL 显示 mode/state/ready/current_face/last_face/result/completed_face_mask/samples、bias/scale、reject/retry/wait_reason、六面均值。NONE 是显式 identity calibration 模式；本文说明语法不构成本轮使用它绕过实测校准的证据。SIX_FACE 清旧结果进入 WAIT_FACE；重采某面仅在请求被接受时失效该面并保留其余面。STOP 保留已完成面，RESET 清本次结果；新校准或 RESET 使旧 Alignment 失效。

```text
EVENT CAL FACE face=<face> result=PASSED|FAILED ...
EVENT CAL COMPLETE mode=<mode> result=PASSED|FAILED ...
EVENT CAL DIAG face=<face|NONE> reason=NONE|NO_STREAM|GYRO_MOVING|ACCEL_MAGNITUDE|GRAVITY_DIRECTION|VARIANCE|SAMPLE_GAP
EVENT ALIGN COMPLETE result=PASSED|FAILED ...
EVENT ALIGN STALE reason=MOTION ready_mask=<mask>
```

DIAG 事件仅在 face/reason 变化时发送。ALIGN STATUS／DETAIL 使用 capability/selected/required/ready masks，只列 selected sources；DETAIL 可含多行 `ALIGN SOURCE name=...`。ALIGN START 必须已有 Calibration READY；STALE 不伪装 Device failure，不自动恢复任务就绪，须按既有事务重新对准。所有异步事件由 Console/SerialTask 的受控路径发送，不由算法直接操作 UART。

## 6. MAG 流与校准包

磁校准的椭球拟合运行在 **PC 端**（GSHC 的 `services/magnetometer_calibration.py`），求解硬铁偏置与软铁矩阵。SCG 按所选设备和协议生成／纳入飞控采样、维护命令、参数校验、矩阵应用及持久化代码；飞控不执行这项椭球拟合。操作顺序为采集、PC 拟合、`CAL APPLY`、`CAL SAVE`、`CAL READ` 确认；不是向飞控发一条拟合启动命令后等待其自行求解。

当前这套磁校准只接入独立的 **Maintenance Serial ASCII 维护串口**，GSHC 使用 `MagMaintenanceSession`／`SerialLink` 收发下列 `MAG i ...` 命令，不经 AIR M0 或 Ground GSP。AIR 的 `CAL_START`／`CAL_FACE`／`CAL_STOP`／`CAL_RESET` 调用既有 `SystemCalibration_*` 校准流程，不是 `SystemMagCalibration_*` 的磁采集、APPLY 或 SAVE 入口；当前没有这套磁校准的 AIR 无线命令。源码与生成代码的存在不证明当前板载固件已包含或实测通过这些入口。

`MAG i STREAM START` 接收后返回 `state=STARTED rate_hz=20`，每 50 ms 最多一条新 sequence 且有效的样本；STOP 返回 STOPPED，飞行配置锁定后自动关闭，不发送历史流。

```text
EVENT MAG SAMPLE instance=<i> physical_device_id=<id> seq=<n> sample_us=<us> x_uT=<x> y_uT=<y> z_uT=<z>
```

`MAG i CAL` 与 `CAL READ` 返回 `state=APPLIED|EMPTY generation physical_device_id instance saved pending failed load_error`。APPLY 接受 **84-byte 小端包的 168 个 hex 字符**，整体仍为一条 ASCII 命令。包布局：

| 偏移 | 长度 | 内容 |
|---:|---:|---|
| 0 | 1 | schema revision=1 |
| 1 | 1 | algorithm revision=1 |
| 2 | 2 | uint16 physical_device_id，小端 |
| 4 | 1 | instance |
| 5 | 1 | reserved=0 |
| 6 | 12 | 3×float32 hard-iron bias，µT |
| 18 | 36 | 9×float32 soft-iron 矩阵，行优先 |
| 54 | 4 | float32 reference field，10..100 µT |
| 58 | 4 | float32 RMS residual，0..0.15×reference |
| 62 | 4 | float32 max residual，RMS..0.50×reference |
| 66 | 4 | float32 condition 指标，1..25 |
| 70 | 8 | 八 octant 各 uint8 覆盖数量，每项至少 4 |
| 78 | 2 | uint16 样本总数，128..4096 |
| 80 | 4 | 前 80 字节 CRC32，小端 |

所有 float 必须有限，bias 绝对值≤1000，矩阵元素绝对值≤10、对称差≤0.02，并通过实现的正定主子式／determinant 检查；身份不符 WRONG_DEVICE。CRC 使用反射多项式 0xEDB88320、初值／最终异或 FFFFFFFF。

APPLY 的 accepted=1 只证明 RAM 应用。SAVE 交给 LoggerTask 原子写 Persistent Storage 双槽并 sync／回读 CRC；须等 saved=1、pending=0 且 generation 确认才算保存完成。CLEAR 先停用 RAM 校准，再请求持久 tombstone。错误包／旧身份／CRC／tombstone 由 load_error 等字段报告。本轮没有 MAG 实板采集、APPLY、SAVE、CLEAR 证据。

## 7. 0.1 新增只读诊断

### 7.1 协商与分页

```text
SYSTEM DIAG
OK SYSTEM DIAG version=1 maintenance=0.1 compatible=0.0 file_service_version=1 entries=7 max_entries=16 max_line=511 polling_ms=1000 firmware=0.1.3 build=4 kind=test build_tag=SST013R4 source_commit=27e2dd65e1d4603a809843195141426549976476 test_id=TF_TEST_013_HW02_R04

SYSTEM DIAG 0
OK SYSTEM DIAG version=1 id=task.lifecycle group=task name=Lifecycle readonly=1 next_cursor=1 end=0 state=OBSERVED reason=not_start_authorization source=Lifecycle age_ms=4294967295 phase=2

SYSTEM DIAG 7
OK SYSTEM DIAG version=1 end=1 next_cursor=0
```

当前 firmware cursor 只接受单字符 0..7；0..6 每页一条，7 为结束，其余 BAD_ARGUMENT/CURSOR。客户端应从 0 逐页使用 next_cursor，拒绝重复 ID／游标、条目数超协商上限、不完整周期和不支持的关键版本。max_entries=16 是 schema／客户端分配上限，不表示当前有 16 项。

### 7.2 字段及当前七条记录

每条非 end 页必须有 version=1、id、group、name、readonly=1、state、reason、source、age_ms、next_cursor、end=0。id/name/source 为有界 ASCII token，不能含空格。当前 GSHC 限制：id 64、group 24、name 64、state 32、reason 96、source 64 字符。状态集合为 OBSERVED、WAIT、BUSY、FAULT、UNKNOWN；未知状态按 UNKNOWN 表示，未知可选字段可忽略。

| cursor／id | group／含义 | 附加字段与限制 |
|---|---|---|
| 0 `task.lifecycle` | task／生命周期观测 | phase；不构成 START 授权 |
| 1 `task.preparation` | task／SystemHealth 就绪／阻塞 | sequence、block、warn；reason 从实际阻塞 mask 选取，完整 mask 仍保留 |
| 2 `thread.logger` | thread／已完成 sink 写入 | counter、unit=completed_writes、sequence、work_age_ms；整次 sink write 成功才推进；不是 sync／durability 证明 |
| 3 `thread.estimator` | thread／估计器预测数据进度 | counter、unit=predictions、data_age_ms、started；数据时间不是调度器心跳 |
| 4 `sensor.ins_solution` | sensor／INS 解算有效性 | data_age_ms、quaternion_valid、velocity_valid、position_valid；不等价于传感器在线 |
| 5 `storage.tf` | storage／RAM 健康观测 | mounted、open、healthy、counter、unit=write_attempts、syncs、errors |
| 6 `communication.console` | communication／缺少完成健康插桩 | UNKNOWN / completion_not_instrumented / source=not_available；不能用任务存在或迭代数冒充健康 |

age_ms／work_age_ms／data_age_ms 的 `4294967295` 表示不可用，不是 0。GSHC 用本机 received_ns 继续老化显示。不同条目独立采样，不是原子系统快照；OBSERVED 表示数据被观测，不表示系统安全、已完成或任务 ready。可选 counter/errors/syncs/progress 为非负 uint32；progress_done/total 必须同时有且 `0≤done≤total`、total>0，未知总量不得伪造百分比。

客户端一周期最多 16 条，每页至多一次有界交换；本实现响应等待 2 秒，完整周期结束后至少间隔 1 秒（协商值可放慢，最多 60 秒）。文件作业与诊断共享单一串口 owner，作业期间暂停诊断轮询并清除／标记暂停，不能把旧条目画成实时值。

串口 0.1 **没有** 任意变量、符号或地址读取／写入命令。GSHC 的 ELF 变量监视另走 SWD：同连接完整镜像比对后只读目录标量，当前每次最多 16 个、间隔至少 1 秒。这与 DIAG 的 16 条上限是两个独立预算。

## 8. LOGFILE v1 完整 grammar 与响应

```text
LOGFILE CAPS
LOGFILE STATUS
LOGFILE ENTER
LOGFILE LIST <cursor>
LOGFILE META <file_id>
LOGFILE READ <file_id> <token> <offset>
LOGFILE POLL <request_id>
LOGFILE CANCEL
LOGFILE DELETE <file_id> <token> CONFIRM    # 只识别并明确拒绝，不执行删除
```

### 8.1 CAPS、STATUS、ENTER

```text
OK LOGFILE CAPS file_service_version=1 supported=1 max_chunk=64 delete_supported=0 telemetry_bulk=0 device_id=unknown boot_id=unknown status_version=1 maintenance_required=1 firmware=<version> <build_identity_fields>
OK LOGFILE STATUS status_version=1 source=FC_DEBUG_RAM sequence=<u32> age_ms=<u32> lifecycle=<0..8> storage_valid=<0|1> mounted=<0|1> healthy=<0|1> writer_open=<0|1> log_fault=<0|1> finalization=<0..3> maintenance=<0..3> cleanup_pending=<0|1> reboot_required=<0|1>
OK LOGFILE ENTER accepted=1 maintenance=<1|2|3> reboot_required=1
ERR LOGFILE ENTER request_id=0 code=BUSY|LOCKED
```

未启用 protocol logging 时 CAPS supported=0，其他 LOGFILE 返回 UNSUPPORTED。STATUS 是 LoggerTask 发布的 RAM 快照，未发布时 NOT_READY；sequence 不单独表示一次写入。`finalization` 数值为 0 IDLE、1 ARMED、2 DRAINING、3 FINALIZED。`maintenance` 为 0 Off、1 Draining、2 Ready、3 Failed。

ENTER 仅在生命周期 PREFLIGHT(2)、READY(3)、POSTFLIGHT(7)，且没有待处理／执行中 START 或配置事务时被 owner 接受。它在同一 IRQ 互斥边界锁存维护预约，阻止新的 START 等冲突操作；ACK 不执行磁盘关闭，也不代表 Ready。重复 ENTER 幂等，已有 Ready 不重开 writer；已有 Failed 不能被重试升级，ACK 可能仍携带 maintenance=3，客户端必须检查最终状态。

### 8.2 mailbox、POLL、忙与取消

LIST/META/READ 为异步单槽请求。提交先返回：

```text
PENDING LOGFILE META request_id=139
LOGFILE POLL 139
PENDING LOGFILE META request_id=139
LOGFILE POLL 139
OK LOGFILE META request_id=139 ...
```

POLL 的成功／待处理结果仍以原操作 META/LIST/READ 为标签，不是 `OK LOGFILE POLL`。客户端必须验证同一非零 request_id；错误的／已释放请求号返回 `ERR LOGFILE POLL ... code=STALE`。单槽尚 pending 或清理未完成时新请求 BUSY。请求序号到 UINT32_MAX 不回绕复用，返回 NOT_READY。

```text
LOGFILE CANCEL
OK LOGFILE CANCEL cancelled=1 cleanup_complete=0
```

CANCEL 只标记 mailbox 取消；LoggerTask 后续关闭私有枚举／读取句柄并撤销 hash cache。ACK 不是 cleanup 完成证据，可用 STATUS cleanup_pending 观察。CANCEL **不会** 关闭 logger writer、退出维护预约、重启、删除文件或取消已发生的记录写入。

mailbox 为 IDLE/PENDING/DONE。最后一次提交／POLL 后 **30 秒无活动**，owner 执行 TIMEOUT 清理；这是空闲超时，不是整个 META 只能运行 30 秒。只要持续合法 POLL，大文件哈希可超过 30 秒，主机仍必须另有整个作业 deadline。失败清理保留 CANCELLED/TIMEOUT/IO_ERROR，不能伪装成功。

### 8.3 LIST 分页

```text
LOGFILE LIST 0
PENDING LOGFILE LIST request_id=<id>
LOGFILE POLL <id>
OK LOGFILE LIST request_id=<id> file_id=<1..999999> size=<bytes> closed=1 next_cursor=<u32> end=0

LOGFILE LIST <next_cursor>
...
OK LOGFILE LIST request_id=<id> end=1 next_cursor=0
```

cursor 为不透明枚举游标，不是可任意替换的 file_id，也不保证所有工程都以文件号排序。使用返回的 next_cursor，拒绝重复 file_id／cursor、非法 end 和缺失 closed=1；GSHC 一次最多列出 1024 份。结束行没有文件条目。file_id 指向固定 mission 日志，协议不接受任意路径、路径穿越、目录名或文件名输入。

closed=1 表示该服务当前不把它作为打开 writer；不倒推历史固件曾正常 flush/close，更不认证旧记录完整性或全卡文件系统健康。

### 8.4 META 和 token

```text
LOGFILE META 67
PENDING LOGFILE META request_id=<id>
LOGFILE POLL <id>
OK LOGFILE META request_id=<id> file_id=67 token=1-CCFD819A-000012D4 size=4820 crc32=CCFD819A format=SSLOG format_version=0.0 closed=1
```

token 固定 19 个字符：`1-<CRC32八位大写hex>-<size八位大写hex>`，size 同时另以十进制返回。META 每个 LoggerTask 周期最多读 512-byte 哈希量子；SerialTask 只提交／取结果。hash 完成／句柄关闭且实际字节数等于 size 后才发布并缓存该 file_id/size/crc；失败不保留可用 cache。

CRC32 使用反射 0xEDB88320、初值 FFFFFFFF、最后取反，与标准 zlib.crc32 一致。CRC 及 token 用来检查变化，**不是稳定设备／启动／文件的强身份**。历史实测 ID69、ID67 恰有相同长度和整文件 CRC，但头部构建身份与 SHA-256 不同，不能据 token 将二者混为同一文件。

### 8.5 READ

```text
LOGFILE READ 67 1-CCFD819A-000012D4 0
PENDING LOGFILE READ request_id=<id>
LOGFILE POLL <id>
OK LOGFILE READ request_id=<id> file_id=67 token=1-CCFD819A-000012D4 offset=0 length=64 crc32=<8HEX> data=<128个大写hex字符>
```

READ 必须对应当前 META cache 的 file_id、size、crc；否则 STALE，不能用旧连接的缓存继续。offset 为十进制字节偏移，0..size，返回最多 64 字节；一般 `length=min(64,size-offset)`。offset=size 可返回 length=0、data=-、空块 CRC；offset>size BAD_ARGUMENT。读取器会复核文件大小，不提供任意长度、写入、上传或远程 seek 状态恢复 API。

分块校验必须核实 request_id、file_id、token、offset、预期 length、hex 长度及该块 crc32，不能只看响应前缀。每次块请求依旧遵循异步 mailbox/POLL。

## 9. 维护关闭状态机与 bootstrap 关闭修复

```text
Off --合法 ENTER--> Draining --排空/flush/close/最终状态保存全部成功--> Ready
                         \--任一 owner I/O/关闭/最终状态保存失败-----> Failed
Ready/Failed --重复 ENTER--> 保持原有结果
Ready/Failed --CANCEL------> 只清理文件 mailbox；维护状态仍锁存
重启：重新初始化预约；旧打开文件不会因复位自动获得关闭证明
```

当前实现不要求先达到 logger StreamingReady 才能请求安全关闭。logger BOOTSTRAP 在 active session 的真实 header、decoder descriptor 和初始配置就绪后即可关闭；若启动报告已完成，先保留该报告。未就绪校准／IMU不被伪造为可用，不制造 mission snapshot 或任务 Ready。Bus 在现有临界区停止接收新记录，已接收数据继续排空，再按既有 flush、close、最终状态持久化顺序完成。错误保留 Failed，不能因为 writer 看起来 closed 就授予读取许可。

主机只有在完整新鲜 STATUS 满足下列条件后才进行 LIST/META/READ：maintenance=2、finalization=3、storage_valid=1、mounted=1、healthy=1、writer_open=0、log_fault=0、cleanup_pending=0，且 age_ms≤3000。本轮 Ready 记录 age_ms=4；随后复查 5／9 ms 仍闭合。maintenance Ready 与任务 ready 是不同量：实测 `SYSTEM STATUS ready=0`、primary_imu_unavailable 持续保留。

## 10. 错误码、重试和主机 deadline

| 领域 | code／reason | 处理 |
|---|---|---|
| 通用 parser | BAD_FORMAT/TOKEN_COUNT、INSTANCE_REQUIRED、LINE_TOO_LONG；BAD_INSTANCE/FORMAT、RANGE；BAD_MODULE/UNKNOWN；BAD_COMMAND/UNKNOWN、UNKNOWN_SUBCOMMAND | 修正请求，不能补造默认实例或忽略多余参数 |
| Device 结果映射 | NOT_READY、OFFLINE、UNSUPPORTED、BAD_PARAM、TIMEOUT、IO_ERROR、VERIFY_FAILED、BAD_STATE、BUSY、NOT_PRESENT、INTERNAL | 保留具体失败；BAD_PARAM 与 LOGFILE BAD_ARGUMENT 不混同 |
| Device 非失败结果文字 | OK、ALREADY_MATCHED、VALUE_ADJUSTED、NO_ACTION、DELEGATED、NOT_EXECUTED | 按操作和 valid/read_result 解释，不统一当“硬件验证通过” |
| 状态／能力拒绝 | LOCKED/FLIGHT、UNSUPPORTED/DEVICE、HARDWARE_READ、DEVICE_OPERATION 等 | Parser 白名单和 owner 结果均须尊重；reason=FLIGHT 是现有通用锁定文本，不单独证明当前真在飞行 |
| MAG CAL | FAILED + reason=NOT_READY/BAD_ARGUMENT/INVALID_OBJECT/WRONG_DEVICE/BUSY/NOT_PRESENT/STORAGE_ERROR | 校准包／身份／持久化错误保留，不用其他设备数据代替 |
| LOGFILE | BAD_ARGUMENT、BUSY、LOCKED、NOT_READY、NOT_FOUND、STALE、IO_ERROR、CANCELLED、TIMEOUT、UNSUPPORTED | `ERR LOGFILE <op> request_id=<id> code=<code>`；解析错误标签可为 PARSE；拒绝前可能 request_id=0 |
| DIAG | BAD_ARGUMENT/CURSOR、UNSUPPORTED 或畸形／缺失关键版本 | 显示不可用／UNKNOWN，不继承另一固件或上次连接的值 |

现有 GSHC FileServiceClient 将 UNSUPPORTED/BAD_MODULE/BAD_COMMAND 映射 unsupported，BUSY/LOCKED/NOT_READY 映射 busy，STALE 映射 stale，其余设备 ERR 映射 I/O error；仍应保留原始 code/detail。每条响应默认等待 2 秒（可在 0.1..30 秒范围设置）；pending 轮询有 0..50 ms 有界退避。等待维护 Ready 时每轮最多 100 ms 等待，失败 maintenance=3 立即退出。

Maintenance API／文件 Job 默认整个作业 300 秒，可显式指定 (0,3600] 秒；本轮 LIST 用 90 秒预算，选定下载用 3600 秒上界但实际正常结束。客户端 deadline 与固件 30 秒 mailbox 空闲超时彼此独立。取消／超时后尽力发 CANCEL，确认主机 transport 正常关闭；关闭失败不能报告整体成功。不得无限轮询、并发抢串口、重放旧 request_id，或将一次 response timeout 当作记录不存在。

## 11. 只读复制、校验和删除支持边界

正式复制顺序：独占维护串口 → 新 CAPS → 新 STATUS → 明确 ENTER → 等待真实 Ready → 完整 LIST → 每份文件新 CAPS+META → 新独占本地 partial → READ/POLL 各块校验 → 全文件 CRC → 再 META 检查 size/crc/token → fsync → 本地重新读取 SHA-256／长度 → 原子发布副本和 manifest → CANCEL 清理 mailbox → 关闭串口。多份文件还须逐份核对选中 ID 仍在新列表中。

本地旧 partial 不计入可续传内容，也不覆盖已有正式副本；空间须容纳完整新文件及 metadata。失败／取消保留 partial 和诊断 checkpoint 供检查，重新下载从零开始。成功时仅移除本作业独有的主机 checkpoint；不删除 TF 文件。本地 manifest 保存 file_id、source token、size、crc32、SHA-256 和校验范围。

当前 CAPS 明确 `delete_supported=0 device_id=unknown boot_id=unknown telemetry_bulk=0`。固件对识别到的 `DELETE ... CONFIRM` 返回 UNSUPPORTED；GSHC prepare_delete/delete 也拒绝，用户确认 token 不能开启此能力。**没有实际远程删除、格式化、文件上传、任意路径 API、稳定 boot/device identity、断点续传或 AIR/telemetry bulk 下载实现。** 本轮没在实卡发送 DELETE/FORMAT，删除拒绝边界依据源码与既有 Host 测试。

SSLOG 副本不因传输 CRC 通过就自动成为完整有效的数据集。生产 FLP 打开仍要求该记录对应的精确 .ssdecoder 与 Descriptor，经 LogOpenCoordinator；不回退离线默认值。当前 GSHC export manifest 明示 `recorded_descriptor_included=false`、`decoder_package_included=false`，不能凭运行中的新固件给旧日志补配身份。

## 12. 整行提交、背压与主机同步

DebugLog 的 320 字节缓冲区在截断时保留 CRLF 和 NUL，分别检查前缀和正文格式化结果。SystemConsole 异步 320 字节缓冲区先检查内部终止，再按有界截断补全 CRLF；普通 3072 字节回复为行尾预留空间。未终止的内部字符串进入既有 fail-stop，普通外部坏包和容量不足仍走错误返回。

Console UART 使用既有 `PlatformUart_WriteFrameAsync`，整段排入或整段拒绝；满队列不发表部分前缀。拒绝字节数通过饱和计数并入 `ConsoleUart_DiagnosticsGet().tx_discarded_bytes` 和 Console health；失败的 best-effort 日志不假装成功。UART 普通 TX ring 为 Console 保留 4096 字节（4095 可用），容纳 3071 字节 legacy 回复；priority 为 1024、RX DMA 为 128，其他 UART 仍按各自生成绑定配置。硬件/资源组合需各自验证。

LOGFILE DONE 在原 mailbox 临界区内有界扫描并只复制真实长度加 NUL；调用方容量不足时返回兼容 BAD_ARGUMENT，保留 DONE 供重试。该临界区不执行 FatFs I/O。

GSHC 先执行有界 SYSTEM INFO 同步探测，隔离探测原始字节，再发送新的严格业务请求。探测行不作为能力或状态权威。LOGFILE v1 缺必要字段是 BAD_RESPONSE；不得拼接散落字段、补默认值或伪装旧固件。原 511 字节客户端行上限、64 字节 READ、CRC/长度/token 与新鲜状态检查保持有效。下载期间暂停诊断分页，旧读数继续过期，断开后清空实时状态和目录。

## 13. 精确硬件证据与当前工作区边界

历史 R04 已经独立完成维护实测：源码快照 `27e2dd65e1d4603a809843195141426549976476`，ELF SHA-256 `717ea512ddd394438a77314432e904aa65387fa7c2792939bc90bb78086bf7fc`，全 512 KiB Flash 读回 SHA-256 `edefd382efc2092df5c51ebb7cc81fc05ddb9c2b2d9c00eddcd8b4c075e6345c`，sector7/option 保留。北京时间 2026-10-17 15:30:36 软件复位启动后，记录 lifecycle 1→2、真实维护关闭 maintenance=2/writer_open=0/finalization=3/healthy=1，未执行 START。

该精确 R04 的 5 次同连接协商及 4 次关闭/重开协商通过；TF 目录为 69 份，实取 ID69 与历史 ID67 各 4820 字节，共 9640 字节，152 READ、4 META。块和整文件 CRC、META 复查、本地 SHA-256、各自精确 decoder 审计通过。实连接 GUI 显示 7 个串口诊断和 69 条目录；原生 I/O 在 GUI 线程外，断开后清空实时数据。记录位于 `.work/dev013_gshc_tf_hw02/r04/hardware/`，属于正式保留证据。

本轮只合入源码、生成、编译和离线 GUI 检查，没有连接探针或串口，也没有烧录。当前工作区保留较新的导航及并行 USB 改动；由它新生成的固件与 R04 不同，不能把上述硬件结论移用于新二进制。R04 197 字节非权威探测中仍观察到桥接链路中段丢字节；桥接器/桥固件问题未定位，不能声称桥接问题已根治。

实时负载、整卡备份、实卡故障注入、实体触摸屏/所有 DPI、完整 MSP/ISR/库间接栈、WCET、导航精度与飞行资格均未由本轮证明。文本 gate 通过也不代表关键合同人工接受完成；NOT PROVEN 必须保留。R04 软件证据和当前合入后的精确测试结果分别见各自报告，不混成未执行的整套通过。

## 14. 普通源码入口与来源

从仓库根运行 `python apps/GSHC/main.py`；从 GSHC 目录运行 `python main.py`。正常程序启动为断开状态，维护端口与 AIR 地面端口分别选择，不自动打开硬件。ELF 变量观察需要匹配 `.ssdiag` 和可用的 pyelftools/pyOCD 依赖；不能从 core/family ID 猜完整 MCU 订货型号。可选依赖的配置方式见 `transport/swd_firmware.py` 与 `transport/_swd_pyocd.py`。

当前根产品版本为 0.1.3，而核心用户配置 payload 的普通默认版本仍为 0.1.2（本轮合入前也是如此）。显式 `test_build` 会生成有界的版本、build、build_tag 和源码基点字段；本轮新生成工程为软件检查专用 `0.1.3 / build 5 / SST013M1`，不是已实测 R04，也不是发布候选。普通发布身份统一属于独立版本收尾，本轮未修改根 VERSION 或擅改用户默认版本。

本地维护 CLI 为 `python apps/GSHC/maintenance_cli.py --help`；`probe/status` 只查询，`list/download` 必须明确 `--enter-maintenance`；下载还必须指定本地目录以及选中文件或 `--all-closed`。ENTER 会关闭日志并在重启前排除 START，不是普通的无副作用查询。本轮不会执行这些硬件命令。

源码依赖与回退清单位于 `.work/dev013_gshc_tf_hw02/merge01/`。固件实现归属 `silverstar_core_0_1_0/payload/System/Src/system_console.c`、`system_log_file.c`、`APP/Src/logger_task.c`、`logger_bus.c` 和 Console UART 插件；主机归属 `apps/GSHC/services/`、`transport/`。下列模板重新从合入后的 owning 源码提取，行号只供查阅，C 控制流和机器合同仍是判定依据。

## 附录：本地实现的响应字段模板

### Template 1 — system_console.c:168

```text
 %s%s=%s
```

### Template 2 — system_console.c:203

```text
 %s_alignment_ready=%u
```

### Template 3 — system_console.c:537

```text
ERR %s %s code=%s reason=%s
```

### Template 4 — system_console.c:733

```text
OK %s %s initialized=%u started=%u online=%u healthy=%u tx=%lu rx=%lu integrity_errors=%lu
```

### Template 5 — system_console.c:753

```text
OK LOG %s initialized=%u mounted=%u open=%u healthy=%u writes=%lu syncs=%lu errors=%lu
```

### Template 6 — system_console.c:778

```text
OK OUTPUT %s ch1_state=%u ch1_active=%u ch1_fault=%u ch2_state=%u ch2_active=%u ch2_fault=%u
```

### Template 7 — system_console.c:800

```text
OK %s %s initialized=%u started=%u online=%u healthy=%u samples=%lu errors=%lu timeouts=%lu
```

### Template 8 — system_console.c:860

```text
OK %s CONFIG SHOW mask=0x%08lX rate_hz=%u accel_bw_millihz=%ld gyro_bw_millihz=%ld accel_range_millig=%ld gyro_range_dps=%ld
```

### Template 9 — system_console.c:882

```text
OK %s CONFIG SHOW source=CACHE mask=0x%08lX rate_hz=%u constellations=0x%08lX dynamic_model=%u protocol=%u messages=0x%08lX
```

### Template 10 — system_console.c:904

```text
OK %s CONFIG SHOW mask=0x%08lX rate_hz=%u
```

### Template 11 — system_console.c:922

```text
OK %s CONFIG SHOW mask=0x%08lX rate_hz=%u range_milliuT=%ld
```

### Template 12 — system_console.c:941

```text
OK %s CONFIG SHOW mask=0x%08lX mode=%u rate_hz=%u
```

### Template 13 — system_console.c:960

```text
OK %s CONFIG SHOW mask=0x%08lX voltage_scale_ppm=%ld voltage_offset_uv=%ld
```

### Template 14 — system_console.c:1039

```text
OK SYSTEM STARTUP completed=%u passed=%u mission_capable=%u degraded=%u required_fail=0x%08lX optional_fail=0x%08lX warning=0x%08lX devices=%u
```

### Template 15 — system_console.c:1070

```text
OK SYSTEM STARTUP %s id=%u name=%s model=%s required=%u present=%u init=%s start=%s config=%s persist=%s verify=%s communication=%s requested=0x%08lX applied=0x%08lX delegated=0x%08lX failed=0x%08lX detail=%lu retry=%lu
```

### Template 16 — system_console.c:1103

```text
 failed_step=%u ack=%u write_layers=0x%02X uart=%s uart_settle=%s protocol=%s nav_pvt=%s rate=%s dynamic_model=%s signals=%s pvt_recovery=%s baseline_pvt=%lu recovered_pvt=%lu signal_complete_us=%lu verify_read_result=%s verify_failed_group=%s verify_failed_key=0x%08lX verify_response_length=%u verify_nak_class=0x%02X verify_nak_id=0x%02X verify_valid_mask=0x%08lX apply_failed_mask=0x%08lX persist_failed_mask=0x%08lX verify_failed_mask=0x%08lX verify_detailed_result=%s verify_expected_class=0x%02X verify_expected_id=0x%02X verify_received_class=0x%02X verify_received_id=0x%02X verify_response_version=%u
```

### Template 17 — system_console.c:1145

```text
 apply_failed_mask=0x%08lX persist_failed_mask=0x%08lX verify_failed_mask=0x%08lX
```

### Template 18 — system_console.c:1400

```text
OK %s IO CLEAR
```

### Template 19 — system_console.c:1416

```text
OK %s IO transport=%s owner=%s owner_instance=%u physical_device_id=%u supported_mask=0x%08lX valid_mask=0x%08lX rx_active=%u rx_bytes=%lu tx_bytes=%lu rx_events=%lu idle_events=%lu tc_events=%lu discarded=%lu ore=%lu framing=%lu noise=%lu parity=%lu dma_errors=%lu restarts=%lu restart_failures=%lu discontinuities=%lu integrity_errors=%lu timeouts=%lu transport_errors=%lu spi_errors=%lu spi_timeouts=%lu busy_timeouts=%lu
```

### Template 20 — system_console.c:1485

```text
 ubx_frames=%lu ubx_checksum_errors=%lu nmea_sentences=%lu nmea_checksum_ok=%lu nmea_checksum_errors=%lu unknown_bytes=%lu parser_resyncs=%lu
```

### Template 21 — system_console.c:1508

```text
 valid_frames=%lu checksum_errors=%lu parser_resyncs=%lu
```

### Template 22 — system_console.c:1584

```text
OK SYSTEM FLIGHT deploy_mask=0x%02lX matched_mask=0x%02lX deploy_triggered=%u tilt_deg=%.2f vz_mps=%.2f delay_ms=%lu landing_mode=%s landing_state=%s baro_valid=%u baro_age_ms=%lu baro_trigger_rate_mps=%.3f candidate_active=%u candidate_elapsed_ms=%lu candidate_baro_samples=%lu candidate_imu_samples=%lu baro_slope_mps=%.3f baro_span_m=%.3f gyro_norm_radps=%.3f accel_norm_mps2=%.3f accel_g_error_mps2=%.3f impact_capable=%u impact_armed=%u impact_threshold_mps2=%.2f
```

### Template 23 — system_console.c:1636

```text
OK SYSTEM START RESULT state=PENDING request_id=%lu
```

### Template 24 — system_console.c:1641

```text
OK SYSTEM START RESULT state=COMPLETE request_id=%lu result=%s reason=%s timestamp_us=%lu
```

### Template 25 — system_console.c:1673

```text
OK SYSTEM START state=PENDING request_id=%lu
```

### Template 26 — system_console.c:1697

```text
OK SYSTEM STATUS state=%u ready=%u block=0x%08lX warn=0x%08lX attitude=%s
```

### Template 27 — system_console.c:1727

```text
OK SYSTEM STACK unit=words valid_mask=0x%02lX DeviceTask=%lu/%lu InsTask=%lu/%lu EstimatorTask=%lu/%lu FlightTask=%lu/%lu LoggerTask=%lu/%lu SerialTask=%lu/%lu RadioTask=%lu/%lu
```

### Template 28 — system_console.c:1756

```text
OK SYSTEM INFO project=SilverStar version=<firmware_version> profile=0x%08lX<build_identity_fields>
```

### Template 29 — system_console.c:1756

```text
 profile=0x%08lX<build_identity_fields>
```

### Template 30 — system_console.c:1774

```text
OK SYSTEM CAPABILITIES compiled=0x%08lX enabled=0x%08lX present=0x%08lX healthy=0x%08lX
```

### Template 31 — system_console.c:1792

```text
OK SYSTEM PROFILE id=0x%08lX frozen=%u
```

### Template 32 — system_console.c:1825

```text
OK SYSTEM READY ready=%u block=0x%08lX attitude_ready=%u attitude_reason=%s gnss_ready=%u gnss_origin_ready=%u gnss_fusion_enabled=%u alignment_ready=%u imu_alignment_ready=%u
```

### Template 33 — system_console.c:1837

```text
 calibration_ready=%u calibration_mode=%s capability_required_for_air_start=1
```

### Template 34 — system_console.c:1870

```text
OK SYSTEM DIAG version=1 id=%s group=%s name=%s readonly=1 next_cursor=%u end=0
```

### Template 35 — system_console.c:1895

```text
 state=%s reason=%s source=SystemHealth age_ms=%lu sequence=%lu block=0x%08lX warn=0x%08lX
```

### Template 36 — system_console.c:1908

```text
 state=UNKNOWN reason=not_published source=LoggerTask age_ms=4294967295
```

### Template 37 — system_console.c:1910

```text
 state=%s reason=%s source=LoggerTask age_ms=%lu sequence=%lu counter=%lu unit=completed_writes work_age_ms=%lu
```

### Template 38 — system_console.c:1923

```text
 state=UNKNOWN reason=not_published source=Estimator age_ms=4294967295
```

### Template 39 — system_console.c:1926

```text
 state=OBSERVED reason=state_time_not_task_heartbeat source=Estimator age_ms=4294967295 counter=%lu unit=predictions data_age_ms=%lu started=%u
```

### Template 40 — system_console.c:1937

```text
 state=UNKNOWN reason=not_published source=INS age_ms=4294967295
```

### Template 41 — system_console.c:1939

```text
 state=%s reason=solution_validity_not_sensor_online source=INS age_ms=4294967295 data_age_ms=%lu quaternion_valid=%u velocity_valid=%u position_valid=%u
```

### Template 42 — system_console.c:1951

```text
 state=UNKNOWN reason=not_available source=StorageHealth age_ms=4294967295
```

### Template 43 — system_console.c:1953

```text
 state=%s reason=ram_observation source=StorageHealth age_ms=4294967295 mounted=%u open=%u healthy=%u counter=%lu unit=write_attempts syncs=%lu errors=%lu
```

### Template 44 — system_console.c:1965

```text
OK SYSTEM DIAG version=1 maintenance=0.1 compatible=0.0 file_service_version=1 entries=7 max_entries=16 max_line=511 polling_ms=1000 firmware=<firmware_version><build_identity_fields>
```

### Template 45 — system_console.c:1974

```text
 state=OBSERVED reason=not_start_authorization source=Lifecycle age_ms=4294967295 phase=%u
```

### Template 46 — system_console.c:1983

```text
 state=UNKNOWN reason=completion_not_instrumented source=not_available age_ms=4294967295
```

### Template 47 — system_console.c:1986

```text
OK SYSTEM DIAG version=1 end=1 next_cursor=0
```

### Template 48 — system_console.c:2104

```text
OK CAL START mode=%s state=%s ready=%u
```

### Template 49 — system_console.c:2142

```text
OK CAL FACE face=%s accepted=1 state=%s completed_face_mask=0x%02X
```

### Template 50 — system_console.c:2182

```text
OK CAL %s mode=%s state=%s ready=%u completed_face_mask=0x%02X
```

### Template 51 — system_console.c:2195

```text
OK CAL STATUS mode=%s state=%s ready=%u current_face=%s last_face=%s last_face_result=%s completed_face_mask=0x%02X samples=%lu
```

### Template 52 — system_console.c:2212

```text
OK CAL DETAIL mode=%s state=%s ready=%u current_face=%s last_face=%s last_face_result=%s completed_face_mask=0x%02X samples=%lu reject_count=%lu retry_count=%lu wait_reason=%s accel_bias=[%.6f,%.6f,%.6f] accel_scale=[%.6f,%.6f,%.6f] gyro_bias=[%.6f,%.6f,%.6f] gyro_scale=[%.6f,%.6f,%.6f] face_xp_acc=[%.6f,%.6f,%.6f] face_xn_acc=[%.6f,%.6f,%.6f] face_yp_acc=[%.6f,%.6f,%.6f] face_yn_acc=[%.6f,%.6f,%.6f] face_zp_acc=[%.6f,%.6f,%.6f] face_zn_acc=[%.6f,%.6f,%.6f]
```

### Template 53 — system_console.c:2336

```text
OK ALIGN START accepted=1 state=%s ready=%u config=%s unavailable_mask=0x%08lX missing_adapter_mask=0x%08lX
```

### Template 54 — system_console.c:2365

```text
OK ALIGN %s state=IDLE
```

### Template 55 — system_console.c:2379

```text
OK ALIGN STATUS state=%s ready=%u config=%s capability_mask=0x%08lX selected_mask=0x%08lX required_mask=0x%08lX ready_mask=0x%08lX unavailable_mask=0x%08lX missing_adapter_mask=0x%08lX stale_reason=%s attitude_algorithm=%u attitude_source=%s final_yaw_deg=%.3f known_yaw_deg=%.3f declination_deg=%.3f final_q_frozen=%u
```

### Template 56 — system_console.c:2426

```text
OK ALIGN DETAIL state=%s ready=%u config=%s capability_mask=0x%08lX selected_mask=0x%08lX required_mask=0x%08lX ready_mask=0x%08lX stale_reason=%s
```

### Template 57 — system_console.c:2496

```text
OK %s CONFIG READ source=HARDWARE read_result=%s valid_mask=0x%08lX baudrate=%lu protocol=%u protocol_in=0x%02X nav_pvt_rate=%u nav_pvt_known=%u navigation_rate=%u dynamic_model=%u constellation_mask=0x%08lX elapsed_ms=%lu response_result=%s failed_group=%s failed_key=0x%08lX nak_class=0x%02X nak_id=0x%02X response_length=%u transaction_id=%lu detailed_result=%s expected_class=0x%02X expected_id=0x%02X received_class=0x%02X received_id=0x%02X response_version=%u unsupported_mask=0x%08lX
```

### Template 58 — system_console.c:2541

```text
OK %s NAV SAT read_result=%s supported_mask=0x%08lX valid_mask=0x%08lX sequence=%lu satellite_count=%u used_count=%u average_cno_dbhz=%u maximum_cno_dbhz=%u average_quality=%u fresh=%u transaction_id=%lu response_result=%s detailed_result=%s response_length=%u expected_class=0x%02X expected_id=0x%02X received_class=0x%02X received_id=0x%02X expected_ck_a=0x%02X expected_ck_b=0x%02X received_ck_a=0x%02X received_ck_b=0x%02X
```

### Template 59 — system_console.c:2584

```text
OK %s MON RF read_result=%s supported_mask=0x%08lX valid_mask=0x%08lX sequence=%lu rf_block_count=%u antenna_status=%u antenna_power=%u jamming_indicator=%u noise_per_ms=%u agc_count=%u fresh=%u transaction_id=%lu response_result=%s detailed_result=%s response_length=%u jamming_state=%u cw_suppression=%u
```

### Template 60 — system_console.c:2619

```text
OK TIME STATUS monotonic_us=%lu mission_started=%u mission_us=%lu
```

### Template 61 — system_console.c:2714

```text
OK %s INFO device=%s model=%s driver=%s
```

### Template 62 — system_console.c:2746

```text
OK %s CAPABILITIES mask=0x%08lX
```

### Template 63 — system_console.c:2926

```text
OK %s SAMPLE DETAIL device=%s model=%s supported_mask=0x%08lX valid_mask=0x%08lX fix_type=%s fix_ok=%s num_sv=%s lat_e7=%s lon_e7=%s height_mm=%s hacc_mm=%s vacc_mm=%s sacc_mmps=%s age_ms=%s position_usable=%u velocity_mask=0x%02X position_reject_mask=0x%08lX velocity_reject_mask=0x%08lX quality_degraded=%u
```

### Template 64 — system_console.c:3121

```text
OK %s SAMPLE DETAIL device=%s model=%s supported=%u present=%u configured=%u supported_mask=0x%08lX valid_mask=0x%08lX sample_valid=%u sample_fresh=%u sample_age_ms=%s pressure_pa=%s temperature_c=%s altitude_m=%s status=%s
```

### Template 65 — system_console.c:3241

```text
OK ESTIMATOR BARO source_supported=%u sample_valid=%u sample_age_ms=%s origin_state=%s origin_sample_count=%lu origin_required_count=%lu origin_altitude_m=%.3f origin_pressure_pa=%s relative_altitude_m=%.3f measurement_variance=%.3f last_update_state=%s last_innovation=%.3f last_innovation_variance=%.3f last_nis=%.3f accepted_count=%lu softened_count=%lu rejected_count=%lu skipped_count=%lu last_skip_reason=%s last_update_age_ms=%s
```

### Template 66 — system_console.c:3303

```text
OK ESTIMATOR STATUS state=%u initialized=%u started=%u mode=%s attitude_source=%s position_source=%s imu_prediction_count=%lu last_state_timestamp=%lu
```

### Template 67 — system_console.c:3406

```text
OK ESTIMATOR GNSS supported=%u fusion_enabled=%u origin_valid=%u origin_lat_e7=%ld origin_lon_e7=%ld origin_height_mm=%ld position_updates=%lu velocity_updates=%lu position_accept_count=%lu position_reject_count=%lu velocity_accept_count=%lu velocity_reject_count=%lu last_update_state=%s last_skip_reason=%s reason=%s last_measurement_timestamp=%lu last_state_timestamp=%lu measurement_age_ms=%s
```

### Template 68 — system_console.c:3433

```text
 position_horizontal_nis=%.3f position_vertical_nis=%.3f velocity_horizontal_nis=%.3f velocity_vertical_nis=%.3f innovation_e=%.3f innovation_n=%.3f innovation_u=%.3f innovation_ve=%.3f innovation_vn=%.3f innovation_vu=%.3f position_horizontal_effective_std_m=%.3f position_vertical_effective_std_m=%.3f velocity_horizontal_effective_std_mps=%.3f velocity_vertical_effective_std_mps=%.3f P_E=%.6g P_N=%.6g P_U=%.6g P_vE=%.6g P_vN=%.6g P_vU=%.6g position_horizontal_accept_count=%lu position_horizontal_reject_count=%lu position_vertical_accept_count=%lu position_vertical_reject_count=%lu velocity_horizontal_accept_count=%lu velocity_horizontal_reject_count=%lu velocity_vertical_accept_count=%lu velocity_vertical_reject_count=%lu position_horizontal_reject_streak=%lu position_vertical_reject_streak=%lu velocity_horizontal_reject_streak=%lu velocity_vertical_reject_streak=%lu reacquire_active_mask=0x%02X reacquire_count=%lu last_inflation_group=%s last_inflation_factor=%.3f last_inflation_attempt=%lu
```

### Template 69 — system_console.c:3529

```text
OK KF STATUS initialized=%u state_dimension=%u prediction_count=%lu sequential_update_count=%lu position_update_count=%lu velocity_update_count=%lu baro_update_count=%lu last_update_type=%s last_update_time=%lu innovation_reject_count=%lu
```

### Template 70 — system_console.c:3542

```text
 reacquire_count=%lu reacquire_active_mask=0x%02X
```

### Template 71 — system_console.c:3564

```text
OK INS STATUS initialized=%u started=%u attitude_ready=%u quaternion_valid=%u velocity_valid=%u position_valid=%u software_attitude_propagation=%u bias_ready=%u bias_samples=%lu last_update_timestamp=%lu
```

### Template 72 — system_console.c:3590

```text
OK %s SAMPLE seq=%lu sample_us=%lu receive_us=%lu valid=0x%08lX
```

### Template 73 — system_console.c:3611

```text
OK %s SAMPLE seq=%lu lat_e7=%ld lon_e7=%ld fix=%u position_usable=%u velocity_mask=0x%02X
```

### Template 74 — system_console.c:3632

```text
OK %s SAMPLE seq=%lu pressure_pa=%ld altitude_cm=%ld valid=0x%08lX
```

### Template 75 — system_console.c:3651

```text
OK %s SAMPLE seq=%lu raw=%ld,%ld,%ld physical_valid=%u calibration_valid=%u
```

### Template 76 — system_console.c:3673

```text
OK %s SAMPLE seq=%lu mode=%u normalized=%u valid=%u
```

### Template 77 — system_console.c:3692

```text
OK %s SAMPLE seq=%lu millivolts=%ld valid=0x%08lX sample_us=%lu receive_us=%lu
```

### Template 78 — system_console.c:3817

```text
EVENT MAG SAMPLE instance=%u physical_device_id=%u seq=%lu sample_us=%lu x_uT=%.4f y_uT=%.4f z_uT=%.4f\r\n
```

### Template 79 — system_console.c:3842

```text
EVENT CAL DIAG face=%s reason=%s\r\n
```

### Template 80 — system_console.c:3863

```text
EVENT CAL FACE face=%s result=%s samples=%lu completed_face_mask=0x%02X\r\n
```

### Template 81 — system_console.c:3871

```text
EVENT CAL FACE face=%s result=%s reason=%s completed_face_mask=0x%02X\r\n
```

### Template 82 — system_console.c:3891

```text
EVENT CAL COMPLETE mode=%s result=%s samples=%lu completed_face_mask=0x%02X reason=%s\r\n
```

### Template 83 — system_console.c:3941

```text
EVENT ALIGN COMPLETE result=%s ready_mask=0x%08lX
```

### Template 84 — system_console.c:3969

```text
EVENT ALIGN STALE reason=%s ready_mask=0x%08lX\r\n
```

### Template 85 — system_console.c:3996

```text
EVENT FLIGHT ACTION_FAILED action=%s result=%s time_ms=%lu\r\n
```

### Template 86 — system_console.c:4011

```text
EVENT FLIGHT PARACHUTE_DEPLOY matched_mask=0x%02lX time_ms=%lu tilt_deg=%.2f vz_mps=%.2f delay_ms=%lu\r\n
```

### Template 87 — system_console.c:4028

```text
EVENT FLIGHT LANDING_IMPACT time_ms=%lu metric_mps2=%.2f peak_mps2=%.2f state=%s\r\n
```

### Template 88 — system_console.c:4044

```text
EVENT FLIGHT LANDING time_ms=%lu\r\n
```

### Template 89 — system_console.c:4455

```text
OK %s LIST count=%u
```

### Template 90 — system_console.c:4468

```text
 DATA instance=%u descriptor_id=%u physical_device_id=%u shared=%u device=%s model=%s
```

### Template 91 — system_console.c:4617

```text
OK %s STREAM state=STOPPED
```

### Template 92 — system_console.c:4631

```text
OK %s STREAM state=STARTED rate_hz=20
```

### Template 93 — system_console.c:4669

```text
OK %s CAL state=%s generation=%lu physical_device_id=%u instance=%u saved=%u pending=%u failed=%u load_error=%s
```

### Template 94 — system_console.c:4718

```text
OK %s CAL action=%s accepted=1
```

### Template 95 — system_console.c:4809

```text
ERR SYSTEM PARSE code=BAD_FORMAT reason=LINE_TOO_LONG\r\n
```

### Template 96 — system_log_file.c:233

```text
ERR LOGFILE %s request_id=%lu code=%s
```

### Template 97 — system_log_file.c:279

```text
PENDING LOGFILE %s request_id=%lu
```

### Template 98 — system_log_file.c:318

```text
OK LOGFILE CANCEL cancelled=1 cleanup_complete=0
```

### Template 99 — system_log_file.c:346

```text
OK LOGFILE STATUS status_version=1 source=FC_DEBUG_RAM sequence=%lu age_ms=%lu lifecycle=%u storage_valid=%u mounted=%u healthy=%u writer_open=%u log_fault=%u finalization=%u maintenance=%u cleanup_pending=%u reboot_required=%u
```

### Template 100 — system_log_file.c:363

```text
OK LOGFILE ENTER accepted=1 maintenance=%u reboot_required=1
```

### Template 101 — system_log_file.c:388

```text
OK LOGFILE CAPS file_service_version=1 supported=%u max_chunk=64 delete_supported=0 telemetry_bulk=0 device_id=unknown boot_id=unknown status_version=1 maintenance_required=1 firmware=<firmware_version><build_identity_fields>
```

### Template 102 — system_log_file.c:418

```text
OK LOGFILE META request_id=%lu file_id=%lu token=1-%08lX-%08lX size=%lu crc32=%08lX format=SSLOG format_version=0.0 closed=1
```

### Template 103 — system_log_file.c:486

```text
OK LOGFILE READ request_id=%lu file_id=%lu token=1-%08lX-%08lX offset=%lu length=%u crc32=%08lX data=%s
```

### Template 104 — system_log_file.c:504

```text
OK LOGFILE LIST request_id=%lu end=1 next_cursor=0
```

### Template 105 — system_log_file.c:507

```text
OK LOGFILE LIST request_id=%lu file_id=%lu size=%lu closed=1 next_cursor=%lu end=0
```


## Negotiated LOGFILE block extension (2026-10-20, maintenance 0.1 development)

The machine authority is [log_file_service_v1.json](../../../../../../contracts/log_file_service_v1.json).
This additive extension retains maintenance0.0 commands, maintenance0.1 text controls,
legacy LOGFILE v1 `max_chunk=64`/READ, AIR M0 and SSLOG bytes. It is independent of
product version and is not a release or hardware qualification statement.

CAPS adds `block_version=1 max_block=512 block_encoding=COBS block_window=1`.
GSHC opts in only when every field and its local binary transport are supported.
An older peer without the extension, or a line-only local transport, uses the
existing64-byte READ path. Malformed/unknown extension fields fail closed.

`LOGFILE BLOCK <file_id> <token> <offset> <nonce16hex> <sequence>` submits one
operation and receives `PENDING LOGFILE BLOCK request_id=<id>`. Only LoggerTask
reads TF. `LOGFILE POLL <id>` returns PENDING/error text or exactly one binary
record: zero byte, COBS(raw), zero byte, with no CRLF or prompt. There is no
automatic stream/burst. The binary payload is never passed to the511-byte text
line parser. The existing Console queue accepts the complete record or rejects
it; rejection is not a successful transfer.

The raw header is44 little-endian bytes: SLB1 magic, version1, kind1, uint16 flags
(bit0 EOF), uint64 host nonce, uint32 request ID, sequence, file ID, whole-file
CRC, size and offset, uint16 payload length and zero reserved uint16. Append
0..512 original bytes, then little-endian CRC32 ISO-HDLC covering header and
payload. Maximum raw560/wire565 bytes. Sequence equals floor(offset/512).
Length must equal min(512,size-offset), EOF must agree, and offset==size gives
an empty EOF block. A short underlying read fails STALE. Nonce is nonzero and
new per attempt; it is not a stable device/boot identity or authentication.

Validate the entire header, exact length, nonce, request ID, sequence, file ID,
token CRC/size, offset, EOF and frame CRC before one local write. A complete
delimited corrupt frame permits at most two POLL retries of the same immutable
completion, without new storage I/O or deadline extension. Bounded stale
request frames are quarantined. Other identity failures stop the operation.
An incomplete frame/timeout requires reconnect, new CAPS/META/nonce and restart
at offset zero; partial continuation remains forbidden. A BLOCK transaction
has a30-second host absolute ceiling plus existing per-response, idle and total
budgets. A local cancellation is not remote cleanup confirmation: CANCEL ACK
still says cleanup_complete=0, and fresh owner STATUS must show cleanup_pending=0.
Maintenance remains latched and never authorizes START or calibration.

The final full CRC, unchanged fresh post-copy META, local readback/SHA and atomic
local publication remain required. No recorded bytes, Descriptor or decoder
package are rewritten. No delete/format/upload command is added. Static block
scratch/mailbox storage is reused in CPU-only CCM. SerialTask copies to its
existing Console buffer and COBS-encodes there after releasing the lock, with
four bytes of input headroom. No extra raw+wire pair,512-byte task-local buffer,
heap or UART queue increase is introduced. Actual ARM map/stack and controlled target measurements
are required; host framing efficiency alone is not a throughput or stack proof.
