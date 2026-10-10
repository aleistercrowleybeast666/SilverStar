# SilverStar 0.1.2

SilverStar 是面向火箭航电开发的三应用软件套件。此分发提供 Python 源码、界面资源、声明式插件及生成模板，适合在 Windows 上配置项目、查看地面站数据、解析与重算飞行日志。

| 应用 | 用途 | 根目录入口 |
|---|---|---|
| SCG（System Configuration & Generation） | 配置设备、导航、协议与 Flight/Ground 硬件；生成项目和构建配置 | `SCG.py` |
| GSHC（Ground Station Host Computer） | AIR M0 地面站界面、接收状态、命令与日志/图表导出 | `GSHC.py` |
| FLP（Flight Log Processor） | exact decoder 日志打开、Recorded/Recomputed/What-if 分析、图表及数据导出 | `FLP.py` |

**0.1.2 是本次本地准备的软件源码分发版本。** 包内不提供 Windows EXE、安装器、Python/Qt、Arm 工具链、CubeMX SDK 或已验收的最终固件。软件检查的通过范围见下文；本版本没有新增连接硬件、烧录或飞行验收。USB Ground 的普通生成入口仍保持阻断，不能作为通用可用 CDC 产品交付。

当前版本以根目录 `VERSION` 为准。历史子文档中的 0.0.x/0.1.0 是当时快照，不覆盖本版本；AIR M0、SSLOG 0.0、`.ssdecoder` 1.2、导航 revision 和第三方库各有独立版本。FCCG 是 SCG 的历史名称；`silverstar_fccg` Python 包及旧项目身份继续兼容。

公共文档统一入口：[docs/public](docs/public/README.md)，包含跨工具流程、教程、API/插件、原理与实现公式。旧文档路径保留兼容入口；历史验收与原始数据不随公共文档分发。

## 快速开始：安装与启动

推荐 Windows 10/11、Python 3.11 或以上、可写的解压目录。实际离线启动验证使用 Windows、Python 3.14.0、PySide6 6.10.1、NumPy 2.4.1、matplotlib 3.10.8、pyqtgraph 0.14.0、pyserial 3.5。Python 3.11 是声明的最低版本，本轮没有另建 3.11 环境验证。依赖是版本范围，未提供锁定环境；首次安装需要从配置的 Python 包源下载依赖。

在解压后的 **SilverStar 根目录** 打开 PowerShell。最小运行环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe SCG.py
.\.venv\Scripts\python.exe GSHC.py
.\.venv\Scripts\python.exe FLP.py
```

每个启动命令分别运行一个应用。若需要开发/测试依赖，可用已有脚本：

```powershell
.\tools\setup_venv.ps1
```

脚本创建根 `.venv` 并安装 `.[dev]`，包含 pytest、PyInstaller 等；它不是 EXE 打包命令。若脚本执行策略阻止运行，可执行前述两条安装命令。始终使用 `.venv\Scripts\python.exe` 可避免系统 Python 与已安装依赖混用。本分发不含应用子目录的 `.venv`；已有完整仓库若含 `apps/SCG/.venv` 或 `apps/FLP/.venv`，对应入口会优先切换到该环境，排查依赖时应检查实际解释器。

SCG/FLP 可检查产品版本及帮助：

```powershell
.\.venv\Scripts\python.exe SCG.py --version
.\.venv\Scripts\python.exe FLP.py --version
.\.venv\Scripts\python.exe FLP.py --help
```

SCG/FLP 支持 `--lang zh_CN` / `--lang en_US` 和 `--theme light` / `--theme dark`。GSHC 使用窗口内语言/主题设置，没有同等的 `--version` 参数。

GSHC 当前默认用户数据目录是 `D:/SilverStar_GSHC_Data`。没有 D 盘或需要自选位置时，**启动前**指定可写目录，例如：

```powershell
$env:SILVERSTAR_GSHC_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'SilverStar_GSHC_Data'
.\.venv\Scripts\python.exe GSHC.py
```

应用会保存设置、缓存或运行日志，解压目录及所选数据目录应可写。SCG 的源码工作区设置位于应用工作区，FLP 使用 Qt 用户设置与应用日志目录。不要将不可写的系统安装目录当作项目输出目录。

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

## GSHC：地面站与数据阅读

GSHC 使用 AIR M0 协议与实际命令/状态机。正式连接需要匹配的地面站固件、传输配置与硬件；源码启动可在没有设备时进行。选定连接类型、端口及参数后，依照真实状态操作。**ACK 只表示命令应答，不表示 Calibration/Alignment 已 READY**，也不代替 START 前置条件。

串口/协议处理在工作线程执行，接收和记录使用有界队列与诊断。日志/图表导出受选定时间范围及真实数据可用性限制；显示的导航位置、轨迹和状态来自接收的数据与定义的处理，不是外部位置真值，也不构成飞行精度证明。AIR 遥测不是 SSLOG 飞行日志，不能将遥测字节交给 FLP 冒充同格式日志。

默认不附带实测数据、串口配置、用户目录或连接脚本。软件验收的离线启动禁用端口枚举并阻止打开串口；因此它证明窗口/事件循环/退出生命周期，不证明实际连接和设备通信。

## FLP：输入、exact decoder 与项目

输入必须是 **一个** `.BIN` / `.sslog` 日志，以及与其 Descriptor 身份精确匹配的 `.ssdecoder` 1.2。不要重命名不同 decoder 来尝试匹配。生产打开统一经 `LogOpenCoordinator`，不提供 Descriptor-less、旧 decoder 1.0、固定默认 parser 或文件名猜测回退。

推荐从 FLP 的 **Open SilverStar Project Folder** 打开 SCG 项目根：使用根 decoder，逐个选择 `Log/` 中日志。也可手动导入一组日志/decoder，或打开 `.ssflp` 项目；后者保留源文件引用、解码身份、重算参数与界面状态，不嵌入或覆盖源日志。源日志与 decoder 按只读输入处理。

目录结构示意（仅格式示意，不是随包实测样例）：

```text
MyProject/
  SilverStar.ssproject
  MyProject.ssdecoder
  Flight_Controller/
  Ground_Station/
  Log/
    flight.BIN
    flight_Export/
```

带明确文件对启动 GUI（把示例路径改为自己的文件）：

```powershell
.\.venv\Scripts\python.exe FLP.py .\MyProject\Log\flight.BIN --decoder .\MyProject\MyProject.ssdecoder
```

本源码包通过根入口启动 GUI；FLP 包的 CLI 可直接从 `src` 运行，不需要假设根安装已注册 `sslog`：

```powershell
$env:PYTHONPATH = (Resolve-Path .\apps\FLP\src).Path
.\.venv\Scripts\python.exe -m silverstar_flp.cli --help
.\.venv\Scripts\python.exe -m silverstar_flp.cli inspect .\MyProject\Log\flight.BIN --decoder .\MyProject\MyProject.ssdecoder
.\.venv\Scripts\python.exe -m silverstar_flp.cli export .\MyProject\Log\flight.BIN .\MyProject\Log\flight_Export --decoder .\MyProject\MyProject.ssdecoder --language zh_CN --theme light
```

上述 inspect/export 需要真实匹配输入，本次分发不附带用户日志，解压烟测只执行 CLI 帮助与空窗口启动。安装 FLP 独立包才会注册其 `sslog` 命令；根 `pyproject.toml` 安装运行依赖，不自动安装全部应用的 CLI 入口。

Recorded 是日志实际记录值；Recomputed 使用实际记录配置；Offline 使用插件离线默认值；What-if 使用明确修改的参数。缺失实际配置不能自动用离线默认值补成 Recorded。分析数据源只发布完整、成功的 run，缺输入须显式报告不可用，不能偷偷换到 Recorded。`EXACT` / `APPROXIMATE` / `UNAVAILABLE` 是重算保真度状态，不是导航位置真值评价。

各通道保留真实采样时间，不按名义频率重建时间轴或强制拼成一张等频表。导出采用选择的数据源与范围；不同采样率通道、数据空白、原始时间倒退和损坏诊断均应保留其语义。常用输出含逐通道 CSV、PNG 和 GIF；可选择导出语言、主题与目录，实际缺数据的项目明确说明。

### 水平/垂直 GNSS 图为何不同

当前 revision 3 的水平闭合误差来自记录的 `NAV_QUALITY`：10 秒窗口、两队列交错、每 5 秒完成一个窗口。高频重复记录的是上一个完成结果，因此 Recorded 水平图按完成结果保持为阶梯。`variance_scale` 是位置测量 **方差** 倍率，不是误差，也不是标准差倍数。

垂直图由 FLP 对 `GNSS_NATIVE` 原始高度/垂直速度独立积分，随真实样本更新；参考重置、断流等形成分段。它没有使用相同的 10 秒/5 秒水平窗口，灰色重置线不等于固件拒绝事件。两图不能直接横比数值或据此断言水平/垂直精度；不应为美观插值阶梯值。完整解释见 [FLP 使用文档](docs/public/FLP/APP_README.md)，其中旧版本段落须按开头的版本说明阅读。

公式文档可直接读[15页PDF](docs/public/math/navigation-models.pdf)，维护源见[模块化TeX入口](docs/public/math/README.md)，涵盖惯导、SF6/KF6/ESKF15的实际实现、坐标、符号、假设和源码版本。

## 插件与开发接口

SCG 插件是 `apps/SCG/plugins/builtin/<name>/plugin.json` 及对应 payload：清单声明身份、能力、依赖、源图、资源与生成边界。保留声明式所有权，禁止给未知目标套默认 CPU/IRQ 或拷贝用户项目覆盖源。源码 API 位于 `apps/SCG/src/silverstar_fccg/plugins/`；builtin 是随版本的参考组件，installed 为用户显式安装内容。

FLP 的解码包是声明式数据，不执行包内 Python。容器插件与算法插件的可信接口位于 `apps/FLP/src/silverstar_flp/plugins/api/`。`.ssplugin` 安装需用户明确信任、主机 allowlist 和重启；它不是在线任意代码商店。GSHC 的协议/transport/services 分层位于 `apps/GSHC/`。共享机器契约位于 `contracts/`；修改跨组件协议时应同步核对生产与消费端。

## 验证状态与 Power of Ten

合并后的三应用版本曾完成 **25 项针对性 Python 检查，0 失败、0 跳过**，以及三套实际应用窗口的离线事件循环/退出烟测。针对性范围覆盖 SCG MCU catalog/导入文档、GSHC AIR epoch/deploy 标记/2D 可见性/阈值、FLP GNSS 导出输入依赖/记录窗口/重算时间轴；不能写成全仓库测试全过。解压包自己的检查结果及文件 SHA256 另存于分发旁的 receipt。

此前 SCG 受影响模块验收为 639 passed、10 skipped，另有 28 个正常软件 gate；10 个真实 ARM Release fixture 缺失的 maintenance 检查仍是跳过。更早固件实际构建记录只证明各自记录的源码、配置、工具与产物；本轮没有重新归属旧二进制给最终 tag。

项目的 PoT 检查采用 **F Prime-inspired 项目文本适配**，不宣称严格原始 Power of Ten 符合或 NASA 认证。checker 成功不能代替人工核对关键输入/状态/容量/生命周期契约；critical-contract review 明确为 **NOT PROVEN**。栈路径、ISR 嵌套、间接调用、库、动态帧、WCET 与板级行为仍需独立证据。保留所有配置、安全边界与失败返回，不能删检查来凑 PASS。

## 许可证与分发内容

原创 SilverStar 源码使用根 [Apache License 2.0](LICENSE)。第三方材料保留自己的版权头和条款：FreeRTOS MIT、CMSIS Apache-2.0、ST HAL/device 相应包条款、FatFs 文件头条款、Bosch 相应 BSD 条款等，均不能被根 LICENSE 改写。

当前补充候选已加入经核实的 ST HAL 完整许可正文、CMSIS/startup 与 C071 SLA0044 来源映射，详见 [第三方来源与许可材料](docs/public/licenses/README.md)。独立核对已补足两份 HAL 配置头、F4 syscalls/sysmem 及 C0 适配映射，并附 ST 工具原始 SLA0048。Semtech SX1280lib 的25个文件对应原始版本/`LICENSE.TXT`，以及38个 board 生成模板的适用许可仍未闭合；不能宣称已完成公开分发许可核验。第一方准确权利人署名是待确认项，不等同于已证明的公开禁令。当前仅本地候选，不附 Python/Qt 二进制；Windows EXE/安装器许可审计未执行。详见 [本版分发说明](docs/public/releases/0.1.2.md)。

包采用文件白名单，不含 `.git`、`.venv`、缓存、临时目录、开发验收证据、原始用户日志或用户项目，也不附带固件最终交付物。来源路径字段的可移植处理以及文档链接范围会逐项记录在 `RELEASE_MANIFEST.json`；源文件及分发内容分别计算 SHA256，不能将处理后的元数据谎称与 Git blob 完全一致。

## 常见问题

- **找不到 PySide6/NumPy 等模块：**确认用根 `.venv\Scripts\python.exe`，检查已有应用本地 `.venv` 是否接管了入口。NumPy 2.4.0 已在依赖声明中排除，勿用该版本。
- **FLP 启动报告数值运行环境错误：**依照实际错误检查 NumPy 与相关数值依赖；不要略过 runtime 验证。
- **项目导入或生成失败：**检查原生 CubeMX 文件闭包、确切芯片/资源与插件组合。未知目标和被阻断的 USB 候选不能靠改名通过。
- **Build & Checks 找不到工具：**安装并配置对应 Arm GNU/Make/Host GCC；安装 Python 依赖不会安装 MCU 工具链。
- **日志打不开：**提供匹配的 decoder 1.2 与 Descriptor，检查源完整性。日志损坏、未知记录、CRC 恢复与截断会产生诊断，不会修复或重写输入。
- **某图/导出不可用：**检查选定 Analysis Source、输入通道与有效时间范围；没有实际数据不能用其他源暗补。
- **GSHC 数据目录不可写：**启动前设置 `SILVERSTAR_GSHC_DATA_ROOT`，或在应用设置选择可写目录。
- **没有连接硬件却无实时数据：**正常；本包的离线软件启动验证不生成真实遥测，不等同串口/无线/飞行验证。
