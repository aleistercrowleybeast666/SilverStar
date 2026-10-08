# 2026-10-08 健康事件发布与日志终结边界修复

本轮完成一个已证实根因的最小软件修复。新增回归、完整 Host、真实 `-fanalyzer` 和 ARM 编译/链接通过；**原样栈门禁 FAIL，关键契约整体审查 NOT_PROVEN，新候选烧录及 TF 文件验收 NOT_RUN**。这不是整套验收完成或当前候选已上板的结论。

基线为 `fix/nightly-user-ready-20261003` 的 `8cee75afb0e0a81a8286587986005965adc53005`。本报告所在提交的固件修改仅为 owning plugin `estimator_task.c` 的四行；编译对象来自独立新生成目录 `.work/finalized_health_20261008_v1/project/Flight_Controller`，没有覆盖已有用户工程。精确脏源码补丁、生成配置、输入清单、工具版本、命令、UTC、退出码和完整日志见[证据清单](evidence/logger_health_finalization_20261008/manifest.json)。编译与最终提交的等价关系由规范化源码哈希及提交后验证建立，不将基线提交的旧二进制称作修复产物。

## 已证实根因与修复边界

前轮 DAP 首次拒绝现场的实际调用链为 `Estimator_HealthEventsPublish → LoggerBus_EventPush → ConfiguredRecordPush → PushStateGet`。EVENT 47 的参数是 barometer 融合组 4、DEAD_RECKONING、reason 1、年龄 2000 ms；现场 lifecycle=LANDED、logger initialized=1、accepting=0、FINALIZED，队列已空，accepted=dequeued=10109，overflow=0。首个断点由这个拒绝触发，因此它自己的暂停不能造成触发前的年龄。记录内没有先于首个命中的 active-flight 暂停；这些事实不证明传感器实物故障或任意调试条件下的时间准确性。

当前 INS 传播和 estimator 预测处理只在 FLIGHT/RECOVERY 运行。LANDED 后融合更新停止，但 `mission_running` 仍为 1，健康年龄仍有意义，原事件发布循环却继续向已经 FINALIZED 的 logger 推送。修复在 `Estimator_HealthEventsPublish` 入口使用现有 IRQ 保护的 `LoggerBus_FinalizationStateGet()`：仅观察到 FINALIZED 时，在 `ChangesGet` 与 push 之前返回。健康组/总体评估和真实超时不被删除。

没有全局忽略 BAD_STATE、改变 LoggerBus 返回契约或压制计数。没有以 LANDED 为统一过滤条件；LANDING 必须事件及 grace 期间的事件仍可发布。DRAINING、状态快照后发生的关闭竞态和队列满仍使用原返回处理，保留拒绝计数及 `ESTIMATOR_HEALTH_LOG_EVENT_FAILED`。快照与随后 push 不是一个原子操作，没有增加长 IRQ 屏蔽，也没有伪造持久化成功。重新初始化只验证现有静止条件下的 bus reset 与 health epoch 初始化，不创建 LANDED→START 重开能力。

数学、协议、四档队列/栈、健康超时、START ACK 超时、RF/PHY、引脚及开伞策略未修改。必要的生命周期契约已补到 [Mission snapshot](architecture/MISSION_SNAPSHOT.md#health-events-at-session-finalization)。

## 不变预期的红绿回归

Host fixture 提取实际 `Estimator_HealthEventsPublish` 函数体，链接真实 LoggerBus、SPSC、日志策略和 navigation health；Host 只提供 IRQ/assertion 边界及在真实状态快照之后注入关闭。它不模拟 TF 持久确认，也不证明 MCU 调度、WCET 或物理存储。

| 证据 | 结果与范围 |
| --- | --- |
| `red/` 初版 fixture | 无效 variance scale/sequence 种子被真实 supervisor 拒绝，作为 fixture 开发失败保存，不计作产品复现 |
| `red_valid_fixture/` 修复前源码 + 有效 fixture | 编译 0；7/11 PASS，4/11 FAIL；已关闭仍发布及重新初始化前的拒绝由 case 4/8 复现。case 6/10 的基线没有状态快照调用，故关闭注入没有触发，不冒充另两项硬件缺陷 |
| `green_owner/` owning 函数体 | 编译 0；同一有效 fixture、同一断言，11/11 PASS |
| `green_generated/` 新生成函数体及依赖 | 编译 0；11/11 PASS |
| pytest 规范目录重跑 | 4 PASS、1 FAIL，16.06 s；新增 11 场景和既有 23 场景通过；FAIL 是既有来源绑定测试拒绝新 estimator 来源 |

11 场景覆盖 Flight、Recovery、LANDED grace、DRAINING 拒绝、FINALIZED 停止发布、队列满、快照后 FINALIZED/ DRAINING 竞态、LANDING 与 grace 事件、静止重新初始化、新旧 epoch、inactive。generic finalized push 仍 BAD_STATE 且计数；健康 age 仍产生原 DEAD_RECKONING 状态。测试没有删除、放松断言或修改既有来源绑定测试。

pytest 首次使用默认 0700 basetemp 导致受限 Windows 目录不可读、5 个 setup error，随后 cleanup PermissionError；保留 `pytest.log`，不算 PASS。重跑复用仓库已记录的 `normal_test_paths.py`，只让全新测试目录用普通 mkdir 继承权限，没有修改已有目录权限、ACL 或沙盒；`no:cacheprovider` 引起的一个 Unknown config option `cache_dir` 警告原样保留。

## 新生成输出的逐项结果

配置来自不可变输入 `.work/bench08c_f407/SilverStar.ssproject`，SHA-256 `067d8d9750c28c41d32b052d161595a6fc44d2b60c8a8ea8e9cb3ea40f941ef5`；F407VET6 / 完整 / KF6 / OneFace / Delay10。保留旧显示标签以维持此前批准的两项 Generated 哈希；**显示标签不是源码提交或二进制身份**。配置键及 queue/stack/user config/Core/ioc 与既有候选字节相同，生成计划 valid=true、dangerous=false。155 个编译输入中只有 estimator 的新规范化哈希不在绑定表。未扩展允许表、未改门禁阈值。

| 检查 | 结果 |
| --- | --- |
| architecture/source graph | PASS，exit 0 |
| 原样 generated `power10-check` | 文本检查 PASS，exit 0；6329 检查、111 一方 C、2761 函数、815 非阻断建议；**critical-contract review NOT_PROVEN** |
| ARM Release / 链接 / artifact / memory | PASS，exit 0；实际编译链接，未用 syntax-only；BIN 331052 B |
| 原样 generated `stack-report` | **FAIL，exit 2**；`Changed or unknown complete callback binding source: APP/Src/estimator_task.c` |
| 真实 `static-analysis` | PASS，exit 0；ARM GCC `-fanalyzer` 编译 `.o` 并链接，完整日志保存 |
| 完整 generated Host | PASS，exit 0；80 executables、4446469 checks、0 failures、11 compile-pass cases、18 expected compile failures、8 not-applicable；详细范围保留完整日志 |
| focused pytest | **FAIL，exit 1**；4 PASS、1 来源绑定 FAIL |
| 本轮修复候选硬件与 TF | **NOT_RUN**，没有烧录、START 或新增 DAP 断点 |

候选 BIN SHA-256：`cf1a359c9212354b63b4af8b83f0db4008897eb333d35d220d8eec4a2f33da4c`；ELF：`e53e3d97e882be508de3e34e7e86800448bc5884ab3363a03c9ba44f1db1c8a6`。匹配 decoder：`46b449244dcfde73baa5faaa795ac496d34f097bd095824959f53210067fafe2`。`artifact_identity.json` 记录完整大小、map、源码图和配置哈希。单函数 `.su` 的 AppTask_Estimator 624→616 B 仅是 compiler frame，不是 task-path 栈证明。RAM 余量也不是栈安全证明；原 artifact 输出的历史 100 KiB 主 SRAM 预算提示未隐藏。

栈门禁最小后续需求是授权登记**这一份精确已复验源码**的规范化 SHA-256：`98df5cb8cefc0a2e5632bf51fd73319cef033d5a7bb511390c246dafb5b64610`。此前授权仅覆盖两项 Generated 来源，本轮没有自行新增。若授权，应修改 owning checker、再生成独立验证工程并原样复验；在 gate 通过和产物身份确认前不得把本候选烧到板上。当前板上仍为前轮恢复后的旧候选 BIN `5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3`，本轮没有硬件写入。

## 同类发布者与 ACK 的只读审查

Flight deployment/impact/landing 采用序列与必须事件；LANDING 成功后才 arm finalization，保持原语义。INS increments 和 Device 周期 power/health/STATS 已有 FLIGHT/RECOVERY 边界。Estimator GNSS recovery/source 事件经 prediction 或 setup 路径；本现场没有另一个同因证据。Device GNSS state/satellite/RF diagnostics 可能在新 source sequence 到达后于关闭期间继续发布，作为**未证实风险**记录，没有借此次修复改写它们。

独立的只读源码/ELF 调用图比较见 `callback_review.json` 与两份完整反汇编：155 个编译源的规范化文本仅 estimator 改变。候选新增 `AppTask_Estimator → LoggerBus_FinalizationStateGet`，新链接 getter 只直接调用 `PlatformCritical_Enter/Exit`；间接调用位置与基线相同。发布函数被编译器内联到 task，不能将独立函数符号缺失说成代码未编译。没有改变回调表或函数指针赋值、添加递归/分配。此比较没有绕过绑定或运行替代栈门禁，仍不证明完整 task/library/MSP/ISR 上界。

START response 已在发送前轮询，AckSend 排在 StatusSend/StreamSend 前，SX1281 control 优先并在两帧后允许 normal 防止饿死；命令缓存及幂等重试保留。未证实优先级缺陷，不修改公平性、800 ms 或 PHY。用户已将晚 START ACK 与观察到的关闭后拒绝作为非阻断发布观察接受；这是用户对这些现象的接受，不是零丢失证明、栈门禁 PASS 或未知 TF 结果 PASS。前轮[硬件报告](TEST5_GSHC_DAP_COMPARISON_20261008.md)的原始证据和状态不回写。

## 前轮 mission ID 与故意未完成记录

只在测试前 startup snapshot 取得 mission_id=46。TEST_5、current、current_diag 三次实际 START 的 mission ID **NOT_PROVEN**；无线 M0/GSP 没有这个字段，现场没有各自 TF header/snapshot。多次 startup/reset 可在没有 START 时预留额外目录，不能按顺序猜成 47/48/49。

| 会话 UTC 窗口 | 状态 |
| --- | --- |
| TEST_5：07:19:14.641–07:19:28.373 | 有限 START 后静止观察 6 s；未诱发 Tilt90 完成；随后烧录/reset 主动中断。标记 **intentional incomplete**，新 TF 尾部验收 NOT_RUN，不称产品失败 |
| 旧 current：07:20:53.007–07:21:23.097 | 无暂停，AIR LANDING=14009 ms；TF NOT_RUN |
| 旧 current_diag：07:28:15.973–07:28:48.027 | 有首拒绝断点暂停，AIR LANDING=14005 ms；TF NOT_RUN，不能作无干预运行证据 |

用户之后提供 TF 时，以真实 header/snapshot/时间窗/精确 decoder 对应并记录上述 intentional incomplete。保留原始日志，不补造缺失任务编号、不为恢复编号再开 DAP。

## 可复现命令与后续最小验收

在仓库根目录，将保存的 `generate.py`、`run_gates.py`、`run_pytest.py` 复制到一个全新的 `.work/<新版本>/`，再用 `.venv/Scripts/python.exe .work/<新版本>/generate.py` 和相应 runner 执行。保存脚本按自身所在目录创建独立 `project/`，不要直接在正式 evidence 目录运行。它依赖保留的 `.work/bench08c_f407/SilverStar.ssproject`；正式证据保存同字节 `reference_config.ssproject`。配置来源路径变化须明确记录，不能覆盖 v1 或已有候选。`run_gates.py` 按顺序调用生成工程中的 `architecture-check`、`power10-check`、`-j2 all artifact-check memory-report`、`-j2 stack-report`、`-j2 static-analysis`、`host-tests`。ARM 路径为 `D:/Arm GNU Toolchain/14.3 rel1/bin`，Host GCC `D:/msys64/ucrt64/bin/gcc.exe`。完整 argv、cwd、时间与 exit 在每项 `*_result.json`；脚本拒绝覆盖已有结果。

新增回归入口为 `apps/SCG/tests/test_logger_health_boundary.py`，配套 fixture/support。保存的 `run_pytest.py` 设置新生成工程环境变量，执行它与既有 `test_estimator_health_publication.py`。复跑亦须更换全新 basetemp/日志路径，保留失败历史。红绿提取单元与实际编译命令保存在各自 `results.json`，不依赖只打印摘要。

下一轮先解决精确来源授权并重验原样栈门禁，确认最终提交、ELF/BIN/decoder 与生成配置一致。之后才进行用户授权的一次有界静态运行：执行器断开、TF 已插、+Y 静止，真实 GSHC 单次 START、重试/晚 ACK 分开记录，观察正常 deployment/landing/finalization，避免重复完整长日志和 ESKF15 重算。软件 Qt API 自动化应明确披露，不声称鼠标操作。Ground 固件不动；没有必要不新增断点。

TF 文件验收必须由用户取回真实数据后完成：记录不可变输入哈希，用精确 decoder 与 Descriptor 经 LogOpenCoordinator 打开，核对全部 run/主副源、序列缺口、普通与导航丢样、最终尾部及快照，不用 Host 结果替代。首次完整任务的当前文件闭合/持久性仍待验证。

用户流程、四档与四算法文档仍按[总览](USER_WORKFLOW.md) → [硬件与档位](SilverStar_Recommended_Configurations.md) → [SCG](FCCG/USER_GUIDE.md) → [GSHC](GSHC/APP_README.md) → [FLP](FLP/APP_README.md) → [纯惯导/SF6/KF6/ESKF15 原理与实际实现](algorithms/NAVIGATION_IMPLEMENTATION.md) → [验证边界](NIGHTLY_SOFTWARE_CLOSEOUT_20261008.md)阅读。本轮不改变数学、四档契约或推荐证据。H7 当前不支持生成、F407 ESKF15 运行失败未解决、F103/NRF 未实物验证、Logger 栈限已有 RET6 配置、无 GNSS 水平漂移、20% RAM 为建议均继续有效。
