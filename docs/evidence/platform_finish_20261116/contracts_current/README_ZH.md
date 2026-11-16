# 最终源码的普通生成与严格栈复验

共享 CRT helper 的原样抽取发生在旧默认 E、E19 B 生成之后；旧保护 ZIP 仍是其实际时代证据，不能作为当前生成 authority。因此从冻结的当前 SCG 源码重新正常生成默认 F407 和 E19 Flight，完成真实双配置 ARM 编译链接、产物检查和严格栈门禁；**12 个门禁全部退出 0**。没有修改生产源码、工具规则、例外、预算或病例索引，没有增加病例。

| 当前工程（独立新路径） | 正常生成时间 | Release / Debug | 与旧 E/B 的实际产物比较 |
|---|---:|---|---|
| `.work/pf1117/current-f/Flight_Controller` | 24.51 s | 各 `all`、`artifact-check`、`stack-report` 通过；6 项累计 207.317 s | 每配置 510 个封印编译产物完全一致；加 BIN/HEX 后完整 512 文件集合及 SHA 也完全一致 |
| `.work/pf1117/current-e19-c/Flight_Controller` | 38.88 s | 各上述 3 项通过；6 项累计 191.538 s | 每配置 504 个封印编译产物完全一致；加 BIN/HEX 后完整 506 文件集合及 SHA 也完全一致 |

全部 C/H/ASM、linker、`.mk` 和 Makefile 与旧 E/B 原字节相同。默认 E 到当前 F 的差异仅为最新 generation receipt/组件锁、病例索引及新增已审 H7/E19 病例、checker 封印和 CRT helper；E19 B 到当前 C 仅为 generation receipt/组件锁及 CRT helper。精确差异列表和完整生成文件哈希在两个 `*-generation.json`，没有用旧目标文件替代实际新构建。

默认 F 两配置分别使用原 `platform-catalog-20261116-f4-{Release,Debug}`；E19 C 使用原 `platform-e19-20261116-f4-{Release,Debug}`。原 30-case 软件封印索引未改。四份实际严格报告均为有限范围 `SOFTWARE BOUND PASS`，MSP 上界 1,932 / 保留 2,304 字节，余量 372 字节。完整任务、异常、中间输入及工具身份保留在 `reports/` 的原始报告与 [CURRENT_RECEIPT.json](CURRENT_RECEIPT.json)。硬件测量、WCET、整机语义关键合同及飞行资格没有因此得到证明。

## 当前状态与真实应用消费

正常业务入口 `TargetGeneration_Apply(..., TargetScope.FLIGHT)` 使用当前 catalog 和模型 reconciliation，不绕过准入。默认模型延续 `ReferenceProject_Create("GuiConvergence_f4")`；E19 延续已有明确合成 wiring fixture，新建输入独立于旧输入。两次 reconciliation 的规范 Flight 配置均未改变。

对原始模型、生成后保存模型和重新打开并 reconciliation 的模型，`ProjectTargetGenerated_IsCurrent` 均为 true。构建结束再读 saved/reopened 模型也为 true。两份 source snapshot 在生成前后、构建完成后均无变更；新合成 CubeMX 输入字节不变，构建输入检查 `changed=[]`。当前应用 `ArtifactStackReportSummary_Encode/Decode` 实际接受四份新的严格栈报告并保持 `passes=true`。

这是**当前源码运行的 SCG 业务 API** 验证，没有进行桌面鼠标测试。将来 frozen EXE 按其可执行文件哈希拥有独立 generation authority，不能将源码入口的 authority 当作那个 EXE 已生成的收据；它应正常生成自己的工程。

## 证据与重放

- [generate_current.py](generate_current.py) 的 `default`、`e19` 两次执行均退出 0；新目标/输入/收据必须不存在，拒绝覆盖。完整生产源及 fixture 哈希、当前组件锁和模型在两个 `*-generation.json`。
- 实际命令使用原 [run_validation.py](../contracts/run_validation.py)，参数 `--replica b`（此模式要求所有 6 门禁成功）；两组逐命令完整输出、工具路径、退出状态和输入稳定记录在 `current-f-build/`、`current-e19-c-build/`。
- [compare_current.py](compare_current.py) 退出 0，读取旧正式产物摘要及已独立验收 ZIP 旁完整清单，比较新实际对象/依赖/`.su`/ELF/MAP/BIN/HEX，核对整个编译产物路径集合，并调用当前应用报告消费及 current 判断。
- [EXECUTION_RECEIPT.json](EXECUTION_RECEIPT.json) 保存运行工具、脚本身份及外层退出状态；两个新工具 Ruff 通过。这里没有新执行完整 Host、Power10 或 analyzer：它们先前已执行的结果仍按 [原报告](../contracts/README_ZH.md) 对应时代陈述，不与本次 12 项拼成未运行的全套。

旧两个保护 ZIP 永不覆盖。旧构建比较现已结束，原有限清理资格仍由根代理逐文件复核；本次新 `current-f` / `current-e19-c` 工程不属于那个旧清单，当前继续保留。本批没有删除、暂存、提交或硬件操作。源码基线 HEAD 只是记录，实际 dirty 输入通过本批完整 raw snapshot 审计，不冒称干净提交。
