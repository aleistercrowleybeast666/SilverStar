# SSFC1.0 / SSGS1.0 与 F103 Ground 软件交付

本目录记录实际板型、生成、ARM 编译、有限栈证明及 GUI 消费验证。源码提交为 `6fed5b639d0835de7874a74db25a63ab0da814ad`。没有执行硬件连接、烧写或实物动作；两块新板继续标记 `verified=false` / `software_candidate`。资源连线、封装、时钟和传感器安装假设见 [板型说明](../../../public/SCG/SSFC1_0_SSGS1_0.md)。

## 配置与交付入口

推荐最终成对工程为 `D:/python_software/SilverStar/dist/pf1117-boards-current/SSFC1_0_SSGS1_0_Current.zip`。完整解压到短路径，在 SCG 打开根目录 `SSFC1_0_SSGS1_0.ssproject`；内置板型不需要 CubeMX 导入。在第三页明确选择两端及新的输出目录。包中保留生成源、原始日志解码包、Release/Debug ELF/BIN/MAP/.su、严格栈报告和 `MANIFEST.json`。源程序生成 authority 与独立打包 EXE 的 authority 不同，使用新 EXE 时应正常生成后再按其当前输入检查；旧报告不自动变为新 EXE 的当前结果。

F103/E19 软件参考包为 `D:/python_software/SilverStar/dist/pf1117-boards/F103_E19_Ground.zip`，打开 `software-inputs/E19_Software.ssproject`。这是明确的 synthetic CubeMX 参考输入；配置同时包含飞控，但该包只交付 Ground。原输入与缓存快照随包完整保留。旧成对包 `dist/pf1117-boards/SSFC1_0_SSGS1_0.zip` 保留原 O 工程证明，不作为最新 Tools 的生成证据。

最终路径、包大小/SHA256、逐文件清单和只读搬迁检查见 [交付摘要](receipt.json)。完整文本收据在 [runs/index.json](runs/index.json) 所列 `.json.gz` 中，每条原文件记录都保留路径、字节数、SHA256 和原始 UTF-8 文本（少数非 UTF-8 用 base64），写入后全部独立解压核验。它们不包含编译产品。完整工程产品留在独立 `dist`，没有进入 Git。

工具链为 Arm GNU Toolchain 14.3.Rel1（GCC 14.3.1）、GNU Make、Host GCC、Python。实际 Windows 路径在每条完整命令收据中。将工具加入 PATH，在解压根目录运行：

```text
mingw32-make -C Flight_Controller CONFIG=Release all artifact-check architecture-check power10-check static-analysis stack-report
mingw32-make -C Ground_Station CONFIG=Release all artifact-check architecture-check power10-check static-analysis host-tests stack-report
```

将 `CONFIG` 改为 `Debug` 执行另一配置。H7 可显式传入 `GCC_PATH="D:/Arm GNU Toolchain/14.3 rel1/bin"`。F103 包只使用 Ground 命令。输入、编译器、对象或库改变都会使旧精确证明失效，不能复制旧报告强行通过。

## 构型与有限证明

H7 TIM6 的实际 owning handler 原来没有分发到 HAL；本轮修正为调用 `HAL_TIM_IRQHandler(&htim6)`，由既有 TIM6 回调推进 HAL tick。保留真实修复前失败、生成文本回归和完整 IRQ TU 的 Host analyzer 正反例。BMI088、NEO-M9N、MMC5983MA 与 E28-2G4M27SX 使用现有驱动，未另建重复 owner。C071 使用 E28-2G4M12SX、USART2/外部 USB-UART，保留无 RTOS 架构。

Ground 独立严格入口核对完整 Make/source graph、CPP/GAS 依赖、编译器、每个 `.su`、对象及真实 ELF。C071 仅准入完整 SSGS 板型；旧裸 C071 自定义配置没有泛化放行。真实 Thumb-1 跳表及 split POP/BX 返回经有限机器码证明；未知 guard、地址、SP 或别名仍拒绝。Ground 回调固定对象/ABI 槽与实际调用路径被封印，不把注册表或未知指针当作安全目标。

F103 原 1024 B MSP 实际不足：Release 上界 3912 B、Debug 3424 B，旧严格检查正确拒绝。修改 owning F103C8 插件 linker 保留 8192 B；没有修改用户已导入的 linker 或单补生成副本。真实链接为 20 KiB RAM，已用 12540 B，其中含 8196 B 栈保留及对齐，余 7940 B。无 RTOS、无 FPU；M3 使用全部 16 个优先级与 NMI/HardFault，36 B 异常帧。向量完整 extent、59 个硬件槽、7 个尾部零值及 BootRAM 常量分别检查。C071 保持 4 个实际优先级，不套用 M3/M4/FPU 假设。

| 目标 | MSP bytes | Release 上界 / 余量 | Debug 上界 / 余量 |
|---|---:|---:|---:|
| SSFC1.0 H743 | 8192 | 6828 / 1364 | 5292 / 2900 |
| SSGS1.0 C071 | 4096 | 1920 / 2176 | 1360 / 2736 |
| F103/E19 Ground | 8192 | 3912 / 4280 | 3424 / 4768 |

H7 各任务的 Release / Debug 余量分别为 Device 380/904、INS 604/804、Estimator 1104/1648、Flight 680/1932、Logger 688/1056、Serial 1572/3028、Telemetry 1820/2084、Idle 256/256 bytes。保持既有 256 B 最小门槛。物理 RAM 余额、静态上界与 Host 耗时不表示硬件高水位、WCET、导航精度或可飞行资格。

## 验证范围及 epoch

O 是独立复现 N 审阅的 H7 与 M 审阅的 C071，随后正常同步当前配置 authority，但保留策略使 H7 的已生成 Tools 仍为 index28 epoch。该次 H7 12、C07114 门禁通过是真实历史结果。最终 P 另从空目录普通 ALL 生成，使用当前 Flight index30/Ground index4；H7 644 个、Ground 175 个 C/H/ASM/linker/mk 输入与 O 原字节相同。P 的 H7 十二、C071 十四门禁全部实际退出0，源输入前后无变化；独立复核各配置 H7 534、C071 259 个编译物与 O 及已审 case 全部同 SHA。所有命令退出码见摘要及 `candidate-p-Flight_Controller-final-validation`、`ssgs-current-validation` 原收据，不用 O 的通过冒充 P。

F103 C 在 owning MSP 修正后普通生成并通过两配置 ARM/artifact/architecture/P10/analyzer/Host，strict 按当时未入册身份拒绝。完成实际 CRT/HAL/MSP/对象审阅后只追加两个精确 case，再普通生成独立 D：两个配置各 229 个编译物与 C 原字节相同，14 个实际门禁全部退出0。保留 C 入册时写明 reproduction pending 的原收据，用 D 收据闭合，没有改写历史状态。Ground 原 C071 两个 case 原字节未变。

- 最终 M3、原 C071 runtime、Ground/Flight 呈现、原 F103 reference 组合一次运行：100 passed；早期94项与全部原始失败另存。不是整个 SCG 测试全集。
- C071 与 F103 各实际8项严格入口检查：基线通过，改源/删 source graph 项/缺 `.su`/改对象/多对象/改 sealed case 六类均拒绝，恢复原字节及时间后再次通过。
- 两个 Ground 真实 `BuildRunner → QualityBatch → report → 保存/重载 → BuildPage → stale 隐藏` 路径通过，消费的是实际生成报告。截图来自明确的 Qt offscreen；不当作原生鼠标操作或实屏验收。
- Git clean → blob → smudge 最后148个敏感路径原字节相同；新case/index/review文档、C0 vendor、板插件与 F103 owning linker 保留精确字节。84个 C0 vendor 文件与声明的 SDK 选择 SHA 全同。原厂许可及来源未删。

所有 analyzer 结果来自实际 `-fanalyzer` 编译，ARM 结果含实际链接，P10 为 emitted 检查。P10 仍报告 critical-contract review NOT PROVEN；本轮没有声称全固件任意配置、全部函数语义或原始 Power of Ten 合规，也没有增加阈值例外。F103 旧完整导入的普通 artifact 检查仍提示旧 IRQ inventory 未提供；新严格 case 单独核对其实际完整向量与五个必须强处理函数，不能外推到其他导入工程。

## 保留及待测

所有 source 输入、CubeMX 来源、log/decoder、旧诊断、未准入 case 和当前工程保留。根负责人按完整归档成员及当前文件身份复核后，删除本任务 13872 个重复编译文件、2375668814 bytes；其余2360个文件、726476848 bytes及保护 ZIP/manifest 经独立后检未变。见 [执行收据](../delivery/board-duplicate-cleanup.json)、[后检](../delivery/board-duplicate-cleanup-verification.json)。原清单已由根负责人按原字节 gzip 归档，本目录只引用同一份，不重复存放。O/P/D、未知旧 `.work` 和用户内容不在删除范围内。

硬件未测：电源、封装、晶振、引脚与复用、DMA/cache/中断时序、UART吞吐、射频前端/空口/天线、存储满盘/掉电、安装/噪声/磁校准、栈高水位、WCET、真实传感器与飞行性能。GUI 原生显示问题由根报告单列，本目录不宣称已解决。
