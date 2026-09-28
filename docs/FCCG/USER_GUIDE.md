# FCCG User Guide

## Algorithm actual parameters / 算法实际参数

新增独立算法参数页面（硬件连接之前），插件声明实际值、单位和 representation。
Project format 12；`.ssdecoder` / project-semantics 1.2，拒绝 decoder 1.1；
Platform 仍为 0.0.12，Record Catalog 与协议布局不变。
参数清单、生成绑定与 Recorded Configuration / Offline What-if 边界见[参数契约](ALGORITHM_PARAMETERS.md)。
精确验证结果仅见仓库根 VALIDATION.md。


## 1. 新建工程
输入工程名和输出目录。默认Core/OS/Environment自动选择。

## 2. Devices
选择IMU、GNSS、其他传感器、通信链路、Storage、Actuator、Indicator。支持多实例的官方IMU/GNSS/Telemetry可使用“增加”按钮重复添加，同型号实例后续绑定不同硬件资源。

## 3. Flight Configuration
选择Alignment/INS/Estimator/Landing Strategy、Calibration/Deployment Mode、三种协议以及Logging。

Logging表的“级别”与“用途”分别表示契约必要性（必须/推荐/可选）和使用场景（飞行/测试）。
Required记录提供日志身份、配置与必要任务事件；Flight记录用于正常飞行、故障分析与FLP离线复算；
Test记录用于深度开发与数值诊断。只有KF6_DIAGNOSTIC、KF6_FULL_P为Test，均为可选且默认关闭。
“打开全部”“只保留飞行日志”“只留必须”是一次性批量修改，之后仍可单独勾选日志；
“只留必须”不保证FLP完整复算。硬件、算法或协议变动时，仍可用日志保留用户选择，
失去可用性的日志关闭，重新可用的日志按metadata默认值恢复。

Calibration采样procedure只有OneFace/SixFace，默认都不选；NONE始终是飞控可用模式。若一个或多个采样procedure被编入，GSHC运行时仍可选择默认NONE。

## 4. Algorithm Parameters
按算法编辑实际数值（不是默认倍率），检查单位与说明；高级参数可折叠，每个算法可恢复默认值。

## 5. Hardware Connection
- Official Board：使用固定logical ID→alias映射，为设备分配兼容资源并验证闭合，不能按扫描顺序重排；
- Custom CubeMX：导入完整CubeMX generated project，由用户完成/确认资源分配。

I2C外部上拉、PWM模式/极性、timebase、SDIO/FatFs等根据hardware snapshot严格验证。

## 6. Generate
Generate验证并增量物化源码、Generated glue、Make/EIDE/VS Code和项目描述符。它不自动执行完整构建/质量门。

## 7. Build/Validation
使用EIDE/VS Code或FCCG高级操作执行支持的构建与验证。Stack Report通过生成工程的`mingw32-make CONFIG=Release stack-report`及Debug对应命令单独执行，详见[Build](BUILD.md)。

## 8. `.ssdecoder`
Logging启用时生成并可导出。它与对应日志精确匹配，供FLP后续解析；不要手工编辑包内容。

## Shared Parameters

When selected algorithms declare a common `shared_key`, Algorithm Parameters shows one Shared Parameters section before the algorithm groups. Editing or resetting that field updates every selected owner. Algorithm reset buttons affect only non-shared fields. Pure INS and KF6 gravity therefore appear once; saved projects and decoder output still retain both equal actual values.
