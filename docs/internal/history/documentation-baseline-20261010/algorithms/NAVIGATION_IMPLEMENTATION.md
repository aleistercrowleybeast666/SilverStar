# 四种导航算法：数学与当前实现

本文以本次收尾的源码为准，面向理解、配置和离线分析；不修改算法数学。源码身份和实际执行的验收范围见[收尾报告](../NIGHTLY_SOFTWARE_CLOSEOUT_20261008.md)。历史规范如[导航规范](../FCCG/platform/details/NAVIGATION_AND_ESTIMATION.md)保留其原版本，不能把其中仅列 KF6 的早期枚举当成当前选项全集。

## 1. 坐标、单位与共同输入

导航系为局部 ENU：E 东、N 北、U 上；Body 是经过安装方向映射后的机体系。姿态为 Hamilton 四元数 `q_nb=[w,x,y,z]`，将 Body 向量旋转到 ENU：`u_n = R(q_nb) u_b`。`q ⊗ δq_b` 是右乘 Body 旋转增量。角速度 rad/s、角增量 rad、比力 m/s²、速度 m/s、位置 m；时间计算用秒，记录与调度用 MCU 单调微秒。ENU yaw 0° 指 Body +X 水平投影向东，不能当成罗盘的北向 0°。

加速度计交付的是比力 `f_b`，静止且 Body 与 ENU 对齐时向上分量约为 +g。导航线加速度为 `R f_b + [0,0,-g]ᵀ`。经纬度/高度由冻结 GNSS 原点转到局部 ENU，GNSS 原点有效性、位置/速度各组有效性分别判定；没有 fix 不能把原点或量测补成有效。

Calibration 先产生实际校正/身份，Alignment 从静止窗口估计倾斜及已知 yaw、磁 TRIAD 或合法硬件四元数窗口。`Calibration READY → Alignment READY → START` 是实际状态依赖，接受 ACK 不等于 READY。START 采用冻结 `INITIAL_STATE.q_nb` 及初速度/原点；START 后软件传播姿态，硬件四元数只作诊断。[校准与对准规范](../FCCG/platform/details/CALIBRATION_AND_ALIGNMENT.md)给出具体窗口和质量条件。

Pure INS 始终保留独立对照状态；融合支路维护自己的状态，不能把估计修正写回 Pure INS。选“无估计器”不是停止惯导。

## 2. Pure INS：二子样圆锥/划桨机械化

相邻三帧构成两个真实间隔 `h₁,h₂`。每段采用梯形积分：

$$a_i=\tfrac12(\omega_{i-1}+\omega_i)h_i,\quad
b_i=\tfrac12(f_{i-1}+f_i)h_i.$$

这里 `a_i` 是角增量，`b_i` 是比力速度增量，不是线加速度。二子样补偿为：

$$\Delta\theta_b=a_1+a_2+\tfrac23(a_1\times a_2),$$
$$\Delta v_b=b_1+b_2+\tfrac12[(a_1+a_2)\times(b_1+b_2)]
 +\tfrac23(a_1\times b_2+b_1\times a_2).$$

第二式的 1/2 项补偿区间内旋转，2/3 项补偿角/比力交叉变化。它不是对 Euler 角做平滑。设 `h=h₁+h₂`，项目在区间起始姿态旋转补偿后的增量：

$$\Delta v_n=R(q_k)\Delta v_b+[0,0,-gh]^T,$$
$$v_{k+1}=v_k+\Delta v_n,\quad
p_{k+1}=p_k+\tfrac12(v_k+v_{k+1})h,$$
$$q_{k+1}=\operatorname{normalize}\{q_k\otimes
[\cos(\|\Delta\theta_b\|/2),\;
\frac{\sin(\|\Delta\theta_b\|/2)}{\|\Delta\theta_b\|}\Delta\theta_b]\}.$$

小角度按实现的极限展开处理。这里是局部平地、常重力模型；不是完整地球旋转/曲率/运输角速度的导航方程。高度/速度积分和姿态漂移不能由归一化消除，缺少水平辅助时必然存在水平漂移。

固件支持配置的一/二间隔聚合，但当前 FLP Corrected IMU 的 Pure INS/KF6 重放要求二间隔及未抽取完整输入；合法一间隔固件日志可看 Recorded 数据，不能在离线端偷偷两两配对。采样缺口、时间不连续和健康标志有显式诊断，不能用标称频率补造样本。

源码：

- [固件机械化](../../apps/SCG/plugins/builtin/silverstar_algorithm_ins_coning2_sculling2/payload/Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c)：`Ins_ComputeSubIntervalIncrement` 及补偿、状态提交。
- [FLP 机械化](../../apps/FLP/src/silverstar_flp/plugins/algorithms/pure_ins/mechanization.py)：`InertialIncrement_BuildFromCorrectedImu`、`Mechanization_Run`；[数学工具](../../apps/FLP/src/silverstar_flp/core/math.py)：四元数右乘、归一化与旋转。
- [Pure INS 插件](../../apps/FLP/src/silverstar_flp/plugins/algorithms/pure_ins/plugin.py)：INITIAL_STATE、记录边界、参数来源与可用性。

## 3. SF6 revision 2：固定增益的六状态融合

SF6 当前顺序与 KF6 不同：

$$x=[v_E,v_N,v_U,p_E,p_N,p_U]^T.$$

姿态与 ENU 增量由独立 INS 支路产生，预测仍用上一节速度/位置方程。量测被接纳后只修改对应轴：

$$x_j^+=x_j^-+k_j(z_j-x_j^-),\quad 0\le k_j\le1.$$

这是固定增益，不计算 `P`、`Q`、`R`、Kalman gain 或 NIS，也没有概率置信区间。`k=0` 不修正该轴，`k=1` 拉到观测（仍校验有限值）；中间值是新观测与当前预测的加权组合。六个默认 0.2 是工程默认值，不能称为最优或精度结论。

五组量测是 GNSS 水平位置、GNSS 高度、GNSS 水平速度、GNSS 垂直速度、气压相对高度。GNSS 高度和气压共用 `pU` 增益；位置修正不注入速度，姿态不受量测修正，SF6 不用磁量测。物理质量、源身份、有效分组仍由 backend 管理。

revision 2 把延迟观测修正到**当前预测状态**，没有历史环、回滚和延迟参数。可信采样时刻用于年龄/每组顺序检查，不可信源使用 receive 时刻；未来、早于初始化、超过 500 ms、重复/逆序输入拒绝。每组 sample/receive 和 uint32 半范围序列推进均要合法。预测 dt 要在 `(0,0.02]`，微秒舍入后的区间必须连续。

常速情况下，延迟 `τ` 的位置观测相对当前真值落后约 `vτ`，单次额外修正偏差约 `-k vτ`；常加速度下速度类似 `-k aτ`。这是模型误差解释，不是实测准确度，也不能据此新增统一频率禁令。无 GNSS 时继续惯性传播及可用气压修正；这些不会约束水平漂移。

候选状态和接纳 tracker 在有限值检查成功后一起提交，数值失败不发布部分成功；坏外部量测走普通错误路径，内部状态损坏沿既有 fail-stop。历史 revision 1 的 SF6 使用固定滞后重放，FLP 按精确 decoder 的 revision/component/state-record 分流，旧日志保持原语义。Explicit Offline 总是当前 revision 2 并标出语义变化；不能把它作为旧日志的 Recorded 配置。

源码与细节：

- [SF6 固件核心](../../apps/SCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload/Algorithm/Estimator/SF6/Src/navigation_sf6.c)、[backend](../../apps/SCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload/Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c)。
- [FLP 当前核心](../../apps/FLP/src/silverstar_flp/plugins/algorithms/sf6/current_state.py)：`Predict`、`Update`；[版本路由](../../apps/FLP/src/silverstar_flp/plugins/algorithms/sf6/plugin.py)：`PluginForDataset_Get`、`Parameters_Resolve`、`run`。
- [revision 2 契约](../FCCG/SF6_CURRENT_STATE.md)、[FLP 历史/现行分界](../FLP/SF6_Replay.md)。

## 4. KF6：六维位置速度 Kalman 滤波

$$x=[p_E,p_N,p_U,v_E,v_N,v_U]^T,\quad
F(h)=\begin{bmatrix}I&hI\\0&I\end{bmatrix},\quad
B(h)=\begin{bmatrix}\tfrac12hI\\I\end{bmatrix}.$$
$$x^-=Fx+B\Delta v_n,\qquad P^-=FPF^T+Q.$$

姿态仍是软件 INS 状态，KF6 不估计姿态或 IMU 偏置。量测从 x 选出水平/垂直位置、水平/垂直速度或 pU 气压高度；各组独立更新，不能对同一 GNSS 再附加一次三维更新。

一般线性更新推导从 `r=z-Hx⁻` 开始。若预测误差协方差为 P、观测方差为 R 且二者独立，则残差协方差 `S=HPHᵀ+R`；最小均方线性增益 `K=PHᵀS⁻¹`，状态 `x⁺=x⁻+Kr`。项目用 Joseph 形式保留数值稳定性：

$$P^+=(I-KH)P^-(I-KH)^T+KRK^T.$$

`NIS=rᵀS⁻¹r` 用对应 1D/2D/3D 参数门限。高于 hard 拒绝；介于 soft/hard 把 R 放大 `min(max_scale,NIS/soft)` 后重算增益；物理非法和数值错误另有结果码。输入 R 是方差（标准差必须平方），拒绝不能算作成功修正。

**过程模型版本必须保留。** 历史 revision 1 每轴用 `Var(Δv)=(σ_a h)²`、`G=[h/2,1]ᵀ`，`Q=G Var(Δv)Gᵀ`。当前 revision 2 为使同一真实惯性区间分段时的噪声累计一致，保存原区间长 `T`，令 `d=σ_a² T`：

$$Q_{axis}(h;T)=d\begin{bmatrix}h^3/3&h^2/2\\h^2/2&h\end{bmatrix},\quad h\le T.$$

完整区间 `h=T`；拆分的各段沿用 T，不能把每段 h 当新 T。它来自该区间白加速度模型的积分 `∫[t,1]ᵀ d [t,1]dt`，不是通用连续噪声密度参数的直接替换。源码身份 `process_model_revision` 决定实际行为，不能把教科书 Q 默认套给所有旧日志。

初始化位置在冻结局部原点为零，初速度来自 INITIAL_STATE，P0 由实际 estimator profile/合格精度生成；GNSS 的 hAcc/vAcc/sAcc 经 scale 和 floor，再形成方差。只有确实可观测的分量能调整初始方差。气压参考与 sigma 来自实际配置；参数单位和 Recorded/What-if 边界见[实际参数](../FCCG/ALGORITHM_PARAMETERS.md)。

KF6 的量测时间：可信 MCU sample 原样使用，否则 `receive - delay`，拒绝下溢/未来。固定滞后引擎保存 144 个惯性增量、48 GNSS、160 气压事件、8 个检查点（每18预测），接纳窗600 ms；源码规定工作预算为 `144+2*(48+160)`。测量落在区间内部时按时间比例拆导航增量；恢复完整 KF 状态/诊断/恢复 tracker 后排序更新及重传播，成功才提交。失败不会悄悄改为当前状态更新。

GNSS outage/reacquire、协方差膨胀及有条件重新锚定是本项目附加的状态机，不是基本 Kalman 公式；真实 receive 侧证据一次采集，历史重放不能伪造新的掉线/恢复，也不重发任务副作用。持续拒绝和重获条件见[掉线恢复](../FCCG/KF6_OUTAGE_RECOVERY.md)、[持续拒绝审查](../FCCG/KF6_CONTINUOUS_GNSS_REJECTION_REVIEW_20261003.md)。

源码：

- [固件 KF6 核心](../../apps/SCG/plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Src/navigation_kf.c)：`NavigationKf_PredictNoise`、`NavigationKf_PredictInterval` 及分组更新；[重放](../../apps/SCG/plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Src/navigation_kf_replay.c)。
- [FLP filter](../../apps/FLP/src/silverstar_flp/plugins/algorithms/kf6/filter.py)：`Kf6_Predict`、`_Vector_Update`；[fixed_lag](../../apps/FLP/src/silverstar_flp/plugins/algorithms/kf6/fixed_lag.py)、[插件参数/调度](../../apps/FLP/src/silverstar_flp/plugins/algorithms/kf6/plugin.py)。[固定滞后契约](../FCCG/KF6_FIXED_LAG_REPLAY.md)。

## 5. ESKF15：右乘姿态误差与残余偏置

名义状态是 `(p,v,q,b_g,b_a)`，共16个存储数但姿态只有3自由度；误差状态15维：

$$\delta x=[\delta p,\delta v,\delta\theta,\delta b_g,\delta b_a]^T,
\qquad q_{true}=q\otimes\operatorname{Exp}(\delta\theta).$$

这是右乘 Body 小角误差，不能与左乘导航系误差的符号混用。`b_g`、`b_a` 是外部校准后残余陀螺/加速度偏置，单位 rad/s 和 m/s²。

传播先从校准后的 Body 输入减残余偏置，再应用二子样圆锥/划桨，用起始 `R(q)` 旋转一次，加重力并积分 p/v；q 右乘 Exp(Δθ)。ESKF 必须保留 Body 输入，不能拿 Pure INS 已旋转的 ENU 增量再做姿态反馈或重复补偿。

令 `ω=ω_m-b_g`、`f=f_m-b_a`，`[u]×v=u×v`。线性化非零块为：

$$F_{p,v}=I,\quad F_{v,\theta}=-R[f]_\times,\quad F_{v,b_a}=-R,$$
$$F_{\theta,\theta}=-[\omega]_\times,\quad F_{\theta,b_g}=-I.$$

这些符号可从右误差直接得到：`R_true≈R(I+[δθ]×)`，所以 `δ(Rf)=R(δθ×f)=-R[f]×δθ`；减去残余加速度偏置则增加 `-Rδb_a`。Body 误差随名义角速度转动产生 `-ω×δθ`，陀螺偏置误差产生 `-δb_g`。位置误差导数是速度误差。这里忽略地球旋转/运输角速度，与本项目局部平地名义传播一致，不能从完整地球模型照抄附加 F 块。

采用 `Φ≈I+Fh+½F²h²`。噪声为连续标准差密度/随机游走，必须平方后进入 W。[当前参数目录](../../apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/plugin.json)中 `gyro_noise_density` 为 rad/s/√Hz、`accel_noise_density` 为 m/s²/√Hz，`gyro_bias_rw` 为 rad/s²/√Hz、`accel_bias_rw` 为 m/s³/√Hz；不要把采样标准差直接当这些密度。固件用各轴相同的加速度密度，在导航坐标的该块仍为 `σ_a² I`；FLP 通过 R 映射同一各向同性噪声，理论等价不等于 float32/float64 逐位相同。项目 Q 积分使用一阶噪声转移 `I+Ft`（确定性 Φ 另保留 F²）：

$$Q_d=hW+\tfrac12h^2(FW+WF^T)+\tfrac13h^3FWF^T.$$

FLP 使用正权 Simpson 节点 0、1/2、1 对同一二次被积式求和。固件线性化取两个半段等权均值；FLP `Prediction_ApplyPair` 用时长加权均值，实际 BodyStep 按整数区间中点重建半段。时间舍入与精度差异保留在 fidelity 边界，不能由上述公式宣称精确实机重放。

带 Body 杆臂 `l` 的 GNSS 预测为：

$$\hat z_p=p+Rl,\qquad \hat z_v=v+R[(\omega_m-b_g)\times l].$$

相应 H 的姿态块分别是 `-R[l]×` 和 `-R[(ω_m-b_g)×l]×`，速度的陀螺偏置块是 `R[l]×`。按选定水平/垂直轴提取；气压使用项目定义的相对高度量测。量测应用与 KF 类似的创新、Cholesky/NIS、R软加权及 Joseph 协方差更新，但还要检查姿态/偏置修正是否超模型范围。

得到 δx 后注入 `p+=δp,v+=δv,q←q⊗Exp(δθ),b_g+=δb_g,b_a+=δb_a`，误差均值归零。不能只更新 q 而不重置 P：

$$P\leftarrow J P_{Joseph}J^T,\quad J_{\theta\theta}=J_r(\delta\theta),$$
$$J_r(a)=I-\frac{1-\cos\alpha}{\alpha^2}[a]_\times
+\frac{\alpha-\sin\alpha}{\alpha^3}[a]_\times^2,\quad\alpha=\|a\|.$$

注入后，新误差满足 `Exp(δθ_new)=Exp(-δθ_hat)Exp(δθ_old)`；在已估计的 `δθ_hat` 附近线性化得到右 Jacobian。其他误差分量在该 reset 映射中保持单位块，但与姿态的交叉协方差也必须随完整 `JPJᵀ` 一起变换，不能只修正姿态对角块。

小角时 `J_r≈I-½[a]×+⅙[a]×²`。这是本项目的右误差 reset；不要套左误差的相反一阶符号。候选状态/P 通过有限值、对称/正定及模型范围检查才发布；数值错误或模型不匹配不会报告已接受。现有源码上限为 dt 0.02 s、姿态注入范数 0.35 rad、残余陀螺偏置范数 1 rad/s、残余加速度偏置范数 5 m/s²；这是模型有效性门限，不是新增设备禁选或准确度规格。质量 flags 的 `0x05` 位使传播噪声倍率为 4，否则为 1；不能把质量降级当作正常高可信输入。具体 NIS soft/hard、噪声和初始标准差随实际 profile 记录，见[参数说明](../FCCG/ALGORITHM_PARAMETERS.md)及 backend。

延迟重放保留192个 Body 输入、208量测、600 ms窗口、最大608步；恢复历史名义状态/P后重新积分 Body 半段，因为偏置/姿态修正会影响以后的导航增量。源/校准 generation、真实时间连续性和容量都是合同，不能跨重置 epoch。精确记录配置初始化要求 `ESKF15_INITIAL_STATE`、完整初始 P 快照、`ESKF15_BODY_INPUT` 及身份一致；缺证据拒绝。其他模式的 INITIAL_STATE/默认 P 明确是离线初始化。

源码：

- [固件 ESKF 核心](../../apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15/Src/navigation_eskf.c)：`Eskf_BodyIntegrate`、`Eskf_Linearize`、`Eskf_NoiseAdd`、`Eskf_ResetJacobianBuild`、`NavigationEskf_Update`；[重放](../../apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15/Src/navigation_eskf_replay.c)与[backend](../../apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c)。
- [FLP filter](../../apps/FLP/src/silverstar_flp/plugins/algorithms/eskf15/filter.py)：`Dynamics_Jacobian`、`Prediction_ApplyPair`、`Measurement_Model`、`Measurement_Apply`、`Rotation_RightJacobian`；[Body 输入](../../apps/FLP/src/silverstar_flp/plugins/algorithms/eskf15/inputs.py)、[重放](../../apps/FLP/src/silverstar_flp/plugins/algorithms/eskf15/replay.py)、[初始化和参数](../../apps/FLP/src/silverstar_flp/plugins/algorithms/eskf15/plugin.py)。

## 6. 调度、记录与结论边界

设备采样、驱动新帧、惯性总线、EstimatorTask 提交和日志抽取不是同一频率。通道保留各自真实 timestamp；不能给低频 GNSS 重复填表来伪造高频观测。任务/ISR ownership 和固定队列见[运行安全](../FCCG/platform/details/RUNTIME_SAFETY.md)与[架构](../FCCG/ARCHITECTURE.md)。本章不新增限频、400 Hz/BMI088 或 JY901B 气压禁选政策，也不改变导航队列/栈。

常见失效应区分：物理无效/无 fix、超时/重复/缺历史、数值/模型失败、输入缺口/队列损失、身份不匹配。无量测通常继续惯性传播并显示降级；不等于准确度或 READY 自动恢复。重放不可用要显示原因，不用默认值伪造 Recorded，不把丢样掩盖成成功输出。SF6 无概率诊断；KF/ESKF 的 NIS、P 也不是定位真值。

Pure INS/KF6 当前没有 `exact_validation_reference`，SF6 当前路径也报告 **APPROXIMATE**；缺条件时为 UNAVAILABLE。ESKF15 默认 APPROXIMATE，但 Recorded Configuration 的完整 Body 输入、初始化和无运行失败条件满足后，还会调用 [RecordedParity_Verify](../../apps/FLP/src/silverstar_flp/plugins/algorithms/eskf15/verification.py)。它核对记录中的时间、有效性、状态/P及更新诊断；连续值绝对容差 2e-4、相对容差 3e-4，接纳/结果码精确比较，CRC/序号/截尾问题阻断通过。周期完整 P 在精确 decoder 中显式关闭且没有分片时，交叉协方差标成 unavailable，不能声称已比较。通过后本项目接口可返回 EXACT/FAITHFUL；这是记录量的受限一致性，不是位级相同、完整内部路径或实机资格证明。

Host 数学/短样例、当前 GUI 回归、历史 ARM 构建、真实板测分别记载。F407/ESKF15 实际运行失败未解决，H7 当前没有生成支持，F103/NRF 未实物验证。没有新的 MCU WCET、完整栈证明或飞行资格结论。
