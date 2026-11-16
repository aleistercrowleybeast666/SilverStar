# SSFC1.0 / SSGS1.0 软件板型与工程

在 SCG 打开 [SSFC1_0_SSGS1_0.ssproject](../../../apps/SCG/examples/SSFC1_0_SSGS1_0.ssproject)，检查“硬件与通信”两端摘要，再在“检查与生成”选择两端、指定输出目录并生成。此工程使用内置板插件，不需要再次导入 CubeMX。选择板卡本身不会替换已有工程的传感器；使用该完整示例可同时获得配套设备和资源引用。

两块板均为 **软件候选、实板未验证**。这里的型号、封装、供电、时钟和引脚是明确的设计假设，不是对用户 PCB 的识别。必须先与实际原理图核对；安装方向、传感器噪声、GNSS/IMU 杆臂、磁环境、射频前端和天线均未实测。UI、工程文件和插件均保留未验证状态。

## SSFC1.0

MCU 为 STM32H743ZIT6（LQFP144、2 MiB Flash），假设 25 MHz 外部晶振，CPU 480 MHz、HCLK 240 MHz、APB 120 MHz。保留 SWD PA13/PA14。板内固定资源如下：

| 功能 | 实际资源与设计连线 |
|---|---|
| BMI088 | I2C1：PB8/SCL、PB9/SDA；加速度计地址 0x18、陀螺仪 0x68 |
| MMC5983MA | 同一 I2C1，地址 0x30；已有驱动按 20 Hz 使用 |
| NEO-M9N | USART1 PA9/TX、PA10/RX，921600 8N1；复位 PC6、PPS PD6 |
| E28-2G4M27SX | SPI1 PA5/SCK、PA6/MISO、PA7/MOSI；NSS PC0、RESET PC1、BUSY PC4、DIO1 PC5；TX_EN PD3、RX_EN PD4 |
| 维护串口 | USART2 PA2/TX、PA3/RX，921600 8N1，接外部 USB-UART 桥 |
| SD 卡记录 | SDMMC1 PC8–PC12、PD2；卡检测 PG2；存储仍由现有 H7 存储适配拥有 |
| START 测试指示 | PC13/STATUS_LED，满足现有 START 动作合同；仅指示输出，**不是点火或火工品驱动** |

USART1/2 RX 分别用 DMA1 Stream0/2（环形），TX 分别用 Stream1/3（普通）；HAL 时间基准为 TIM6，RTOS 使用既有 H7 port。TIM6 IRQ 明确转交 HAL_TIM_IRQHandler，回调只为 TIM6 递增 HAL tick。SD 的原厂输入保存 provenance，并使用现有经哈希约束的 owning replacement；不另外创建存储实现。

选择 MMC5983MA 是因为已有实际驱动、三轴 ±8 G/18 bit 输出与 SET/RESET 能力符合当前磁力计入口。厂商 0.4 mG 噪声指标限定在其条件下，不能据此保证整机航向精度。磁铁、供电回路、大电流线和射频前端对磁场的影响仍需布局与实测；硬铁/软铁校准、安装方向和倾角不可用示例值代替。

示例使用现有 ESKF20 软件验证模式和 coning2/sculling2 INS，保留 SSLOG。初始协方差、噪声、重力、已知航向、磁场参考和同位安装确认是用于软件构建的显式假设，需在功能属性中核对。ESKF20 没有该板的已测时序配置，不能报告为飞行合格或实时时限已证明。运行范围与实例仍由原任务模型拥有。

## SSGS1.0

MCU 为 STM32C071FBP6（**TSSOP20 GP 引脚版本，不是带 N 的替代封装**），128 KiB Flash、24 KiB RAM，使用内部 HSI48、48 MHz；保留 SWD PA13/PA14。

| 功能 | 实际资源与设计连线 |
|---|---|
| E28-2G4M12SX | SPI1 PA5/SCK、PA6/MISO、PA7/MOSI，3 MHz；NSS PA4、RESET PA0、BUSY PA1、DIO1 PB3/EXTI3 |
| PC 串口 | USART2 PA2/TX、PA3/RX，921600 8N1，外部 USB-UART 桥 |
| 串口 DMA | RX DMA1 Channel1、TX Channel2，普通模式；接收使用现有 ReceiveToIdle DMA 字节流入口 |
| 中断 | SysTick、EXTI2_3、DMA1_Channel1、DMA1_Channel2_3、USART2 |

这是现有 GroundBridge/GSP/SS-TM-S 的无 RTOS 串口地面站，未恢复 MCU 原生 USB CDC。历史裸 C071 自定义工程仍不因此被放行；当前准入仅为完整 SSGS1.0 精确板型。共享链路仍沿用当前协议、速率和空口默认，两端模块功率分别为 27 dBm / 12 dBm。

## 构建和结果边界

安装项目要求的 Arm GNU 与 GNU Make，将其加入 PATH。生成后在所选工程根目录执行（Windows 可用 mingw32-make 代替 make）：

```text
make -C Flight_Controller CONFIG=Release all artifact-check architecture-check power10-check
make -C Flight_Controller CONFIG=Debug all artifact-check architecture-check power10-check
make -C Flight_Controller CONFIG=Release static-analysis stack-report
make -C Flight_Controller CONFIG=Debug static-analysis stack-report
make -C Ground_Station CONFIG=Release all artifact-check architecture-check power10-check static-analysis host-tests stack-report
make -C Ground_Station CONFIG=Debug all artifact-check architecture-check power10-check static-analysis host-tests stack-report
```

飞控产物位于 `Flight_Controller/build/FCCG/SilverStar_H743ZI/<配置>/`；地面站 Release 在 `Ground_Station/build/`、Debug 在 `Ground_Station/build/Debug/`。地面站两个配置均保存真实 `.su` 和调试信息供软件栈分析；调试信息不增加烧写 BIN 内容。构建、保存和导出仍是不同操作。

严格栈入口针对已审查的完整输入和 Arm GNU 14.3.Rel1 编译物；修改源码、配置、编译器或链接结果后会拒绝旧证明，需要重新审查，不能复制旧报告使其变为当前。地面站报告是 `ground-stack-budget.json`，核对实际 Cortex-M0+ 的 main/reset、全部已链接向量、4 级可配置中断与 NMI/HardFault，每层保守使用 36 B 基本异常帧，采用 4096 B MSP 和既有 256 B 最小余量。它不含 RTOS 任务；SCG 的检查页面按真实 MSP 范围显示结果。飞控报告仍按现有任务和 H7 中断上下文规则处理。

验收以本轮实际命令收据为准；P10 文本检查通过不表示关键合同、栈、时序和硬件全部通过。硬件待测包括电源/晶振、所有引脚与复用、DMA/中断时序、串口吞吐、空口兼容和链路预算、存储掉电/满盘、温漂、磁校准和导航性能。本文不授权烧写、连接设备或实物动作。

## 来源

- [STM32H743ZI 数据手册](https://www.st.com/resource/en/datasheet/stm32h743zi.pdf)、[STM32C071FB 数据手册](https://www.st.com/resource/en/datasheet/stm32c071fb.pdf)。
- [MMC5983MA Rev A 官方数据手册](https://www.memsic.com/Public/Uploads/uploadfile/files/20220119/MMC5983MADatasheetRevA.pdf)。
- [Ebyte E28 系列官方产品页](https://www.ebyte.com/product/527.html)。
- [STM32 Cortex-M0+ 编程手册 PM0223](https://www.st.com/resource/en/programming_manual/pm0223-stm32cortexm0-mcu-programming-manual-stmicroelectronics.pdf)。

板插件内 `hardware-provenance.json` 保留 CubeMX 生成输入与修改说明；C0 MCU family 的 `vendor-provenance.json` 记录 STM32CubeC0 V1.4.1 的实际选择文件和 SHA256，原厂 HAL/CMSIS 许可随选中子集保存。H7 继续使用既有 STM32CubeH7 V1.12.1 owner。
