# KF6 fixed-lag replay

本契约仅适用于 FCCG 拥有并生成的 KF6 固件。FLP、GSHC 和参考固件未参与修改。
精确验证结果、内存和栈快照集中在根目录 `VALIDATION.md`。

## 现有时间同步与 Fixed-Lag Replay

原有时间链有以下职责：

| 层 | 当前实现与时间含义 |
|---|---|
| Platform | `platform_time_stm32f4.c` 使用已有 1 MHz 定时器、HAL tick、待处理中断补偿和 32 位毫秒 tick 扩展，提供单调 64 位 MCU 微秒轴。 |
| System Time | `system_time.c` 转发单调时间，管理任务时间原点和 UTC 映射快照；UTC 映射需要调用方提供对应关系，不自动估计时钟偏移。 |
| JY901B provider | `IMU_OnFrameDecoded` 在解析各类帧时调用 `PlatformTime_Us()`。Pressure/Height 帧的 `PressureTimestampUs` 是接收解析时间，不是可信原生采样 epoch。 |
| JY901B adapter | Barometer 的 sample 与 receive timestamp 均沿用 PressureTimestampUs。新可信标记默认为 false。 |
| NEO-M9N provider | NAV-PVT 提取 iTOW；`lastUpdate_us` 是解析时的 MCU 时间。当前没有 iTOW → MCU sample epoch 的偏移求解或映射。 |
| NEO-M9N adapter | GNSS sample 与 receive timestamp 均使用 lastUpdate_us；GetTime 单独提供 iTOW，不把它当 MCU 微秒。新可信标记默认为 false。 |
| Sensor hub | 现有惯性 TimeSyncPolicy 枚举包括多种名称，但当前运行实现只允许 PASSTHROUGH，保留 sample/receive 时间，不回滚估计器。Barometer 快照转发新增可信标记。 |
| Estimator | 新增统一量测时间解析，在 MCU 轴上得到 measurement timestamp；之后由一个 KF history 恢复历史状态、更新、重传播。 |
| SSLOG | 当前 native 和 measurement records 保留 sample/receive 时间和量测值；decoder 实际参数包含三种 delay。完整 replay 诊断输出已由联合修改需求授权，编码和 FLP 对接仍待实现。 |

**Time Synchronization != Delayed Measurement Replay。** 原有机制解决 MCU 单调时间、
底层计数器回绕、任务/UTC 参照及样本时间传递；没有历史 x/P 恢复、OOSM 排序或重传播。
本轮没有复制第二套 clock conversion、offset 或 wrap 系统。

`SystemTime_MeasurementTimestampResolve` 位于原有 System Time 模块：

- provider 已通过现有 time sync 转换到 MCU 轴、且明确标记可信时，直接使用 sample timestamp；
- 否则使用 `receive_timestamp - configured_delay`；
- 校验零时间、下溢、未来 native epoch，不静默修正；可信时间绝不再次减 configured delay；
- JY901B 当前使用后一条；iTOW 保留在现有 provider/GetTime 接口，不假装已有映射。

得到历史时间仍必须进入真正的 replay；只改时间戳后调用当前 x/P update 是错误实现，
Host 测试保留这种负面对照。

## 历史状态与事件

`navigation_kf_replay.[ch]` 由 KF6 插件拥有。`NavigationReplayContext` 存储有序 aiding
events、接收证据 tracker、工作上下文和诊断；`NavigationReplayStorage` 存储固定 IMU
环和检查点，可单独布置到 CPU CCM。EstimatorTask 是唯一所有者。

- 144 个 IMU 条目，包含起止 MCU 时间、原 dt 和已经转换到导航坐标系的 delta velocity；
- 48 个 GNSS 条目和 160 个紧凑 Barometer 条目，共用一张有序事件索引；GNSS 条目保存
  measurement/receive time、epoch、source/sequence、量测/R、有效分组、维度及不可变的
  接收侧证据。高频 Barometer 只保存其实际使用的时间、身份、高度与 R，不浪费 GNSS 字段；
- 8 个完整 `NavigationKfContext` 检查点，每 18 个预测保存一次；包含 x、P、参数、
  NIS/创新诊断、接受/拒绝计数、恢复状态及其 generation，不只保存 x/P；
- 固定 600 ms 接纳窗口；按真实时间淘汰，保留窗口边界之前最近的检查点。
  采样率超出静态容量时显式 overflow，不通过提前淘汰偷偷缩短窗口；
- 最大工作预算为 `144 + 2*(48+160)` 次预测分段/辅助更新。达到上限、数值错误或不连续时间
  会停止该 epoch，保留调用前的 current state，不降级成 current-state update。

默认以 200 Hz IMU、25 Hz GNSS 和 200 Hz Barometer 使用。550 ms 配置上限给 600 ms 历史预留 50 ms
调度余量；实际 START 后尚未积累的历史仍拒绝并计数，不保证窗口未建立时的延迟更新。

## 更新流程与确定性

1. 在真实接收侧校验 source/sample、序列、质量、坐标转换及 R；生成接收证据。
2. 找到 measurement time 之前或边界上的最近检查点。检查点位于该 IMU boundary
   预测之后、该边界 aiding updates 之前。
3. 恢复完整 KF 上下文，插入事件，按 measurement time、GNSS position、GNSS velocity、
   Barometer、source、sequence 排序。相同时间的 GNSS position/velocity 作为组合事件时，
   保留旧顺序：两个 update 完成后再处理各组恢复结果。
4. 重放后续 IMU 与 aiding events，并重建受影响的检查点；成功后才替换 current state。
5. 同一 GNSS 包的分离延迟先插入较旧分量，再插入较新分量，避免本包后续 rewind
   使先取得的结果过时。

量测位于 IMU 区间内时，导航 delta velocity 按区间时长比例拆分，使用原 KF predict
公式在两段执行。其离散假设是该区间内导航增量均匀分配；Q 的公式、sigma、P0、NIS
均未改动。准时参考也使用相同事件边界分段，不能拿未分段的过程噪声累计冒充参考。
历史保存导航系增量，因此不重复姿态传播；姿态、冻结原点等独立上游状态不由 KF
measurement update 反向影响。

全部 delay 为零、provider 未给可信历史 epoch 时，在原当前 IMU boundary 执行 fast
path，事件仍进入历史供以后 replay 使用。严格的零延迟等价性以**相同实际参数、R 和
输入事件**为前提；新默认 baro=2.5、vertical scale=1.75 自然不同于旧默认输出。
显式可信历史 epoch 即使配置 delay=0 也必须 rewind，不能丢弃其时间意义。

## GNSS true-outage 与副作用

原 `NavigationKf_GnssEpochTrack` 只在每个实际接收包上执行一次，输入真实 receive
time。现有 outage 门限、一致性公式、正常 gate 与协方差膨胀公式保留。
四组独立 validity 进入历史；连续一致时长和 generation 随不可变证据保存。
达到膨胀上限后的 controlled re-anchor 条件与协方差规则见
[恢复契约](KF6_OUTAGE_RECOVERY.md)。这属于本轮有意新增的算法行为，
不再宣称与之前只含 inflation 的恢复实现逐位相同。
重放只应用该证据到相关 position/velocity 分组，不重新用回拨后的 measurement time
推断掉线。连续接收不会因 velocity delay=270 ms 被判为失联。

引擎不调用日志、遥测、Flight/Mission、transport、告警或接收计数 API。EstimatorTask
在真实到达路径上只发布一次结果，replay 内部 KF 计数随 checkpoint 恢复后重算。
Mission 初始化、START rollback、Abort 清空历史并递增 epoch，旧量测不能跨原点/模型
重置更新新估计器。参数发生变化而未建立新 epoch 时拒绝更新。

## 参数与资源边界

三种 delay 是 KF6 advanced 实际参数，可独立设置；Barometer 非零 delay 使用同一
引擎。当前 Barometer R 为 configured sigma²，JY901B 1.5 m 建议值不进入 R，也不
伪装为 native variance。旧工程显式值保持不变，缺失字段的兼容语义见
[算法参数契约](ALGORITHM_PARAMETERS.md)。

历史不使用 heap、递归或 DMA buffer。性能记录使用已有 `SystemTime_GetMonotonicUs`
测量插入/回放路径的 MCU 微秒耗时，保存 last/max、replay count、last/max steps、
history miss、overflow、rejection、event HWM 与最大 rewind age。Host 的数值与运行
耗时不是 on-target cycle timing；实机耗时仍需要板上验证。
