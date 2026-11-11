# 三仓工作流、联调与清理交付 · 2026-11-10任务（2026-11-12收尾）

本轮三仓代码、跨仓数据链和可确认的清理已经交付。SilverStar 的45ba8701便携包正常构建并
逐文件读回，但FLP/GSHC原生显示采样仍白屏，最终GUI验收未通过。19项诊断包含不加载产品的
纯Qt最小复现，仍未证明唯一根因；没有提交猜测性修复或降低门禁。下文将通过、未证明、
硬件待测与保留清理项分别记录。本报告及其收据提交只增补文档，不改变45ba8701的产品代码身份。

## 分支与交付身份

所有修改沿用原候选成果；没有从旧 main 重建、合并 main、移动发布标签或 force-push。
[基线清单](BASELINE.json)记录实际路径、remote、HEAD、原始未提交输入与 worktree。

| 仓库 | 本轮分支 | 起始 SHA | 当前交付状态 |
| --- | --- | --- | --- |
| SilverStar | `feature/usb-transport-0.1.3-20261013` | `e143188dbad9ca0a70dfdc27f52b4226a370cfe8` | 产品代码已正常推送 [45ba8701](https://github.com/aleistercrowleybeast666/SilverStar/commit/45ba8701af5f4baf83692fb15b5fbac2d9dfcc21)；同源码便携包已本地构建并逐文件读回。本报告所在后续提交为文档交付身份，最终提交链接在交付回复中给出 |
| Underline_RETLDC | `codex/release-candidate-20261103` | `a6e5d3b1eab66032c109cedbcd0743c05395c2c9` | 已正常推送 [239ce7b](https://github.com/aleistercrowleybeast666/Underline_RETLDC/commit/239ce7b5092da213c69b2c5dfceb797a0c239f33) |
| TreeDiagram | `codex/gui-convergence-20261110` | `b1157260ee4faa8a625b48530e48f0f0ef93e50c` | 已正常推送 [38a6ccf](https://github.com/aleistercrowleybeast666/TreeDiagram/commit/38a6ccf23ca24b2ca60956b7365780ec1eb5fe39)；当前代码与wheel为af54cd1对应源码 |

这是工作分支交付，不是正式 Release。源代码的应用版本、协议和 schema 没有为名称统一而改号。

## 用户现在如何使用

- **SCG** 保持硬件与通信 / 任务流程 / 检查与生成三页。硬件摘要和共享无线链路沿用同一
  配置 owner；两端未配置的原因分别可见。真实阶段胶囊现在能编辑“进入本阶段时执行”的
  action / target，与条件共用私有草稿；共享实例只编辑一次。构建页显示真实目标、ELF/map、
  区域容量、预算和严格栈状态，不以当前选择代替构建身份。参数导入关闭弹窗后的生命周期、
  工程未保存保护、取消后台任务后又取消退出的状态均已修复。
- **Underline** 保持五工作区。导入、修正必要单位/校准并选择区间后，顶部主操作首次即可
  完成处理和分析；草稿用“应用并重新计算”。失败、取消和过期回调保留旧有效结果。
  有草稿时导出就地说明使用上一版已应用结果；区间已改变而无结果时要求重算。物理参数
  仍只有工程一个 owner。左栏收窄，主图和物理结果获得空间，复杂项折叠。首屏按可用屏幕
  和边框限制尺寸，125%/150% 不需要手动最大化。
- **TreeDiagram** 保持四工作区。模型缺项可定位，PID/LQR 按算法显示有关参数，控制周期
  使用整数校验；阶段摘要打开同一实例属性。刷新保留选中的稳定 run ID，取消运行后等待
  正常结束再处理关闭，结果明确显示属于当前还是历史配置。参数导出取已完成 run 的固定
  输入/实现快照，保留现有离线 6DoF、C 核心和四类仿真执行机构的实际边界。
- **GSHC / FLP** 保留既有导航与严格日志/decoder 身份。方向、连接、维护等已有软件实现
  没有被重新列成未实现。FLP 修正旧夹具的 bootstrap 记录预期、真实保存和窗口生命周期
  缺口；关闭的窗口及其子对象及时销毁，取消关闭仍保留当前窗口和工作。

具体说明：[SCG](scg.md)、[Underline](https://github.com/aleistercrowleybeast666/Underline_RETLDC/blob/239ce7b5092da213c69b2c5dfceb797a0c239f33/docs/evidence/gui_convergence_20261110/REPORT_ZH.md)、
[TreeDiagram](https://github.com/aleistercrowleybeast666/TreeDiagram/blob/38a6ccf23ca24b2ca60956b7365780ec1eb5fe39/docs/DELIVERY_20261110_ZH.md)。

源码运行（分别在对应仓库根）：

```powershell
# SilverStar
.venv/Scripts/python.exe apps/SCG/main.py
.venv/Scripts/python.exe apps/GSHC/main.py
.venv/Scripts/python.exe apps/FLP/main.py

# Underline_RETLDC
.venv/Scripts/python.exe main.py

# TreeDiagram
./TreeDiagram.cmd
```

Underline 的最终便携版在 `D:/python_software/Underline_RETLDC/dist/gui-convergence-20261110-fit/`，
解压 ZIP 后运行 `Underline_RETLDC/Underline_RETLDC.exe`，保留其依赖目录。
TreeDiagram 当前 wheel 位于 `D:/python_software/TreeDiagram/dist/gui-initial-frame-20261111/`；
唯一 run/工程/导出副本仍保存在 `D:/python_software/TreeDiagram/dist/gui-convergence-20261110/`，
不再依赖 pytest basetemp。旧wheel已恢复核验后归档。
SilverStar 新包在 `D:/python_software/SilverStar/dist/gcf1111/`，解压 ZIP 后分别运行
`SilverStar/SCG.exe`、`SilverStar/GSHC.exe`、`SilverStar/FLP.exe`，保留共享依赖目录。
Windows 解压目标使用短路径（例如 `D:/SilverStar`），避免插件目录超过普通 Win32 路径限制。
正常打包入口现在会提前给出具体超长路径，不要求修改系统策略。

## 本轮真实跨仓数据链

新建并明确标为 synthetic 的 121 点试验 CSV，经 Underline 真实解析、顶部计算、保存与
默认无 GUI CLI 导出。有效区间 2–4 s、总冲 225 N·s、推进剂 0.18 kg、总质量 0.42 kg。
这不是旧 Golden 拷贝，也不是实测发动机。

TreeDiagram 实际导入后完成 run `4008f769-9d31-4182-bee5-7477845b5870`：18 s，最高
461.482221 m，结束原因是仿真时长到达，不能写成已经落地。运行使用 KF6、10 ms PID、
gravity=9.78、Kp=1.75；之后编辑器改为 9.81，历史 run 导出仍为 9.78。

SCG 真实 Preview/Cancel/Apply 与 CLI 使用同一后端；普通导入默认不启用控制研究。
普通和显式研究工程均正常生成，实际 C 消费者以 GCC `-fanalyzer` 严格编译并运行。
原生 Apply 后保存的规范 `SilverStar.ssproject` 与后端候选逐值严格一致，保留 float32 值。
研究输出为有界 body-Y 力矩请求，`deployable=false`、`electrical_output=false`。
任务调度、ARM 产物和 Host 证据分别记录，不冒称实物执行器闭环。

| 产物 | SHA-256 |
| --- | --- |
| 新 motor 包 | `eed976bb0d95d90f680a6b72988e42b2a93b5342d5756a1d4a0a437930f017e3` |
| 完成 run 导出的 `.sstuning.json` | `ab27c43327d51c0c26988c26c3a2d5699c10ce7872592276d24750c95f6580b8` |
| Underline 最终 fit EXE | `87e4d65154db99cad5f07587a8c7bd6af35351d2cb83637ff99dae46474b3840` |
| Underline 最终 fit ZIP，98,654,508 B | `7d518a16f927a0fd643e158ca7bec0b95d24823896a350af710bb94d8da7c58a` |
| TreeDiagram 当前 wheel，192,914 B | `d26d396759eecd40e710b9ea032f989c42e66af10683760f000f87b830e3db99` |
| SilverStar 45ba8701 完整 ZIP，241,516,558 B | `4cf2382e6b22f367def0c0273a96ae426b2289fe56cbf16518948b423e956014` |
| 同包 SCG.exe | `4a47e2dbc070156de7fc5cf703954950f96803e92ef6faad35b46cb154a9bcc0` |
| 同包 GSHC.exe | `30083f337de0c4e1cd364ba0e0b3c16feba008e25d9213cece7057e05261283d` |
| 同包 FLP.exe | `f74de6d705711b851f0420e71719e2a508eb90353bbffe143de952959a9f34c1` |
| 清理后 Android debug APK，2,479,069 B | `7e2d2118c0da9ef0b9643e3335fe63f782ac626b3cfa785771ebebed10605b66` |

命令、实际模型、参数、输入和限制见[联调结果](integration/results.json)、
[执行命令](integration/commands.json)、[主负责人回归](ROOT_REGRESSIONS.md)。

## 验证与精确范围

Windows 11、Python 3.14.0；SilverStar/TreeDiagram 为 Qt 6.10.1，Underline 为 Qt 6.11.1。
实际 ARM 工具链为 Arm GNU 14.3.Rel1；原始命令与工具身份在各 receipt 中。

| 批次 | 本轮实际结果 |
| --- | --- |
| Underline 正常打包入口最终 fit 批次 | 单次 413 passed / 1189.76 s，Ruff、实际 PyInstaller、浅深色 EXE smoke 全部通过；472 输入起止一致，891 ZIP 成员逐项散列核验 |
| TreeDiagram 当前完整套件 | 首屏适配后单次139 passed / 48.66 s；新wheel隔离安装、67源码/SDK逐字节核对、fresh GCC、安装包原生150%均通过。首批136 passed/31.92s及旧wheel作为独立历史批次保留 |
| SCG 本轮当前 ARM/严格栈 | 8 个当前配置 all / artifact-check / stack-report 退出 0；另 2 个修复前 H7 结果明确保留为历史 |
| SCG 任务调度与关键边界 | 单次 94 passed / 244.00 s；实际 PID/LQR、状态、任务/记录/资格与故障边界，不以 mock 返回替代 owning C |
| H7 正常生成完整 Host | 72 程序，4,405,830 checks，0 failures；完整 mandatory 尾部通过，按选型不适用和预期编译拒绝保留 |
| PID 选择性 Host | 3 程序，1146 checks，0 failures；明确是选择性执行，不叫完整套件 |
| 当前 H7/PID 原样 P10、架构和 ARM 静态分析 | 6 项命令退出 0；真实 `-fanalyzer` 编译/链接；固定全固件 critical-contract NOT PROVEN 提示保留 |
| Horizon 后端 | 单次 staged 56 passed / 202.10 s；另一次原生 mode2/300 ms 正常路径 2 passed / 54 deselected / 29.50 s，范围分别记录 |
| GSHC 相关方向/重连/维护等八文件 | 单次 80 passed / 39.23 s；不是整个 GSHC 套件或硬件通信 |
| GSHC 清理后明确命令的当前八文件 | c8ec254a 单次79 passed / 32.81 s，190输入未变；与早先80项分别记录，首次遗漏PYTHONPATH的8项collection error完整保留 |
| SCG 清理后新 research/F407 Release | 正常生成、ARM all、artifact-check、严格stack-report四步均exit 0；MSP余372 B，新工程约41 MiB，未改八配置历史结果 |
| SCG / FLP / GSHC 首屏适配 | 生产入口原生125%/150%六场景的几何检查及三快速关闭通过；独立回归4 / 11 / 8 passed，不加总成新的全套。几何检查不证明像素显示；FLP/GSHC后续原生采样白屏仍阻断最终GUI验收 |
| 清理工具完整测试文件 | 14 passed / 23.70 s；复合工程扩展名修复前真实失败保留 |
| Android 旧外壳删除后的新 BuildRoot | assembleDebug/lintDebug/testDebugUnitTest，58 tasks，14 tests/0 failures，7 lint warnings；离线构建成功 |
| FLP 完整批次（ea0f587d） | 单次 1963 passed / 5 skipped / 2827.38 s，1968 collected，0 failed/error/interrupted/untouched；381源码及109输入起止一致。后续仅启动入口适屏改动另记针对性验证，不冒称此批在后续HEAD执行 |
| SilverStar 45ba8701 完整便携包 | 三应用独立 Analysis/PYZ/EXE 与共享 COLLECT、staging 均 exit 0；2,301 源资源及7,579运行输入记录核验，3,449个ZIP成员与安装树逐文件读回一致，总532,397,020逻辑B；实际SCG/FLP --version退出0，原生界面结果另记 |
| Windows 打包路径检查 | 8项回归通过；真实263字符目的地在昂贵Analysis之前按预期拒绝，短目的地正常全构建。保留旧COLLECT失败完整日志，不复用旧Analysis冒充新包 |
| 最终便携包原生操作 | SCG默认首屏150%与真实工具链检查通过，双端缺少目标时生成/构建均禁用；FLP125%真实Golden日志与精确decoder载入14记录，UIA可读、错误计数0，但采集白屏，未通过视觉验收；GSHC150%同样白屏，未连接设备 |
| OpenGL显示隔离 | 19项诊断，Qt6.10.1/6.11.1纯Qt最小GL程序均原生采集白屏，raster对照正常；唯一根因NOT PROVEN。software真实3D报GL1282，不能作为修复 |

FLP 首批实际902 passed calls / 6 failed / 1 skip，1 interrupted、1054未执行，不称完整通过。
六处失败是当前 owning C 明确发布的 bootstrap 记录与旧夹具时间戳预期不一致；
150 s watchdog 另暴露关闭后 Qt 控件仍存活、重复窗口累积的问题。修复和新全套结果
见 [FLP 报告](flp.md)。新完整批次独立执行，不拼接旧通过数、不提高超时上限。

原生代表场景覆盖 SCG 中文浅色125%、TreeDiagram125%和150%、Underline 最终包中文浅色125%
和英文深色150%。通过真实按钮/键盘打开属性、Preview、保存、导出；未失焦输入和事务
范围另有 Qt 回归。原生操作与 offscreen 各自范围见 [GUI_NATIVE.md](GUI_NATIVE.md)。
测试结束关闭自有应用并退出 computer use。最终FLP只丢弃此次合成日志导入产生的未保存工程，
原始日志/decoder未改。详见[最终包原生收据](gui_native/final-package.json)及
[显示诊断](flp/native_compositor_20261112/README.md)。
提交时本轮FLP、清理工具和打包路径检查的原始文本证据保留原始换行字节，避免Git自动转换
破坏收据中的SHA；其余完整大日志使用可逐字节解压核验的gzip。此设置不改变任何门禁或例外。

GNSS 的既有能力也已复验：SCG 完整 `test_release_mag_rotation.py` 的12项包含四型号
Airborne <4g 默认、显式 Portable 配置的保存重开/渲染，以及混合实例冲突拒绝。
H7 完整 Host 还执行 NEO-M9N device、adapter 和 multi-instance 路径。
这些是当前软件消费者证据，接收机实际 ACK 与上板验证仍单列待测。

代表图：[SCG 阶段动作](scg/gui/stage-150.png)（offscreen）、
[SCG 实际预览](gui_native/scg-import-preview-125.png)、
[Underline 最终包](gui_native/underline-fit-result-150.png)、
[TreeDiagram 历史结果](gui_native/treediagram-result-150.png)。

## 当前资源和栈

以下为实际 ELF/map，R/D 表示 Release/Debug，单位 B；物理余量与工程预算分开。
完整 region 百分比、ELF/map SHA、构建/配置身份在 [SCG receipt](scg/receipt.json) 及引用报告。

| 当前工程 | FLASH 已用 R/D（物理容量） | 主 SRAM 已用 R/D（物理容量） | 主 SRAM 物理余量 R/D | SRAM 预算余量 R/D |
| --- | --- | --- | --- | --- |
| F407 普通 | 360172 / 380068（524288） | 101676 / 101812（131072） | 29396 / 29260 | 724 / 588，预算102400 |
| F407 安装采集 | 412804 / 430884（524288） | 101884 / 102020（131072） | 29188 / 29052 | 516 / 380，预算102400 |
| H743 ESKF20 + SYNC400 + 显式旋转 | 390220 / 405932（2097152） | 220988 / 221112（524288） | 303300 / 303176 | 无另设预算 |
| F407 本轮 PID | 361468 / 381532（524288） | 101676 / 101812（131072） | 29396 / 29260 | 724 / 588，预算102400 |

F407 CCMRAM 物理容量65536：普通已用62656/余2880；安装采集65072/余464；PID62712/余2824。
H743 DTCMRAM 容量131072，MSP预留8192/余122880；RAM_D2容量294912、RAM_D3与ITCM各65536，
本配置均未分配。不能把这些银行合称 CCM，空闲物理 RAM 也不证明任务栈安全。

当前8配置严格软件栈证据通过，任务保留256 B上下文及至少256 B余量，Idle恰为256 B。
H7 Device任务余量R/D=372/896，MSP=1364/2900；本轮PID Flight=392/1720，MSP=372/372。
F4原四级优先级域、H7全部16级可配置异常嵌套及NMI/HardFault/FP/main/reset保持原规则。
这些是精确配置的静态软件证明，不是硬件高水位、WCET或飞行资格。

## 已执行的清理与归档

以下为已完成删除收据的最终汇总，取自
[`cleanup_summary.json`](cleanup_summary.json)（2026-11-12 00:59:13 +08:00）。
七个工作根的只读盘点于00:42:55完成；完整前后清单、错误/链接与脚本见
[盘点收据](cleanup_inventory/receipt.json)。不以逻辑文件大小冒充物理磁盘释放量。

| 统计范围 | 已核对结果 | 边界 |
| --- | --- | --- |
| 16个已完成批次的逻辑删除 | 33,149,579,354 B | 精确清单/独立旧根无重叠；不含恢复临时副本或空目录体积 |
| Git索引列出的工作文件内容 | 1,103,283,581 → 726,928,975 B，净减376,354,606 B | 是基线与00:59:13暂存时内容快照，包含本轮增补；随后报告文字/收据封印不回填成同一时点，也不是Git历史对象缩减 |
| 持久归档小计 | 19份命名归档，共6,990,525,756 B | 包含3份退休最终提交bundle；不含镜像目录、外迁Android工具/密钥及辅助清单，不代表净回收 |
| D盘单一区间观察 | 33,830,522,880 → 56,625,303,552 B，增加22,794,780,672 B | 起点为11月11日19:18续行观察，终点为上述汇总时点；并行构建、归档和其它写入，不能独占归因于清理 |

C盘同一区间可用量为26,164,006,912 → 24,768,262,144 B（减少1,395,744,768 B）。
这是实际读取的磁盘可用量变化，不能给出排除其它进程影响的清理独占净回收量；各批次区间不相加。

| 活动工作根 | 起始可读取逻辑内容 B | 盘点后 B | 边界 |
| --- | --- | --- | --- |
| SilverStar | 30,712,586,284 | 32,813,452,896 | 新当前构建/测试证据使根内容增加；原732个访问错误仍记录，链接20→30未跟随 |
| Underline_RETLDC | 1,904,599,421 | 2,318,924,499 | 最终包/验证输出保留，1个访问错误仍记录 |
| TreeDiagram | 155,523,979 | 162,668,507 | 最终wheel和唯一run保留，无访问错误/链接 |

这三项包括Git、环境和并行产物；根体积变化不是本轮逻辑删除量。旧GSHC/Android根已不存在，
扫描的1项root-not-found是预期缺失；旧FCCG和FLP的0可读取文件字节不代表权限残留/链接内容为空。
`silverstar-packages`、`silverstar-packages-long-path`、`silverstar-final-build`
三批现已按原归档恢复清单删除，分别3502 / 621 / 30文件、1,160,784,281 / 659,265,444 /
230,243,603逻辑B，三批均0错误。当前45ba8701包与诊断复现继续保留。

- 44 个 tracked 历史 ZIP/ELF 共389,657,470 B已归档、逐文件实际恢复核验后从当前树删除。
  冷档382,210,525 B，SHA `258a3d0e1c2caa36d477b173c2f32514a801caec1682b3fc3e38652903f5db61`；
  14处历史下载引用改为原始固定SHA并附迁移说明。[清单与恢复位置](COLD_ARCHIVE.md)。
- 旧 GSHC checkout已移除16,532文件/1,226,406,516逻辑B；旧Android外壳18,051文件/
  1,923,551,302逻辑B；旧FLP可核验55,924文件/2,737,349,713逻辑B，106链接和1个无权限目录
  保留且未跟随。旧FCCG归档恢复核验后已移除463,684文件/23,298,183,556逻辑B；
  原86个拒绝访问路径保留（该批没有reparse条目），新增身份变化或删除错误为0。
  旧GSHC与Android根已不存在；旧FLP和FCCG根因上述残留仍存在，未改ACL或跟随链接。
- 原Android工具链、缓存和私有debug key已迁到 `D:/DevelopmentToolchains/SilverStarAndroid`，
  逐文件校验，并在旧shell删除后重新构建。旧外壳恢复集还依赖清单中的16,802份外迁文件，
  `shell-remainder.zip` 单独不是完整恢复集。密钥不提交Git或公共归档。
- 原0.1.2许可输入保留于 `D:/SilverStar_Archive/retained_inputs/`，打包仍核对其原始许可链。
- 已正常Git移除1个无独有提交、无用户改动且无ignored内容的worktree，共363文件/
  4,033,055逻辑B。当前Git登记54棵树，即活动主树与53个历史worktree；后者因未合并HEAD、
  修改或ignored内容未获可删结论而保留。详见[移除收据](worktree_cleanup.json)，不使用通配符删除。
- Underline旧pre-fit另移除905文件/387,115,321逻辑B，保留145,133,411B外部冷档，
  904文件均实际恢复核验；最终fit和472输入未变，清理后源码/最终EXE默认CLI均通过。
- SCG旧可再生产物移除13,759文件/1,081,518,924逻辑B；3,892唯一对象实际落盘恢复核对。
  FLP移除940份旧重复PNG/CSV、37,486,196逻辑B；614内容先恢复核验，当前full2对应副本保留。
  TreeDiagram首批192,473B wheel已在独立归档实际解压75成员、核对后移除；15份其它交付文件未变。
- 缓存逻辑删除分别为Underline 4,498,105 B、TreeDiagram 2,425,121 B、GSHC 6,868,274 B；
  GSHC的未归属 `apps/GSHC/.work/inspect_width.pyc` 保留。TreeDiagram唯一run和最终wheel迁到受保护的dist交付目录，
  清理后再次从真实run导出得到同一SHA；Underline清理后源码/便携CLI实际导出也一致。
- 清理工具区分repository root与scope，默认预览、按清单执行并复核身份；新增三仓差异产物
  检查和ignore规则，不把vendor、Golden、许可或名为build的源码误删。[工具验收](CLEANUP_TOOL.md)。

旧独立仓库退休前全部refs、Git恢复、LFS核对、现有issue/PR说明与评论已备份。
迁移README随后更新的三个最终提交，另有各自 `migration-tip.bundle` 及实际恢复收据，
共159,083,788 B；原refs的bundle保持原身份。两层Git备份均已纳入上述19份归档小计。
恢复位置为 `D:/SilverStar_Archive/20261110/retired/`，保留原路径/SHA清单、Git镜像/bundle、
恢复收据和可读取的独有文件冷档；无权限及链接残留不冒称已备份其内容。
三个远端均已完成只读退休，退休操作的远端GET收据确认archived=true且可见范围未改；没有永久删除远端。
详见[备份、恢复与退休状态](retirement.json)。Wiki远端返回repository-not-found，没有取得wiki内容，
因此不声称已经证明其历史上从未存在。
普通删除提交不会减少历史Git对象，archive也不声称释放GitHub历史空间。

## 保留的边界与未完成项

1. FLP源码/便携EXE和GSHC便携EXE的原生显示采样白屏，阻断最终GUI验收。前台自有客户区
   屏幕采样与WGC均为空白，控件自身绘制正常；纯Qt最小GL程序在6.10.1和6.11.1也复现。
   no-fit单次正常已被重复试验推翻，不能认定首屏适配为根因。软件OpenGL导致真实3D报错，
   不能推荐。采集链路、Qt、驱动和桌面合成之间的唯一原因仍 **NOT PROVEN**。
   下一步需在可正常观察原生GL画面的另一会话或机器上复测本包、最小对照与真实3D，
   再根据证据修复并重建。当前保留45ba8701候选及必要失败复现，不另造一个无产品修复的新包。
2. 全固件每条第一方/第三方关键语义的完整人工审计仍为 **NOT PROVEN**。本轮当前栈缺口、
   传感器/回调/旋转状态/调度边界的局部证据不能改写成全系统审计完成或原始P10认证。
   下一步按具体失败分支及调用者处理逐项补人工审计/故障证据；文本扫描不能自行证明这些语义。
3. 真实MCU栈水位、IRQ抢占时序、WCET、DMA/cache、同步接线、断电保存/重启读回、接收机ACK、
   串口链路和飞行验证待硬件。Host故障注入不是断电/上板或MCU恢复证据。
4. SS0000/SS0007/SS0014原始硬件记录及精确decoder缺失的测试保留具体skip；不拿合成Golden代替。
   控制研究和四类执行机构保持现有离线/限定能力，没有自动部署或实物执行器驱动。
   需要匹配的原始记录/decoder与目标板到位后，按既有验收清单重跑对应项。
5. 无权限目录、未知独有内容和53个历史worktree保留；不改ACL、安全策略或扩大删除范围。
   当前任务中的原始输入、完整full2结果与显示失败复现仍保留；任务根清理标记继续保护这些
   内容，含义是验收阻塞下的保留，不是仍有后台测试进程。后续先按清单解决归属与恢复核验。
6. 若要永久删除 `SilverStar_GSHC`、`SilverStar_FLP`、`SilverStar_FCCG` 三个远端，需要按用户
   本任务7.5在全部备份/恢复/依赖处理完后作最后一次精确确认；当前授权足以执行只读退休，
   不能把笼统清理推断为永久删除。该项不阻塞其余工作。
