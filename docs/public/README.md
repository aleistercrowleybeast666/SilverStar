# SilverStar 0.1.2 公共文档

此目录统一保存适合发布包阅读的教程、API/插件、共享契约、原理及实现公式。先安装[根README](../../README.md)的共享环境，按[三工具流程](USER_WORKFLOW.md)操作，再核对[支持矩阵](SUPPORT_MATRIX.md)与[版本/证据边界](shared/VERSIONS_AND_EVIDENCE.md)。

| 入口 | 适用内容 |
|---|---|
| [SCG](SCG/README.md) | 配置、插件、SourceGraph、原生所有权、工程、生成/构建 |
| [GSHC](GSHC/README.md) | AIR/GSP、地面状态、校准、实时显示与日志/图表导出 |
| [FLP](FLP/README.md) | exact decoder、parser、重算/比较、数值工件、API与导出 |
| [导航实现](algorithms/NAVIGATION_IMPLEMENTATION.md) | 惯导、SF6、KF6、ESKF15的共同约定与实现边界 |
| [项目目录](shared/PROJECT_FOLDER_CONTRACT.md) | Flight/Ground/Log/decoder的共同身份与路径 |
| [单仓库架构](shared/MONOREPO_ARCHITECTURE.md) | 三工具职责和共享契约 |
| [0.1.2分发说明](releases/0.1.2.md) | 源码分发、已知限制和许可证待完成项 |

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

当前状态仍为本地源码发布准备，未push、创建远端tag或公开上传。普通native USB入口BLOCKED，PoT关键合同NOT PROVEN；软件与日志分析结果不等于硬件、导航真值或飞行安全验收。公式与其源码/坐标/版本说明将在本入口列出，不能将理想公式冒充真实实现。
