# 兼容目标

当前工程为 SilverStar_GSHC，Python / PySide6 地面站上位机；产品显示身份由根 VERSION 提供，当前为 0.1.2。

- 产品 SilverStar 0.1.2，AIR M0，PC ↔ GS 使用 GSP-MIN，实机联调目标为 SS0.5。
- 校准事务、默认校正、Reset 与 Alignment 依照[共同契约](AIR_CALIBRATION_CONTRACT.md)；wire 以 [AIR_PROTOCOL](AIR_PROTOCOL.md) 为准。
- 平台相关格式版本为 Serial Maintenance 0.0、SSLOG 0.0、`.ssdecoder` package/project-semantics 1.2；本工程仍只处理现有串口 AIR/GSP 和 JSONL，维护串口仅由独立磁力计采集路径显式启用；AIR 页面不因格式版本新增 `.ssdecoder` 输入。
- 保留采样校准、六面重采、初对准、START、分层诊断、双语/主题、日志及后处理。
- 不修改 FCCG、FLP、飞控或外部 reference firmware；GSHC 平台参考镜像的完整权威在 FCCG。

入口见[文档索引](README.md)，能力状态见当前进度（历史或内部参考，不纳入公共说明的验收依据），实际验收结果与硬件限制见 VALIDATION（历史或内部参考，不纳入公共说明的验收依据）。
