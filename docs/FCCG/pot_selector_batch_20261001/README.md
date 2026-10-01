# 2026-10-01 白天 source selector 安全批次

本批严格 Flight Power of Ten 从 **180 项降至 171 项**，Ground 仍为 **0 项**。Flight 仍然 FAIL；不存在整机原版十条规则合规或硬件/飞行资格结论。旧 180 项报告与旧验证结果未改写。

## 版本、归属及生成

起始 HEAD：`70ce20d157545d9109491d004bd293e5c0b053db`。继承的 dirty 为 AGENTS 的严格 Rule 5 补充、Core selector、原 Host 测试的读取结果保护，以及 selector 新夹具和 pytest。全部保留并接续，无 reset/clean/stash、无并行修改者。本批 owning source 是 `apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Src/system_source_selector.c`，没有仅修复生成副本。

新隔离工程为 `.work/SelectorSafety_70ce20d_20261001_v1/{baseline,after}`。读取先前隔离工程中的配置，通过 `TargetGeneration_Apply` fresh ALL 生成，不改用户最终候选。基线生成后仅将 selector 替换为上述 HEAD 的原始 bytes；其他固件 payload 无本批修改。after selector 与 owning source 逐字节相等；基线与 after 的 checker SHA-256 相同。生成配置、命令、版本、退出码及源码/日志/产物哈希在 [result.json](result.json)，该文件的验证对象是可审计 dirty snapshot，不能误标为起始 HEAD 的干净源码。

## 真实契约及缺陷

| 函数 | 契约与失败路径 | 严格计数 / code lines |
|---|---|---:|
| `SystemImu_Init` | CountGet 超容量为普通 INTERNAL_ERROR，清空存储 count；循环中实例 ID 在 count 内，驱动 result 属于枚举，再发布 initialized。内部损坏 fail-stop。 | 2 / 48 |
| `SystemGnss_Init` | 同上；保留主源失败时的初始化替补和源变化事件。 | 2 / 52 |
| `SystemTelemetry_Init` | 同上；没有设备或普通驱动失败保持既有错误返回。 | 2 / 54 |
| `SystemImu_Start` | count 容量、order 实例索引、驱动 result 契约；调用前清除旧 started，失败不保留旧成功状态。 | 3 / 34 |
| `SystemGnss_Start` | 上述契约及 active 索引/位置映射一致；一次有界扫描记录按原单向顺序首个成功候选，完成后发布 active。替代原第二次扫描，非为避门槛拆函数。 | 5 / 58 |
| `SystemTelemetry_Start` | count 和 active 索引、驱动 result 契约；旧 started 在重试前撤销。失败且无替补返回 NOT_READY，Send 不会继续使用旧 started。 | 3 / 31 |
| `SystemSourceSelector_GnssSwitchEvaluate` | count、active、active_position/order 对应、候选索引；存活替补前检查，不以无 fix 代替失联判据。 | 4 / 53 |
| `SystemSourceSelector_TelemetryNextStart` | count、active_position/order 对应、候选索引及驱动 result；候选失败撤销旧 started，不发布 active/position。 | 4 / 37 |
| `SystemSourceSelector_TelemetryHealthProcess` | count、active 索引及连续 timeout 不超过阈值；在健康读取及 `limit-count` 计算前检查，防止损坏计数产生无符号下溢。 | 3 / 56 |

基线各函数均为 0 个 checker 有效计数。以上 28 个新增计数均为业务值检查，替换了无有效计数的静态对象地址检查；未增加白名单、排除源文件、弱化阈值或制造静态非空/对齐断言。有限循环仍以既有编译期 MAX（最大 4）为上界；驱动 result 检查在 initialized/started 成功发布之前。成功返回仍要求至少一个成功实例。普通错误与内部损坏保持不同处理路径：外部参数/普通 I/O 失败返回既有错误，内部损坏进入既有终止 trap，Host longjmp 仅拦截该 trap，不代表 MCU 恢复。

Init/Start 的调用者是启动路径；GNSS runtime processing 经设备所有者路径、遥测 health/替补经遥测 processing 路径。本批未新增 ISR 写者、回调注册表或扩大临界区。整文件审阅发现其余入口及 pending event 的并发/所有权仍需独立审查，本批不宣称完整状态机或并发安全证明。

## 门禁和补充密度

原生成 checker 实跑基线 180、after 171（两次 make exit 2），Ground 两次 exit 0。剩余 **153 零断言、18 单断言**，全部保留 FAIL，详见 [current_171.csv](current_171.csv) 和 [inventory.json](inventory.json)。九个目标函数没有新增超过 60 行失败。相关原 checker 路径测试也继续检查原阈值和失败预期。

另一个测量脚本复用原 parser 定义而不改门禁：基线 2,513 / 2,604 函数，after 2,541 / 2,604 = **0.975806 次文本计数/函数**。扫描范围为原 first-party 路径；不预处理所有配置，正则对 typed-object 宏可能计两次，无法证明语义有用性、路径覆盖或整体平均合规。该补充统计绝不替代 N=2/M=20，也不作为论文平均规则的完整证明。

AGENTS 已完整核对并保留其他仓库指导。[作者详细 Rule 5](https://www.spinroot.com/p10/rule5.html) 的 N=2/M=20 与[概览](https://spinroot.com/p10/)的平均口径分别记录，没有混同。

## 第三方和证明边界

[linked_third_party_inventory.json](linked_third_party_inventory.json) 记录 F407 47 个受控 vendor/middleware link inputs、F103 23 个受控 compile inputs、map 中的 libc/libm/libgcc/libnosys archives 及版本头哈希。F103 单次编译链接使用临时 object，不能靠 LOAD 名称可靠归因源文件；使用原 source graph 与构建命令。LOAD 与选入编译不等于 GC 后仍保留的精确调用图。

现有受控偏差不扩大：HAL/CMSIS/FreeRTOS/FatFs 原始上游代码不纳入 first-party gate；固定 task entry、既有 RTOS/HAL callbacks 及库间接调用需另行递归、栈和时间分析。FreeRTOS 版本头为 V11.3.0，CMSIS Core 5.6，FatFs revision ID 68300；上游许可及源码未改。HAL 的轮询/回调、RTOS 的调度/任务间接调用、FatFs 的 I/O 与库函数路径均未完成原十条逐项证明，标记 **NOT PROVEN**，不能由本批工具通过清除其违规。

静态链接 spare bytes、Host 执行时间及断言计数不证明任务栈裕量、main/MSP/ISR 嵌套、STM32 WCET、导航精度或硬件/飞行资格。即使 stack-report 在其模型下通过，实际任务路径、动态帧、库调用和中断嵌套仍需独立证据。本批未刷机、START/执行器、推送、发布、打包或关机。

## 验证记录

| 验证 | 最终结果 |
|---|---|
| 相同最终 Host 契约夹具的修复前基线 | 32 失败、6 正常通过；每例完整日志保留 |
| 最终相关 pytest（selector、启动 FSM、JY901B、M9N、原 checker 路径） | 51/51 通过，未 skip |
| 生成完整 Host suite | 72/72 通过 |
| F407 / F103 fresh ARM 编译和链接 | 两者 exit 0 |
| F407 `static-analysis` | `-fanalyzer -c` 实际编译/链接，exit 0；非 syntax-only |
| F103 first-party 分源分析 | 14 个实际 `-fanalyzer -c` 编译均 exit 0 |
| 分析器负向 canary | double-free 返回 1，包含 `analyzer-double-free` 诊断，符合预期 |
| architecture / artifact / stack-report | 各 exit 0，仅证明工具记录的范围 |

命令与完整日志在 result.json、verification_final.json。同目录保存了运行及计数脚本；脚本故意拒绝复用已有输出目录，复跑应选新的明确版本目录，不覆盖旧证据。

完整执行结果以 result.json 和每项完整日志为准。初始 pytest 共用 `.work/pytest` 被权限错误阻挡，之后改用全新 basetemp；该初始执行没有完整保存日志，只保留会话记录，不能计为通过。早期 `gnss_order` 负例未先制造主源失联，健康路径提前返回；夹具已改为失联后检验损坏候选索引。后续 `start_order-2` 命中了更早的 active/order 一致性检查，其失败日志保留，最终将一致性和候选索引分别覆盖，保持 fault、无非法 port 调用及无成功发布的安全期望。

验证最终结果和尚存阻塞见 [verification_final.json](verification_final.json)。最新发布决定仅追加到[本地延期记录](已实现但仍有问题、暂不发布内容.md)，保留此前候选评估；本批不实施 GUI、隐藏或算法扩展。完成当前批次后冻结源码，并按明确传输授权导出限定审查资料至用户自己的 Library，供父任务亲自逐函数审阅，不扩大断言修改。

限定 ZIP 已保存至 Library，身份见 [library_review_receipt.json](library_review_receipt.json)，ZIP 路径/哈希及源码版本见 [review_export.json](review_export.json)。当前配置所需 161 个头文件由实际 ARM `-MM` 依赖闭包得到，排除未启用的 HAL/RTOS 变体；与 17 个对应完整 C 文件、171 个完整函数体及原 checker 一同提供，不包含用户日志或二进制。原 checker 在字符串续行后的行号存在偏移，包内同时提供原诊断 `line` 和真实 `actual_line/end_line`，不改门禁计数。Windows Python 不支持 `os.setxattr`，官方本地身份 helper 返回 1，故未声称写入了本地扩展属性；Library 保存本身成功，精确身份另存于本地 receipt。
