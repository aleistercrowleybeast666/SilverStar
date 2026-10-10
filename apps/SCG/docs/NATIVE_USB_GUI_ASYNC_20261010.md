# USB Ground 候选：GUI 线程刷新 P2 修复与普通验证（2026-10-10）

本次只处理父任务 ordinary review 指出的重复完整 Plan/文件 hash 审核阻塞 GUI 的 P2。代码提交 `640a0d3fb6c717b541062d4aa8794841e3e5191c` 和 `f61cbd851b8ac32b865deb1a3997058685dfebbd`；最终所有下列测试和新编译均使用后一 clean revision。此前已验收的 first-batch 软件证据保持原样，见 [NATIVE_USB_GUI_FLOW_20261010.md](NATIVE_USB_GUI_FLOW_20261010.md)，证据提交 `bf22bdcd56e76687e8be40d5f221cb3c29668ec1`。

## 行为与完整性

原合法 F103/C071 候选的 `_Project_Refresh` 分别阻塞 6.750/9.262 秒，20ms Qt timer 回调为 0。现在 `_Project_Display` 与 `_TargetQualityResults_Refresh` 只提交不可变的 model/project 快照，由现有 `Task_Run`/`FunctionWorker` 执行全部昂贵 native Plan/source/receipt/artifact 审核。一次刷新只有一个完整 Plan；各已存 quality records 共用本次 Tool 输入字节与审核结果。每次请求重新审核，没有持久信任缓存；原配置、源图、模型、SDK IRQ、receipt、ELF/产物 hash 校验保留，指针前后变化也会拒绝。

一个 QObject-owned single-shot timer 合并 pending 请求，沿用单后台任务、进度、取消、retired-worker 与关闭归属。epoch、项目及模型一致性保护 success/error callback；切项目、取消、关闭、销毁后不能用旧结果覆写新状态或启动排队任务。import、Generate/Build、quality 和 artifact/open/clean 路径遵守同一请求归属；artifact 验证和已授权生成物清理也进入 worker。legacy 非 USB import 保持原 `_GroundCubeMxImport_Complete` callback API。

UI 只改 MainWindow 逻辑；25 个其他 UI 文件不变，构造器新增六项 owned timer/worker 状态，移除这六项后原 widget/layout/style AST 相同。两个分开的相同 offscreen 进程以相同未绑定参考模型渲染，Ground/Build 1280×820 均像素一致。同进程渲染曾出现 Ground 高度/字体缓存差异，其截图和 receipt 原样留存，未改产品样式来适应截图。offscreen 中文字体缺字仍限制完整桌面视觉验收；此比较只证明参考页保持外观。

## 最终真实执行

| 执行 | 结果与范围 |
|---|---|
| ua04 | 12 passed、0 skipped，实际正常导入/保存/重载/生成、切换/拒绝未知配置、取消、progress 与新 ARM Build；使用实际 existing tool detector 后真实启用 Generate/Build button `.click()`，不是只发 action signal |
| ur06 | 16 passed、0 skipped，真实 20ms Qt timer；完整 Plan 在非 GUI 线程且每刷新一次；quality state、pending 合并、项目替换、迟到 import 成功/错误、取消、close、QObject 销毁、排队 timer 与 artifact 审核 |
| ugr04 | 99 passed、0 skipped，既有 GUI/Build/target-progress/native-control/clock/radio/ABI/runtime 回归 |
| ul19 | 2 passed、0 skipped，两组共 34 次 ordinary lifecycle Host 执行，每组 17 scenarios；实际生成 USB core/class/interface/stream，LL/PCD/Cortex/UID 使用明确 Host substitutes |
| uag01 | 8 条原样 emitted command 全 exit 0，每颗 architecture、ordinary Host、artifact 与 Power-of-Ten 各 1 条；实际对象/ELF CPU/ABI 与独立 SDK IRQ/vector 核对保留 |

`ur06` 只读此前 ug08 实际 compiled legal candidates，fixture 核对其 compiler/backend receipts 及 normal/analyzer ELF 在测试前后未变；`ua04` 则重新生成并实际编译两个新输出，因此旧候选刷新测试与新固件构建的证据范围分别明确。

| 目标 | 同步旧有界面填充 | 全刷新用时 | 后台 timer ticks | 最大后台 tick 间隔 | Plan 次数/线程 |
|---|---:|---:|---:|---:|---|
| STM32C071FBP6 | 0.577s | 3.762s | 100 | 0.067s | 1 / worker |
| STM32F103C8T6 | 0.519s | 2.494s | 58 | 0.065s | 1 / worker |

后台 cadence 的统计从同步界面填充返回后开始；没有声称整个 view update 都在 500ms 以下。真实 Build 加完成后审核的整个窗口中，F103 68.406s、3288 ticks、最大间隔 0.720s；C071 73.373s、3610 ticks、最大间隔 0.622s。任务仍沿用原忙碌状态和 Cancel UI，界面线程能处理 timer/events。

## 新输出、命令与版本

- `STM32F103C8T6`：`C:\Users\chdxm\AppData\Local\Temp\ua04\usb-ee466bf8fd30`；339 条 compiler/link/analyzer 命令均 exit 0，normal/analyzer ARM link 实际成功，firmware/analyzer diagnostics 为 0。工具 `arm-none-eabi-gcc (Arm GNU Toolchain 14.3.Rel1 (Build arm-14.174)) 14.3.1 20250623`。完整 source-snapshot SHA256 `c8319f1b14a78c35bd1545d094079e5e343664cf3fc1bf0cb6a0a028098e3c1c`；compiler receipt `9e8a02f9b7a213adc9acc425d6e7695f8ed69cd23f79ec2017a864b1d71f2799`；backend receipt `f19e2ebcca7cd71fa125679c5cb7fd6cfc3f73a017a98c350c850fe84ac25bc9`。normal/analyzer ELF SHA256 均为 `fde957fe80fdf038f4c5c6640bc851446e8ef7acb7605258fd94dca87c81240b`。
- `STM32C071FBP6`：`C:\Users\chdxm\AppData\Local\Temp\ua04\usb-6d85cddbb6b8`；351 条 compiler/link/analyzer 命令均 exit 0，normal/analyzer ARM link 实际成功，firmware/analyzer diagnostics 为 0。工具 `arm-none-eabi-gcc (Arm GNU Toolchain 14.3.Rel1 (Build arm-14.174)) 14.3.1 20250623`。完整 source-snapshot SHA256 `851607edcad886b9145e40d5ca7efdbced80f2c5d1a8bf2229075e381a3710c7`；compiler receipt `e4fd841899690f58e6dc5aceb104b63546c5e2cc834cc2b17b030908cb4534a3`；backend receipt `60ea983ff28eede75c6d3e8754baa3d7f87bfa5791b60a4c63628754c607a7aa`。normal/analyzer ELF SHA256 均为 `ee90e6871f5f5723982701e8b6783dd2638f4bd76f352f5099d2d38e031028b9`。

ELF 字节与此前正常构建相同符合本次仅 Python/UI 调度改动的范围；这是重新执行的新编译，来源提交/命令/模型/receipt/source snapshot 单独记录，没有拿旧二进制冒充新构建。原 HAL/CMSIS/startup/linker/clock/GPIO/IRQ/PCD/middleware 所有权保持，本增量无 firmware generator/native C 改动。

## 失败历史与实际局限

ua01 的两个失败来自旧 10s helper 不覆盖 now-async Export 后完整审核阶段：实测 Export 约 7.44s、审核约 2.99s、旧界面填充约 0.6s。测试明确等待完整任务阶段，仍有 bounded budget 和 timer/thread 验证，未靠超时扩充单独掩盖 GUI 阻塞。ur01 将未改动的 view 填充纳入后台 cadence 后失败，后续明确分别计量，同时保持后台最大 gap <0.5s。

ua03 10 passed/2 failed：新测试真实 Build button 未启用，因为只选择 compiler 路径而未调用现有 tool detection；f61 修正测试走真实 detect button，未伪造 compiler availability。ugr03 98 passed/1 failed：新 wrapper 破坏 legacy callback identity；f61 仅 USB 分支使用请求 guard，legacy API 原样恢复，原回归测试没改。

ur05 同一 f61 代码与构建、回归、生命周期及截图并跑，14 passed/2 failed，失败在同步旧有 view 填充 <0.75s：F103 0.977s、C071 0.941s，未进入后台 cadence 断言。其他任务结束后未改任何代码或阈值，独立 ur06 全 16 passed，填充 0.519/0.577s。该并跑失败及原始 receipt/log 保留；不能把结果表述成并发重负载下全部小于 0.75s，也未证明 GUI 所有 legacy 工作都瞬时完成。其余全部历次失败/通过日志、source/dirty snapshot、command receipts 按版本留存，没有拼接未执行的全套通过。

pytest unknown `cache_dir` 配置 warning、Host vendor unused-parameter 等既有 warning 按原 scope 保留，不能等同于 firmware/analyzer warning。PoT 退出 0 仍保留 manual critical-contract `NOT PROVEN`，不宣称 whole-program stack、STM32 WCET 或所有异步 PCD/IRQ interleaving 已证明。

## 归档与状态

证据 [verification.json](evidence/native_usb_gui_async_20261010/verification.json) 包含 962 个 listed files，加 manifest 共 963 文件；listed 原始字节 23907399；manifest SHA256 `a2ed150fc05756a5d911e15680c46606597d9c8a3e731bbb3fab9280bb10d05b`。归档完整 compiler/backend/source-snapshot/model/pointer/quality receipts、命令日志、normal/analyzer ELF/map/.su、selected first-party/derivatives/Tools、actual lifecycle Host fixtures、Qt response、失败历史、父 ordinary P2 reproduction 与视觉边界/截图。vendor 不大量复制，原始 pinned path/hash 留作 provenance。

代码/证据只落 `D:\python_software\SilverStar\.work\ccdi` 的 `feature/scg-classic-cdc-contract-20261009`。日用 HEAD 保持 `56448bd35736221d7885a26704f2f953b0fe5055`，原三个 inventory untracked 文件不变；没有硬件、DAPLink、串口、烧录、START、FINAL 修改、push 或 merge。自有启动的构建/测试均已结束，系统级全进程盘点因权限限制未确认。

b66 独立 USB 安全审查被平台中止，仍是 `NO_PASSED_OUTCOME`，本次未重试、未绕过、未复做；普通入口/正式发布 guard 保持，候选并未交付为通用可用。硬件未测不是本轮软件工作的新增前置条件。F407 与其他未支持配置继续明确拒绝，本增量未扩大其 runtime support。此报告交父任务进行新的普通独审；本次工具通过不代替独审或正式放行。
