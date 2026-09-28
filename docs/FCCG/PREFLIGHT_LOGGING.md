# 飞前日志策略

正常飞行工程默认 `SYSTEM_LOG_PREFLIGHT_NATIVE_ENABLE=0U`、
`SYSTEM_LOG_PREFLIGHT_CORRECTED_IMU_ENABLE=0U`。Logger 从启动阶段持续运行；
这两个开关只控制连续传感器记录的生产者，不暂停设备采样。

| 生产路径 | PRE-FLIGHT / READY | FLIGHT / RECOVERY |
| --- | --- | --- |
| `DeviceNativeLog_Process` / `DeviceNativeLog_ImuProcess` | 在读取日志快照、更新去重序号和 LoggerBus push 之前返回 | 保持实例选择、去重和工程流策略 |
| `ImuSampleBus_Process` | 继续消费惯性源、校准样本处理、入队供 Alignment 使用；仅 CorrectedLog 跳过写日志 | 继续完整采样与 corrected 记录 |
| InsTask | 保留初对准处理；现有 mission/lifecycle gate 不产生飞行解算流 | 产生工程选择的 inertial increment、Sample、Raw Sensor、Pure INS |
| EstimatorTask | 继续 GNSS/Baro origin window、诊断与对准状态处理 | 现有 prediction gate 产生 measurement、state、covariance、diagnostic |
| DeviceTask 低频状态 | 保留既有 Power、Health、Stats 及状态变化诊断 | 保持既有策略 |
| LoggerTask / FlightTask 关键记录 | 保留 bootstrap、descriptor、config、calibration/alignment 结果和事件 | 保留 START、INITIAL_STATE、mission config、fault、landing 等记录 |

原始连续流包括 IMU_NATIVE、GNSS_NATIVE、BARO_NATIVE、MAG_NATIVE、HW_QUAT_NATIVE；
IMU_CORRECTED 使用独立开关。未选择的流仍受现有 manifest/project logging policy 控制。
高频流暂停不代表设备离线，也不代表日志 record sequence 缺失。

启动阶段继续建立文件，写入 header、decoder profile、SYSTEM_CONFIG、
DEVICE_DESCRIPTOR、ALGORITHM_DESCRIPTOR、LOG_STREAM_DESCRIPTOR 和 self-test 诊断。
校准/初对准开始、成功、失败、START_REJECTED 和 fault 事件不经过上述连续流 gate。
最终 GNSS/Baro origin、初始姿态及 P0 仍由现有 Alignment / INITIAL_STATE 路径保存。

START transaction 先完成 Prepare、origin freeze、navigation start 和 flight queues reset，
再提交 FLIGHT；其后 FlightTask 写入 START 配置与 INITIAL_STATE。
日志 gate 不修改 START transaction，也不在飞前推进 native 去重序号。
目标调度的首样本时序仍须实机确认；Host 边界验证和精确计数见根目录 VALIDATION.md。

落地后继续使用现有 `SYSTEM_LOG_POST_LANDING_GRACE_MS`、drain、flush、finalize 与
storage fault 规则。LANDED 后普通连续流依照原有 lifecycle gate 停止，Logger 在宽限期间
继续接收允许的尾段记录。不得通过停止 Logger 或隐藏 overflow 来节省文件空间。

## 诊断构建

排查传感器时可在生成工程的 `System/User/system_user_config.h` 手动把两项改为 `1U`，
或为编译命令提供：

```text
-DSYSTEM_LOG_PREFLIGHT_NATIVE_ENABLE=1U
-DSYSTEM_LOG_PREFLIGHT_CORRECTED_IMU_ENABLE=1U
```

头文件用 `#ifndef` 保留显式构建覆盖。两项默认值对 Release / Debug 均为 0，
选择 Debug 优化等级不会自动开启飞前全量日志。诊断构建仍受队列容量和 SD 延迟约束。
参数不进入 GUI、project format、decoder schema；日志容器和各 record 布局不变。

Host storage fixture 使用真实 native/corrected producer、LoggerBus、LoggerTask、
codec、FatFs 和 diskio；设备源、校准状态、导航输出与调度是测试模型。
它证明门控与字节存储行为，不能替代真实 GNSS origin、校准收敛或硬件时间保证。
