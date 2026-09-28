<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

# SilverStar IMU 接口

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

> `0.0.12` 表示协议、接口和实现均处于首次发布前阶段。文档中的结构可以在评审后调整，不提供跨版本兼容承诺。

## 1. 范围

IMU Interface只表示加速度计与陀螺仪。磁力计、气压计和硬件四元数使用独立接口，即使它们来自同一物理模块。System只调用`Interfaces/Inc/system_imu_if.h`中的直接函数；当前实现由`Devices/IMU/JY901B/Adapter/Src/jy901b_imu_adapter.c`在链接期唯一提供。

## 2. 样本

```c
#define SYSTEM_IMU_VALID_ACCEL       (1UL << 0)
#define SYSTEM_IMU_VALID_GYRO        (1UL << 1)
#define SYSTEM_IMU_VALID_TEMPERATURE (1UL << 2)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    int32_t accel_raw[3];
    int32_t gyro_raw[3];
    float accel_b_mps2[3];
    float gyro_b_radps[3];
    float temperature_c;
    uint32_t valid_mask;
} SystemImuSample;
```

`accel_b_mps2`与`gyro_b_radps`必须已经转换到系统定义的机体系，不得把传感器坐标冒充机体系。

IMU Interface不使用姿态把样本转换到ENU。运行期样本先经`SystemInertial`逐字段发布为Virtual IMU，再由ImuSampleBus、Calibration、INS和Telemetry消费；这些下游不得直接包含具体Device头文件。二阶圆锥/划桨机械化生成的共享`SystemInertialIncrement`同样保持在机体系；Pure INS、KF导航支路和未来其他姿态支路分别使用自己的姿态上下文完成body-to-ENU变换。多独立惯性设备的同步与组装边界见[`SYSTEM_INERTIAL.md`](SYSTEM_INERTIAL.md)。

## 3. 能力位

```c
#define SYSTEM_IMU_CAP_ACCEL               (1UL << 0)
#define SYSTEM_IMU_CAP_GYRO                (1UL << 1)
#define SYSTEM_IMU_CAP_TEMPERATURE         (1UL << 2)
#define SYSTEM_IMU_CAP_SELF_TEST           (1UL << 3)
#define SYSTEM_IMU_CAP_CONFIG_OUTPUT_RATE  (1UL << 4)
#define SYSTEM_IMU_CAP_CONFIG_BANDWIDTH    (1UL << 5)
#define SYSTEM_IMU_CAP_CONFIG_RANGE        (1UL << 6)
#define SYSTEM_IMU_CAP_DATA_READY          (1UL << 7)
```

## 4. 通用配置

```c
#define SYSTEM_IMU_CFG_OUTPUT_RATE     (1UL << 0)
#define SYSTEM_IMU_CFG_ACCEL_BANDWIDTH (1UL << 1)
#define SYSTEM_IMU_CFG_GYRO_BANDWIDTH  (1UL << 2)
#define SYSTEM_IMU_CFG_ACCEL_RANGE     (1UL << 3)
#define SYSTEM_IMU_CFG_GYRO_RANGE      (1UL << 4)

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    uint16_t output_rate_hz;
    float accel_bandwidth_hz;
    float gyro_bandwidth_hz;
    float accel_range_g;
    float gyro_range_dps;
} SystemImuConfig;
```

通信波特率、I2C地址和SPI时钟不得出现在通用IMU配置中，它们属于具体Device私有硬件配置。

## 5. 直接接口

```c
const char *SystemImu_NameGet(void);
SystemDeviceResult SystemImu_Init(void);
SystemDeviceResult SystemImu_Start(void);
SystemDeviceResult SystemImu_Stop(void);
SystemDeviceResult SystemImu_RuntimeOwnerActivate(void);
void SystemImu_Process(void);
SystemDeviceResult SystemImu_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemImu_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemImu_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemImu_IoDiagnosticsGet(SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult SystemImu_IoDetailGet(SystemImuIoDetail *detail);
SystemDeviceResult SystemImu_LatestSampleGet(SystemImuSample *sample);
SystemDeviceResult SystemImu_NextSampleGet(SystemImuSample *sample);
SystemDeviceResult SystemImu_SelfTestRun(SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemImu_ConfigApply(const SystemImuConfig *config,
                                         SystemDeviceConfigReport *report);
SystemDeviceResult SystemImu_ConfigVerify(const SystemImuConfig *config,
                                          SystemDeviceConfigReport *report);
SystemDeviceResult SystemImu_EffectiveConfigGet(SystemImuConfig *config);
SystemDeviceResult SystemImu_NoiseCharacteristicsGet(
    SystemImuNoiseCharacteristics *noise);
```

`SystemImu_LatestSampleGet()`用于状态显示、对准检查等“只关心最新值”的读取；`SystemImu_NextSampleGet()`必须从Device自有FIFO按时间顺序弹出一帧，空时返回`SYSTEM_DEVICE_NOT_READY`。DeviceTask会在每个调度周期批量排空最多`SYSTEM_IMU_DRAIN_MAX_SAMPLES_PER_CYCLE`帧，防止1 kHz FOG等高频设备因任务抖动只保留最后一帧。FIFO深度和溢出统计属于具体Device；样本sequence跳变会在System层统计并可由离线解析器识别。

本接口没有Ops对象、函数指针或运行期注册。未启用的能力由Target capability在编译期阻止调用；已选择但不支持的操作返回`SYSTEM_DEVICE_UNSUPPORTED`。

## 6. Canonical接口与实例诊断

`SystemImu_*`是算法和Startup使用的单一Canonical接口；`IMU`能力只含三轴加速度和三轴角速度，不包含复合模块的气压、磁场或硬件四元数。`Generated/Inc/project_device_instances.h`另提供`ProjectImuInstance_CountGet()`及Info/Capabilities/Health/Sample/Config/I/O静态facade，供`IMU <instance>`维护、Sensor Status与`IMU_NATIVE`日志按`device_class + instance_id`读取。Generated实现使用有界`switch(instance_id)` direct case，越界返回`NOT_PRESENT`。所有selected JY901B实例均初始化、Start、Process并记录Native数据；Calibration/Alignment开始前从配置primary起选择第一个已有新鲜、校验有效且finite样本的instance，随后锁定Canonical source，本次运行和START后均不自动切换。不存在运行期注册、Voting、Multi-INS或Multi-EKF。

## 7. 噪声提示

Device可以提供传感器特性，但不得直接创建KF矩阵：

```c
typedef struct
{
    float accel_noise_density_mps2_sqrt_hz[3];
    float gyro_noise_density_radps_sqrt_hz[3];
    float recommended_process_accel_std_mps2[3];
    uint32_t valid_mask;
} SystemImuNoiseCharacteristics;
```

最终Q由System Estimator Profile和KF算法生成。

## 8. JY901B参考实现

JY901B物理驱动解析：

- `0x51`加速度；
- `0x52`角速度；
- 输出速率、带宽、量程和内部算法为设备私有配置；
- UART波特率识别与切换完全位于JY901B Device层；
- 由帧解析回调把每个完整加速度+角速度组合放入Device FIFO，System按`get_next_sample()`完整排空。

JY901B通过同一Device组件内的四个独立Adapter暴露IMU、Magnetometer、Barometer和Hardware Quaternion逻辑接口，但只有一个物理驱动、UART/DMA实例和Parser。IMU Adapter拥有全部物理配置：启用启动写入时，直接应用波特率、回传频率、带宽、加速度/角速度量程、回传内容、轴向/方向、六轴或九轴模式、融合滤波和加速度滤波等目标，然后恰好执行一次保存。该路径不得预读；保存失败必须在启动报告中明确。波特率救援、DMA启动、数据流超时和配置写入失败均须返回具体错误，不得降为成功。

JY901B现在拥有最多4个按source instance索引的静态Driver context，因此
`JY901B_BUILD_MULTI_INSTANCE_READY=1U`。每个context独立保存UART资源、parser、FIFO、配置、
样本、错误/超时计数和时间基线；同一物理JY901B的IMU/气压计/磁力计/硬件四元数Adapter
共享该context。两个JY901B可在独立UART上并行解析，源码仍只编译一份，且任何instance的
reset/config/frame/error都不得污染另一个instance。

运行期只有`SystemImu_Process()`可以消费JY901B RX流；Magnetometer、Barometer和Hardware Quaternion的`Process`入口不得重复消费UART。共享快照在短关中断临界区内整结构复制，读者不得观察半更新字段。System Startup完成同步配置/回读后，DeviceTask调用`SystemImu_RuntimeOwnerActivate()`冻结访问上下文；当前没有运行期JY901B配置命令，因此直接接口的配置/回读在该模式下返回`SYSTEM_DEVICE_BUSY`，不得从其他任务执行UART重启、波特率切换、Save或寄存器响应等待。未来增加运行期配置时必须使用IMU物理拥有者的静态事务，不得为三个附属逻辑接口建立独立拥有者。

`IMU 0 IO`底层累计计数不因GNSS维护查询而清零。`IMU 0 IO CLEAR`只在System Console按JY901B的`physical_device_id`保存当前I/O与Parser统计作为维护显示基线，后续`IMU 0 IO`显示相对增量；它不修改JY901B内部累计计数、断流序号、Parser、DMA、数据流或健康状态。BARO 0、启用时的MAG 0和ATTITUDE 0共享同一物理基线。启动阶段JY901B配置可能产生restart/discontinuity初值，运行期验收可以先清维护基线，再检查GNSS查询期间的新增量。

Hardware Quaternion Adapter只暂存所需模式；Magnetometer和Barometer的物理配置同样委托给IMU Adapter。三者在配置报告中返回`SYSTEM_DEVICE_CONFIG_DELEGATED`并填写`delegated_mask`，不得再次写寄存器或保存。真实回读验证由IMU拥有者统一执行。各逻辑接口根据自己的帧类型、有效位和最近样本时间独立计算健康；加速度/角速度更新不能让磁场、气压或四元数错误地变健康。

JY901B低层不直接包含`System/User`配置头。Adapter把唯一的`SYSTEM_LOCAL_GRAVITY_MPS2`传入物理驱动，驱动用该值把g换算为m/s²。

### 7.1 Calibration与任务姿态边界

SystemCalibration支持`NONE`、`ONE_FACE`和`SIX_FACE`。ONE_FACE的期望方向支持X+/X-/Y+/Y-/Z+/Z-且默认Y+；SIX_FACE由维护命令显式指定当前采集面。方向只用于静止度、重力方向和Correction计算，不得用于构造、重置或约束任务初始四元数。`NONE`提交零偏0、比例1的单位Correction并进入READY。

Correction进入READY后保持冻结，InsTask统一应用`corrected=(measured-bias)*scale`。此后允许移动飞控到任意实际安装姿态；用户必须执行并完成`ALIGN START`，由所选静态窗口算法生成并冻结final `q_nb`后START才可继续。默认GravityKnownYaw只使用corrected accel/gyro和配置yaw；TRIAD额外使用已校准磁场；hardware compatibility模式使用四元数窗口。任何新Calibration事务或`CAL RESET`都会立即使Alignment失效；反向的`ALIGN RESET`不得清除Correction。详细契约见[CALIBRATION_AND_ALIGNMENT.md](CALIBRATION_AND_ALIGNMENT.md)。

JY901B accel/gyro的构建资格允许用于静止Landing判定，因此`STILLNESS`和`BARO_IMU_WINDOW`可以选择；这不表示它能可靠捕获着陆冲击。其impact qualification保持0，`IMPACT_THEN_STILLNESS`必须由集中能力门在编译期拒绝。

```c
#define JY901B_IMU_BUILD_LANDING_STILLNESS_QUALIFIED 1U
#define JY901B_IMU_BUILD_LANDING_IMPACT_QUALIFIED    0U
```

## 9. MPU6050和BMI088兼容性

MPU6050后端可以只声明加速度、角速度、温度和I2C私有端口；默认不声明硬件四元数。

BMI088后端可以声明加速度、角速度、自检、ODR、带宽和量程；SPI/I2C属于私有端口；不声明磁场、气压和硬件四元数。

因此二者可通过重写Device后端接入，不需要修改INS、KF、Telemetry或日志接口。
