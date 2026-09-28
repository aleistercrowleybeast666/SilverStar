# SilverStar 0.0.12 用户配置

`System/User`只保存跨设备、跨MCU的任务配置。具体Device选择、构建资格映射、Device-owned/内部硬件服务、Board物理映射、项目资源和MCU backend属于`Targets/`、`Devices/`、`FlightLogic/`、`Board/`、`Generated/`与`Platform/`，不能写回本目录。

## 配置文件

- `system_user_config.h`：固件/Profile版本、采样率、重力、机械化、KF6、Calibration、日志、Power和维护参数；
- `system_user_alignment_config.h`：Alignment算法、known ENU yaw、磁偏角、source集合和窗口质量门；
- `system_user_flight_config.h`：Deploy trigger、TILT参考、Mission delay和Landing模式/阈值；
- `system_user_startup_config.h`：启动配置写入、持久化、真实回读验证和IMU初始重力方向；
- `system_user_capability_validation.h`：通用算法/能力组合的集中编译期约束；
- `system_user_inertial_config.c`：当前Virtual IMU静态源描述。

0.0.12不再存在`system_user_registry.h`。不要在System/User填写具体driver头、`GetOps`、ISR callback或Provider ID。

## 修改普通参数

1. 在对应User头中覆盖参数；
2. 检查单位、坐标、有效范围和与采样率/窗口的约束；
3. 运行`mingw32-make host-tests`，确认Profile与expected compile contract；
4. 运行`mingw32-make architecture-check`；
5. 对目标执行clean Debug/Release构建并核对日志`SYSTEM_CONFIG`/`MISSION_CONFIG`最终值；
6. 飞行阈值和噪声参数必须用真实日志/HIL/飞行数据调参，Host通过不等于现场有效。

## 更换设备

同类设备替换不在System/User完成：

1. 新增MCU无关Device native driver和Host测试；
2. 在该Device组件的`Adapter/`实现现有`Interfaces/Inc/system_*_if.h`直接函数；
3. 在Device build capability头声明真实资格/噪声建议；
4. 在`Targets/<target>/target.mk`和`target_system_config.h`选择、映射；
5. 更新`Generated/`项目资源/project descriptor、所属Device/内部服务与module manifest；
6. 完成Adapter mapping、architecture、ARM和硬件验收。

System/User只在任务确实要改变算法或速率时修改，不因型号变化复制设备常量。

## 当前默认组合

- Alignment：Gravity + Known ENU Yaw；
- Attitude：START后software always；
- Mechanization：two-sample coning/sculling；
- Fusion：KF6；
- IMU/Baro/Hardware Quaternion逻辑频率200 Hz，GNSS目标25 Hz；
- Magnetometer逻辑能力和MAG stream默认关闭；
- Deploy：APOGEE_VZ only，确认0 ms；
- Landing：BARO_IMU_WINDOW；
- Output：2个逻辑通道；Mission Action逻辑口0/1分别映射通道1/2；
- 当前启动策略为：GNSS不写配置、执行真实验证；JY901B按既有策略应用配置并由唯一IMU owner保存一次；Telemetry应用易失配置。修改这些开关前必须复核ACK、持久化和恢复方案。

当前JY901B的hardware quaternion六轴known-yaw与九轴静态Initial Alignment资格均为1，但两种任务期authoritative资格均为0；absolute magnetic vector和impact资格也为0。因而两种hardware quaternion预飞静态对准可编译，TRIAD、飞行全程hardware姿态权威和IMPACT_THEN_STILLNESS组合必须编译期拒绝，不运行期fallback。JY901B stillness资格为1，STILLNESS与BARO_IMU_WINDOW可编译。

## Estimator噪声

默认值来自Target映射的所选Device recommendation；User override只用于实验、特殊安装或环境：

```text
SYSTEM_ESTIMATOR_PROCESS_ACCEL_{E,N,U}_STD_MPS2_OVERRIDE
SYSTEM_ESTIMATOR_GNSS_HORIZONTAL_STD_FLOOR_M_OVERRIDE
SYSTEM_ESTIMATOR_GNSS_VERTICAL_STD_FLOOR_M_OVERRIDE
SYSTEM_ESTIMATOR_GNSS_VELOCITY_STD_FLOOR_MPS_OVERRIDE
SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_OVERRIDE
```

不要增加`USE_DEVICE/USE_SYSTEM`开关或复制第二套相同默认值。缺recommendation且override不完整必须编译失败。GNSS实时hAcc/vAcc/sAcc仍决定不确定度下限以上的实际R。

## Calibration与Alignment

预飞顺序固定：`Calibration -> Alignment -> START`。Calibration correction变化立即失效Alignment。默认known yaw按SilverStar ENU定义：body +X水平投影，0° East，+90° North；`q_nb`表示body到ENU。

Alignment选择的required source可以比System Profile的设备Required更严格。当前Baro origin若被选为required，即使Baro在设备健康层是Optional，窗口未ready也阻止START。

## FlightRecovery

Deploy mask可组合TILT/APOGEE_VZ/DELAY并按OR触发；mask=0关闭自动Deploy。TILT默认参考START冻结的rocket axis；DELAY严格相对accepted START，不是physical launch。

BARO_IMU_WINDOW先用direct Baro短窗趋势建立candidate，再要求同一时间窗的corrected gyro/accel、样本数、覆盖率、span、freshness全部通过。它不读取KF高度/vz、INS position或GNSS高度。所有阈值仍需真实飞行日志验证。

## 日志

日志开关已改为按Record的`SystemLogStreamConfig`，不存在32-bit mask。当前项目默认policy由`Generated/Src/project_log_config.c`给出，START时冻结；Record ID、metadata和逐字段little-endian双向codec是`Protocol/SSLOG/Inc/sslog_records.h`与`Protocol/SSLOG/Src/sslog_records.c`的普通源码。authoritative Make不运行Python或生成器，禁止用C struct布局直接写wire；`Protocol/SSLOG/schema/`仅是离线解析器参考。

Native sensor/POWER记录携带`source_descriptor_id + instance_id`；勾选某类Native stream的默认语义是记录当前启用的该类能力实例。当前项目只有instance 0，尚无按实例过滤、Sensor Selection或Multi-EKF配置。Physical Device到Capability Endpoint的映射由Generated descriptor/facade负责，不在System/User参数中手工建立运行期registry。

离线重放优先使用`IMU_CORRECTED`、`INERTIAL_INCREMENT`、GNSS/Baro measurement、Pure INS/KF和descriptor/config Record。默认不保存每个UART/UBX字节；底层协议分析应增加独立可选Record。

## 启动写入安全

- GNSS波特率变更必须同时考虑模块端、MCU UART和已知速率恢复；
- 未确认ACK/掉电层时不得自动写Flash；
- JY901B配置由唯一IMU物理owner处理一次，共享逻辑Adapter不得重复save；
- `SHOW`是软件effective cache，`READ/VERIFY`是真实设备事务，不得互换；
- 配置写入/验证失败要保留阶段掩码和detail，不伪造成功。

具体Target组合见`Targets/SilverStar_F407/Inc/target_system_config.h`，正式规则见[`docs/details/SYSTEM_PROFILE.md`](../../docs/details/SYSTEM_PROFILE.md)。
