# SCG 开发版使用说明

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

当前主导航只有三个可自由切换的工作区：**硬件与通信、飞行流程、检查与生成**。没有状态估计、控制或日志子页，也不需要依次点完“下一步”。内部类和旧字段名继续用于兼容，不代表仍有七个主页面。稳定发布 v0.1.2 的七页截图与操作描述属于历史版本，不能据此判断当前布局。

产品号取根 VERSION，当前开发线为 0.1.3，工程格式为 24。旧工程通过明确迁移读取，原始文件在用户保存前保持不变；算法、日志、硬件及独立 decoder/协议/插件身份不会随产品版本机械重置。

## SCG：配置、生成与构建

1. 新建项目并选择外部、可写的项目根目录。根描述符为 `SilverStar.ssproject`；Flight、Ground 与 `Log/` 分别保存目标源码和日志。不要选本分发源码目录作为固件输出目录。
2. 在“硬件与通信”顶部为飞控、地面站分别选择已有板卡，或导入完整 CubeMX 工程目录。紧接其后的“配置共享无线链路”在一个草稿中修改双方模块与公共 PHY，可预览预设，检查后一次应用；取消不改变工程。再配置各端设备、安装方向和资源绑定。更换无线家族需重新核对引脚。地面站至 PC 的物理 UART/USB 接口在其目标区；现场 COM 端口由 GSHC 管理。平台、完整资源与来源详情可展开；导入资源不等于证明了外接接线或实机支持。
3. 在“任务流程”选择模板或添加阶段胶囊，点击胶囊编辑进入条件和相关功能引用。下方主表每行只对应一个共享功能，点击名称或阶段范围打开该功能属性。默认已接受 START 后进入上升；可选加速度起飞/燃尽检测默认各 2g、保持 200ms。开伞可选。参数和来源只有一个 owner；确认统一提交，取消、Esc 和关闭不保存草稿。阶段窗口内打开的子属性也属于阶段草稿，父窗口取消一并撤销。
4. 在“检查与生成”查看对应问题，分别生成 Flight Controller 或 Ground Station，并运行相应构建/检查。问题可以定位到硬件目标或阶段并展开详情。只生成一个目标时，不以另一个目标未完成的独立硬件无关阻断。Flight 日志生成时，项目根会产生与该配置匹配的 `<ProjectName>.ssdecoder`。
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

Release 通常采用 `-O2 -g`，Debug 采用 `-Og -g3`。输出 ELF/HEX/BIN/MAP 和静态资源信息；工具缺失会阻止相应构建/检查。SDK、构建工具及它们的版本不随此源码包安装。历史 v0.1.2 包解压验证没有重新编译全部固件，不能证明这些命令在每个配置上均已执行；当前实际检查以版本证据记录为准。

**烧录说明：** SCG 未提供已验证的通用 flash 按钮。真实硬件使用者应依据确切 MCU/板卡、引脚供电与生成 ELF，另行配置 STM32CubeProgrammer 或已验证的板级烧录流程；模板内 OpenOCD/J-Link 结构不构成已验证烧录能力。历史 v0.1.2 发布准备没有执行这些操作，没有连接 DAPLink、串口或设备，也没有发送 START。

## 阶段功能、记录与兼容

阶段显示名称可以修改，绑定使用稳定 stage_id。持续功能只创建一份实例和参数，默认在开始阶段进入时启动、结束阶段退出时停止，因此包含结束阶段本身；旧显式进入边界停止保留原义。跨阶段保持同一实例状态。阶段插入、重排或删除边界后，查看相关功能的范围与问题；删除引用点不会悄悄改绑相邻阶段。一次性任务表示发起一次任务请求，完成/失败仍由实际插件报告，不等于只计算一次或已经完成物理动作。

参数在具体功能属性中编辑，继续使用插件实际值、单位和精度。`.ssparams`（兼容 `.ssparameters`）导入先核对插件 ID、版本、manifest 摘要和参数 schema，预览变化后只应用到该算法及已有 shared_key 关联，不替换硬件或整个流程。同一导入入口接收 TreeDiagram `.sstuning.json`：外层 bundle 保留模型/运行来源，内部仍使用原有严格标量 profile；全部 owner 通过检查后一次应用。PID/LQR 控制研究记录尚无目标任务/执行机构消费者，不随标量参数导入部署到固件。恢复插件默认与保留工程显式值是不同操作。

“任务记录”卡管理记录内容和抽取策略，保存位置来自第一页的存储设备。记录/遥测区间可配置，并由原生消费者执行；依赖 INS/估计器时，失效或过期输出会暂停相应数据流。关键身份、自检、校准/对准与事件保持必要生命周期。没有回收流程时，不隐式触发落地停止，记录按配置持续到任务终止。详见[飞前日志](PREFLIGHT_LOGGING.md)。

新工程默认流程与自定义流程使用同一有界原生消费者。旧桌面参考流程需要显式迁移并通过校验；未支持触发、运行中换算法等绑定仍阻止生成。配置与生成成功不等于实机实际过程或飞行资格。

GSHC 目前通过导入 SCG 导出的 `.ssmission` 获得配置声明，自定义阶段的实时上报仍需对应固件与协议消费者。FLP 从精确匹配的 `.ssdecoder` 读取配置，并按原始日志展示 Recorded；桌面参考 trace 不会补造成板端记录。

## 硬件与 USB 支持边界

下表保留 v0.1.2 发布准备与后续开发的受限硬件证据，不是本次 GUI 重构新增的实机结论。实际执行的软件检查以[版本与证据记录](../shared/VERSIONS_AND_EVIDENCE.md)为准。

| 范围 | 当前证据与边界 |
|---|---|
| STM32F407 + SS0.5 声明式 Flight/Ground 路径 | 已有受限软件构建、Host 与静态检查记录；历史三应用合并时未重建全体固件。TF 卡、板级时序、实际通信与飞行资格仍需独立验证 |
| F103C8 / STM32C071FBP6 原生单 FS classic CDC Ground | **EXPERIMENTAL** 私有候选；有配置模型、原生构建/架构检查记录。完整普通生成入口 **BLOCKED**，这些候选不是可直接部署的通用 USB Ground |
| F407 原生 TIM1 / Ground | 私有正常计时与 Ground 路径候选的软件检查；不替代首批 C071 验证，也不证明 EP0 正式放行 |
| 其他 STM32、USB 栈、多个 FS/HS、其他时钟/资源组合 | 未由上述证据证明；未知配置拒绝。MCU 家族名称或 GUI 可选项不等于整族验收 |

原生 CDC 候选保持 HAL、CMSIS、startup、linker、clock、GPIO、IRQ、PCD 与 middleware 的原有所有权；SCG 接入有界 queue/session/协议与已核对的适配。USB EP0 的独立安全审查没有获得通过结果，相关正式依赖路径不得写为已审或已放行。这里保留阻断和未知配置检查。


## 插件、所有权及检查

阅读[用户指南](USER_GUIDE.md)、[工程格式](PROJECT_FORMAT.md)、[参数](ALGORITHM_PARAMETERS.md)、[插件](PLUGIN_FORMAT.md)、[生成所有权](GENERATED_CODE.md)、[构建](BUILD.md)与[架构](ARCHITECTURE.md)。跨工具从[公共总入口](../README.md)进入；惯导与融合算法见[实现说明](../algorithms/NAVIGATION_IMPLEMENTATION.md)。

原生 HAL/CMSIS/startup/linker/clock/GPIO/IRQ/PCD/middleware 所有权不被 SCG 偷换；用户已拥有的 payload 不被正常 Apply 强制替换。错误返回、配置拒绝、安全检查和 PoT critical-contract NOT PROVEN 都保留。

历史源码修复、旧计数与旧 MCU/板卡证据保持原时间身份，不是本版完整验收。此公共说明不附用户原始日志、内部安全审查或烧录脚本。
