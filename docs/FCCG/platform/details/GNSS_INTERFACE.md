# SilverStar GNSS 接口
> **0.0.12增量**：所有GNSS实例持续解析和记录。`no fix`不等于设备故障；active GNSS只在基础liveness/消息新鲜度失效时向后续备用单向切换，不自动failback。

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

> `0.0.12` 表示协议、接口和实现均处于首次发布前阶段。文档中的结构可以在评审后调整，不提供跨版本兼容承诺。

## 1. 样本

```c
#define SYSTEM_GNSS_VEL_VALID_E (1U << 0)
#define SYSTEM_GNSS_VEL_VALID_N (1U << 1)
#define SYSTEM_GNSS_VEL_VALID_U (1U << 2)

#define SYSTEM_GNSS_FIELD_FIX_TYPE            (1UL << 0)
#define SYSTEM_GNSS_FIELD_FIX_OK              (1UL << 1)
#define SYSTEM_GNSS_FIELD_SATELLITE_COUNT     (1UL << 2)
#define SYSTEM_GNSS_FIELD_POSITION            (1UL << 3)
#define SYSTEM_GNSS_FIELD_HEIGHT              (1UL << 4)
#define SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY (1UL << 5)
#define SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY   (1UL << 6)
#define SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL (1UL << 7)
#define SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL   (1UL << 8)
#define SYSTEM_GNSS_FIELD_SPEED_ACCURACY      (1UL << 9)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint32_t position_reject_mask;
    uint32_t velocity_reject_mask;

    int32_t latitude_e7;
    int32_t longitude_e7;
    int32_t ellipsoid_height_mm;
    int32_t msl_height_mm;

    float velocity_enu_mps[3];
    float velocity_variance_m2ps2[3];

    float horizontal_accuracy_m;
    float vertical_accuracy_m;
    float speed_accuracy_mps;

    uint8_t velocity_valid_mask;
    uint8_t fix_type;
    uint8_t fix_ok;
    uint8_t satellite_count;
    uint8_t position_usable;
    uint8_t course_usable;
    uint8_t online;
    uint8_t quality_degraded;
} SystemGnssSample;
```

`supported_fields`表示当前Device能够提供的通用字段，`valid_fields`表示当前样本中真实有效的字段。字段不受支持、受支持但当前无效、数值未通过质量门限和样本陈旧必须分别表达；不支持的值不得用数值0冒充。

## 2. 速度有效维数

- UBX-NAV-PVT可提供N/E/D三轴速度，转换为ENU后设置E|N|U；
- 仅有RMC/VTG的NMEA后端通常只能由地速和航迹角得到E/N，设置E|N；
- 缺失U不得填零并声明有效；
- KF根据有效掩码选择2D或3D速度更新。

转换：

```c
v_enu[0] = velE_mmps * 0.001f;
v_enu[1] = velN_mmps * 0.001f;
v_enu[2] = -velD_mmps * 0.001f;
```

## 3. 能力位

```c
#define SYSTEM_GNSS_CAP_POSITION          (1UL << 0)
#define SYSTEM_GNSS_CAP_VELOCITY_2D       (1UL << 1)
#define SYSTEM_GNSS_CAP_VELOCITY_3D       (1UL << 2)
#define SYSTEM_GNSS_CAP_ELLIPSOID_HEIGHT  (1UL << 3)
#define SYSTEM_GNSS_CAP_MSL_HEIGHT        (1UL << 4)
#define SYSTEM_GNSS_CAP_TIME              (1UL << 5)
#define SYSTEM_GNSS_CAP_ACCURACY_FIELDS   (1UL << 6)
#define SYSTEM_GNSS_CAP_CONFIG_NAV_RATE   (1UL << 7)
#define SYSTEM_GNSS_CAP_DYNAMIC_MODEL     (1UL << 8)
#define SYSTEM_GNSS_CAP_SATELLITE_DIAGNOSTICS (1UL << 9)
#define SYSTEM_GNSS_CAP_RF_DIAGNOSTICS        (1UL << 10)
```

## 4. 通用配置

GNSS没有IMU“带宽”概念。通用配置只包含有意义的导航参数：

```c
#define SYSTEM_GNSS_CONSTELLATION_GPS      (1UL << 0)
#define SYSTEM_GNSS_CONSTELLATION_BDS      (1UL << 1)
#define SYSTEM_GNSS_CONSTELLATION_GALILEO  (1UL << 2)
#define SYSTEM_GNSS_CONSTELLATION_GLONASS  (1UL << 3)

typedef enum
{
    SYSTEM_GNSS_DYNAMIC_MODEL_PORTABLE = 0,
    SYSTEM_GNSS_DYNAMIC_MODEL_STATIONARY,
    SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_1G,
    SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_2G,
    SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G
} SystemGnssDynamicModel;

typedef enum
{
    SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX = 0,
    SYSTEM_GNSS_OUTPUT_PROTOCOL_NMEA,
    SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX_AND_NMEA
} SystemGnssOutputProtocol;

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    uint16_t navigation_rate_hz;
    uint32_t constellation_mask;
    SystemGnssDynamicModel dynamic_model;
    SystemGnssOutputProtocol output_protocol;
    uint32_t enabled_message_mask;
} SystemGnssConfig;

typedef enum
{
    SYSTEM_GNSS_CONFIG_READ_RESPONSE_OK = 0,
    SYSTEM_GNSS_CONFIG_READ_NAK,
    SYSTEM_GNSS_CONFIG_READ_TX_ERROR,
    SYSTEM_GNSS_CONFIG_READ_CHECKSUM_ERROR,
    SYSTEM_GNSS_CONFIG_READ_MALFORMED_RESPONSE,
    SYSTEM_GNSS_CONFIG_READ_TIMEOUT,
    SYSTEM_GNSS_CONFIG_READ_NOT_READY
} SystemGnssConfigReadResult;

typedef enum
{
    SYSTEM_GNSS_TRANSACTION_DETAIL_NONE = 0,
    SYSTEM_GNSS_TRANSACTION_DETAIL_RESPONSE_OK,
    SYSTEM_GNSS_TRANSACTION_DETAIL_NAK,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BUSY,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_VERSION,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_LAYER,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_POSITION,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_LENGTH,
    SYSTEM_GNSS_TRANSACTION_DETAIL_KEY_MISMATCH,
    SYSTEM_GNSS_TRANSACTION_DETAIL_VALUE_LENGTH_MISMATCH,
    SYSTEM_GNSS_TRANSACTION_DETAIL_COUNT_OVERFLOW,
    SYSTEM_GNSS_TRANSACTION_DETAIL_CHECKSUM_ERROR,
    SYSTEM_GNSS_TRANSACTION_DETAIL_TX_ERROR,
    SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT,
    SYSTEM_GNSS_TRANSACTION_DETAIL_NOT_READY
} SystemGnssTransactionDetail;

typedef enum
{
    SYSTEM_GNSS_CONFIG_READ_GROUP_NONE = 0,
    SYSTEM_GNSS_CONFIG_READ_GROUP_UART,
    SYSTEM_GNSS_CONFIG_READ_GROUP_PROTOCOL,
    SYSTEM_GNSS_CONFIG_READ_GROUP_NAV_PVT,
    SYSTEM_GNSS_CONFIG_READ_GROUP_RATE,
    SYSTEM_GNSS_CONFIG_READ_GROUP_DYNAMIC_MODEL,
    SYSTEM_GNSS_CONFIG_READ_GROUP_SIGNALS
} SystemGnssConfigReadGroup;

typedef struct
{
    uint32_t valid_mask;
    uint32_t baudrate;
    uint32_t constellation_mask;
    uint32_t elapsed_ms;
    uint16_t navigation_rate_hz;
    SystemGnssDynamicModel dynamic_model;
    SystemGnssOutputProtocol output_protocol;
    uint8_t protocol_in;
    uint8_t nav_pvt_rate;
    uint8_t nav_pvt_known;
    SystemGnssConfigReadResult read_result;
    SystemGnssConfigReadGroup failed_group;
    uint32_t failed_key;
    uint16_t response_length;
    uint8_t nak_class;
    uint8_t nak_id;
    uint32_t transaction_id;
    uint32_t unsupported_mask;
    SystemGnssTransactionDetail detailed_result;
    uint8_t expected_class;
    uint8_t expected_id;
    uint8_t received_class;
    uint8_t received_id;
    uint8_t response_version;
} SystemGnssHardwareConfig;

typedef enum
{
    SYSTEM_GNSS_CONFIG_STAGE_NONE = 0,
    SYSTEM_GNSS_CONFIG_STAGE_UART,
    SYSTEM_GNSS_CONFIG_STAGE_UART_SETTLE,
    SYSTEM_GNSS_CONFIG_STAGE_PROTOCOL,
    SYSTEM_GNSS_CONFIG_STAGE_NAV_PVT,
    SYSTEM_GNSS_CONFIG_STAGE_RATE,
    SYSTEM_GNSS_CONFIG_STAGE_DYNAMIC_MODEL,
    SYSTEM_GNSS_CONFIG_STAGE_SIGNALS,
    SYSTEM_GNSS_CONFIG_STAGE_PVT_RECOVERY,
    SYSTEM_GNSS_CONFIG_STAGE_VERIFY
} SystemGnssConfigStage;

typedef struct
{
    SystemDeviceResult uart_baudrate_result;
    SystemDeviceResult uart_settle_result;
    SystemDeviceResult protocol_result;
    SystemDeviceResult nav_pvt_result;
    SystemDeviceResult rate_result;
    SystemDeviceResult dynamic_model_result;
    SystemDeviceResult signals_result;
    SystemDeviceResult pvt_recovery_result;
    SystemDeviceResult verify_result;
    SystemGnssConfigStage failed_stage;
    uint32_t baseline_pvt_sequence;
    uint32_t recovered_pvt_sequence;
    uint64_t signal_complete_timestamp_us;
    uint8_t ack_result;
    uint8_t write_layers;
    SystemGnssConfigReadResult verify_read_result;
    SystemGnssConfigReadGroup verify_failed_group;
    uint32_t verify_failed_key;
    uint32_t verify_valid_mask;
    uint16_t verify_response_length;
    uint8_t verify_nak_class;
    uint8_t verify_nak_id;
    SystemGnssTransactionDetail verify_detailed_result;
    uint8_t verify_expected_class;
    uint8_t verify_expected_id;
    uint8_t verify_received_class;
    uint8_t verify_received_id;
    uint8_t verify_response_version;
} SystemGnssConfigTransactionReport;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint8_t satellite_count;
    uint8_t used_count;
    uint8_t average_cno_dbhz;
    uint8_t maximum_cno_dbhz;
    uint8_t average_quality;
    uint8_t fresh;
    SystemGnssConfigReadResult read_result;
    SystemGnssTransactionDetail detailed_result;
    uint32_t transaction_id;
    uint16_t response_length;
} SystemGnssSatelliteDiagnostics;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint16_t noise_per_ms;
    uint16_t agc_count;
    uint8_t rf_block_count;
    uint8_t antenna_status;
    uint8_t antenna_power;
    uint8_t jamming_state;
    uint8_t cw_suppression;
    uint8_t jamming_indicator;
    uint8_t fresh;
    SystemGnssConfigReadResult read_result;
    SystemGnssTransactionDetail detailed_result;
    uint32_t transaction_id;
    uint16_t response_length;
} SystemGnssRfDiagnostics;
```

UART波特率是NEO-M9N Device私有链路配置，不是所有GNSS设备的共同字段。

GNSS绝对时间辅助类型：

```c
typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint32_t time_of_week_ms;
    int32_t nanosecond;
    uint32_t time_accuracy_ns;
    uint16_t year;
    uint8_t month;
    uint8_t day;
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
    uint8_t date_valid;
    uint8_t time_valid;
    uint8_t fully_resolved;
} SystemGnssTime;
```

不支持绝对时间的Adapter在`SystemGnss_TimeGet()`中返回`SYSTEM_DEVICE_UNSUPPORTED`。尚未取得第一份有效时间时返回`SYSTEM_DEVICE_NOT_READY`。

## 5. 直接接口

```c
const char *SystemGnss_NameGet(void);
SystemDeviceResult SystemGnss_Init(void);
SystemDeviceResult SystemGnss_Start(void);
SystemDeviceResult SystemGnss_Stop(void);
SystemDeviceResult SystemGnss_RuntimeOwnerActivate(void);
void SystemGnss_Process(void);
SystemDeviceResult SystemGnss_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemGnss_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemGnss_IoDiagnosticsGet(SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult SystemGnss_IoDetailGet(SystemGnssIoDetail *detail);
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample);
SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time);
SystemDeviceResult SystemGnss_SelfTestRun(SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemGnss_ConfigApply(const SystemGnssConfig *config,
                                          SystemDeviceConfigReport *report);
SystemDeviceResult SystemGnss_ConfigVerify(const SystemGnssConfig *config,
                                           SystemDeviceConfigReport *report);
SystemDeviceResult SystemGnss_EffectiveConfigGet(SystemGnssConfig *config);
SystemDeviceResult SystemGnss_NoiseCharacteristicsGet(
    SystemGnssNoiseCharacteristics *noise);
SystemDeviceResult SystemGnss_HardwareConfigRead(SystemGnssHardwareConfig *config);
SystemDeviceResult SystemGnss_LastConfigReportGet(
    SystemGnssConfigTransactionReport *report);
SystemDeviceResult SystemGnss_SatelliteDiagnosticsRead(
    SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult SystemGnss_LatestSatelliteDiagnosticsGet(
    SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult SystemGnss_RfDiagnosticsRead(SystemGnssRfDiagnostics *diagnostics);
SystemDeviceResult SystemGnss_LatestRfDiagnosticsGet(
    SystemGnssRfDiagnostics *diagnostics);
```

`SystemGnss_RuntimeOwnerActivate()`由DeviceTask在开始周期调度前调用一次，把设备从启动同步独占模式切换到运行所有者模式。切换前的System Startup允许同步发送、推进Parser和有限等待；切换后只有`SystemGnss_Process()`可以消费GNSS RX流、推进UBX Parser或执行设备命令。其他任务调用硬件配置、卫星或RF诊断入口时只提交静态事务并有限等待，不得再次调用Device的`Process()`。

运行期单槽状态等价于`IDLE→SUBMITTED→SEND_REQUEST→WAIT_RESPONSE→PROCESS_RESPONSE→COMPLETE/FAILED`。每次DeviceTask调用最多发送一个请求、消费已经到达的响应、检查一次超时或完成一次状态转换，不得使用`while(wait_response)`或延时。CONFIG READ依次跨周期读取UART、protocol、NAV-PVT、rate、dynamic model和signals；组失败后的逐key回退也逐周期发送和等待。第二请求返回`SYSTEM_DEVICE_BUSY`；事务ID非零且递增；超时、NAK、checksum、畸形响应或RX discontinuity结束事务并释放/回收slot；无关NAV-PVT或class/id/key不匹配的帧不得完成当前事务。

`SystemGnss_TimeGet()`在不支持绝对时间的GNSS上返回`SYSTEM_DEVICE_UNSUPPORTED`。`SystemGnss_LatestSampleGet()`必须通过`velocity_valid_mask`表达二维或三维速度，不能用零值代替缺失分量。`SystemGnss_EffectiveConfigGet()`只返回当前缓存，不能冒充硬件读取；`SystemGnss_HardwareConfigRead()`必须发起真实硬件读取并以`valid_mask`标明实际取得的字段；`SystemGnss_LastConfigReportGet()`只复制最近一次事务的逐阶段诊断，不启动新事务。`*DiagnosticsRead()`发起有界硬件查询，`Latest*DiagnosticsGet()`只复制最近快照，不发送新命令。

本接口没有Ops对象、函数指针或运行期注册。任何输出指针为NULL时返回`SYSTEM_DEVICE_INVALID_ARGUMENT`，不得触发硬件访问；`Init/Start/Stop`遵循通用Device幂等规则。

## 6. Canonical接口与实例诊断

JY901B、NEO-M9N和SX1281官方插件支持每种最多四个物理实例，各自拥有独立driver/parser状态和资源绑定，源码只进入Source Graph一次。Generated descriptor区分`physical_device_id`与能力类别内连续编号的`instance_id`，静态facade通过有界direct case调用具体实例；越界返回`NOT_PRESENT`，不回退到0，不建立registry、vtable或heap。维护、Sensor Status和Native Log可读取全部启用实例。Canonical接口只输出当前active来源的一份数据：IMU在Calibration/Alignment前选择并锁定，飞行中不切换；GNSS按基础liveness单向切换；AIR只用一个active transport。投票、多INS和Multi-EKF尚未实现。 GNSS切换不依据RTK精度排名，恢复的旧主源不自动failback。

## 7. 位置可用性

System根据通用字段计算`position_usable`、`velocity_valid_mask`和拒绝掩码，不能依赖UBX私有结构。NEO-M9N Adapter只负责把NAV-PVT映射到通用字段。当前门限保持为：

- Device在线；
- `fix_type`为3D或GNSS+DR，且`fix_ok`通过；
- 卫星数不少于6；
- `hAcc <= 5 m`；
- `vAcc <= 10 m`；
- 速度的`sAcc <= 2 m/s`；
- 数据年龄不超过500 ms。

拒绝位定义为：`OFFLINE`、`NO_FIX`、`FIX_FLAG`、`FIX_TYPE`、`SATELLITES`、`HACC`、`VACC`、`SACC`、`STALE`、`FIELD_INVALID`和`FIELD_UNSUPPORTED`。`position_reject_mask`与`velocity_reject_mask`分别记录位置和速度判定，允许`fix_type=3`但因其他任一条件失败而不可用。

规则如下：

- 支持且有效的质量字段应用现有门限；
- 支持但无效的字段设置对应原因和`FIELD_INVALID`，阻止相关量测；
- 样本过期设置`STALE`；
- 必需的基本定位字段不支持时阻止位置使用；
- 可选质量字段不支持时设置`FIELD_UNSUPPORTED`和`quality_degraded=1`，但不能仅凭该项阻止START；
- 仅支持水平速度时仍可设置E|N，不得因垂直速度不支持而清空全部速度；
- 速度可用性不得依赖位置精度；course只用于水平运动方向诊断，当前KF6不融合course。

## 8. 本地ENU

原点保留整数经纬高，使用WGS84原点曲率半径：

```text
E = (N0+h0) cos(lat0) Δlon
N = (M0+h0) Δlat
U = hellipsoid - h0
```

绝对经纬度不得先转换为float再相减。位置融合使用椭球高；MSL高度只用于显示和日志。

## 9. NEO-M9N参考能力

当前NEO-M9N Adapter使用UBX-NAV-PVT，提供：

- 经纬度；
- 椭球高与MSL高；
- N/E/D速度；
- hAcc/vAcc/sAcc；
- 25 Hz PVT；
- Airborne 4g动态模型。

## 10. 0.0.12运行时配置与可用门限

NEO-M9N启动后由System通过通用写入请求明确配置星座、导航频率、动态模型、输出协议和
UBX-NAV-PVT输出。具体Device把一次请求映射到RAM、BBR和Flash，System通用接口不暴露u-blox存储层。当前配置为
25 Hz、Airborne 4G、UBX、GPS+BDS+Galileo，并使能每个导航历元输出NAV-PVT。

启用启动写入时，每个目标配置键均写入RAM、BBR和Flash。在信号配置前记录当前NAV-PVT sequence作为恢复基线，顺序必须严格为：

1. 配置接收机UART波特率并同步切换MCU UART；
2. 等待至少100 ms使新波特率链路稳定；若波特率实际改变，还必须在有界时间内确认新波特率下收到合法UBX帧；
3. 配置端口输入输出协议；
4. 使能并设置UBX-NAV-PVT输出率；
5. 配置导航率；
6. 配置Airborne 4G动态模型；
7. 配置GPS+BDS+Galileo星座/信号；
8. 记录信号配置完成时间，等待新的NAV-PVT恢复数据流。

星座/信号步骤必须是最后一个配置写入，之后只能等待数据，禁止再发送协议、消息率、导航率、动态模型或其他配置命令。恢复帧必须同时满足`pvt_sequence > baseline_pvt_sequence`且`receive_timestamp_us > signal_complete_timestamp_us`；ACK、NAK、NMEA、其他UBX帧或仅有字节活动均不能满足该条件。每一步结果、失败stage、ACK结果、写入层、基线/恢复sequence和信号完成时间必须保存在`SystemGnssConfigTransactionReport`并进入启动诊断与TF事件；不得以`(void)`丢弃失败。

`WRITE=0`时不发送VALSET/VALGET等配置I/O，也不执行上述写入事务，但仍初始化UART/DMA/Parser并检查数据流。当前0.0.12默认暂定为`SYSTEM_GNSS_BOOT_WRITE_CONFIG=1`、`SYSTEM_GNSS_BOOT_VERIFY_CONFIG=1`；宏语义不变，仍可独立切换验证四种组合。

`SystemGnss_ConfigApply()`只负责参数合法性和真实写入；`SystemGnss_ConfigVerify()`必须用VALGET从接收机真实读取并逐字段比较，不能比较缓存或目标结构；`SystemGnss_EffectiveConfigGet()`明确返回最近一次已应用或真实读取后保存的缓存。维护命令`GNSS 0 CONFIG SHOW`必须标注`source=CACHE`；`GNSS 0 CONFIG READ`必须调用`SystemGnss_HardwareConfigRead()`并标注`source=HARDWARE`，不得回显缓存冒充读取。`WRITE=1,VERIFY=0`不得预读或回读；`WRITE=0`时不论`VERIFY`为何值均不得执行VALSET、VALGET、比较或其他配置I/O。

健康状态使用最近时间窗口：近期PVT、UART/DMA状态、Parser错误增量和连续错误数共同决定`online/healthy`。历史上曾出现未知帧、校验错误或超时不能永久锁死健康；只有窗口内仍存在问题时才影响当前健康，累计计数继续保留。

GNSS样本进入预飞原点窗口的默认门限为：3D/GNSS+DR定位、至少6星、hAcc不大于
5 m、vAcc不大于10 m；速度要求sAcc不大于2 m/s。门限只控制“是否允许使用”，
融合协方差仍由每帧hAcc/vAcc/sAcc和Profile下限共同生成，因此门限放宽不会让KF
忽略接收机报告的低精度。

## 11. 0.0.12硬件读回与诊断约束

当前台架事实是：921600 bit/s双向UBX通信、VALSET ACK、NAV-PVT输出以及信号配置后的PVT恢复路径均已观察到正常工作；当前`fix_type=0`、`numSV=0`只表示尚无有效定位，不能据此否定UART或配置写入链路。该事实不等于GNSS已完成室外定位或全部配置持久化验收。

真实配置读回按`UART`、`PROTOCOL`、`NAV_PVT`、`RATE`、`DYNAMIC_MODEL`和`SIGNALS`六组执行VALGET。组请求失败后必须逐键回退；逐键回退全部成功时该组有效，任一键失败时清除该组对应`valid_mask`位，并记录首个真实失败的`failed_group`、`failed_key`、`nak_class`、`nak_id`和`response_length`。兼容汇总结果保持`RESPONSE_OK`、`NAK`、`TX_ERROR`、`CHECKSUM_ERROR`、`MALFORMED_RESPONSE`、`TIMEOUT`和`NOT_READY`；`detailed_result`进一步区分`BAD_VERSION`、`BAD_LAYER`、`BAD_POSITION`、`BAD_LENGTH`、`KEY_MISMATCH`、`VALUE_LENGTH_MISMATCH`、`COUNT_OVERFLOW`和`BUSY`等原因。

UBX-CFG-VALGET主机请求payload version固定为`0x00`，接收机响应payload version固定为`0x01`。响应必须校验class/id、可识别layer、可接受position、完整key、请求key匹配以及由key高位类型编码确定的U1/U2/U4/U8 value长度，并在任何读取前完成边界检查。长度12的单个U4响应由4字节响应头、4字节key和4字节value组成，是合法响应。ACK/NAK解析器必须识别CFG-VALSET `0x06/0x8A`与CFG-VALGET `0x06/0x8B`；无关NAV-PVT、旧响应、缓存或目标配置均不得完成VALGET事务。

NEO-M9N的`supported_fields`描述NAV-PVT能够提供的字段；`valid_fields`按当前帧定位状态生成。`fix_type`、`fix_ok`和`satellite_count`在完整NAV-PVT帧中始终有效；经纬度、水平精度、水平速度和速度精度至少要求`gnssFixOK=1`且fix type不低于2D；高度、垂直精度和垂直速度还要求3D或GNSS+DR。`fix_type=0`时不得把残留坐标、速度或巨大精度数值标成有效导航解。

`GNSS 0 NAV SAT`通过通用GNSS接口查询UBX-NAV-SAT，验证version、`numSvs`、`8 + numSvs * 12`长度、最大计数和每块边界，输出卫星总数、已用于解算数、平均/最大C/N0和平均质量。合法的`numSvs=0`响应仍返回`RESPONSE_OK`和`satellite_count=0`。

`GNSS 0 MON RF`查询UBX-MON-RF。RF block的flags低2位映射为`jamming_state`，block偏移`+16`映射为`cw_suppression`。旧`jamming_indicator`暂时保留为`cw_suppression`兼容别名，不得再解释为干扰状态。`antenna_status`枚举为0 INIT、1 DONTKNOW、2 OK、3 SHORT、4 OPEN；`antenna_power`枚举为0 OFF、1 ON、2 DONTKNOW，DONTKNOW不得自动解释为正常或故障。接口只暴露通用字段、支持/有效/新鲜状态，不暴露u-blox结构或型号判断；不支持的Adapter返回`SYSTEM_DEVICE_UNSUPPORTED`。详细结果只进入本地维护控制台和TF事件，不修改AIR固定帧。
