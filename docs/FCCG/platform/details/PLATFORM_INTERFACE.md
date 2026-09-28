# SilverStar Platform Interface

> 文档版本：0.0.12
> 适用范围：SilverStar 0.0.12

Platform抽象通用MCU能力，不抽象传感器。公共头位于`Platform/Inc`，当前实现位于`Platform/STM32F4`；只有后者可以包含STM32/HAL/CubeMX类型。

## 1. 返回值与资源ID

`PlatformResult`固定表达OK、already initialized、not ready、busy、timeout、invalid argument、unsupported和I/O error。每类外设使用平台逻辑ID，例如`PlatformUartId`、`PlatformSpiId`、`PlatformGpioId`；这些ID不是vendor实例号或GPIO地址。

`Generated/Inc/project_resources.h`把项目语义资源映射到Platform ID；`Generated/Src/platform_resources.c`把Platform ID映射到`huart1`、GPIO pin等当前Target物理资源。`Platform/STM32F4`只通过`platform_stm32f4_resources.h`的窄getter取得资源，不认识JY901B、M9N、SX1281或SilverStar板名。

## 2. UART

公共能力：初始化、同步/异步写、读取、flush/stop/restart RX、baud读写、队列计数、诊断和周期Process。

STM32F4 backend拥有：

- Receive-to-Idle DMA和128-byte DMA buffer；
- 三路静态RX ring及Console普通/优先TX ring；
- HAL UART/DMA callback；
- 断流、discard、overrun/framing/noise/parity、restart和transport统计；
- 异步TX分块与优先队列选择。

Device只调用`PlatformUart_Read/Write`，不能看到DMA position、HT/TC、HAL handle或callback。Device parser必须正确处理任意分片和多frame合并。

## 3. SPI、I2C与ADC

- `PlatformSpi_Write/Transfer`执行有界事务；NSS等片选由设备通过Board逻辑GPIO控制；
- `PlatformI2c_Write/Read/MemoryWrite/MemoryRead`提供有界阻塞事务，使用7-bit设备地址；不提供通用WriteRead/repeated-start事务。backend按实际inventory与consumer启用；
- `PlatformAdc_Read`返回raw count，电压比例与业务单位由`Devices/Power/InputVoltage`转换。

这些接口不包含设备寄存器、地址常量或协议命令。

## 4. GPIO与IRQ事件

`PlatformGpio_Write/Read`使用物理电平（0低、1高）；active-low等业务极性由Device/FlightLogic实现转换。`PlatformGpio_IrqConsume()`每次消费一个已累计事件；backend可累计多次中断，不能只保留易丢失的单bit脉冲。

STM32 EXTI callback只匹配Platform表并增加计数。ISR不得执行SPI、打印、协议解析、System调用或注册Device回调。SX1281在自己的Process中消费DIO1并读取radio IRQ状态。

## 5. Time与Critical

- `PlatformTime_Us/Ms`是单调时间；`PlatformTime_Init`必须验证可用性；
- `PlatformTime_DelayMs`只用于无法避免的有界bootstrap事务，不得在周期Device状态机中代替deadline；
- `PlatformCritical_Enter`返回前一中断状态，`Exit`必须恢复该状态，不能无条件开中断；
- System Time在Platform成功初始化后才发布ready，Mission Time与UTC映射建立在同一单调轴上。

## 6. 公共头禁区

`Platform/Inc`以及可移植层不得出现：

```text
HAL_*, stm32*, GPIO_TypeDef, UART_HandleTypeDef, SPI_HandleTypeDef
GPIOA/GPIO_PIN_x, huart*, hspi*, main.h, cmsis_gcc.h
JY901B, NEO-M9N, SX1281或其他具体设备名
```

MCU backend同样不得认识具体设备或具体Board；它只消费由项目胶水提供的Platform资源getter。具体设备和Board服务使用哪个逻辑资源由`project_resources.h`表达，具体HAL handle/pin由`platform_resources.c`表达。

## 7. 新backend最低交付

1. 实现目标实际使用的全部Platform函数，未使用能力也需明确返回`PLATFORM_UNSUPPORTED`或由Target不链接；
2. 建立项目逻辑资源与物理资源映射、Board服务和Target manifest；
3. 实现OS port、SysTick/HAL tick等目标时间边界；
4. 提供静态缓冲、临界区、IRQ事件和无heap证明；
5. 在Host接口测试之外完成backend语法/ARM构建、外设loopback和实际设备测试；
6. 若有D-Cache/DMA一致性需求，先扩展最小Platform DMA cache契约，不得让Device直接调用vendor cache API。

当前只完成STM32F407 backend的实现、静态检查和ARM编译；其他MCU仅为架构可扩展目标，不得宣称已支持。

## 当前provider与绑定边界

STM32F4 I2C与PWM已有软件实现；Classic CAN为reserved，不能提供给普通consumer。provider按实际inventory及选中consumer启用，不能因源码存在而全量编译。CubeMX版本、HAL timer timebase发现及Verified Board固定映射的闭合规则见[Build与Targets](BUILD_AND_TARGETS.md)。
