# SilverStar 0.1.2 GUI 软件 checkpoint（2026-10-08）

本轮从 `fix/nightly-user-ready-20261003` / `b2fae225155a925dac475a2e95f8b978d76dde99` 继续，保留先前 `a261796`、FLP `cc5fb52`、SCG `5821058` 及后来修改。用户随后要求北京时间 20:10 前停止本机工作，供 20:15 携机离开；本报告是软件 checkpoint，**不是发布、完整安全验收或外场候选**。最终提交身份见 Git；提交内容对应证据目录的源码哈希清单。未 push、未 tag/Release、未连接或操作硬件、未生成最终外场工程。

## 已修改的产品行为

SCG 明确切换轻量/最简时，`project/feature_tiers.py::_FeatureTier_DevicesNormalize` 按当前列表保留每传感器类和遥测的第一实例及原参数，删除后续超额实例，最简删除 GNSS。同步撤下已删除实例的 capability/resource/alignment/AIR 绑定；未知而未删除的来源仍保留给校验拒绝。完整/标准可重新添加，但不会从旧预设恢复删除的设备；算法、参数、协议预设的恢复保持原机制。直接打开旧的冲突工程不自动删设备，仍拒绝生成。用户的新明确切档要求覆盖历史四档文档的“切档保留冲突”行为。

SCG 卡顿的主要证据是同一 GUI 配置事务反复 `ProjectView_Get → VariantResolve → PluginManifest_Parse`，以及反复读取 Board/CubeMX inventory。`plugins/catalog.py` 复用最多 8 个精确设备/目标快照，插件 Scan 或所选 variant manifest 的 mtime/size 变化使缓存失效；无效 variant 仍报错。`resources.py::BoardInventory_ReadScope` 只在一次 GUI 事务中复用同一硬件读取，结束即清空，下一次操作和生成继续读取。显示回滚快照仅在模型对象及完整字典相等时复用；新配置仍执行完整 reconciliation/validation。

FLP 的“处理中”来自计数进度分支覆盖数字格式。`ui/main_window.py::_Task_Progress` 现在同时保留阶段百分比和真实 B/对象计数；`ui/workers.py::_ProgressEmitter_Build` 不因同阶段节流吞掉阶段变化。`core/artifacts.py::_Encoder` 在一次写入内复用同一只读 ndarray 对象的已完成写入；只读视图必须沿有限 base 链确认只读或不可变 bytes，mutable base 不复用。压缩、真实写入/fsync、哈希、写后校验、源身份、取消、原子提交和 GUI 发布保持原契约。没有虚假计时进度，没有自动算法重算。

## 无 profiler 的前后点击测量

同一 FLP Python 3.14 / PySide6-Shiboken 6.10.1 环境、native `windows` 平台、同一实际插件目录、ReferenceProject 完整档、三次添加/删除 IMU；串行执行，没有并行构建。before 是从 b2fae22 只导出的 Python 源码，使用同一当前 VERSION，plugins 为指向本仓库的 junction，没有复制 vendor。原仓库没有回退。计时覆盖真实 QtTest 点击/组合框回调，并另记事件处理时间。

| 操作 | before 三次回调秒数 | after 三次回调秒数 | 中位数 before → after |
| --- | --- | --- | --- |
| 添加 IMU | 14.794 / 13.227 / 12.478 | 0.799 / 1.042 / 1.472 | 13.227 → 1.042 |
| 删除 IMU | 10.645 / 10.764 / 10.425 | 0.861 / 0.706 / 0.787 | 10.645 → 0.787 |

包含随后事件处理的中位数为添加 13.280 → 1.093 秒、删除 10.691 → 0.824 秒。另有 profiler 的同五步约 84 → 8 秒，仅用于定位，不能作为真实点击耗时。after 仍存在约一秒级同步配置处理，本记录不声称瞬时响应。

## FLP 原生生产路径和 9% 阶段

实际输入为既有精确 decoder/Descriptor 下的 mission 000051、10,168 条记录及两个真实 KF6 run，没有重算长日志或 ESKF15。native Windows GUI 通过生产 `_Project_Open/_Project_Write` 保存重开，逐数组比较全部 run。额外 8 个 run 是扩展实际结果数组的**持久化受控样本**，总 10 run、271,843,328 原始数组字节；不是新算法计算、准确性或硬件证据。较大样本保存 39.724 秒，收到 9,188 个真实进度事件。

**9% 的阶段停留仍存在。** 实际两-run 保存的该阶段持续 16.461 秒、3,792 次计数更新、最大相邻进度间隔 0.086 秒；10-run 保存持续 14.958 秒、3,792 次更新、最大间隔 0.095 秒。该阶段的权重不是预计剩余时间，不能伪造均匀百分比。较大保存全程最大相邻进度间隔 0.285 秒；整个 GUI 观察（含载入/展示/故障流程）50 ms heartbeat 最大间隔 1.721 秒，不能据此声称无任何主线程停顿。逐事件阶段、百分比、状态文字、实际字节/对象数及单独统计保存在证据中。

取消及受控磁盘满失败保留旧原子工程且不显示完成；保存中关闭沿既有契约等待提交成功再关闭，不能把“关闭必须取消”当产品要求。重复保存/打开明确拒绝，active worker 不被替换。主源 `replay:kf6:what_if:1`、副源 `replay:kf6:recomputed:1` 保存重开一致，所有算法 run 方法在该探针中设为失败哨兵，仍正常重开。仅配置保存正常完成并载入原日志，零恢复 run、零自动重算；若已选主源指向未保存 run，显示既有 `project_result_recompute_required` 提示，不放松身份校验。

原生探针 v1 错把关闭期望设为取消；v2 错把仅配置工程的手动重算提示期望为空，均保留 FAIL。v3 在核实既有契约后分别断言原子提交完成、明确重算提示及零自动重算，未为它们修改产品逻辑。SCG 探针截图可见控件重叠；其连续手动 `processEvents` 没有明确投递 DeferredDelete，旧动态控件可能尚未退役。停止期限前没有再次运行 GUI 来区分采样与产品布局，视觉布局验收 **NOT PROVEN**，不能把截图当完整视觉 PASS。

## 版本和原门禁

根 VERSION、三应用动态版本来源、SCG 新项目身份为 0.1.2。仅 exact official 0.1.0/0.1.1 项目身份在内存迁移，打开不写输入文件；decoder 引用保持原值。固件 owning `System/User/system_user_config.h` 仅 PATCH `0→2`、LOG_BUILD_TAG `SILV0100→SILV0102`，其他运行参数不变。AIR M0/CMD/ACK、SSLOG 0.0、`.ssdecoder` 1.2、项目 14/15/16/17、插件 ID、兼容包/路径、vendor 和算法独立版本不随产品补丁统一改号。旧 decoder/日志/报告没有改写。

一个独立软件代表性 F407/KF6/full/Delay10 工程从既有 formal 配置生成，**不是外场配置决定**；不猜引脚或开伞策略。正常再生成保护用户源，不能据新模型版本认定旧用户 payload 或二进制已升级。

| 检查 | 本轮结果/边界 |
| --- | --- |
| SCG 最终相关配置/缓存/四档/栈单元批次 | PASS：48 项，71.03 秒；追加 exact 版本头/未知修改拒绝栈批次 PASS：16 项 |
| SCG 较早四档/日志边界批次 | PASS：101 项；之后显示缓存相关批次 PASS：65 项，各自源码时点见日志，不能拼成未执行的全套 |
| FLP 同进程相关 GUI/进度/工件/worker 回归 | PASS：44 项，300.83 秒 |
| 000051 native 两-run、10-run、大样本、取消/关闭/错误 | PASS：上述明确范围；主副源及重复操作的补充 native 探针 PASS |
| 架构 | PASS：原 emitted architecture-check，356 checks，批准头来源后重生成检查工具再执行 exit 0 |
| Power10 | 文本 PASS：6329 checks、111 first-party C、2761 函数、1675 heuristic candidates、815 非阻断建议；critical-contract manual review **NOT PROVEN** |
| ARM all/artifact/memory | PASS：实际 ARM GCC 14.3 rel1 编译链接，之后再生成复用构建检查 exit 0；不是语法检查 |
| static-analysis | PASS：真实 GCC `-fanalyzer` 编译/链接 exit 0，完整日志保留 |
| Host | 初轮 FAIL：70/80 console 硬编码 0.1.0；owning 测试改用 system_version.h 宏，fixture 同步后完整 PASS：80 executables / 4,446,469 checks / 0 failures；11 compile-pass、18 expected rejection、8 not-applicable 保留 |
| 栈 | **FAIL exit 2**：最初拒绝未知版本头；用户批准唯一 header hash 后仍拒绝 Generated/Src/project_metadata.c，未扩大名单 |
| monorepo 全文件批次 | **FAIL**：70 PASS / 2 FAIL，旧 evidence before_decode_table.md 缺 AIR_CALIBRATION_CONTRACT.md 链接及本机 apps/FLP/.venv 存在；没有删历史证据、环境或改测试消除失败 |
| 新完整四档全套/全部 GUI/全目录文档链接复测 | NOT_RUN：按停止期限停止扩展；当前修改文档的链接另做静态核对 |
| 历史 FLP native abort 的精确根因闭环 | FAIL / NOT PROVEN：先前菜单生命周期缺陷已修复并有对应证据，不能据新探针通过断言旧 abort 已获原生 dump 归因 |
| 0.1.2 上板/硬件时序、完整手工关键契约、飞行资格 | NOT_RUN / NOT PROVEN |

唯一批准的新 header 归一化 SHA-256 是 `ffb28f9bf8e08e73c80a16c1121e8c37954f7bb7ade95f2aa47a5226787cc840`，owning proof v12 与 reference overlay 只追加这一项，旧名单和阈值不变。追加测试确认其他 patch 或 gravity 改动仍拒绝。

栈新增阻塞 `Generated/Src/project_metadata.c`：旧 reviewed SHA `ae4706ff828b966e517972f147eee2d5ca938a144ff437ef3b71d32a9f186181`，新 `bba3aed1cc73043a10cfd126a7759728a10de53e3769e2563fb209a4b12feadf`；逐行仅 `SILVERSTAR_PROJECT_CONFIG_DIGEST 0xA79E2E92UL → 0x42A4C1C6UL`。这是独立 compiled input，**未经批准，未登记**；继续前应核对新模型 identity/digest 变化，并盘点全部其他未知编译输入，不逐个包装成版本头批准。

## 证据和继续顺序

[证据清单](evidence/gui_0_1_2_20261008/manifest.json)保存命令脚本、完整失败/通过日志、真实进度、配置与源摘要、工具版本、输入及工件哈希。大型 .ssflp 数据及构建仍在 `.work/gui012_20261008`，未为交接复制 vendor 或数据大包。三个 `work_*_20261006` 盘点文件保持未跟踪且原哈希不变。

可复现命令路径见证据脚本，Python 为 `apps/FLP/.venv/Scripts/python.exe`；测试 runner 复用 pytest-qt，但保持 FLP NumPy 2.4.1 / Qt。测试使用 workspace 内普通目录及私有 decoder/settings，未改 ACL/沙盒；禁用 cacheprovider 的已知 `Unknown config option: cache_dir` warning 完整保留。部分探针在私有路径准备或错误 node-id 阶段失败，未产生对应 PASS；缓存单元曾直接改 session fixture 导致污染，改为 monkeypatch 自动恢复后重跑 48 项通过，失败日志保留。

后续最小步骤：核对 checkpoint 和本清单；审核独立未知 digest 来源，未经明确批准保持栈 FAIL；在正常事件循环下重验 SCG 布局和三次添加/删除；复测四档新/旧工程、资源、算法参数、日志及保存重开；确认 config-only 的缺 run 提示可用且无自动重算；选定真实硬件/四档/校准/部署配置后另行授权静态验收。最小静态检查为执行机构物理隔离、供电与设备连接确认、精确生成配置/decoder/二进制绑定、M0 权威 READY、一次有授权的记录、普通日志损失与导航丢样区分、TF 完整性及全 run 重开。旧 28b/000041 或 000051 不能冒充 0.1.2 上板结果。

阅读順序仍为[用户流程](USER_WORKFLOW.md) → [硬件与四档边界](SilverStar_Recommended_Configurations.md) → SCG/GSHC/FLP → [四算法数学与实际实现](algorithms/NAVIGATION_IMPLEMENTATION.md)：该章第 1 节坐标/单位/初始化，第 2 节纯惯导，第 3 节 SF6 固定增益，第 4 节 KF6，第 5 节 ESKF15 误差约定及实现，第 6 节调度/时间戳/失效边界。数学冻结，本轮未借文档改算法。H7 无当前 builtin 支持、F407 ESKF15 运行失败、F103/NRF 未实物验收、Logger RET6 指定配置范围、无 GNSS 水平漂移和 20% RAM 建议均保持原边界。
