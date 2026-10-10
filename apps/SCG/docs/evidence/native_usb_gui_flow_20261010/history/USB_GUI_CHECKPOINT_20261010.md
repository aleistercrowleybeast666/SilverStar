# 第一批普通 USB 产品接线检查点

父任务要求当前测试边界交回检查点。本文件是未完成交接，不是最终全通过报告。

## 授权、版本与改动

直接人类 `Sentinel_a33dd516d57c8191b300647e7c8d205c` 回复“允许”后，原 GUI 接线动作审批已通过并执行。两个此前拒绝均发生在执行前；没有绕过拒绝。该授权不覆盖 b66 独立安全审查。

唯一开发目录 `D:\python_software\SilverStar\.work\ccdi`，分支 `feature/scg-classic-cdc-contract-20261009`。当前 HEAD `63771a17e63052c238246dd4fe3fe6394de8ccec`，最后核对无 dirty。

- `4926f773cdf6e71e185857a5fc1097834f664f7b`：修 F103 Reset/Disconnect 丢失 class DeInit 错误返回；失败保留资源，允许清理重试。新增正常失败和 suspend 场景。
- `e782a33c9e6f1c453cafa1649e6e335665222c92`：已有界面的 exact F103/C071 导入、绑定模型保存/重载、candidate Plan/Export/Build、真实产物检查、工具选择、取消/进度接线；保留正式生成阻断。
- `f91f82e4a0b4e83bb583c39b86a3d98f150cccf2`：资源表显示实际 SPI/GPIO 输出/输入/中断类型，修严格普通 GUI 测试发现的类型问题。
- `63771a17e63052c238246dd4fe3fe6394de8ccec`：仅真实 ARM 质量审计测试的有界等待改为 120 秒。产品源代码相对 f91 不变，全部结果/过期产物/发布阻断断言保留。

## 已完成验证，范围不得合并或扩大

- `ul17`：f91 clean，2 pytest tests passed，17 场景/目标，共 34 次普通生命周期执行，0 skipped，16.86 秒。实际生成 core/class/interface/adapter 执行；LL/PCD/Cortex/UID 为明确 Host 替身，不代表原生控制器/IRQ 运行。
- `ugr02`：f91 clean，99 passed，0 skipped，169.30 秒。普通 GUI、进度、计时 CNT=0、native control/radio/runtime/CPU/IRQ/no-heap 等保留回归。
- `ug07`：f91 clean，11 passed/1 failed，315.92 秒。失败为 C071 真实质量审计超过旧通用 10 秒测试等待，不写为全通过。两款 normal/analyzer ARM 构建实际成功、339/351 命令、无 firmware/analyzer diagnostics。F103 完整 GUI 成功路径通过；C071 未到 stale-artifact 断言。
- `ugg01`：ug07 两款候选的架构、普通 Host、产物、原有 PoT 共 8 项 exit 0。准确命令、日志和时间在 `ugg01-gates.json`。
- `usb-gui-visual-boundary.json`：只修改两个 UI 文件的许可逻辑方法；另 24 个 UI 文件保持；构造器/控件/布局/样式不变。
- `usb-gui-visual-settled/receipt.json`：f91 的相同普通未绑定参考模型，offscreen 1280x820，Ground/Build 页面像素相同；这是有限 Qt 软件渲染对照，不是原生桌面或候选内容完全相同声明。最初渲染的字体状态差异证据保留在 `usb-gui-visual/`。

对应执行记录/日志：`ul17-command.json`, `ul17.log`, `ugr02-command.json`, `ugr02.log`, `ug07-command.json`, `ug07.log`, `ug07-build-index.jsonl`, `ugg01-gates.json`, `ugg01-*.log`。

## 正在运行，不要启动重复构建或修改源码

`ug08 all` 完整 12 项普通 GUI 重跑。所属 exec session **43452**；进程未中断。父任务可读取本目录 `ug08.log`、结束后的 `ug08-command.json`、成功编译时追加的 `ug08-build-index.jsonl`。启动命令：

`D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe -B C:\Users\chdxm\Documents\Codex\2026-10-10\task\run_usb_gui_tests.py ug08 all`

实际子测试命令/cwd/source hashes 由 runner 在结束时写 command receipt。截止交接日志前六项已通过，后续真实 ARM 构建仍在运行，不能据此预测余项通过。不要中断正在写文件/编译的进程。

## 最短剩余步骤

1. 等 ug08 自然结束，读完整失败或 12 passed 结果；保持源码版本与 receipt 一致。若真实失败，继续修该具体问题。
2. 若 ug08 全通过，执行 `run_usb_candidate_gates.py ugg02 ug08`：两款最终构建的 8 项不变生成检查。不要用 ug07 的哈希替代 ug08。
3. 归档 final saved model、backend/compiler receipt、完整 `source-snapshot.json`、commands.log、normal/analyzer ELF/map/.su、选定 generated/derivative/Tools、ul17 的 actual Host fixtures、失败/通过历史和视觉证据；不大量复制 vendor。新增 `NATIVE_USB_GUI_FLOW_20261010.md` 与证据 manifest。归档需 `.gitattributes * -text` 并验证 Git index bytes；独立证据提交。
4. 给旧 `USB_GUI_WIRING_BLOCKED_20261010.md` 加授权已解决的版本说明，并注明旧 lifecycle 报告中的 P2/接线缺口已被后续提交处理，保留历史范围。
5. 核最终 clean HEAD、日用不变、所属进程结束；交父任务普通审查/后续通知合并。不要自行 push/merge。

## 保持的边界

b66 平台中止的独立 USB 安全审查仍 NO_PASSED_OUTCOME，未重试、未绕过、未标已审。未研究畸形 USB 或替代 owner 表达式。正式发布/通用生成仍阻断；候选普通软件 GUI 交付和正式固件放行分别说明。PCD/PMA/IRQ 的原生运行、所有交错、whole-program stack/WCET 与 manual critical-contract acceptance 没有此处证据；本轮不增设硬件为软件产品验收前提。F407 旧候选保留，未新放行。

日用目录最后 HEAD `56448bd35736221d7885a26704f2f953b0fe5055`，仍仅三个原有 untracked inventory 文件。没有 hardware、DAPLink、串口、烧录/START、FINAL 改动、push 或 merge。此前 OS 全进程枚举受限，不声明完整系统进程审计；上述 43452 为本轮已知自有运行会话。
