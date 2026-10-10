# Builtin Components

当前SilverStar 0.1.0官方builtin按以下类别组织：

- Core 0.0.12；
- MCU/Platform：STM32F407VET6/F4 backend；
- Board：SS0.5 verified Board；
- Devices：JY901B、NEO-M9N、E28-2G4M12SX/SX1281、maintenance UART、SD/TF(SDIO+FatFs)、输入电压、点火/开伞输出、指示灯；
- Algorithm：Calibration、Alignment common/strategies、Coning2Sculling2 INS、KF6；
- FlightLogic：flight cycle/recovery、deployment、landing；
- OS：FreeRTOS 11.3.0；
- Protocol：AIR M0、Maintenance 0.0、SSLOG 0.0；
- Hardware provider：STM32CubeMX；
- Environment：VS Code + EIDE + Arm GNU。

## Capability资格
Raw/Data capability只表示能提供数据；`*_qualified`表示满足某个明确使用合同。FCCG不能根据设备型号猜资格。

## Multi-instance
官方JY901B/M9N/SX1281允许同插件最多4实例，前提是硬件资源独立。插件源码只编译一次，运行时context/descriptor/resource按实例隔离。

## Calibration
OneFace/SixFace是可选采样procedure；NONE始终可用。空procedure build自动NONE/Identity/READY；有采样procedure时地面站仍可显式选择NONE。
