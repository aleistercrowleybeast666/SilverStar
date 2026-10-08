# 2026-10-08 单次复查：任务 000045

用户在[任务 000044](STATIC_BENCH_ACCEPTANCE_20261008.md)后要求“再试一次，看看是否还会出现”，仍明确所有执行器未连接、静止 +Y、TF 已插入。本次只有一次新的有限静态生命周期；没有重新烧录、Ground 重刷、固件/参数/算法修改、额外输出指令或自动重试。**拒绝现象复现：logger 收尾后 1 次 state rejection，SX1281 发送入队拒绝增长；约 94.3 ms 最大循环间隔单字段再次在 START 前出现。日志实际文件完整性仍待取卡验证。**

## 身份、必要复位与采样方案

应用源码仍为 `cac7bd29bf6f6aec5297715ea14893b4b7684953`；本次开始时文档 HEAD 为 `87d98e598db5706a2d23d09e64ef0d77e1af8f90`，分支 `fix/nightly-user-ready-20261003`。2233 个应用文件与已验证源盘点完全相同，不重新运行已经完成的大测试。三个原未跟踪盘点文件保留原字节。

只读确认 COM3 CH340 `1A86:7523`、位置 `1-1`；COM9 DAP `FAED:4870`、序号 `132765403520`。Cortex-M4/F407 ID `0x10076413`、512 KiB。04:28:05.824915–04:28:12.959 UTC 从 `0x08000000` 读取 331020 B，SHA-256 为 `5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3`，与既有 cac7bd2 BIN 完全一致。只读识别没有 halt、reset 或 flash。寄存器只识别家族/修订/容量，不独立证明封装后缀，物理放置/执行器断开以用户确认作为本轮条件。

复位前 live 状态：mission44、LANDED=6、accepting=0、finalization=3、file_open=0、session_active=0、session_finalized=1、aggregate_length=0、assert active=0、CFSR/HFSR=0；前后状态括号同为 `[6,0,3,2]`，旧最大间隔仍 94308 us。现有 [FlightCycle START precondition](../apps/SCG/plugins/builtin/silverstar_flight_logic_cycle_reference/payload/FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c) 把 LANDED/Postflight 的 START 锁住，logger finalized 不会再打开。没有开放的任务重置命令，不能用直接修改 RAM 状态来重开任务。

确认 COM3 可独占打开（DTR/RTS=false，未发送字节）后，04:30:06 UTC 执行唯一一次 `reset run; shutdown`，exit0；没有烧录。启动内 counters/maxima 因复位重新初始化，下一任务 ID 为45，不与000044的绝对计数相减。前置 flash 读回在复位前完成；本轮复位后五次采样均不 halt，不把旧任务 halt 或旧启动累计值带入新任务。

采样计划先保存到 evidence：复位前关闭状态；校准/对准权威 READY 后 preSTART；实际 flight transition 后 active；首次收到 LANDING；LANDING 接收 +1.4 s；LANDING 接收 +4 s。AIR 接收持续进行，SWD 由单个工作线程顺序运行，每次约0.20–0.23 s，不并发读探针。live 数据多字段可能跨时刻；新增 lifecycle/accepting/finalization/state_reject 前后括号，分别保存其原始值。AIR 的 LANDING **主机接收时刻不等于 MCU 落地时刻**，所以采样阶段以读到的实际状态判定，不能仅凭延迟名称判断。

AIR 当前没有这三个内部计数的直接实时下载接口，故使用已有只读 SWD 诊断方式。没有活动期 halt，仍不能把 SWD 总线访问当作绝对零扰动。进程名枚举未见其他 python/openocd/compiler/make 任务；Win32_Process 命令行查询被环境拒绝，没有改系统权限，也不能据此宣称能查看全部不可见工作。

## 实际执行结果

串口脚本 04:30:28.196579–04:30:55.683445 UTC，exit0。一次 CAPABILITY_ACK、CAL_START OneFace、ALIGN_START、UNLOCK、START，均无命令重试；从 IDLE 才做单面校准/对准，未覆盖既有 READY，未 CAL_RESET/SAVE、多面运动或其他硬件操作。只用 ACK 确认命令响应，使用新收到的 preflight READY 作为 START 前提。

| 项目 | 000045 本次结果 |
| --- | --- |
| 文件 | `0:/missions/000045/flight.sslog` |
| AIR 事件，任务相对时刻 | START 2 ms；Delay10 逻辑展开10001 ms；LANDING14006 ms |
| 接收 | 53 flight frames；最大接收间隔0.589 s；149 GSP frames，CRC/resync/discard=0；无观察到的 BOOT/FAULT |
| 最终状态 | LANDED，accepting=0，finalization=3，文件关闭、session_finalized=1、aggregate_length=0 |
| START 快照 | generation=acknowledged_generation=1，phase=0，io_fault=0 |
| 队列 | 普通80/估计器48；head=tail，overflow/capacity_reject=0；high water22/7；accepted=dequeued=10114 |
| I/O | append/flush/serialize/close/final-status failure、discarded bytes、storage/sink error=0；bytes_written=878123，仅为运行时计数 |
| 调试操作 | 0次烧录；1次启动复位；0次活动期或收尾 halt；连接已关闭 |

上述功能检查 PASS 是有限流程观察，不能将脚本 exit0 扩大成完整实录、零丢样或飞行资格 PASS。

## 同口径计数对照与复现判断

| 阶段 | 000044 logger state rejection / SX1281 tx_dropped / 最大间隔us | 000045 同项 |
| --- | --- | --- |
| START 前（含随后 UNLOCK/READY/START 的基准窗口） | 0 / 43233 / 94308 | 0 / 7763 / 94307 |
| actual flight 后早期 | 0 / 45473 / 94308 | 0 / 9784 / 94307 |
| 首次 LANDING 接收后，实际宽限期 | 未采样 | 0 / 11365 / 94307，accepting1、finalization1 |
| LANDING 接收+1.4s，实际 finalized | 未采样 | 1 / 11365 / 94307，accepting0、finalization3 |
| 最后关闭状态 | 2 / 46909 / 94308（旧任务45s观察后halt捕获） | 1 / 11365 / 94307（LANDING接收+4s，live） |
| preSTART 到最终的 tx_dropped 增量 | +3676 | +3602 |

两轮观察窗口及启动前等待时间不同，绝对计数、总接收帧数、日志字节数和增量不用于做精确频率/丢包率比较。原来000044约256s uptime时才做 preSTART，000045约28.7s；本次复位清零后仍出现同一类现象。

**logger：复现的是停收后的拒绝，次数由2变为1。** 本次第一次 LANDING 快照的状态前/后括号为 `[6,1,1,0]`；+1.4s和+4s均为 `[6,0,3,1]`。因此直接观察到“落地宽限期0拒绝 → finalized后1拒绝且不继续增加”。源码中关闭 accepting 的唯一正常路径是 landing+1000ms grace 到期进入 DRAINING；initialized 不会退回0，writer fault锁存为0，目标代码没有调用 LoggerBus_Reset。可排除本次容量满/写入失败触发这些 state rejection 的解释。

仍不知道这一候选 push 的记录类型、调用者和逐条时刻。[LoggerBus_ConfiguredRecordPush](../apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/logger_bus.c)先做 state check，再检查 enabled/period；被拒绝的候选甚至可能属于禁用/未到周期的流。**不能把1/2次拒绝直接解释为1/2条应写日志损失，也不能直接断言无害。** TF可核对应记录的时间/序号覆盖；未写下的拒绝调用身份未必能仅凭TF恢复。

**SX1281：队列入队拒绝再次增长，并在落地后停止增长。** enqueue 普通/优先/tracked API在队列容量拒绝时递增 tx_dropped；RadioFault清队列另一路同时必增rx_error。本轮rx_error、tx_timeout、CRC、SPI/BUSY timeout均0，恢复保留生命周期统计且目标无ClearStats调用，故按当前程序计数语义可归类为入队拒绝。单纯 radio busy 返回不直接增加计数。TelemetryService发送失败不推进下一发送截止时间，后续循环可再次尝试，所以同一个待发内容可贡献多个拒绝。数字不是空口丢包数/不同帧数；普通与控制拒绝比例、无线空口接收完整性仍未证明。AIR/GSP接收无CRC错误只覆盖收到的帧。

**Estimator：约94.3ms最大 start-to-start 单字段在START前再次出现，任务内未观察到更大值。** 源码计算相邻两次 EstimatorTask_TimingBegin 的 monotonic 差，保留启动以来最大值；不是累计耗时、DAP调用窗口、任务间隙总和或处理duration。000044为94308us，000045五次单字段读取均94307us，不能把它说成本次飞行处理耗时。读取到的最大处理duration单字段为1784us，仅为本次观测，非WCET证明。

**本次五份完整 timing 快照的 `timing_coherent` 全为false**（序号在读取窗口中变化）。这不应被静默忽略：上表max_interval/max_duration属于原始aligned uint32单字段观测；不能将其与同一快照其他字段组合成一致时刻的任务执行证明，不能声称完成了“全时段一致timing采样”的无长间隔验收。state前后括号不变也不等于所有动态字段原子快照。约94.3ms发生在首次preSTART读时或以前；没有最大间隔发生时间，不能区分固件启动/准备、调度和live SWD扰动原因。本轮没有halt，故它不是本轮活动期halt造成的。

## 留待 TF 的核对与取回路径

本次结束后不自动 START/复位。需要原始整个 `missions/000045/`，并保留 `missions/000044/` 便于对照：flight.sslog、manifest及全部snapshot/object sidecars，源文件不可修改。运行时878123/885023 B计数不能代替实文件长度/哈希，不能用旧000041或合成样本补实物验收。

- 核对CRC、记录序号、完整结束/final status、START快照/Descriptor与decoder严格身份；检测普通日志损失，核对惯性增量、ESTIMATOR_STEP/KF6的序号与时间连续性。
- 核对landing与允许截止边界，比较000044/45的最后各类记录及必需事件。计数拒绝身份缺失时继续保留NOT_PROVEN；不要把未保存记录自动认作禁用流。
- 用TF中的遥测诊断与主机实收帧按时间对照；发送尝试计数和AIR序号间隙不直接等于空口丢包率。仍可能缺少端到端发收证据。
- 两轮均无GNSS位置/速度更新，不验导航精度。完整栈/ISR/MSP/WCET、关键契约人工验收和历史Qt/Shiboken原生崩溃根因保持既有NOT_PROVEN/FAIL，未由本轮解决。

本次沿用精确包 `D:\python_software\SilverStar\.work\bench08c_f407\KF6_Static_20261008_f045d8c.ssdecoder`，144321 B，SHA256 `46b449244dcfde73baa5faaa795ac496d34f097bd095824959f53210067fafe2`。仍需FLP LogOpenCoordinator将此包与TF Recorded Descriptor严格匹配，主副数据源、全部run及保存/取消/关闭/原子提交/重开为NOT_RUN。

[证据清单](evidence/static_bench_repeat_20261008/manifest.json)记录原始命令、UTC/exit、脚本、live SWD布局/原始字节、串口字节、对照表及全部应用源哈希。BIN读回留在标明的`.work`路径；未复制vendor或清理旧证据。重跑必须重新获得任务范围并用新证据目录，不能直接覆盖运行这些拒绝重复文件的harness。

后续文件验收：用户原位替换 ZIP 后，[实际 TF 与 FLP 离线报告](STATIC_LOG_FILE_ACCEPTANCE_20261008.md)已完成 000044/45 的严格文件与软件持久化验收，原截止时的 NOT_RUN 不改写为当时已通过。拒绝调用身份、空口完整性和启动最大间隔归因仍为 NOT PROVEN；此后没有新增硬件动作。
