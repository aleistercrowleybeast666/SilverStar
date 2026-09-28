# SilverStar 0.0.9 平台规范

SilverStar 0.0.9是首次发布前的FCCG-ready reference firmware。本版把System、具体Device与MCU实现分离，引入独立Interfaces、Device Adapter、Board Service、FlightLogic组件、vendor无关Platform契约、薄Generated glue、显式Target manifest和官方FreeRTOS-Kernel V11.3.0。当前真实实现和编译目标仍只有STM32F407VET6；“可移植”表示依赖边界成立，不表示其他MCU已经受支持或上板验证。

## 1. 版本与兼容性

- 固件版本：`0.0.9`；日志构建标识：`SILV0009`；System Profile ID：`0x00000009`；
- AIR遥测协议正式名称为M0；wire兼容枚举保持`AIR_PROFILE_COMPACT_V0 = 0`，类型值、固定长度、字段偏移、token、字节序、5 Hz周期和无应用层CRC契约不变；
- 飞行日志格式正式名称为0.0；wire magic保持`SSLOG0`，文件头、Record header、little-endian和CRC-32/ISO-HDLC语义不提升；
- 既有SSLOG Record `0x01..0x19`的ID和`record_version=0`不因架构移动而改变；新增descriptor为`0x1A..0x1C`，从version 0开始；
- 串口维护协议正式名称与版本为0.0；命令、权限和响应语义不变；
- 0.0.9处于首次发布前阶段，不保留旧Provider、CMSIS-RTOS2、旧LoggerBus结构或旧构建图的兼容层。

固件版本与wire协议版本是独立概念。以后升级SilverStar版本不得自动升级AIR遥测协议M0、串口维护协议0.0或飞行日志格式0.0。

## 2. 架构

正式依赖方向为：

```text
System / APP / Algorithm / FlightLogic / Protocol
             |
             v
         Interfaces
             |
             v
 Device Adapter / Board Service
             |
             v
           Devices
             |
             v
      Platform public API
             |
             v
        MCU backend

Generated: project resource/log/metadata connection
Board: PCB-specific services
Target: selected modules + backend + vendor source set + OS port
```

硬性边界：

- System不知道JY901B、NEO-M9N或SX1281，只调用`Interfaces/Inc/system_*_if.h`中的直接函数；
- Interfaces没有Ops结构、函数指针vtable或运行期注册；每个Target在链接期只能提供一套具体实现；
- Device目录内的`Adapter/`可以同时包含Interface与该Device头，负责native sample到System公共结构、错误码、能力和配置的转换；Adapter不得依赖HAL、concrete Board或Target；
- Device core负责协议、解析、配置和状态机，只使用Platform API，不包含HAL、FreeRTOS、DMA回调模型或MCU句柄；
- Platform公共头只表达UART/SPI/I2C/GPIO/ADC/Time/Critical等通用MCU能力；STM32 backend通过opaque resource bridge取得句柄和pin，不知道JY901B/M9N/SX1281或当前PCB意义；
- `Generated/project_resources.h`表达当前Device到Platform ID的语义连接，`Generated/platform_resources.c`保存CubeMX handle/pin物理映射；Board只实现SilverStar PCB 0.5特有服务；
- Algorithm和Protocol不依赖HAL、FreeRTOS、Platform或具体Device。

换MCU原则上只新增/替换Platform backend、Target startup/linker/port和Generated physical mapping；换传感器原则上只替换完整Device Driver+Adapter、能力声明及少量Generated连接。若必须修改System/Algorithm/Protocol，说明原公共契约不足，需要单独接口评审。

## 3. 当前Target与硬件基线

`TARGET_PROFILE=SilverStar_F407`明确区分MCU `STM32F407VET6`、PCB `SilverStar 0.5`与firmware target `SilverStar_F407`，并选择：

- MCU/板：STM32F407VET6，PCB 0.5，Platform backend `STM32F4`；
- IMU/气压/可选磁场/硬件四元数：JY901B，USART1，230400 bit/s；
- GNSS：NEO-M9N，USART2，CubeMX侧921600 bit/s；模块端速率、ACK和掉电保持仍需上板确认；
- Console：USART3，230400 bit/s；
- Telemetry：E28-2G4M12SX/SX1281，SPI1 + NSS/RESET/BUSY/DIO1；
- 电压采样：ADC1_IN10；输出：`P_CONTROL1`、`P_CONTROL2`；
- Storage/Log Sink：SDIO + FatFs静态后端。

SX1281保持2473 MHz、12 dBm、SF10、800 kHz、CR4/5、16-symbol preamble、variable length和hardware CRC ON。JY901B、NEO-M9N的默认启动写入策略、导航速率目标和现有解析行为不因本轮重构改变。

## 4. Platform与中断

公共Platform API位于`Platform/Inc`：

- `PlatformUart_*`：后端拥有DMA/IRQ、接收环形缓冲、异步发送队列、baud和诊断；Device只读写字节；
- `PlatformSpi_*`、`PlatformI2c_*`、`PlatformAdc_*`：有界同步外设事务；
- `PlatformGpio_*`：逻辑电平与`PlatformGpio_IrqConsume()`事件消费；
- `PlatformTime_*`：单调微秒/毫秒时间与必要启动延迟；
- `PlatformCritical_*`：保存/恢复临界区状态。

STM32F407 UART使用Receive-to-Idle DMA并在backend内转入静态ring buffer；Device看不到Half Transfer、Transfer Complete或HAL callback。GPIO EXTI只累计Platform事件，SX1281进程主动消费DIO1，不注册Device callback。未来M7 backend如启用D-Cache，必须在Platform层增加并评审最小DMA cache契约，不得把cache操作泄漏到Device。

## 5. FreeRTOS与任务

- 官方快照：`ThirdParty/FreeRTOS-Kernel`，版本V11.3.0，保留官方目录、版权和`LICENSE.md`；
- 实际只编译`list.c`、`queue.c`、`tasks.c`和`portable/GCC/ARM_CM4F/port.c`；
- `configSUPPORT_STATIC_ALLOCATION=1`，`configSUPPORT_DYNAMIC_ALLOCATION=0`，不编译任何`heap_*.c`；
- APP使用`xTaskCreateStatic`、`vTaskDelay`和`vTaskStartScheduler`，不使用CMSIS-RTOS2；
- `SysTick`只驱动FreeRTOS，HAL tick继续由TIM1提供；
- `configMAX_PRIORITIES=8`，当前创建7个任务：Device/INS优先级7、Estimator 6、Flight 5、Serial 4、Logger/Telemetry 3；
- Idle task内存由`vApplicationGetIdleTaskMemory`静态提供；software timer关闭，因此不创建Timer task。

System、Algorithm、Protocol、Devices、Interfaces与Platform公共API不得包含FreeRTOS头。第三方Kernel内部的`TaskFunction_t`等函数指针属于记录在案的第三方偏差，不构成恢复第一方运行期插件/回调架构的理由。

## 6. System Profile、Startup与持续所有权

Target在`target_system_config.h`把已选Device的构建资格映射为`SYSTEM_SELECTED_*`，`system_user_capability_validation.h`集中拒绝不合格的Alignment、Deploy、Landing与Estimator组合。System Profile保存启用、Required和Optional capability，不保存具体Device类型或Ops地址。

`SystemStartup_Run()`按启用capability调用直接Interface完成初始化、启动、可选配置写入、可选真实回读验证和基础通信检查。禁用能力不得初始化、处理或影响启动降级结果。写入/验证由`system_user_startup_config.h`显式选择；当前GNSS启动不写配置、仅验证，JY901B和Telemetry写入保持既有配置。任何保存/持久化与恢复策略仍需上板评审。

持续所有权：

- DeviceTask：Platform UART推进、IMU/GNSS/Power/Output设备处理、IMU样本总线与System Health；
- INSTask：Calibration correction、Alignment输入和Pure INS机械化；
- EstimatorTask：KF6预测、GNSS/Baro量测与Estimator诊断；
- FlightTask：Calibration/Alignment/Lifecycle/FlightRecovery/Indicator；
- TelemetryTask：Telemetry Service和SX1281 transport；
- SerialTask：Console transport与Maintenance解析；
- LoggerTask：LoggerBus消费、SSLOG编码、Storage/Log Sink写入和finalization。

所有跨任务队列、bus、descriptor表、Platform缓冲和状态均有编译期容量，不使用运行期heap。Console、Alignment诊断和DebugLog统一使用Common层有界静态格式器，避免newlib `snprintf/vsnprintf`把`malloc/_sbrk`重新带入最终ELF。

## 7. 导航、对准与飞行状态

0.0.9保持0.0.8已经验证的数学和状态语义：

- Body/ENU与`q_nb`仍表示body到ENU；
- Calibration支持NONE、ONE_FACE和SIX_FACE；
- 默认Initial Alignment为窗口化Gravity + Known ENU Yaw，START后冻结初始姿态并只做软件四元数传播；
- JY901B六轴/九轴hardware quaternion具备START前静态窗口Initial Alignment资格，但两种任务期authoritative资格均为0；该资格不允许START后替代或修正软件传播姿态；
- Pure INS保持二子样圆锥/划桨补偿；融合保持六状态位置/速度KF6、GNSS分组门控、重捕获和Baro融合；
- Lifecycle保持BOOT/SELF_TEST/PREFLIGHT/READY/FLIGHT/RECOVERY/LANDED/POSTFLIGHT/FAULT；
- FlightRecovery保持NONE/TILT/APOGEE_VZ/START-relative DELAY触发、one-shot Mission Action、RECOVERY及可选Landing；默认仍为APOGEE_VZ与BARO_IMU_WINDOW；
- JY901B accel/gyro具备Landing stillness资格，支持STILLNESS与BARO_IMU_WINDOW；impact资格保持0，IMPACT_THEN_STILLNESS继续编译期拒绝；
- 不因平台化引入15维ESKF、多级火箭、双伞、复杂pyro、完整launch detector或新的公开Lifecycle状态。

Host测试证明软件语义保持，不等于执行器、落地冲击捕获或整套安全链路上板验证。

## 8. AIR遥测协议M0与串口维护协议0.0

AIR遥测协议M0由`Protocol/air_protocol.*`纯字节编解码，Telemetry Service只依赖通用Interfaces。技术枚举`AIR_PROFILE_COMPACT_V0`保持数值0、现有固定帧和稳定Sensor ID表；System Sensor Status使用静态目标描述与实时Interface健康/样本生成，不在Telemetry中硬编码具体型号。

串口维护协议0.0由System Console解析，UART Console Adapter只处理字节链路。IMU/GNSS/BARO/MAG/ATTITUDE/TELEMETRY/POWER使用`<CAPABILITY> <INSTANCE> <COMMAND>`，系统和算法模块保持无实例号；旧无实例能力命令不保留。Physical Device与Capability Endpoint通过Generated descriptor中的`physical_device_id`、`device_class`和类别内`instance_id`区分；JY901B的IMU 0、BARO 0和ATTITUDE 0是独立逻辑端点但共享一个物理ID。Generated facade对每个能力提供Count与静态`switch(instance_id)` direct binding，不存在实例返回`NOT_PRESENT`，不得回退到0。当前正式F407仍只有instance 0，JY901B同插件重复资格为0；多实例兼容不等于同型号重复Driver、Sensor Selection或Multi-EKF。`STATUS`给出运行与健康摘要，不新增独立`HEALTH`命令；`IO CLEAR`按物理ID建立共享显示基线，不清底层累计计数、Parser、Platform ring buffer或健康状态。SerialTask不直接执行设备事务、状态转换或功率动作。

## 9. 飞行日志格式0.0

职责分离：

```text
Protocol/SSLOG = wire format + record metadata + endian codec normal source
LoggerBus       = bounded static record queue
LoggerTask      = consume + encode + flush + sink
SystemLogPolicy = per-record stream policy
Generated       = project-enabled stream selection
Board LogSink   = target storage destination
```

`Protocol/SSLOG/Inc/sslog_records.h`与`Protocol/SSLOG/Src/sslog_records.c`是Record ID、version、payload size、metadata及wire codec的正常受控源码。serializer/deserializer按字段显式读写little-endian整数和float bit pattern；payload C struct只用于内存，禁止按结构体布局直接复制到wire或从wire强制转换。`Protocol/SSLOG/schema/sslog_schema.json`同时是FCCG/解析器使用的声明式Record Catalog真源，JSON Schema限制有限基础类型、固定数组和纯数据语义；Host离线validator核对字段与padding总和、parser metadata、C ID/size/codec、Generated stream配置及profile哈希。firmware build不读取JSON或执行Python。

`SystemLogStreamConfig[SSLOG_RECORD_COUNT]`以record type为键，取代32-bit mask；当前工程的enabled/decimation/period/policy由`Generated/Src/project_log_config.c`提供并在START时冻结。`SYSTEM_CONFIG`只记录汇总计数和最终配置，具体设备、算法、日志流分别通过可重复的`DEVICE_DESCRIPTOR(0x1A)`、`ALGORITHM_DESCRIPTOR(0x1B)`和`LOG_STREAM_DESCRIPTOR(0x1C)`表达。`DECODER_PROFILE_DESCRIPTOR(0x1D)`为64-byte one-shot Record，在Logger session开始时记录package schema 1.0、container 0.0以及Record Catalog、project semantics、generation profile三个SHA-256的前16字节；固件只消费Generated常量，不计算SHA-256，不嵌入ZIP自身哈希。DEVICE_DESCRIPTOR包含明确`physical_device_id`；POWER及IMU/GNSS/BARO/MAG/HW_QUAT Native记录包含`source_descriptor_id + instance_id`，与Canonical算法记录区分。各Native producer通过Generated Count/Instance facade遍历全部启用实例，每实例保存独立sequence/timestamp基线；当前正式Target只有instance 0，Canonical记录仍只保存当前instance 0来源的一份。预留的Sensor Source Change事件复用既有EVENT framing，当前单源工程不产生伪切换。

FCCG以后将Record Catalog和`project_semantics.json`放入同一个纯数据`.ssdecoder`。Canonical JSON固定为UTF-8、键字典序、无无意义空白、JSON稳定最短数字、LF并保留一个末尾LF。`record_catalog_hash`与`project_semantics_hash`分别为规范化JSON的SHA-256；`generation_profile_hash`输入依次为UTF-8 package schema ID、LF、UTF-8 container plugin ID、LF、完整32-byte Catalog hash和完整32-byte semantics hash。日志只保存三者各自前16字节。

STATS与TELEMETRY_DIAG已有真实周期producer并默认启用：Device Task在FLIGHT/RECOVERY每1 s记录ImuSampleBus overflow、LoggerBus overflow、Canonical INS update sequence和health flags；Telemetry Task每200 ms从通用`SystemTelemetryHealth`记录Transport/Link健康。Health读取失败不写伪数据；Telemetry Service内部调度统计不进入该payload。日志可用性必须以实际producer为依据，schema存在本身不构成available声明；新增诊断日志不得改变AIR遥测协议M0 wire。

Record version唯一位于通用Record header/record metadata；`MISSION_CONFIG` payload不再携带第二个冗余version字段。

新增Record流程：共同修改payload C类型、record metadata、显式双向codec、parser参考schema/metadata和日志文档；增加所有Record字节往返、长度/endian/CRC/unknown-type测试。不得直接序列化C struct、恢复runtime serializer registry或把Python生成重新接回authoritative Make。

## 10. 构建与发布

顶层`Makefile`与其显式包含的`BuildSystem/*.mk`、`Targets/*/target.mk`、各`module.mk`是唯一source of truth。禁止大范围wildcard、`$(notdir ...)`对象压平和IDE手工include/exclude作为正式构建配置。

```powershell
mingw32-make TARGET_PROFILE=SilverStar_F407 CONFIG=Debug all
mingw32-make TARGET_PROFILE=SilverStar_F407 CONFIG=Release all
```

输出为`build/<Target>/<Debug|Release>/SilverStar_0_0_9.{elf,map,hex,bin}`，对象保留源码相对目录。构建只依赖GNU Make和Arm toolchain，不依赖Python/FCCG。`.eide/eide.yml`是当前F407可直接构建的手工镜像，输出隔离到`build/EIDE/`；`architecture-check`确保其源、include、define、CPU/FPU、linker与forced include和Make一致。未来FCCG可以覆盖该镜像，但Make保持正式release/validation权威。

CubeMX只管理STM32时钟、GPIO、DMA、UART、SPI、SDIO、ADC、NVIC和HAL初始化。重新生成后必须确认`.ioc`没有恢复FreeRTOS middleware、`freertos.c`、CMSIS-RTOS2或defaultTask，并复核USER CODE以外的必要改动。

## 11. 验收状态

0.0.9交付必须运行：

- `mingw32-make host-tests`：接口、Platform mock、Device Driver+Adapter、Board Service、算法、Calibration/Alignment、Lifecycle/Recovery、AIR、SSLOG和编译期能力契约；
- `mingw32-make architecture-check`：依赖边界、旧架构残留、Generated薄glue、无Python构建、heap/CMSIS、manifest和FreeRTOS源集；
- clean Debug与clean Release ARM GCC构建，并分别运行`artifact-check`，核对ELF/MAP/HEX/BIN、源集、层级对象路径及无libc/RTOS heap符号。
- `mingw32-make power10-check`和`mingw32-make static-analysis`：第一方严格Power of Ten、warning=0和Arm GCC analyzer；
- EIDE镜像静态一致性，并在可调用builder环境中执行一次原生EIDE CLI Debug build。

当前静态/Host/编译结果只能证明软件实现和F407 backend可构建。GNSS模块端配置、SD卡持续写入、LoRa链路预算、输出执行器、传感器动态性能和整机飞行必须依据串口日志、逻辑分析仪/示波器、双机、HIL和上板试验另行验收。

## 12. Strategy、Mode与Target内存追加规范

当前构建期Strategy为GravityKnownYaw、Coning2Sculling2、KF6、BarometerImuWindow和MultiTrigger。未选择Strategy不进入source graph；`ESTIMATOR_STRATEGY=None`不编译KF6。Calibration的Existing/OneFace/SixFace与MultiTrigger的Apogee/Tilt/Delay属于Mode，后者允许0..N组合且mask=0不自动部署。不得恢复runtime strategy registry或函数指针dispatch。

F407通过vendor-neutral memory placement宏把Estimator、当前Alignment strategy storage、七个任务栈和Idle栈放入CPU-only CCMRAM；DMA相关对象留在主SRAM。Target linker/startup负责`.ccmram_bss`定义和清零，CubeMX重新生成后必须复核。Power of Ten、CCMRAM、EIDE与Strategy组件化均不改变0.0.9、AIR遥测协议M0、串口维护协议0.0或飞行日志格式0.0；技术wire标识仍分别为profile numeric 0和magic `SSLOG0`。

## 13. 文档索引

- [工程架构](../details/ARCHITECTURE.md)
- [Platform契约](../details/PLATFORM_INTERFACE.md)
- [设备接口与Adapter](../details/DEVICE_INTERFACE.md)
- [构建与Target](../details/BUILD_AND_TARGETS.md)
- [System Profile](../details/SYSTEM_PROFILE.md)
- [生命周期](../details/SYSTEM_LIFECYCLE.md)
- [Calibration与Alignment](../details/CALIBRATION_AND_ALIGNMENT.md)
- [导航与估计](../details/NAVIGATION_AND_ESTIMATION.md)
- [AIR遥测协议M0](../details/AIR_PROTOCOL.md)
- [串口维护协议0.0](../details/MAINTENANCE_PROTOCOL.md)
- [飞行日志格式0.0与Storage](../details/STORAGE_AND_FLIGHT_LOG.md)
- [编码约束](../details/CODING_STANDARD.md)
- [移植与发布](../details/PORTING_AND_RELEASE.md)
- [验收要求](../details/VALIDATION_REQUIREMENTS.md)
- [FCCG组件边界](../details/FCCG_COMPONENT_BOUNDARIES.md)
- [完整文档清单](../details/DOCUMENT_LIST.md)
