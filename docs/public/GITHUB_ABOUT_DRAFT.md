# GitHub About 修改草案 / GitHub About draft

本文件保存本轮 About 文案及应用记录。目标仓库：[aleistercrowleybeast666/SilverStar](https://github.com/aleistercrowleybeast666/SilverStar)。

This local file records this revision's About wording and application. Target repository: [aleistercrowleybeast666/SilverStar](https://github.com/aleistercrowleybeast666/SilverStar).

## 当前状态 / Current state

2026-10-19 获得针对本轮 18 文件及 About/topics 的明确发布批准后，已应用下列 256 字符中英合并描述与 14 个 topics，独立远端查询回读一致。主页保留 v0.1.2 Release 地址；默认分支为 `main`，Issues 已开启。

After explicit approval for this revision's 18 files and About/topics on 2026-10-19, the 256-character bilingual description and 14 topics below were applied and independently read back successfully. The homepage remains the v0.1.2 Release; the default branch is `main`, and Issues are enabled.

## 描述 / Description

中文：

> 无控探空火箭航电工具链：SCG 配置与 STM32 工程生成；GSHC 地面遥测与三维姿态；FLP 轨迹/曲线分析、离线复算与数据导出。

English:

> Open-source sounding-rocket avionics: SCG configuration and STM32 project generation; GSHC telemetry and 3D attitude; FLP trajectory/chart analysis, offline recomputation and data export.

建议单个 About 字段使用以下中英合并版本，内容与两种语言的 README 对等：

Suggested combined text for the single About description field, equivalent to the two README introductions:

> 无控探空火箭航电工具链：SCG 配置与 STM32 工程生成；GSHC 地面遥测与三维姿态；FLP 轨迹/曲线分析、离线复算与数据导出。 Open-source sounding-rocket avionics: SCG configuration and STM32 project generation; GSHC telemetry and 3D attitude; FLP trajectory/chart analysis, offline recomputation and data export.

## 主页 / Website

建议指向当前稳定版下载入口：[SilverStar v0.1.2](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2)。发布介绍与教程继续由 README 提供入口。

Use the stable download page: [SilverStar v0.1.2](https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2). Keep the release article and tutorial linked from the README.

```text
https://github.com/aleistercrowleybeast666/SilverStar/releases/tag/v0.1.2
```

## Topics

```text
sounding-rockets
avionics
stm32
embedded
telemetry
ground-station
flight-data-analysis
code-generation
python
pyside6
inertial-navigation
sensor-fusion
data-visualization
trajectory-analysis
```

共 14 个 topics，保留现有十项并增加惯性导航、传感器融合、数据可视化与轨迹分析。对应 v0.1.2 导航配置、Recorded 轨迹/曲线及正式导出选项；FFT/频谱未找到稳定版入口，不加入描述或 topics。USB、Android、磁力计、IEKF 和维护协议的开发状态不作为稳定发布能力。

The 14 topics retain the existing ten and add inertial navigation, sensor fusion, data visualization, and trajectory analysis. They correspond to v0.1.2 navigation configuration, Recorded trajectories/curves, and release export options. No stable FFT/spectrum entry point was found, so it is omitted. USB, Android, magnetometer, IEKF, and maintenance development work are not presented as stable release features.

## 应用范围 / Application scope

本轮已按明确批准应用描述与 topics，主页没有改动。About 字段不属于 Git 提交内容，文案与回执保留在本地；v0.1.2 标签及 Release 资产保持原样。本文件未随 18 个访客展示文件提交。

The description and topics were applied within the explicitly approved scope; the homepage was unchanged. About fields are separate from Git commits, and the wording/receipt remain local. The v0.1.2 tag and Release assets are unchanged. This file was excluded from the 18 published visitor-facing files.
