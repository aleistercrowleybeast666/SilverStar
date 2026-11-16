# 关键合同、依赖拒绝与精确静态栈证据

本批从 `d52854c4a7b12c79dbb06cf967006e599103d24e` 的实际工作区继续。
构建使用各次生成时冻结的源码，不能把基线 SHA 当成没有修改的最终源码身份。
`runs/*generation-source-snapshot.json`、每批 `generated-inputs.json`、完整命令与
`input-stability.json` 分别记录输入时代、生成文件及运行期间是否变化。
最终提交由根代理统一处理；本批没有提交、推送、刷机或物理操作。

## 已闭合的有限软件合同

[REVIEW_ZH.md](REVIEW_ZH.md) 给出调用者、所有权、错误传播和具体未证明边界。
Logger 的真实缺陷是在完成报告元数据校验前已经发布首条记录。本次 owning payload
在首次发布前验证容量及 completed/passed 域，普通未完成、设备失败和存储失败路径保持。
旧真实 C 的三种损坏输入确实失败，修复后同一八项期待全部通过，且使用真实 GCC
`-fanalyzer -flto` 编译与链接，不是语法检查。

另外，增广估计器关闭 SSLOG 原来通过 Python 校验却在 ARM 缺头。本次在工程校验和
直接 source graph 入口精确拒绝该不支持组合，写输出前结束，原模型不变；没有暗中启用
日志，也没有修改数学 C、参数 ABI 或 TreeDiagram SDK。

Source selector、mission/runtime 和 SPSC 的结论只覆盖审阅表中列出的入口与原用例。
整个固件的每个关键语义依然 **NOT PROVEN**；原样 Power10 文本明确保留此结论。
最终默认 E 的扫描为 128 个第一方 C、7180 text checks、1014 条非阻断建议；最终 E19 A
也是 128 个第一方 C、7040 text checks、1011 条建议。建议数和候选密度不是语义证明，
这两份原始日志均明确输出 `Critical-contract review NOT PROVEN; manual acceptance pending.`

## 构建时代与结果

| 时代 | 实际输入 | 实际结果与后继关系 |
|---|---|---|
| pre | 原 Logger | 正常独立生成；三损坏用例失败、其余五项通过 |
| A | 六行 Logger 修复 | Release ARM/artifact/architecture/P10/真实 analyzer 通过，Debug ARM/artifact 通过；两配置严格栈正确拒绝未审阅的新输入 |
| B | 独立正常生成，纳入 A 的人工审阅 case | 两配置 ARM/artifact/strict 全通过，逐配置 510 个产物与 A 完全相同 |
| C | 后续三 storage owner 的 E19 module-2 reader | Release ARM/artifact/architecture/P10/真实 analyzer 通过，Debug ARM/artifact 通过；严格栈先拒绝旧 seal。完整审阅后保留该时代 case |
| D | 共享对象目录加入 E19，使 decoder 的 16-byte profile 身份变化 | 两配置 ARM/artifact 通过，旧 C seal 严格拒绝。Release 额外 architecture/P10/真实 analyzer 均通过；没有将该失败回填成功 |
| E | 最终目录与 reader 冻结后的独立正常生成 | 两配置 ARM/artifact/strict 均通过；逐配置 510 个产物与 D 完全相同。最新原样 architecture/P10/真实 analyzer 全部通过，九项完整命令已结束 |

C/D 的唯一本地源码差异是 `Generated/Src/project_log_decoder_profile.c` 常量。
[实际比较](runs/c-d-linked-instruction-comparison.json) 记录两 ELF 的所有不同字节位置、
常量出现位置与解析器身份；实际函数指令行没有变化。该比较没有屏蔽字节或代替 seal，
D 的新 case 仍绑定完整真实源、对象、ELF、工具链与 runtime 输入，再由 E 独立复现。

[最终资源与产物摘要](runs/final-artifact-summary.json) 来源为 E 的实际 memory/stack JSON。
默认 F407 的 MSP 保留 2304 bytes，保守上界 1932，余量 372；各任务最小余量为 Idle 256。
这些是精确构型的静态界限，不是 MCU 高水位或 WCET。RAM/CCM spare 不替代栈证明。

## 最终 E19 独立构型

整文件审阅发现 `Sx1278TelemetryInstance_NameGet/InfoGet` 把 E19 报告为 E32 的真实错误，
已由无线 owner 保留前失败并修正。根代理最终 249 项真实 Host/注错/ARM ABI 组见 radio
证据；旧错误名称时代的 74 Host 结果不用于替代新身份的验证。

本批随后正常生成 `contract-e19-a`，两配置实际 ARM/artifact 通过，Release
architecture/P10/真实 analyzer 均通过，严格栈先正确拒绝旧 case。手工审阅完整 source
graph、167 C、导入 Core/FATFS 差异、11 个实际 UART/SD DMA BSS 对象和每个 linked callback
slot，再追加精确病例。独立正常生成的 `contract-e19-b` 两配置 ARM/artifact/strict 全通过；
逐配置 **504 个完整产物与 A 完全相同**，见
[E19 最终摘要](runs/e19-final-artifact-summary.json)。没有把默认 E28 case 外推到 E19，
没有过滤 profile bytes、改 CubeMX 原输入或增宽 callback/栈例外。

根代理在这个最终 A 工程另外完成了实际完整 Host suite：74 executables、5,508,837 checks、
0 failures，12 compile-pass、17 expected compile-failure、23 not-applicable，mandatory storage
4/4；711.62 s，生成输入前后不变。[完整日志（gzip）](../radio/e19-final-full-host-tests.log.gz) 与
[命令/输入收据（gzip）](../radio/e19-final-full-receipt.json.gz) 单独保留。
解压日志 SHA-256 为 `f207569d1a1948c0c458297f1a193dd711654c170580bf7150f3d98f6d92edb8`。
它对应最终 A/B 相同编译闭包，不沿用旧错误名称时代的 Host 通过。

三 GPIO、内部 DIO4 前端、SPI1 128 分频与 reset OD 上拉是明确的合成接线，不能称硬件通过。
该构型的 Ground 由板卡代理独立验证，本目录的 F407 Flight 证明不涵盖 F103 Ground。
SSFC1.0 H7 的两个 N 精确病例也仅在完整源码/对象/IRQ 复核后合入；它们的独立重生与
全部板卡门禁由 boards 证据负责，不与本目录默认 F407 计数混合。

## 原始失败与测试范围

| 运行 | 精确结论 |
|---|---|
| `logger-before-v2` → `logger-after` / `logger-final-c` | 3 failed + 5 passed → 8 passed；后者是最终 reader C 生成输入上的重新执行 |
| `journal-before` | 3 failed + 4 passed，真实不支持组合原来未拒绝 |
| `existing-host` | 原 navigation/queue、selector、mission 组共 74 passed |
| `selected-host` | 实际生成的七个 Host executable，2,109,308 checks、0 failures，mandatory storage 4/4；不是完整 Host suite |
| `mission-runtime-b` | 原测试文件的十个未改场景和断言，以 B 实际生成 C 编译执行全部 0；不是该 pytest 文件整文件通过 |
| `thumb1-before` | 13 个实际 C071 机器码夹具全部被旧解析器拒绝 |
| `thumb1-contract-v1` | 159 passed，包含原 125 项和 34 项真实 Thumb-1 正常/篡改边界；对应当时索引，保留原时代 |
| `manifest-new-cases-before` | 1 failed + 15 passed，旧固定索引 SHA 正确拒绝新增 case；没有删除历史二十项完整等式 |
| `final-contract-tests` | 最终 30 项 case 索引下，一次完整 167 passed / 40.17 s；上述 159 项加八个真实 Logger 正常/损坏用例，使用 E 实际生成的 logger/codec/decoder，不把早前失败回填 |
| `journal-final-style` | 板卡 owner 后续只对 C0 source-graph 条件作等价样式合并后，独立七项依赖准入回归全部通过 / 12.83 s；没有把它拼接或回填至此前 167 项源码时代 |

所有初次夹具/诊断错误也保留：`logger-before` 是链接夹具缺 LTO，`stack-interface`、
`stack-baseline` 等区分历史合成 fixture 和新完整输入检查，`journal-after` /
`contracts-python-final` 是测试构造参数错误；`thumb1-switch-candidate` 是解析器开发中失败。
这些失败不会被最终通过覆盖，也不拼接成未执行的“全仓通过”。完整状态见相应 `.exit`、
JUnit、原始日志；E19/H7 case 的追加结果在同目录收据单独列出。新测试/正式重放工具 Ruff
通过；五个改动生产 Python 文件另做完整 Ruff 诊断与原始提交对照，原有非零问题保留，
不声称全仓 lint 通过。`ruff-baseline-comparison.json` 区分旧诊断与并行新增的 C0 分支样式提示。

## 重放与保留

普通构型由 `apps/SCG/tools/validation/generate_stack_review_cases.py <新目录> --case f4`
生成。`run_validation.py <Flight_Controller> <新日志目录> --replica b` 执行两配置六门禁；
`--extra` 在该不可变工程执行 Release architecture/P10/真实 analyzer。
`inspect_case.py` 只捕获未准入候选及诊断，绝不自动批准 case；新增 case 需要另行全输入审阅。

`generate_e19.py a|b` 为明确的合成接线建立各自只读输入和独立生成目录，不能代表真实 PCB。
本任务新建的 `.work/pf1117/contract-e19-*` 由本批拥有；原始 CubeMX 输入、日志、decoder、
模型和正式证据都不是清理对象。`archive_evidence.py` 只按清单复制，拒绝覆盖不同字节，
没有删除操作。`executed-runner-snapshots` 是先前已执行命令的原始文本快照及哈希；当前
正式 `.py` 重放工具保持可执行，不以改扩展名逃避检查。

仍缺真实任务/ISR 时序、MCU WCET/高水位、物理 RF/UART、DMA/cache/掉电、接线、传感器
精度及飞行资格。全局语义审计、任意配置静态界限也没有在此宣称完成。
