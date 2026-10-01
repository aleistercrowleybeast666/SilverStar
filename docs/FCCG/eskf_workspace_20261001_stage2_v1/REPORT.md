# 2026-10-01 固件收口第二批：ESKF scratch 复用

本批以本地 `42d4203b0158184e4a8609a1a971a788f335cfb0` 为基线，只修改 ESKF15 所属声明式插件的 kernel/header，新增实际 kernel/replay 对照测试和本目录证据。先前 UART/JY/质量状态修复、AGENTS 和其他工作均保留。本批未修改 KF6、导航模型、15 状态维度、float 精度、200 Hz 配对节拍、协议、日志或任务栈；未实施 CCM 跨区迁移、MCU 移植、打包或硬件动作。

## 实际修改与边界

- 将 `temporary[15][15]` 改为 `product_row[15]`，逐行完成 T P Tᵀ。P、transition 和 candidate P 保持分离，k 累加顺序与旧版相同；每行消费完才覆盖。节省 `(225-15)*sizeof(float)=840` 字节。
- Cholesky scratch 复用已完成最后一次读取的 F：Predict 必须先完成 NoiseAdd；Update 必须先完成 reset congruence。本批未把 F 和 product_row 互相别名，因为过程噪声仍读取 F。
- Initialize 先用 memmove 保存 nominal/covariance 到 candidate buffers，再把 F 用作 Cholesky scratch，最后成功才提交 state。真实 backend 以 `s_work.f` 传入初始协方差，若直接复用 F 而不保存输入，会破坏它；这是此次优化必须防止的新风险，**不是声称旧版已经发生该错误**。
- 校验错误保留原结果码，已有已发布 state 不部分提交。没有新增凑数断言、扩大白名单或改变 PoT 其他规则。
- 注释明确共享 state/work 必须串行访问；并发/重入必须分别拥有 state 和 workspace。CPU-only scratch 可以放普通 SRAM，但不能当 DMA buffer，也不移到任务栈。

当前 source-callsite 审阅：Predict/Update 由 EstimatorTask 执行；FlightTask 调用生命周期准备/初始化/回滚。现配置优先级 Estimator=6、Flight=5；ESKF 初始化先完成 backend，再发布 mission_running。未发现 ISR 直接访问 workspace。Reset 本身不清空/改写 workspace。**上述有限审阅不是整个调度、优先级继承、未来调用者及全部生命周期的形式证明**；共享实例并发保证仍须人工接受。测试中的两个独立实例并发通过只证明实例隔离。

## 前后证据

`test_eskf_workspace_equivalence.py` 从上述基线 commit 抽取旧版 kernel/replay 四个文件，分别以 GCC 16.1.0、O0/O2、`-fno-fast-math -ffp-contract=off` 编译旧新实现。七种 scenario × 两级优化加 sizeof 检查，共 **15 passed**；最后注释修订后重新完整执行，仍 **15 passed in 11.95s**。

对照覆盖静止、恒定转动、平移、GNSS 失锁/恢复、延迟测量回放、初值别名、故障、独立实例并发。正常输入 240 个 5ms 周期，记录 nominal 全 16 个 float、完整 15×15 P、时间/源/代际/初始化标志，以及 replay anchor/working state、计数和更新结果。非法时间/间隔/源/代际、NaN、无效协方差、无效测量、NIS 拒绝/降权、历史数量损坏、时间戳边界等保留既定拒绝与不提交行为。详见已提交 harness；这不是所有故障的穷尽证明。

旧新完整输出逐字节相同，不是只比较 P 的对角线。O0/O2 的这组轨迹也相同；14 对完整结果去重保存为 7 个完整 `.trace`，每个原始路径和两侧 SHA256 均在 `trace_equivalence.json`，最终注释版本轨迹 SHA 也相同。无硬件精度、稳定性或 ARM 浮点位级等价声明。

最终注释只纠正生命周期 ownership 描述，保持行数。真实 kernel 预处理字节完全相同，记录在 `final_comment_equivalence.json`；其后实际重新编译受影响 ARM/分析器目标并链接、执行 PoT、artifact、stack。最终 Release ELF 与注释修订前 ELF SHA 相同。Host 全套在注释修订前的相同 executable 代码上执行，未把它写成再次全套执行。

## 验证结果

| 范围 | 本轮实际结果 |
| --- | --- |
|完整生命周期 + 400/200Hz body cadence + 质量人工接受状态|23 passed in 302.79s；包含完整 lifecycle 16 项，不拼接旧结果|
|旧新 kernel/replay 完整轨迹|15 passed，最终源码再跑 15 passed；两次分别记录|
|ESKF Host 全套|71 executables；4,361,109 checks；0 failures；8 compile pass cases；16 expected compile failures；实际 storage/logger byte integrity 通过|
|隔离 KF6 / ESKF15 / Pure INS PoT、F103 Ground PoT|均 exit 0；断言建议及人工审阅仍未完成|
|F407 KF6 / ESKF15 / Pure INS，F103 Ground 实际 ARM compile/link|均 exit 0；ARM GNU 14.3.1，完整日志留存|
|ESKF 实际 `-fanalyzer -c` 编译与链接|exit 0；不是语法检查；最终注释后增量重新分析受影响对象并链接|
|三种 F407 architecture / artifact / task stack report|均 exit 0；ESKF 最终版本再次 artifact/stack exit 0|

主 driver 19 个质量/构建命令全部 exit 0；最终注释 driver 5 个命令全部 exit 0。命令、cwd、时间、工具版本、输入 config/hash、source snapshot、全部输出、artifact hash 在 `result.json`、`final_comment_checks.json` 及日志。F103 的 4 条 newlib `_close/_lseek/_read/_write` 未实现 stub 链接警告仍存在，**不宣称全部固件严格零警告**。KF6 Host/static 由第一批报告记录，第二批未伪装成重新执行；本轮 KF6 实际 ARM/source-graph/artifact/stack 已重新执行。

## PoT 当前政策与计数

按用户 2026-10-01 07:45 后选择的 F Prime-inspired C 政策，>10 代码行且无 runtime candidate 是非阻塞建议；平均只作信息，关键契约仍 `NOT PROVEN / manual_acceptance_pending`。没有用平均值替代安全契约，没有把旧 180 项直接写成修复至零。历史严格 N=2/M=20 清单、旧失败和原始证据仍保留。

|配置|first-party C|functions|heuristic runtime candidates|平均候选/函数|建议|
|---|---:|---:|---:|---:|---:|
|KF6 Flight|108|2608|1595|0.611580|741|
|ESKF15 Flight|108|2535|1500|0.591716|720|
|Pure INS Flight|105|2484|1433|0.576892|716|
|Ground|15|148|106|0.716216|34|

Ground 的当前硬门禁仍零失败，但这不是“Ground 没有建议”。分母是 checker 所扫描第一方 C 的函数（含 generated），不含第三方/header/宏展开后的全程序语义；candidate 是启发式不是有效契约证明。相对于第一批，ESKF scratch 不改变 candidate 数；函数变长可新增建议，禁止将这种变化藏掉。GUI 对硬失败/仅建议的区分、整个目标零有效候选的阻断及建议导出留给已授权下一轮，不在此批实现。

## 新鲜链接资源：完整同源 flight 配置

|配置|Flash used / spare|main SRAM used / spare|CCM used / spare|runtime heap|
|---|---:|---:|---:|---:|
|KF6|316148 / 208140|101280 / 29792|55432 / 10104|0|
|ESKF15|302292 / 221996|99880 / 31192|63456 / 2080|0|
|Pure INS|283772 / 240516|81952 / 49120|44016 / 21520|0|

字节；当前 F407 容量 Flash 524288、main SRAM 131072、CCM 65536。ESKF 第一批同配置基线 Flash 302268、SRAM 99880、CCM 64296：本批 **Flash +24，SRAM 不变，CCM -840**。实际 linked `s_work` 为 3140，地址 0x1000D898；NM/sections 全输出和 ELF hash 在 `linked_resources.json`，最后 artifact hash 以 `final_eskf_artifacts.json` 为准。

ESKF 普通 SRAM spare 31192=30.46 KiB=23.80%；CCM spare 2080=2.03 KiB=3.17%。按最新纯建议颜色，SRAM 绿、CCM 红（<10 红、10..20 黄、>20 绿），不会因此改变生成成功状态或宣称安全。KF6 普通 SRAM 22.73% 绿、CCM 15.42% 黄；Pure INS 二者均绿。

所有现配置任务数组共 27648 字节，包含在链接静态占用中；当前 linker 另在 main SRAM 保留 `_Min_Stack_Size=0x400` 的 main/MSP 区域，heap=0。Task report 的 configured/known estimate 是已有工具范围，不是 SRAM spare 推出的栈裕量。KF6 Estimator 4096/3244，ESKF 4096/2520，Flight 4096/3600，Serial KF6/ESKF 6144/4944。未增加新栈分析器，也未缩栈。

**真实 MSP 主流程/中断嵌套、库调用边界、FPU context 假设、硬件 high-water mark、STM32 WCET/5ms 峰值仍 NOT PROVEN**。现有 .su/linked call 检查通过不能取代这些证据；Host CPU 时间不转换 MCU 最低频率。5ms 对 72/84/100/168/180 MHz 的 360k/420k/500k/840k/900k cycles 只是可用预算，不是测量成本。

Kernel state/work 单体 ESKF 为 992+3140=4132 字节（不含配置、replay、库、栈及业务）。生产 ESKF history 16992、body history 12288、window 184 都另计。上表是完整固件，不是最小算法内核，也不是任一新 MCU 的可用性/最低主频证明。KF6/INS 独立 kernel Flash 下界本轮未测，后续研究不挡住 GUI 轮。

## CCM 最小放置方案：仅评估，未实施

现有 `platform_memory_target.h` 通过 `PLATFORM_CPU_FAST_DATA/BSS` 集中标记 CPU 快内存；F407 映射到 `.ccmram_data/.ccmram_bss`。平台 API 默认空宏，故其他目标可按能力回落普通 data/bss。`PLATFORM_DMA_ACCESSIBLE` 独立映射 `.dma_bss`；F407 `PlatformMemory_IsDmaAccessible` 拒绝 CCM。启动汇编明确 copy CCM data、zero CCM bss；linker 提供对应 start/end/load symbols。

- 有足够普通 SRAM 的无 CCM MCU：新 target 明确把 CPU_FAST 宏映射到常规 data/bss（或专用 CPU 段映射到 SRAM），并同步 startup copy/zero symbols、RAM容量/DMA边界、artifact 容量表及验证。不运行时搬移/动态分配。现 F407 不能全量这样回落：ESKF 合计 163336 字节，超过单个 128KiB main SRAM；这个合计只是容量必要条件，不包含新布局 padding/MCU port 额外差异。
- 保留 CCM 的选择性策略须区分 hot/cold 段或给对象独立段，不能只关全局 CPU_FAST 宏。s_work3140、s_history16992 是数值/回放频繁访问对象，暂保留；CCM 性能获益尚未做 MCU 实测，不能报加速倍数。s_window184 太小，不值得单独为颜色迁移。
- `s_io_baselines`4864 是 CPU 配置/IO baseline 候选，若后续确认全链无 DMA 指针逃逸、任务归属和 copy/zero 正确，可独立映射主 SRAM。按当前符号大小估算，ESKF CCM spare≈6944(10.60%)、主 SRAM spare≈26328(20.09%)，alignment 可能有细小变化。这只是方案，**本轮未移动、未验证新布局**。`s_estimator`10232 混合运行与准备状态，不能未经访问/并发审阅整块称作冷数据。
- 任务栈/TCB 必须保留现配置和调度/FPU/上下文条件；DMA buffers、logger/serial storage 不移 CCM；此次不追求 6.4KiB 数字。

## 收口与剩余

第一批真实 UART/JY 停止/重启/波特率恢复失败路径已提交 `42d4203`，报告保留在 `../pot_firmware_closeout_20261001_stage1_v1/REPORT.md`；本批仅完成上述有限 ESKF 优化及对照，不扩展共享生命周期协议。所记录 KF6 软件自动检查通过，不能据此声明全部 firmware 契约审阅、硬件外场、飞行资格、导航准确度或最坏时间完成。

ESKF 可选项的 CCM 紧张、回放峰值和硬件资格不单独成为 KF6 软件门禁；两者共享的软件缺陷仍应统一处理。现未发现本批新增的共享缺陷。整个目标零候选阻断与 GUI 命名/磁力计等按下一轮授权处理；跨区迁移、MCU移植和最低主频测量留待后续。此处停止新增优化，交回父线程开展已授权 GUI 轮。

执行时四个 kernel/header/test 文件的 raw bytes 保存于 `source_raw/`；`final_source_sha256.json` 同时记录执行时与 Git blob 的 SHA。Git 原有 text 规则归一 CRLF→LF，已逐字节验证除此之外没有差异；证据目录禁用归一，全部完整输出的 hash 保持原字节。
