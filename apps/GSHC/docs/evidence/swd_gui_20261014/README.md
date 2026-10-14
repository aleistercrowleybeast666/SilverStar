# Native Windows Qt / real SWD GUI evidence, 2026-10-14

Base commit: `39ee1c038c0f3c3f97fa8b8ab913828ca79c2537`.
[使用入口及核验边界](../../../../../docs/public/GSHC/SWD_GUI_CHECK_20261014.md)。

Computer Use 的 node_repl/sky 工具未暴露；采用 QtTest 驱动本应用 Windows 原生控件，
调用实际 `app.main()`、Controller、SwdWorker 和默认 pyOCD 后端。未用外部 OS 鼠标
自动化或人工点击，不是 offscreen 或 FakeMemory 台架。截图为实际窗口的 QWidget.grab。
设置/数据目录隔离在本任务中；未修改系统 PATH 或用户原有配置。

完整 `native03` / `run03` 退出 0，11 个可视状态，3 次真实连接、各一次真实定时刷新，
2 次按钮断开、第 3 次连接中正常 closeEvent 退出。CPUID 0x410FC241、ID 0x413、
REV 0x1007，6 个 DHCSR 样本为 0x01010000 / running，symbols=unmatched。
144 DAP 包逐包检查通过；无 CPU 控制、复位引脚/目标写/flash/UART。
退出时 SWD/probe worker 均为空，接口 dev/RX thread 均释放，所有者表与库锁为空；
应用退出 0，UART open 调用 0。没有在退出后重新连接硬件。

启动前 pyOCD 未加载，真实连接时 `SILVERSTAR_SWD_PYOCD_PATH` 未设置；库从
`.work/dev013_swd_pyocd01/deps/pyocd/__init__.py` 默认位置发现。不是仅 worker 临时配置可用。
正常用户入口为 `.venv/Scripts/python.exe apps/GSHC/main.py`，仍需保留该隔离依赖目录。

Busy 场景向 claim 注入 USBError；缺依赖场景暂时设置不存在目录，两者均零 DAP 包，
恢复后连接正常。没有启动真实竞争调试器，不能把 Busy 注入称为实机排他性证明。
GUI 重复 attach/refresh 在已有 owner 时拒绝，控件禁用；没有抢占其他会话。

`native01` 首次脚本状态栏属性名错误、`native02` 未等待按钮状态刷新，均退出 2，
0 DAP 包、产品应用退出 0、所有资源为空。失败源/结果/完整日志保留；修复只涉及
核验脚本，未改变产品准入。`native03` 是完整单次执行，不是拼接前两次通过。
唯一产品改动为中英文 SWD 缺依赖文字，GUI regression `pytest01`：11 passed / 21.31s / exit 0。

本轮没有 ELF 匹配实现、flash 比对或变量猜测；公开 SWD 读取仍是固定识别寄存器与 RAM。
此前 CLI/RAM 和 143 项软件回归见[原证据](../swd_pyocd_20261014/README.md)，原归档未修改。
本轮原生截图补充原先 GUI 尚未实机核对的边界，没有扩大芯片/时序/READY/飞行资格结论。

`evidence.zip` / `manifest.json` 含当前源快照和哈希、台架前检查、完整状态/释放结果、
144 个包、11 张原生截图、两次失败及模拟回归日志、脚本、版本和任务清单。
不包含旧环境、SDK、整个仓库或安装依赖的复制。任务所有文件记录用途、所有者和 SHA256，
没有 cleanup 授权或执行。用户原有清单、v0.1.2 tag、发布包及前序正式证据保留。
测试窗口已正常关闭、连接释放；完成后停止等待用户验收，不 push/tag/发布。
