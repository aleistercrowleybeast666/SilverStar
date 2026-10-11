# Windows 0.1.2 便携包

发布文件名为 `SilverStar_0_1_2_Windows_Portable.zip`，沿用 UNDERLINE 的版本下划线及 Windows_Portable 命名。`dist` 仅保留发布 ZIP；最新 `SHA256SUMS.txt` 和发布记录在独立交付目录，校验行使用此最终文件名。此次 ZIP 仅改名，字节内容仍是提交 `6feeadd000c866e456c08d5c85057d0f529d0993` 的已验证构建；后续标签提交只同步发布元数据，不重建 EXE。

包内为 `SCG.exe`、`GSHC.exe`、`FLP.exe`，以及单一共用 `_internal` 依赖/源码/资源目录和 `docs`。目标为 Windows 10/11 64位；Qt 使用操作系统提供的 ICU。无需另装 Python；SCG 的外部 Arm 编译工具链、CubeMX SDK 仍需用户单独提供。此包没有安装器，也没有最终固件。

完整解压到用户可写目录后启动相应 EXE。不要单独复制 EXE、删除 `_internal`，或把三套独立 dist 合并覆盖 DLL。三个程序来自同一构建环境，共用依赖；首次生成/导出时保持包及工作目录可写。可从任意当前工作目录启动，程序按 EXE 的相对目录找资源。

SCG 保留 `apps/SCG` 的工作区结构及 builtin 声明式插件，生成工程请选择包外的新用户目录。未知配置拒绝，普通 native USB 生成入口继续阻断，私有候选不是通用可用 CDC 交付。

GSHC 既有默认用户数据目录为 `D:/SilverStar_GSHC_Data`，本次未改程序。可在现有设置界面选数据目录，或启动前使用它已有的环境变量，例如 PowerShell：

```powershell
$env:SILVERSTAR_GSHC_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'SilverStar_GSHC_Data'
& '.\GSHC.exe'
```

FLP 正常打开日志仍须精确 `.ssdecoder` 和 Descriptor，通过 LogOpenCoordinator；不提供缺包回退。录制日志和原解码包保持只读，导出写入新目录。

`licenses` 保留本次实际依赖版本的上游许可/版权/字体材料及 Qt LGPL/GPL 原件、对应版本源码链接；根 Apache-2.0 只覆盖原创代码。Qt/PySide6/Shiboken 以共用动态 DLL 形式分发，保留替换这些库及调试修改库所需的权利；不要把第三方条款改写为 Apache。文件摘要、版本、打包命令、离线检查和未测范围以包旁 receipt 为准。

本机已有开发环境；不宣称纯净 Windows 机器验证。无硬件、串口连接、DAPLink、烧录、CONNECT 或 START。原源码候选和旧 receipt 保留，不能替代新 EXE 的检查。

本次实包已直接启动三个发布 EXE，检查 SCG 打开合成参考工程、GSHC 生成带模拟标记的日志、FLP 显示合成日志的 exact decoder 与 Recorded 数据；具体范围与退出状态见旁置 receipt。冻结 QA 的生成及导出检查单独记录，不能合称完整 GUI 验收。发布示例使用简体中文；程序语言可在既有设置中选择，无需修改程序。
