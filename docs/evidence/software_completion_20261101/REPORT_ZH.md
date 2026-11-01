# 三仓库软件收尾报告（2026-11-01）

本轮从 [BASELINE.json](BASELINE.json) 记录的三个 HEAD 和原工作区继续，保留已完成工作。
本报告对应用户要求的严格栈、关键合同、控制调度、SCG 主页/生成页与三仓库交付；
不将合成数据、Host 计时或文本扫描当作硬件验收。历史失败保留，后续结果不倒填旧记录。

## 已实现

1. **严格栈检查**：解析真实 ELF 函数范围、条件间接调用、返回尾调用、动态 SP 与栈增长环；
   库、固定 HAL 回调、RTOS、启动、MSP 和 ISR 嵌套进入完整闭包。未知整体状态现在令 CLI
   非零退出，任务单项通过不能掩盖 whole-program NOT PROVEN。新证明只允许人工审查后
   固定的五个模型、十个 Release/Debug 构型；修改参数、源码、头、编译器或产物仍拒绝。
2. **关键软件合同**：mission getter 在完整状态验证后才发布；终止配置失败仍终止且返回
   错误；日志/动作失败向上传播。控制任务沿实际 INS/Estimator 历史样本携带来源、epoch、
   标定 generation，在同一临界区检查并发布，过期或故障立即撤销输出。详见
   [mission 复核](critical/REVIEW_ZH.md)与[控制器复核](control/README_ZH.md)。
3. **控制调度**：显式启用的 PID/LQR 接入既有 FlightTask，固定 10 ms，跨连续阶段保留
   状态，终止/故障后本次任务不自动重启。输出为 Body Y 请求力矩，显式 1 N·m/core-unit
   映射、上限 ±1 N·m；`electrical_output=false`、`deployable=false`。20 ms 旧参数仍可
   用数学核心导入，不能启用该任务。GUI 默认不勾选。
4. **资源修复**：F4 GPIO 状态按完整资源表的最高逻辑编号分配，未按已选设备删容量；
   F407 MSP 预留从 1024 增至 2304 字节。RAM 100 KiB 门槛和栈最低 256 字节余量不变，
   无线/日志/UART 缓冲不缩减，DMA 未搬到不可达银行。[前后证据](critical/gpio-capacity/REVIEW_ZH.md)。
5. **SCG GUI**：第三页两端使用同一配置准入，初始未配置两端均禁用；工具检测不覆盖原因。
   第一页显示硬件、共享通信、设备资源摘要，详细配置改为一个选项窗的页签。取消/Esc/
   关闭不写 live 模型；原迁移/保存入口保留，过期草稿拒绝。实际原生窗口正常退出后
   Computer Use 已 reset 关闭。[交互与截图](gui/README_ZH.md)。
6. **Underline**：保留原界面与导出插件，实际发动机文件→TreeDiagram 链路重新运行。
   另修复临时图片 exporter、图表菜单和隐藏编辑控件的 Qt 所有权；没有禁用 GC 或重做界面。
7. **USB**：F103/F407 共享有界 EP0 策略补齐初始/继续/状态 LL 错误撤销与迟到回调拒绝，
   三种 Ground 路径补齐实际缺失的 provenance 头。后续继续修复 F407 描述符零长度/
   越界/无进展及 getter 的部分更新；复用精确 no-heap owner，只有已审 LL SHA 的 F407
   派生 FIFO 改为 128/64/64/16 words，原输入与原配置事实保留。普通私有候选与独立
   通用 kit 分别验证，正式 USB 准入仍不解锁。

## 本次证据索引

| 范围 | 实际结果 | 原始记录 |
|---|---|---|
| mission 状态/运行时合同 | 同一整组 31 passed；原来 9、1、4 个真实失败分批留存 | `critical/mission-combined-after-v2.log` |
| F4 GPIO 容量 | 原组 1 failed/9 passed；修复后 10 passed，真实 GCC analyzer | `critical/gpio-capacity/index.json` |
| architecture / owning 源 | 16 项完整组合通过；生成 Tools 逐字节对应 payload owner | `critical/gpio-capacity/architecture-after-v1.log` 与 `critical/gpio-capacity/ownership-after-v3.log` |
| SCG GUI | 最终 11 文件完整 59 passed / 910.54 s；源码未漂移；另有原生实际交互与缩放截图 | `gui/verification-v10`、`gui/native-final-observation.json` |
| 控制调度与来源合同 | v7b 完整 62 passed；真实生成 PID/LQR 数值和 strict analyzer | `control/task-v7b-receipt.json` |
| 栈工具回归 | 完整 14 文件 252 passed；最后独立带完整收据复跑也是 252 passed / 26.01 s | `stack/v5/formal-stack-regression.json` |
| 独立 ARM 与严格栈 | A/B 各十次真实 ARM；5256 项原始产物逐项相同；B 十次 artifact、5×architecture/P10/real-analyzer、十次严格栈全退出 0 | [固定构型报告](stack/v5/DELIVERY_ZH.md)、`stack/v5/final-summary.json` |
| 拒绝篡改 | 7 类输入/对象/证明改动全部非零退出；原字节与mtime恢复后正例再次通过 | `stack/v5/negatives-b/commands.json` |
| 三产品实际 CLI | 3 个 10 ms run→bundle→Preview/Apply→生成→decoder→C 输出均成功 | `delivery/actual-runs-v1`、`delivery/consumer-v1` |
| TreeDiagram | 完整 118 passed；15 个真实示例；实际 push CI 成功 | TreeDiagram `docs/evidence/software_completion_20261101` |
| Underline | 普通完整 383 passed / 754.36 s；原失败 381 项同序独立复跑通过 / 445.47 s；整仓 Ruff 0 | Underline `docs/evidence/software_completion_20261101/heap-lifecycle/owners-v2` |
| 私有 F103/F407/C071 USB | descriptor-v2 三板全部重新 normal+analyzer ARM，emitted architecture/Host/P10/artifact 十二项全 0；P10 仍 manual NP | [精确候选追加](usb-exact/descriptor-v2/README_ZH.md)、[原阶段](usb-exact/README_ZH.md) |
| 通用 USB kit | 新完整 148 passed/6 能力 skips；四次 normal/analyzer ARM 链接 0；Power10 仍 F103 5 / F407 9 失败组 | [追加修复](usb/owners-v2/README_ZH.md)、[原阶段](usb/README_ZH.md) |
| 完整 emitted Host | 默认 77 / 安装 78 个程序、各存储完整性 4/4，全部退出 0；预期编译拒绝和 N/A 分开保留 | `control/full-host-c-f407.json`、`control/full-host-c-installation.json` |

新增 USB 元数据准入的 16 个实际前失败，修复后包含在 27 项完整定向选组中通过；
最终工作区/图不变性选组 8 passed、18 deselected。新导出的 F103 33 / F407 35 个
kit 文件及完整编译输入与已执行 ARM 的版本逐字节相同。148 项完整组选组属于补充元数据
校验前的源码版本，27 项与 8 项单独记账，不拼接为当前 HEAD 的一次完整 148 项执行。

默认/安装的完整 Host 配置关闭研究控制；启用 PID/LQR 的调度与来源验证是独立的 v7b
62 项，实际任务 ARM/严格栈另有两个启用构型。每次完整 Host 有 12 个编译正例、17 个
预期编译拒绝、20 个主 Host 不适用项，另有存储阶段 63 条 record 不适用输出；详见
[完整 Host 汇总](control/full-host-c-summary.json)，不将 N/A 计作通过。

严格栈软件证明范围只覆盖五个固定模型的 Release/Debug。默认、安装与控制 F407 的
MSP 上界 1932 / 2304 字节，余量 372；H743 Release 为 6828 / 8192，Debug 为
5292 / 8192。全构型任务最小余量 256 字节。每个 bank 的实际用量、预算和物理余量见
栈报告；安装 Debug SRAM 为 101980 / 102400 字节、CCMRAM 为 65056 / 65536。
这些 RAM 剩余字节不替代栈或时序证明。未审核的构型/参数/源码/工具链仍被严格拒绝。

Power10 保持 F Prime-inspired 项目适配及显式 `critical-contract review NOT PROVEN`；
它不从文本推断整个固件的合同已证明。每个表格结果只覆盖对应实际执行，不能相加为一套
未执行的“总测试”，也不表示原始 Power of Ten 全符合或 NASA 认证。

## 运行方法

首次检出时，在各自仓库执行 `python -m venv .venv`。SilverStar 与 Underline 使用
`.venv\Scripts\python.exe -m pip install -e .`；TreeDiagram 先执行
`.venv\Scripts\python.exe -m pip install -r requirements-tested.txt`，再执行
`.venv\Scripts\python.exe -m pip install -e ".[test]"`。本机本轮使用已有环境，
没有重装依赖。TreeDiagram 实际 C 算法需要本机 GCC（PATH 或 `CC`）；默认无控制场景
可不使用 C 编译器。ARM 固件验证另需收据记录的 Arm GNU 14.3.Rel1 与 GNU make，
不是 Python 安装器自带功能。

在各自仓库目录，使用已有受测虚拟环境：

```powershell
# D:\python_software\SilverStar
.\.venv\Scripts\python.exe apps\SCG\main.py --lang zh_CN --theme light
# D:\python_software\TreeDiagram
.\.venv\Scripts\python.exe run.py
# D:\python_software\Underline_RETLDC
.\.venv\Scripts\python.exe main.py
```

Underline 从既有导出对话框选 TreeDiagram motor-test 格式；CLI 是
`python -m underline_retldc.cli export PROJECT OUTPUT.tdmotor.json`。TreeDiagram 用
`example OUTPUT --controller pid --control-period-us 10000` 创建匹配的研究场景，
`run` 后 `export-parameters` 输出 `.sstuning.json`。SCG 任务页导入并预览，明确选择
10 ms 研究任务再 Apply。只导入数学核心时使用 `--include-control-core`；研究调度使用
`--include-control-task`，两者不会自动接入电气驱动。

## 准确未完成项

**软件门禁与能力边界**：通用 USB kit 仍有 F103 **5 组**、F407 **9 组**严格规则
失败：保留的原生 main/fault 常驻循环、条件编译，以及混合派生的长函数。不能在保留
当前程序模型的同时把永久服务/故障循环改成有限运行；也未通过扩大例外、改阈值、隐藏
源码或单为行数拆函数使其变绿。上游 UART analyzer 诊断、完整标准请求/异步生命周期、
独立 USB 全程序栈及整体 critical-contract 验收仍未闭合。这些是软件事项，不能称为
“只等硬件”。精确 F407 输入的 FIFO 缺失已通过有记录的派生配置修复；其他原生配置仍
保留自己的事实和 runtime geometry 拒绝。私有 USB 工具通过不等于正式普通生成准入
通过。研究控制没有电气执行器、六轴自动控制分配或部署资格。

TreeDiagram 的单级刚体、小攻角工程近似、ORK 子集及仿真执行器边界继续有效；未实现
分离/柔性/回收伞等扩展。Underline 首版发动机包支持真实接通的推力与 metadata，
压力/温度辅助流不伪称已支持。本轮没有制作新安装器或重建 EXE。

**独立硬件待测**：实际栈 high-water、完整 IRQ 压力与 MCU WCET；生产 IMU/MAG 资格和
GNSS 配置读回；安装标定上板全链；无线 TX_DONE/最长空窗；USB 枚举/拔插/取消压力；
真实执行器、台架/飞行与导航准确性。本轮未连接或控制硬件。软件来源证明不提供这些测量。

用户原已延期的活动 H 半双工重设、飞行中在线调参、运行时 XYZ 杆臂补偿继续延期；
本轮仍活动 S。其他 OS 桌面与完整商业依赖分发审查没有新增验收结论。

## 代码身份与保留

SilverStar 分支 `feature/usb-transport-0.1.3-20261013`：主批次代码
`e7c42b7c4971fddb02c6d5c60864b50dffaa3f1a`，最终 USB/Host 源码提交
`e4b909c05c6887d54a977f973a19378970d0aabc` 已正常推送并读取远端分支核对；14 个追加源文件的实际字节与 Git EOL 对照见
[最终源码绑定](FINAL_SOURCE_COMMIT.json)。TreeDiagram 分支 main，功能提交
`997d112c190ef1549ba5950f5e4f97c0a7c5ad8c`，报告追加提交
`b1157260ee4faa8a625b48530e48f0f0ef93e50c` 已正常推送并核对 main；Underline 修复提交
`351ab0b0167eb37bd6312c2bde79181d6225e97f` 在 main 已正常推送并读取远端 main 核对。SDK 源元数据另固定于 SilverStar
`ad2da03c3b248d15d7cf8e1c3278781fb7cd3f79`；完整原字节与 Git EOL 区别在收据中分别记录。
完整证据随本报告所在提交交付；最终消息给出该证据提交的实际远端链接。
[PUSHED_PRODUCTS.json](PUSHED_PRODUCTS.json) 保存已核对的产品提交身份，TreeDiagram 最后
文档提交的 push CI 也实际成功，见 [CI 收据](TREEDIAGRAM_FINAL_CI.json)。未使用 force
push 或发布 release。证据文件的逐字节索引是 `EVIDENCE_SHA256.json`；可运行
`.venv\Scripts\python.exe docs/evidence/software_completion_20261101/evidence_integrity.py verify`
检查发布内容完整性。该检查只验证记录字节，不把记录中的失败解释为通过。

[工作区清单](WORKSPACE_INVENTORY.md)记录临时输出用途和正式证据。
原 AGENTS 改动、astra/cleanup 历史证据、根 work 清单以及 Underline 原展示文档保留原状。
旧目录读取权限错误原样记录并跳过，没有修改权限。`gh` 本机不可用时使用公开只读 GitHub
API 核对 TreeDiagram push CI，没有绕过访问控制。本轮未执行任务末清理。
