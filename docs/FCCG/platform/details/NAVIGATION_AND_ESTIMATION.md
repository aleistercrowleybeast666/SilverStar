# SilverStar 导航、惯导与状态估计规范

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

> `0.0.12` 表示协议、接口和实现均处于首次发布前阶段。文档中的结构可以在评审后调整，不提供跨版本兼容承诺。

## 1. 四个正交算法选择

```c
typedef enum
{
    SYSTEM_ALIGNMENT_HW_QUAT_6AXIS_KNOWN_YAW = 0,
    SYSTEM_ALIGNMENT_GRAVITY_MAG_TRIAD = 1,
    SYSTEM_ALIGNMENT_HW_QUAT_9AXIS = 2,
    SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW = 3
} SystemAlignmentAlgorithm;

typedef enum
{
    SYSTEM_ATTITUDE_SOFTWARE_ALWAYS = 0
} SystemAttitudePolicy;

typedef enum
{
    SYSTEM_MECHANIZATION_CONING2_SCULLING2 = 0
} SystemMechanizationAlgorithm;

typedef enum
{
    SYSTEM_FUSION_NONE = 0,
    SYSTEM_FUSION_KF6
} SystemFusionAlgorithm;
```

姿态初对准配置位于`System/User/system_user_alignment_config.h`，其余导航配置位于`system_user_config.h`：

```c
#define SYSTEM_ALIGNMENT_ALGORITHM       SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW
#define SYSTEM_ALIGNMENT_KNOWN_YAW_DEG   0.0f
#define SYSTEM_ATTITUDE_POLICY           SYSTEM_ATTITUDE_SOFTWARE_ALWAYS
#define SYSTEM_MECHANIZATION_ALGORITHM   SYSTEM_MECHANIZATION_CONING2_SCULLING2
#define SYSTEM_FUSION_ALGORITHM          SYSTEM_FUSION_KF6
```

这些宏是当前配置值，不使用`DEFAULT`命名。`SYSTEM_FUSION_NONE`表示直接使用独立Pure INS支路作为导航输出，不运行KF6预测或量测更新，也不生成KF6诊断/P日志。

## 2. 初始对准

Calibration与Alignment职责分离，但存在严格的单向依赖：`Calibration READY -> Alignment READY -> START READY`。六个候选方向只属于Calibration；校准完成后不得用校准姿态生成、重置或约束任务初始四元数。飞控可以在校准完成后移动到任意实际安装姿态，再显式执行`ALIGN START`。

Calibration READY且执行`ALIGN START`后，InsTask按所选算法非阻塞收集静态窗口。默认`GRAVITY_KNOWN_YAW`收集100～128帧corrected acceleration和corrected gyro，以窗口均值建立重力方向并应用配置的ENU yaw；TRIAD额外收集已校准磁场；hardware quaternion兼容模式收集完整四元数窗口并做hemisphere/sign统一、均值、归一化和离散度检查。所有模式都输出同一`q_nb`（body到ENU），不使用最后一帧，也不使用Euler-angle decomposition。

姿态子项就绪与总体Alignment READY由SystemAlignment公共判定产生。required attitude与barometer source必须READY；GNSS origin保持optional。READY时一次性冻结`final_alignment_q_nb`和窗口诊断，此后最新hardware quaternion不得覆盖它。`SystemHealth`、`SYSTEM READY`、PREFLIGHT_STATE和START事务使用同一冻结结果。

收到START后，InsTask复制冻结的final quaternion到任务快照。若Calibration/Alignment依赖失效或READY guard已锁存STALE，返回明确的Calibration/Alignment原因，不得伪装为内部`BUSY`。详细窗口、质量门、yaw和算法契约见[CALIBRATION_AND_ALIGNMENT.md](CALIBRATION_AND_ALIGNMENT.md)。

### 2.1 六轴硬件四元数 + 已知航向

该兼容模式使用START前hardware quaternion静态窗口建立tilt，再以统一SilverStar ENU yaw修正水平方向。当前JY901B具备该静态Initial Alignment资格；消费级六轴姿态不能独立确定绝对yaw，因此必须提供known yaw。该资格不允许hardware quaternion成为START后的权威姿态源；新的软件默认模式不使用legacy body-axis参数。

### 2.2 重力/磁场 TRIAD

`GRAVITY_MAG_TRIAD`由corrected accel/gyro与calibrated magnetometer窗口直接建立rotation basis，并应用磁偏角；hardware quaternion既不是数学输入也不是成功条件。

### 2.3 九轴硬件四元数

该兼容模式对START前合法hardware quaternion静态窗口统一双覆盖符号、求均值、归一化并检查离散度，不改变直接Interface已经交付的坐标和分量语义。当前JY901B具备该静态Initial Alignment资格，但任务期authoritative资格保持0。

### 2.4 重力 + 已知ENU yaw（默认）

corrected acceleration窗口均值确定gravity/up，corrected gyro只用于静止检查；算法直接构造tilt quaternion，再绕navigation +Z修正到配置yaw。默认`yaw=0 deg`表示body +X水平投影指向East，不是`0=North`的compass heading，也不应用磁偏角。

## 3. START后姿态

软件传播从START冻结的Alignment final `q_nb`开始，使用二子样圆锥补偿角增量持续更新。SilverStar 0.0.12只有`SYSTEM_ATTITUDE_SOFTWARE_ALWAYS`：START后可以继续读取和记录硬件四元数，但不得把它回注到任务姿态；工程中不存在软件姿态向硬件四元数的渐近过渡源文件、配置或运行路径。运行期权威姿态始终是归一化四元数，Euler angles不参与导航或估计算法。

Pure INS支路始终保持独立，不接受KF或硬件四元数回注，作为基线对照。

## 4. 机械化

当前唯一算法：

- 二子样二阶圆锥误差补偿；
- 旋转补偿；
- 二阶划桨误差补偿；
- ENU速度和位置积分。

共享惯性增量总线固定传递补偿后的机体系增量：

```c
typedef struct
{
    uint64_t timestamp_us;
    uint32_t sequence;
    float dt_s;

    float delta_theta_b_corrected[3];
    float delta_velocity_b_sculling_corrected[3];
} SystemInertialIncrement;
```

语义与所有权要求：

- `delta_theta_b_corrected`是二子样二阶圆锥补偿后的机体系角增量；
- `delta_velocity_b_sculling_corrected`是旋转补偿和二阶划桨补偿后的机体系比力速度增量，尚未旋转到ENU，也尚未加入重力增量；
- 总线不得发布由Pure INS姿态转换后的ENU速度增量；
- Pure INS、KF导航支路以及未来其他姿态支路分别维护自己的`q_nb`，使用各自姿态将机体系速度增量转换到ENU并完成重力补偿；
- `timestamp_us`使用System Monotonic Time，表示该完整机械化区间结束时刻；`sequence`对成功发布的完整增量单调递增；
- Pure INS状态、姿态和机械化上下文保持独立，任何KF状态或量测修正不得写回Pure INS。

## 5. KF6状态

```text
x = [pE pN pU vE vN vU]^T
```

KF6数学核心的预测输入仍是导航系速度增量，但该增量必须由KF导航支路在消费`SystemInertialIncrement`后，使用KF支路自己的当前姿态上下文生成。Estimator不得直接复用Pure INS已经旋转到ENU的结果。

设KF支路生成的导航系速度增量为`delta_velocity_n_corrected`，状态转移：

```text
p_k = p_{k-1} + v_{k-1} dt + 0.5 Δv dt
v_k = v_{k-1} + Δv
```

量测按序贯方式独立更新：

- GNSS位置水平E/N 2D；
- GNSS位置垂直U 1D；
- GNSS速度水平vE/vN 2D；
- GNSS速度垂直vU 1D（仅在垂直速度有效时）；
- 气压高度1D。

同一GNSS历元的EN与U使用同一份量测各一次，按上述顺序执行合法的序贯更新，不再执行额外的完整ENU重复更新。各组独立NIS门控，因此U或vU异常不会切断水平修正，反向亦然。旧`NavigationKf_UpdateGnssPosition/Velocity2D/Velocity3D`接口保留为分组实现的兼容wrapper。

## 6. P0生成

System Estimator Profile生成P0，Device只提供精度提示。

默认：

```text
σpE=2 m, σpN=2 m, σpU=3 m
σvE=0.5 m/s, σvN=0.5 m/s, σvU=0.5 m/s
P0=diag(4,4,9,0.25,0.25,0.25)
```

有合格GNSS精度时可用`max(Profile下限, accuracy×scale)`调整已观测分量。只有二维速度时不得缩小vU方差。

## 7. Q生成

IMU Device必须通过直接Interface给出推荐等效过程加速度标准差。当前所选JY901B包的推荐值为：

```text
E=1.5 m/s², N=1.5 m/s², U=2.0 m/s²
```

KF根据dt生成速度增量噪声和状态过程协方差。Device不得直接生成6×6矩阵。普通用户无需在System/User重复填写这些值；只有实验调参、特殊安装或特殊环境才定义`SYSTEM_ESTIMATOR_PROCESS_ACCEL_E/N/U_STD_MPS2_OVERRIDE`。未定义override时，`SystemEstimatorProfile`直接采用所选IMU包的推荐值。

## 8. R生成

NEO-M9N始终优先使用实时hAcc/vAcc/sAcc，并施加下限：

```text
水平位置1.5 m
垂直位置2.5 m
速度0.15 m/s
scale=1.25
```

三项下限的默认值来自NEO-M9N Device；可选`SYSTEM_ESTIMATOR_GNSS_HORIZONTAL_STD_FLOOR_M_OVERRIDE`、`SYSTEM_ESTIMATOR_GNSS_VERTICAL_STD_FLOOR_M_OVERRIDE`和`SYSTEM_ESTIMATOR_GNSS_VELOCITY_STD_FLOOR_MPS_OVERRIDE`只替换对应floor。实际量测仍严格使用：

```text
horizontal_std = max(hAcc * scale, horizontal_floor)
vertical_std   = max(vAcc * scale, vertical_floor)
velocity_EN_std = max(sAcc_EN * scale, velocity_floor)
velocity_U_std  = max(sAcc_U * scale, velocity_floor) * gnss_velocity_vertical_scale
```

因此Device静态推荐值不会把GNSS R退化为固定值。JY901B Barometer的推荐高度标准差为5 m；未定义`SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_OVERRIDE`时由Barometer Interface提供。当前量测方差与该推荐下限取较大值，未来Device提供更大的实时不确定度时继续优先保留实时值。

Device推荐值与可选User override在构建`SystemEstimatorProfile`时解析为明确最终数值；START沿用Lifecycle既有顺序冻结该Profile，飞行阶段只消费冻结结果。飞行日志格式0.0的`SYSTEM_CONFIG`继续写入最终生效的过程噪声、GNSS floor和气压标准差，不记录来源标签，也不改变Record布局。

## 9. NIS门控与GNSS重捕获

- 3D soft 11.345，hard 16.266；
- 2D soft 9.210，hard 13.816；
- 1D soft 6.635，hard 10.828。

soft与hard之间扩大R后重算；超过hard拒绝。正常模式继续保留这一异常值保护。GNSS position EN、position U、velocity EN、velocity U与气压分别门控，一个组拒绝不连带拒绝其他组。

仅靠hard reject不能自行修复“INS预测继续漂移、创新继续增大”的正反馈。因此KF内部对四个GNSS组分别维护reject streak、GNSS自一致计数、reacquire active、膨胀间隔和有限attempt。进入重捕获必须先发生对应组有效历元间隔严格超过 gnss_reacquire_outage_ms（默认 300 ms）的失联。连续新鲜 GNSS 的 hard reject 本身永不授权膨胀。返回帧先执行普通 NIS，接受时直接回到跟踪；仅仍拒绝时才继续确认。还必须同时满足：System GNSS质量门已通过、字段和时间戳有效、对应组连续hard NIS reject达到配置值，并且GNSS最近历元本身连续满足运动学一致性。单帧跳点或GNSS自身连续乱跳只被拒绝，不触发协方差膨胀。

位置自一致性使用相邻GNSS历元：

```text
predicted_delta_p = 0.5 * (v_gnss[k-1] + v_gnss[k]) * dt
self_residual = (p_gnss[k] - p_gnss[k-1]) - predicted_delta_p
```

E/N使用水平norm，U独立使用绝对值；容差同时包含hAcc/vAcc、sAcc、dt、用户floor与不确定度倍率。速度组使用`|delta_v| <= configured_max_acceleration * dt + accuracy_margin`，水平与垂直最大加速度分别配置，因此该判据允许探空火箭真实高动态，不是“静止半径窗口”，也不要求GNSS先同意已经失锁的KF预测。

重捕获只降低对Prediction的信任，不改小GNSS报告R、不覆盖状态、不改变ENU原点。每个组按配置间隔执行有限次选择性膨胀：

```text
P' = D * P * D'
```

`D`仅缩放该组的`[pE,pN]`、`pU`、`[vE,vN]`或`vU`维度。每次操作检查finite、恢复对称并受位置/速度方差cap与最大attempt保护；禁止每个25 Hz reject都指数膨胀。对应组连续融合成功达到配置次数后退出reacquire，其他组的状态互不代替。

当前用户配置为：连续hard reject 5次、连续GNSS运动一致3个相邻区间后允许进入，`D`目标缩放因子2.0、两次膨胀至少间隔5个对应组新历元、最多8次、连续融合成功3次退出；位置与速度方差cap分别为`1.0e6 m²`和`1.0e4 (m/s)²`。所有值位于`System/User/system_user_config.h`，算法源文件不得另写可调默认值。

## 10. 数值保护

- Joseph协方差更新；
- 对称化；
- 对角下限；
- SPD求解检查；
- NaN/Inf检查；
- 数值故障健康位；
- 完整P日志调试。


## 公式文件

- [`../formula/flight_controller_6d_kf_equations.tex`](../formula/flight_controller_6d_kf_equations.tex) / [PDF](../formula/flight_controller_6d_kf_equations.pdf)
- [`../formula/ins_coning_sculling_mechanization.tex`](../formula/ins_coning_sculling_mechanization.tex) / [PDF](../formula/ins_coning_sculling_mechanization.pdf)

## 11. SilverStar 0.0.12 Calibration与初始对准实现

当前固件的任务初始姿态固定采用`ALIGN START`后由所选静态窗口算法生成并在READY冻结的final `q_nb`。默认GravityKnownYaw和TRIAD是已接入的软件对准能力，hardware quaternion模式也使用多帧hemisphere mean；当前JY901B六轴/九轴模式具备这种预飞静态资格，但不具备START后权威姿态资格，不存在最新单帧捷径或飞行中回注。

对准与机械化统一使用`SYSTEM_LOCAL_GRAVITY_MPS2=9.78f`，该宏是工程中唯一的本地重力配置。Algorithm上下文由调用方显式传入该值，不包含第二套默认值。

当前用户配置为`SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW`且known ENU yaw为0 deg（body +X水平投影指向East）。窗口质量、模式必需Interface和required source检查均属于公开Alignment判定，不得在START增加隐藏门槛。

SystemCalibration独占Mission Calibration事务和Correction结果；SystemAlignment只在Calibration READY后通过通用source adapter调度初始姿态、GNSS原点和气压原点。总体状态为`IDLE/COLLECTING/CHECKING/READY/FAILED/STALE`，最终READY只按`(ready_mask & required_mask) == required_mask`判断，并受STALE锁存约束。当前`selected=ATTITUDE|GNSS|BARO`、`required=ATTITUDE|BARO`；因此GNSS无fix不阻止START并保持既有`NO_PREFLIGHT_ORIGIN`、START后不动态开启GNSS融合且不重建原点的策略，但BARO窗口未ready时不得提前通过Alignment。这里的“GNSS重捕获”只指已获准融合的KF量测组重新进入，不是重新获取预飞许可或重建原点。接口及维护语义见[`SYSTEM_CALIBRATION.md`](SYSTEM_CALIBRATION.md)、[`SYSTEM_ALIGNMENT.md`](SYSTEM_ALIGNMENT.md)和[`SYSTEM_INERTIAL.md`](SYSTEM_INERTIAL.md)。

### 11.1 Calibration状态机

`CAL START ONE_FACE`支持X+/X-/Y+/Y-/Z+/Z-六个重力方向，默认Y+。期望重力方向是所选机体系单位轴，方向接受条件为归一化平均加速度与期望方向点积不小于`0.9396926f`。单面模式对每轴计算：

```text
accelerometer_bias_b = mean_acceleration_b - expected_direction_b * SYSTEM_LOCAL_GRAVITY_MPS2
```

`CAL START NONE`是合法Calibration事务：它明确选择不执行本次采样，并提交单位Correction（加速度/角速度零偏为0、比例为1），随后Calibration进入READY。ONE_FACE持续等待合格窗口；SIX_FACE由`CAL FACE <direction>`明确指定并采集六个面，重复方向覆盖旧结果，集齐后求解三轴零偏与比例。等待原因明确区分无数据、运动、幅值、方向、方差、间隙和数值异常。

Calibration进入READY后立即结束候选方向的姿态语义。任务初始姿态仅来自本次Alignment窗口冻结的final `q_nb`，START不得引用Calibration方向或构造Y+姿态。四元数保持WXYZ Hamilton、body到ENU；yaw统一为body +X水平投影相对East的几何角。

任何`CAL START ...`或`CAL RESET`必须在事务开始时立即使现有Alignment失效；新的Correction提交同样不得保留旧Alignment。Alignment结果失效后START READY立即失效，即使Calibration稍后重新完成，也必须重新执行并完成`ALIGN START`。反向不成立：`ALIGN RESET`和重新Alignment不得清除Calibration结果。

常用选择项位于`System/User/system_user_alignment_config.h`：算法、known ENU yaw、legacy参考机体轴、磁偏角、窗口和质量门。JY901B磁标定有效声明位于`Devices/Magnetometer/JY901B/Inc/jy901b_magnetometer_config.h`，只有完成整机磁标定并确认其生效后才可置1。

## 12. 预飞原点窗口和实际P0

PREFLIGHT期间持续保存最近100帧合格GNSS位置/速度和最近100帧气压高度。START事务冻结窗口，执行3σ异常值剔除，至少保留80个内点后才建立对应原点。窗口最后样本还必须满足新鲜度限制。

GNSS不可用不阻止START；但GNSS融合权限在START事务中一次性冻结。若START前未形成合格GNSS原点窗口，则本次任务内GNSS位置和GNSS速度均不参与KF更新，即使飞行中稍后获得定位也不动态启用。气压原点不可用时只禁用气压高度更新。

若START前形成合格GNSS原点窗口，则以冻结的平均纬度、高度计算WGS-84子午圈曲率半径M和卯酉圈曲率半径N。任务期间固定使用该局部切平面参数，将经纬度差换算为E/N坐标：`E=(N+h0)cos(phi0)Delta_lambda`，`N=(M+h0)Delta_phi`；高度差形成U。500 m级局部任务不在飞行中重建原点或动态改变曲率半径。

实际P0对角线取Profile保守下限、GNSS报告精度和窗口实测离散度的较大者。后续GNSS位置R额外加入冻结原点方差，气压R额外加入气压原点方差。START日志记录实际使用的P0、原点、窗口样本数和离散度。

## 13. 时间对齐边界

当前KF6检查`sample_timestamp_us`并拒绝超过500 ms的陈旧量测，但本版本尚未实现历史状态回放。GNSS/气压量测仍更新到当前KF状态；几十毫秒量测延迟在高动态下仍可能放大innovation。新GNSS reacquisition解决的是“可靠量测在短时异常后长期无法重新进入”，不补偿量测时刻与当前状态时刻的偏差。高动态精度定型前仍应评估固定滞后/OOSM历史缓冲：在量测时刻更新历史状态，再重放后续惯性增量到当前时刻。


## 14. 估计器只读诊断

诊断不得形成第二套导航状态，也不得参与算法分支。EstimatorTask直接发布现有KF上下文、冻结原点、融合许可和量测结果；InsTask直接发布现有机械化输出、姿态就绪和Calibration Correction快照。System Console只读取这些静态快照。

- `ESTIMATOR STATUS`用于确认任务状态、算法模式、姿态/位置来源、惯性预测计数和最近状态时间；
- `ESTIMATOR GNSS`保留原有字段顺序，并在末尾追加四组NIS、E/N/U与vE/vN/vU innovation、各组effective std、六个P对角、分组接受/拒绝计数、reject streak、reacquire mask/count及最近膨胀组/因子/attempt；
- `KF STATUS`使用现有KF预测和三类聚合更新计数，`sequential_update_count`仍为位置历元、速度历元和气压更新调用总和；末尾只追加reacquire count与active mask摘要；
- `INS STATUS`区分姿态就绪、Calibration完成和START后软件机械化传播，速度/位置有效性只有在机械化形成合法状态后置位。

START前，`SYSTEM READY.gnss_ready`表示当前GNSS位置样本合法且新鲜，`gnss_origin_ready`表示预飞窗口达到冻结条件，`gnss_fusion_enabled`表示按当前窗口执行START时可启用KF6 GNSS融合。GNSS为Optional，这三个字段不阻止READY。START事务冻结后，`gnss_fusion_enabled`只表示本次任务冻结的实际许可：没有预飞原点时固定为0并报告`NO_PREFLIGHT_ORIGIN`；START后获得fix不启用融合、不重建原点。

GNSS旧聚合计数维持每个历元最多增加一次：至少一个有效position组真正融合时该历元计入position accept（soft也属于已融合），所有尝试的position组均未融合才计入position reject，因此`accept+reject=updates`；velocity同理。分组详细计数单独反映部分接受/拒绝。GNSS诊断状态至少包含`DISABLED`、`WAIT_ORIGIN`、`WAIT_SAMPLE`、`ACCEPTED`、`REJECTED`、`STALE`和`INVALID`。气压诊断的`WAIT_STATE_CATCHUP`是样本等待KF状态时间追上的正常pending状态，不表示拒绝或失败。

## 16. 采样驱动周期与离线重放

SilverStar 0.0.12不使用固定100 Hz定时器强行更新导航。IMU Device把完整加速度+角速度样本放入自有FIFO，System通过`get_next_sample()`按时间顺序排空；InsTask按真实`sample_timestamp_us`构造子区间。两子样机械化每两个区间输出一次惯性增量，KF预测对每个惯性增量执行一次。GNSS和气压只在出现新sequence时更新。

`System/User/system_user_config.h`集中配置：

- 设备请求输出频率；
- 机械化允许的最小/最大采样频率和时间容差；
- 辅助样本最大年龄；
- 日志分频和低频周期。

标称频率只用于配置、合法性检查和日志元数据。算法积分和电脑重放必须使用每条记录的真实时间戳。

飞行日志格式0.0保存两条重放路径：

1. `IMU_CORRECTED`保存实际进入INS的任务校准后机体系加速度/角速度，用于重新运行二子样机械化和任意融合算法；Calibration参数由独立`CALIBRATION_RESULT`记录恢复。当前正式任务默认不保存未校准IMU raw/native数据；
2. `INERTIAL_INCREMENT`、`GNSS_MEASUREMENT`和`BARO_MEASUREMENT`，用于跳过设备解码、任务Calibration和机械化，直接比较不同融合算法。

Pure INS和KF6在线结果同时记录以作为回归基线。电脑端应编译同一份Algorithm C源码，不另写语义可能漂移的Python版算法。

## 17. 气压量测单槽等待

EstimatorBus只保存最新气压快照，因此EstimatorTask必须把尚晚于当前KF状态时间的首个新气压样本复制到单槽pending。pending存在期间不得用总线后续快照覆盖，不得提前更新`last_baro_sequence`；每个惯性增量到达后重新比较状态时间，追上后对同一pending样本执行一次且仅一次1D更新。临时等待状态为`WAIT_STATE_CATCHUP`，不在每个IMU周期重复增加`skipped_count`。

只有`ACCEPTED`、`SOFTENED`、`REJECTED`，或已经确定不能使用的`STALE`、`INVALID`、`ORIGIN_NOT_READY`、`UNSUPPORTED`等终态才消费sequence并释放pending。该机制不做历史状态回放，但消除了“future sample先消费、随后被最新快照覆盖”造成的气压更新永久饥饿；气压更新成功后必须能约束KF的PZ。Pure INS路径不接受该KF回注。

## Algorithm configuration contract

Pure INS/KF6 实际参数、单位、P0/Q/R 转换与 decoder 1.2 边界见[算法参数契约](../../ALGORITHM_PARAMETERS.md)。默认值保留旧算法数值行为；公式、时序与融合策略不变。
