# GSHC 只读 SWD：源码 GUI 使用与核验，2026-10-14

Windows 原生 Qt 窗口的完整连接路径已核对：真实 Controller、SwdWorker 和默认
pyOCD 后端通过指定 Horco 显示身份及运行状态，断开、再次连接和连接中退出均释放。
本轮只修正了缺依赖提示，将旧的“缺少 OpenOCD 后端”改为通用 SWD 后端依赖提示。

## 用户启动入口

从 `D:/python_software/SilverStar` 打开终端运行：

```powershell
.venv/Scripts/python.exe apps/GSHC/main.py
```

这是当前 0.1.3 开发源码入口；冻结 v0.1.2 的发布 EXE 没有更新。
本机依赖已装在 `.work/dev013_swd_pyocd01/deps`，无需再次安装或修改系统 PATH，
也无需设置 `SILVERSTAR_SWD_PYOCD_PATH`。源码后端按自身文件位置找默认依赖目录，
不是只靠工作线程临时环境变量。目录缺失会显示 SWD 后端依赖缺失，并给出安装路径说明。
隔离依赖仍须保留；Git 不携带这份已安装运行时。

1. 在顶部 **SWD 调试器**中选择 `Horco CMSIS-DAP / FAED:4870 / 132765403520`。
   只有一个探针时可自动选中，但选择/枚举不连接飞控。完整 USB 身份在探针状态提示中。
2. 切换到 **运行诊断 / 日志**页，按 **连接 SWD 目标（只读）**。
   控件刷新最多约 500 ms，扫描未结束时须等待按钮启用。
3. 本台架显示 `STM32F405/407/415/417 | ID 0x413 REV 0x1007`、运行中、采样距今，
   同时保留 **固件符号未匹配 / 非原子读取**。连接中禁用再次连接、探针切换和重新检测。
4. 按 **断开 SWD 目标**，等待“目标未连接”及连接按钮重新启用。关闭窗口会取消
   当前读取并走同一释放路径；没有暂停、恢复、复位或刷写操作。

SWD 的运行状态不等于飞控 READY，不会替代维护串口或 AIR M0 的状态来源。
本轮测试没有连接顶部任何串口，也没有点击日志服务、校准、START 或执行器相关操作。
公开 Python API 约定见[首版接口文档](SWD_READ_ONLY_20261013.md#api-与-cli)，
CLI 示例见 [pyOCD / Horco 台架说明](SWD_PYOCD_BENCH_20261014.md)
的“本机使用与隔离依赖”段及 `apps/GSHC/swd_cli.py --help`。
模块为 `transport.swd_session`，公开操作为 `Swd_Attach(selected_probe)`、
`Swd_Snapshot()`、`Swd_ReadMemory(address, length)` 和 `Swd_Detach()`。
调用者应检查 `SwdReply.result`、在 finally 中释放；重复采样须遵守 100 ms 的速率限制。
`selected_probe` 必须来自当前 `ProbeInventory_Read(Event())` 中唯一匹配的明确 USB 身份，
不能选第一项或直接绕过身份验证。无写入/复位/暂停/恢复接口。

## 原生路径证据

当前环境没有暴露可调用的 `node_repl / sky` 原生 Computer Use 工具。
采用 QtTest 驱动本应用的 Windows 原生控件，调用 `main.py` 所用的 `app.main()`，
没有使用外部 Windows UI Automation 或人工鼠标点击。它不是 offscreen 窗口或模拟
SwdSession：Qt platform=`windows`，窗口 exposed，原始 Controller/工作线程/后端未替换。
为保护用户数据，测试仅隔离 QSettings 和应用数据目录；真实连接时专用 SWD 依赖
环境变量未设置，启动时 pyOCD 未加载，显式连接后从上述默认目录加载。

| 场景 | 实际结果与边界 |
|---|---|
| 原生选择/维护页打开 | 精确 Horco 身份，选择后 0 DAP 包；不自动连接 |
| 三次真实连接及各一次定时刷新 | CPUID 0x410FC241，ID 0x413 / REV 0x1007；六个 DHCSR 样本均 0x01010000、running |
| 手动断开和重复连接 | 前两次接口、接收线程和所有者锁释放；可再次连接 |
| 连接中再连接/换探针 | 按钮禁用，manager 拒绝再次 attach/refresh，不创建第二会话 |
| Busy 显示 | 向 claim 注入 USBError，显示“会话忙；未接管”；0 DAP 包，无竞争程序 |
| 缺依赖显示 | 注入不存在的依赖目录，正确提示 SWD 依赖缺失；0 DAP 包；移除注入后再次连接成功 |
| 在第三次连接中关闭窗口 | 正常 closeEvent/Controller 取消及释放，应用退出 0；无工作线程、接收线程或所有者残留 |

真实场景共 144 个 DAP 包，逐包检查全通过；仅读取识别/核心状态，没有本轮 RAM 块
或 flash 读取。UART open 次数为 0。底层源仍为
`39ee1c038c0f3c3f97fa8b8ab913828ca79c2537` 的已审计实现，未添加调试控制。
WinUSB 对任意外部 bulk/HID 客户端的排他性没有新增证明；Busy 是故障注入，不是
有意启动竞争调试器的实机实验。已核对的 native 控件图见证据包。

首两次核验脚本分别因状态栏属性名错误、尚未等待连接按钮刷新而停止；两次均
0 DAP 包、应用正常退出且资源为空。原脚本和失败记录保留；修正的是测试时序，
没有修改按钮准入条件。第三次一次完整执行得到 11 个 GUI 状态快照并成功退出。
追加的 offscreen GUI 回归结果单独记录，不能与这次真实窗口执行混称为上板覆盖。

## ELF 与未验证边界

现有 SWD 实现没有 ELF 输入/可加载段匹配功能，公开内存读取仅允许 RAM，后端也
限制固定识别寄存器和 RAM，拒绝 flash。`SwdSnapshot.symbols` 保持 `unmatched`，
GUI 显式显示未匹配；本轮没有扩展 flash 读取或新固件元数据，没有根据 ELF 路径、
日期或旧构建来猜变量。不能把诊断页已有串口字段解释成来自 SWD 的符号变量。

本次仅验证当前 Horco、当前 STM32 ID 0x413 台架和短时读取。未证明精确芯片料号、
持续运行时序/无扰动、其他型号/探针、真实竞争 Busy、硬件异常释放或飞行资格。
支持边界和前序 RAM/CLI 证据见 [底层说明](SWD_PYOCD_BENCH_20261014.md)。
本轮没有扩展功能；验证完成后已关闭测试窗口、释放连接，停止等待用户验收。

[本轮证据目录](../../../apps/GSHC/docs/evidence/swd_gui_20261014/README.md) 保存启动配置、
原生截图、状态/释放记录、逐包日志、完整失败记录、测试命令、源哈希和清单。
v0.1.2 tag、发布包、用户原有文件和前序正式证据未修改，未 push、发布或 tag。
