# SilverStar

简体中文 · [English](README.en.md)

面向无控探空火箭航电开发的开源工具链：用 **SCG** 配置硬件与生成工程，用 **GSHC** 查看地面遥测，用 **FLP** 阅读和分析记录日志。

**稳定发布：[v0.1.2 · 2026-10-12](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2)** · [下载 Windows 便携包](https://github.com/aleistercrowleybeast666/SilverStar/releases/download/v0.1.2/SilverStar_0_1_2_Windows_Portable.zip) · [示例日志](docs/public/examples/README.md) · [使用文档](docs/public/README.md) · [问题反馈](https://github.com/aleistercrowleybeast666/SilverStar/issues)

## 下载与快速体验

便携包适用于 **Windows 10/11 64 位**，无需安装 Python。完整解压后运行 `SCG.exe`、`GSHC.exe` 或 `FLP.exe`；三个程序共用 `_internal`，请保留目录结构。

1. **配置项目**：打开 SCG，浏览设备、导航、遥测和硬件配置。生成工程时选择包外的可写项目目录；编译固件另需 Arm GNU、Make，以及对应的硬件资源。
2. **浏览地面站**：打开 GSHC，可在未连接状态下浏览界面。实时数据需要匹配的地面站与通信链路。
3. **带数据体验**：从[示例页](docs/public/examples/README.md)下载主要案例 `000062` 及其精确配对的 `.ssdecoder`，在 FLP 中打开日志并选择该解码包，查看 **Recorded** 数据、任务摘要与图表。历史记录 `000028` 可作为独立参考；无需连接硬件。

GSHC 默认数据目录为 `D:/SilverStar_GSHC_Data`。没有 D 盘或希望另选位置时，可在便携包目录打开 PowerShell：

```powershell
$env:SILVERSTAR_GSHC_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'SilverStar_GSHC_Data'
& '.\GSHC.exe'
```

<details>
<summary>v0.1.2 下载校验</summary>

文件：`SilverStar_0_1_2_Windows_Portable.zip`，大小 **220688183 字节**。SHA-256 与 [Release](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2) 公布值一致：

```text
3330d83f49a2665c9052ad624719c22c484dde84507b02024868ded4f6ecce8e
```

</details>

## 三款工具

| 工具 | 可以做什么 | 使用说明 |
|---|---|---|
| **SCG** · System Configuration & Generation | 选择传感器、导航算法、遥测链路和任务参数，检查引脚与外设资源，生成 STM32 飞控/地面站工程与配套解码包 | [SCG 指南](docs/public/SCG/README.md) |
| **GSHC** · Ground Station Host Computer | 接收 AIR M0 遥测，显示准备状态、三维姿态、轨迹和任务事件，记录会话并导出数据、图表与姿态动画 | [GSHC 指南](docs/public/GSHC/README.md) |
| **FLP** · Flight Log Processor | 精确配对日志与解码器，检查完整性，查看轨迹、曲线与滤波器内部数据，离线复算、比较并导出分析结果 | [FLP 指南](docs/public/FLP/README.md) |

### SCG：从配置到工程

SCG 提供完整、标准、轻量和最简四种配置档位。可配置设备与接口、安装方向、校准/初始对准、导航参数及遥测任务；导航组件包括 Pure INS、SF6、KF6 和 ESKF15。设备与算法以声明式插件组织。FCCG 是 SCG 的历史名称，`silverstar_fccg` 包名与旧入口继续兼容。

**设备与功能档位**：图中为 FINAL 项目的真实配置，包括 JY901、NEO-M9N 及各自接口选项。

![SCG v0.1.2：设备、接口与功能档位](docs/public/assets/v0.1.2/scg_final_devices.png)

**导航配置**：按项目能力选择导航源，设置校准、初始对准与融合算法参数。

![SCG v0.1.2：导航源、校准和初始对准](docs/public/assets/v0.1.2/scg_final_navigation.png)

**工程生成入口**：识别板卡与 MCU，检查 CubeMX 硬件资源，再生成/更新飞控工程及对应解码器。图中展示入口与硬件信息，未执行生成或烧录。

![SCG v0.1.2：硬件资源与生成/更新飞控工程](docs/public/assets/v0.1.2/scg_final_generation.png)

### GSHC：飞行监测、三维姿态与导航曲线

GSHC 将预飞行准备、飞行监测和后期处理放在同一界面：查看设备准备状态与任务事件、观察三维姿态和导航数据、保存 JSONL 会话，并按需导出摘要、数据、图表和姿态动画。

图中为正式 v0.1.2 的“飞行”页：左侧三维姿态与右侧 E/N/U 速度、位置曲线来自 `000062` 的 Recorded 数据，展示约 60–70 秒的窗口。该画面是未连接设备的离线显示演示；日常实时监测使用地面站遥测。

![GSHC v0.1.2 飞行页：000062 离线记录驱动的三维姿态与六路导航曲线](docs/public/assets/v0.1.2/gshc_flight_recorded_000062.png)

### FLP：轨迹、曲线与离线分析

FLP 使用原始日志和精确匹配的 `.ssdecoder`，显示 **Recorded** 数据的完整性、任务事件、位置/速度/加速度/角速率/姿态及滤波器内部通道。时间窗口可在全程与局部区间间切换；三维回放将姿态与 ENU 轨迹放在一起查看。离线复算、What-if 和主辅结果比较使用各自的分析数据源。

导出可选择概览、诊断、事件、CSV、图表/三维轨迹 PNG 和飞行回放 GIF，便于后续分析与分享。下面的图均选用原始 **Recorded · KF6**，没有用复算替换记录值。

**水平轨迹 · 主要案例 `000062`**：颜色表示相对高度，并标出起点、开伞事件与终点。

![FLP v0.1.2：000062 Recorded 水平轨迹](docs/public/assets/v0.1.2/flp_000062_recorded_plane.png)

**三维姿态与轨迹 · `000062`**：查看任务范围内的姿态、ENU 路径及事件位置。

![FLP v0.1.2：000062 Recorded 三维姿态和轨迹](docs/public/assets/v0.1.2/flp_000062_recorded_3d.png)

**速度曲线 · 独立参考 `000028`**：显示约 347.784 秒任务中的 E/N/U 分量；它使用 TEST_5 解码器，与 FINAL 案例分开解析。

![FLP v0.1.2：000028 Recorded 全程 ENU 速度曲线](docs/public/assets/v0.1.2/flp_000028_recorded_velocity.png)

[三工具图解](docs/public/V0_1_2_WALKTHROUGH.md)提供操作步骤、`000062` 全程速度曲线及两组记录的来源说明。截图来自正式 **v0.1.2** 程序文件；这些历史台架、手持与抛体记录用于展示工具流程，不是火箭飞行验证。

## 示例与文档

[无需硬件体验与示例下载](docs/public/examples/README.md)提供 FINAL 的 `000062` 主要案例及 TEST_5 的 `000028` 独立参考，每个压缩包只含原始日志和对应解码器，并附校验值与版本来源。样例需单独下载，不在 Windows 便携包内。

FLP 要求原始 `.BIN` / `.sslog` 与 Descriptor 身份匹配的 `.ssdecoder`，缺包或身份不符会报告错误。Recorded 表示实际记录值；复算与 What-if 是独立分析结果。请保留原日志和解码包，将导出写入新目录。

| 从这里开始 | 内容 |
|---|---|
| [三工具操作路线](docs/public/USER_WORKFLOW.md) | 配置、生成、地面监测、离线分析与导出 |
| [Windows 包说明](docs/public/WINDOWS_PACKAGE.md) | 运行目录、数据位置和外部工具 |
| [公共文档索引](docs/public/README.md) | 各应用使用说明、插件、API 与共享契约 |
| [支持矩阵](docs/public/SUPPORT_MATRIX.md) | 硬件组合、配置起点与验证范围 |
| [导航实现](docs/public/algorithms/NAVIGATION_IMPLEMENTATION.md) · [公式 PDF](docs/public/math/navigation-models.pdf) | 算法实现、坐标、符号与假设 |
| [发布介绍与教程](https://www.kechuang.org/t/92068) | v0.1.2 功能介绍和实测案例 |

## 稳定发布与开发

下载使用以 [v0.1.2 Release](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2) 为准，精确源码由 [v0.1.2 标签](https://github.com/aleistercrowleybeast666/SilverStar/tree/v0.1.2) 固定。远端 `main` 以该版本为基线，文档可继续更新。**0.1.3 开发线尚未发布**；源码版本由根 `VERSION` 标识。

开发版本统一登记于[版本清单](versions.json)，唯一手填产品号仍在根 `VERSION`。运行 `python -B tools/silverstar_version.py` 可查看解析后的应用、协议、格式和插件版本；规则与兼容边界见[版本管理](docs/public/shared/VERSION_MANAGEMENT.md)。

v0.1.2 的实测配置包括 STM32F407 飞控和 STM32F103 串口地面站，覆盖台架、手持与抛体采集，尚不构成火箭飞行验证。原生 USB CDC 的 F103/C071 路径仍属实验范围，普通生成入口受限，尚未完成对应 USB 硬件的上板验证。磁力计工作流、InEKF、维护协议等 0.1.3 开发内容以各自说明和验收状态为准。Android 保持开发版及真实 USB/控制门禁，DeviceService 是 mock-only 原型；两者均不在 v0.1.2 桌面包内。

各项检查的适用范围见[版本与证据边界](docs/public/shared/VERSIONS_AND_EVIDENCE.md)和[软件验证说明](docs/public/SOFTWARE_VERIFICATION.md)。

当前开发线已完成离线基线整理。飞行配置现在可创建默认七阶段的无控任务模板（就绪、任务开始、动力上升、滑行、开伞请求、下降、落地），按需插入自定义阶段、调整顺序，并选择将 START 与起飞检测分开或显式合并。原生工程、`.ssmission` v2、GSHC 离线查看及 FLP 精确 decoder 声明已接通；共享参考解释器可输出摘要匹配的 `.ssmissiontrace`。**新阶段尚未绑定固件执行，带该流程的固件生成会明确拒绝**；原固件流程与已有参数保持原路径，不能把桌面参考记录当作板端 Recorded。[任务过程与后续接入](docs/public/shared/MONOREPO_ARCHITECTURE.md)

机体系采用固定导航点 O、+z 朝鼻锥、+x 朝舱门径向基准、+y=z×x 的右手系。无下标 xyz（兼容旧 XYZ）均表示箭体系；设备原生轴使用 s_i 下标，导航系用 E/N/U。主 IMU 可以非零，安装分布图使用实际位置；原始 IMU 可以配置鼻锥轴及舱门轴。逐设备杆臂补偿尚未启用，旧安装基准保持原义。[坐标定义与公开参考](docs/public/algorithms/NAVIGATION_IMPLEMENTATION.md)

ESKF20、InEKF15、InEKF20 已开放选择、生成及实验构建，不再以缺少已验证时序为由禁止构建；明确标记硬件/时序/飞行未经验证。初值、协方差、噪声与物理模型约束仍须配置，构建成功不代表运行初始化或飞行验收通过。

合成案例（参考事件序列，不是飞行数据；输出路径须不存在）：

```powershell
New-Item -ItemType Directory -Path .work -Force | Out-Null
.\.venv\Scripts\python.exe -B tools/replay_mission_process.py apps/SCG/examples/Uncontrolled_Desktop_Reference.ssmission apps/SCG/examples/Uncontrolled_Reference_Events.jsonl .work/uncontrolled_demo.ssmissiontrace
```

配套原生工程在 `apps/SCG/examples/Uncontrolled_Desktop_Reference.ssproject`。在 SCG 打开后先另存到自己的工程目录再编辑；当前每阶段一个进入条件，尚无组合条件或分支。GSHC 可打开快照及同摘要的参考 trace；FLP 从精确 decoder 读取配置后才接受匹配 trace。配置快照基础曾通过 744 项检查，后续增量检查及 H7 待测清单见[版本与证据边界](docs/public/shared/VERSIONS_AND_EVIDENCE.md)。

### 从源码运行

稳定源码请从 v0.1.2 标签下载；开发检出使用其自身版本和文档。要求 Python 3.11+，在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe SCG.py
.\.venv\Scripts\python.exe GSHC.py
.\.venv\Scripts\python.exe FLP.py
```

每条启动命令分别运行一个应用。需要测试与打包依赖时使用 `tools/setup_venv.ps1`；固件编译工具链单独安装，见[构建说明](docs/public/SCG/BUILD.md)。

## 反馈与许可

欢迎通过 [GitHub Issues](https://github.com/aleistercrowleybeast666/SilverStar/issues) 提交问题和建议。请附软件版本、相关硬件配置、复现步骤与日志；日志解析问题请同时附上匹配的 `.ssdecoder`。

原创 SilverStar 源码使用 [Apache License 2.0](LICENSE)。第三方代码和依赖保留各自条款；SX1280 库来源、修改与尚未解决的许可事项见[第三方来源与许可](docs/public/licenses/README.md)。
