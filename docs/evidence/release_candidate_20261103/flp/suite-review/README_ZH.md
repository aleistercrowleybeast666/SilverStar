# FLP 测试覆盖与未通过项 · 2026-11-04

## 原收集范围

初始收集 **1,953** 个唯一 pytest node ID。四段运行覆盖了全部原始 ID，没有重复启动任何原始节点。每个节点只按其首次执行分类。**1,678 通过、155 错误、85 失败、32 跳过、3 未完成，未开始 0**。各段均退出 1。没有一次完整运行通过。此前的 1,952 项单独收集早于参数名与实录数值隔离测试加入，以首段实际收集列表为准。

分类顺序为未完成（已开始且无 finished）、错误（setup 或 teardown 失败）、失败（call 失败）、跳过、通过。某节点同时在 call 和 teardown 出错只计一次“错误”；pytest 文本摘要中的阶段计数会与逐节点计数不同。[互斥统计与逐文件分布](nonoverlap-summary.json) · [各未通过节点、阶段和错误](nonpasses.json)

| 段 | 启动 | 通过 | 错误 | 失败 | 跳过 | 未完成 |
|---|---:|---:|---:|---:|---:|---:|
| full-bounded-1 | 1,525 | 1,288 | 140 | 72 | 24 | 1 |
| continued-1 | 109 | 107 | 0 | 1 | 0 | 1 |
| continued-2 | 1 | 0 | 0 | 0 | 0 | 1 |
| continued-3 | 318 | 283 | 15 | 12 | 8 | 0 |

首段收集之后、时间栏源码修改之前记录了 FLP 文件摘要，仓库 HEAD 为 `72adf71d`。该进程已载入修前的 MainWindow。后面三段在 HEAD `4b822087` 上单独运行，包含时间栏修复 `a632486e`，使用真实本地 SCG 根与 GCC。独立复测结果都保留各自源码与配置范围。原三项未完成不会用隔离结果回填。

## 未完成的三个首次执行

1. `test_project_excludes_analysis_only_diagnostics` 在 150 秒内未返回，首段因此退出。单独以 75 秒看门狗复现时，调用栈位于 `_Project_Write` 的 `_Error_Show`，弹窗一直等候确认。测试的假 decoder/工程身份被正确拒绝为 `parse_cache_source_identity_invalid`。现在负例明确验证该错误和项目文件未生成。正例改用原始不可变配对，仅将派生测量用于 analysis-only 计算。通过私有 `_Replay_ResultSet` 注入未经正常重算入口登记的诊断结果后，保存仍拒绝 `project_result_input_identity_mismatch`。原基线 `8a25f99e` 和当前库上同因。未修改生产策略或重写身份。
2. `test_reader_rejects_nonregular_or_reparse_before_open[fifo]` 的故障注入拦截全局 `Path.open`，原监控器写 phase 日志时也被它命中。
3. 同一测试的 `[reparse]` 分支遇到相同拦截。独立证据输出改用 `io.open`，保留测试对产品的完整 Path.open 拦截，两项独立运行均通过。

原无头测试的两个进程及保存提示栈保存在归档中。核实 PID、父进程、解释器、完整 pytest 命令后，仅终止了这两个测试子进程。`test_joint_gui_state.py` 的范围检查现在用 `before_close_func` 处理失败时遗留的合成草稿。真实四项断言显示打开日志后概览页错误地显示了时间栏。基线四项均同样失败。正式产品 `a632486e` 修改后有单独验收，首段的旧结果仍为失败。第一次续跑命令超出 Windows 长度限制，压缩包中保留了 `WinError 206`。实际续跑通过 pytest `@参数文件` 精确列举未开始的节点。

## 正常用户路径

普通路径通过 `Replay_Execute` 写入实际输入和引擎身份。独立短路径的 6 项测试全部通过（99.58 秒），包括多算法和独立 what-if 数值往返、真实 GUI 还原多次运行、复用有效的解析缓存、后台打开在有效/缺失/异常缓存状态下的行为。另有最终便携 EXE 的独立桌面试验，保存保留了解析缓存。关闭第一个进程后，第二个 EXE 重新打开 `HostCandidate.ssflp`，精确匹配并显示原来的 40,080 条记录。[实际保存](../../packaged-gui/final-flp-save.state.txt) · [新进程重新打开](../../packaged-gui/final-flp-reopen.state.txt)

本轮 decoder 目录修复 9 项、实际记录磁旋转 7 项、任务快照 GUI 4 项在各自原始执行中全部通过。其他非通过项涉及不同原因，含缺少 KF6 算法 revision、旧测试对象缺少 devices/metadata，以及专门的源或实录前提。七个旧失败样本已与改动前源码分别比较。[七例基线对照](../baseline-review/README_ZH.md)

## 明确环境后补测

- 提供本机 `SILVERSTAR_FCCG_ROOT` 和真实 GCC 后，current-native parity / horizon 两文件独立 31 通过、2 跳过，后者要求另外提供精确 KF/ESKF 实录与 decoder。KF6 horizon 完整文件独立 63 通过。
- 从实际 SCG 生成和运行的 KF 板端算法 Host 测试 24 项通过，获得 O0/O2 的新鲜帧。匹配生成工程后 FLP 12 个 KF 案例通过。ESKF Host 夹具链接缺少 `SystemMissionProcess_LoggingActiveGet`，32 个 setup 报错，FLP 没有拿到新鲜 ESKF 帧，12 个对应案例仍为错误。这批补测不能作为实际飞行或对原始全套通过的证明。

## 复验和原始证据

从仓库根执行下例。临时目录和证据目录应为这次新建的位置。程序保留逐测试 phase 日志、退出码、各段 JUnit 和有界等待。超时段可能无法产生 JUnit，其 JSONL 记录保留实际阶段和最后一个节点。对已归档的结果，先将完整输出压缩包解到含 `summarize_flp_suite.py` 的目录，再执行该脚本可重算逐节点结果。

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:SILVERSTAR_FCCG_ROOT=(Resolve-Path 'apps/SCG').Path
$env:PATH='D:/msys64/ucrt64/bin;'+$env:PATH
$env:SS_FLP_SOURCE=(git rev-parse HEAD)
.venv/Scripts/python.exe -B -u docs/evidence/release_candidate_20261103/flp/suite-review/run_flp_suite.py --repo . --work .work/0.1.3-flp-repro --evidence .work/0.1.3-flp-repro/evidence --tag flp --case-seconds 150
```

[完整日志、节点清单、JUnit、现场过程与命令收据](run-outputs.zip) · [原始文件字节索引](run-outputs-sha256.json)
