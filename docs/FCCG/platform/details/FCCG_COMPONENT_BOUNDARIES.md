# FCCG组件边界
> **0.0.12增量**：FCCG `docs/platform/` 是平台规范权威；外部reference firmware只作为只读来源。长期FCCG扩展通过builtin/overlay/importer持久化，不能要求修改外部参考仓库。

本文定义FCCG当前组件装配与生成工程的payload边界。FCCG已实现GUI配置、声明式插件管理、严格JSON项目模型、资源解析、代码生成和构建前端；生成后的固件不依赖GUI运行。

## Ownership原则

FCCG创建工程时复制的Component Source归目标工程所有，之后允许用户或Codex修改；普通Apply Configuration不得覆盖这些源码。只有`Generated/`内明确列出的薄连接文件由FCCG管理和重写。`SilverStar.ssproject`与安装的manifest共同确定配置与Source Graph；其中`build.target_profile`是派生完整性锁。工程自有组件源码不因普通Apply被覆盖，也不要求恢复到包内原始hash。

| 组件类别 | 当前目录/文件 | 责任与可移植边界 |
| --- | --- | --- |
| Core | `APP/`、`System/`、`Interfaces/`、`Common/`、`Modules/` | 任务编排、系统行为、跨组件契约和通用容器；不认识具体Sensor、HAL或STM32 |
| MCU | `Platform/Inc/`、`Platform/STM32F4/`、`Drivers/`、`startup_stm32f407xx.s`、linker script | UART/SPI/I2C/PWM/GPIO/ADC/Time/Critical后端与STM32F407启动；generic Platform不包含板级资源意义 |
| Board | `Board/SilverStar_0_5/` | PCB物理事实、固定logical ID→alias映射及验证来源；不拥有通用storage、power或任务动作业务 |
| Device | `Devices/IMU/JY901B/`、`Devices/GNSS/NEO_M9N/`、`Devices/Telemetry/SX1281/`、`Devices/Console/UART/` | 每个目录同时携带native Driver和`Adapter/`；Adapter只依赖公共Interface、Device和Platform API，不依赖HAL、concrete Board或Target |
| Algorithm | `Algorithm/Common/`、`Algorithm/Calibration/`、`Algorithm/Alignment/<Strategy>/`、`Algorithm/INS/<Strategy>/`、`Algorithm/Estimator/<Strategy>/` | Common与Calibration correction常驻；OneFace/SixFace按Mode选择编入；互斥Strategy仅选中实现进入图；无Device/Board/STM32/FreeRTOS依赖 |
| FlightLogic | `FlightLogic/FlightCycle/`、`FlightLogic/Deployment/<Strategy>/`、`FlightLogic/Landing/<Strategy>/` | 生命周期组合、deploy判定和landing判定；当前Deployment=MultiTrigger、Landing=BarometerImuWindow；`APP/Src/flight_task.c`只负责周期编排和系统动作连接 |
| OS | `OS/FreeRTOS/`、`ThirdParty/FreeRTOS-Kernel/`、`Targets/SilverStar_F407/Src/freertos_target_irq.c` | 官方11.3.0 kernel、SilverStar静态配置/Hook和F407 IRQ连接；不包含heap backend或CMSIS-RTOS2 |
| Protocol | `Protocol/Src/air_protocol.c`、`Protocol/SSLOG/` | AIR遥测协议M0纯字节源码与飞行日志格式0.0正常源码；numeric 0和`SSLOG0`是技术wire标识，逐字段little-endian codec是Protocol组件，不由FCCG生成 |
| Generated Glue | `Generated/` | project resource mapping、静态instance facade、project log selection/metadata、project semantics与decoder profile常量；由FCCG从统一模型和Source Graph生成 |
| Target | `Targets/SilverStar_F407/` | 声明F407 flags/linker、memory和OS port契约；组件/provider源集由统一Source Graph解析 |

## 连接关系

```text
System / APP
    |
Interfaces
    |
Generated facade / Device Adapter / FlightLogic service
    |
Device native driver
    |
Platform API
    |
STM32F4 backend

Generated/project_resources + platform_resources
    └─ 只把当前工程选择映射到Platform ID、CubeMX句柄和GPIO pin
```

`Platform/STM32F4`只通过`platform_stm32f4_resources.h`取得opaque handle或GPIO资源；`huart1`、`RADIO_NSS`等当前工程映射集中在`Generated/Src/platform_resources.c`。

## Capability实例生成责任

FCCG区分Physical Device插件实例与Capability Endpoint实例。对每个物理模块，Generated glue需要产生：

- 稳定且项目内唯一的`physical_device_id`；
- 每个`SystemDeviceClass`内从0连续编号的`instance_id`；
- 含descriptor/physical/class/instance/flags/capability/rate/hash的Capability Endpoint Descriptor；
- `device_class + instance_id`到Canonical Adapter的静态direct binding case；
- 维护协议`LIST`所需的device/model/共享物理metadata；
- Native log的`source_descriptor_id + instance_id`来源metadata。

JY901B、NEO-M9N和SX1281官方插件支持每种最多四个物理实例，各自拥有独立driver/parser状态和资源绑定，源码只进入Source Graph一次。Generated descriptor区分`physical_device_id`与能力类别内连续编号的`instance_id`，静态facade通过有界direct case调用具体实例；越界返回`NOT_PRESENT`，不回退到0，不建立registry、vtable或heap。维护、Sensor Status和Native Log可读取全部启用实例。Canonical接口只输出当前active来源的一份数据：IMU在Calibration/Alignment前选择并锁定，飞行中不切换；GNSS按基础liveness单向切换；AIR只用一个active transport。投票、多INS和Multi-EKF尚未实现。 同一JY901B的IMU/BARO/ATTITUDE以及显式启用的MAG端点共享物理ID；AIR仍使用既有sensor_id + instance_id，不增加wire字段。

## 日志可用性生成责任

Record schema、ID、metadata和codec存在只说明格式可解析，不等于该Record在目标工程可用。FCCG对外标记日志`available`前必须确认选中的Component Source具有实际producer调用点，并且其通用接口依赖已连接；不得仅按schema列表生成可用性。

当前reference中，STATS由Device Task周期诊断路径生产，依赖ImuSampleBus统计、LoggerBus overflow和Canonical INS snapshot，默认周期1 s；TELEMETRY_DIAG由Telemetry Task从通用`SystemTelemetryHealth`生产，默认周期200 ms。后者不包含Telemetry Service内部队列/调度统计，FCCG不得把APP连接到SX1281私有统计，也不得通过启用诊断日志改变AIR M0 wire。

### `.ssdecoder`配置包契约

日志容器插件只负责飞行日志格式0.0的File Header、Record Header、sync、CRC和framing。每个工程的纯数据`.ssdecoder`由FCCG同时装入声明式Record Catalog与`project_semantics.json`；它们不是runtime插件，也不能携带可执行脚本。`Protocol/SSLOG/schema/sslog_schema.json`是Catalog真源，JSON Schema和Host离线validator必须先验证字段类型、数组、padding、payload size、语义默认值和C mirror。

FCCG按UTF-8、键字典序、无空白、稳定最短JSON数字、LF及单个末尾LF规范化Catalog和project semantics并分别计算SHA-256。generation profile输入为UTF-8 package schema ID、LF、UTF-8 container plugin ID、LF、完整32-byte Catalog hash、完整32-byte semantics hash。FCCG把三项hash前16字节写入`Generated/project_log_decoder_profile.*`；固件在Logger session开始时one-shot生产`DECODER_PROFILE_DESCRIPTOR(0x1D)`。ZIP自身SHA-256不得嵌入日志，避免循环依赖。

## 替换场景

- JY901B换BMI088：复制新的Device Driver+Adapter，修改Target选择、Generated resource mapping和capability aggregation；System、KF6和FlightLogic不修改。
- STM32F407换H743：替换MCU backend、CubeMX/startup/linker/RTOS port及Generated physical mapping；JY901B、M9N、SX1281、Algorithm和FlightLogic不修改。
- Deployment算法替换：保留`FlightDeployment*`显式输入/输出契约或提供等价适配，只替换`FlightLogic/Deployment`；`flight_task.c`不承载阈值数学。

## Strategy与Mode

Strategy是build-time selected的互斥Component；未选择实现不编译、不依赖linker GC、也不通过大段`#if`隐藏。当前分类：

| 功能 | 分类 | 当前reference选择 |
| --- | --- | --- |
| Calibration | Mode/operation | 可选OneFace、SixFace采样procedure；NONE为常驻运行期能力 |
| Alignment | Strategy | GravityKnownYaw |
| INS | Strategy | Coning2Sculling2 |
| Estimator/Fusion | Strategy | KF6；None不编译KF6 |
| Landing | Strategy | BarometerImuWindow |
| Deployment | Strategy + Modes | MultiTrigger；Apogee/Tilt/Delay为可组合trigger Modes |

Mode由已编入Component的runtime/project配置选择。Mode Set可以按contract允许0..N项；Deployment `selection: []`/mask=0合法且不自动部署。Calibration空Mode Set表示不编入采样procedure，仍保留NONE/Identity correction。NONE不是FCCG可选Mode，也不表示加载已有校准。参见[共同契约](../../AIR_CALIBRATION_CONTRACT.md)。FCCG负责选择Strategy并生成source graph，runtime只选择Mode；不得生成runtime registry、vtable或函数指针dispatch。

`SilverStar.ssproject`与安装manifest是配置真源。FCCG解析一次Source Graph，Make和原生EIDE从同一结果生成；VS Code调用生成的Make。固件编译使用已物化的源列表，不在Make中重新运行FCCG生成器。

Device组件拥有细粒度构建资格，Target只负责映射为通用`SYSTEM_SELECTED_*`能力。Hardware Quaternion的六轴/九轴preflight alignment资格与任务期authoritative资格必须分别建模；IMU的Landing stillness与impact资格也必须分别建模。FCCG不得因为选择了hardware quaternion Alignment Strategy就自动授予飞行全程姿态权威，也不得因为IMU能判断静止就自动授予冲击捕获资格。

## Deployment硬件动作边界

```text
MultiTrigger decision
 -> FlightRecovery
 -> System Mission Action Interface
 -> FlightLogic/MissionAction/GpioOutput
 -> output_service
 -> PlatformGpio_Write
 -> Generated P_CONTROL2 mapping / physical MOS
```

Deployment Strategy不得包含HAL、Platform GPIO、GPIO port/pin、MOS或PWROUT物理知识。active level、pulse/latched、one-shot、START/PWROUT1与Deploy/PWROUT2语义由所选MissionAction实现和声明式Device资源约束保持，必须另做台架验收。

## Target Memory组件职责

FCCG的MCU/Target插件应携带memory capability、vendor-neutral placement映射、linker、startup初始化、DMA/cache规则、Make/EIDE forced include和artifact预算。Component Source只表达CPU-fast/DMA-accessible意图。F407当前把CPU-only大对象与静态栈置于CCMRAM，DMA对象留主SRAM；这不是可复制到其他MCU的固定地址算法。

## 当前实现与剩余边界

声明式manifest、依赖和版本校验、资源冲突检查、工具链配置、生成摘要、Make与原生EIDE渲染已经实现。普通Apply保护工程自有源码；组件升级的自动源码合并不属于当前承诺。完整平台规范保留在FCCG的`docs/platform/`，无需复制到每个生成工程。
