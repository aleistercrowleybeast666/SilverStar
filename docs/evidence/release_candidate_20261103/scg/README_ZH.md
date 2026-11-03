# SCG 0.1.3 软件候选验证 · 2026-11-03

## 当前入口

从仓库根执行 `.venv/Scripts/python.exe apps/SCG/SCG.py`。Windows 发布目录的 SCG 启动器由总交付报告记录。三页分别是硬件与通信、任务流程、检查与生成。[用户指南](../../../../docs/public/SCG/USER_GUIDE.md) · [项目格式](../../../../docs/public/SCG/PROJECT_FORMAT.md) · [插件格式](../../../../docs/public/SCG/PLUGIN_FORMAT.md)

硬件卡位于共享空口摘要之前。板卡或 CubeMX 导入、接口、接线在各自目标的私有草稿内。共享无线拥有两端模块、功率与空口参数。选择实验磁力计相对旋转时，飞控硬件的高级安装入口调用工程的同一选择校验。流程页保留阶段与共享功能运行范围。阶段名称不改变 ID，阶段按钮可先应用该阶段再进入共享功能。记录与遥测范围、记录内容、算法和准备参数都由相应属性窗口管理。输入有效数字后直接应用，一处无效保留草稿，取消或 Esc 不写正式模型。生成页使用同一份目标就绪判定，按目标显示当前产物、真实银行、审阅预算与独立栈证据。

## UART 与历史迁移

原生 MCU USB Device CDC 候选操作、专属生成器、Host 路径、插件与命令已退出活动产品。147 项历史实现或仅服务于这些实现的测试/工具的原始字节摘要见 [分类记录](removed-cdc-files.json)。旧证据保留原提交与结论。保留了物理 UART、外置 USB-UART、Ground 字节流和会话/背压/溢出边界、F1/F4 HAL ReceiveToIdle DMA、Ground GSP、Flight 维护和共享无线。C0 MCU 元数据可识别历史器件，当前不生成 C071 CDC 工程。H7 SD 没有纳入 CDC 删除范围。

历史工程保留可读数据字段。迁移前，保存和针对任一目标生成会返回明确原因，原文件不动。用户须在地面站属性中明确选择 UART 和具体资源，核对硬件来源及波特率后再应用。原输入含 CDC 时需另选普通 UART 工程。实测源保护时，旧 F407 原生参考 141 个文件逐字节不变，拒绝时缓存没有创建文件。普通 F407 UART 输入 121 个文件逐字节不变且导入成功。[保护结果](input-protection.json)

## 正常生成与真实门禁

ARM GNU 14.3.Rel1、GNU Make 4.4.1、MSYS2 Host GCC 16.1.0。精确工具路径、版本及 Python/Qt 见 [运行环境](tools.txt)。产品批提交 `99533471730641da658218bce439e64d1721a04c`。首轮生成期间仓库 HEAD 为 `8a25f99e7096df94cbf46b83bf4049a55e43a887`，包含工作区新改动。构建基于各自独立生成的实际工程。逐个文件摘要、所选图与实际源码快照保留了生成当时的身份。没有用后来的提交号给早期二进制追认版本。

四个地面工程均由 `TargetGeneration_Apply(..., TargetScope.GROUND)` 正常生成。每个工程独立通过 `all`、`host-tests`、`architecture-check`、真实 `static-analysis`、`artifact-check`、原样 `power10-check`。F103/SX1281 使用声明的地面站 0.5 PCB。F103/SX1278 和 F407 两个构型均为独立软件接线夹具。F407 两个构型的首轮结果为五项失败、一项架构通过。缺少 GPIO context 数量、没有选择已实现的 F4 UART DMA 适配、以及同步开发中的平台条件编译均在实际修复后重新生成验证。四份 Ground 方向实现均与实际被编译的最终源 SHA-256 `283926c7a8b06772828b94b0777e932e08b1b58cb173814256be29cd3da8aa18` 匹配。

F407 飞控的 SX1281/E28 与 SX1278/E32 各自通过真实 ARM 编译链接、架构、Power of Ten 文本门禁、ARM `-fanalyzer` 实际分析及产物检查。SX1281 保留 2,473 MHz、名义 800,000 Hz 的既有配置，SX1278 测试使用 433 MHz、125,000 Hz。Ground 和 Flight 构型均未选择原生 CDC 源。

在默认与可选传感器源码冻结后，用相同正常入口重新生成六个构型。F103/E28 和 F103/E32 的 163/189 项输入中各只有 platform_gpio.h 改变，各自重新运行六项门禁，全部退出 0。F407 两个 Ground 构型的 198/171 项输入（图中全部 C/ASM、头、链接脚本、Make 声明和 Host/Tools）分别与原有已实跑的构型逐字节相同。两个 Flight 构型各有 10 项输入变化，实际重新编译并运行架构、原样 Power of Ten、ARM 静态分析及产物门禁，均退出 0。最后生成的 E28 解码包 SHA-256 为 `2895ad3f1c9d8c7933567e7632776aa1b996c9d2f526622f07a752cd019cd305`。

两套最终飞控的严格 `stack-report` 均退出 2。默认 E28 的编译声明匹配历史 Release 案例，但完整输入含 14 项修改及 1 个新增头。E32 的新硬件输入和 SX1278 图与旧 E28 声明不同，严格旧回调校验拒绝 `APP/Src/device_task.c` 的源身份。没有修改允许清单。P10 的人工关键契约仍报告 NOT PROVEN。这些软件运行没有测量串口真实吞吐、无线射频、硬件触发、时序或飞行安全。[各轮结果及产物哈希](build/matrix.json) · [严格栈输入差异](build/stack-closure-delta.json) · [完整命令与输出](build/commands-and-complete-logs.zip) · [逐文件输入身份](build/exact-generated-inventory.zip) · [生成的第一方输入](build/generated-first-party-inputs.zip)

### 实际资源

| 目标/无线 | 银行 | 使用 / 物理容量（B） | 占比 | 物理余量（B） | 审阅预算 / 余量（B） |
|---|---|---:|---:|---:|---:|
| ground f103-sx1278 | FLASH | 17,848 / 65,536 | 27.2% | 47,688 | 未声明 |
| ground f103-sx1278 | RAM | 5,372 / 20,480 | 26.2% | 15,108 | 未声明 |
| ground f103-sx1281 | FLASH | 29,020 / 65,536 | 44.3% | 36,516 | 未声明 |
| ground f103-sx1281 | RAM | 6,652 / 20,480 | 32.5% | 13,828 | 未声明 |
| ground f407-sx1278 | FLASH | 19,664 / 524,288 | 3.8% | 504,624 | 未声明 |
| ground f407-sx1278 | RAM | 4,936 / 131,072 | 3.8% | 126,136 | 未声明 |
| ground f407-sx1278 | CCMRAM | 0 / 65,536 | 0.0% | 65,536 | 未声明 |
| ground f407-sx1281 | FLASH | 29,828 / 524,288 | 5.7% | 494,460 | 未声明 |
| ground f407-sx1281 | RAM | 6,164 / 131,072 | 4.7% | 124,908 | 未声明 |
| ground f407-sx1281 | CCMRAM | 0 / 65,536 | 0.0% | 65,536 | 未声明 |
| flight f407-sx1278 | FLASH | 348,564 / 524,288 | 66.5% | 175,724 | 未声明 |
| flight f407-sx1278 | RAM | 92,428 / 131,072 | 70.5% | 38,644 | 102,400 / 9,972 |
| flight f407-sx1278 | CCMRAM | 62,656 / 65,536 | 95.6% | 2,880 | 未声明 |
| flight f407-sx1281 | FLASH | 360,172 / 524,288 | 68.7% | 164,116 | 未声明 |
| flight f407-sx1281 | RAM | 101,676 / 131,072 | 77.6% | 29,396 | 102,400 / 724 |
| flight f407-sx1281 | CCMRAM | 62,656 / 65,536 | 95.6% | 2,880 | 未声明 |

地面站 F4 未分配的 CCMRAM 不代表可用作一个连续缓冲区。F407/E28 飞控静态 SRAM 预算仅剩 724 B。物理余量、链接器配置与任务/MSP 安全余量分别计算，实际报告未证明的栈仍为 NOT PROVEN。最终六份 memory-report 在 `build/flight-v2-*-memory.json` 和 `build/matrix-v3-*-memory.json`。每个阶段的命令收据、原始错误和实际执行脚本在日志压缩包。源码包中的 `files.json` 将每个工程相对路径映射至 `blobs/<SHA-256>` 原始字节。

## GUI

两个独立 Qt 进程使用真实 `MainWindow` 和隔离 SettingsStore。普通启动模型没有注入已配置设备。截图进程显式关闭自动工具探测，以便稳定观察未检测状态。随后使用单独的参考模型捕获了阶段、共享功能和对应的属性窗。每套包括宽窄主视图、空工程、两端属性、共享无线、阶段及功能、算法/准备/协议和构建选项。实际像素数、逻辑尺寸、按钮可见性和模型相等断言在各套的 JSON。均为 Qt offscreen 渲染。物理桌面或打包启动由总交付单独记录。[中文浅色 125%](final-125/capture.json) · [English dark 150%](final-150/capture.json) · [捕获脚本](capture_gui.py)

## 测试与遗留

UART、Ground 回压/DMA、导入与资源、Flight 维护及有界流程整组 **109 passed / 233.74 s**。最终 GUI、迁移和功能范围整组 **89 passed / 494.78 s**，覆盖多数字无回车提交、非法草稿、Esc、打开/关闭、退出及单目标准入。独立历史 schema 整组 **48 passed / 26.08 s**。14–23 版软件样本实由历史写入器 `f284db36` 生成，当前读取后写 24，测试逐字段要求只去除旧 Ground.enabled 并更新版本。不能直接保存带旧 CDC 引用的工程。这些整组有重叠，不相加作为覆盖总数。

正常源冻结后，Ground GAS 输入、格式、双目标产物检查、SX1278 普通双端工程、Host 场景、真实 GCC 分析与 ARM 检查整组 **307 passed / 920.65 s**。首轮 47 failed / 259 passed，47 项均发生在导致旧格式夹具无法构造的过时断言中。修正夹具后的整组 306 passed / 1 failed。其唯一失败的两个相邻 Ground 质量检查输入之间，活动 core 的 payload 摘要改变，真实身份校验拒绝了旧输入。最后一轮在冻结源上完整执行通过。[输入变化](target-check-input-change.json)


功能库的真实窗口探测对 ESKF15 先取消、再应用。两次操作后的正式 owner 依次为 KF6、ESKF15。

本页的六构型软件门禁不覆盖实板，也不证明普通任务栈或 ISR 最坏时间。当前可见的失败及修复前结果与成功日志一同保留。[回归与故障原始日志](tests-and-failures.zip) · [软件批次文件清单](code-files.txt)
