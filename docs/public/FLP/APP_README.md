# SilverStar FLP 0.1.2 使用说明

FLP 是只读日志解析、导航重算、比较与导出应用。产品版本取根 VERSION；`.ssflp` 项目仍为 **v3**，SSLOG container 仍为 **0.0**，exact `.ssdecoder` 与 project semantics 为 **1.2**，不随产品版本机械升级。

## 安装和启动

从源码根执行[根 README](../../../README.md)的共享环境安装，然后运行：

```powershell
.\.venv\Scripts\python.exe FLP.py
.\.venv\Scripts\python.exe FLP.py --version
```

本分发不提供 EXE、安装器、Python/Qt 或用户日志。

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


## 界面、工程与数据源

五页为 Overview、Replay、Flight、State Estimation、Data Explorer。Replay 管理每次算法 run 及主数据源、可选副数据源；Flight/State Estimation 展示所选来源。主副 run 身份独立保存；导出冻结主数据源、时间范围和选项，不把副数据源暗补到缺失主数据。每次 What-if 或 Offline 重算都有自己的参数、输入来源、保真度和诊断。

`.ssflp` v3 包含一组源 log/decoder 引用、精确身份、参数、notes 与 UI state，并可选择保存经过校验的 parse/result 数值工件。工件为有界数据文件及 lossless gzip，非 pickle/可执行代码；原始 log/decoder 不嵌入或改写。保存先写未引用 generation、flush/fsync、读回校验，再原子替换项目。缺失或坏结果不触发自动数值重算，坏 parse cache 经同一 exact coordinator 回读源日志。

保存、取消、关闭等待与重开都以实际提交状态为准；阶段百分比不等于持久化成功，100% 在完整提交和 GUI 发布后出现。Windows 内部工件路径可能比项目文件名更长；全面长路径支持仍未完成，失败时选择短目录/工程名并保留原输入和旧工程。

## parser 与插件

容器解析只认识有界 SSLOG0 framing；字段、单位、通道、实例及语义由匹配 decoder 给出。未知 CRC-valid 类型/version 保留 raw 并报告 partial，损坏区间与时间空白显式诊断，不修补输入。动态算法和可视化元数据通过受控 API 提供，decoder 不执行 Python。

阅读[SSLOG](SSLOG.md)、[decoder](Decoder_Profile_Package.md)、[数据模型](Data_Model.md)、[工程格式](Project_Format.md)、[数值工件](Project_Artifacts.md)、[Replay](Replay.md)、[容器 API](Log_Container_Plugin_API.md)、[算法 API](Algorithm_Plugin_API.md)、[显示质量](Display_DataQuality.md)和[架构](Architecture.md)。惯导/SF6/KF6/ESKF15 的实现与公式从[算法入口](../algorithms/NAVIGATION_IMPLEMENTATION.md)阅读。

EXACT 要求匹配的不可变 Golden 与声明区间内完整有效输入。exact decoder 身份不能自行升级数值 fidelity；旧 SILV0008 / 固件 0.0.10 等身份对应的历史 APPROXIMATE 结论保留，不外推为当前全部算法均通过或均失败。

## GNSS 水平与竖直一致性图的读法（当前 revision 3）

水平图呈阶梯、竖直图呈连续折线，首先反映的是**统计口径和输出节奏不同**。
不能仅凭外观判断算法正常，也不能把两图的数值直接当作同一窗口下的误差比较。
以下说明对应当前 revision-3 窗口证据与 FLP 的离线竖直诊断。

### 水平的两个图分别是什么

| 图 | 显示的量 | 单位与含义 |
|---|---|---|
| 水平上图 | `NAV_QUALITY.closure_norm_m` | 米；GNSS 水平位置变化减去同一窗口内水平速度积分后，EN 闭合向量的模长 |
| 水平下图 | `NAV_QUALITY.variance_scale` | 无量纲；窗口对水平位置测量**方差**的倍率，不是第二条误差，也不是另一个方向的闭合量 |

水平闭合量可写为：

```text
closure_EN = p_EN(t_end) - p_EN(t_start) - integral(v_EN, t_start, t_end)
c = norm(closure_EN)
```

它检查接收机的位置变化与速度积分是否自洽，**不是相对真实位置的绝对导航误差**。

当前窗口方案为两个 10 秒窗口序列，起点错开 5 秒。例如，序列 A 为
`[0,10]、[10,20]、…`，序列 B 为 `[5,15]、[15,25]、…`；这里的 0 只是监测起点示意，
不是所有日志的 START 或 GPS 时间零点。两个序列合起来每 5 秒完成一个窗口。
图上两个上下子图并不分别代表 A、B：上图画最近完成窗口的闭合量，下图画其方差倍率。

窗口完成后才发布新的统计结果；两次完成之间保留上一份可用结果。
因此即使 `NAV_QUALITY` 约以 25 Hz（约 40 ms 一条）记录，也不代表每 40 ms 计算出
一个新的 10 秒窗口结果。**25 Hz 是记录节奏，5 秒一次（约 0.2 Hz）是此窗口方案的统计更新节奏。**
Recorded 水平图使用向后保持的阶梯绘法，表现日志中真实保持的值；它没有漏做区间计算。
首次完成窗口前没有有效闭合证据，图中的空白不能解释成误差为零。

下图的当前窗口倍率关系为：

```text
k_R = min(k_max, max(1, (c / H)^2))
```

其中 `H` 为该日志的闭合误差加权门限，`k_max` 为配置的倍率上限。
000062 的 `H = 10 m`、`k_max = 4`。闭合量不超过 10 m 时，该倍率保持 1；
超过门限后才增大，所以倍率图常比闭合图更长时间保持水平。
这是**方差/协方差 R 的倍率**，不是标准差的倍率；对应标准差倍率为 `sqrt(k_R)`。
这项只表示窗口贡献的倍率，不应当作包含接收机质量、卫星数、NIS 等其他调权后的总倍率，
也不应把它当作融合拒绝状态。无效或过期窗口应结合有效性标记解读，不能只看倍率是否为 1。

### 竖直图为何逐样本变化

当前竖直图由 FLP 使用 `GNSS_NATIVE` 和记录的有效 GNSS 原点，在离线环境中独立计算：

```text
vertical_residual(t) = U(t) - U(t_ref) - integral(v_U, t_ref, t)
```

每个可用原生样本都更新积分及残差；000062 的接收间隔约为 40 ms，FLP 用普通折线连接
这些实际样本。因此它看起来是密集曲线。**当前这项竖直诊断没有采用水平相同的
10 秒窗口、5 秒错开方案**，而是从当前参考点累计，直到连续性条件触发参考重置。

无效垂直速度、来源或 replay epoch 改变、序列不连续、时间倒退，以及超过配置最大间隔
（000062 为 120 ms）等情况会重置离线积分链和局部参考。
竖直图的灰色竖线表示这种**离线局部参考重置**，不等同于固件 GNSS 断流或融合拒绝事件。

水平窗口内部以原生 GNSS epoch 积分，横轴使用记录的 MCU `evaluation_us`；
竖直诊断使用可信样本时间，否则使用接收时间。二者除了窗口长度不同，时间选择也不同。
所以不能直接横比两图数值大小、把竖直累计漂移与水平最近 10 秒闭合量当作同一统计量，
或据此推断某一轴精度更高。

### 000062 的原始记录核对实例

已有 000062 日志含 3390 条 revision-3 `NAV_QUALITY`，其中 3140 条标记为有效证据，
但只有 **26 个不同的完成窗口**。26 个窗口的 `window_end_us - window_start_us`
全部为 `10,000,000 us`，相邻完成窗口结束时间全部相差 `5,000,000 us`，窗口索引 0、1 交替。
重复记录保持的是同一窗口结果，不是 3390 份独立完成窗口。

| 从 START 起的记录时间 | 水平闭合量 | 窗口方差倍率 |
|---|---:|---:|
| 75.070 s | 11.70554 m | 1.370197 |
| 80.072 s | 15.71896 m | 2.470857 |
| 85.072 s | 8.223319 m | 1.000000 |

这些窗口字段、闭合量和倍率已与 exact `.ssdecoder` 定义及原始记录载荷核对。
日志 SHA256 为 `7ba89a60127a027adc28623cfb4b5e4898c72b99fd0374d58d59154633c89218`；
decoder SHA256 为 `47394c9d1b27f76e074ce43b324dd218e3448c6a5465628fdce2c744e3afe0e5`。
以上是已有日志的读图实证，不是新硬件试验、位置真值验证或飞行安全结论。

### Recorded 与离线诊断的边界

Recorded 水平图读取飞控记录的 revision-3 `NAV_QUALITY`，不以接收机原生数据重新计算
并替换这些值。选择 Recomputed/What-if 时，水平图只使用该所选运行提供的 completed
`window_evidence` 和明确的 MCU 时间映射，按完成窗口点显示；没有证据时显示不可用，
不借用 Recorded 的结果。竖直图则是独立的接收机原生离线诊断，不是记录的固件加权或拒绝决策，
也不参与固件/KF6/NIS 的计算。

解读时保留水平阶梯和真实数据空白；**不要用插值或平滑把保持值美化成连续曲线**，
否则会掩盖实际更新时刻并制造不存在的中间统计结果。若需要水平和竖直使用同一窗口口径，
应另行定义诊断指标，不能靠更改绘图方式实现。

实现依据：[水平记录显示模型](../../../apps/FLP/src/silverstar_flp/analysis/gnss_integrity_display.py)、
[GNSS 页面绘图](../../../apps/FLP/src/silverstar_flp/ui/gnss_integrity.py)、
[离线竖直计算](../../../apps/FLP/src/silverstar_flp/analysis/gnss_vertical_consistency.py)。
