# SilverStar Power Interface 与 Power Manager

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

> `0.0.12` 表示协议、接口和实现均处于首次发布前阶段。文档中的结构可以在评审后调整，不提供跨版本兼容承诺。

## 1. 电源样本

```c
#define SYSTEM_POWER_VALID_VOLTAGE    (1UL << 0)
#define SYSTEM_POWER_VALID_CURRENT    (1UL << 1)
#define SYSTEM_POWER_VALID_POWER      (1UL << 2)
#define SYSTEM_POWER_VALID_SOC        (1UL << 3)
#define SYSTEM_POWER_VALID_TEMPERATURE (1UL << 4)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;

    float voltage_v;
    float current_a;
    float power_w;
    float state_of_charge_percent;
    float temperature_c;

    uint32_t valid_mask;
} SystemPowerSample;
```

`sample_timestamp_us`表示电源量测对应的物理时刻，`receive_timestamp_us`表示完整量测被飞控接收并接受的时刻。当前ADC后端可以暂时令两者相等，但字段和语义必须分别保留，以兼容未来CAN BMS、SMBus智能电池或其他具有测量与传输延迟的电源模块。

## 2. 当前ADC后端

当前ADC Device只声明电压有效。分压比、ADC参考电压、偏移和比例校准属于`Devices/Power/ADC/Inc/adc_power_config.h`；ADC实例由Board资源映射并经Platform ADC访问。

## 3. 直接接口

```c
typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    float voltage_scale;
    float voltage_offset_v;
    float current_scale;
    float current_offset_a;
} SystemPowerConfig;

const char *SystemPower_NameGet(void);
SystemDeviceResult SystemPower_Init(void);
SystemDeviceResult SystemPower_Start(void);
SystemDeviceResult SystemPower_Stop(void);
void SystemPower_Process(void);
SystemDeviceResult SystemPower_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemPower_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemPower_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemPower_LatestSampleGet(SystemPowerSample *sample);
SystemDeviceResult SystemPower_SelfTestRun(SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemPower_ConfigApply(
    const SystemPowerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult SystemPower_ConfigVerify(
    const SystemPowerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult SystemPower_EffectiveConfigGet(SystemPowerConfig *config);
```

System通过上述直接函数调用`Devices/Power/InputVoltage/Src/power_service.c`的唯一实现；不存在Ops对象或运行期注册。

`SystemPower_*`继续作为当前Canonical Power接口；`ProjectPowerInstance_*`静态facade供`POWER <instance>`维护与POWER Native记录标注来源。当前只生成POWER 0；类别内实例号与ADC物理资源编号无关，未来实例由FCCG生成descriptor和direct case。

## 4. Power Manager

System Power Manager负责：

- 滤波；
- 欠压、过压和快速压降判断；
- 电源健康事件；
- 日志和遥测；
- 不同Device有效位兼容。

ADC底层不得直接决定飞行状态。
