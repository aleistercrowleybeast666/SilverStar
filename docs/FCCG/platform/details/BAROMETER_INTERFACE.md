# SilverStar Barometer 接口

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

> `0.0.12` 表示协议、接口和实现均处于首次发布前阶段。文档中的结构可以在评审后调整，不提供跨版本兼容承诺。

## 1. 样本

```c
#define SYSTEM_BARO_FIELD_PRESSURE    (1UL << 0)
#define SYSTEM_BARO_FIELD_ALTITUDE    (1UL << 1)
#define SYSTEM_BARO_FIELD_VARIANCE    (1UL << 2)
#define SYSTEM_BARO_FIELD_TEMPERATURE (1UL << 3)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    int32_t pressure_raw_pa;
    int32_t altitude_raw_cm;
    float pressure_pa;
    float altitude_m;
    float altitude_variance_m2;
    float temperature_c;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint32_t valid_mask;
} SystemBarometerSample;
```

`supported_fields`描述当前Device能够提供的字段，`valid_fields`描述当前样本真实有效的字段；`valid_mask`保留现有日志和维护命令语义，当前值与有效字段位一致。不支持的字段不得伪造为0，也不得因温度等可选字段缺失而使整个接口失败。

## 2. 配置、噪声与直接接口

```c
typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    uint16_t output_rate_hz;
} SystemBarometerConfig;

typedef struct
{
    float recommended_altitude_std_m;
    float pressure_noise_std_pa;
    uint32_t valid_mask;
} SystemBarometerNoiseCharacteristics;
```

```c
const char *SystemBarometer_NameGet(void);
SystemDeviceResult SystemBarometer_Init(void);
SystemDeviceResult SystemBarometer_Start(void);
SystemDeviceResult SystemBarometer_Stop(void);
void SystemBarometer_Process(void);
SystemDeviceResult SystemBarometer_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemBarometer_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemBarometer_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemBarometer_LatestSampleGet(SystemBarometerSample *sample);
SystemDeviceResult SystemBarometer_SelfTestRun(SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemBarometer_ConfigApply(
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult SystemBarometer_ConfigVerify(
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult SystemBarometer_EffectiveConfigGet(SystemBarometerConfig *config);
SystemDeviceResult SystemBarometer_NoiseCharacteristicsGet(
    SystemBarometerNoiseCharacteristics *noise);
```

System通过上述符号直接调用所选Device的唯一Adapter；不存在Ops对象或运行期注册。

## 3. Canonical接口与实例诊断

`SystemBarometer_*`返回配置的primary BARO能力。Generated按实例facade供维护、Sensor Status及BARO_NATIVE读取全部启用端点并独立去重；不以0作为所有构建的固定绑定。来自同一JY901B的IMU、BARO、ATTITUDE及可选MAG共享physical_device_id和I/O owner，仍为独立能力端点。多物理实例由FCCG生成descriptor/direct case，不产生registry，也不自动复制Canonical量测。

## 4. JY901B映射

`0x56`帧：

- 前4字节：压力，Pa，int32；
- 后4字节：模块高度，cm，int32。

JY901B Barometer Adapter只能读取统一JY901B物理快照，不得再次初始化UART。其配置由IMU Adapter统一应用和保存；Barometer Adapter返回`SYSTEM_DEVICE_CONFIG_DELEGATED`并报告`delegated_mask`。健康只由`0x56`气压/高度帧的新鲜度、有效性和相关错误决定。

## 5. 原点和融合

START前对新的baro sequence进行平均，START时冻结原点：

```text
z_baro = altitude_m - baro_origin_m
```

同一压力数据计算出的设备高度和软件高度不得作为两条独立量测同时融合。

System选择规则：有效设备高度优先保持现有JY901B路径；只有压力时按统一标准大气模型换算高度；只有有效高度时直接使用高度。压力与高度同时存在时仍只生成一条气压高度量测。DeviceTask把压力、高度、字段掩码和时间戳发布到EstimatorBus；EstimatorTask在START前维护原点窗口，START冻结原点，任务期间以`altitude-origin`执行1D KF更新。

气压计为Optional时，目标未启用、接口不支持、Device未就绪或原点不足均不得阻止START；系统退化为不使用气压z修正，并通过维护串口和TF事件明确报告。若Profile把气压计设为Required，则由通用Required规则阻止任务。

运行时诊断必须区分Target启用/接口能力/配置状态、样本新鲜度与有效性、原点状态，以及KF更新的`ACCEPTED`、`SOFTENED`、`REJECTED`和跳过原因。诊断只观察现有数值路径，不得为获得“通过”而修改气压噪声、NIS门限或量测符号。

当前KF6默认高度标准差为5 m，Device可以给建议值，System Profile拥有最终覆盖权。

## 6. 任务期pending语义

任务期气压更新使用一个设备无关的单槽pending。若新样本的`sample_timestamp_us`晚于当前KF状态时间，EstimatorTask锁存完整样本并报告`WAIT_STATE_CATCHUP`，但不更新已消费sequence、不递增每周期跳过计数，也不允许总线后续最新样本覆盖该槽。状态时间追上后，样本按正常新鲜度、字段合法性、冻结原点和NIS门限处理；接受、软化、拒绝或永久丢弃后才释放pending。`sample_valid=1`表示pending已经通过字段/高度解析，`measurement_variance`必须大于零，成功更新后PZ应受到约束。
