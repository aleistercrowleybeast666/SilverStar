# SilverStar

SilverStar 是面向无控探空火箭航电开发的开源工具链，包含系统配置与工程生成工具 SCG、地面遥测交互工具 GSHC，以及日志分析工具 FLP，覆盖硬件配置、固件生成、地面监测和离线分析流程。

**当前公开稳定发布：v0.1.2，发布于 2026-10-12。** [下载 Windows 便携包](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2) · [查看 v0.1.2 源码](https://github.com/aleistercrowleybeast666/SilverStar/tree/v0.1.2) · [发布文章与教程](https://www.kechuang.org/t/92068)

`main` 以 v0.1.2 稳定源码为基线；入口说明可以随后更新，精确发布源码请以 `v0.1.2` 标签为准。0.1.3 正在开发，尚未发布；其开发功能不属于本页所述 v0.1.2 便携包。

| 应用 | 用途 | Windows 便携包 | 源码入口 |
|---|---|---|---|
| SCG（System Configuration & Generation） | 配置设备、导航、遥测与 Flight/Ground 硬件，生成 STM32 工程及配套解码包 | `SCG.exe` | `SCG.py` |
| GSHC（Ground Station Host Computer） | 接收遥测、发送控制命令，显示设备状态，记录会话并导出轨迹、图片与表格 | `GSHC.exe` | `GSHC.py` |
| FLP（Flight Log Processor） | 配对日志与精确解码包，查看记录、轨迹和事件，离线复算与结果对比 | `FLP.exe` | `FLP.py` |

导航算法包括 Pure INS、SF6、KF6 和 ESKF15；传感器与算法采用插件化组织。FCCG 是 SCG 的历史名称，内部 `silverstar_fccg` Python 包名继续保留兼容；当前启动入口使用上表中的 SCG 名称。

## 下载与启动

Windows 10/11 64 位用户请从 [v0.1.2 Release](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2) 下载 `SilverStar_0_1_2_Windows_Portable.zip`，完整解压到可写目录，然后运行所需 EXE。无需另装 Python。三个程序共用 `_internal` 依赖目录，请保留目录结构，不要单独移动 EXE。

生成固件后的编译与烧录仍需配置外部 ARM GNU 工具链、相应 SDK 和烧录工具；这些工具及最终固件不包含在便携包中。工程输出请选择包外的用户目录。

发布附件校验：

```text
文件大小：220688183 字节
SHA256：3330d83f49a2665c9052ad624719c22c484dde84507b02024868ded4f6ecce8e
```

GSHC 的既有默认数据目录是 `D:/SilverStar_GSHC_Data`。没有 D 盘或需要指定其他位置时，可在启动前设置：

```powershell
$env:SILVERSTAR_GSHC_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'SilverStar_GSHC_Data'
& '.\GSHC.exe'
```

## 从稳定源码运行

需要与发布版本对应的源码时，请下载或检出 `v0.1.2` 标签。源码运行需要 Python 3.11 或以上；该版本包的实际验证环境为 Python 3.14.0，未单独验证 Python 3.11 环境。在源码根目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe SCG.py
.\.venv\Scripts\python.exe GSHC.py
.\.venv\Scripts\python.exe FLP.py
```

后三条命令分别启动一个应用。应用版本以所选源码树的根目录 `VERSION` 为准；AIR、SSLOG、解码包和第三方库的版本独立管理。

`v0.1.2` 标签对应提交 `c31c13cc0686a56a3184d4f207fd3816c5d39696`。便携包清单记录的载荷来源是 `6feeadd000c866e456c08d5c85057d0f529d0993`；两次提交之间仅更新两份发布元数据文档，未重建 EXE。

## 文档与使用边界

- [公共文档入口](docs/public/README.md)：跨工具流程、教程、API 和插件说明。
- [Windows 便携包说明](docs/public/WINDOWS_PACKAGE.md)：目录结构、依赖、数据路径和打包验证范围。
- [v0.1.2 冻结分发记录](docs/public/releases/0.1.2.md)：构建和候选阶段的历史记录；其中发布前状态描述属于当时快照，公开发布状态以 [GitHub Release](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2) 为准。

本次发布说明记录了 STM32F407 飞控与 STM32F103 串口地面站的台架、手持和抛体外场数据采集。这些记录不等同于实际火箭飞行验证，其他硬件组合与任务条件仍需验证。USB CDC 的 F103/C071 工程接入属于实验范围，普通 native USB 生成入口仍受限，尚未完成相应 USB 硬件的上板验证。软件检查也不代表栈、实时性或飞行资格已经获得证明。

GSHC 中 ACK 不等于 READY，应以设备报告的准备状态为准。FLP 打开生产日志需要精确匹配的 `.ssdecoder` 和 Descriptor；请保留原始日志与解码包，导出到新目录。

0.1.3 中的 Android 开发版、DeviceService 模拟原型、SWD 诊断及新增维护/USB/导航改动仍在开发，不能作为 v0.1.2 已发布能力介绍。

## 来源、许可与反馈

原创 SilverStar 源码采用 [Apache License 2.0](LICENSE)，第三方组件保留各自条款，详见[来源与许可说明](docs/public/licenses/README.md)。项目包含从成都亿佰特官网下载并修改的 SX1280 固件库，原下载包未附独立 `license.txt`；相关来源及许可状态已记录，不能将根许可证解释为全部第三方代码的许可证。

欢迎通过 [GitHub Issues](https://github.com/aleistercrowleybeast666/SilverStar/issues) 反馈问题，并附软件版本、硬件配置、复现步骤及相关日志；飞控日志请同时提供对应 `.ssdecoder` 解码包。
