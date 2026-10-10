# SilverStar 用户阅读与操作路线

本文面向当前 0.1.2 候选软件；新 GUI 行为、软件门禁和未完成项见[0.1.2 验收记录](GUI_ACCEPTANCE_0_1_2_20261008.md)。先前软件与板测记录保留原身份；[000051 静态复测](LOGGER_HEALTH_RETEST_20261008.md)不能代替 0.1.2 的硬件验收。

## 1. 先认识整个流程

SCG 配置设备、算法、协议与真实硬件资源，生成独立 Flight/Ground 工程及其精确 `.ssdecoder`；GSHC 采集地面会话并显示权威状态；FLP 读取飞控日志与匹配 decoder，分析 Recorded 数据并保留每次离线计算。三者共享项目身份，运行职责各自独立。

先读[项目目录契约](architecture/PROJECT_FOLDER_CONTRACT.md)、[双目标模型](architecture/TARGET_MODEL.md)和[AIR Link](architecture/AIR_LINK.md)。创建用户选定的项目目录，保留项目、生成身份、decoder、实际二进制和源日志的对应关系。普通再生成保护工程中用户拥有的源文件；不能用另一次生成的 decoder 为旧日志补身份。

## 2. 硬件与四档

阅读[推荐组合与验证范围](SilverStar_Recommended_Configurations.md)和[四档契约](FCCG/platform/details/FEATURE_TIERS_20261006.md)。内部标识仍为 `full/standard/compact/minimal`，中文显示固定为完整、标准、轻量、最简，档位不是 MCU 型号。

| 档位 | 估计器选择（四档均可纯惯导） | 设备边界 | 普通/估计器日志队列 |
| --- | --- | --- | --- |
| 完整 | SF6、KF6、ESKF15 | 各插件声明的实例上限 | 80/48 |
| 标准 | SF6、KF6 | 各插件声明的实例上限 | 80/48 |
| 轻量 | SF6 | 每种传感器最多一个，最多一个遥测；允许单 GNSS | 56/16 |
| 最简 | SF6 | 每种传感器最多一个，最多一个遥测；禁止 GNSS，关闭维护协议，要求本地日志契约 | 24/16 |

用户明确切换到轻量/最简时，按当前列表顺序保留各传感器类及遥测的第一个实例和原参数，移除后续超额实例；最简还移除 GNSS，且不能重新加入。移除实例的来源/资源绑定同步撤下，仍须审核剩余资源和其他冲突。回到完整/标准可以再次添加设备，但不会恢复已移除实例；原档策略、参数和协议预设仍可恢复。直接载入已有冲突配置不会自动删设备，生成必须拒绝，需明确切档或手动修改。多功能 IMU 内置气压与独立气压的所有权规则保持不变，不等于禁选 JY901B 气压。历史四档契约中的“切档保留冲突”由本次用户明确要求更新，见 0.1.2 记录。

资源颜色和 20% RAM 是建议，不是安全门槛或栈证明。H7 没有当前 builtin 生成支持；F407/ESKF15 运行失败尚未解决；F103/NRF 未实物验证；RET6 Logger 栈结论限其记载配置。无 GNSS 的水平位置会漂移。

## 3. SCG 配置与生成

按[SCG 应用说明](FCCG/APP_README.md)、[用户指南](FCCG/USER_GUIDE.md)、[SCG 索引](FCCG/README.md)和[构建说明](FCCG/BUILD.md)操作：选择设备实例 → Flight/Navigation/Telemetry 配置 → 实际 Board 或用户 CubeMX 工程 → 手动确认资源 → 查看 Build & Validation 的错误与预算 → 生成。

初对准与惯导不同。先配置 Calibration/Alignment，再配置传播与融合；数学和实现从[四算法说明](algorithms/NAVIGATION_IMPLEMENTATION.md)进入。引脚、执行器和开伞策略必须来自真实工程和用户决定，示例配置不能替代确认。

导入或重开项目后检查档位、设备、算法实际值、canonical 来源、Flight/Ground 资源及协议；有冲突先修正再生成。不通过修改源码、减导航队列或隐藏诊断来绕过生成错误。

## 4. GSHC 采集

阅读[GSHC 应用说明](GSHC/APP_README.md)、[接收架构](GSHC/UPPER_COMPUTER_ARCHITECTURE.md)和[AIR M0](GSHC/AIR_PROTOCOL.md)。连接行为在用户授权的硬件验收阶段进行。命令 ACK 只表示相应事务接受/结果，不能替代 Calibration/Alignment 或控制器的 READY；以权威快照为准。

会话 JSONL 和实时显示窗口不同；显示裁剪不等于持久记录裁剪。诊断页用于核对 GSP、空口、ACK、队列积压及状态年龄。NRF 没有 RSSI/SNR 时显示空值，不补零。保持现有预飞/飞行/后处理布局。

## 5. FLP 分析与保存

阅读[FLP 应用说明](FLP/APP_README.md)、[decoder 精确匹配](FLP/Decoder_Profile_Package.md)、[工程保存](FLP/Project_Artifacts.md)（由[FLP 架构](FLP/Architecture.md)补充契约）和[算法说明](algorithms/NAVIGATION_IMPLEMENTATION.md)。源日志及 decoder 保持原样。

打开项目或 log/decoder 对，检查 Descriptor、固件/配置身份与数据质量，再选 Recorded 或离线算法。Offline 默认值不能称为记录值；What-if 是独立结果，不能覆盖历史 run。主副数据源都要检查可用性和身份。

保存含数据与结果时，压缩、哈希和校验显示真实处理量；阶段百分比不表示已持久提交。100% 只在原子提交并完成 GUI 发布后出现。取消要保留原工程；关闭进行中的保存沿现有提交等待规则。重开应恢复全部已完成 run、参数、主副数据源，缺失或坏缓存经同一严格 coordinator 回读源日志，不自动重算，也不使用备用 decoder。

## 6. 验证与故障排查

Windows保存时若提示工程/工件路径过长，请选择较短保存目录或工程名后重试；不要移动或修改原日志/decoder来绕过身份检查。当前宿主可能在项目文件路径合法时，因内部SHA256工件文件达到长路径边界而失败。该失败应明确报“未完成”，保留旧工程和run；详见收尾报告中的实测范围。全面长路径支持尚未实现。

依次核对[当前 0.1.2 验收](GUI_ACCEPTANCE_0_1_2_20261008.md)、[先前软件收尾](NIGHTLY_SOFTWARE_CLOSEOUT_20261008.md)、[前次 GUI 记录](RELEASE_GUI_CLOSEOUT_20261008.md)、[运行安全](FCCG/platform/details/RUNTIME_SAFETY.md)和[实物验收清单](field/FIELD_TEST_CHECKLIST_0_1_0.md)。PASS 只覆盖记录的命令/源码/配置。FAIL 或 NOT PROVEN 不得拼接成全面通过。

软件收尾报告截止时没有硬件操作。随后用户接好硬件并另行授权；[准备阶段](STATIC_BENCH_PROGRESS_20261008.md)保留原门禁失败，[授权后的静态任务记录](STATIC_BENCH_ACCEPTANCE_20261008.md)记录新源码、一次 Flight 烧录读回、权威 READY 和任务 `000044`。执行机构全部物理断开，观察的是 Delay10 逻辑展开；没有生成最终外场工程。

用户随后授权[一次静态复查](STATIC_BENCH_REPEAT_20261008.md)，同一BIN在必要的一次启动复位后完成任务 `000045`。落地宽限期拒绝为0，停收/finalized后变为1（000044为2）；SX1281入队拒绝复现。约94.3ms是启动以来单次最大的Estimator循环start-to-start间隔，两轮均在START前读到；本轮完整live timing快照序号不一致，不能扩为全段一致timing验收。

用户已原位替换日志，[实际 TF 文件与 FLP 离线验收](STATIC_LOG_FILE_ACCEPTANCE_20261008.md)完成 `000044/45` 的精确 Descriptor、CRC、snapshot/校准/初始状态、已记录导航输入连续性，以及同一原生 GUI 进程的两次 run、主副数据源和完整保存重开。零序号缺口只覆盖已接受记录，不能证明停收拒绝无害；空口完整性、拒绝调用身份及启动最大间隔归因仍未证明。下一步只针对这些未证明问题先制定最小观测与测试方案，不自动重跑硬件。旧 `28b168f/mission000041` 不替代本次证据。
