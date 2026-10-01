# 固件收口阶段一及 ESKF15 优化基线

基线：`ff3550867dea6d54ac23a65d4906c2316d93fc06`。本批只修已确认的 JY/UART 错误传播和自动质量结果保存，采集 ESKF15 优化前资源；尚未实施 ESKF 优化、数学模型更改或 GUI 收口。源快照、完整日志、配置和产物哈希见 `result.json`。阶段结果不表示已穷尽所有固件缺陷或已经 FIELD READY。

## 修复边界及前后失败

- `IMU_SaveConfig` 检查接收停止结果；停止失败不发送解锁/保存帧。所有退出使用已存在的 `IMU_ReceiveResume`，接收恢复失败覆盖发送结果为明确 RX 错误，避免恢复失败仍返回保存成功。保存成功仍表示发送路径成功，不代表独立 NVM 内容验证；设备没有由此增加的 NVM 回读证明。
- F4 `PlatformUart_ReceiveRestart` 只有 HAL 接收停止成功才启动 DMA；停止/启动失败保持 `rx_active=0`，记录重启失败。公开 RxRestart 和 UART ErrorCallback 共用此路径，不能让错误回调绕过停止结果。
- F4 BaudSet 检查停止和 DeInit，失败时仅执行一次有界恢复。恢复 DeInit/Init 失败则不启动接收；恢复成功回到旧波特率并仍返回原操作错误。每次 HAL 生命周期失败记录 transport error。没有新循环、等待、分配、运行时回调注册或数量断言；临界区保护接收状态及诊断更新，HAL 调用保持在临界区外。
- 保存/读取 Power10 质量记录保留 `POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending`，公开记录提供 `manual_acceptance_pending`。自动文本通过可以保存为 passed，但不等于人工验收。明确 FAIL 标记不能被调用者的 succeeded=True 覆盖，保存/加载均保留 failed。读取旧 passed 记录会补未证明限定，不改写旧 JSON。现有 JSON 字段和版本不变；未实现 GUI 布局、弹窗或导出。

实际 JY 驱动及 F4 backend 故障注入：同一最终用例组在旧源码上 **12 失败 / 29 通过**，修复后 **41 全通过**。包含正常保存、停止失败、解锁/保存发送失败、恢复失败及组合；UART 正常、停止失败、DeInit 失败、新 Init 失败、恢复 DeInit/Init/DMA 失败、第二次停止失败及错误回调。旧失败日志 `before_boundaries_v2.log` 原样保留。早期用例把 deinit_fail 名称误匹配成 init_fail，已修正场景选择器；其初次 11/30 日志仍保留，不用它替代最终 12/29 前置证据。

质量记录负例旧版 **3 失败 / 1 通过**，新版含 CLI 成功但关键 FAIL 的用例。完整受影响合并回归 **188 passed**；其中质量记录与既有项目契约组合 **14 passed**。第一次组合测试因未设置应用 tools 导入路径而 collection error，完整日志保留；正确设置当前进程 PYTHONPATH 后重跑，不安装环境。两处旧集成测试还要求历史成功句，已更新为当前授权的“project text checks passed”并额外要求 NOT_PROVEN 标记；条件编译的允许/拒绝期望没有改变。前置旧句失败为 **2 失败 / 2 通过 / 12 未选中**，与真实固件边界失败分别记录。随后完整 lifecycle 执行 **15 通过 / 1 旧密度期望失败**，原日志保留；该故意违规 fixture 改用仍然硬拒绝的 malloc，并要求同时保留密度提示及 NOT_PROVEN。修正后局部 Power10 集成 **5 通过 / 11 未选中**，不拼成未执行的完整 16 项通过。完整 estimator Release/Debug pytest 矩阵留给后续阶段，不声称本批执行。

## 实际隔离验证

使用 `.work/FirmwareCloseout_ff35508_stage1_v1`，保留之前所有冻结/候选工程。KF6/Ground 来自原配置 SHA256 `b819099f75eaf596f87679adf324d7afbb609c33ece34edd9850ec92b5a98313`；ESKF15 只替换 estimator 插件并经既有配置协调和生成器生成，协议及完整日志开启。两个 F407 生成结果的 JY、F4 UART 文件与 owning payload 原始字节相同。

F407 KF6、F407 ESKF15、F103 Ground 的实际 ARM 14.3.1 编译链接均退出 0；两个 F407 架构、ELF 资源和静态调用栈预算工具均退出 0。KF6 的 `static-analysis` 实际使用 `-fanalyzer` 编译并链接，不是语法检查。每次命令与完整退出结果见 `result.json`；完整 KF6 Host 套件为 **72 执行器 / 4393820 检查 / 0 失败 / 8 编译通过用例 / 16 预期编译失败用例**，见 `kf6_host.log`。Ground 的 size 为 text 21884 / data 12 / bss 14112 B，保留四条 `_close/_lseek/_read/_write` newlib 链接警告，不能称其完全无警告。Ground 分析器、ESKF 专属 Host 和 PureINS 回归未在本批执行，后续矩阵须分别记录。

Power10 文本检查三个目标均退出 0，仍明确关键契约 NOT PROVEN：KF6 108 文件/2608 函数/741 提示，ESKF15 108/2535/720，Ground 15/148/34。增加的函数来自错误处理封装，不为密度清零增加断言。Rule5 保持批准的 F Prime 启发适配；用户后续要求的全目标零候选硬保护及 GUI 反馈属于下一轮待实现要求，本批没有恢复均值/每函数数量硬门槛。

| F407 配置 | Flash 使用/余量 B | 主 SRAM 使用/余量 B | CCM 使用/余量 B |
|---|---|---|---|
| KF6 本批修复后 | 316148 / 208140 | 101280 / 29792 | 55432 / 10104 |
| ESKF15 优化前基线 | 302268 / 222020 | 99880 / 31192 | 64296 / 1240 |

KF6 与上一修复前同配置资源报告相比 Flash +80 B，主 SRAM/CCM 不变。ESKF15 尚未优化，没有优化后数值。其 CCM 只剩 1240 B，首步即使省下 840 B也仅约 2080 B；这不足以自动证明安全裕量或未来配置扩展容量，应继续测量，必要时建议更大 MCU。

## ESKF15 工作区设计

已链接符号证实：`s_work=3980 B`、`s_history=16992 B`、`s_body_history=12288 B`、`s_state=992 B`、`s_window=184 B`。工作区由调用者持有，backend 的 `s_work` 是 CPU-only 私有静态对象；没有必要把全部临时变量移到全局。当前已发现 Initialize/Predict/Reset/SnapshotGet 的生产调用在 EstimatorTask；INSTask 的 BodyInputFill 只复制调用者输入，不使用工作区。后续仍需完成公开入口、ISR、重入和源切换的所有权核查，不能把注释当互斥证明。

建议首步删除一个 15x15 临时矩阵，改为工作区内 15 元素行缓存，**预计 3980→3140 B，省 840 B**：

| 阶段 | 活跃数据 | 可复用条件 |
|---|---|---|
| Initialize | 调用者 nominal/covariance、候选 P、校验矩阵 | 实际 backend 以 F 作为输入协方差；必须先保存到独立候选缓冲再让 F 用于校验，禁止覆盖尚活跃输入，并新增别名回归 |
| 线性化/转移构造 | F、transition、原始 P | F 必须保留到 NoiseAdd，不能与乘法行缓存提前重叠 |
| Congruence | transition、原始 P、行缓存、candidate P | 一行 T*P 完成后算该行输出；原始 P/transition不改，每个点积的 k 顺序不变 |
| NoiseAdd | F、candidate P | 噪声累加完成后 F 失效 |
| Cholesky 校验 | candidate P、校验矩阵 | 可复用已失效的 F；校验失败前不得提交 state |
| Joseph/reset | transition、candidate P、F 中的原 P 副本 | reset 的原 P 副本在 Congruence 完成前保持独立；完成后才能让 F 用于校验 |

行缓存放在实例工作区中，不转移到任务栈，也不与其他任务/ISR共用，不减少历史容量。第一步不改 15 维状态、浮点精度、200Hz 节奏、数学模型、状态或日志/协议格式。优化前后需同编译选项、逐步比较完整 nominal state、225 项 covariance、更新结果/NIS/失效不提交行为，先要求确定性轨迹一致；若出现浮点差异，必须解释原因并明确容差，不能只比较最终位置。后续轨迹需覆盖姿态转动、GNSS 失锁恢复、气压更新、延迟重放、时间戳/队列边界及多实例源切换。

当前静态预算 ESKF Estimator 为配置 4096 B、工具估算 2520 B、余量 1576 B；KF6 对应 4096/3244/852。Flight 路径工具余量 496 B、Device 432 B。完整 ELF 哈希、符号与预算链在 `eskf15_baseline.json`、`*_nm_sizes.log`、`*_stack_budget.json`。这些是工具算法和已解析路径范围的估算，不是实测 HWM；main/MSP/ISR 嵌套、所有库/回调语义、STM32 WCET和飞行硬件资格仍需单独证明。

性能基线尚未测量。后续采用同一编译器/优化参数和固定输入序列，分别测预测、普通更新、延迟 replay 的多次主机执行时间分布，并保存输入、逐步结果及运行条件；主机时间只用于同环境前后比较。ARM 编译不能替代 STM32 周期测量；DWT 周期、实际调度/中断干扰和栈 HWM 留给用户硬件验证，不把主机速度当严格 WCET。

## 未完成与下一轮已授权需求

本阶段未实施 ESKF15 优化及前后导航轨迹比较；未完成全部历史 171 项的安全语义亲审、优化后 KF6/ESKF15/PureINS/Ground 全矩阵或硬件证据。不得宣称已经解决所有固件问题。第三方受控例外仍保留，未证明项目项不得在聚合时变为 FIELD READY。

已记录用户 08:20、08:29 授权，当前不实施 GUI：下一轮 PoT 自动检查与人工/硬件资格分开显示；硬规则或全目标零有效候选报错、仅审查提示显示自动通过并告知提示；增加审查清单导出、配置/源码标识和取消/空清单/Unicode 路径测试。首发隐藏磁力计选择/校准及持久化入口；GSHC 去掉相关校准 UI且保留其他修复，FLP 最小标题修正，双矢量固定重力+已知方向并保留外部姿态。多传感器按配置顺序冷/待机备份，不维护多套导航状态，需核查现有硬件初始化、稳定/切换超时和防反复切换，复用机制接 baro GUI，不新增插件。FCCG 对外 SCG 改名需要旧工程/schema/命令/导入兼容审查，不盲目替换历史记录；下一轮制作“已实现但仍有问题、暂不发布内容”及恢复条件。

未执行 push/tag/release、刷机/START/执行器、打包或网络/远程软件操作。当前阶段检查点完成后交父任务协调继续。
