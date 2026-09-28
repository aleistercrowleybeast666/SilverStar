# SilverStar Storage 与飞行日志格式 0.0

## 当前导航记录扩展

当前 catalog 为原28项加7项独立记录。旧ID、field offset、CRC和payload布局不变；
新增`ESKF15_STATE`、`ESKF15_FULL_P_PART`、`ESKF15_INITIAL_STATE`、
`ESKF15_INITIAL_P_PART`、`ESKF15_MEASUREMENT`、`ESKF15_BODY_INPUT`及`NAV_QUALITY`，
分别使用0x21–0x27。新decoder要求FLP 0.0.5；原decoder不被改写。
状态变化事件0x2F走真实event codec。新算法不使用KF6身份承载15维内容。

ESKF初始状态/完整初始P、实际body输入和量测操作是所选算法的Required证据；
不选ESKF时这些记录不可用，GUI不会因其Required级别错误打开它们。
周期完整P默认关闭；打开后按一次snapshot cadence整体提交四片，每片保持既有槽预算。
初始P必需性与周期P可选性分开。不同queue可交错，消费者按epoch/snapshot/part关联，
不得依赖四片恰好邻接状态记录。缺片、CRC、丢记录继续明确报告。
具体时序、质量与faithful/approximate边界见[导航契约](../../NAVIGATION_CONTRACT.md)。

## Logger启动准入

上一轮修复SDIO/FatFs落盘字节完整性；本轮修复启动时普通周期流与开文件、descriptor和自检报告
写入争抢队列的短时突发。用户报告的新日志字节校验已正常，但启动仍有丢记录；它不是新的CRC修复。
SSLOG 0.0与SilverStar 0.0.12保持不变；当前`.ssdecoder`/Project Semantics为1.2。
旧记录身份、布局和CRC保持不变；导航契约新增独立ESKF15/质量记录，见下文。

LoggerBus持有唯一`LOGGER_BOOTSTRAP` → `LOGGER_STREAMING_READY`准入状态，静态、有界、无heap。
BOOT/其他EVENT、STATS、System/Device/Algorithm/Stream/Decoder descriptors、Mission config、
Calibration/Alignment结果和Initial State可在bootstrap入队。普通周期raw/native、corrected、
INS/Estimator输出、Power/Health/Telemetry诊断在此阶段不进入队列；不阻塞DeviceTask或FlightTask，
不改变它们的采样、校准、对准或飞行计算。策略原本关闭/抽取掉的记录继续按原规则处理。

Logger成功open后立即消费，只有open失败才进入retry延迟。文件头后排队Required decoder descriptor；
已经入队的BOOT/关键快照保留FIFO次序，队列满时继续消费并重试descriptor。待其排空后排队启动
System/Device/Algorithm/Stream配置批次，排空后写完整自检报告并sync。自检尚未完成时保持原session
并继续消费关键记录。sync期间新到达的关键记录也必须排空，随后在同一临界区检查两队列为空并
开放streaming；START仍保留原来的实际任务配置和Initial State记录。后续Calibration/Alignment结果
始终允许记录，不要求用户先完成采样程序才能开放普通日志。

`bootstrap_suppressed_count`表示按策略本应发出、但启动阶段未准入的普通记录。Push与原policy过滤
一样返回OK；它不是成功入队承诺，不占槽、也不产生sequence。`accepted_count`才是入队总量。
`state_reject_count`记录未初始化/结束后的拒绝；`capacity_reject_count`包含真实队列满拒绝及
SystemConfig批次预检空间不足（批次尚未提交）。实际`overflow_count`只来自队列Push丢弃，并继续
驱动原有writer sequence gap。不能把suppression当丢包，也不能把真实drop重新编号藏掉。

正常SS0.5启动、NONE或已选procedure、Alignment、START及数分钟记录要求logger/IMU overflow、
sequence gap、CRC/length/sync错误全为零。有限过载允许drop/gap，但所有存活记录仍须严格CRC、
长度、连续framing和EOF正确，Logger恢复消费且其他任务继续执行。Host端到端使用真实Logger/FatFs/
diskio/codec，生产节拍、其他任务工作计数和SD卡延迟是模型；真实任务调度与IMU总线overflow仍须台架验证。
容量、峰值、延迟、RAM/FLASH和实测日志只在根VALIDATION记录；默认队列容量及任务优先级未调整。

## 任意字节流与DMA所有权

Storage backend必须支持任意合法CPU buffer地址、文件offset和写入length，调用方不需要
4或32字节对齐。MISSION_CONFIG payload=91 bytes、record=119 bytes是合法协议尺寸，
禁止补齐payload、改变CRC或由FLP放宽CRC来掩盖writer错误。AIR M0、Maintenance/SSLOG 0.0、
平台0.0.12及旧SSLOG记录布局保持不变；`.ssdecoder`当前使用1.2算法参数契约。

SS0.5的`FATFS/Target/sd_diskio.c`使用固定512-byte main-SRAM buffer。每次只向BSP提交
一个sector，write先复制、read在完成后复制；匹配read/write completion并等待card-ready后
才能复用。FatFs继续负责partial/full/partial sector及read/modify/write，不在Logger重写文件系统。
扇区计数与字节数分离，检查空指针、零计数、计数上限和sector溢出。当前单次请求最多128 sectors，
与此FatFs最大cluster传输相容。等待有30秒整体上限，card-busy轮询让出CPU；CTRL_SYNC检查真实就绪。

缓冲区、完成队列及控制块全部静态，无heap。F407没有DCache。HAL completion只由实际SD handle
路由。错误类型completion、提交失败或timeout锁存diskio不可用；重初始化和迟到IRQ不能解锁，
必须复位后重新开始。这样即使DMA仍占用scratch，也不会被后续调用覆盖。这个保守策略不提供热插拔恢复。
单个文件系统的生产调用只由LoggerTask持有；health getter可以跨任务读取。禁止并行调用FatFs。

Logger遇到partial/uncertain write或sync失败时停止本次writer，不重放aggregate、不追加到疑似损坏文件，
best-effort结束sink但不标记finalized。该故障不会停止飞控任务。已经失败的文件可能有截断尾部，
审计应明确失败；修复不会伪造或修补已经丢失的数据。只有尚未开始写文件的open失败可继续重试。

### Queue独立诊断

普通/Estimator queue保持原容量，按归一化占用率优先消费且限制连续同队列最多3次成功pop，
另一队列非空时必须获得服务；producer把完整record复制进queue。Overflow只增加明确drop；
启动队列已满时不能因decoder descriptor入队失败而关闭文件，否则唯一consumer永远无法腾出空间。
Logger先保持session打开并消费，在dequeue后重试尚未入队的Required descriptor，成功后只写入一次。
每次serialize前，writer将新观察到的累计overflow增量加入sequence，因此双队列轮转不会造成push序号重排，
也不会假装丢弃不存在。Gap位置表示writer首次观察到drop的位置，不表示每个被丢样本的精确timestamp。
进程内的LoggerBus_Reset仅用于启动/测试，不能在活动文件中清零累计drop。STATS的原有overflow字段保持不变；
最后一条记录后发生的丢弃或STATS自身丢弃，不能仅靠文件推断完整损失量。

`LoggerBus_DiagnosticsGet`提供两队列当前量/HWM及accepted/dequeued/overflow累计计数；
`LoggerTask_DiagnosticsGet`提供最大迭代间隔、iteration/drain/serialized计数、io_fault、
streaming_ready时间、open尝试/失败/session次数、append/flush/serialize/close失败和discarded_bytes；
write_count/total_write_us/max_write_us可算平均sink write调用延迟，包含Storage/FatFs调用；
`SystemStorage_HealthGet`提供max_write_latency_us/max_sync_latency_us。这些是内部C诊断接口，
没有新增维护命令或wire字段。用两个带monotonic timestamp的快照差值测START前后production rate：
accepted增量/秒为入队率，(accepted+overflow)增量/秒为实际单记录排队尝试率；另报bootstrap suppression、
state拒绝与批次预检拒绝，不混算。discarded_bytes包含不确定写入后放弃重放的aggregate字节，
不能直接当作已证实丢失字节数。用调试器或专用台架调用读取，64-bit延迟更新受临界区保护。

队列增长要与存储延迟、任务调度和实际production rate一起判断。关键descriptor/生命周期批次不再逐条
f_sync：队列排空或首条critical的20ms deadline到达即flush，常规250ms sync保持不变；deadline不随
后续critical延长。已开始的有界存储操作可能使实际完成晚于deadline，必须记录真实最大延迟。
不提高Logger优先级或单纯增大queue来掩盖介质吞吐不足。

### 可重复Host与真实SS0.5验收

1. 在新生成的verified SS0.5+SD/TF+Logging工程运行`mingw32-make host-tests`，也可单独运行
   `python Tests/Host/storage_integrity/run_storage_integrity.py --project .`。
   Host使用实际FatFs、diskio、LoggerBus/Task、Storage/LogSink和C codec；SD卡和RTOS时间为模型，
   DMA延迟到completion才消费buffer。只在严格连续framing、全部CRC、文件长度和EOF正确时通过。
2. Target bench仅在无点火/部署负载的室内台架使用。将`Tests/Target/storage_integrity.c`临时加入
   专用台架工程，在scheduler启动、FatFs已link/mount且暂停常规Logger后，从唯一存储owner调用
   `StorageIntegrity_Run()`。不要与Logger并发。函数用CREATE_NEW创建BYTECHK.BIN/LOGCHK.BIN，
   不删除或格式化；已有同名文件时失败。确认返回Ok，保留读回文件。其静态RAM只属于台架构建。
3. 使用当前verified Board与SD/TF插件、已知良好卡，执行preflight → NONE calibration → alignment
   → START → 室内记录2–5分钟 → 正常停止，等待Logger完成grace/drain/flush/close后取出卡。
   保存START前后与停止后的三组诊断快照、任务HWM、卡型号和固件/decoder身份。
4. 独立运行`python Tools/sslog_audit.py SSxxxx.BIN --decoder Project.ssdecoder`。
   核查文件头CRC、record CRC/length、sequence、尾字节、boundary signature和STATS overflow。
   故意overflow用`--allow-queue-drops`，仅当CRC仍全正确且gap总量与有效STATS累计drop完全对应才可通过。
   工具在首个坏frame停下，不resync获得通过；boundary extra/missing-byte signature只是局部CRC假设，
   不修改输入文件，也不声称恢复数据。`--scan-candidates`可另报坏文件的CRC/length candidate、
   恢复候选中的gap及STATS，结果与严格判定分离，不能据此证明queue损失或获得通过。
   传`--catalog`只证明codec framing，不证明项目decoder精确匹配。
5. 至少两次运行或两张卡；每次保留BIN、匹配`.ssdecoder`、审计JSON及诊断快照。
   FLP能打开、GSHC遥测正常都不能替代TF文件逐字节/CRC验收。

未提供本地SS0014.BIN和对应decoder时，只能保留prompt提供的历史缺陷事实，不能写成已复测。
小型synthetic corruption定义位于`tests/fixtures/sslog_corruption_cases.json`，回归从实际C writer产生的
字节流构造512边界重复/缺字节、CRC翻转、oversized length、sequence gap与尾字节并验证严格拒绝。
实际执行结果、RAM/FLASH变化与硬件状态仅记录在根VALIDATION。
> **0.0.12增量**：固件build tag为`SILV0012`；`.ssdecoder` package/project-semantics现为1.2。Physical Device、source descriptor、instance identity用于区分多IMU/GNSS native record。`CALIBRATION_RESULT`在NONE/OneFace/SixFace均是Required有效快照。

> 文档版本：0.0.12
> 正式名称：飞行日志格式0.0
> wire magic：`SSLOG0`；profile id：0
> 适用范围：SilverStar 0.0.12

## 1. 职责分层

```text
APP/System producers
    -> FlightLogRecord
LoggerBus
    -> bounded static normal/estimator queues
LoggerTask
    -> Protocol/SSLOG serialize + aggregate + flush
SystemLogSink Interface
    -> SilverStar 0.5 Log Sink Service
SystemStorage Interface
    -> SilverStar 0.5 Storage Service / FatFs / SDIO
```

`Protocol/SSLOG`不知道任务和Storage；LoggerBus不知道wire encoding、FatFs和文件名；LoggerTask不知道介质物理类型；System Console只公开`LOG`抽象，不接受`TF`别名。对外协议名称是“飞行日志格式0.0”，`SSLOG0`只作为现有二进制magic和技术实现目录名保留。

当前TF/SDIO Storage和文件Log Sink由单实例`Devices/Storage/SdSdioFatFs`拥有。Board仅提供已验证的SDIO/时间映射；CubeMX快照提供SDIO及FatFs App/Target glue，MCU/Platform提供受控FatFs core和HAL provider。禁止同时编译旧Board路径和Device路径实现。换介质应替换Device与资源声明，保持System/LoggerBus/维护接口。

## 2. 权威Codec与Record Catalog

固件运行时的权威声明和实现是：

```text
Protocol/SSLOG/Inc/sslog_records.h
Protocol/SSLOG/Src/sslog_records.c
```

它们以普通受控C源码定义Record ID、Record version、payload size、静态metadata，以及所有Record逐字段显式little-endian serializer/deserializer。`SslogRecords_PayloadSerialize()`与`SslogRecords_PayloadDeserialize()`对每个多字节整数和float bit pattern显式读写；`FlightLogRecord`及其payload union只属于进程内类型，禁止用`memcpy`、强制指针转换或`sizeof(C struct)`直接生成/读取wire payload。LoggerBus内部复制有界记录不构成wire编码，真正出入SSLOG字节流必须经过上述codec。

FCCG/离线解析器的声明式Record Catalog及镜像位于：

- `Protocol/SSLOG/schema/sslog_schema.json`；
- `Protocol/SSLOG/schema/sslog_record_catalog.schema.json`；
- `Protocol/SSLOG/schema/sslog_parser_metadata.json`。

`sslog_schema.json`是每工程`.ssdecoder`所需Record Catalog真源，声明Record ID/version/payload、字段顺序、有限基础类型、固定数组、padding、little-endian、单位/quantity/scale/offset、enum/bitfield、timestamp/validity、实例路由字段与producer mode；JSON Schema禁止嵌入可执行脚本。`sslog_parser_metadata.json`是完整镜像。Host Test调用`Tools/validate_sslog_record_catalog.py`，核对每条Record字段与padding总和等于payload、两份JSON一致、C ID/size/codec/config存在及Generated profile hash匹配。

这些JSON不进入固件构建、不在运行时解析，也不驱动authoritative Make；firmware `all`不得启动Python。项目默认stream policy由`Generated/Src/project_log_config.c`拥有。Catalog和C codec同时受控并由离线validator互相约束：Catalog存在不能替代显式C codec，C codec变化也不得绕过Catalog更新。

## 3. 文件头

文件头固定64 bytes，全部little-endian：

| 偏移 | 长度 | 字段 |
|---:|---:|---|
| 0 | 8 | `SSLOG0` + 两个`0x00` |
| 8 | 2 | log profile id，当前0 |
| 10 | 2 | file header size=64 |
| 12 | 2 | record header size=24 |
| 14 | 2 | nominal IMU rate |
| 16 | 2 | nominal INS rate |
| 18 | 1 | coordinate frame=ENU |
| 19..21 | 3 | position axis order E/N/U |
| 22 | 1 | quaternion order WXYZ |
| 23 | 1 | Hamilton body-to-navigation语义 |
| 24 | 4 | local gravity，float32 |
| 28 | 8 | AIR兼容标识`AIR-NCRC` |
| 36 | 8 | firmware build tag，0.0.12为`SILV0012` |
| 44 | 2 | Record CRC size=4 |
| 46 | 2 | mechanization subsample count |
| 48..51 | 4 | firmware major/minor/patch/build |
| 52 | 2 | max serialized Record size |
| 54..59 | 6 | reserved，写0 |
| 60 | 4 | file header CRC32 |

CRC为CRC-32/ISO-HDLC（反射多项式`0xEDB88320`，初值/终值异或`0xFFFFFFFF`），与常用`zlib.crc32()`结果一致。

## 4. Record格式与version

```text
u32 sync                 0x31474C46，文件字节"FLG1"
u8  record_version       来自静态Record metadata
u8  record_type
u16 payload_length
u32 record_sequence
u64 timestamp_us
u32 valid_flags
u8  payload[payload_length]
u32 crc32                覆盖header + payload
```

公共header固定24 bytes，尾CRC固定4 bytes。解析器对未知`record_type`或未知`record_version`按`payload_length`和CRC安全跳过；CRC失败时扫描下一sync；断电造成的末尾半条Record忽略。

`record_version`只属于单个Record schema，不是飞行日志格式版本。当前所有Record为version 0。`MISSION_CONFIG` payload不再保存第二个冗余version字段；唯一权威版本就是公共header/静态metadata。

新增独立语义优先分配新Record ID；同一ID发生不兼容payload变化才递增该Record version。只有文件头、公共Record framing、CRC或同步恢复规则整体不兼容时才分配新的飞行日志格式版本和wire magic。

## 5. Record目录

| ID | 名称 | payload bytes | 默认策略 |
|---:|---|---:|---|
| 0x01 | SAMPLE | 196 | disabled/decimation |
| 0x02 | EVENT | 12 | event |
| 0x03 | STATS | 16 | periodic，1 s |
| 0x04 | ESTIMATOR | 136 | decimation=4 |
| 0x05 | SYSTEM_CONFIG | 132 | one-shot |
| 0x06 | RAW_SENSOR | 132 | disabled/decimation |
| 0x07 | PURE_INS | 68 | decimation=1 |
| 0x08 | KF6_DIAGNOSTIC | 104 | decimation=4 |
| 0x09 | KF6_FULL_P | 84 | decimation=4 |
| 0x0A | POWER | 48 | periodic |
| 0x0B | HEALTH | 40 | periodic |
| 0x0C | TELEMETRY_DIAG | 48 | periodic，200 ms |
| 0x0D | INITIAL_STATE | 144 | one-shot |
| 0x0E | IMU_NATIVE | 80 | disabled/decimation |
| 0x0F | GNSS_NATIVE | 84 | decimation=1 |
| 0x10 | BARO_NATIVE | 48 | decimation=1 |
| 0x11 | MAG_NATIVE | 60 | decimation=1；能力关闭时无producer |
| 0x12 | HW_QUAT_NATIVE | 48 | decimation=1 |
| 0x13 | INERTIAL_INCREMENT | 52 | decimation=1 |
| 0x14 | GNSS_MEASUREMENT | 72 | every |
| 0x15 | BARO_MEASUREMENT | 32 | every |
| 0x16 | IMU_CORRECTED | 60 | decimation=1 |
| 0x17 | CALIBRATION_RESULT | 72 | event |
| 0x18 | ALIGNMENT_RESULT | 96 | event |
| 0x19 | MISSION_CONFIG | 91 | one-shot |
| 0x1A | DEVICE_DESCRIPTOR | 26 | one-shot，每实例一条 |
| 0x1B | ALGORITHM_DESCRIPTOR | 16 | one-shot，每实例一条 |
| 0x1C | LOG_STREAM_DESCRIPTOR | 12 | one-shot，每stream一条 |
| 0x1D | DECODER_PROFILE_DESCRIPTOR | 64 | one-shot，每Logger session一条 |

精确Record ID和wire codec以`sslog_records.*`为固件权威；声明式解析字段以Record Catalog为FCCG/解析器权威，二者必须通过离线validator一致。默认stream参数以`project_log_config.c`为当前项目权威。最大payload为256 bytes，当前最大196 bytes。

## 6. Stream policy

0.0.9删除`SYSTEM_LOG_MASK_*` 32-bit瓶颈。`SystemLogPolicy`维护：

```c
typedef struct
{
    FlightLogRecordType record_type;
    uint8_t enabled;
    uint16_t decimation;
    uint32_t period_us;
    SslogStreamPolicy policy;
} SystemLogStreamConfig;
```

静态runtime表大小为`SSLOG_RECORD_COUNT`，不使用heap。默认值来自`ProjectLogConfig_StreamByIndexGet()`；START时冻结，rollback才允许解冻。策略包括EVERY、DECIMATION、PERIODIC、EVENT和ONE_SHOT。算法启用与算法日志启用独立；没有运行的数据源自然不会产生Record。

每个stream最终配置通过LOG_STREAM_DESCRIPTOR记录，离线工具不需要推断C宏。

FCCG的日志metadata对全部28个Record显式声明独立的level和purpose。
required保障身份、配置及必要任务事件，flight涵盖正常飞行与FLP离线复算，
test用于开发/数值深度诊断。当前仅KF6_DIAGNOSTIC与KF6_FULL_P是Test，
均为Optional且默认关闭。高频的INERTIAL_INCREMENT、ESTIMATOR_STEP
和量测记录仍属Flight，因为完整重放需要这些证据。GUI的Enable All、Flight Logs Only、
Required Only只批量修改现有stream启用位；Required Only不保证faithful replay。
组件或协议变动时保持仍可用stream的用户选择，对失去可用性的stream关闭，
重新可用时按metadata默认启用位恢复，不自动执行Enable All。

### 6.1 真实诊断生产路径

`STATS`与`TELEMETRY_DIAG`均已具有真实producer，不再是“只有schema和codec、没有运行时来源”的Record。两者仅在既有日志会话的`FLIGHT`和`RECOVERY`阶段按单调时间工作；禁用或周期未到时不读取并不推送。

```text
Device/INS runtime statistics
    -> DiagnosticLog_StatsProcess (Device Task周期日志路径)
    -> LoggerBus_StatsPush
    -> Flight Log Format 0.0

Telemetry Transport Health
    -> DiagnosticLog_TelemetryProcess (Telemetry Task周期路径)
    -> LoggerBus_TelemetryDiagnosticPush
    -> Flight Log Format 0.0
```

`STATS`默认启用、周期为`1000000 us`。字段来源固定为：

- `imu_queue_overflow_count`：`ImuSampleBus_StatsGet().overflow_count`；
- `logger_queue_overflow_count`：LoggerBus普通队列与Estimator队列累计overflow之和；
- `ins_update_count`：当前Canonical `InsOutputSnapshot.update_seq`；
- `health_flags`：当前Canonical `InsOutputSnapshot.health_flags`。

没有可用INS snapshot时，后两个字段明确写0；不修改INS或Estimator数据路径。

`TELEMETRY_DIAG`默认启用、周期为`200000 us`，逐字段复制通用`SystemTelemetryHealth`的发送/接收时间戳、包计数、错误计数、完整性错误、RSSI、SNR和online。它只表示当前Transport/Link健康快照，不包含Telemetry Service内部的ACK队列、状态队列或调度统计，不增加无线发送内容，也不改变AIR遥测协议M0。`SystemTelemetry_HealthGet()`失败时不生成全零伪记录且不推进周期基线，下一周期继续尝试。APP producer不得引用SX1281私有统计类型。

对外声明Record可用必须同时存在真实producer；仅有Record ID、payload、schema、metadata和codec不代表运行时可用。FCCG只在满足条件时在选中producer及其依赖后把对应日志标记为available。

## 7. Descriptor设计

旧`SYSTEM_CONFIG`中的固定device/provider ID数组、algorithm数组和log decimation数组已删除。`SYSTEM_CONFIG`只保存固件/Profile、配置digest、速率、队列容量、descriptor计数和最终Estimator参数。

- `DEVICE_DESCRIPTOR`：descriptor ID、physical device ID、class、instance、driver ID、flags、capability、rate、driver/model name hash；
- `ALGORITHM_DESCRIPTOR`：descriptor ID、class、instance、algorithm ID、flags、config digest、name hash；
- `LOG_STREAM_DESCRIPTOR`：record type/version、enabled、policy、decimation、period。
- `DECODER_PROFILE_DESCRIPTOR`：package/container版本及Record Catalog、project semantics、generation profile三个128-bit截断hash。

Target内部descriptor表仍有明确编译期容量上界，这是无heap内存证明；扩展实例通过多写Record完成，不受某个payload固定数组槽数限制。`physical_device_id`表示实际硬件模块归属，`instance_id`表示同一`device_class`中的逻辑能力实例，二者不得互换。当前JY901B的`IMU 0`、`BARO 0`、`ATTITUDE 0`以及启用时的`MAG 0`均链接到`physical_device_id=1`，但保留各自独立descriptor ID。

## 8. Capability instance原始记录

`POWER`、`IMU_NATIVE`、`GNSS_NATIVE`、`BARO_NATIVE`、`MAG_NATIVE`和`HW_QUAT_NATIVE`payload均以以下4 bytes开头：

| offset | 类型 | 字段 | 语义 |
|---:|---|---|---|
| 0 | u16 LE | `source_descriptor_id` | 链接对应`DEVICE_DESCRIPTOR.descriptor_id` |
| 2 | u8 | `instance_id` | Record所表达能力类别内的实例号 |
| 3 | u8 | `reserved` | 当前写0，解析器不得赋予语义 |

Record Type表达能力类别，所以`IMU_NATIVE instance=0`是`IMU 0`，`BARO_NATIVE instance=0`是`BARO 0`，`HW_QUAT_NATIVE instance=0`是`ATTITUDE 0`；不能把它们笼统解释为“JY901B instance 0”。所有字段继续由`sslog_records.c`显式逐字段little-endian编码/解码，禁止直接序列化C struct。schema与parser metadata同步携带这些字段，但只作为离线参考。

Device Task的Native producer通过`ProjectXxxInstance_CountGet()`遍历IMU、GNSS、BARO、MAG、ATTITUDE和POWER全部启用端点，再按instance facade读取样本和descriptor。各类别使用固定生成上界的静态sequence/timestamp数组，每个实例独立去重；一个实例失败或没有新sequence时只跳过该实例，不阻止同类其他实例。同一类别的instance 0/1继续写相同Record Type，通过`source_descriptor_id + instance_id`分流，不新增重复Record ID。该路径不改变ImuSampleBus、Calibration、INS或Estimator数据路径。生成工程可包含多个真实实例，按配置生成descriptor与静态facade；Host fixture验证隔离行为，不作为生产源编入。

`RAW_SENSOR`是早期聚合诊断Record，不是按能力实例寻址的权威Native记录。`INERTIAL_INCREMENT`、`IMU_CORRECTED`、`PURE_INS`、`ESTIMATOR`、`KF6_DIAGNOSTIC`、`GNSS_MEASUREMENT`、`BARO_MEASUREMENT`和`ALIGNMENT_RESULT`继续表示当前Canonical stream、选定来源或融合状态，只保存一份；多个Raw instance不等于多套INS/KF。

### 8.1 Decoder Profile Descriptor与`.ssdecoder`

Logger session写入File Header后one-shot排队`DECODER_PROFILE_DESCRIPTOR(0x1D)`。其64-byte payload依次包含四个u16版本、三个完整16-byte hash前缀和8-byte写零reserved；`sslog_records.c`显式按little-endian逐字段编解码，不直接序列化C struct。旧解析器可按公共Header的`payload_length`和CRC跳过未知0x1D Record，飞行日志格式0.0容器不升版。

FCCG把Record Catalog与`Generated/project_semantics.json`放入同一纯数据`.ssdecoder`，按以下确定性规则产生Generated常量：

```text
canonical_json = UTF-8 + lexicographic keys + no insignificant whitespace
                 + shortest stable JSON numbers + LF + one terminal LF
record_catalog_hash = SHA-256(canonical Record Catalog JSON)
project_semantics_hash = SHA-256(canonical project semantics JSON)
generation_input = UTF-8(package_schema_id) + LF
                 + UTF-8(container_plugin_id) + LF
                 + full_32_byte_record_catalog_hash
                 + full_32_byte_project_semantics_hash
generation_profile_hash = SHA-256(generation_input)
```

固件只记录三项SHA-256的前16字节，不实现SHA-256，也不保存`.ssdecoder` ZIP自身hash，以避免循环依赖。

## 9. Sensor Source Change事件

`EVENT.event_id=FLIGHT_LOG_EVENT_SENSOR_SOURCE_CHANGE`记录真实来源切换；主源未变化、旧源恢复或最后来源的重复重试不得伪造切换事件。编码为：

| 字段 | 位 | 语义 |
|---|---|---|
| `arg0` | 7:0 | `SystemDeviceClass` |
| `arg0` | 15:8 | old instance |
| `arg0` | 23:16 | new instance |
| `arg0` | 31:24 | reason：1 initial selection、2 failover、3 recovery、4 configuration；当前selector使用5 prestart primary unavailable、6 GNSS liveness timeout、7 consecutive TX timeout、8 telemetry init failure |
| `arg1` | 15:0 | old descriptor ID |
| `arg1` | 31:16 | new descriptor ID |

当前selector以真实old/new实例查找descriptor；不存在的descriptor不得伪造为有效来源。该事件复用既有12-byte EVENT payload，不改变飞行日志格式0.0文件头、Record header、CRC、endianness或容器magic。

## 10. 离线重放

默认重放层级：

1. `IMU_CORRECTED`：实际进入INS的Calibration后机体系加速度/角速度；
2. 带`source_descriptor_id + instance_id`的IMU/GNSS/Baro/Mag/Hardware Quaternion/Power native公共样本；
3. `INERTIAL_INCREMENT`和Estimator实际量测；
4. Pure INS、KF6 state/diagnostic/P；
5. System/Mission配置、descriptor、Calibration、Alignment和Initial State。

正式默认不保证保存每个UART/UBX原始字节，也不把`IMU_NATIVE`当成离线重新标定的唯一输入。需要底层协议诊断时应定义新的可选RAW_DEVICE_FRAME类Record，不复用导航Record含义。

每条Record携带真实单调时间戳；解析器不得用标称频率重建时间。在线与Host重放应复用同一C Algorithm实现，Python只负责解析、调度、参数扫描和绘图。

## 11. 写盘、flush与收尾

LoggerTask使用静态Record buffer和aggregation buffer。完整Record才进入聚合；空间不足、关键Record或sync周期到达时批量写入。文件头、System/Mission config、descriptor、Initial State、关键Lifecycle/Calibration/Alignment事件应尽力及时flush。

Landing确认后先把LANDING EVENT可靠加入LoggerBus，再以landing timestamp建立post-landing grace截止时间。截止前继续记录正常尾段；截止后Bus拒绝新Push但不计作overflow，LoggerTask排空normal/estimator queue、写完aggregation、flush并结束session。写入/sync不确定性锁存writer故障且不重放，只有全部成功才锁存finalized。本次上电不再自动开启第二个session。

Storage/Log失败不得阻止、拒绝或回滚START、Deploy或Landing；它只进入Health、事件和丢弃计数。

## 12. 新Record流程

1. 在`sslog_records.h`分配未使用ID、version、payload size和metadata，在`project_log_config.c`声明当前项目默认policy；
2. 在`sslog_protocol.h`定义字段名、数组长度和类型相匹配的内存payload类型；
3. 在`sslog_records.c`增加逐字段显式little-endian serializer/deserializer；不得退回C struct直写wire；
4. 增加所有Record的encode-decode-encode字节一致性、长度、little-endian、CRC、buffer-small、bad version/type/size/CRC和queue overflow Host测试；
5. 若由新producer产生，增加LoggerBus窄Push接口、实际生产调用点与明确overflow行为；对外available声明不得只依据schema；
6. 同步更新本文、Record Catalog、JSON Schema、parser metadata与Generated profile常量；
7. 运行Host离线Catalog validator、architecture-check和Debug/Release目标构建，并确认firmware构建日志没有Python/生成器调用。

禁止新增runtime serializer函数指针表、动态Record注册或JSON runtime parser。

## 13. 验收边界

Host测试覆盖29类payload双向codec字节往返、Record长度、endian、完整Record解码错误、CRC、descriptor、stream policy、queue和finalization；同时验证双实例Native分流/独立去重/故障隔离、Decoder Profile三项hash与one-shot调用，以及STATS/TELEMETRY_DIAG生产路径。架构检查验证真实producer、Count/Instance facade、Catalog/C mirror、无registry/heap、Host fixture不进入Target图，并确认authoritative manifest不调用Python或生成器。ARM编译证明F407 Storage/Log Device实现可链接；没有TF卡长时间写入、断电注入和文件恢复实测时，不得声称Storage硬件已经验证。

## Decoder algorithm parameters (package 1.2)

`firmware_algorithm_parameters` remains per onboard algorithm and contains each final resolved actual value. FCCG `shared_key` metadata is intentionally absent: FLP need not understand it. Package schema and project semantics remain 1.2, Record Catalog and wire layout are unchanged, and `required_flp_minimum_version` is 0.0.4.
