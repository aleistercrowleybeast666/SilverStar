# SystemInertial 输入边界规范

> 文档版本：0.0.12
> 适用范围：SilverStar 0.0.12

## 1. 数据路径

```text
Device
  -> Inertial Source
  -> Source / Factory Calibration
  -> sensor_to_body transform
  -> future time assembly
  -> Virtual IMU (SystemInertialSample)
  -> Mission Calibration (SystemCalibration)
  -> ImuSampleBus / INS / Estimator / Telemetry
```

SystemInertial 是稳定的下游入口。当前0.0.12只把唯一`SystemImu_*`直接接口的样本逐字段透传为Virtual IMU，不实现多source assembler、插值或投票。物理IMU有限主备选择由上游System source selector负责，在Calibration/Alignment前锁定；Generated facade静态调用所选Device Adapter；JY901B的accel、gyro、raw、temperature、sample/receive timestamp、sequence和valid mask保持数值及bit语义兼容。

## 2. Virtual IMU

`SystemInertialSample` 是当前下游消费类型，保留现有完整 IMU 字段。公共入口为：

```c
SystemDeviceResult SystemInertial_Init(void);
SystemDeviceResult SystemInertial_LatestGet(SystemInertialSample *sample);
SystemDeviceResult SystemInertial_NextGet(SystemInertialSample *sample);
```

NULL 返回 `SYSTEM_DEVICE_INVALID_ARGUMENT`；未初始化或IMU接口未就绪返回 `SYSTEM_DEVICE_NOT_READY`；`SystemImu_LatestSampleGet/NextSampleGet`的其他返回值原样传播。模块不调用`Init/Start/Process`，也不分配动态内存。

## 3. 固定 Source sample

未来惯性来源统一使用固定结构：

```c
typedef struct
{
    SystemInertialSourceId source_id;
    uint32_t sequence;
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    SystemInertialTimestampQuality timestamp_quality;
    uint32_t valid_mask;
    float accel_mps2[3];
    float gyro_radps[3];
} SystemInertialSourceSample;
```

valid mask 独立表示 `ACCEL_X/Y/Z`、`GYRO_X/Y/Z`。完整 IMU 使用六位，三轴加速度计只使用 ACCEL_XYZ，单轴 FOG 只使用对应 GYRO 位。未使用字段置零；禁止动态长度 packet 和 malloc。

即使固定结构约 50 bytes，6 sources × 1 kHz 也只是数百 kB/s 的内存带宽量级，STM32F407 可以承受。真正需要限制的是每 source FIFO 深度、重复 buffer 和插值矩阵计算；FIFO 深度必须由 System/User 配置，本轮默认 1 且不新增复杂 FIFO。

## 4. 时间语义与未来同步

- `sample_timestamp_us`：测量对应的系统时间，是未来跨设备同步的主时间轴。
- `receive_timestamp_us`：数据到达软件的时间，用于 transport latency、stale 和 I/O 健康诊断。
- timestamp quality：`UNKNOWN`、`HARDWARE`、`DRDY_CAPTURE`、`SOFTWARE_ESTIMATED`、`RECEIVE_ONLY`。

同一物理设备内天然同步的 accel/gyro（例如 JY901B、ADIS 或设备内部同步的双芯片方案）由 Device 直接提交完整 6DOF source，System 不重复同步。来自独立设备的 FOG、石英加速度计或多单轴器件，未来由 `System/Inertial/Assembler` 同步；任何 Device driver 都不得依赖另一个传感器 driver。

已预留通用 policy：`PASSTHROUGH`、`NEAREST`、`HOLD_LAST`、`LINEAR_INTERPOLATE`，以及 `master_source`、`max_skew_us`、`stale_us`。本轮只允许 PASSTHROUGH，不实现特殊设备类别分支。

## 5. 安装变换与 Source Correction

Source descriptor 保留完整 `sensor_to_body[3][3]`，能够表达非正交安装和未来冗余单轴器件，不将安装简化成 axis/sign。

Source / Factory Calibration 位于 Virtual IMU 组装之前，统一数学形式为：

```text
x_corrected = M * (x_measured - b)
```

内部参数均为 float，支持：

- `NONE`：`b=0, M=I`；
- `BIAS_ONLY`：仅减 bias；
- `DIAGONAL`：减 bias 后使用矩阵对角项；
- `FULL_MATRIX`：减 bias 后使用完整 3×3 矩阵。

`SystemInertialSource_CorrectionApply()` 是纯数学接口。FULL_MATRIX 要求被处理的 accel 或 gyro 三轴同时有效；部分轴 source 应使用 NONE/BIAS_ONLY/DIAGONAL，直到未来 assembler 形成完整向量。Correction 完全由配置决定，核心代码禁止 `if MEMS/FOG/RLG` 类别分支。当前 JY901B 配置为 NONE，所以输出不变。

Mission Calibration 仍由 SystemCalibration 在最终 Virtual IMU 上执行 `NONE/ONE_FACE/SIX_FACE`，服务于上电 bias 和当前任务校准。它不替代持久的 factory scale、cross-axis、non-orthogonality、installation matrix 或温度模型。

## 6. 未来扩展边界

完整物理IMU的有限主备选择已经实现；多独立单轴accel/gyro、FOG + quartz同步组装及投票仍属未来扩展，只能在 `System/Inertial` 内增加编译期确定的固定source descriptor/slot、Assembler 和 Selector；ImuSampleBus、Calibration、INS、Estimator、Telemetry 的 Virtual IMU 接口不得因此变化。本轮不引入运行期Device Registry或可变函数表。

用户策略集中在`system_user_inertial_config.h/.c`：primary source、Virtual IMU选择、sync policy、master source、FIFO depth、correction和transform。FCCG读取项目模型并输出受控项目配置，但本仓库的authoritative Make不执行Python或生成器，组件源码也不依赖GUI存在。传统人工配置和手工移植必须始终受支持，不能把用户参数散落回Device或System核心。
