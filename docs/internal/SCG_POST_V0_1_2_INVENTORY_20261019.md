# 正式 v0.1.2 之后的 SCG 改进清单

2026-10-19；owner：Codex 只读清点。用途：开发进展与验收索引，非发布说明或合规结论。本次只新增本文件，未运行构建/测试、打开 GUI、占用串口/SWD、操作硬件、清理、切换分支或推送。

## 基线与读法

- 正式 `v0.1.2` 的 peeled commit 为 `c31c13cc0686a56a3184d4f207fd3816c5d39696`；annotated tag 对象为 `942f20ef64df3cb1aa65be7349361c409418aa0f`。两者不可混用。
- 审查时分支 `feature/usb-transport-0.1.3-20261013`，HEAD `7896c1d09a7f9138c41cdac35beef38347d94b78`；当前还有大量未提交实现及未跟踪文件。下表明确区分**提交**和**工作区**，HEAD 不代表完整受测源码快照。
- 分类：**A 已接入**＝有实际产品入口/调用链及相应软件证据；**B 软件验证**＝实现或生成物已有定向验证，完整集成或硬件资格仍欠缺；**E 实验**＝默认未选/关闭、需开发者显式启用；**R 研究/计划**＝隔离原型或设计，不能选作固件能力。同一项可以同时为 A/B，表示软件入口可用而物理能力未验收。
- 以下结果是**读取已有记录**，不是本轮重跑。每份报告的源码、配置、失败、跳过和日期边界继续有效；不能把若干旧 PASS 合成当前脏工作区全套 PASS。
- F103 Ground、F407 Flight、C071 相关基础生成/导入及 10 月 9–10 日的首批 native USB 工作已在 v0.1.2 基线内；不能把整个现有多 MCU/GUI 体系重新算成发布后新增。

## 配置、GUI 与工程生成

| 改进 | 状态/归属 | 当前入口、依据与边界 |
|---|---|---|
| 常用导航参数直接可见，高级项保留折叠状态 | A；提交 `08e76ec5` | SCG Navigation Configuration → Algorithm Parameters；[说明](../public/SCG/NAVIGATION_PARAMETER_VISIBILITY_20261015.md)。SCG 166 项、FLP 148 项为各自当时的定向范围；不改变算法数值。 |
| NIS 概率输入、残差自由度提示、独立软/硬门开关 | A/B；`57b78fbb` | [NIS 指南](../public/SCG/NIS_PROBABILITY_0_1_3.md)、[证据](../evidence/nis_probability_20261014/REPORT.md)。格式 18 显式保存概率；生成时转 finite float32 阈值，未编辑旧数值保持精确。GNSS 水平联合 df2、垂直/气压 df1；不是状态维数 6/15，SF6 无 NIS。硬件统计一致性、ESKF 软加权前后 NIS 阶段差异未由界面验收消除。 |
| 固定结构原点、逐 IMU/GNSS 安装 XYZ、未知/实测零区分 | A 配置/B 物理能力；工作区 | [安装配置说明](../public/SCG/SENSOR_INSTALLATION_0_1_3_20261018.md)；源码 [sensor_installation.py](../../apps/SCG/src/silverstar_fccg/project/sensor_installation.py)、[编辑器](../../apps/SCG/src/silverstar_fccg/ui/sensor_installation_editor.py)。可编辑、保存/重开、生成 JSON/宏；格式 20 按需启用，实例 ID 保持稳定。**`PROJECT_SENSOR_INSTALLATION_RUNTIME_APPLIED=0`**；新位置不参与运行补偿。 |
| 项目 JSON Schema 与真实解析器对齐到格式 14–20 | A；工作区 | [Schema](../../apps/SCG/schemas/project.schema.json)、[最终 118 项证据](../../.work/sensor-installation-0.1.3-20261018/schema-closeout-02/verification-summary.json)。实际 Draft202012 验证、生产打开/保存、生成和两文件源码导出通过；生产权威仍是 `ProjectModel_Parse`，没有新增运行时 jsonschema 依赖。先前 14/15 Schema 漏列及 152/159 源图旧断言已由后续专项闭合，旧失败保留。 |
| 更新算法身份与用户拥有源码之间的再生成校验 | A；`57b78fbb`、`887f7208` 等 | [assembler.py](../../apps/SCG/src/silverstar_fccg/generator/assembler.py)、[fusion_timing.py](../../apps/SCG/src/silverstar_fccg/generator/fusion_timing.py)、[kf6_identity.py](../../apps/SCG/src/silverstar_fccg/generator/kf6_identity.py)。旧 payload 不能凭新 metadata 冒充新 NIS/时序语义；不证明身份就拒绝。正常再生成继续保留用户拥有的组件源码；native 实验导出使用分离的新目录。 |

安装 XYZ 与旧 ESKF15 `lever_arm_body_*_m` 独立。旧全局杆臂已有位置/速度观测用途，但多个 GNSS 仍共用该值；本批未按实例迁移，也未新增多 IMU 动态测量点换算。KF6/SF6/Pure INS 不消费新安装坐标。目标“上电仅健康检查及静止陀螺零偏”仍待实施；当前 OneFace 还会计算单面加速度偏置，不能把目标流程写成已实现。

## ssdiag、ELF 与可定位诊断

| 改进 | 状态/归属 | 当前入口、依据与边界 |
|---|---|---|
| SCG 生成诊断描述，成功构建后绑定实际 ELF；统一安全 ELF/DWARF 解析 | A/B；`355b3df2` | [目标/ELF 操作说明](../public/GSHC/TARGET_ELF_0_1_3.md)、[原始证据](../evidence/target_elf_20261014/REPORT.md)；共享实现 `apps/SCG/src/silverstar_diagnostics/`。按 Flash **LMA** 比较完整非空 PT_LOAD，包含 `.data` 初值；未知目标/坏加载映像/不匹配不能授权 RAM 诊断。401 项是 F1/F4/C0 元数据，非逐板通过。 |
| Flight/Ground 项目根入口、明确 pending/unbound/ready 状态及实际输出收据 | B，产品调用链已接入；工作区 | [swd_diagnostics.py](../../apps/SCG/src/silverstar_fccg/generator/swd_diagnostics.py)、[project_descriptor.py](../../apps/SCG/src/silverstar_diagnostics/project_descriptor.py)、[runner.py](../../apps/SCG/src/silverstar_fccg/build/runner.py)、[专项测试](../../apps/SCG/tests/test_swd_project_descriptor.py)。当前输出 `Flight.ssdiag`/`Ground.ssdiag`；构建前撤销旧绑定，成功后只接受唯一精确 ELF 输出，不猜目录。描述是主机数据，不把 Python binder 塞进固件源图/Make 执行链。当前整合的全量验收由正在进行的 GSHC 任务负责，本清点未复跑。 |
| 显式 ELF+HEX 编程映像身份，限定 erased alignment gap 的解释 | B；工作区 | [image.py](../../apps/SCG/src/silverstar_diagnostics/image.py)；[已有独立候选报告](../../.work/dev013_gshc_image_contract01/REPORT_CN.md)记录 382 项及特定 ELF/HEX 的 331012 字节只读实机匹配。它是显式 v2 身份策略；v1 仍严格，不能自动忽略任意间隙。旧候选报告的结果不自动覆盖当前根整合版本。 |
| 有限 RAM 标量 watch、局部 API/CLI 摘要与完整身份失效 | A/B；`176733d7` | [证据](../evidence/swd_watch_20261015/report.md)、[watch.py](../../apps/SCG/src/silverstar_diagnostics/watch.py)。目录由 ELF 类型/符号推导，拒绝指针、数组、局部等不支持项；有限项数/速率/字节数。连接/镜像身份改变即清空，不把 host receive age 当 MCU sample age。旧报告中 GSHC 全套失败是历史范围，当前 GSHC 修复不能由此推断，本报告也不另占探针验证。 |

## 维护 0.1、TF 日志与安装标定

| 改进 | 状态/归属 | 当前入口、依据与边界 |
|---|---|---|
| 维护 0.1 兼容 0.0，分页只读 DIAG | A/B；`258aaa6e` 及工作区后续合入 | [完整协议说明](../../apps/SCG/plugins/builtin/silverstar_protocol_maintenance_serial_0_0/docs/MAINTENANCE_PROTOCOL_0_1.md)、[证据入口](../../apps/SCG/docs/evidence/maintenance_0_1_20261013/README.md)。7 个实际 RAM reader、目录上限 16、行上限 511；无任意地址读写。维护版本、诊断 schema1、文件服务1、SSLOG0.0 独立，不能从 0.1 推断所有能力。 |
| Logger 独占 TF 文件服务与维护 START 排斥 | A/B；`cb944b7c`、`a9b73a5b`、`e1c40c5b` | [文件服务证据](../../apps/SCG/docs/evidence/log_file_service_20261013/README.md)、[UART 安全检查点](../public/SCG/UART_MAINTENANCE_20261013.md)。ENTER 原子排斥 START/config，drain/flush/close/final-status 全成功才 Ready；LIST/META/READ/POLL/CANCEL 有界 mailbox，64 B READ。维护锁 boot-latched，完成/断线不解除；不是实现了会话 EXIT。 |
| 整行 UART 背压、异步回复容量检查、bootstrap 关闭与 TF 拷贝校验 | A/B；工作区 | `system_console.c`、`system_log_file.c`、`logger_task.c` 与 UART owning payload；[完整协议第 9/11/13 节](../../apps/SCG/plugins/builtin/silverstar_protocol_maintenance_serial_0_0/docs/MAINTENANCE_PROTOCOL_0_1.md)。整行入队不是物理送达。主机块 CRC/整文件 CRC/META 再核对/fsync/SHA/readback/原子发布；当前 unknown device/boot identity 禁止续传，重新下载从零开始，DELETE 明确拒绝。 |
| 显式 MAG 设备/采集配置准入、已有 MAG CAL 命令复用 | A/B；工作区 | [release_policy.py](../../apps/SCG/src/silverstar_fccg/project/release_policy.py)、[MAG 专项测试](../../apps/SCG/tests/test_magnetometer_entry_generation.py)、协议第 6 节。去掉“所有显式磁设备延期”的总禁令，仍保留 magnetic alignment/旧 source override 等独立门禁；可收数/拟合并不赋予磁航向或 READY。 |
| TF-only 磁内参事务、候选/已提交分离、失败回滚及 provenance | A/B；工作区 | [TF 生命周期](TF_INSTALLATION_CALIBRATION_20261018.md)、[v21 输入审查](TF_STACK_INPUT_REVIEW_20261018.md)。84 B 旧 APPLY 包兼容；TF SSIC kind1 为 116 B、SSOB 双槽代次/CRC/readback，SAVE accepted 不代表 durable；失败恢复已提交值，重复保存幂等。启动只加载匹配 endpoint/config/driver/model 的对象。无 SPI Flash；同型号换芯片无法自动识别。 |
| 安装会话的 PC 求解、完整身份/时间/内参冻结、两槽采集和候选 CAS 存储 | E/B；工作区 | [插件入口](../../apps/SCG/plugins/builtin/silverstar_installation_capture/README.md)、[软件集成](INSTALLATION_CAPTURE_SOFTWARE_INTEGRATION_20261019.md)、[最新 v9](INSTALLATION_RUNTIME_LIFECYCLE_REVIEW_20261019.md)。默认未选，真实 `BEGIN` 返回 `SOURCE_QUALIFICATION`，wire UPLOAD/APPLY/SAVE 关闭。后续真实 C+FatFs 候选/head 事务已落地，覆盖旧集成报告“分块 TF 尚未实现”的旧状态，但**不等于 wire 保存或运行时应用开放**。 |
| 先磁旋转、后六面并复用原始数据的安装流程 | R，部分 E/B 软件链 | [设计](INSTALLATION_CALIBRATION_0_1_3_DESIGN_20261018.md)、[流式评估](INSTALLATION_CAPTURE_STREAMING_EVALUATION_20261019.md)、[离线证明](INSTALLATION_CAPTURE_OFFLINE_PROOF_20261019.md)。沿用维护口，不把控制命令塞进 SSLOG；未知磁倾角约束、激励/多解检查和独立留出验证，必要补斜姿态。六面不称完整陀螺尺度标定。真源测量时间/每 native 帧资格、全入口 lease、取消端到端时限仍欠缺，不能用合成 proof 解锁。 |

已有硬件记录须单列：精确 **R04** 曾完成两份 TF 日志共 9640 B 下载及校验；精确 **TF 候选 ELF `7056eac7…`** 于 10 月 18 日获当时授权烧录、349708 B 加载区回读匹配及启动只读观察。前者不覆盖当前导航/USB 生成物，后者不证明 MAG 实际拟合精度或安装采集。最新 v9 ELF `3c307ae0…` 是离线验证输出，不能冒称已经上板。本次没有复用这些授权做任何硬件操作。

## 传感器、对准、算法与时序

| 改进 | 状态/归属 | 当前依据与边界 |
|---|---|---|
| JY901B/S 显式磁输出、名义比例、过期与无依据温度位修复 | B；工作区 | [精确驱动报告](../../.work/dev013_jy901_mag_20261018/REPORT.md)、[MAGNETIC_OUTPUT](../../apps/SCG/plugins/builtin/silverstar_device_imu_jy901b/docs/MAGNETIC_OUTPUT.md)。73 项、B/S 实际 ARM/analyzer/Host 定向记录；B/S 默认磁关闭，显式 capture 开启。时间仍为接收/解析代理；模块内部校正顺序、修订比例、独立磁测量率及同步均未资格确认。其当时 artifact/stack 失败保留，后续特定 F407 TF 候选闭环不代表所有 B/S 配置通过。 |
| 磁记录按实际 Descriptor 路由而非固定别名 | A/B；工作区 | [结果记录](../../.work/dev013_mag_logging_20261018_v1/results.json)、[SCG 测试](../../apps/SCG/tests/test_magnetometer_recording.py)。显式 JY/LIS3MDL/MMC5983MA 记录路径及 FLP 路由专项通过；无新 SSLOG 布局。广域 SCG 回归仍有历史/环境失败记录，不写成全绿。历史日志仅存磁代次/hash，不足以重建完整磁系数；完整不可变 mission companion 仍待实现。 |
| 加权方向对准改为固定上界 Jacobi SVD | B；工作区 | [owning README](../../apps/SCG/plugins/builtin/silverstar_algorithm_alignment_common/README.md)、[2890 oracle 与生成验证](../../.work/0.1.3-initial-alignment-20261017/validation_summary.json)。最多 6 观察、16 sweeps，正确使用方向权重、有限/秩/反射/不收敛检查；保持 ACCEPTED/READY 区分。它求解已有方向对应问题，不能拿来把重力和磁场视为同向量的磁安装 Wahba。旧资源失败后来仅在特定 TF 集成候选重验。 |
| INS 复用本次中间量、ESKF reset 全协方差特化 | A/B；`5af1efa1` | [21 项差分、实际目标编译及历史失败](../evidence/navigation_performance_20261015/REPORT.md)。保留完整 15×15 交叉项及异常回退；相同输入有限输出逐字节比较。Host 时间不当 MCU 提速/WCET；当时栈失败由后续输入审查定向闭合，不删除原失败。 |
| 完整协方差 congruence scaling 工具 | B；`68a5205e` | [独立测试](../../apps/SCG/tests/test_eskf15_covariance_scale.py)、[证据目录](../evidence/eskf15_covariance_scale_20261015/)。事务性完整 P 变换；独立工具的存在不代表主动 GNSS recovery 已使用。 |
| mode0 当前态、mode1 原延迟回放；源/接收/应用/评价 epoch 分离 | A/B；`cb53daf3`、`887f7208` | [时序闭环](../evidence/algorithm_timing_closeout_20261015/README.md)、[后续六配置验收](../public/SCG/NAVIGATION_DEFAULT_OFF_ACCEPTANCE_20261016.md)。mode1 仍默认；mode0 无数值 history，保留年龄/顺序/水位和故障准入。精确 decoder/语义不匹配拒绝，旧记录不回填新语义。早期“只有声明未实现”文档已被后续实现覆盖。 |
| mode2 延迟主滤波 + 独立完整输出状态/P 传播 | E/B；`615d5052`、`21562359`、`cd3fd065` | [开发证据](../evidence/fusion_horizon_development_20261016/REPORT.md)、[后续验收](../public/SCG/NAVIGATION_DEFAULT_OFF_ACCEPTANCE_20261016.md)。实际有 KF/ESKF owning C、SCG/FLP 实验选项及精确 Recorded/What-if CPU 回放，非仅规划；早期栈输入失败后来有 v19/v20 精确闭环。无板级时序/精度证明，不能称默认生产方案。 |
| 原子 GNSS receipt、source handoff 新鲜度屏障和坏内部状态撤销 READY | A/B；`cd3fd065` | `system_gnss_receipt.c`、`system_source_selector.c` 及[六配置报告](../public/SCG/NAVIGATION_DEFAULT_OFF_ACCEPTANCE_20261016.md)。外部坏包保留普通错误，内部所有权不一致进入既有安全失败；不改 mission origin。 |
| GNSS 重捕获配置/qualifier/kernel/replay/horizon 准备件 | E/R；`cd3fd065` | ESKF0.4.0 的 29 参数、104 B 配置身份与 OFF 状态严格记录；**active recovery 被生成验证拒绝**，完整 1/5/30/120 s 失锁矩阵及 backend 激活未完成，不能列成已恢复 GNSS 能力。 |
| ESKF20、InEKF9/15/20 数学参考及独立审计 | R；工作区隔离 Python | [实验 README](../../apps/SCG/experiments/navigation_0_1_3/README.md)、[模型](../../apps/SCG/experiments/navigation_0_1_3/ESKF20_MODEL.md)。有数学/全 P/Jacobian/对称性等离线验证；**无 plugin/算法 ID/源图/固件选择或生成入口**，没有 C backend、完整 ARM/资源/硬件证明。旧 10 月 15 日“20 状态未定义”的计划已由隔离模型补充，固件准入状态未变。 |

## 多 MCU、USB、无线电及资源审计

| 改进 | 状态/归属 | 当前依据与边界 |
|---|---|---|
| 能力检查型 classic FS CDC kit，独立 inspect/derive/build/refresh 工作流 | E/B；`2b6c4892`、`54b9267d` 及工作区后续修复 | [workflow](../../apps/SCG/docs/USB_NATIVE_WORKFLOW_20261015.md)、[最新兼容审计](../../apps/SCG/docs/USB_CDC_COMPATIBILITY_20261015.md)。完整原生 CubeMX 工程是输入，检查实际 ABI/生命周期/内存后派生新输出；后台有界 build 使用直接 argv，不执行输入工程脚本。原生启动/IRQ/PCD/存储所有权不能靠模板猜测。 |
| F103 PMA、F407 OTG FIFO 与 EP0/退役状态的具体检查 | E/B；工作区 | 最新兼容审计保留 BTABLE/失败初始化/Class 空指针等红绿用例、实际 ARM/analyzer 增量链接及 IRQ/vector 检查。F407 后续完整 fixture 用生成的 128/64/64/32 FIFO 块，**旧 original input 仍缺 notification TX2**；不能沿用旧 workflow 文字把后续 fixture 说成不存在，也不能把 fixture 说成用户原项目已修复。 |
| USB 门禁与 C071 支持边界明确化 | E，尚未接受 | 最新原样 Power10 仍 **exit1：F103 7 组/F407 10 组**；包括实证 F103 `wLength=65535` 转交 512 B 类缓冲等 vendor/native 合同缺口。零 heap 链接不豁免 `_sbrk` 源策略。C071 官方 USBX/ThreadX 示例存在，但用户 PCD-only 工程不完整；CubeMX 生成请求登录/下载并 KO，未获 complete build。USBX/HS/复合/多实例/DMA-cache/未审 ABI 不自动准入。**不能称所有 STM32 支持 USB。** |
| SX1278/E32-400M20S 固定配置驱动实验 | R/B；工作区 | [独立实验说明](../public/SCG/SX1278_EXPERIMENTAL_20261015.md)、[payload](../../apps/SCG/plugins/builtin/silverstar_device_telemetry_sx1278/)。有模拟寄存器/故障、独立 ARM/analyzer ABI fixture；不是完整 Flight/Ground 固件。正常生成集成、AIR/记录身份、异步 Stop 调用方清理、整套门禁及 RF 硬件仍待办。目录出现不表示正式支持或已替换 E28。 |
| CPU-only queue/history 放置与链接丢弃证据 | A/B；`89427d9a`、`887f7208` | [内存闭环](../evidence/algorithm_memory_closeout_20261015/README.md)。2560 B CPU 输入队列进 startup-cleared CCM；不用 history 须由 map 证明准确 section/object/size 已丢弃，不能静默忽略缺符号。队列/预算不扩大；历史 KF legacy O0 Flash 超 1088 B 的失败仍有效于该配置。 |
| 栈输入、依赖闭包、混配拒绝、源图和历史夹具可复验 | A/B；已提交 v18–v20，工作区 v21–v23 | [v21](TF_STACK_INPUT_REVIEW_20261018.md)、[v22](INSTALLATION_STACK_INPUT_REVIEW_20261019.md)、[v23](INSTALLATION_RUNTIME_LIFECYCLE_REVIEW_20261019.md)。登记精确源+头+compiler-input tuple；改源、改头、改依赖或混合已知版本仍拒绝，无自动学习。历史 F103 RET6/RFT6 由永久小 fixture 重建，后续 116/116 定向通过，不借丢失 `.work` 假称跳过。新生成 F103 Flight 仍不因历史 fixture 自动准入。 |
| 安装候选晚到取消/超时、HAL 固定回调和任务/MSP 路径审查 | B/E；工作区最新 v9 | [最新报告](INSTALLATION_RUNTIME_LIFECYCLE_REVIEW_20261019.md)。实际 Commit 成功后必须报告 CandidateOnly/真实代次，不能以晚 cancel 覆盖；真实 C+FatFs 红绿、17 存储回归、32 C/UART pytest、91 输入/生成测试、8 HAL 完整函数体/12 Host 情形及新 ELF 门禁分别记录。不是全 HAL 时序验证。 |

最新 v9 的特定 F407 配置：主 SRAM **102292/102400 B，余 108 B**；CCM **64896/65536 B，余 640 B**；Flash load sections **391592 B**；任务栈未扩大。条件化 boot/MSP 模型为 **844/1024 B**，余 180 B，见 [MSP 审查](INSTALLATION_BOOT_MSP_REVIEW_20261019.md)。这些数值不等于任意配置的安全余量。较早 6208 B 采集模型失败保留；两槽状态 1960 B 加协调/对齐形成 1992 B CCM 的实际集成，没有放宽原预算。

Power10 使用既定 F Prime-inspired 项目适配；>10 行零运行候选是非阻断建议，关键合同审查仍明确 **NOT PROVEN**。全程序递归/库/间接调用、动态帧、异常中断交错、HAL 停 tick/卡住 EN、真实最小 SP/HWM、WCET、TF/FAT 断电与导航/飞行资格均不能从工具 exit0 推断。后续窄范围修复没有改写早期失败、删源、扩例外或制造断言。

## 当前验收入口与尚缺项

1. **配置/UI 离线入口**：仓库根 `.venv/Scripts/python.exe SCG.py`；查看常用/NIS/时序选项与 Flight Devices 安装输入。启动不是构建或硬件验证；不要保存/再生成冻结证据工程。安装 Schema/源图最终证据是上述 118 项，不是旧 22 项初验。
2. **生成/诊断入口**：SCG 在另选的新目录生成，构建日志核对 `DIAGNOSTICS|bound|...` 和确切 ELF；项目 `.ssdiag` 的 pending/失败状态不得当成绑定成功。当前 Flight/Ground 项目入口与 GSHC 后续整合由并行任务验收；普通 Make 不自动运行主机 binder。探针连接不是本次操作范围。
3. **导航冻结验收入口**：[补充说明](../public/SCG/NAVIGATION_REVIEW_ADDENDUM_20261016.md)与[六配置清单](../evidence/navigation_receipt_default_off_20261016/validation.json)。后者记录每个实际 ARM/analyzer/Power10/architecture/artifact/stack 及完整 Host 运行；前者的历史 FLP raw-only 导出限制后来由提交 `e0bc7938` 修复，历史 golden/model fixture 由 `09615f22` 定向修复，不能继续把旧失败概括成当前全局状态。也没有当前全仓库一次性 PASS。
4. **维护/TF/MAG 软件入口**：完整维护协议、TF 生命周期/v21/v4 报告及 `test_maintenance_r04_generation.py`、`test_magnetometer_entry_generation.py`、`test_installation_capture_generation.py`、`test_installation_store_lifecycle.py`。本次只读这些入口，不运行其构建、不连接已烧录候选。安装插件继续 default OFF/真实 BEGIN 拒绝。
5. **发布阻断**：先闭合 [RELEASE_IDENTITY_FOLLOWUP](RELEASE_IDENTITY_FOLLOWUP_20261018.md)：根产品 0.1.3 与普通 C 默认 0.1.2/build0 的身份不一致尚 OPEN；显式测试身份不代表普通生成已统一。还需精确最终 dirty snapshot 的整合验收、USB 剩余失败处理、真实源资格/安装全入口互斥与 wire 验证/应用/保存、完整不可变标定快照随日志导出，以及上述关键合同/栈/WCET/硬件缺证。

本次本地读取与文档写入无权限拒绝、无连接阻断、无执行结果不明。C071 的登录/包环境、旧 COM9 拒绝等是各原任务记录的历史/具体路径限制，未在本次重试。暂停的 M9N INT32_MIN 任务未调查或运行；并行 GSHC 程序与其他安装/TF 任务文件未改。
