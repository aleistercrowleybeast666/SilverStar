# SilverStar_FCCG Documentation

本目录分成两层：

1. **FCCG软件文档**：本目录根部，描述配置器、插件、工程模型、生成器、构建和GUI；
2. **SilverStar平台规范**：[`platform/`](platform/)，描述飞控接口、状态机、算法、AIR/维护/SSLOG和验证要求。

## FCCG软件文档
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`PLUGIN_FORMAT.md`](PLUGIN_FORMAT.md)
- [`PROJECT_FORMAT.md`](PROJECT_FORMAT.md)
- [`GENERATED_CODE.md`](GENERATED_CODE.md)
- [Selected device build capabilities](DEVICE_BUILD_CAPABILITIES.md)
- [`BUILD.md`](BUILD.md)
- [`COMPONENTS.md`](COMPONENTS.md)
- [`USER_GUIDE.md`](USER_GUIDE.md)
- [`CURRENT_PROGRESS.md`](CURRENT_PROGRESS.md)
- [飞前日志策略](PREFLIGHT_LOGGING.md)
- [`GUI_STYLE_GUIDE.md`](GUI_STYLE_GUIDE.md)
- [KF6 outage recovery](KF6_OUTAGE_RECOVERY.md)
- [KF6 固定滞后重放与时间同步](KF6_FIXED_LAG_REPLAY.md)
- [联合外场修改报告](JOINT_FIELD_REWORK.md)

## 共同协议契约
- [`AIR_CALIBRATION_CONTRACT.md`](AIR_CALIBRATION_CONTRACT.md)
- [导航、质量、时序、日志与预飞契约](NAVIGATION_CONTRACT.md)
- [统一导航机器契约](../../contracts/navigation_v1.json)

当前产品版本为 SilverStar 0.1.0；AIR仍为M0，Maintenance/SSLOG仍为0.0，`.ssdecoder`/Project Semantics为1.2（拒绝1.1）。平台细节沿用合仓前 0.0.12 规范快照，未改变 wire identity。

GUI规范同时参见[CXYL Python GUI Style Guide](CXYL_Python_GUI_STYLE_GUIDE.md)。完整平台条目见[文档清单](platform/details/DOCUMENT_LIST.md)，实际验收快照见[VALIDATION](VALIDATION.md)。

## Algorithm configuration contract

Pure INS/KF6/ESKF15 实际参数、单位、P0/Q/R 转换与 decoder 1.2 边界见[算法参数契约](ALGORITHM_PARAMETERS.md)。当前质量策略为 revision 3；历史 decoder/revision 保持原语义。旧参数值不被静默夹紧或改写，已退役参数在当前 GUI 中只读并明确不参与计算。
