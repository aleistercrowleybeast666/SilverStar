# pyOCD / Horco 只读台架证据

基线 `8ff26e9fb3d5b616efca91f3d46cca7f26e2d501`，分支
`feature/usb-transport-0.1.3-20261013`。本目录只保存本轮证据，不修改历史证据。
当前范围和本机使用见 [公开说明](../../../../../docs/public/GSHC/SWD_PYOCD_BENCH_20261014.md)。

用户批准 official PyPI pyOCD 0.45.1 隔离安装及指定三线/外部供电/执行器断开台架。
pip resolve/install 各退出 0，26 个包来源均为 files.pythonhosted.org。
52.27 MiB 的 deps 留在 `.work/dev013_swd_pyocd01/deps`，没有放入本归档或 Git。
仓库不包含运行时自动安装代码，不改系统 Python/PATH/驱动/SDK。

实际台架记录：

- 初次 `bench_command.json` 退出 2：辅助包检查器错误地拒绝 DP/AP 配置块写，
  没有完整目标识别；释放 Ok。原包日志和拒绝结果保留。
- `bench02_command.json` 退出 0：2026-10-14 00:07:50 UTC 开始；Horco
  FAED:4870 / 132765403520，DP 0x2BA01477、AP0 0x24770011、CPUID 0x410FC241、
  STM32 ID 0x413 / REV 0x1007，16 字节 RAM 读取和两次释放成功。
  DHCSR 0x03010000 -> 0x01010000 -> 0x01010000；首次读清历史 reset 位，
  后两次 running。92 包全部通过检查，无 CPU 控制、目标内存写或 NRST 操作。
- 后来增加 host 枚举取消和显式超时处理。`cli03_command.json` 退出 0：
  当前源码通过真实默认 CLI 读取同一 16 字节 RAM并释放成功，44 包全部通过。
  cli03 源哈希与当前 dirty snapshot 相同。bench02 的旧适配源另保存完整文件，
  从最后两项 host 修改逆向重建并核验其 SHA256 与当时记录完全一致。

真实读取为非原子原始字节，ELF 未匹配。最后一个 release 后没有再发状态读取；
“释放后运行”来自 bench02 首次 release 后的第二次 attach 样本，不能扩大为连续证明。
无故意竞争的实机测试；进程预检和用户单会话约束不证明不存在任意外部 HID 客户端。
GUI 回归使用模拟，未实际点击 GUI 连接。其余芯片/探针、持续时序、READY 和飞行资格未验证。

一次完整 `pytest06` 执行六个 SWD/探针文件，**143 passed / 49.28 s / exit 0**，
无 warning/skip 汇总。使用实际 pyOCD 编码器、bulk RX、Probe/DP/AP，USB 和内存为模拟。
初次 17 passed 带配置 warning；pytest02 的 96 passed / 2 failed 包括子进程 import 路径
及旧默认路由假设，后者仅查 USB descriptor，没有 claim/目标读取；pytest03 为缩进收集错误。
pytest04 99 passed，pytest05 新增 actual encoder 的 18 passed。完整失败日志均保留，
不把分次通过拼成全套执行。测试命令/环境/退出码见 `task/test_commands.json`。

`evidence_final.zip` 保存完整日志、pip reports/归档哈希、当前及台架源快照、工具版本、
实际源审计片段、许可证、包记录和 task inventory；`manifest_final.json` 给出归档及每项 SHA256。
初次 `evidence.zip` / `manifest.json` 保留原阶段快照；其中可选 requirements 文件有
字面换行转义问题，收尾核查时已修复为真实 26 行并与安装报告逐项核对。
此文件不参与已执行的直接 pyOCD 安装或台架读取，当前交付以 final 快照为准。
没有归档用户虚拟环境、依赖 DLL、Cube SDK 或无关工作树。
task inventory 对本任务所有保留文件记录路径、目的、所有者、大小及哈希。
deps 是保留运行时依赖；测试 payload 仍保留，**没有清理授权或清理操作**。
没有操作串口、刷写、校准、START、执行器、导航/开伞算法或其他仓库任务。
v0.1.2 tag/release 未修改；没有 push、发布或 tag。
