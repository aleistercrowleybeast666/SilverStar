# SilverStar Magnetometer 接口

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

## 1. 范围

Magnetometer Interface表示独立的三轴磁场逻辑传感器。它可以来自独立磁力计，也可以来自包含磁力计的复合IMU模块。通用接口不得依赖任何具体型号、帧类型或总线；具体实现由所选Device组件内Adapter唯一提供。

## 2. 样本与有效位

```c
#define SYSTEM_MAG_VALID_RAW           (1UL << 0)
#define SYSTEM_MAG_VALID_PHYSICAL_UNIT (1UL << 1)
#define SYSTEM_MAG_VALID_CALIBRATED    (1UL << 2)
#define SYSTEM_MAG_VALID_TEMPERATURE   (1UL << 3)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;

    int32_t raw[3];
    float magnetic_field_b_uT[3];
    float temperature_c;

    uint32_t valid_mask;
    uint8_t calibration_valid;
} SystemMagnetometerSample;
```

`magnetic_field_b_uT`必须使用系统机体系。完成单位换算只表示`SYSTEM_MAG_VALID_PHYSICAL_UNIT`有效；只有完成硬铁、软铁和安装矩阵校准后，才能设置`calibration_valid=1`及`SYSTEM_MAG_VALID_CALIBRATED`。

当前JY901B Magnetometer逻辑接口默认关闭；诊断目标显式启用后只声明raw与物理单位有效，`calibration_valid=0`且不得置`SYSTEM_MAG_VALID_CALIBRATED`。这不删除通用Magnetometer接口或AIR M0的`MAGNETOMETER=0x04` sensor ID，也不赋予绝对矢量Alignment资格。

## 3. 能力位

```c
#define SYSTEM_MAG_CAP_RAW_OUTPUT          (1UL << 0)
#define SYSTEM_MAG_CAP_PHYSICAL_UNIT       (1UL << 1)
#define SYSTEM_MAG_CAP_TEMPERATURE         (1UL << 2)
#define SYSTEM_MAG_CAP_SELF_TEST           (1UL << 3)
#define SYSTEM_MAG_CAP_CONFIG_OUTPUT_RATE  (1UL << 4)
#define SYSTEM_MAG_CAP_CONFIG_RANGE        (1UL << 5)
#define SYSTEM_MAG_CAP_DEVICE_CALIBRATION  (1UL << 6)
```

## 4. 通用配置

```c
#define SYSTEM_MAG_CFG_OUTPUT_RATE  (1UL << 0)
#define SYSTEM_MAG_CFG_RANGE        (1UL << 1)

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    uint16_t output_rate_hz;
    float range_uT;
} SystemMagnetometerConfig;
```

设备不支持某个字段时按`DEVICE_INTERFACE.md`返回`SYSTEM_DEVICE_UNSUPPORTED`，不要求所有磁力计都能配置输出率或量程。

## 5. 直接接口

```c
const char *SystemMagnetometer_NameGet(void);
SystemDeviceResult SystemMagnetometer_Init(void);
SystemDeviceResult SystemMagnetometer_Start(void);
SystemDeviceResult SystemMagnetometer_Stop(void);
void SystemMagnetometer_Process(void);
SystemDeviceResult SystemMagnetometer_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemMagnetometer_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemMagnetometer_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemMagnetometer_LatestSampleGet(
    SystemMagnetometerSample *sample);
SystemDeviceResult SystemMagnetometer_SelfTestRun(
    SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemMagnetometer_ConfigApply(
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult SystemMagnetometer_ConfigVerify(
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult SystemMagnetometer_EffectiveConfigGet(
    SystemMagnetometerConfig *config);
```

System通过上述符号直接调用所选Device的唯一Adapter；不存在Ops对象或运行期注册。

## 6. Canonical接口与实例诊断

`SystemMagnetometer_*`表示当前Canonical磁场能力；`ProjectMagnetometerInstance_*`静态facade用于`MAG <instance>`维护、Sensor Status和`MAG_NATIVE`来源标记。实例号按Magnetometer类别编号，不是复合IMU编号。JY901B当前默认不生成MAG 0；诊断构建启用时MAG 0与IMU 0、BARO 0、ATTITUDE 0共享同一`physical_device_id`。不存在实例必须返回`NOT_PRESENT`，不得映射到IMU 0。

## 7. 0.0.12使用范围

磁场主要用于START前九轴TRIAD对准和硬件姿态输出健康判断。六状态位置-速度KF不直接融合磁场。推力段是否使用磁场修正姿态由未来估计器策略决定。

## 附录A：JY901B参考实现示例

本附录仅说明一个具体Device如何适配通用接口，不构成Magnetometer Interface的通用定义。

在复合JY901B后端中，Magnetometer配置由IMU Adapter统一应用和保存；Magnetometer Adapter返回`SYSTEM_DEVICE_CONFIG_DELEGATED`并报告`delegated_mask`，自身不得初始化UART、写寄存器或保存。其健康只由`0x54`磁场帧的新鲜度、有效性和相关错误决定。

JY901B `0x54`帧提供三个有符号磁场原始值。官方参数给出的分辨率为：

```text
0.0667 mGauss/LSB = 0.00667 µT/LSB
```

具体后端可以定义：

```c
#define JY901B_MAG_MGAUSS_PER_LSB 0.0667f
#define JY901B_MAG_UT_PER_LSB     0.00667f
```

```c
sample.magnetic_field_b_uT[i] =
    (float)raw[i] * JY901B_MAG_UT_PER_LSB;
```

完成该换算后可以声明物理单位有效；未完成整机磁场标定时仍必须保持`calibration_valid=0`。
