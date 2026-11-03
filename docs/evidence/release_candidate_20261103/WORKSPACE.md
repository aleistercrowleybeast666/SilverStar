# 本轮软件候选的工作目录

下列路径在原有 checkout 内或单独的 Windows 构建临时目录。未清理既有 `.work`、输入工程、原始文件或旧版本包。

| 所有者和用途 | 本地位置 | 保留证据 |
|---|---|---|
| 主集成，GSHC 方向、串口、FLP 与生成日志 | `D:/python_software/SilverStar/.work/0.1.3-release-20261103/root` | [串口](gshc/README_ZH.md)、[日志与显示](flp/README_ZH.md) |
| SCG 普通生成、真实工具链与 UI | 同一版本目录下的 `scg` | [逐目录所有权](scg/workspace-inventory.json)、[实际构建](scg/README_ZH.md) |
| 传感器、GNSS、持久化和运行时 | `D:/python_software/SilverStar/.work/release-20261103/sensors` 及分项记录中的 Host 目录 | [完整位置](../release_20261103/sensors/work-inventory.json) |
| 便携包的 Analysis、COLLECT 和独立解压核实 | `D:/python_software/SilverStar/.work/0.1.3-release-20261103/packaging`、`%LOCALAPPDATA%/Temp/SilverStar-RC-20261103`；解压测试用 `%LOCALAPPDATA%/Temp/sr1103q` 与 `sr1103r3` | [构建命令](build_candidate.ps1)、[逐文件验证器](verify_portable.py) |
| 最终 Windows 交付 | `D:/python_software/SilverStar/dist/rc1103c` | 压缩包内 `CANDIDATE_MANIFEST.json` 及报告所链 SHA-256 收据 |

初次收集的临时绝对路径太长，Win32 返回 206。第一份中间包用于发现 GSHC 的缺件，下一次打包在修复规则前停止。核对中间包原 ZIP、清单内全部文件并确认中断目录为空后，将两处输出原样移入任务专属工作区。当前 `dist/rc1103c` 是交付目录。复验时对用户交付包另行解压，避免把程序首次运行产生的设置带进 ZIP。[中间产物转存收据](packaging/intermediate-moves.json)
