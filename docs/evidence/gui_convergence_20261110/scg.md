# SCG GUI、严格栈与关键合同收敛（2026-11-10）

工作基线是 `feature/usb-transport-0.1.3-20261013` 的
`e143188dbad9ca0a70dfdc27f52b4226a370cfe8`；没有从旧 main 重建。
本报告区分各次真实运行，不把不同批次的通过项拼成一次全套。
较大的原始构建日志以 `.log.gz` 保留，其余测试日志原文保留；解压后字节 SHA-256 见
[`scg/receipt.json`](scg/receipt.json)。生成工程与编译产物位于
`.work/gui-convergence-20261110/scg`，不是用户最终工程，也不是硬件证据。
2026-11-11 已归档清理部分过期 A/旧 H7/测试副本；当前有效工程完整保留，
原始 receipt 的历史命令路径不改写。恢复位置与精确范围见本报告末尾。

## GUI 已完成

- `720ec4bd` 修复真实 `_Capsule_Click` → `stage_only=True, function_id=None`
  入口没有将 `actions_widget` 加入布局的问题。进入动作和目标仍归同一私有阶段草稿；
  缺失目标在底部显示错误，Cancel / Esc 不改工程，Apply 后保存重开一致。
- 单个共享实例属性保留唯一编辑器，移除重复分类标题和嵌套边框；
  运行范围、参数、可折叠输入依赖与诊断沿用同一模型。变更影响所有引用阶段的提示可见。
- 飞控和地面站的不可生成原因直接显示在构建摘要。硬件页与三页导航沿用已完成工作，
  没有改变无线默认值或将生成目标变成清空另一端配置的开关。
- 内存显示真实 MCU 的物理银行、独立审查预算、实际 ELF/map 名称与配置身份。
  严格软件栈报告在验证实际 ELF、checker、工具、封印 manifest、审查文档身份和
  PSP/MSP 数值一致性后才显示；明确标注硬件水位尚未测量。
- `24d70124` 使配置身份从项目内已验证 ELF 的完整生成路径读取，同时支持自动内存
  布局的子目录；不以当前 UI 选择或任意名为 Release 的祖先目录猜测身份。
- 原生测试随后发现真实跨仓 Apply 阻断：QMessageBox 已释放所属复选框，导入方法
  还在 exec 返回后读取它。`a2d9ae9c` 在活对象阶段记录纯 bool，默认不选研究控制，
  保留 stale-preview 拒绝；不访问已释放的 Qt 子对象。
- `02f36089` 修复已应用参数关闭时丢失的缺口。最后成功保存的快照独立于生成就绪状态，
  工程名显示“未保存”；关闭、打开另一工程和新建共享 Save/Discard/Cancel 边界。
  写入失败、另存为取消及尚未应用的对准草稿不允许静默关闭。
- `d797a19b` 本地化保存/丢弃按钮，并将保存提示改为配置已保存，明确生成/构建另行执行。
  `e4bdd76e` 补齐后台任务取消后又取消退出的状态复位，后续任务可以正常发布结果，
  已取消的旧任务仍不发布。

实际验证：

| 运行 | 结果与范围 |
| --- | --- |
| `stage-before.log` → `stage-after.log` | 真实胶囊布局失败复现；修复后相关 6 项通过 |
| `gui-final.log` | 63 项单次执行：61 通过，2 个原夹具问题失败（旧摘要等值断言；独立 Qt 子进程缺包路径） |
| `hardware-final.log` | 修复上述夹具后，完整硬件事务文件 14 项通过；未改变等待时限或业务预期 |
| `stack-presentation-shapes.log` | 25 项单次通过：正确软件报告、失败 MSP 保留、损坏工具/身份/计算/范围拒绝 |
| `memory-identity.log` | 6 项单次通过，覆盖 Release/Debug × legacy/auto 身份 |
| `import-lifecycle-before.log` → `import-lifecycle-after.log` | 真实主按钮/Preview/Apply/Cancel 与 DeferredDelete：原先普通和控制导入 2 失败、Cancel 通过；修复后连同显式选择/过期预览共 8 项单次通过 |
| `unsaved-before.log` → `unsaved-final-verbose.log` | 原始真实关闭 3 项失败；最终 8 项单次通过 / 137.01 s，含真实保存/丢弃/取消、保存失败、另存为取消、只读浏览、旧 worker 取消后关闭和真实另存为。中间 5 通过/1 失败是状态断言误匹配工程名，原始日志仍保留 |
| `unsaved-localization.log` | 1 项通过，按钮中文、默认 Cancel 与 Discard 角色保持 |
| `close-worker-before.log` → `close-worker-after.log` | 真实 Yes→Cancel 组合暴露退出标志未清除；修复后新旧 2 项单次通过 / 44.20 s，验证下一个实际异步任务结果可正常发布 |
| `gui/gui-final-125.json` | 中文浅色 125%，Qt offscreen，实际按钮入口、980×700 主窗、720×620 属性窗 |
| `gui/gui-delivery-150.json` | 英文暗色 150%，相同真实入口，底部按钮可达，浏览与 Esc 未改工程 |

截图工具是 `apps/SCG/tools/validation/capture_workspaces.py`，不再使用
`function_id=""` 的旁路代替普通胶囊。两张代表图见
[`阶段动作与目标`](scg/gui/stage-150.png) 和
[`共享 INS 属性`](scg/gui/shared-ins-150.png)。以上是 offscreen 范围；
原生桌面验收由本轮总报告单独记录。
其中真实 Cancel→Save 退出后，规范输出 `SilverStar.ssproject` 与内存、CLI ordinary
候选的算法参数逐值严格一致，保留原 float32 十进制值。另名导入的原输入文件保持不变；
工程保存按既有目录契约写规范文件名。详见 [`GUI_NATIVE.md`](GUI_NATIVE.md)。

## 第一批严格栈证明

`caf782c5` 修复当前完整输入没有审查案例、SYNC400 实际非 NULL readback 绑定未证明、
以及 readelf 对 DWARF 常量输出原始字节引发 UTF-8 解码失败的问题。
只有 `readelf --debug-dump=info` 使用无损一一映射；没有丢弃字节。
SYNC400 的唯一只读 profile、Prepare/FrameRead/Readback 目标、调用者与所有实际间接
站点均检查，raw/SPI 混用、额外间接站点及身份变化仍拒绝。

普通生成 A 的六个配置都实际 ARM 编译和链接成功，而旧严格栈检查都失败。
逐项源代码/对象/库/回调来源审查后加入精确案例，再通过新的正常生成 B 独立编译。
B 的全部对象、`.su`、`.d`、ELF、map 与 A 的封印字节逐项相同；
六次 emitted `stack-report` 均退出 0，`SOFTWARE BOUND PASS`。
旧十个案例与所有上下文、余量、优先级、异常规则不变。

| 配置 | Release / Debug MSP 余量 | 状态 |
| --- | --- | --- |
| F407 reference | 372 / 372 B | 两种配置 ARM、artifact-check、严格栈均通过 |
| F407 installation capture | 372 / 372 B | 两种配置 ARM、artifact-check、严格栈均通过 |
| H743 ESKF20 + SYNC400 + opt-in rotation | 1364 / 2900 B | **磁旋转状态修复之前**的两种配置通过，不充当之后修复的证据 |

所有任务保留 256 B 上下文和至少 256 B 余量，Idle 恰为 256 B。
F407 保持原四级优先级域；H743 保留全部 16 级保守可配置异常嵌套，另含 NMI、
HardFault、扩展浮点异常帧以及 main/reset。资源与完整调用链见 receipt 和压缩原报告。
独立 checker 回归是 `bindings-final.log` 119 项和 `review-final.log` 34 项两次运行。
其前置历史 logger 夹具问题完整保留于 `bindings-regression.log`，通过固定原历史
源文件与出处解决，没有使当前严格源身份检查接受变化。

当前 proof 数据随后做无损表示拆分：一个 4,370 B 的版本 2 索引与 20 个独立案例，
最大案例 495,291 B，均低于新增仓库治理 2 MiB 上限。每个文件仍含原完整数据；
索引 SHA 由 checker 固定，所有案例（含未选中案例）必须存在并逐一校验 SHA、
名称和固定安全路径。重复 JSON 键、缺失/重复案例、越界/链接路径、篡改和超大文件
均拒绝；没有缩减源、库、对象集合或新增例外。
GUI 与 emitted checker 使用字节一致的纯数据解析器，GUI 不执行工程中的 Python。
`original-cases-equivalence.json` 从实际 `git show e143188...` 核对原十个完整案例，
与拆分后逐项严格相等；其余十个也与审查前格式的 canonical SHA 相同。
`split-final-tests.log` 为一次 **80 passed / 26.77 s**，包括篡改、历史格式、原十/新十
内容保持、报告消费以及导入参考工程时保留证明 owner。格式迁移本身不是另一次 ARM 编译。
最终状态安全修复、分拆与相应精确案例在 `84d44ea8`；没有改变源码覆盖、栈余量、
任务上下文、异常嵌套或回调例外。正式 receipt 最后再次读取全部 A/B 编译产物并核对
封印；10 份实际 B 报告也通过当前 GUI 生产 summary 编码/解码入口，含 2 份明确的
修复前 H7 历史记录，当前源码有效的是另外 8 个配置。

H743 输入是经过逐文件核验迁移的
`D:/SilverStar_Archive/retained_inputs/synced-h743-fixture-v2`；
详见 [`retained_h743_input.json`](retained_h743_input.json)。它是软件 CubeMX 夹具，
不是同步接线、外设时延或板载运行证明。

## 本轮关键合同

| 边界 | 实际检查及结果 |
| --- | --- |
| GPIO 消费边沿 | F4/H7 × 9/96 容量真实后端：无效 ID/NULL、未消费和积压拒绝、64 位时间跨界、锁前 IRQ、嵌套临界区；输出不半写，实际 GCC `-fanalyzer` |
| SYNC400 / native qualification | 现行真实 C 的 blob/reset/readback、配对/顺序/间隙/跨 epoch/停滞拒绝；生成的资格 owner 用 GCC `-fanalyzer` + LTO 验证物理身份、两帧连续性、时效、Stop；物理端口仍为注入输入 |
| 磁旋转 logger 满 | 真实 owner 在 ADOPTED 日志拒绝时不发布/应用新旋转；保留普通满队列错误路径 |
| 磁旋转 Stop | maintenance revocation 在下一次 DeviceTask Service 之前使 Provider/TryApply 拒绝，未覆盖调用方输出 |
| 磁旋转 history 索引/计数 | 原始 head=8、count=9 实际运行 2 项失败；owning payload 增加访问/发布前检查，先撤销 valid/qualified，之后进入真实断言终止路径 |
| 原生压力/磁传感器 | 真实 BMP390/MMC5983MA 内部坏状态在 I/O 之前终止；总线错误不发布；实际 GCC `-fanalyzer` |

`critical-final.log` 是当时 23 项单次运行，`rotation-contracts.log` 是随后 10 项；
history 修复后的完整 `test_release_mag_rotation.py` 是
`rotation-state-after.log` 的 **12 passed / 36.81 s**。前失败原始日志保留。
故障测试只在 Host 拦截既有终止 trap，以便读取真实 fault record；它不进入目标固件，
也不证明 MCU 能恢复。该检查依赖 DeviceTask 对 history 的唯一写入所有权，不把
不一致并发读取当成有效断言。

## 状态修复后的当前 H743 与真实 PID

本轮磁旋转 history 修复后再次正常生成 current-a，H743 与实际导入的新 run PID
各自 Release/Debug 编译链接和产物检查成功，而尚未审查的严格栈均按原门禁退出 2。
H743 完整选中输入只改变 owning `mag_rotation_runtime.c`；PID 采用实际导入模型，
不是默认关闭配置：Kp=1.75、period=10000 us、output limit=0.4，仍 deployable=false。
源与对象审查后独立正常生成 current-b，其四种配置实际重新编译，all、artifact-check、
stack-report 共 12 项退出 0。完整 A/B 编译对象与链接产物逐项相等。

| 当前配置 | 关键任务余量 Release / Debug | MSP 余量 Release / Debug |
| --- | --- | --- |
| H743 + SYNC400 + online rotation | Device 372 / 896 B | 1364 / 2900 B |
| F407 + 本轮真实 run PID | Flight 392 / 1720 B | 372 / 372 B |

H743 主 SRAM 为 220988 / 221112 B，占物理容量 524288 B；DTCM 中 MSP 保留 8192 B。
PID SRAM 为 101676 / 101812 B，相对原 102400 B 工程预算余量为 724 / 588 B；
相对物理 131072 B 则为 29396 / 29260 B。PID CCM 已用 62712 B，余 2824 B。
原固定安装 F407 的 CCM 65072 B / 余 464 B 仍单独保留，不能拿普通配置余量代替。

current-b H743/PID 的原样 `power10-check`、`architecture-check`、`static-analysis`
另一次完整 6 项均退出 0；static-analysis 真正使用 ARM `-fanalyzer` 编译并链接，
不以语法检查代替。P10 的固定全固件 critical-contract NOT PROVEN 提示保留。
当前新函数和故障路径的局部证据不等于全部第一方/第三方函数已完成逐条语义审计。

FLP 严格生产入口发现的合成 Golden producer 缺项由 owning producer/expected 源修复。
之后另外新鲜生成四个模型；全部选中编译源、头、汇编、链接脚本、构建/选源声明、
Generated metadata、decoder C 和 `.ssdecoder` 与各自已编译 B 精确一致。
工程 component_provenance/payload_digest **确实变化**，逐文件差异属于 Tools/证明格式
及 Tests/Host/Golden/runner；已记录在 `final-generation-equivalence.json`，没有把整个
工程描述符说成未变，也没有把格式/Host 数据迁移说成新增 ARM 编译。

最终生成工程 Host 实际结果：

| 运行 | 实际结果 |
| --- | --- |
| H743 原样 `make host-tests` | exit 0，72 executables / 4,405,830 checks / 0 failures；6 compile-pass、16 expected compile-fail、34 按选型 not-applicable；完整 mandatory storage/logger 尾部通过 |
| PID `-Only lifecycle_logging,control_provenance,control_research` | exit 0，3 executables / 1146 checks / 0 failures；17 按选型 not-applicable；mandatory storage/logger 尾部通过。**这是明确的选择性运行，不是 PID 全套** |

完整 not-applicable、预期编译拒绝与夹具声明保留在原日志。
`lifecycle_logging` 使用真实 FlightTask 与明确禁用的控制 adapter，不能充当 enabled
控制器端到端 Host 证据。`control_research` 使用实际启用的 backend/runtime 与本轮
生成的参数，任务表和输入端口是明确的合成夹具；来源/epoch/校准代际/健康/队列拒绝
另由 `control_provenance` 执行真实 owning C。enabled FlightTask 的调度顺序和静态
调用闭包由源码审查与真实 PID ARM 产物证明，控制输出没有接执行器电气驱动。
存储夹具声明逻辑记录与物理 epoch 未覆盖；前述独立资格边界测试不会被它代替。

三个完整测试文件 `test_mission_critical_contracts.py`、`test_mission_process_native.py`、
`test_control_research.py` 加正常生成 owner/栈工具回归 1 项，实际单次
**94 passed / 244.00 s**。包含 PID/LQR 27 类正常/过期/故障/抢占/Stop/调度场景及
实际 body-Y 力矩单位，事件/活动范围/就绪位/终止状态坏值故障，生成阶段名与稳定 ID、
恢复动作权限、依赖就绪与实际校正加速度消费者。编译实际执行 `-fanalyzer`，Host 终止
trap 拦截仍是测试专用，不是 MCU 恢复。完整命令、源文件/编译器身份与日志在
`task-contracts-command.json`、receipt 和 contracts 条目保留。

## 运行方法与证据边界

```powershell
.venv/Scripts/python.exe apps/SCG/main.py
.venv/Scripts/python.exe apps/SCG/tools/validation/capture_workspaces.py <新输出目录> --scale 1.5 --language en_US --theme dark
.venv/Scripts/python.exe apps/SCG/tools/validation/generate_stack_review_cases.py <新输出目录> --h743-input D:/SilverStar_Archive/retained_inputs/synced-h743-fixture-v2
.venv/Scripts/python.exe apps/SCG/tools/validation/generate_stack_review_cases.py <另一个新输出目录> --case research --research-model <本轮已应用的research.ssproject>
```

上述源码入口自行设置包路径；正常生成目录中的 Makefile 使用
`mingw32-make CONFIG=Release GCC_PATH="D:/Arm GNU Toolchain/14.3 rel1/bin" all`
以及独立 `artifact-check`、`stack-report`、`power10-check`、`architecture-check`、
`static-analysis`、`host-tests`。生成工具不替 gate 自动加入案例。

硬件待测独立保留：MCU 实际栈水位、真实 IRQ 嵌套和抢占、WCET/周期迟到、
DMA/cache、传感器同步接线和时延、储存断电恢复及飞行验证。
Power of Ten 的文本计数不证明全部关键合同，也不代表原始规则完全合规或 NASA 认证。
其全固件手工 critical-contract NOT PROVEN 不会被本报告的局部边界审查改写成 PASS。

正式目录仅保留 185 个去重后的日志/报告/图像输入及 1 份 receipt，总计约 1.50 MB，
最大单文件小于 440 KB。所有压缩文件已实际解压比对原始字节 SHA，完整 A/B 输入和
产物摘要仍在各案例封印与 receipt 中。新增产物治理仍使用原 2 MiB 上限，没有为本轮
证据增加例外。

## 任务副本清理（2026-11-11）

仅处理本任务创建并已封印的 16 个过期生成/测试目录，不扩展到历史 `.work` 或其他 owner。
原 v1 清单保留，v2 补齐 `.bak`、`.tdproj`、`.tdrun`、`.sstuning`、`.tdmotor` 等保护。
所选目录内项目、CubeMX 输入、decoder、日志、Tests、HardwareGenerated 和 fixture 留原处。
`b/f4`、`b/capture`、`current-b/h7`、`current-b/research`、`final-generation`
五棵树完整保留，包含上述当前八个 Release/Debug 配置及正常生成/Host 输入。

两阶段各自实际 exit 0：先逐文件验证祖先路径、非 reparse、size、mtime、file ID、device、SHA，
归档 15,944 条路径；3,892 个去重内容对象逐个写入磁盘、重新打开读回校验大小/SHA，
再复核全部来源及保留树。取得 `archive-verified.json` 后，删除阶段重新检查清单、归档和来源，
只移除清单中的精确叶子及空目录，没有递归删除或修改 ACL。

实际移除 **13,759 文件 / 1,081,518,924 逻辑字节**、5,524 个空目录，错误为零。
**13,786 个保留文件**最终再次核验身份及 SHA；删除日志与清单一一对上，所有已记录删除路径
均已确认不存在。脚本统计时点任务树剩 14,114 文件 / 1,245,375,174 B；此后增加了小型证据
整理脚本和末尾日志，不以这个时点数冒充全工作区最终盘点。

持久归档：`D:/SilverStar_Archive/20261110/task/scg/generated-copies.zip`，267,900,415 B，
SHA-256 `398eb4066b8e504fe311e19904a4de68b279cccd9b39771850557527913822ca`。
同目录保留原清单、`manifest-v2.json`、执行脚本、恢复说明、实际删除 journal 和结果收据。
ZIP 使用 `objects/<SHA-256>`，原路径映射在清单中；实际恢复采用有界单文件 scratch，
没有声称同时重建完整目录树。v2 清单 SHA：
`d9624f463027bd9c943e532407dd4590797ad80d072672da83c66cf8485f5f51`。

D 盘删除阶段 free 从 39,426,809,856 到 43,731,083,264 B，区间变化 +4,304,273,408 B。
当时还在并行清理旧 FCCG 等任务，且归档和来源位于同盘；此数**不能归因于本批物理回收**，
也不能与逻辑删除量或 ZIP 大小互换。完整阶段记录、命令对应日志散列、保留与限制见
[`scg-cleanup.json`](scg-cleanup.json)。本次未修改产品或重跑无关固件测试。

## 清理后正常入口复核（2026-11-11）

清理完成后另建一个 research / STM32F407 / Release 工程，复用本轮实际已应用的
`integration/research.ssproject`，不修改此前封印的 `current-b`，不重复八配置矩阵。
输入 SHA-256 `35da63b60ae0d5722d37f22defd7791d182e7afc7bdcf7768eb544beba111297`
在生成前后及收据整理时一致。执行记录 HEAD 为
`ea0f587dd3364b850e5ad07e7544d0bd934dcb12`；这次验证没有修改产品或门禁。

实际依次运行正常 `generate_stack_review_cases.py --case research --research-model …`、
生成 Makefile 的 `all`、`artifact-check`、`stack-report`，四步均 **exit 0**，
合计 288.092 s。完整 argv、cwd、配置、工具版本、每步耗时和日志散列见
[`scg-postcleanup/receipt.json`](scg-postcleanup/receipt.json)。严格栈检查实际输出
**SOFTWARE BOUND PASS**，绑定已有审查案例 `convergence-current-20261110-research-Release`；
任务最小预算余量 256 B，MSP/main/ISR 预算 2,304 B、估计 1,932 B、余量 372 B。
实际 FLASH/main SRAM/CCMRAM 使用量分别为 361,468 / 101,676 / 62,712 B，
heap 保留量及运行时分配符号均为零。

新 ELF SHA-256 `1d589c00f14c47b57f1e17155d532582b1cd3968536518802a0b54ec540fd8b1`。
新工程保留在 `.work/gui-convergence-20261110/scg/post-cleanup-research/`，
运行后共 42,964,284 B；这是清理收据统计之后新增的一次验证输出，不混入原删除量。
独立正式证据共 15 文件 / 183,072 B，含完整日志、执行脚本、输入、生成记录、
实际 `memory-report.json`、`stack-budget.json` 与审查案例；每个压缩文件都实际解压
比对原始字节。它们不计入上方原 `scg/` 185 个 payload 的历史数目。

收据整理时 SCG 相对记录 HEAD 的唯一已跟踪源码差异是 GUI application 入口的
窗口边界修正；该入口不被本生成命令导入，本次不声称验证这个 GUI 修改。
本次也未重跑 Power of Ten、architecture、static-analysis 或 Host 全套，
不改写既有证据范围、全固件手工 critical-contract NOT PROVEN 或硬件待测状态。
