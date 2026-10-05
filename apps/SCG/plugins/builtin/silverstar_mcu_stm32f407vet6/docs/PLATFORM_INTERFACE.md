<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

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
- `PlatformI2c_Write/Read`提供阻塞式7-bit master事务，`PlatformI2c_MemoryWrite/MemoryRead`使用Platform自有的8/16-bit寄存器地址枚举；不提供伪装成任意repeated-start的`WriteRead`；
- `PlatformAdc_Read`返回raw count，电压比例与业务单位在Board Power Service转换。

这些接口不包含设备寄存器、地址常量或协议命令。

## 4. GPIO与IRQ事件

`PlatformGpio_Write/Read`使用逻辑电平。`PlatformGpio_IrqConsume()`每次消费一个已累计事件；backend可累计多次中断，不能只保留易丢失的单bit脉冲。

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

0.0.12只完成STM32F407 backend的实现、静态检查和ARM编译；其他MCU仅为架构可扩展目标，不得宣称已支持。


## 8. FCCG Platform插件扩展与所有权

本节以及`tools/reference_overlays/platform/`中的I²C、Classic CAN和PWM实现属于FCCG，
不属于外部参考固件commit。reference importer先复制只读snapshot，再重放这些overlay；
最终manifest的`metadata.source_origins`分别标记`reference_base`和`fccg_extension`。

F407 Platform manifest声明资源header、getter、Platform ABI、CubeMX匹配规则和条件backend。
只有实际硬件inventory包含相应资源且已选Device确实分配该资源时，Source Graph才加入backend：

- I²C（supported，不等于硬件verified）：7-bit未左移地址、阻塞master读写及8/16-bit memory-register读写；公共ABI不含HAL常量，不声明DMA/IRQ或任意repeated-start。SCL/SDA必须Open Drain；NOPULL必须由Board的external_verified元数据或自定义snapshot绑定确认提供外部上拉证据；
- Classic CAN（reserved）：仍可盘点CAN/FDCAN库存，但普通consumer会在资源解析阶段被拒绝；当前不声明Filter、Router、Bus-Off恢复或实机验证；
- PWM（supported，不等于硬件verified）：仅接受CubeMX PWM Generation + `HAL_TIM_PWM_ConfigChannel`共同证明的普通CH1..4、edge-aligned up-counter、PWM1/PWM2。模式、极性、prescaler、ARR和基频均来自CubeMX，Device不能覆盖极性；0/100%使用forced inactive/active端点，中间duty恢复原PWM模式，Stop先置逻辑inactive再停channel。

HAL/CMSIS采用单一来源政策`plugin_payload_authoritative`：HAL、CMSIS、startup、linker和Platform backend来自本插件；自定义CubeMX快照只贡献受控的`Core/Src`和`Core/Inc`，其Drivers/CMSIS/startup/linker不得进入Source Graph。当前兼容门禁精确要求CubeMX 6.15.0与`STM32Cube FW_F4 V1.28.3`。

默认SS0.5没有I²C/CAN/PWM consumer，因此不编译这些backend，也不加入无关I²C/CAN/PWM代码。外部参考固件保持只读，以上能力只由FCCG overlay持有。
当前production support仍仅为STM32F407VET6/SS0.5；renderer可消费其他Platform契约不代表其他MCU已经验证。
