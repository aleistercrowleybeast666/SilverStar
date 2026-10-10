# SCG 0.1.2 使用说明

SCG 是 System Configuration & Generation，历史命名 FCCG 以及 Python 包 `silverstar_fccg` 保留兼容身份。产品版本取根 VERSION。新工程的实际内容由所选插件和目标决定，不能把 GUI 的候选项当作硬件支持证明。

## 安装和启动

从仓库或源码包根运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe SCG.py
.\.venv\Scripts\python.exe SCG.py --version
```

完整环境、版本、用户目录说明见[根 README](../../../README.md)。

## 当前页面与版本

当前 `MainWindow._page_widgets` 为七页：Flight Devices、Flight Configuration、Navigation Configuration、Telemetry Configuration、Flight Hardware、Ground Hardware、Build & Checks。内部类仍可保留兼容字段名，不能据此另造第八个 Ground Configuration 页面。Navigation 集中 source、Calibration、Alignment、INS/Estimator 与实际算法参数；Telemetry 管共享 AIR、两端 radio 和 Ground PC 参数。

SCG 基础格式 14、Ground radio 扩展 15、radio variant 16、feature tiers 17 均有严格兼容边界；当前四档预设使用 17。decoder/project-semantics 为 1.2。插件自身 manifest 版本、旧项目、旧日志和协议各有独立身份，不机械替换成产品 0.1.2。

## SCG：配置、生成与构建

1. 新建项目并选择外部、可写的项目根目录。根描述符为 `SilverStar.ssproject`；Flight、Ground 与 `Log/` 分别保存目标源码和日志。不要选本分发源码目录作为固件输出目录。
2. 在 Flight Devices 配置传感器/设备实例；在 Flight Configuration、Navigation、Telemetry 配置策略、校准、对准、INS/估计器、AIR 与共享无线参数。页面依据插件清单显示能力；未知或不匹配配置必须拒绝。
3. 在 Flight Hardware / Ground Hardware 选择匹配板卡，或导入真实 CubeMX 工程与 `.ioc`。检查确切 MCU、封装、时钟、GPIO、IRQ、SPI/UART 等资源。导入文件仍由原生 CubeMX 工程拥有。
4. 在对应硬件页生成 Flight Controller / Ground Station；Build & Checks 检测工具、显示构建与校验结果。Flight 日志生成时，项目根会产生与该配置匹配的 `<ProjectName>.ssdecoder`。
5. 已有用户源码不会被正常重新生成强制替换。需要验证模板修复时应生成到新的隔离项目；已有工程须明确迁移所需修复，不能把旧 ELF 当作新源码产物。

生成工程使用声明式 SourceGraph 决定 sources、includes、defines、CPU/FPU、linker 与强制包含；Make、EIDE、VS Code 共享这份所有权。它不是遍历目录自动拼接所有 C 文件。构建需另外安装 Arm GNU、GNU Make，Host 检查还需兼容 Host GCC，并使工具可被检测。

以下为**生成后**在相应目标目录使用的检查命令；是否提供某项取决于目标模板，先检查生成的 Makefile：

```powershell
mingw32-make CONFIG=Release all
mingw32-make CONFIG=Release host-tests
mingw32-make CONFIG=Release architecture-check
mingw32-make CONFIG=Release power10-check
mingw32-make CONFIG=Release static-analysis
mingw32-make CONFIG=Release artifact-check
mingw32-make CONFIG=Release stack-report
```

Release 通常采用 `-O2 -g`，Debug 采用 `-Og -g3`。输出 ELF/HEX/BIN/MAP 和静态资源信息；工具缺失会阻止相应构建/检查。SDK、构建工具及它们的版本不随此源码包安装。本次包解压验证不重新编译全部固件，也不声称这些命令在每个配置上均已执行。

**烧录说明：** SCG 未提供已验证的通用 flash 按钮。真实硬件使用者应依据确切 MCU/板卡、引脚供电与生成 ELF，另行配置 STM32CubeProgrammer 或已验证的板级烧录流程；模板内 OpenOCD/J-Link 结构不构成已验证烧录能力。本次发布准备没有执行这些操作，没有连接 DAPLink、串口或设备，也没有发送 START。

## 硬件与 USB 支持边界

| 范围 | 当前证据与边界 |
|---|---|
| STM32F407 + SS0.5 声明式 Flight/Ground 路径 | 已有受限软件构建、Host 与静态检查记录；本轮三应用合并后未重建全体固件。TF 卡、板级时序、实际通信与飞行资格仍需独立验证 |
| F103C8 / STM32C071FBP6 原生单 FS classic CDC Ground | **EXPERIMENTAL** 私有候选；有配置模型、原生构建/架构检查记录。完整普通生成入口 **BLOCKED**，本包不是可直接部署的通用 USB Ground |
| F407 原生 TIM1 / Ground | 私有正常计时与 Ground 路径候选的软件检查；不替代首批 C071 验证，也不证明 EP0 正式放行 |
| 其他 STM32、USB 栈、多个 FS/HS、其他时钟/资源组合 | 未由上述证据证明；未知配置拒绝。MCU 家族名称或 GUI 可选项不等于整族验收 |

原生 CDC 候选保持 HAL、CMSIS、startup、linker、clock、GPIO、IRQ、PCD 与 middleware 的原有所有权；SCG 接入有界 queue/session/协议与已核对的适配。USB EP0 的独立安全审查没有获得通过结果，相关正式依赖路径不得写为已审或已放行。这里保留阻断和未知配置检查。


## 插件、所有权及检查

阅读[用户指南](USER_GUIDE.md)、[工程格式](PROJECT_FORMAT.md)、[参数](ALGORITHM_PARAMETERS.md)、[插件](PLUGIN_FORMAT.md)、[生成所有权](GENERATED_CODE.md)、[构建](BUILD.md)与[架构](ARCHITECTURE.md)。跨工具从[公共总入口](../README.md)进入；惯导与融合算法见[实现说明](../algorithms/NAVIGATION_IMPLEMENTATION.md)。

原生 HAL/CMSIS/startup/linker/clock/GPIO/IRQ/PCD/middleware 所有权不被 SCG 偷换；用户已拥有的 payload 不被正常 Apply 强制替换。错误返回、配置拒绝、安全检查和 PoT critical-contract NOT PROVEN 都保留。

历史源码修复、旧计数与旧 MCU/板卡证据保持原时间身份，不是本版完整验收。此公共说明不附用户原始日志、内部安全审查或烧录脚本。
