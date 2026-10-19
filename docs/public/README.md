# SilverStar 使用文档

此目录保存使用教程、API/插件、共享契约与实现说明。首次体验可先下载 [v0.1.2 Windows 便携包](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2)，再用[示例日志与匹配解码包](examples/README.md)体验 FLP。源码启动见[中文首页](../../README.md)或 [English home](../../README.en.md)。

稳定发布的文档固定在 [v0.1.2 标签](https://github.com/aleistercrowleybeast666/SilverStar/tree/v0.1.2/docs/public)。0.1.3 仍在开发，尚无正式发布；请按各页版本和状态阅读，开发功能不属于 v0.1.2 便携包。按[三工具流程](USER_WORKFLOW.md)操作，再核对[支持矩阵](SUPPORT_MATRIX.md)与[版本/证据边界](shared/VERSIONS_AND_EVIDENCE.md)。

For an English introduction, start with the [English README](../../README.en.md) and [sample walkthrough](examples/README.md#english). Most detailed guides are in Chinese. The [v0.1.2 documentation tag](https://github.com/aleistercrowleybeast666/SilverStar/tree/v0.1.2/docs/public) fixes the stable version; 0.1.3 remains unreleased and its development features are separate from the stable package.

| 入口 | 适用内容 |
|---|---|
| [v0.1.2 三工具图解](V0_1_2_WALKTHROUGH.md) | 三页 SCG、GSHC 真实三维模型、FLP 平面/立体/曲线 |
| [无需硬件体验](examples/README.md) | 000062 主要案例、000028 独立参考、精确配对下载与校验 |
| [SCG](SCG/README.md) | 配置、插件、SourceGraph、原生所有权、工程、生成/构建 |
| [GSHC](GSHC/README.md) | AIR/GSP、地面状态、校准、实时显示与日志/图表导出 |
| [FLP](FLP/README.md) | exact decoder、parser、重算/比较、数值工件、API与导出 |
| [导航实现](algorithms/NAVIGATION_IMPLEMENTATION.md) | 惯导、SF6、KF6、ESKF15的共同约定与实现边界 |
| [项目目录](shared/PROJECT_FOLDER_CONTRACT.md) | Flight/Ground/Log/decoder的共同身份与路径 |
| [单仓库架构](shared/MONOREPO_ARCHITECTURE.md) | 三工具职责和共享契约 |
| [0.1.2分发说明](releases/0.1.2.md) | 冻结分发历史、已知限制与第三方许可说明 |

直接阅读[惯导与融合算法15页PDF](math/navigation-models.pdf)；[模块化TeX入口](math/README.md)提供主文档和九个子文件，注明实现、符号、坐标与版本边界。

## 共用说明

- [AIR_LINK](shared/AIR_LINK.md)
- [DEVICE_STARTUP](shared/DEVICE_STARTUP.md)
- [DEVICE_VARIANTS](shared/DEVICE_VARIANTS.md)
- [GROUND_STATION](shared/GROUND_STATION.md)
- [MCU_PLATFORM](shared/MCU_PLATFORM.md)
- [MISSION_SNAPSHOT](shared/MISSION_SNAPSHOT.md)
- [MONOREPO_ARCHITECTURE](shared/MONOREPO_ARCHITECTURE.md)
- [PCB_INSTANCE_WORKFLOW](shared/PCB_INSTANCE_WORKFLOW.md)
- [PERSISTENT_STORAGE](shared/PERSISTENT_STORAGE.md)
- [PROJECT_FOLDER_CONTRACT](shared/PROJECT_FOLDER_CONTRACT.md)
- [TARGET_MODEL](shared/TARGET_MODEL.md)
- [TARGET_RESOURCE_PLAN](shared/TARGET_RESOURCE_PLAN.md)
- [VERSIONS_AND_EVIDENCE](shared/VERSIONS_AND_EVIDENCE.md)

## 文档整理规则

旧入口保留兼容路径；原文按原字节保存于内部历史快照，历史日期/版本/测试计数不改成当前。内部测试、原始日志、绝对机器路径、构建证据与未获通过的独立审查不迁入公共目录。公共内容描述冻结源码与已知边界，不能通过修改程序或删除检查让文档成立。

v0.1.2 已于 2026-10-12 [公开发布](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2)；下载、校验值与稳定源码以该 Release 和标签为准。候选、待推送等历史措辞保留在对应日期的分发记录中，不代表当前发布状态；第三方许可未解项继续以来源与许可材料为准。0.1.3 开发内容不属于 v0.1.2 便携包。普通 native USB 入口 BLOCKED，PoT 关键合同 NOT PROVEN；软件与日志分析结果不等于硬件、导航真值或飞行安全验收。公式与其源码/坐标/版本说明将在本入口列出，不能将理想公式冒充真实实现。

[第三方来源与许可材料](licenses/README.md)：官方原始正文、逐文件摘要、已有修改及未解项。

- [Windows 便携包](WINDOWS_PACKAGE.md)
- [测试证据保留与软件验证范围](SOFTWARE_VERIFICATION.md)
