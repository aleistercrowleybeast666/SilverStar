# 2026-10-08 授权来源复验与 mission 000051 静态运行

唯一待定来源已获用户“允许”，owning checker 仅新增 `APP/Src/estimator_task.c` 的精确规范化哈希 `98df5cb8cefc0a2e5632bf51fd73319cef033d5a7bb511390c246dafb5b64610`（V11）。本轮所有原软件门禁通过，随后已完成 Flight 烧录、verify、精确读回及一次生产 GSHC 静态生命周期。关闭后未再观察到此前已定位的健康发布拒绝。**整体关键契约审查仍 NOT_PROVEN，TF 文件与全事件清单验收仍 NOT_RUN**，不称完整飞行资格或零丢失。

基线为 `6bfd678cbde9a7b10ef8f8b03be7c9607fc88077`，分支 `fix/nightly-user-ready-20261003`。该提交拥有[四行产品修复、修复前失败及未授权时原样栈 FAIL](LOGGER_HEALTH_FINALIZATION_20261008.md)；这些历史结果保留。本轮实际代码修改只在 owning `Tools/check_task_stacks.py` 增加一个精确记录及其查询入口。AST 比较证明其他函数与所有既有记录不变；没有修改阈值、unknown fail、一般规则或额外授权来源。

## 软件复验与身份

独立新工程位于 `.work/finalized_health_20261008_v2/project/Flight_Controller`。配置、硬件、数学、队列、栈、AIR/CMD/ACK 和 ACK 调度均保持原值。155 个编译输入没有额外未知来源。新 ELF 的只读调用图比较再次确认：只新增 Estimator→现有 finalization getter→IRQ enter/exit，间接调用位置与原已审阅 bench 相同。所有日志、配置、命令、工具版本、精确源码与授权记录见[证据清单](evidence/logger_health_retest_20261008/manifest.json)。

| 本轮实际执行 | 结果 |
| --- | --- |
| fresh generation / architecture/source graph | PASS |
| 原 generated `power10-check` | 文本 PASS，exit 0；6329 checks、111 一方 C、2761 functions、815 非阻断建议；**critical-contract review NOT_PROVEN** |
| ARM Release 编译/链接、artifact、memory | PASS，exit 0 |
| 原 generated `stack-report` / exact source binding | PASS，exit 0；没有绕过绑定；Estimator 4096/3252/844 B，Logger 3072/1768/1304 B（configured/estimate/margin，仅该报告范围） |
| 实际 ARM `-fanalyzer` 编译对象并链接 | PASS，exit 0，不是 syntax-only |
| 完整 generated Host，包括存储完整性 | PASS，exit 0；80 executables、4446469 checks、0 failures、11 compile-pass、18 expected compile failures、8 not-applicable；381.31 s |
| 新增 11 场景、既有 23 场景与拒绝未知来源测试 | pytest 5/5 PASS，exit 0，12.45 s；一个 `cache_dir` 插件配置警告保留 |

以上来自这一个新生成工程的完整执行，没有把此前多个选择性 PASS 拼成未执行的整套结果。单一来源授权不等于原 Power of Ten 全固件合规、NASA 认证或完整栈/WCET/ISR 的正式证明。RAM 余量和单函数 `.su` 不替代报告的实际覆盖范围。

表内 Logger 数值是本次生成配置的静态门禁估算，不扩展既有 RET6 Logger 栈结论到其他配置或实物型号。

| 实际产物 | 身份 |
| --- | --- |
| BIN，331052 B | `cf1a359c9212354b63b4af8b83f0db4008897eb333d35d220d8eec4a2f33da4c` |
| ELF，fresh v2 路径 | `bb57ae0d8d04c53048bf19d44d54b97ec4fcebec11875c8a4bfc76f963a077f4` |
| 精确 decoder | `46b449244dcfde73baa5faaa795ac496d34f097bd095824959f53210067fafe2` |

V2 BIN 与先前已复验的四行修复 BIN 字节一致；checker 来源证明不改变固件。ELF 包含新构建路径的调试信息，使用 V2 哈希绑定本次 RAM 字段。显示标签 `KF6_Static_20261008_f045d8c` 只保持原配置/decoder 身份，不能作为本次源码提交。最终提交源码由证据的规范化哈希与提交后校验对应到编译输入。

## Flight 写入与单次运行

用户确认执行器断开、TF 插入、+Y 静止。指定 CMSIS-DAP serial `132765403520`，实际 chip ID `0x10076413`、512 KiB Flash、UID words `0x00470051 / 0x42325004 / 0x20313339`。写入前核心运行、旧已知固件 PREFLIGHT，完整 Flash 读回 SHA-256 与此前恢复的 `109a4eee42d2ba9189a1fef26559ec5dfcbc0ae7cda54f7dc6a76d6bdd674fba` 一致。ID/容量/UID/固件对应本次设备，不从芯片 ID 单独推断封装或引脚资格。

09:21:26.645–09:21:46.608 UTC 的 Flight `program ... verify reset` 与精确应用读回 PASS；读回 SHA 为上述新 BIN，sector 7 与写入前一致。仅写应用所在扇区，未 mass erase/options，Ground 未刷。编程期在已核对的 PREFLIGHT 暂停/重启；活动期主基线没有 halt、断点或 DAP 连接。

09:25:44.697–09:26:14.918 UTC，运行真实 GSHC `MainWindow / Controller / SerialWorker / ProtocolWorker`，Qt API 驱动真实窗口，不声称鼠标 GUI 输入。COM3 校验为 VID:PID `1a86:7523`、location `1-1`、230400 baud。一次 CONNECT、所选 +Y OneFace RAM 校准、ALIGN、UNLOCK 和**一次 public START**；真实 READY 门控及命令缓存/重试保留。

OneFace 当前实现只更新 `SystemCalibration` 的 RAM `s_status` 偏置、标度、代次与 READY，没有 TF 校准对象写入路径。初始脚本额外禁用了 CAL_START，属于过严解释；核对源码后只恢复原静态流程的 RAM OneFace。新 mission 日志/快照正常记录本次 RAM 校准身份，不修改已有 TF 校准对象。初始 snapshot_ready=0 的零代次/零 mag hash 不是已提交 TF 身份，不能与最终字段比较后声称 TF 校准被改写。完整物理介质校准对象的前后字节等价本轮未取卡，仍 NOT_PROVEN。

| 生产 GSHC 实测 | 记录 |
| --- | --- |
| public START / wire START | 1 / 2（同一事务重试） |
| 成功权威 | 首个 FLIGHT_STATE，先于晚 ACK；没有 START failure/timeout |
| 首 TX→ACK RX / ACK 处理延迟 | 1541.2826 ms / 0.1468 ms |
| MISSION_START / DEPLOY / LANDING | 3 / 10001 / 14013 ms |
| 采集原始字节 | 5177 B；151 GSP / 115 AIR；CRC、parse、resync、尾部 buffer 均 0；离线重解析与日志帧逐项一致 |
| FLIGHT_STATE | 53 帧；末次 GSHC 估计丢包 **10/63，15.873%**，原样显示和保存 |
| 本次 GSHC 结束 | serial/protocol closed=true、logger error 空、无额外 START |

解析器零错误不是零无线丢包。保留可见的非零估计，不据此声称导航日志无丢样或确定无线丢包根因；实际 TF 序列与样本损失待取卡。用户接受晚 ACK 作为非阻断观察不等于这些未知项 PASS。ACK 公平性、超时与 PHY 未改，也不将单次较早到达 ACK 归功于本修复。

## 关闭后的边界证据

新 ELF 离线推导 43 个地址/大小；只在 START 前和运行结束后非暂停读取。09:27:04.509–09:27:04.712 UTC 的结束读数绑定同 UID 与新 ELF，核心保持运行，所有 OpenOCD 服务关闭。

| 结束读数 | 实际值 |
| --- | --- |
| lifecycle / logger admission / finalization | LANDED=6 / accepting=0 / FINALIZED=3 |
| logger session | active=0、finalized=1、snapshot_ready=1 |
| accepted / dequeued / normal / estimator queue | 10116 / 10116 / 0 / 0 |
| state reject / capacity reject / overflow | 0 / 0 / 0 |
| append / flush / serialize / open / close failure | 全部 0；final-status-write-failed=0、io_fault=0 |
| sink | session_active=0、healthy=1、bytes_written=878815；运行期诊断，尚非取卡字节审计 |
| estimator / assertion | mission_running 仍 1；health_flags=130，LOG_EVENT_FAILED bit 8 未置；assert fault 72 B 全 0 |
| 活动期融合依据 | 气压组 4 has_success=1、stored state ACCEPTED；成功时间与最后导航发布时间接近，nav update_sequence=1401 |

其他四个 GNSS 融合组在这次静止无有效 GNSS 环境没有成功融合，不声称所有组健康。结束读数中气压最后成功融合距仍运行的 monotonic task time 为 57,925,239 μs；这是离线按捕获字段计算的年龄，不是调用 target getter。原 GroupGet 的 2 s/10 s 时效规则保留，focused Host 也验证真实超时仍可查询；不能把源对象中最后存储的 ACCEPTED 当作此刻派生健康状态。

健康发布者的 stored previous-state 气压组仍为 ACCEPTED，未消费关闭后时效变化。结合确切生成代码的 FINALIZED guard、 unchanged Host 错误契约、仍为 1 的 mission_running、长期已关闭会话及无拒绝/失败位，支持本次已确认边界路径不再错误发布。没有以“计数 0”单独宣称所有同类发布者的根因已解决。Device GNSS/RF 等潜在晚发布者仍保持原代码；本次无另一个被证实的同因问题。**TF 中 event 47 全清单与文件尾部完整性仍 NOT_RUN**。

## 真实任务目录、剩余验收与复现

START 前与结束后均读得 mission ID **51**，真实 sink path 同为 **`0:/missions/000051/flight.sslog`**，末次 logger snapshot_mission_id 也为 51。用户下一步取回 TF 时，请保留完整 `/missions/000051/`，包括 `flight.sslog`、manifest、快照/最终状态对象，不只截取日志尾部。匹配 decoder 已保存在[本轮附件](evidence/logger_health_retest_20261008/candidate.ssdecoder)。读取不可变副本并先哈希，使用精确 decoder / Descriptor 经 FLP `LogOpenCoordinator` 打开，检查全部 run、主副源、普通和导航缺口、文件尾部与快照。本轮不会用 Host 或 RAM healthy 替代这个验收。

此前 TEST_5、current、current_diag 的实际任务号仍 **NOT_PROVEN**；不要把 000051 倒推出前三次编号。它们的 UTC 窗口与 TEST_5 intentional incomplete 标记继续见[前轮记录](LOGGER_HEALTH_FINALIZATION_20261008.md#前轮-mission-id-与故意未完成记录)，取 TF 后才映射。

复现软件检查：把附件 `generate_initial.py`（实际执行的 runner）、`run_gates.py` 与 `run_pytest.py` 复制到一个全新 `.work/<新版本>/`，在仓库根用 `.venv/Scripts/python.exe` 依次执行；配置来源仍指向保留 `.work/bench08c_f407/SilverStar.ssproject`，附件保存同字节 reference config。不得覆盖 V1/V2 或已有用户工程。原 gate 的完整 argv/cwd/UTC/exit 分别在 `*_result.json`；硬件命令在 `hardware_*/command.json`，**硬件脚本不是无需再次核对设备/授权的通用重跑建议**。

所有失败/记录修正原样保留：离线 GDB 初次类型名错误、该 Windows GDB 不支持 UTF-8 charset 设置（最终字段查询成功但 CP1252 转换警告保留）；预读 OpenOCD 实际 exit 0 后十六进制解析器失败，保留 initial script/raw log，离线修正记录且未重复连板；初始 snapshot_ready 断言过早，没有发送 START；两个 PowerShell/Python 引号构造错误未触发硬件，改为保存脚本。复制 V1 runner 的两个旧元数据常量已明确更正并保留原记录，未更改实际生成/门禁结果。

本轮结束板上为新 BIN `cf1a359c…33da4c`，未恢复旧版，核心运行、LANDED，连接关闭；不自动重新 START、关机或清理用户数据。三个 `work_*_20261006` 文件保留原哈希。文档/四算法与四档先前闭合结果未重新伪称完整实机验证；[阅读顺序与算法实现定位](NIGHTLY_SOFTWARE_CLOSEOUT_20261008.md)保持，H7、F407 ESKF15、F103/NRF、无 GNSS 漂移和 20% RAM 建议等边界不变。
