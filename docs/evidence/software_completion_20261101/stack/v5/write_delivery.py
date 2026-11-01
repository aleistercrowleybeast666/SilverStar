"""Render the final report only from completed, preserved B results."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


if __name__ == '__main__':
    summary = json.loads((HERE / 'final-summary.json').read_text(encoding='utf8'))
    resources = json.loads((HERE / 'resource-summary.json').read_text(encoding='utf8'))
    coverage = json.loads((HERE / 'analyzer-coverage.json').read_text(encoding='utf8'))
    assert summary['whole_program_stack_acceptance'] == 'SOFTWARE BOUND PASS'
    rows = []
    for row in resources:
        msp = row['main_msp_exceptions']
        banks = '; '.join(region['name'] + ' ' + str(region['used_bytes']) + '/' +
            str(region['review_budget_bytes'] or region['physical_capacity_bytes'])
            for region in row['regions'] if region['name'] != 'FLASH')
        rows.append(f"| {row['case']} | {row['configuration']} | {msp['worst_known_bytes']} / {msp['configured_bytes']} / {msp['margin_bytes']} | {row['minimum_task_margin_bytes']} | {banks} |")
    text = f'''# 严格栈软件验收：五模型、十构型

最终正常生成 B 绑定源码提交 `{summary['source_commit']}`。五个实际模型的
Release、Debug 严格栈门禁均为 **SOFTWARE BOUND PASS，退出 0**。这是固定输入、
工具链和已审阅运行时合同下的软件栈上界；不是任意项目通用放行或硬件认证。
机器可读结论见 [final-summary.json](final-summary.json)。

## 实际执行

- B 的 10 次实际 ARM 编译链接、10 次 artifact-check 全为退出 0。
- B 原样 emitted architecture-check 5 次、power10-check 5 次、真正 ANALYZE=1
  ARM 编译链接 5 次、stack-report 10 次全部退出 0；完整命令、退出码及日志哈希在
  [gates-b/commands.json](gates-b/commands.json)。没有用 syntax-only 替代分析器。
- A、B 均正常生成并真正编译。10 组、5,256 项 `.o/.su/.d/ELF/map` 原始字节完全相同；
  没有拷贝旧 ELF、剥离调试信息或对产物做归一化。
  [完整比较](build-b/raw-byte-comparison.json)包含两边每项哈希。
- 14 个 stack 测试文件一次完整执行为 **252 passed，20.42 秒**，
  [原始日志](final-all-stack-regression-v2.log)。源提交后的独立收据 run 也是
  **252 passed，26.01 秒，退出 0**，完整 command/env/前后哈希见
  [formal-stack-regression.json](formal-stack-regression.json)，[日志](formal-stack-regression.log)。
  没有将两个 run 拼成一次结果。pytest 唯一配置提示是关闭
  cacheprovider 后既有 cache_dir 选项；不是 C 编译警告。
- 7 个真实 B 副本破坏输入均被严格检查器拒绝；修改头文件、降低 `.su` 帧、修改对象字节、
  删除/修改 proof manifest、修改人工审阅文档、修改控制元数据均不能继续通过。
  每项原始字节和时间戳恢复，哈希核对一致，最终恢复后的正例退出 0。
  [负例命令和恢复记录](negatives-b/commands.json)。

正常构建和资源命令在 [build-b/commands.json](build-b/commands.json)，
完整原件在 [reports-b](reports-b)。[analyzer-coverage.json](analyzer-coverage.json)
逐文件核对 Make 声明的 first-party 集合与日志中真实带 `-fanalyzer` 的编译集合，
每个构型均无遗漏和额外文件。H7 两个 owning `FATFS/Target/*.c` 在其精确集合中；
F407 同名导入源不被错误改成 first-party。

## 资源和上界

下面单位均为 byte。MSP 列依次是软件上界、配置容量、剩余；任务余量是全部启用任务的最小值。
固定任务上下文 256、最小余量 256、F407 SRAM 审阅上限 102400 均未放宽。

| 模型 | 配置 | MSP 上界 / 容量 / 余量 | 最小任务余量 | 静态内存已用 / 适用上限 |
| --- | --- | --- | --- | --- |
{chr(10).join(rows)}

内存已用包含保留主栈；完整 bank 明细、物理余量、padding span、每任务最坏调用链及
ELF 哈希在 [resource-summary.json](resource-summary.json)。内存 artifact 原始报告的
`stack_proof: NOT_PROVEN` 字段未改写；它自身不做整程序栈证明。这里的结论来自相同
ELF 哈希对应的独立严格 `stack-budget.json`，不能借静态 RAM 空闲量代替栈证明。

## 证明闭包与实际修复

实际 ELF FUNC 范围、编译器 `.su` 和机器 SP 操作共同建立函数帧；以两者较大值计入。
分析涵盖条件间接分支、编译器 switch 表、局部 BL helper、汇编及 libgcc 共用后缀，
未知 SP 操作、正增长循环、递归和未解间接调用继续拒绝。修复过一个重要的 noreturn
推断缺陷：返回型 tail branch 不能令初始化函数被误判为永不返回，从而遗漏任务业务循环。
旧的低估诊断 [whole-probe-v3.log](../v1/whole-probe-v3.log)明确作废，不是可接受上界。

每个 case 密封完整选定 C、工程头文件、汇编、linker、Make、编译器工具/ABI 头文件、
实际链接 CRT/archive、对象/栈/依赖及 ELF/map。工程文本来源哈希只统一 CRLF/LF；
所有编译产物及 proof 文档使用原始字节哈希。完整 DWARF 保留，正式生成器仅使用
`-ffile-prefix-map="$(CURDIR)"=.` 使独立路径编译可重现。人工审阅文件的真实 SHA 被校验；
检查器没有自登记、自更新 proof 或在 mismatch 时继续放行的通道。

HAL 间接调用不仅匹配字段偏移：固定 case 同时约束实际加载指令/到达定义、句柄对象来源、
BSS 清零区间、父子 DMA 连接和全部目标集合。任意 NULL 赋值不能单独证明字段只会为空。
RTOS 上下文切换、启动/CRT 初始化数组、实际向量表、main/reset、相关 ISR 及 NMI/HardFault
均计入。F407 使用审阅后的完整原始优先级域 {{0,5,6,15}}，H743 保守使用 16 级；
每层都计最大 ISR 链及 108 byte 硬件扩展帧，不利用 tail-chain、屏蔽或 lazy FP 来减预算。

本次 F407 主栈从 1024 增到 2304，拥有者模板真实修改。相应 SRAM 空间来自完整板级
GPIO 资源表决定的上下文容量，9 槽替代此前固定 96 槽节省 1740 byte；稀疏高编号及
不透明旧配置仍保留相应容量。参见 [GPIO 合同及前后证据](../../critical/gpio-capacity/REVIEW_ZH.md)。
旧 installation Debug 超 100 KiB 的真实失败保留在 v2；没有提高 RAM 门槛或削减队列。

启用 PID/LQR 的两模型使用真实 TreeDiagram 10 ms run bundle，经现有严格 importer
正常生成，Flight 任务闭包分别包含 `ControlPid_Step` 或 `ControlLqr_Step`；禁用模型
没有把仅链接、不可达的数学核冒充执行证明。Underline-PID 模型字典与 PID 完全相同，
不是遗漏第六种不同配置。控制输出仍是明确 Nm 单位的有界研究结果，不是电气输出。

## 范围、失败记录和重放

只接受这五模型和十配置。更改项目名、参数、来源/头文件、Make、ABI 或工具链安装输入
需要新的实际构建与人工审阅；不能复制 manifest 给其它固件就宣称通过。
`final-summary.json` 原样记录收集时的工作区状态：后续 USB Python 生成/传输模块与
Host `test_interfaces.c` 夹具仍有独立修改。它们不在已经封存的 B 目标编译输入内，
但本报告不把这些后续修改冒充为 e7 的整体测试结果；其新输出/完整 Host 由所属报告另记。
Host 修复只让布局断言匹配新增历史 provenance；后续正常生成 C 的默认 481 文件和安装
502 文件实际目标 C/ASM/头文件、Make/linker/sourcegraph flags 与 B 精确相同，见
[独立比较](../../control/full-host-c-vs-b.json)。后续 USB 修复属于通用 kit 的 no-heap
owner、精确 F407 LL 输入派生 FIFO 及共享 descriptor 合同，未更改本次 Flight
render、算法/runtime C payload 或栈 Tools；它们使用独立 USB 验证 epoch。
固定 case 的 C/header/Make/工具链/产物身份检查仍照常拒绝任何后续生成造成的输入差异。
软件证明不覆盖任意内存破坏、恶意改写向量/TCB 或故障硅片。
MCU 栈高水位、WCET、中断延迟、RF、传感精度及飞行资格均未测量。

Power10 文本工具退出 0 仍保留 **critical-contract review NOT PROVEN**。
[定向关键合同复核](../../critical/REVIEW_ZH.md)只覆盖其列明的 mission/并发状态/故障传播等合同，
不代表所有固件规则、所有指针或所有失败路径已人工证明。完整 Host 另有独立记录；
首次 B default Host 的旧 ABI 大小断言真实失败不被这些栈通过结果覆盖。

早期版本及未通过过程见 [INDEX](../INDEX.md)。首次 gate-driver 在 A/B 原始比较文件
尚未写出时拒绝前置条件，见 [final-gates.log](final-gates.log)，当时未执行任何门禁；
完整正式执行见 [final-gates-v2.log](final-gates-v2.log)。
新输出位置和只读输入边界见 [workspace-inventory.json](../workspace-inventory.json)，没有清理旧工作区。

重放从 `generate_candidates.py` 的 current catalog 和实际 bundle 构造开始，使用新的
独立输出目录，禁止覆盖本次证据。已生成工程可直接按对应 commands.json 执行：

```powershell
mingw32-make -C <project> CONFIG=Release "GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin" all artifact-check
mingw32-make -C <project> CONFIG=Release "GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin" architecture-check power10-check static-analysis stack-report
mingw32-make -C <project> CONFIG=Debug "GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin" all artifact-check stack-report
```
'''
    (HERE / 'DELIVERY_ZH.md').write_text(text, encoding='utf8')
    print('Final delivery report written from preserved B results')
