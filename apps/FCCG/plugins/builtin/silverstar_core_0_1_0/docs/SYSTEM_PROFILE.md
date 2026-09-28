<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

# SilverStar System Profile 与构建期组合

> 文档版本：0.0.12
> 适用范围：SilverStar 0.0.12

System Profile描述启用能力、Required/Optional策略和算法配置，不保存具体Device枚举、Ops地址或运行期注册项。具体硬件选择属于Target manifest；设备资格在Target配置中映射为通用`SYSTEM_SELECTED_*`宏。

## 1. 配置入口

| 入口 | 职责 |
|---|---|
| `System/User/system_user_config.h` | 固件版本、采样率、导航/KF、日志、诊断与通用策略 |
| `system_user_alignment_config.h` | Alignment算法、known yaw、磁偏角与窗口质量门 |
| `system_user_flight_config.h` | Deploy触发、TILT参考、Landing模式和阈值 |
| `system_user_startup_config.h` | 启动写入/持久化/验证与初始重力方向 |
| `system_user_capability_validation.h` | 通用能力组合的集中编译期拒绝规则 |
| `Targets/<target>/target.mk` | Device core+Adapter、Board、Platform backend、Generated glue和OS port选择 |
| `Targets/<target>/Inc/target_system_config.h` | 目标能力enable、Required/Optional与Device qualification映射 |

0.0.12不存在`system_user_registry.h`。把具体设备名、头文件或入口宏写回System/User属于架构回退。

## 2. Target composition

当前`SilverStar_F407`目标选择JY901B、NEO-M9N、SX1281、UART Console、STM32F4 backend与SilverStar PCB 0.5 Board。Target直接include所选`module.mk`；Device Interface由所选Device组件内Adapter实现，存储Device与内部硬件服务组件实现其各自Interface。

`target_system_config.h`是允许认识设备构建资格的组合点，例如把设备包的accel/gyro能力、Estimator噪声建议、absolute magnetic vector资格、hardware quaternion预飞/任务期资格、Landing静止/impact资格和Mission Action能力映射为通用宏。System只读取映射后的宏。

目标内共享物理约束也在这里校验。当前JY901B的IMU、Barometer、Magnetometer和Hardware Quaternion逻辑输出必须共享同一物理stream rate；Mag enable与JY901B返回帧选择必须一致。

## 3. System Profile结构

`SystemProfile`至少包含：

```c
typedef struct
{
    uint32_t profile_id;
    uint32_t enabled_capabilities;
    uint32_t required_capabilities;
    uint32_t optional_capabilities;
    uint8_t output_channel_count;
} SystemProfile;
```

它不包含`imu_driver`、`gnss_driver`、`GetOps`或函数地址。具体设备元数据由`SystemDescriptor_*`只读接口提供并写入SSLOG descriptor。

## 4. Capability状态

必须区分四种状态：

1. compiled/selected：Target链接了实现并声明构建资格；
2. enabled：该profile要求运行期启用；
3. required/optional：失败时是fatal还是degraded；
4. runtime usable：设备当前online/healthy、sample valid/fresh且满足算法质量门。

构建资格不能由运行期health补齐；运行期online也不能赋予未评审的TRIAD、hardware quaternion预飞/任务期姿态或Landing资格。反之，qualified只说明允许使用，仍必须检查实时有效性。hardware quaternion的静态Initial Alignment资格与飞行全程authoritative资格是两个独立维度，不能互相代替。

`enabled_capabilities`必须是当前Target可编译能力的子集；`required_capabilities`和`optional_capabilities`必须互斥且都属于enabled集合。Startup跳过未启用Interface。

## 5. 当前能力策略

默认启用：IMU、GNSS、Barometer、Hardware Quaternion、Telemetry、Console、Power、Storage、Log Sink、Output、Mission Action和Time。Magnetometer逻辑能力默认关闭。

Required至少包含IMU和Output；GNSS、Barometer、Hardware Quaternion、Telemetry、Console、Power与Storage按当前profile为Optional或由具体Alignment策略另行要求。设备层Optional不覆盖算法事务required：例如当前Alignment选择Baro origin时，Baro窗口未ready仍阻止Alignment/START。

Output profile为2个逻辑通道。健康检查遍历所有通道；无法读取、FAULT、非SAFE或physical active都阻止READY。

## 6. 当前算法组合

- Alignment：`SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW`；
- Attitude：`SYSTEM_ATTITUDE_SOFTWARE_ALWAYS`；
- Mechanization：`SYSTEM_MECHANIZATION_CONING2_SCULLING2`；
- Fusion：`SYSTEM_FUSION_KF6`；
- Deploy：默认`SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ`；
- Landing：默认`SYSTEM_LANDING_MODE_BARO_IMU_WINDOW`。

Hardware quaternion保留预飞显示、fallback诊断和日志；当前JY901B六轴known-yaw与九轴静态Initial Alignment qualification均为1，而两种任务期authoritative qualification均为0。Mag raw/物理量能力不代表absolute-vector qualification，当前仍为0且默认Mag关闭。JY901B stillness qualification为1，STILLNESS与BARO_IMU_WINDOW可编译；impact qualification为0，因此选择IMPACT_THEN_STILLNESS必须编译失败。

## 7. Estimator静态参数

Estimator噪声采用“所选Device recommendation为默认，User override为可选”原则。Target映射：

- IMU三轴process acceleration std；
- GNSS horizontal/vertical position和velocity floor；
- Barometer altitude std。

用户只在实验、特殊安装或特殊环境下定义`*_OVERRIDE`。未定义override时使用Target映射值；若选中Device没有recommendation且override不完整，编译期校验失败。运行期GNSS hAcc/vAcc/sAcc仍参与R计算，静态floor不能覆盖更大的实测不确定度。

Profile源文件输出最终只读结构，SSLOG `SYSTEM_CONFIG`记录最终生效值和config digest，不记录“来自哪个C宏”的实现细节。

## 8. 配置冻结

START事务冻结：

- Navigation/Estimator/System Profile；
- Calibration correction和Alignment结果；
- Log stream policy；
- Mission config与Output/Mission Action可用性。

FLIGHT及之后不得修改会影响重放、坐标、估计或动作判定的配置。START失败或明确rollback可调用专用Unfreeze/Reset路径；普通Console写入不得绕过冻结。

## 9. Descriptor与配置digest

`Generated/Src/project_metadata.c`提供固定只读descriptor表：每条device/algorithm拥有descriptor ID、class、instance、driver/algorithm ID、flags、capability/rate和名称hash。公共上界用于内存证明，实际日志通过一实例一Record扩展。

`SystemDescriptor_ConfigDigestGet()`标识当前组合的关键静态配置。新增/替换Device、算法或改变影响重放的配置时必须审查并更新digest生成方法；不能把指针值或编译地址纳入digest。

## 10. 编译期拒绝

至少覆盖：

- enabled/required capability超出Target compiled能力；
- KF6缺少必需IMU/GNSS/Baro噪声建议且无完整override；
- TILT缺gyro或软件姿态传播；
- APOGEE_VZ缺导航垂直速度；
- DELAY缺mission monotonic time；
- 非零Deploy缺Mission Action；
- stillness或Baro/IMU landing使用未通过静止判断资格的IMU；
- impact landing使用未通过静止或冲击资格的IMU；
- TRIAD缺absolute magnetic vector；
- hardware quaternion算法/轴数与preflight alignment qualification不匹配，或把preflight qualification误作任务期authoritative qualification；
- selected/required Alignment source集合非法；
- JY901B共享物理stream rate或Mag frame选择不一致。

这些组合在Host expected-compile-failure矩阵中验证；禁止改为运行期静默fallback。

## 11. 修改流程

- 只改任务/算法参数：修改System/User，运行Profile/算法/能力测试与目标构建；
- 换同类Device：新增Device core与Adapter，更新Target manifest、Generated资源/metadata、Board和qualification；System/User不出现型号；
- 新增能力类别：先评审Interfaces、Capability bit/descriptor class、Startup/Health/Telemetry/Log语义，再实现Target；
- 新建MCU目标：新增Platform backend、Board、Target、Generated项目胶水和OS port，Device Adapter仅在设备语义变化时调整；通用System/Algorithm/Protocol保持不变。

详细构建选择见[BUILD_AND_TARGETS.md](BUILD_AND_TARGETS.md)，设备契约见[DEVICE_INTERFACE.md](DEVICE_INTERFACE.md)。
