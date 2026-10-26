# H743ZI 静态构建候选

本候选用于板卡设计前的编译、分析和栈配置检查，不能作为已上板配置。
GUI 布局保持不变。ESKF20、InEKF15、InEKF20 可选择并构建，显示为
“H7 离线检查通过，未上板”；该状态仅针对下述固定构型的 Release 软件检查。
没有增加已验证飞行默认值，也没有把软件检查提升为上板或飞行验证。
成功编译或 `-fanalyzer` 无报错不等于整机静态验收通过。

## 固定输入

输入为用户的 `SSFC_1/SSFC_1.ioc`，原文件未修改，其 SHA-256 为
`234d352e68fca1e9a0689a15007966830f53d0b8d6284f4f607ffa848af61099`。
可复现的派生输入保存在
[`SSFC_H743ZI_Static.ioc`](../../../apps/SCG/tests/fixtures/h743_static/SSFC_H743ZI_Static.ioc)。
派生输入由 CubeMX 6.15.0、STM32Cube FW_H7 V1.12.1 实际生成，精确器件为
STM32H743ZIT6（2 MiB Flash），不能用 H743ZG 的 1 MiB 工程替代。

时钟为 25 MHz HSE 无源晶体、PLL1 M=5/N=192/P=2，CPU 480 MHz、HCLK 240 MHz、
APB 120 MHz；保持 SWD。480 MHz 是编译候选的假设，实物芯片版本、供电和晶体尚未验证。
TIM6 提供 HAL tick，FreeRTOS CM7 r0p1 端口拥有 SVC/PendSV/SysTick，
CubeMX 不再重复生成这三个异常处理函数。

| 用途 | 静态测试分配 |
|---|---|
| SWD | PA13 / PA14 |
| HSE | PH0 / PH1 |
| BMI088、BMP390、MMC5983MA | I2C1，PB8 / PB9 |
| 可选第二颗 BMI088 | 独立 I2C2，PB10 / PB11 |
| NEO-M9N | USART1 PA9 / PA10，RESET PC6，PPS PD6 |
| E28-2G4M27SX | SPI1 PA5/PA6/PA7，NSS PC0，RESET PC1，BUSY PC4，DIO1 PC5，TX_EN PD3，RX_EN PD4 |
| 维护串口 | USART2 PA2 / PA3，921600 / 8N1 |
| 日志存储 | SDMMC1 PC8–PC12 / PD2，检测 PG2；生成的阻塞 FatFs 接口 |
| START 测试 GPIO | PC13，仅用于满足现有 START 配置契约，无点火负载 |

这不是 PCB 引脚定稿。I²C 上拉/时序、SPI 模式/速率、射频前端极性、GNSS 配置及 PPS 延迟、
SD 卡路径均未通过电气验证。双 BMI088 只验证实例数增加后的构建、资源分配和静态占用；
仍只选择一个主源，没有增加冗余融合或故障投票。

导航初始化、同位置假设、噪声与初始协方差是脚本明确设置的静态测试值，
不是实测标定或可直接用于飞行的参数。磁力计时间上界验证标志仍为 0。
三种估计器仍需显式启用 `software_validation_build=1` 并填写必要参数；
GUI 允许选择，构建时不绕过未配置输入检查。`qualified_timing_profiles` 仍为空。

## 构建与复现

在仓库根目录运行。需要项目 Python 环境、CubeMX 6.15.0/H7 包、Arm GNU 14.3.Rel1、
GNU Make 和 Host GCC。先把派生 IOC 放入新的输出目录，避免覆盖任何用户工程：

```powershell
$candidate = Join-Path (Get-Location) '.work/h743_reproduce/cube'
New-Item -ItemType Directory -Path $candidate -ErrorAction Stop | Out-Null
Copy-Item apps/SCG/tests/fixtures/h743_static/SSFC_H743ZI_Static.ioc $candidate
$ioc = Join-Path $candidate 'SSFC_H743ZI_Static.ioc'
@"
config load $ioc
project name SSFC_H743ZI_Static
project toolchain Makefile
SetStructure Advanced
SetCopyLibrary "copy only"
isPluginError "Clock Configuration"
isPluginError "Pinout & Configuration"
config save $ioc
project generate
exit
"@ | Set-Content .work/h743_reproduce/generate.script
& 'C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/jre/bin/java.exe' `
  -jar 'C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/STM32CubeMX.exe' `
  -q .work/h743_reproduce/generate.script

& .venv/Scripts/python.exe apps/SCG/tools/validation/h743_static_validate.py `
  --cube-project .work/h743_reproduce/cube --output .work/h743_reproduce/release `
  --dual-imu --run --config Release `
  --arm-gcc 'D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gcc.exe' `
  --make 'D:/msys64/ucrt64/bin/mingw32-make.exe' `
  --host-gcc 'D:/msys64/ucrt64/bin/gcc.exe'
```

工具路径按本机修改。Debug 使用新的 `--output` 和 `--config Debug`。
输出必须位于本仓库 `.work` 的新子目录，已有输出会被拒绝。
不加 `--run` 仅生成工程；不会运行构建，也不会宣称已验证。
脚本不调用烧录、调试连接或串口操作。

每个案例保存原生工程、配对解码器、各检查的完整日志、退出码、生成源文件清单及 ELF SHA-256。
`summary.json` 汇总真实结果。`--run` 的退出码只覆盖实际执行的六项软件检查：
编译链接、架构、项目 Power of Ten 文本检查、`-fanalyzer`、链接产物与任务栈。
全部通过才返回 0，生成失败或任一检查失败返回 2。
`whole_program_stack_acceptance`、上板及飞行状态独立保存；返回 0 也不改变它们。

本次保留的完整本地证据位于 `.work/h7_20261025`。
`software_release_v3` / `software_debug_v3` 保存确定性修复和输入审阅后的最终案例。
`verified_release` 保留此前重生成时暴露的身份失败；暂停时被中断的日志保留为
`*.paused.log`，续跑重新执行检查，不把中断结果计为通过。
早期 `final` / `final_debug` 以及
[首轮精简结果](../../../apps/SCG/tests/fixtures/h743_static/validation_20261025.json)
保留当时的失败，不追改为成功。最终结果另附于同目录的收尾记录。
最终[收尾记录](../../../apps/SCG/tests/fixtures/h743_static/validation_closeout_20261026.json)
保存 7 个案例的命令、退出码、ELF/源清单/栈报告/解码包哈希及各组测试结果。
这些记录不替代完整日志，也不是硬件测量记录。

## 本次软件验证结果

Release 的 ESKF20、InEKF15、InEKF20 和双 BMI088 ESKF20，以及 Debug 的三种单 IMU
案例，共 7 个全新生成案例，六项软件检查均返回 0。独立诊断模式仍按约定返回 2。
最终 7 个 `.ssdecoder` 均由 FLP 的正式包读取器通过结构、摘要和语义校验；
没有使用 H7 实测飞行日志，也没有验证实时链路。

| 执行范围 | 通过 | 跳过 |
|---|---:|---:|
| 最终 SCG 专项回归（生成器、传感器、增强导航、平台及身份） | 286 | 14 |
| 日志、存储、安装参数、任务调度及维护接口 | 109 | 0 |
| 配置协调及地面站指示灯 | 31 | 0 |
| 栈检查器正向与拒绝用例 | 88 | 0 |
| GSHC 任务快照、就绪状态及诊断描述 | 51 | 0 |
| FLP 任务快照、解码器及导航记录合同 | 68 | 0 |

各组可能重叠，不累加为覆盖率或全仓库测试数。14 项跳过均因真实完整原生 USB CDC
输入未配置，未被记为通过。完整 JUnit、日志和修复前失败记录保留在本任务目录。

## 内存与检查边界

数据、静态任务栈和 DMA 缓冲区位于 512 KiB AXI SRAM（0x24000000）。
DTCM 顶端独立保留 8 KiB MSP，未把分散的 RAM 容量相加冒充连续空间。
当前只支持声明清楚的 `legacy` 链接布局；H7 自动内存重排尚未支持。
DMA 后端在 D-cache 开启时拒绝缓冲区，尚未实现和验证缓存维护策略。

估计任务原有 4096 B 对 Release ESKF20/InEKF20 的已知路径只剩 80 B，
因此增强估计器启用时增加至 5120 B，其他估计器保持原分配。
任务检查采用实际 ARM ELF、编译器 `.su` 和反汇编调用关系，核对只读回调表、
实际调用点、源文件与完整编译输入身份。它不等于整个任务或中断的安全证明。

Release 下各任务最坏已知路径（含 256 B 上下文预留）如下，单位为字节：

| 任务 | 配置 | ESKF20 / InEKF20 | InEKF15 | 最小余量 |
|---|---:|---:|---:|---:|
| Device | 2560 | 2188 | 2188 | 372 |
| INS | 3072 | 2336 | 2336 | 736 |
| Estimator | 5120 | 4016 | 3824 | 1104 |
| Flight | 4096 | 3376 | 3376 | 720 |
| Logger | 3072 | 2344 | 2344 | 728 |
| Serial | 6144 | 4440 | 4440 | 1704 |
| Telemetry | 4096 | 2160 | 2160 | 1936 |
| Idle | 512 | 256 | 256 | 256 |

双 BMI088 的 ESKF20 案例具有相同的任务路径上界；这不证明并发采样时序或总线吞吐量。

普通 `stack-report` 的未知回调、动态帧、递归和源身份约束保持失败关闭。
新增 `check_task_stacks.py --diagnostic` 只输出实际 ELF 的分配、直接路径与未解决边界，
总是以 2 退出并标记 NOT PROVEN；不会输出未证明任务的“可用余量”。
256 B 上下文预留覆盖所用 CM7 FP 端口的任务异常保存，MSP/main/中断嵌套仍需独立证明和实测。

## 本轮修复及仍待验证的边界

- BMI088 的实例层已归入适配目录；BMP390/MMC5983MA 的原生层改用自己的样本类型和有类型的直接总线接口，System 映射留在适配层。I²C/SPI 分别编译和进行 Host 故障注入。
- MMC5983MA 测量超时现在返回明确超时并累计计数，不再混成普通 I/O 错误，不发布新样本。保留修复前失败及修复后正常、超时、内部状态损坏用例。
- 静态测试脚本仅在私有派生输入中移除 CubeMX 的精确未用堆别名块，前提为 LFN=2、EXFAT=0、LOCK=2、REENTRANT=0；未知配置拒绝，原 IOC/源文件不改。没有放宽通用导入器或架构规则。
- 项目 Power of Ten 文本检查和实际 `-fanalyzer` 已通过固定构型检查；关键契约人工验收仍为 NOT PROVEN，不宣称原始 Power of Ten 或 NASA 认证。
- BMI088 profile 的实际链接表、启动回调 Release/Debug 调用点及 H7 完整输入依赖纳入失败关闭检查。冻结输入清单与检查器配对；改动源、头文件、汇编、链接脚本或构建声明须重新审阅，不能混搭单独已知哈希。
- 原基线的 5 个身份回归已按实际版本变化审阅并修复。通用来源审阅不自动授权新的编译闭包；负向用例继续拒绝未知重组。参考覆盖副本同步到实际生成器的检查器版本。
- 真实重生成暴露了自动依赖补齐中的集合遍历顺序问题：同一选择在不同进程中可能出现不同组件顺序及配置/解码摘要。现在保留既有选择顺序追加依赖，跨 8 个进程种子检查一致性；不重排用户已有列表，不忽略配置摘要。
- 输入审阅 v3 对照既有实际编译的依赖图核对确定性生成预期，新增身份仅允许精确摘要常量与声明顺序的已审阅变化；最终构建再用实际 `.d`、`.su` 和 ELF 验证。冻结清单本身不是构建通过证据。完整审阅收据保留于 `backend_closeout/h743_input_review_v3.json`。
- MSP/main/ISR 嵌套、完整关键契约人工审查、MCU 最坏执行时间和栈高水位仍为 NOT PROVEN。软件任务报告不能替代这些证据。
- 自定义硬件尚无板卡身份，因此不导出可供 GSHC 使用的 `.ssmission` 快照；固件及精确日志解码包照常生成，不伪造板卡 ID。

GSHC/FLP 的已有任务快照、导航就绪状态和精确解码器读取合同做了相关回归，
未修改这两个程序的实现，也未增加离线状态替代实机 READY 的路径。
SCG 界面布局未调整；仅修复外置设置目录初始化时错误沿用应用目录边界的问题。

## 来源与例外

- HAL、CMSIS 器件支持来自本机 STM32Cube FW_H7 V1.12.1；保留各 `LICENSE.txt`，ST 部分为 BSD-3-Clause，CMSIS Core 为 Apache-2.0。
- FatFs R0.12c 来自同一包，保留 ChaN 原有许可与免责声明。
- FreeRTOS 公共内核为仓库已有 V11.3.0；CM7 r0p1 的 `port.c`、`portmacro.h` 从
  [官方 V11.3.0 标签](https://github.com/FreeRTOS/FreeRTOS-Kernel/tree/V11.3.0/portable/GCC/ARM_CM7/r0p1)取得，保留 MIT 许可。
  两文件 SHA-256 分别为 `109904c180190083d8325dd12e4a627f082fb69ca49f06ece242fcb8fbca7c4d`、
  `b87c63cfc45a0b9df9f9ae02bdfbaa395f25cc17d72a3de11c69f48a2e672d18`。
- H7 平台适配从本仓库已有平台实现派生，复用平台 API 和静态资源发布方式，不新增运行时回调注册表。
- first-party 保持严格告警及 `-fanalyzer`；第三方采用既有独立策略。CMSIS/HAL 头作为系统头处理，
  避免将其已知转换告警误计为项目代码告警；这不表示第三方代码无告警、无缺陷或满足原始 Power of Ten。

板卡完成后再测：硅版本与时钟、电源和缓存、各驱动初始化/超时/断流、GNSS/PPS 与磁力计时间界、
SD 故障、任务高水位与最大中断嵌套、最坏执行时间及导航精度。上板测试和飞行验证继续分开记录。
