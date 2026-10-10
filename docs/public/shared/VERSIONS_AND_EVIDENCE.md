# 产品、格式与证据身份

| 身份 | 0.1.2 源码中的口径 | 权威来源 |
|---|---|---|
| Suite 产品版本 | 0.1.2 | 根 VERSION，各应用读取它 |
| SCG 基础项目 | 14 | `project/model.py:PROJECT_FORMAT_VERSION` |
| Ground radio 扩展 | 15 | `PROJECT_GROUND_RADIOS_FORMAT_VERSION` |
| Radio variant 扩展 | 16 | `PROJECT_RADIO_VARIANTS_FORMAT_VERSION` |
| 四档项目 | 17 | `PROJECT_FEATURE_TIERS_FORMAT_VERSION` |
| FLP `.ssflp` 项目 | 3 | `core/project.py:PROJECT_VERSION` |
| Decoder / Project Semantics | 1.2 | strict decoder coordinator / 生成声明 |
| SSLOG / Maintenance | 0.0 | 具体 wire 契约与 codec |
| AIR | M0 / wire Profile 0 | GSHC AIR_PROTOCOL 与实际协议 |
| 插件 manifest | 各自独立，参见组件清单 | builtin plugin.json |
| 上游库 | 各自独立 | vendor 文件头、LICENSE、实际来源 |

产品补丁版本不能机械改写 wire、源日志、decoder、插件版本、既有项目拥有的 payload 或历史二进制。SCG 接受 14/15/16/17 的明确边界，旧版本迁移以实际 loader 为准；“当前基础常量14”和“四档17”可以同时成立。

## 软件验证的口径

本次三应用合并曾有25项针对性Python检查通过；三个实际窗口离线启动/事件循环/退出通过。源码分发另有解压文件哈希/入口/帮助/离线烟测，最终结果绑定最终包的 receipt。不能把这些结果写成全套测试、全部固件配置、桌面GPU、串口无线、TF、栈、WCET或飞行资格均通过。

F103C8/C071FBP6 classic CDC 是 EXPERIMENTAL 私有候选，普通完整生成入口 BLOCKED；F407 private TIM1/Ground 不替代首批 C071。USB EP0 独立审查没有通过结果；不能重标已审或据此正式放行依赖。PoT critical-contract review 是 NOT PROVEN。保留未知配置和失败检查。

历史报告、原日志、构建文件和证据保留原日期/源码/命令/配置身份，不纳入公共文档包，公共目录不复制它们。原文内具有日期、旧固件/Golden或旧格式身份的段落仍按各自历史范围阅读；当前说明另明确源码边界，不将旧结果重新归属本版。
