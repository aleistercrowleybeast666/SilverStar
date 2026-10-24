# 0.1.3 安装标定：离线 B0 / B2a 原型

Owner：`installation_calibration_B0_B2a`；日期：2026-10-18。
2026-10-19：已批准每面单事务自动分段，正式会话/样本契约在 `contracts/installation_calibration_v1.json`，共享实现由 GSHC `services/installation_calibration_*.py` 持有。本目录兼容入口及数值反例继续保留；最新软件接入说明见 `apps/GSHC/docs/INSTALLATION_CALIBRATION_BACKEND_20261019.md`。
后续获准的 B1 有界采集与 B2 会话/编解码离线原型见 [B1_B2_OFFLINE.md](B1_B2_OFFLINE.md)；下表保留 run04 初版数学原型的范围，新批次状态以该补充说明为准。
窗口/留出和完整 SSIC 的本轮收尾草案见 [CONTRACT_DRAFT.md](CONTRACT_DRAFT.md)，尚未接入生产或解除应用禁用。
本目录是独立实验代码，未注册为 SCG 插件、未接入 GSHC、维护串口、TF、SPI Flash 或飞行状态机。
所有结果仅为候选，`apply_allowed=False`，没有 Apply/Save 方法。B0 协议合同和 B2a 完整产品服务仍未完成。
总体边界见[安装标定设计](../../../../docs/internal/INSTALLATION_CALIBRATION_0_1_3_DESIGN_20261018.md)。

## 运行与文件

在仓库根执行（需要已有 NumPy、SciPy、pytest）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B apps/SCG/experiments/installation_calibration_0_1_3/verify.py --run run04
```

`run04` 若已存在，换一个未使用的短字母数字名称。runner 拒绝覆盖旧证据；只复制本目录的小型源文件，不复制仓库/工具链。每次保留完整日志、工具版本、命令、退出码、HEAD、实际实验源码快照/哈希、原始配对数据、案例指标及 owner/purpose/hash inventory。输出仅进入 `.work/dev013_installation_calibration_20261018/<run>/`，清理授权为 false。

| 文件 | 用途 |
|---|---|
| `prototype.py` | 不可变输入、回放快照、内参候选、AM 外参候选、多门禁、取消/计算进度、同面补采建议；无 I/O |
| `synthetic_cases.py` | 独立构造固定世界磁场下的真实刚体姿态，包括对称退化和多解反例 |
| `test_prototype.py` | 正常、故障、模型反例、回放与隔离测试 |
| `verify.py` / `pytest.ini` | 独立测试配置、240 秒单次运行超时及完整证据保存；不汇总为固件测试通过 |

纯数据 API：`Snapshot_Export(session, accel, mag, policy)` 返回 JSON 可编码对象；`Snapshot_Import(payload)` 重建自有不可变输入。随后调用 `session.Solve(accel, mag, policy, cancel=..., progress=...)`。`progress(done, total)` 仅表示多起点搜索完成数量，不表示采集/设备完成进度。`CandidateIsCurrent()` 对比原始记录、两套完整内参、坐标约定和质量策略的内容哈希。此 JSON 只是实验回放数据，不是新维护协议版本、SSLOG 控制格式或已提交标定对象。

## 数据及数学边界

每条 `RawPair` 保存 session/boot、两传感器的板卡/物理/Descriptor/instance/driver/model/config/frame 身份、epoch、32-bit 序号、64-bit 源及接收时间、时钟域、同步有效性/不确定度、质量标记、阶段、面、窗口、pose、训练/留出标签、软件内参前的物理量原始值，以及采集时的内参 ID/代次。单位固定为 m/s²、rad/s、µT。当前原型的接收时间也要求在声明的同一时钟域；真实 PC 收包时钟转换/丢包检测尚未实现。

本次求解所用 `Intrinsic` 则另外保存完整 bias、SPD matrix、ID、generation、单位和输出 frame。采集时内参的记录不会被重算覆盖。原型最多 4096 条配对记录，磁椭球助手接收 128–4096 个 XYZ 点。后者只是数学助手，未实现旋转阶段逐样本元数据档案；生产复用仍需采集层提供该档案，不能用本助手替代它。

独立实现参考 AM-Align 的数学约束，没有下载或复制第三方源码：

- [AM-Align 论文](https://construction-robots.github.io/papers/59.pdf)、[作者项目](https://github.com/JokerJohn/AM_Align)。
- 将已校准的静态比力和磁场归一化，拟合 `aᵢᵀ R_AM mᵢ = s`；未知常数 `s` 反映夹角，不把重力和磁场当成同向量 Wahba 对应。采用列向量、右手系、静止比力朝上；若使用相反重力符号，必须显式改约定。
- 磁椭球采用固定 SPD 内参规范；外参承担剩余正交旋转。静态六面助手仅求对角加速度 bias/scale 和静态 gyro bias，不能标定 gyro scale 或非正交轴。
- 左扰动雅可比为 `(R mᵢ) × aᵢ`，消去 `s` 后加权中心化；对它的三个奇异值检查局部激励。相同声明 pose 的多个窗口共享总权重，重复静态样本不制造新几何约束。
- 有界多起点非线性最小二乘（默认 72 个，测试通常 48/96 个；每个 `max_nfev=160`）只搜索候选。稳健损失之后仍使用普通 RMS/最大残差门禁；不以稳健权重隐藏坏数据。
- 训练数据决定候选顺序及多解判断，留出数据只验证固定候选、不参与选模或消除训练多解。补采后重新求解，并重新保留独立验证窗口。示例留出窗口与训练窗口姿态可相同，但样本不同；它不能验证新磁环境，也不能证明全局唯一。
- 未知 `R_GA` 时只输出 `R_AM`，不假装得到磁到陀螺旋转；显式提供有来源的 `R_GA` 才计算 `R_GM=R_GA R_AM`，来源仍只是声明。

## 门禁的真实状态

| 项目 | 已实现/已验证范围 | 未证明或未实现 |
|---|---|---|
| 元数据、单位、窗口、时间/序号 | 严格类型/范围、身份变化、boot/epoch、回退/重复、同步预算、质量标记、窗口混用拒绝 | 不从前向序号跳跃推断采样丢失；缺少源采样率和降采样契约，需采集层提供 gap 标记；不证明真实时钟同步 |
| 静态/磁环境 | 校正后模长、方差、gyro 范数、面方向、窗口数量检查 | 所有阈值 `PROVISIONAL_SYNTHETIC_ONLY`，没有硬件资格；稳定干扰可能不可识别 |
| 正常六面、噪声 | 已知真值的固定世界场姿态，候选精度及留出门禁 | 不能推广到所有六面动作或所有磁环境 |
| 对称退化 | 物理可实现的正反面对应，零残差仍由局部秩门禁拒绝 | 多起点结果不是代数全根枚举 |
| 多解/粗先验 | 六面两组精确解、各自局部满秩；粗先验仅诊断，多个训练解阻止候选通过 | `global_uniqueness=NOT_PROVEN_MULTISTART` 始终保留；未找到竞争解不等于唯一 |
| 低水平磁分量 | `sqrt(1-s²)`、局部奇异值、候选分离联合检查 | 指标取决于模型/内参正确，不能替代现场磁质量证据 |
| 异常/留出 | 模长不变的方向异常、仅留出异常、留出不得选模的反例 | 没有认证级异常检出率/误报率、统计置信区间 |
| 错轴 | 声明冲突拒绝；构造隐藏反射后 `-R F` 与 `-s` 仍满足约束的反例 | `coordinate_evidence=DECLARED_NOT_HARDWARE_VERIFIED`；数值残差无法检查所有轴错、符号错或加速度/gyro 轴错 |
| 同面补采 | 以 `1-(n·u_min)²` 排序面；示例在两个面保持贴面改朝向后恢复局部激励且得到候选 | 不要求用户知道转角，不保证一次/两个姿态足够；局部最弱方向建议不保证消除所有离散解 |
| 内参变化回放 | 从不变原始六面和旋转点重估不同系数，更新 generation、旧候选失效，再算 AM | 椭球仅代数拟合、基本覆盖/残差检查；不是成熟抗异常椭球工具，也无全量旋转档案服务 |
| 取消/容量/进度 | 搜索中取消、记录容量、起点/评估预算、纯数据计算进度 | 不是设备端 cancel ACK/终止确认，不是硬实时耗时保证 |
| gyro 动态标定 | 显式 `NOT_IMPLEMENTED`；动态样本拒绝进入静态求解 | 不估计 gyro scale/非正交轴/动态积分误差 |
| 协议、会话生命周期、TF、UI | 仅沿用设计边界；不改变现有协议 | codec/golden、幂等操作、断线/重启恢复、TF 互斥与提交、生产 UI/worker 均未实现 |

### 错误含义

`REJECTED` 表示输入/绑定不可信，先修复数据来源；`NEED_SAMPLES` 表示已计算但质量不足，结合 reasons 决定重新采集或补采；`NUMERICAL_FAILURE` 表示预算内没有收敛解或数值失败；`CANCELLED` 不产生可应用结果。`CANDIDATE_ONLY` 仅表示本实验数值门禁通过。

常见 reasons：`TRAIN` / `HOLDOUT` 为对应残差失败；`LOCAL_EXCITATION` 为局部激励不足；`HORIZONTAL_FIELD` 为水平磁分量不足；`MULTIPLE_SOLUTIONS` 为发现相隔明显但训练拟合同样好的解；`WINDOW_QUALITY` 为至少一个窗口未通过静态/磁质量；`WRONG_DEVICE_OR_CONFIG` 为身份不匹配；`TIME_OR_SEQUENCE_DISCONTINUITY` 为时间或序号不连续；`UNQUALIFIED_SYNC_OR_QUALITY` 为同步或来源质量未满足声明预算。原始诊断码保留；产品层仍需本地化及采集侧错误映射。

## 证据与后续接入

本次各轮完整结果见[证据汇总](../../../../.work/dev013_installation_calibration_20261018/RESULTS.md)。失败轮次和原始快照保留，不能用后一次成功覆盖。数据与代码都是合成/实验输入，不能作为 MCU、TF、磁环境或飞行验收。

后续先冻结坐标 owner 与 TF owner 的身份/变换/代次契约，再冻结维护串口安装消息、配对时间语义、源质量和容量；将已验证的纯算法迁入 GSHC 服务需重新做集成验收。真实采集/B1、生产 B2b/B3、生成 power10/Host/analyzer/ARM/链接/栈验证均未在本任务执行，也不因本实验 PASS 获得任何完成或合规声明。
