# 本地 SCG/FLP 集成与 RE/RF 实际试验，2026-10-07 UTC

本次按用户授权更新日常源码供本地测试，不烧录、不访问硬件、不推送。
日常起点为 `cd76d8e0c8ccddb28e823e0f6ab6d47613276f51`；SCG 候选为
`5fa6dc3b25106bfbcad1facea6b9af79a9e39a5c`，FLP 候选为
`9df808e03bfffb88ec20f43569f7109011c2b350`。复用 `.work/kh`，未复制仓库、
venv 或历史构建。集成分支为 `integration/local-user-test-20261007`。

## 集成范围和验证

合并日常历史的三个 Logger 冲突全部采用已审 5fa 文件：队列几何检查、局部
record 生命周期、配置感知的 alignment 测试。完成后，SCG/共享契约整树与
5fa 完全一致，FLP/FLP 文档整树与 9df 完全一致，GSHC 与日常 cd76 完全一致。
算法数学、协议、24/16 实验以外的队列默认、NAV_STATUS 均没有本次新改动。

最终组合提交之前的生产组合源码为 `3aef956`，版本测试修正当时为审计 dirty
输入，随后随此报告提交；没有后续生产源码改动。本轮实际执行：

| 检查 | 实际结果 | 范围 |
|---|---|---|
| SCG tier、日志策略、schema、MPU epoch、importer 短回归 | 64 passed，exit 0 | 无完整生成工程/ARM 重建 |
| FLP 小型真实存储进度和三个独立 GL 所有权进程 | 8 passed，exit 0 | 21-sample PureINS 测试输入；不是实飞或大规模算法验算 |
| 跨应用版本、共同导航契约 | 修正旧测试后 2 passed，exit 0 | 保留修正前 1 failed / 1 passed 记录 |
| 组合目录身份、改变的 Python AST、manifest JSON | PASS；74 个 Python 文件 | 静态语法，不是 C 静态分析 |
| 实际 RE NRF、RF 四模块、F407 KF6 项目模型校验 | 三者 PASS，参数未变 | 读取保留工程；不改源工程 |
| 当前 SCG render 的小型 decoder 被 FLP 严格读取 | 三者 PASS | 仅 package admission；不是日志/Descriptor 打开或 replay |

旧版本测试错误地假设除单一 RTOS 外的所有插件都是 0.1.0。唯一新增的测试修正
明确列出已审独立版本：KF6/SF6 0.2.0，BMP280/MS5611 0.1.1，以及两个 FreeRTOS
11.3.0 port；其它插件仍断言 0.1.0。没有修改 manifest 来满足测试。
SCG 和跨应用 pytest 的 `Unknown config option: cache_dir` 警告保留。

本轮未重新执行完整 Host、ARM、-fanalyzer、Power10、架构、artifact、stack 或
memory 大套。下表的固件结果属于各自历史已执行修订，不能归属为本次组合的新
二进制。FLP 历史 17 项组合通过仍含 34 个 QBasicTimer 跨线程警告；云端
134/139 尚未归因，完整 GUI 生命周期仍待用户验收。ESKF15 仍未通过 F407 实机。

父线程另确认原 28b 板测工程的 TF 000041 已完成 FLP 解析：10188 records，
CRC/序列/结尾正常，1405 estimator Step、703 barometer 成功、overflow 0。
这属于原 28b 的板测/解析闭环，本轮没有重新解析、烧录或测试 5fa/组合候选。

## 配置及真实资源

RE/RF 均经实际官方 CubeMX 6.15/F1 V1.8.7 工程生成、SCG 导入；不是手写假 IOC。
RET6 为 REx/xE，512 KiB Flash、64 KiB SRAM；RFT6 为 RFTx/xG，768 KiB Flash、
96 KiB SRAM。两者为 Cortex-M3，`-mthumb -mfloat-abi=soft`，无 FPU/CCM。
原 E28 RE/RF 工程为 64 MHz HSI PLL。无线和外设工作情况没有板测。

| 试验及来源 | 模式/模块 | Flash 口径 | 主 RAM（含静态栈和 MSP） | 余量 | 距 20% 余量目标 |
|---|---|---:|---:|---:|---:|
| RET E28，cf66 Logger 修复 | Minimal；MPU6050、BMP280、E28-2G4M12SX；无 GNSS | ELF load 222620 B | 63936 / 65536 B | 1600 B，2.44% | 少 11508 B |
| RET NRF，已执行 Host 合同 batch（8ce + 审计 dirty Host 快照，提交为 2eff） | Minimal；MPU6050、BMP280、NRF24L01+；无 GNSS | ELF load 209480 B；BIN span 209488 B | 62224 / 65536 B | 3312 B，5.05% | 少 9796 B |
| RET NRF，f8 外部编译参数 24/16 实验 | 同上，只有 normal/est 深度覆盖 | ELF load 209456 B；BIN span 209464 B | 54208 / 65536 B | 11328 B，17.29% | 少 1780 B |
| RF 四模块，3ed454c 历史实际链接 | Compact；MPU6050、NEO-M9N、E28-2G4M12SX、BMP280 | BIN/Flash load span 252832 B | 97488 / 98304 B | 816 B，0.83% | 少 18845 B |

四者满足各自 linker 硬容量，但均未达到 20% SRAM spare。Flash load 字节之和与
BIN/address span 包含对齐的口径不同，不混用。24/16 的直接对照是 f8 默认
62224 B RAM / 209464 B ELF load，而不是后来 209480 B 镜像；同修订净差为
RAM -8016 B、ELF load -8 B。旧 boolean Compact 的 RF 79080 B 记录不是新
Compact tier 的默认结果，不能替代 97488 B。

RET 最小模式保留本地 SDIO/FatFs SSLOG，maintenance 关闭；RF 保留本地全流
profile，并手动关闭 maintenance。RE 缺少 GNSS：气压计约束垂直状态不保证
水平位置不漂移。SF6 核心仍是原来的 192 B，无“删除历史缓存”节省声明。
NRF 两端实际配置为 channel 73、1 Mbps、地址 E7E7E7E701、0 dBm、1000 us
重试间隔、三次重试，物理/逻辑 payload 32/61 B；没有 RF 交换板测。

## 队列、日志和速率

| 配置 | normal | est | IMU/nav 两队列 | 聚合 buffer | 静态 task/idle 栈；MSP |
|---|---|---|---|---|---|
| RET 默认（E28 或 NRF Minimal） | 58 × 168 B | 40 × 96 B | 16 / 16 | 1024 B | 21504 B；2048 B |
| RET 24/16 实验 | 24 × 168 B | 16 × 96 B | 16 / 16 | 1024 B | 与默认相同 |
| RF Compact 默认 | 80 × 200 B | 48 × 200 B | 64 / 64 | 4096 B | 21504 B；2048 B |

24/16 未写入 SCG 默认。RF 40/16 仅只读提案，未构建；现有 all-streams
snapshot 合同为 `1 config + 9 device + 4 algorithm + 40 stream = 54`
个 normal slot，40 少 14。54 只是已有必要约束，不证明 START 的额外记录和
动态拥塞仍有足够容量。RE Minimal 使用独立拥有的 53-record snapshot cursor，
默认 normal 58 留五个槽；24-depth 满队列/第 25 项 FULL、溢出计数、完整 cursor
排空和无假 START ACK 均有独立实验。不能由此把 RF all-streams 改为相同深度。

配置的 MPU 输出为 200 Hz，BMP280 为 20 Hz；RF M9N 为 25 Hz/airborne 4G。
Coning2/sculling2 聚合两个真实 IMU interval。以下是配置/发送策略，不是实测
写盘速率；EVERY 跟随成功 producer 发布，不能保证固定无丢帧频率。

RET 当前包启用 20 个 stream，全部 40 个 stream descriptor/catalog 保留：

- 周期：STATS、HEALTH 各 1 Hz；SF6_STATE 配置 10 Hz。
- EVERY：BARO_NATIVE、INERTIAL_INCREMENT、IMU_CORRECTED、LANDING_DIAGNOSTIC、
  SF6_MEASUREMENT；实际受对应 producer、初始化/START、节流和队列结果约束。
- EVENT：EVENT、CALIBRATION_RESULT、ALIGNMENT_RESULT、ALIGNMENT_EVIDENCE。
- ONE_SHOT：SYSTEM_CONFIG、INITIAL_STATE、MISSION_CONFIG、DEVICE_DESCRIPTOR、
  ALGORITHM_DESCRIPTOR、LOG_STREAM_DESCRIPTOR、DECODER_PROFILE_DESCRIPTOR、
  MISSION_SNAPSHOT_IDENTITY。

RF 历史已编译 stream 表启用 26 项，包含 ESTIMATOR/PURE_INS 25 Hz 配置和
TELEMETRY_DIAG 1 Hz 配置，SF6_STATE/SF6_MEASUREMENT 的保存选项为关闭。这里
的 enabled 不证明选定 SF6 producer 实际生成了其它算法结果。
当前已审首发投影裁掉这三个不适用项，读取该保存项目后生成的当前包启用 23 项：
同类 metadata/event/sensor 条目，额外 GNSS_NATIVE、GNSS_MEASUREMENT、
BARO_MEASUREMENT、ESTIMATOR_STEP、GNSS_RECOVERY 的 EVERY 选项。
该保存项目的 SF6_STATE/MEASUREMENT 仍关闭，不能当作已记录完整 SF6 p/v/q。
本次保持保存选择，没有擅自启用、制造 common NAV_STATUS 或新默认。
因此 RF 的 97488 B 和旧 stream 表只能作为历史编译证据；当前首发策略的 RF
四模块需要另行配置和编译后才有新资源/日志证据。

## 栈与执行边界

RET NRF 默认的实际 ELF 栈报告（byte）与 24/16 实验估计一致：

| task | worst-known estimate | 配置 | margin |
|---|---:|---:|---:|
| Device | 1604 | 2560 | 956 |
| INS | 2224 | 3072 | 848 |
| Estimator | 1440 | 4096 | 2656 |
| Flight | 3480 | 4096 | 616 |
| Logger | 2736 | 3072 | 336 |
| Telemetry | 2168 | 4096 | 1928 |
| Idle | 256 | 512 | 256 |

RF 原 gate 曾因 M9N-only startup binding 不匹配而失败；后续只读 callback
检查得到 Device 2112/2560、Logger 3072/3072，Logger margin 0，仍 FAIL。
cf66 的 Logger 作用域修复实际重新编译验证了 RET/F407，没有新的 RF 二进制可
据此宣称 RF 栈通过。RE 栈通过也不替代 RF 栈证明。
所有 task 栈已包含在 RAM 表中，不再相加；whole main/MSP/ISR、第三方/间接
调用、实际高水位和 WCET 仍 NOT PROVEN。

| 历史执行范围 | ARM/link / analyzer | Host | 其它 gate | 板测 |
|---|---|---|---|---|
| RET NRF 默认已执行 Host 合同 batch | PASS / PASS | 完整 wrapper 含 storage：71 executable、4402031 checks、3 compile positive、16 named reject、0 failure | architecture/P10/artifact/stack/memory exit 0；critical-contract NOT PROVEN | NOT RUN |
| RET 24/16 f8 实验 | PASS / PASS | 原 snapshot+streaming 1037 checks；扩展 snapshot 478 checks 为独立运行，不能相加当独立 coverage；无完整 Host PASS | emitted P10/architecture/stack exit 0；整体证明未闭合 | NOT RUN |
| RF 四模块历史 tier | PASS / PASS | 完整 Host FAILED：缺失未选中 JY header；未重跑 RF 完整 Host | architecture/P10/artifact exit 0；stack FAIL（含后续 Logger margin 0） | NOT RUN |

RET 原 newlib `_read/_write/_close/_lseek` stub 警告保留。RF 上述最终历史 ARM/
analyzer 日志无 warning，不代表原 Power of Ten 合规、板端外设可用或飞行资格。
5fa 后续仅增加 Host qualification 隔离正例/negative 变异证明；不构成新 ARM
镜像。RF 不继承 RE 的完整 Host 或 Logger 栈通过结论。

## 回退与证据

回退 Git 引用：`backup/daily-before-local-integration-20261007` 指向原 cd76。
原 untracked `work_build_candidates_20261006.csv`、`work_inventory_20261006.txt`、
`work_subtree_classification_20261006.csv` 保留原地，另作了字节备份和 SHA 核对。
没有删除或清理别人文件，没有关闭用户 GUI。

本次命令、日志、失败、身份、三个小 decoder 和备份清单位于
`.work/kh/.work/integration_20261007`。历史固件完整证据仍在已审 Host/NRF/RF
证据包及对应隔离工程，不用本次静态检查冒充新 ARM 或大套 PASS。
待决仍为 common 日志方案、队列默认及后续硬件/GUI/最终验收安排。
