# SilverStar 0.0.8 平台规范

SilverStar 0.0.8是面向STM32F407VET6探空火箭飞控的未发布平台版本。本版冻结AIR wire format、INS机械化、GNSS预飞融合许可、DeviceTask结构和SX1281射频参数；当前修订在KF6内部增加GNSS EN/U分组门控与量测重捕获，日志协议继续冻结为SSLOG0。

## 1. 版本与AIR Profile

- 软件版本：`0.0.8`，构建标识`SILV0008`；
- AIR Profile：`AIR_PROFILE_COMPACT_V0=0`，唯一确定整套AIR消息布局和数值编码；
- 飞行日志协议：`SSLOG0`，profile id=0；
- AIR不含应用层CRC，当前完整性由SX1281 LoRa硬件CRC提供。

软件版本、AIR Profile和飞行日志格式互相独立。软件版本只出现在SYSTEM INFO、固件构建信息和LOG元数据中，不编码进AIR Capability。未来不兼容地改变i16加速度/角速度、Q15四元数、字段顺序或固定帧长度时必须分配新的`air_profile_id`；量程、射频参数、设备型号或独立`command_policy`变化不改变Profile。

## 2. 软件边界

- `APP/`负责线程入口、静态队列与任务编排；
- `Algorithm/`只包含无HAL、无FreeRTOS的纯数学算法；
- `System/Calibration/`管理IMU Calibration事务和Correction；
- `System/Alignment/`以稳定Source和四mask管理窗口化任务初始姿态、GNSS原点和气压原点；默认姿态算法为`Gravity + Known ENU Yaw`；
- `System/Inertial/`提供具体IMU Provider到Virtual IMU的稳定输入边界；
- `System/Src/system_flight_recovery.c`在既有FlightTask周期中管理任务动作、自动开伞、可选着陆、确认计时与one-shot事件；
- `System/`其余部分负责Provider、Registry、Profile、启动、生命周期、健康和维护控制台；
- `Devices/`拥有具体硬件、DMA与Parser；`Protocol/`只编解码字节；`Modules/`承载Telemetry等跨接口服务。

公共System接口不暴露HAL、UART、SPI、SDIO、FatFs或具体设备类型。系统不使用动态内存，不新增RTOS线程。

Device运行期capability只描述可输出字段和可执行操作；飞行算法资格由各Device包的`*_build_capabilities.h`声明，经`System/User/system_user_registry.h`映射后由`system_user_capability_validation.h`集中校验。构建资格不代替online/healthy/valid/fresh运行期检查，运行期健康也不能赋予未评审的算法资格。

## 3. 正式预飞依赖

依赖严格单向：

```text
Calibration READY
        ↓
Alignment READY
        ↓
START READY
```

上电后Calibration为`IDLE/NOT_SELECTED`，Alignment为`IDLE`，不自动执行校准或对准。Calibration支持：

- `NONE`：显式选择不采样，提交accel/gyro bias=0、accel/gyro scale=1并进入READY；
- `ONE_FACE`：复用单面静态窗口、六个配置方向和异常重试；
- `SIX_FACE`：用户任意顺序显式采集±X/±Y/±Z，求解三轴accel bias/scale和六面平均gyro bias，gyro scale保持1。

每次`CAL START ...`或`CAL RESET`必须立即清除已有Alignment的姿态、GNSS原点、气压原点和ready状态。Calibration重新READY后也必须重新执行`ALIGN START`。`ALIGN START/STOP/RESET`不得反向修改Calibration结果。

所有START均要求Calibration READY和Alignment required部分READY。GNSS仍为Optional：START前无GNSS原点不阻止任务，但本次任务固定禁用GNSS融合，飞行中不动态取得融合许可或重建原点。KF内部“reacquisition”只适用于START时已获准融合的量测组。

Calibration采集期间通过9字节`STATUS CALIBRATION_DIAGNOSTIC(0x0D)`和维护串口边沿事件解释无数据、运动、比力模长、重力方向、方差或采样间隙；相同诊断不重复广播，清除时发送一次NONE，诊断重试不等于Calibration FAILED。所有姿态Alignment模式使用静态窗口并冻结唯一`q_nb`（body到ENU）；软件模式的READY guard只检查校正惯性数据，不把hardware quaternion变化误判为失效。确认发生运动后整体状态锁存为`STALE(5)`，START重新返回`ALIGNMENT_REQUIRED`，且必须人工重新`ALIGN START`。source局部ready与`ready_mask`保留诊断含义，START成功后监视停止。详细数学契约见[Calibration与Initial Alignment](../details/CALIBRATION_AND_ALIGNMENT.md)。

## 4. AIR Profile 0

固定帧为：FLIGHT_STATE 50字节、PREFLIGHT_STATE 26字节、CAPABILITY/PREFLIGHT_STATUS/SENSOR_STATUS/STATUS/CMD/ACK各9字节；`AIR_MAX_FRAME_LEN=50`且Transport MTU为64。协议仍为V0、`AIR_PROFILE_COMPACT_V0=0`，详细偏移、枚举、token和字段合法性以[AIR_PROTOCOL.md](../details/AIR_PROTOCOL.md)为唯一二进制规范。

Capability声明`air_profile_id`、独立`command_policy`、Calibration能力、`sensor_summary_flags`以及16 g/2000 dps量化满量程；byte5只区分IMU/GNSS/AUX是否存在并声明snapshot支持，不再编码固定Alignment source。`PREFLIGHT_STATUS.byte6`只保留低四位Alignment state。Alignment进入READY或FAILED时，System通用逻辑Sensor Registry冻结snapshot，按IMU、GNSS、其余sensor ID/instance升序发送9字节`SENSOR_STATUS`，最后发送携带snapshot ID的`STATUS ALIGNMENT`；STALE不生成snapshot且arg1为`0xFF`。该事务可在Capability ACK前pending，ACK可抢占burst，但周期包不得插入；协议不定义Sensor Query命令。Profile 0从校准后的机体系物理量按标准重力`9.80665 m/s²`量化，不使用导航当地重力，也不传递具体IMU raw计数。

PREFLIGHT/READY立即发送Capability并每1秒重发，直到最近一次成功发送的sequence和`air_profile_id=0`被ACK；ACK后本上电周期永久停止Capability广播，并开始发送9字节PREFLIGHT_STATUS：安全机会立即一次，之后1 Hz，重要状态变化可提前。一个飞控上电周期只对应一个地面站会话。未ACK时只处理PING和CAPABILITY_ACK；AIR START额外要求Capability已ACK且AIR interlock已UNLOCK。

START成功后停止Capability、PREFLIGHT_STATUS和PREFLIGHT_STATE，并清除除已接受START最终响应外的未完成预飞控制事务。已在PREFLIGHT提交的START必须在Lifecycle响应到达后可靠排入最终ACK，即使系统已切换FLIGHT；该ACK优先于普通FLIGHT_STATE。当前独立`command_policy=PREFLIGHT_ONLY`，所以新的入站CMD只丢弃、不解析、不执行、不ACK；5 Hz FLIGHT_STATE和必要STATUS事件继续发送。底层SX1281收发状态机不因此重构。

## 5. START结果与可观测性

AIR ACK仍为9字节，结果逐项区分`CAPABILITY_REQUIRED`、`CALIBRATION_REQUIRED`、`ALIGNMENT_REQUIRED`、`SYSTEM_NOT_READY`、姿态未就绪/非法/陈旧、hooks不可用、prepare失败、原点失败、导航失败、队列失败和坏参数；`BAD_CMD`允许原样回显未知command byte。`BUSY`只表示已有START请求或事务正在执行。PREFLIGHT_STATUS的`start_block_reason`与真实AIR START共用Lifecycle预检查和映射。维护串口`SYSTEM START`不要求AIR Capability握手，但使用相同Calibration/Alignment依赖并输出完整reason。

维护协议增加CAL与ALIGN命令；`SYSTEM READY`保留旧字段并显示Calibration、Alignment与AIR会话状态。AIR Capability ACK只限制AIR START，不得使本地ready变为0。

## 6. 保持不变的运行策略

- SX1281：2473 MHz、12 dBm、SF10、800 kHz、CR 4/5、16 symbol preamble、variable length、hardware CRC ON；
- PREFLIGHT_STATE与FLIGHT_STATE均为5 Hz；新增PREFLIGHT_STATUS只在Capability ACK后至START成功前以1 Hz发送；
- Pure INS保持独立，不接受KF或硬件姿态回注；共享惯性总线只传机体系补偿增量；
- START冻结Alignment最终`q_nb`，之后只由校正陀螺增量执行软件四元数传播；不存在切回hardware quaternion的过渡。气压融合和GNSS预飞原点冻结/融合许可策略不变；KF6的GNSS量测保持position EN/U与velocity EN/U独立门控和内部重捕获；
- JY901B保持一个物理UART/DMA/Parser实例；
- 当前JY901B默认使用Gravity + Known Yaw；Mag逻辑Provider和MAG回传帧关闭，Mag raw/µT能力不代表绝对航向资格；hardware quaternion保留预飞显示/fallback与日志，但不具备6轴/9轴权威Alignment资格，默认请求6轴算法；
- 日志使用SSLOG0；既有Record ID与字段布局冻结，新增能力优先追加新Record。

## 7. FlightRecovery与Mission Action

外部Lifecycle枚举保持`BOOT/SELF_TEST/PREFLIGHT/READY/FLIGHT/RECOVERY/LANDED/POSTFLIGHT/FAULT`不变。START真正提交并进入FLIGHT后，FlightRecovery通过Mission Action Provider执行一次任务开始动作。自动开伞采用`TILT/APOGEE_VZ/DELAY` trigger bitmask，多个bit为OR、mask=0关闭自动触发；当前默认仍为APOGEE_VZ only。TILT默认相对START冻结的initial rocket axis，DELAY严格相对START后的mission time 0而非physical launch；同周期多条件成立时日志保存完整matched mask，动作仍exactly once。只有timestamp+sequence表示的新有效Estimator样本才重新评价传感器触发；当前默认确认0 ms，首个越阈新样本立即锁存one-shot。动作成功才产生`PARACHUTE_DEPLOY`事件并进入RECOVERY。

第一版Mission Action Provider位于`Devices/MissionAction/Output/`，封装现有1-based Output Provider：逻辑功率口0映射通道1/P_CONTROL1，逻辑口1映射通道2/P_CONTROL2。System只决定何时执行，Devices决定如何执行；System接口不出现HAL或GPIO。

着陆检测当前默认启用并使用`BARO_IMU_WINDOW`：RECOVERY直接读取`EstimatorPressureSnapshot.altitude_m`，以短窗口线性回归高度变化率打开candidate，再在同一时间窗口同时验证Baro回归斜率/span和corrected gyro/accel静止、样本数、覆盖率及freshness。KF高度/vz、INS position、GNSS高度均不参与；Baro失效时保持RECOVERY且不fallback。`STILLNESS`保留台架/HIL兼容，`IMPACT_THEN_STILLNESS`仅供声明可靠冲击采样能力的IMU；当前JY901B capability为0，配置impact模式会在编译期拒绝。AIR仍只使用既有9-byte STATUS `0x05/0x06`；MISSION_CONFIG draft升级为record version 2以记录bitmask、delay和Baro/IMU窗口配置，SSLOG0公共framing与EVENT布局不变。

GNSS融合许可仍只在START冻结，飞行中不动态开启、也不重建ENU原点。已获许可的量测内部按position EN/U和velocity EN/U四组独立NIS门控；连续hard reject且GNSS自身相邻历元满足运动学一致时，按组、按间隔、有限次数执行`P'=D P D'`，使可靠GNSS可以重新进入。此机制不修改AIR、Lifecycle、GNSS Device配置或Quality Gate，也不替代未来的固定滞后/OOSM时间对齐。

## 8. 正式规范索引

- [文档清单](../details/DOCUMENT_LIST.md)
- [工程架构](../details/ARCHITECTURE.md)
- [System Calibration](../details/SYSTEM_CALIBRATION.md)
- [System Alignment](../details/SYSTEM_ALIGNMENT.md)
- [Calibration与Initial Alignment算法契约](../details/CALIBRATION_AND_ALIGNMENT.md)
- [System Inertial](../details/SYSTEM_INERTIAL.md)
- [System生命周期](../details/SYSTEM_LIFECYCLE.md)
- [AIR二进制协议](../details/AIR_PROTOCOL.md)
- [Telemetry接口](../details/TELEMETRY_INTERFACE.md)
- [维护串口协议](../details/MAINTENANCE_PROTOCOL.md)
- [Console接口](../details/CONSOLE_INTERFACE.md)
- [导航与估计](../details/NAVIGATION_AND_ESTIMATION.md)
- [Output与Mission Action](../details/OUTPUT_INTERFACE.md)
- [Storage与日志SSLOG0](../details/STORAGE_AND_FLIGHT_LOG.md)
- `details/DEVICE_PROVIDER_INTERFACE.md`（历史文件，0.0.9平台化后已删除）
- [验收要求](../details/VALIDATION_REQUIREMENTS.md)

## 9. 验证边界

Host测试和ARM编译只能证明接口、算法、状态机和二进制布局的静态实现。本轮不改变硬件参数，也不把静态结果描述为GNSS、JY901B、SX1281、TF或安全输出已经重新上板验证。

本地状态指示抽象见[`details/SYSTEM_INDICATOR.md`](../details/SYSTEM_INDICATOR.md)。当前仅启用SYSTEM灯，校准面/Calibration/Alignment成功使用500 ms非阻塞常亮提示。
