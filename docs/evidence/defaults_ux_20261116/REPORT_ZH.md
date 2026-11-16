# 三仓默认设置与操作入口收敛 · 2026-11-16

沿用当前候选成果，没有从旧 main 重建。SilverStar 基线为
`cf33be46bffcb43fc60bbca710fa20c0126ffe79`，分支为
`feature/usb-transport-0.1.3-20261013`；Underline 基线 `239ce7b`，继续
`codex/release-candidate-20261103`；TreeDiagram 基线 `38a6ccf`，继续
`codex/gui-convergence-20261110`。开始和推送前核对了各自远端；保留现有 worktree、用户未跟踪输入和候选提交。

## 实际修改

- SCG 删除“设备与资源概览”内的两个重复编辑按钮；上方两端的硬件选项仍是统一入口。
  恢复默认分别作用于无线方案、当前算法专有参数和对准参数草稿，均保留应用/取消事务。
  默认值来自现有模型及插件定义，未更改频率、速率或参数默认值。
- 无线普通界面只提供 LoRa。共享 PHY 对飞控和地面站已配置的活动通信端点执行相同的后端校验，
  包含模块限定频率、无线系列、调制及已有空口参数约束。即使只生成一端，另一端已配置的
  不兼容模块也不能绕过检查；未配置且本次不生成的另一端仍允许缺省。
  窗口显示模块限定频段及冲突；不会用后选的一端静默覆盖另一端或清除硬件绑定。
- 显式恢复会清掉当前数字输入草稿，包括未回车和中间非法文本；普通刷新继续保留输入。
  恢复按钮不会接管 Enter 默认动作。属性窗口首次显示复用主窗口的屏幕边界约束，
  不在定时刷新时调整窗口、重建编辑器或覆盖草稿。
- GSHC 的“任务快照…”和紧凑状态移至顶栏，从所有工作区直接访问。
  完整配置摘要、摘要值及离线 trace 留在一个详情窗口；不改变实时状态或设备权限。
  导出窗口增加草稿恢复默认、固定底部操作和错误提示，并修复 Enter 误触全选、非法时长回退。
- Underline 增加修正、校准及发动机物理参数的局部恢复；保留原始数据、通道、单位、区间和对象身份。
  未知物理量恢复为未知，不填造试验值；同时修复未失焦数值应用、语言切换覆盖草稿及 Enter 隐式恢复。
- TreeDiagram 四类参数窗口增加模型默认、偏离数量和待应用状态，保留安装、装配、发动机与历史运行。
  修复窄窗向量溢出、Enter 隐式恢复和气动数值修改后仍保留旧来源声明的问题。

## 提交与运行

SilverStar 实现提交：[66d24420](https://github.com/aleistercrowleybeast666/SilverStar/commit/66d244202c3d6f592606a882283e9d15a60dbf76)。

- [Underline 提交](https://github.com/aleistercrowleybeast666/Underline_RETLDC/commit/ef964623bba5f80cff9d97e2e4c33ba491f4e3eb)
- [TreeDiagram 提交](https://github.com/aleistercrowleybeast666/TreeDiagram/commit/83c90491a1a9ce4c0a42641ed0161b160632802f)

在对应仓库目录复用现有虚拟环境：

```powershell
# D:\python_software\SilverStar
.\.venv\Scripts\python.exe SCG.py
.\.venv\Scripts\python.exe GSHC.py
# D:\python_software\Underline_RETLDC
.\.venv\Scripts\python.exe main.py
# D:\python_software\TreeDiagram
.\.venv\Scripts\python.exe run.py
```

现有窗口仍运行旧进程，请先保存工程再自行重启。此次没有关闭用户的 SCG、GSHC 窗口。
本轮修改源码；既有便携包、wheel 和冻结发布没有覆盖，也不代表本轮新界面。

## 验证

最终命令、退出码、源文件和日志 SHA-256 见 [validation.json](validation.json)。

| 范围 | 最终结果 |
|---|---|
| SCG 十个完整相关测试文件 | 209 passed，0 failed/errors/skipped，410.287 s |
| GSHC 六个完整相关测试文件 | 89 passed，0 failed/errors/skipped，200.800 s |
| Underline 完整套件 | 420 passed，0 failed/skipped，714.92 s；Ruff 与两个正常入口 smoke 通过 |
| TreeDiagram 完整套件 | 173 passed，0 failed/skipped，53.51 s |

SCG 另用 Qt 实测 DPR 1.25/1.5，按 1366×768 物理屏幕扣除任务栏后的逻辑范围，
检查无线、硬件、阶段、任务准备四类属性窗 × 中英浅深两组，共16场景：窗口边界、
底部按钮可达及可见表单无横向溢出均通过。GSHC 检查顶栏和导出底栏；
TreeDiagram 四类编辑器16场景通过。这些均为离屏 Qt 验证，不替代原生桌面验收。

前后对照和非通过结果保留：

- 无线旧基线会放过“仅生成飞控，但已配置地面站频段冲突”和声明成 packet/GFSK 的兼容候选；
  修后分别报告频段/系列不兼容和仅支持 LoRa。原默认值及协议迁移要求未变。
- SCG 首次扩展回归为206 passed/3 failed：三项旧测试将现行格式24当成14/18，
  或把包含任务流程的新数据仅改版本号冒充13。已验证模型、参考工程及旧测试与本轮基线字节一致，
  并直接执行基线测试重现三项失败。测试改用仓库已有 v14/v17/v18 历史夹具，
  保留精确数字往返、v18概率输入，以及v17概率输入和v13携带任务流程的拒绝断言。
  没有修改解析器、降低阈值、跳过失败或扩大例外。
- GSHC 实键盘复现6项 Enter 错误，修后6项定向及最终89项完整相关回归通过。
  Underline、TreeDiagram 同类键盘问题也分别留有修前记录和最终单次全套结果。
- 新测试开发中的无效阶段ID/不支持功率、数值显示预期等夹具错误已纠正，原日志保留。
  SCG 早期无实时输出的回归被中止，不计为通过；各轮结果不累加成一次完整执行。
- 布局探针最初误用了离屏虚拟533逻辑像素屏幕且未注册字体，截图为缺字方框；
  正式探针显式使用目标笔记本边界、注册实际字体并检查截图。
  探针关闭合成未保存工程时等待确认，诊断堆栈已保留；仅在测试清理阶段选择丢弃合成草稿。

## 未完成与边界

- 原生鼠标交互未完成：独立 SCG 测试窗口已被读取，但 Computer Use 随后持续报告
  `Computer Use helper already has an active request`，重连仍失败。已结束控制会话并关闭本任务进程。
  原生125%/150%目视验收不能标为通过；GSHC/FLP既有原生 OpenGL 显示问题仍见前轮报告。
- 本轮没有新安装包，也没有重新进行实物无线、串口、执行器或飞行试验。
  仅有软件配置相容，不代表两端已经建立真实无线通信。
- 本轮不改固件 payload、科学算法、协议字段或交换契约；未重新执行 ARM、Power of Ten、严格栈和全局
  关键语义合同验收。既有报告中的硬件待测和 NOT PROVEN 仍然有效，不以本轮 GUI 回归替代。
- GSHC 小窗口检查仅覆盖本次顶栏、详情入口和导出底栏，旧预飞表格窄窗压缩未宣称解决。
- 未删除旧独立远端、旧 worktree 或用户输入。既有永久删除审批没有因本轮界面请求获得授权。

## 证据与工作区

本轮各仓使用单一 `defaults-ux-20261116` 任务目录。正式报告只纳入小型日志、收据和可复现测试；
完整临时日志、生成项目、离屏截图及输入散列留在对应任务目录，未复制整个工程或 SDK。
SilverStar 本地位置为 `.work/defaults-ux-20261116/{root,gshc}`；
Underline 为 `.work/defaults-ux-20261116`；TreeDiagram 为 `.qa/defaults-ux-20261116` 和
`.test-tmp/defaults-ux-20261116`。均由本轮测试生成，不构成硬件证据；不清理其他历史目录。

Underline 详见其 `docs/Defaults_UX_20261116.md`，TreeDiagram 详见其 `docs/DELIVERY_20261116_ZH.md`。
