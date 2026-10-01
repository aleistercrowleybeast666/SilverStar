# 检查器正确性、F Prime 参考口径与旧 FCCG 核查

本批基于 `e8ea807f5a9fc3e09ff54826cff92220ede41952`，按用户 2026-10-01 07:45 UTC 的最终决定实施 F Prime-inspired 项目适配。修改范围只有检查器所属 Core payload、其回归测试、AGENTS、编码标准及本批证据。没有固件 C/H/链接脚本语义修改，没有改变功能、数据、返回类型、事件、运行时断言或第三方例外。没有发布、刷机或生成用户最终外场候选。

## 实际修复

1. Windows PowerShell 5.1/.NET 的文化相关 `StartsWith(BOM)` 对无 BOM 文本也可能返回真，旧代码因此删除首字符，污染首函数的起始行与代码行数。改为首字符精确比较，验证 LF/CRLF、带/不带 BOM 四种输入。
2. 函数扫描只删除预处理首行，跨行宏的后续物理行可能被当作函数声明或计入下一函数。现在删除完整跨行指令，保留物理行位置；宏的规则检查仍看到原先的完整净化文本。没有扩大扫描路径或例外，也没有执行条件预处理。
3. 外层括号按配对边界移除；窄范围指针强制转换还原后，固定地址不会获得候选计分。显式空指针比较与同一运行时对象断言去重。没有尝试用文本证明任意 typedef、别名、支配关系或语义等价。
4. 顶层 `1 || runtime`、`0 && runtime` 等明显常量条件不计分；括号内的部分常量、数组索引和三元表达式不误当作整个条件恒真/恒假。
5. `count <= sizeof(array)` 等运行时容量条件不再被一律拒绝。仅在识别纯常量条件时替换 `sizeof` 操作数；原条件仍用于去重和调用筛选。不是对任意 C 表达式或可变长数组语义的证明。

新增正确性回归在原检查器上 **32 失败、2 通过、48 未选中**；原始完整失败日志保留。修复后中间版本 82 项通过，授权口径修改后中间版本 84 项通过；最后加入嵌套条件和其他规则拒绝用例后 **91 项全部通过**。中间结果没有拼接成未执行的全套结果。最终回归继续拒绝动态分配、有限 while/do、未授权永久循环和函数指针；旧路径、条件编译、BOM、编码、常量等既有回归也包含在 91 项中。

## 官方基线与适配边界

固定上游提交为 `4b58f3666fe4ca8a3cacd389aed5faf1fb32b063`，六个官方文件的 URL、字节数及 SHA256 见 [fprime_source_baseline.json](fprime_source_baseline.json)。读取的是官方公开源码，没有运行 NASA CodeQL，也没有把远端技能文件作为本仓库操作指令。

[F Prime 密度查询](https://github.com/nasa/fprime/blob/4b58f3666fe4ca8a3cacd389aed5faf1fb32b063/.github/codeql/fprime-queries/FprimeUseOfAssertionsDensity.ql) 的严重程度为 recommendation：针对超过 10 LOC、没有断言的函数，并处理 enum/bool 返回、WARNING/FATAL 事件、static_assert、GTest、断言设施、未实例化模板、构造/析构等情况。这些是 C++/CodeQL AST 判定，不能直接等同本项目物理代码行和正则候选计数。

其 [pack 2](https://github.com/nasa/fprime/blob/4b58f3666fe4ca8a3cacd389aed5faf1fb32b063/.github/actions/codeql/jpl-standard-pack-2.yml) 排除密度查询，将该项移到 [known-autocode-issues 配置](https://github.com/nasa/fprime/blob/4b58f3666fe4ca8a3cacd389aed5faf1fb32b063/.github/actions/codeql/jpl-standard-known-autocode-issues.yml)。[工作流](https://github.com/nasa/fprime/blob/4b58f3666fe4ca8a3cacd389aed5faf1fb32b063/.github/workflows/codeql-jpl-standard.yml) 对此配置实际过滤 build 路径；不能说 pack 2 自己执行了密度项，也不能只看 paths-ignore。SilverStar **没有复制这个生成代码排除**，原有第一方生成路径继续扫描。

| 官方处理 | SilverStar 本次处理 |
|---|---|
| >10 LOC、无断言 recommendation | >10 非空非注释物理代码行、零运行时候选，非阻断审查提示 |
| enum/bool 返回与 WARNING/FATAL 事件 | 不靠名称/类型文本自动豁免；人工核查失败原因、返回值使用、事件语义与故障后状态 |
| static_assert | 人工核查其编译期证明覆盖什么，不能替代运行时生命周期和外部输入校验 |
| GTest 与断言基础设施 | 人工分类测试期契约及 fail-stop 基础设施；不为减少提示改变代码 |
| 构造/析构、未实例化模板 | C 固件不对应这些 C++ 类别；不添加类似豁免 |
| 自动生成代码密度过滤 | 不引入；第一方模板和生成结果保持现有完整路径覆盖 |

全函数均值和 >20 行子集均值仅作信息。关键契约缺失、未处理可失败操作及故障路径仍阻断人工验收；尚未完成审查也不能称验收完成。工具每次明确输出 `POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending`。短函数仍需关键契约审查。F Prime 的 [CPP-4 指导](https://github.com/nasa/fprime/blob/4b58f3666fe4ca8a3cacd389aed5faf1fb32b063/.github/skills/fprime-cpp-design/SKILL.md) 区分内部编程错误与地面/硬件输入错误；坏包、超时和存储容量不足保留普通错误处理，不全部改成致命断言。

## 本批可复查结果

配置 SHA256：`b819099f75eaf596f87679adf324d7afbb609c33ece34edd9850ec92b5a98313`。使用独立 `.work/PoTCheckerCorrectness_e8ea807_20261001_v1/after`，生成检查器与 owning payload 的 SHA256 相同。逐文件 C/H/LD 哈希与上一完整固件批次完全一致。

| 目标 | 文件/函数 | 候选/全函数均值 | >20 行函数/候选/均值 | 零候选 >10 行提示 | 文本检查退出码 |
|---|---|---|---|---|---|
| Flight | 108 / 2605 | 1595 / 0.612284 | 971 / 1419 / 1.461380 | 740 | 0 |
| Ground | 15 / 148 | 106 / 0.716216 | 38 / 80 / 2.105263 | 34 | 0 |

Flight 候选由此前只读审计的 1591 变为 1595，Ground 106 不变；这是计数器正确性变化，不是新加断言。函数总数仍为 2605/148。按**当前一对象一候选算法**计算 >20 行且候选<2 的信息数量为 498/4；它与历史一对象计两项算法的 171/0 不同，不能称“171 个真实缺陷已全部修复”，也不能把不同算法数字直接做消减统计。历史门槛报告保持原状。

Flight 架构检查 328 checks / 0 failures，退出 0。最终 pytest 91 passed，退出 0，Windows PowerShell `5.1.26100.9444`，Python `3.14.0`，GNU Make `4.4.1`。原始命令、退出码、时间、源快照、配置、日志哈希和完整生成源码树在 [result.json](result.json)，逐函数行在 [flight_functions.csv](flight_functions.csv) 和 [ground_functions.csv](ground_functions.csv)。本批证据 `* -text`，避免 Git 换行转换破坏记录字节哈希。

这次是检查器修改，没有重跑 ARM 链接、固件全 Host 或分析器，不把它们列为本批新执行结果。上一固件语义批次的实际 F407/F103 链接、Flight/14 个 Ground 分析器编译与 Host 结果仍只属于 [原记录](../pot_jy_rule5_average_batch_20261001_v1/result.json)。相同源树支持关联审阅，不等于当前提交执行了复合全套。

## 旧 FCCG 的实际情况

只读使用旧仓库 Git 对象，未修改旧工作区、全局 Git 设置或旧证据。旧仓库存储提交 `f58b17e98e73fc77afb288689e496b6e6bcf5832`，checker 历史提交 `ec5e1a318b669b98344000e419dda8a140b66e97`（2026-09-26）。Core 0.0.12 检查器与 monorepo `2763bb8` Core 0.1.0 初始版本在统一换行后字节相同：迁移本身没有丢失这个检查器设计。

旧门槛是 **每个 >20 行函数至少两项**，没有均值门槛；`SILVERSTAR_ASSERT_OBJECT` 按非空+对齐计 **2**，显式断言每次计 1，未排除固定地址/常量/重复。因此旧 PASS 不能证明两个有效运行时不变量。跨行宏边界缺陷也已经存在；误删无 BOM 首字符则是后来的 BOM 处理回归。

确有完整配置日志：KF6 Flight Release 的 PoT 为 6459 checks / 99 文件 / 2427 函数，架构 318/0；Pure INS Release 为 6118 checks / 96 文件 / 2303 函数。质量日志包含实际 `CONFIG=Release ANALYZE=1 all` 命令，汇总记录其退出结果。另一个 navigation review 的 PASS 只覆盖 2 文件/196 函数，不能当成全第一方通过。路径、Git 对象哈希及相关行见 [legacy_checker_audit.json](legacy_checker_audit.json)。存储日志的提交不能单独证明日志执行时的源码恰为该提交；不把旧二进制归到当前源码。历史 PASS、当前低候选数和不同源配置可以同时成立。

## 仍未证明或待修内容

- 本工具只扫描所列目录中的 `.c`，不做头文件/宏展开 AST、完整条件预处理或真正的编译调用图。包含未激活分支和部分未链接平台源，不能用函数总数代替实际链接范围。
- 候选计数既可能误收（已由前置 guard 保证的条件、语义同义条件），也可能漏收（未证明纯函数、窄语法之外的表达式）；它不是有效断言数量的严格上界或下界。候选不证明生命周期、容量、数值或任务/ISR 一致快照契约。
- 前批已修 JY 时间、读回与收发失败边界；`IMU_SaveConfig` 的收发停止/恢复结果及 F4 BaudSet 的 HAL 恢复返回处理仍需单独审查。没有宣称全部资源或 READY 故障轨迹已证明。
- 任务路径、库及间接调用、动态栈帧、main/MSP、中断嵌套栈界与 STM32 WCET、硬件/飞行证据仍 NOT PROVEN。第三方 HAL/RTOS/库仍是既有受控例外；不宣称其完全符合原十条。前批 F103 四条 newlib 链接警告保留为前批限制，未被本次文本 PASS 消除。

环境短暂断开后现有 pytest 会话与生成会话均正常退出 0，没有启动重复构建。系统级 CIM 进程枚举因访问拒绝未能完成；通过既有会话句柄、记录 PID、完整日志和退出码确认本批命令状态，不声称完成全系统进程审计。
