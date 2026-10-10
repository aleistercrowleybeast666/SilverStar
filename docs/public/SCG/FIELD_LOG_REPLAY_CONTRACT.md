# 全速输入与导航重放契约

Record 的正式字段、尺寸、版本由 SSLOG 插件的 `sslog_schema.json` 定义，
生成工程的 `.ssdecoder` 同时携带该 Catalog、实际参数和 Project Semantics。
本轮保持平台版本、文件容器及 AIR/维护协议不变；改变 payload 的 Record 升级自己的版本。
具体验收数值、hash、资源占用与测试结果仅见根目录 `VALIDATION.md`。

## 输入、执行与输出

正式退出 SAMPLE、RAW_SENSOR、IMU_NATIVE、HW_QUAT_NATIVE；这些 ID 留空，不复用。
KF6 仅运行公共惯性前端和 KF6 导航，不计算或写入 Pure INS 旁路。
选择 Pure INS 时仍运行、记录该算法。ESTIMATOR 自身提供 KF6 的 q、p、v、线加速度，
无需另一个导航算法提供姿态显示。

IMU_CORRECTED、INERTIAL_INCREMENT、GNSS_NATIVE、GNSS_MEASUREMENT、BARO_NATIVE、
BARO_MEASUREMENT、ESTIMATOR_STEP、GNSS_RECOVERY 采用 EVERY；配置器与固件拒绝
对 EVERY 设置 decimation 或 period。corrected IMU 不得再次 calibration。
Barometer observation 保留 altitude、pressure 及有效性、health、来源身份，删除重复整数表达。
GNSS observation 保留四组有效性及拒绝原因，不能从 aggregate position_usable 推断 EN 可用性。

导航/简要诊断默认 25 Hz、完整 P 默认 5 Hz；首状态、epoch reset、生命周期变化、
reanchor 和 covariance inflation 额外写入关键状态/P。POWER 默认 10 Hz，
TELEMETRY_DIAG、STATS、HEALTH 默认 1 Hz。Required bootstrap 与 admission 规则继续生效。
保留的记录默认启用，实际无 producer/物理输出的记录仍按能力解析关闭。

## 执行顺序

不能用文件顺序或 receive timestamp 对齐到下一个 increment 猜执行顺序。
同一 replay_epoch 中按下列 operation sequence 合并：

- ESTIMATOR_STEP：引用 INERTIAL_INCREMENT.sequence，携带实际 prediction 结果、
  attitude 结果、present timestamp 与 replay generation。
- GNSS_MEASUREMENT：receive tracking、position insert、velocity insert 各有操作序号。
  序号 0 表示未执行；位置/速度操作序号相等表示一次 combined insert。
  两组各有 resolved measurement timestamp，receive tracker 每 packet 只运行一次。
- BARO_MEASUREMENT：引用 observation 的 sample/receive/sequence，包含实际 altitude、R、
  measurement/present time、操作序号、epoch、generation、更新结果、innovation、NIS。
- ESTIMATOR snapshot 的 operation_sequence 表示该状态已包含的最后一次执行操作。

ReplayResult 的数值定义取自 `navigation_kf_replay.h`，不能把 HISTORY_MISS 等失败
当成 current-state update。history 按 measurement time 排序，同时间按 position、velocity、
barometer、source、sequence 排序；checkpoint 是该时刻 measurement 之前的状态。
必须恢复完整 KF 内部状态而非仅 x/P。姿态只受 IMU 传播，不被平移 KF measurement 回滚。

## 时间同步与重放

原有 SystemTime 负责 MCU/mission 时间转换、计数扩展以及 measurement time 的统一解析。
当前 JY901B 没有可信 native sample epoch，使用 receive time 减 configured delay。
未来 trusted native time 经原 time-sync 转换后直接使用，不再次减 delay。
NEO-M9N 的 navigation solution 当前仍以 MCU 接收 epoch 进入该路径；接收机 iTOW/时间信息
不是已经完成历史滤波更新的证明。不得构造第二套并行时钟。

time synchronization 得到时间坐标；fixed-lag 引擎执行历史 checkpoint 恢复、历史 measurement
更新、后续事件重放并回到 present。GNSS 与 Barometer 共用同一引擎，零延迟保留 fast path。

## 四组恢复与着陆

Pos EN、Pos U、Vel EN、Vel U 独立 quality/update/NIS/recovery。
GNSS_RECOVERY 提供接收质量、outage、consistency、inflation、reanchor 计数/原因。
通信无新 epoch、收到低质量 epoch、滤波 NIS 拒绝是三种不同情况。
reanchor 必须有真实 availability outage、连续一致返回、最小时长/样本数，以及耗尽的
正常膨胀恢复；历史 reanchor 只重置受影响组的 state/variance，清零该组 cross covariance，
检查 SPD 后重放。详见 `KF6_OUTAGE_RECOVERY.md`。

LANDING_DIAGNOSTIC 只在 candidate start/reset/complete 时写入；包括 reset reason、
elapsed、有效时间覆盖、静止比例、最长不良时间、barometer slope/span/coverage。
物理阈值保持不变，短噪声按时间容错；snapshot 获取完成后才读取 evaluation time。

## 验证入口

`tests/joint_navigation_support.py` 从实际生成工程编译真实 C frontend、KF6、replay 与 codec，
由 `tests/fixtures/joint_navigation_golden.c` 输出数值日志。它与生成 decoder 成对提供给 FLP。
App dispatch 的独立 timing tests 覆盖不同 position/velocity/barometer delay、trusted time
不重复补偿，以及错误 current-state 更新的负对照。Host storage stress 使用当前 GNSS 速率
与全速输入，测量真实 codec/FatFs/diskio 路径上的抖动、队列高水位和有据可查的过载损失。
合成验证不能代替硬件 SD 延迟或真实外场测试，也不自动赋予 FLP EXACT。
