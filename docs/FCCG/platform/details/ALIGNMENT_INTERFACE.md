# Alignment 接口索引

> 文档版本：0.0.12

SilverStar 0.0.12已将传感器校准和任务初始状态建立正式拆分：

- [SystemCalibration接口与预飞校准规范](SYSTEM_CALIBRATION.md)
- [SystemAlignment接口与初始状态规范](SYSTEM_ALIGNMENT.md)
- [Calibration与Initial Alignment算法、q_nb及ENU yaw权威契约](CALIBRATION_AND_ALIGNMENT.md)

正式依赖始终是：

```text
Calibration READY -> Alignment READY -> START READY
```

本索引不再重复定义结构体、状态或命令，以避免两份规范漂移。
