<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

# SilverStar Storage 与飞行日志格式 0.0

## FCCG Logger bootstrap增量

当前LoggerBus从`LOGGER_BOOTSTRAP`开始，只准入关键事件、STATS、配置/descriptor和
Calibration/Alignment/Initial State快照。普通周期流等header、decoder、启动配置及自检报告
排空并sync后进入`LOGGER_STREAMING_READY`再开放。成功open立即drain，尚未完成的自检不关闭session。
启动suppression独立统计，不占queue/sequence；真实overflow继续留下gap。新增内部拒绝、写入/同步
失败、session、放弃aggregate及延迟诊断，不改变SSLOG 0.0和decoder/project semantics 1.1。
正常启动要求overflow/gap为零，有限过载只允许drop而不允许CRC/长度/字节损坏；Host调度为模型，
实机证据与精确数值见根VALIDATION。当前权威流程见`docs/platform/details/STORAGE_AND_FLIGHT_LOG.md`。

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

当前TF/SDIO Storage和文件Log Sink由存储Device插件拥有，生成到`Devices/Storage/SdSdioFatFs`；Board只提供已验证的物理资源映射，CubeMX快照提供SDIO与FatFs App/Target glue，MCU/Platform插件提供受控FatFs core。因此换介质只替换存储Device及其硬件契约，不改变System、LoggerBus或Maintenance命令。

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

0.0.12删除`SYSTEM_LOG_MASK_*` 32-bit瓶颈。`SystemLogPolicy`维护：

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

每个stream最终配置通过`LOG_STREAM_DESCRIPTOR`记录，离线工具不需要推断C宏。

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

对外声明Record可用必须同时存在真实producer；仅有Record ID、payload、schema、metadata和codec不代表运行时可用。未来FCCG只能在选中producer及其依赖后把对应日志标记为available。

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

Device Task的Native producer通过`ProjectXxxInstance_CountGet()`遍历IMU、GNSS、BARO、MAG、ATTITUDE和POWER全部启用端点，再按instance facade读取样本和descriptor。各类别使用固定生成上界的静态sequence/timestamp数组，每个实例独立去重；一个实例失败或没有新sequence时只跳过该实例，不阻止同类其他实例。同一类别的instance 0/1继续写相同Record Type，通过`source_descriptor_id + instance_id`分流，不新增重复Record ID。该路径不改变ImuSampleBus、Calibration、INS或Estimator数据路径。正式F407当前仍只有instance 0，双实例行为由Host fixture验证，尚未提供按实例GUI过滤。

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

`EVENT.event_id=FLIGHT_LOG_EVENT_SENSOR_SOURCE_CHANGE`记录真实运行时source切换；没有发生old/new变化时不得伪造。编码为：

| 字段 | 位 | 语义 |
|---|---|---|
| `arg0` | 7:0 | `SystemDeviceClass` |
| `arg0` | 15:8 | old instance |
| `arg0` | 23:16 | new instance |
| `arg0` | 31:24 | reason：1 initial selection、2 failover、3 recovery、4 configuration、5 pre-start primary unavailable、6 GNSS liveness timeout、7 telemetry consecutive TX timeout、8 telemetry init failure |
| `arg1` | 15:0 | old descriptor ID |
| `arg1` | 31:16 | new descriptor ID |

old/new instance必须均对应现有descriptor，未使用位保持0。IMU在Calibration/Alignment前选中备用时先写reason 5；GNSS基础liveness切换使用reason 6；AIR连续10次真实本地TX timeout后真实切换使用reason 7，初始化跳过失败primary使用reason 8。无backup而继续重试不伪造source-change。该事件复用既有12-byte EVENT payload，不改变飞行日志格式0.0文件头、Record header、CRC、endianness或容器magic。

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

Host测试覆盖29类payload双向codec字节往返、Record长度、endian、完整Record解码错误、CRC、descriptor、stream policy、queue和finalization；同时验证双实例Native分流/独立去重/故障隔离、Decoder Profile三项hash与one-shot调用，以及STATS/TELEMETRY_DIAG生产路径。架构检查验证真实producer、Count/Instance facade、Catalog/C mirror、无registry/heap、Host fixture不进入Target图，并确认authoritative manifest不调用Python或生成器。ARM编译证明F407 Storage Device/Log Sink可链接；没有TF卡长时间写入、断电注入和文件恢复实测时，不得声称Storage硬件已经验证。


## CALIBRATION_RESULT 生效快照语义

`CALIBRATION_RESULT`（Record `0x17`、version 0、72-byte payload）表示本日志会话中
实际生效的IMU校正状态与参数快照，不是“执行过物理校准”的证明。mode为`NONE`时，
它明确表示未执行OneFace/SixFace采样流程、使用零bias和单位scale；此时state为READY、
ready/correction_valid为1。启用Logging时该Record保持required，并由Flight Task在每次
正常会话的启动/状态事件路径至少提交一次；禁用Logging时不构建Logger/SSLOG。

## FCCG storage integrity implementation

The SS0.5 diskio payload uses the FCCG-owned sector bounce/completion overlay. Storage accepts
arbitrary CPU byte buffers; MISSION_CONFIG remains 91 payload / 119 total bytes without padding.
Partial writes/sync uncertainty latch the Logger fault without replay/reopen. Queue overflow creates
explicit sequence gaps and stays separate from CRC corruption. Internal C diagnostics provide queue
high-water marks and storage/task latency; Maintenance and SSLOG wire fields are unchanged.
The current platform storage contract owns the full Host/Target and two-run/card procedure.
Real TF-card acceptance and historical SS0014 regression remain pending; exact software results live
only in the FCCG root VALIDATION.md. Custom CubeMX glue requires independent porting/validation.
