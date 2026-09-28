<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

# SilverStar Hardware Quaternion 接口

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

> `0.0.12` 表示协议、接口和实现均处于首次发布前阶段。文档中的结构可以在评审后调整，不提供跨版本兼容承诺。

## 1. 目的

硬件四元数不是所有IMU都具备的能力，因此独立于IMU Interface。它可来自JY901B等内部姿态解算模块，也可来自未来的外部姿态计算机。

## 2. 样本

```c
typedef enum
{
    SYSTEM_HW_QUAT_MODE_UNKNOWN = 0,
    SYSTEM_HW_QUAT_MODE_6AXIS,
    SYSTEM_HW_QUAT_MODE_9AXIS
} SystemHardwareQuaternionMode;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    float quaternion_wxyz[4];
    SystemHardwareQuaternionMode mode;
    uint8_t normalized;
    uint8_t valid;
} SystemHardwareQuaternionSample;
```

## 3. 能力与配置

```c
#define SYSTEM_HW_QUAT_CAP_OUTPUT      (1UL << 0)
#define SYSTEM_HW_QUAT_CAP_6AXIS       (1UL << 1)
#define SYSTEM_HW_QUAT_CAP_9AXIS       (1UL << 2)
#define SYSTEM_HW_QUAT_CAP_CONFIG_MODE (1UL << 3)
```

通用配置和直接接口：

```c
typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    SystemHardwareQuaternionMode mode;
    uint16_t output_rate_hz;
} SystemHardwareQuaternionConfig;

const char *SystemHardwareQuaternion_NameGet(void);
SystemDeviceResult SystemHardwareQuaternion_Init(void);
SystemDeviceResult SystemHardwareQuaternion_Start(void);
SystemDeviceResult SystemHardwareQuaternion_Stop(void);
void SystemHardwareQuaternion_Process(void);
SystemDeviceResult SystemHardwareQuaternion_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemHardwareQuaternion_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemHardwareQuaternion_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemHardwareQuaternion_LatestSampleGet(
    SystemHardwareQuaternionSample *sample);
SystemDeviceResult SystemHardwareQuaternion_SelfTestRun(
    SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemHardwareQuaternion_ConfigApply(
    const SystemHardwareQuaternionConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult SystemHardwareQuaternion_ConfigVerify(
    const SystemHardwareQuaternionConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult SystemHardwareQuaternion_EffectiveConfigGet(
    SystemHardwareQuaternionConfig *config);
```

System通过上述符号直接调用所选Device的唯一Adapter；不存在Ops对象或运行期注册。

## 4. Canonical接口与实例诊断

`SystemHardwareQuaternion_*`表示当前绑定ATTITUDE 0的硬件姿态能力；维护协议使用独立的`ATTITUDE <instance>`名称，不能归入IMU。`ProjectAttitudeInstance_CountGet()`及Info/Capabilities/Health/Sample/Config静态facade供ATTITUDE维护、Sensor Status与`HW_QUAT_NATIVE`日志读取；Native producer遍历全部启用实例并独立去重。当前只生成ATTITUDE 0，并以descriptor链接到JY901B物理设备；未来实例由FCCG生成direct case。该facade不授予任务期权威姿态资格，不实现姿态源选择，也不改变START后的软件传播。

## 5. JY901B映射

JY901B `0x59`帧提供四个有符号Q15值，顺序为W/X/Y/Z：

```c
q[i] = (float)raw_q15[i] / 32768.0f;
```

Hardware Quaternion Adapter只暂存六轴/九轴目标模式并在配置报告中返回`SYSTEM_DEVICE_CONFIG_DELEGATED`；JY901B IMU Adapter在一次物理配置事务中应用该模式并只保存一次。Quaternion Adapter不得独立预读、写寄存器或保存。其健康只由`0x59`帧的新鲜度、范数、模式有效性和相关错误决定，不能借用IMU样本时间。

Adapter必须检查范数并归一化。接口只输出设备定义下的WXYZ，不直接宣称为最终ENU `q_nb`。

System姿态适配层负责：

- 安装轴转换；
- 四元数方向和Hamilton约定；
- 六轴/九轴模式标记；
- 输出统一body-to-ENU `q_nb`。

## 6. Alignment兼容模式与运行期边界

Hardware Quaternion Interface只为显式选择的`HW_QUAT_9AXIS`或`HW_QUAT_6AXIS_KNOWN_YAW`模式提供Alignment输入。两种模式都必须收集完整静态窗口，先处理`q/-q`双覆盖符号，再求均值、归一化并检查离散度；不得把最后一帧直接作为任务姿态。

构建期资格必须区分“START前静态Initial Alignment”和“任务期权威姿态源”。当前JY901B的六轴known-yaw与九轴preflight alignment资格均为1，对应authoritative资格均为0。前者只允许静态窗口生成一次`final_alignment_q_nb`；不得用它推导START后hardware quaternion可修正、替换或持续驱动任务姿态。

```c
#define JY901B_QUATERNION_BUILD_PREFLIGHT_ALIGNMENT_6AXIS_QUALIFIED 1U
#define JY901B_QUATERNION_BUILD_PREFLIGHT_ALIGNMENT_9AXIS_QUALIFIED 1U
#define JY901B_QUATERNION_BUILD_AUTHORITATIVE_6AXIS_QUALIFIED       0U
#define JY901B_QUATERNION_BUILD_AUTHORITATIVE_9AXIS_QUALIFIED       0U
```

默认`GRAVITY_KNOWN_YAW`和可选`GRAVITY_MAG_TRIAD`不依赖hardware quaternion。Alignment READY后冻结的`final_alignment_q_nb`是START唯一初始姿态来源；接口后续样本只用于diagnostics/logging或hardware兼容模式的预飞guard。

SilverStar 0.0.12只支持`SYSTEM_ATTITUDE_SOFTWARE_ALWAYS`。`Algorithm/attitude_transition.*`、transition context、配置宏和相关测试均不存在；START后任务姿态不得被hardware quaternion修正、替换或渐近牵引。完整Alignment和ENU yaw契约见[CALIBRATION_AND_ALIGNMENT.md](CALIBRATION_AND_ALIGNMENT.md)。
