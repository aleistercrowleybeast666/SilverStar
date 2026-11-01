# 共享 F407 描述符修复后的私有 USB 最终验证

本 epoch 的 F103、F407、C071 三板均重新经过真实 private Import/Export、正常 ARM 编译链接和
ARM `-fanalyzer` 编译链接。三个结果都是 `CompiledCandidate`，各自原样 emitted architecture、
Host、Power10、artifact 四门禁全部退出 0。没有复用旧 ELF，也没有修改原始 CubeMX 输入或门禁。
完整收据及归档索引见 [receipt.json](receipt.json)，12 项门禁命令见 [gate-commands.json](gate-commands.json)。

| 私有构型 | 实际编译器命令（全退出 0） | 实际分析的 C TU | emitted 四门禁 |
| --- | ---: | ---: | --- |
| STM32F103C8T6 | 345 | 55 / 55 | 0 / 0 / 0 / 0 |
| STM32F407VET6 | 399 | 64 / 64 | 0 / 0 / 0 / 0 |
| STM32C071FBP6 | 357 | 57 / 57 | 0 / 0 / 0 / 0 |

分析流程是真实 ARM GCC `-fanalyzer -S`，随后 GAS 汇编和实际 ELF 链接；并非 syntax-only。
三板全部选定 C 源都在分析命令中，实际生成 assembly/object 与 normal/analyzer ELF 均存在。
F407 修改的 `ReviewedNativeControl/Core/Src/usbd_core.c`、`Class/CDC/Src/usbd_cdc.c`，以及
共享 `Generated/Src/pc_usb_control.c` 均实际进入分析。`warning_diagnostics` 三板均为空，
含义限于实际记录的 first-party/vendor 编译策略，不冒称所有 vendor 代码采用完全相同的警告选项。

## 相同阶段的完整编译输入比较

[compiled-closure-comparison-v2.json](compiled-closure-comparison-v2.json) 将新的编译后工程与
旧已归档的 `arm-v2-F103-artifacts.zip`、`arm-v2-F407-artifacts.zip`、`c071-v1-C071-artifacts.zip`
中实际 compiler receipt 逐项比较。范围包括选定 C/ASM、工程全部头文件的严格超集、Make/linker、
来源图、include/define/MCU flags 和 required symbols/IRQ。

- F103：192 项输入及编译图字段完全相同。
- C071：211 项输入及编译图字段完全相同。
- F407：219 项中仅 `Generated/Inc/pc_usb_control.h`、上述 reviewed core/class 两个 C 文件变化；
  编译图、Make、linker、其它头文件和输入不变。该构型已经完整重新构建和执行门禁。

初始 Export 阶段与旧编译后归档的比较发现编译器后加的 `native_abi_probe.c` 及相关 Make/graph
差异，因此没有仅凭 Export 宣称无影响，而是保守对三板全部重新编译。首次编译后比较辅助脚本
还误将 `build` 输出目录内的 `.deps.mk` 和 Host stub 头文件视为输入，原记录保留在
[compiled-closure-comparison.json](compiled-closure-comparison.json)，它不是通过证明。
v2 排除的仅是生成构建输出目录，同时明确断言编译 include 路径不指向该目录；未排除任何目标
源文件或改变固件门禁。[validate.py](validate.py) 的该辅助比较更正不改变任何已生成固件字节。

## 精确 Host 的真实失败与修正

第一轮 [faults.log](faults.log) 是 **1 passed / 1 failed，39.61 s**。F103 原有 18 个 normal
lifecycle 与 10 个 EP0 case 全通过；F407 原有 18 个 normal 及 20 个扩展 case 中，仅
`descriptor-request-invalid` 失败。错误实际发生在 Host `USBD_LL_StallEP` 的 OUT 端点允许条件：
新的坏描述符 getter 按产品合同先发布软件 STALL 并执行 LL STALL，而测试直到后续 SETUP 前才
设置既有 `allow_control_error`，因而先触发了 stub 断言。超时和完整 stderr 均保留，没有改写为通过。

测试 owner 仅将这一预期错误 case 的允许标志提前到首个坏 getter 之前，保留设备 owner、端点、
零发送/接收、整个数组不被部分改写等原断言。生产 `ground_usb_control.py`、`native_control.py`
前后哈希相同；唯一变化是 `tests/usb_descriptor_cases.py` 的夹具时序。

同一完整两板组在新目录重跑：[faults-post.log](faults-post.log) **2 passed，31.35 s，退出 0**；
两个 normal 组各 18 case，F103 10、F407 20 个扩展 case 全部退出 0。这里的扩展 case 包括合法
getter 正例及无效描述符/owner/长度/传输故障场景，不能把它们全部称为实际 USB 硬件错误。
[faults-command.json](faults-command.json) 与 [faults-post-command.json](faults-post-command.json)
记录真实命令、输入哈希和耗时；四个 `*-host.zip` 保留前后实际 harness、生成源码、编译日志及逐项收据。

## 来源和边界

三板初始正常生成期间的 `apps/SCG/src`、plugins、contracts 快照没有变化，见
[generation-source-snapshot.json](generation-source-snapshot.json)。源 HEAD 为
`e7c42b7c4971fddb02c6d5c60864b50dffaa3f1a` 加收据记录的 dirty epoch，不能声称整个工作区干净。
后续 generic metadata 准入修复改动了 `build/native_usb.py` 和 `generator/native_usb_graph.py`，
其时间差在 `receipt.json.subsequent_source_changes` 原样记录；这些不进入本次已封存的私有目标
编译输入。generic 路径使用独立验收记录，本报告不把它与 private 结果混用。

各板 zip 保存真实 source snapshot、全部 compiler commands、配置/来源图、normal/analyzer ELF/map
及内存/artifact 报告；F407 相关派生源码也以实际字节归档。归档完成后重新读取验证所有成员哈希。
临时输出位于 `.work/sc-261101-usb/d2`，故障夹具位于 `fd2`、`fd3`；这是本任务已记录的短路径，
没有改变正常 Windows 长度规则、清理旧工作区或更改原输入。

重放使用 [validate.py](validate.py)、[run_gates.py](run_gates.py) 的命令及
[上一 epoch 环境清单](../COMMANDS.json)，必须改为新的输出目录，不覆盖证据。

本次没有连接 USB、烧写、发射或运动。所有 private/formal USB 发布限制保留，C071 的既有独立审查
限制也未重试或绕过。Power10 仍明确输出 **critical-contract review NOT PROVEN**，它的 text gate
范围是既有 first-party 集合，不等于对全部派生 vendor USB 栈的完整十规则证明。全 EP0/异步交错、
整程序关键合同、这些 USB 固件的严格整程序栈、WCET、真实时钟/电气/射频及硬件资格仍未证明。
Flight 五模型的独立栈证明不外推到本目录 USB 固件。
