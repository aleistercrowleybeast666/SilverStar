# 2026-10-08 授权后静态任务 000044：有限通过与剩余阻塞

本记录承接[准备阶段](STATIC_BENCH_PROGRESS_20261008.md)。准备阶段 Release 命令 exit2/stack FAIL 和当时未烧录、未 START 的结论保持原样。本次在用户明确批准两个完整源文件哈希后，从源码提交 `cac7bd29bf6f6aec5297715ea14893b4b7684953` 重新生成、实际 ARM 编译、运行各门禁，并完成一次 Flight 烧录和一次静态任务；没有重刷 Ground、重复 START 或复位重试。

任务 `000044` 的权威 READY、START、Delay10 逻辑展开、落地、日志关闭及 finalized 观察通过。**实际 TF 文件尚未交回，FLP 实录严格打开和保存重开为 NOT_RUN；两次 logger state rejection 与遥测发送拒绝未归因，零丢样/完整实录验收为 NOT_PROVEN。** 不能把脚本 exit0 扩大为全系统验收完成。

## 源码、设备、产物与操作边界

分支为 `fix/nightly-user-ready-20261003`。应用代码检查/生成/烧录基线为上述 `cac7bd2`；本报告的后续提交只归档文档和证据，通过完整应用源文件哈希盘点核对。原三个未跟踪 `work_*_20261006` 输入保持原字节。没有 push、tag 或 Release。

用户报告 TF 插入、设备静止且“+Y 摆放”、全部执行机构物理断开。COM3 为 CH340 `1A86:7523`、位置 `1-1`，230400/8N1，打开前 DTR/RTS=false。DAP 序列号 `132765403520`，Cortex-M4/F407 ID `0x10076413`、512 KiB；寄存器不独立证明 VET6 封装后缀。原配置、资源分配及用户接线背景作为匹配上下文，未猜引脚。

候选 `.work/bench08c_f407` 名称固定为 `KF6_Static_20261008_f045d8c`，这是批准的显示名，**实际生成源码提交为 cac7bd2**。SS0.5/F407VET6、Full、JY901B vertical ORIENT、M9N、SX1281、SD_SDIO、OneFace、原矢量对准、KF6、二子样圆锥/划桨、Delay10、原 200 Hz、普通/估计器队列 80/48 及任务栈均未改。Core main.c/main.h、IOC、app_task_config.h 与源工程逐字节相同；外部用户工程未覆盖。

| 本次实际产物 | SHA-256 |
| --- | --- |
| C 工程 ELF，3326520 B | `14637f20ac2b83bc4b169b232a364d037013e494444aa23ad246070148ae4cfd` |
| BIN，331020 B | `5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3` |
| 精确 `.ssdecoder`，144321 B | `46b449244dcfde73baa5faaa795ac496d34f097bd095824959f53210067fafe2` |
| 根 `.ssproject` | `067d8d9750c28c41d32b052d161595a6fc44d2b60c8a8ea8e9cb3ea40f941ef5` |
| generated project_semantics.json | `3ccbafd3475a4ed8ebaa343307447651b31d1b17fb0a1c17ce75e578a9c5a2a9` |

前一次 B 工程与本次 C 的 BIN/decoder 相同，ELF 因调试源路径改变而不同；本次仅以 C 的实际 ELF 建立 SWD 地址/布局。decoder manifest 继承的历史 firmware_commit 字段不能代替本次实际源码身份；本次身份由生成记录、源盘点、命令和产物哈希独立绑定。

03:44 UTC 只读复核目标及 512 KiB 备份，SHA `e72caaa5adbb92d69854d824ce05ee086a2a1deb83f2e79a3d70ed01aebe8aa1`，与先前只读备份相同。03:46:51.542798–03:47:08.712002 UTC 完成一次 `program BIN 0x08000000 verify reset`，随后读回 331020 B，exit0、读回与上述 BIN 哈希完全相同。没有 option-byte、保护修改、mass erase 或 Ground 操作。旧 28b/000041 不能替代此任务。

## 两个源哈希为何不同，以及影响

本次用户授权只把以下两份**完整字节**纳入 owning payload 的审查证据：`Generated/Src/project_metadata.c`=`ae4706ff828b966e517972f147eee2d5ca938a144ff437ef3b71d32a9f186181`；`Generated/Src/project_log_decoder_profile.c`=`e66c2a4581505fdb114a88f7ff65c866c0e2c0b9b4c99186d0922960bbe98da4`。修改位于 [check_task_stacks.py](../apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py)，没有改阈值、callback 目标或未知源码 FAIL 规则。155 个实际编译 C 源没有额外 unknown；生成 checker 与 owner 相同。对这两个文件各追加未批准注释，仍被完整源码检查拒绝，两项负向检查 PASS。

1. `project_metadata.c` 的配置摘要由 `0x6E6BDB8D` 变为 `0xA79E2E92`，由候选显示名进入 ProjectGenerationState_Normalize 的摘要输入引起；这标识新的配置身份。另一差异是 descriptor getter 前一空行，来自 renderer 的 compact snapshot assertion 占位模板（`4d49ab28` 引入，Full 展开为空）。空行不改变 C token、控制流或数学。恢复原显示名可以恢复旧摘要，但仍不能恢复完整源字节哈希。
2. `project_log_decoder_profile.c` 只改变 semantic hash 和 generation profile hash 数组，getter 与 record catalog hash 不变；原因是当前完整 semantics 已变化，不能笼统称为“改名”或“无行为影响”。[render.py](../apps/SCG/src/silverstar_fccg/generator/render.py) 的物理设备定义按完整 catalog 排序编号。`f8ae48f` 加入 NRF24L01P 占据编号 25，即使本机选择 SX1281，后续 POWER_ADC/STORAGE/OUTPUT 仍由 25/26/27 变为 26/27/28。实际硬件绑定没有变，但日志数字的解释必须用本次 matching decoder。
3. core/storage/power 的组件 manifest 锁及源码归属元数据有历史更新，包括 `8ce6993` 的 InputVoltage 服务到 Adapter 归属调整。这改变 semantics/provenance。详细 old/new manifest、源 diff 和规范化诊断归档于证据目录；不推断这些元数据差异单独证明硬件行为。
4. 还有**实际日志集合变化**：`2f26b010` 的首版“只记录所选算法”策略，在 [feature_tiers.py](../apps/SCG/src/silverstar_fccg/project/feature_tiers.py) 中令 KF6 配置的 PURE_INS 日志有效开关为 0（原工程为 1），原因 `logging.algorithm.disabled`；用户存储的选项没有被删除。Raw IMU、惯性增量、修正 IMU、ESTIMATOR_STEP、KF6 记录设置保留。这改变记录集合，不改变 Pure INS/KF6 导航数学。不能宣称新版全部日志流与旧版相同。

old/new `record_catalog.json` 字节完全相同，SHA `7af595f2376c22dc57cd63a34340d685dd8785fc20c5e1ffe88f7bb9a355c74b`，因此本比较未改变记录字段布局；语义编号、availability、组件锁变化则要求精确包/Descriptor 匹配。M0/CMD/ACK 帧规则未改变。保持旧 hash 数组会错误陈述新工程语义，省略未知文件检查会弱化边界，两者都不是合适修复。

## 本次重新执行的软件检查

全部命令完整日志及开始/结束 UTC、工具版本、cwd、exit、源码身份见[证据 manifest](evidence/static_bench_authorized_20261008/manifest.json)。完成后没有重复重负载检查。

| 检查 | 本次结果与范围 |
| --- | --- |
| generation / source graph / exact unknown boundary | PASS，155 C 源、无额外 unknown、2 项越界源码拒绝 |
| architecture-check | PASS / exit0，356 checks |
| power10-check 原样执行 | 文本 PASS / exit0，6329 checks，111 first-party C，2761 functions，815 nonblocking recommendations；critical-contract manual review NOT_PROVEN |
| ARM Release all + artifact-check + stack-report + memory-report | PASS / exit0，106.852 s，实际编译链接、callback 源证明/任务预算执行完成 |
| static-analysis | PASS / exit0，实际 ARM `-fanalyzer` 编译，不是 syntax-only |
| Host 全部 | PASS / exit0，309.475 s，80 executables、4446469 checks、0 failures、11 compile-pass、18 expected compile failures、8 NOT_APPLICABLE；四个存储阶段完整执行 |
| Flash verify/readback | PASS / exit0，一次 Flight 操作、精确 BIN 读回 |

历史软件结果仍以[准备报告](STATIC_BENCH_PROGRESS_20261008.md)和[软件收尾报告](NIGHTLY_SOFTWARE_CLOSEOUT_20261008.md)各自日期/源码范围为准：SCG 65 PASS；四档 83 PASS/3 setup ERROR，另用正确应用目录运行 3 GUI PASS，不能拼为同批 86 PASS。FLP 合并 124 PASS、GNSS 15 PASS、GSHC 53 PASS 属已有应用版本回归，本次未重跑；历史 Qt/Shiboken native abort 根因仍未证明，保留 FAIL/NOT_PROVEN。当前仅 checker 证据源改动，没有将历史测试重新标成 cac7bd2 实际执行。

## 一次静态任务及诊断

任务脚本 03:51:10.479203–03:52:05.805673 UTC（最终诊断另有独立时间），exit0。一次 CAPABILITY_ACK、CAL_START OneFace、ALIGN_START、UNLOCK、START；每一步用新收到的权威 preflight 状态确认，不以 ACK 代替 READY。起始校准/对准为 IDLE 才执行，没有覆盖既有 READY、CAL_RESET/SAVE、多面/运动操作或显式输出指令。START 前 TF/logger admission 检查通过。

| 观察 | 结果 |
| --- | --- |
| mission ID / 文件 | `44` / `0:/missions/000044/flight.sslog` |
| AIR 事件时刻 | START 3 ms；Delay10 逻辑展开 10001 ms；LANDING 14004 ms |
| 接收 | 53 flight frames，最大接收间隔 0.583 s；178 GSP frames，CRC/resync/discard=0；未观察 BOOT/FAULT |
| 生命周期及故障 | LANDED=6；assert active=0，CFSR/HFSR=0 |
| START snapshot | generation=acknowledged_generation=1，phase=0，io_fault=0；61/61 快照条目遍历 |
| 日志完成 | session_finalized=1；file_open/session_active/aggregate_length=0；accepted=dequeued=10175 |
| 队列及容量 | 普通 80、估计器 48；head=tail，overflow/capacity_reject=0；高水位 22/7 |
| I/O 观测 | append/flush/serialize/close/final-status failure、discarded bytes、storage/sink errors=0；bytes_written=885023（运行时计数，尚非取卡实文件大小验证） |

before_unlock 与 after_start_live 为非 halt 观测；仅 timing 用相同偶数序号括住快照，多字段跨时刻一致性不能假定。落地且日志完成之后，执行一次 halt/capture/resume；原始 OpenOCD 明确记录 `RESUMED_AFTER_COHERENT_CAPTURE`。这个 halt 后的 timing/stack 值不是飞行实时或 WCET 证明。

必须保留的异常与边界：

- logger `state_reject_count`：START 前 0、任务早期 0、收尾后 2。源码计数分支包含未初始化/停止接收以及 alignment evidence 的 writer fault；本次 writer fault=0，但没有逐条记录归因证据。不能把这两次自动当成正常收尾，也不能证明不是导航/必需证据丢失。
- SX1281 `tx_dropped`：43233 → 45473 → 46909。计数分支包含普通/优先/跟踪发送队列拒绝与 radio fault 排队清除，未记录每次调用/帧身份。本次 tx_timeout/rx_error/CRC/bus error=0，不足以把 tx_dropped 判为无损或无影响。原始 178 帧接收证据只覆盖收到的帧。
- 累计 timing max interval=94308 us；max processing duration=1864 us，duration>20 ms=0，prediction cap=0，prediction queue overflow=0。interval 不等于处理耗时；缺少 max interval 的发生时刻/事件归因，不能证明它发生在任务内或任务外，更不能用 processing duration 掩盖调度间隙。TF 完整时间序列仍需核对。
- GNSS position/velocity updates=0，origin invalid；本次为无 GNSS 固定点更新的室内静态观察，不验导航精度。导航的 mission_running=1 是落地时保留的导航快照字段，不能覆盖权威 LANDED。
- 栈 `0xA5` untouched prefix（words floor）：Device181、INS250、Estimator487、Flight218、Logger403、Serial1112、Telemetry639。运行时 task high-water-valid=0；以上仅 halt 后填充值观察，不等于 scheduler API 高水位或充分安全裕量。全部任务/库/间接调用/MSP/ISR 嵌套、动态帧和 STM32 WCET 仍 NOT_PROVEN。

## 最小后续验收与文档入口

本次已停止串口并关闭诊断连接；任务已落地、日志关闭，不再自动 START/复位。需要用户取卡并提供**整个 `missions/000044/` 原目录**（flight.sslog、manifest、全部 snapshot/object sidecars），保留原件，同时携带本次精确 decoder。AIR 当前没有日志下载通道，SWD 读计数不能取代 TF 文件。

1. 对原始文件建立 SHA 清单，核对实文件长度、结束/final 状态、完整记录序号/普通日志丢失诊断、导航时间连续性及 START 快照/Descriptor。两次 state reject 和 tx_dropped 的影响不能确认时继续 NOT_PROVEN。
2. FLP 生产入口通过 LogOpenCoordinator 使用本次 decoder 和 Recorded Descriptor 严格匹配，拒绝 fallback/default；分别验证主副数据源和全部 run、真实保存进度、取消/关闭/重复操作、原子提交和重开。
3. 保留现有 GPIO/Delay10/算法/队列与安全断开条件；任何第二轮硬件动作先按用户下一步指令确定，当前不自动重跑。

文档从[用户流程总览](USER_WORKFLOW.md)按“硬件与四档 → SCG 配置生成 → GSHC 采集 → FLP 分析 → 算法原理与实现 → 验证边界与排障”阅读。[四算法实现章](algorithms/NAVIGATION_IMPLEMENTATION.md)第 1 节坐标/单位，第 2 节 Pure INS，第 3 节 SF6 固定增益，第 4 节 KF6，第 5 节 ESKF15 右乘 body 姿态误差，第 6 节时间戳/调度/噪声/记录，包含公式、初始化校准与源码映射；数学冻结。

[推荐配置](SilverStar_Recommended_Configurations.md)的边界保持：H7 尚无当前生成支持；F407 ESKF15 运行失败未解决；F103/NRF 未实物验证；Logger 栈结论只覆盖记载 RET6 配置；无 GNSS 水平漂移；20% RAM 为建议。原 Power of Ten 与 F Prime-inspired adaptation 的范围不能混同，critical-contract review NOT_PROVEN 阻止完整手工验收声明，静态桌面任务不构成外场/飞行资格。

复现命令以证据中的实际命令为准，重跑必须使用新目录、重新确认硬件授权，不能覆盖原日志：

```powershell
# 仅说明已执行命令；当前不再自动执行硬件操作
.venv/Scripts/python.exe .work/static_bench_authorized_20261008/generate.py
.venv/Scripts/python.exe .work/static_bench_authorized_20261008/run_gates.py versions architecture power10 release analyzer host
.venv/Scripts/python.exe .work/static_bench_authorized_20261008/flash_candidate.py --execute
.venv/Scripts/python.exe .work/static_bench_authorized_20261008/run_static.py
```

这些 harness 有拒绝覆盖既有证据的保护。源工程、烧录前全 flash 备份、新 BIN/ELF/decoder、读回镜像留在 manifest 标明的 `.work` 路径，未大规模复制 vendor；formal evidence 保留原始命令、日志、布局、原始 SWD/串口字节及源文件哈希。
