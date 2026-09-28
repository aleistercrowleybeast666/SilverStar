<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

# FCCG组件边界

本文定义SilverStar 0.0.12 reference firmware未来拆入独立`SilverStar_FCCG`工程时的payload边界。本仓库没有实现GUI、插件管理器、`.ssplugin`、JSON驱动构建或代码生成器。

## Ownership原则

FCCG创建工程时复制的Component Source归目标工程所有，之后允许用户或Codex修改；普通Apply Configuration不得覆盖这些源码。只有`Generated/`内明确列出的薄连接文件可由未来FCCG重写。`SilverStar.ssproject`记录组合，但不是源码hash或完整性锁。

| 组件类别 | 当前目录/文件 | 责任与可移植边界 |
| --- | --- | --- |
| Core | `APP/`、`System/`、`Interfaces/`、`Common/`、`Modules/` | 任务编排、系统行为、跨组件契约和通用容器；不认识具体Sensor、HAL或STM32 |
| MCU | `Platform/Inc/`、`Platform/STM32F4/`、`Core/`中的CubeMX外设初始化、`Drivers/`、`startup_stm32f407xx.s`、linker script | UART/SPI/GPIO/ADC/Time/Critical后端与STM32F407启动；generic Platform不包含板级资源意义 |
| Board | `Board/SilverStar_0_5/` | SilverStar PCB 0.5的已验证物理资源、连接和语义映射；通用服务由Device或内部组件拥有 |
| Device | `Devices/IMU/JY901B/`、`Devices/GNSS/NEO_M9N/`、`Devices/Telemetry/SX1281/`、`Devices/Console/UART/` | 每个目录同时携带native Driver和`Adapter/`；Adapter只依赖公共Interface、Device和Platform API，不依赖HAL、concrete Board或Target |
| Algorithm | `Algorithm/Common/`、`Algorithm/Calibration/`、`Algorithm/Alignment/<Strategy>/`、`Algorithm/INS/<Strategy>/`、`Algorithm/Estimator/<Strategy>/` | Common与Calibration全量组件进入正式图；互斥Strategy仅选中实现进入图；无Device/Board/STM32/FreeRTOS依赖 |
| FlightLogic | `FlightLogic/FlightCycle/`、`FlightLogic/Deployment/<Strategy>/`、`FlightLogic/Landing/<Strategy>/` | 生命周期组合、deploy判定和landing判定；当前Deployment=MultiTrigger、Landing=BarometerImuWindow；`APP/Src/flight_task.c`只负责周期编排和系统动作连接 |
| OS | `OS/FreeRTOS/`、`ThirdParty/FreeRTOS-Kernel/`、`Targets/SilverStar_F407/Src/freertos_target_irq.c` | 官方11.3.0 kernel、SilverStar静态配置/Hook和F407 IRQ连接；不包含heap backend或CMSIS-RTOS2 |
| Protocol | `Protocol/Src/air_protocol.c`、`Protocol/SSLOG/` | AIR遥测协议M0纯字节源码与飞行日志格式0.0正常源码；numeric 0和`SSLOG0`是技术wire标识，逐字段little-endian codec是Protocol组件，不由FCCG生成 |
| Generated Glue | `Generated/` | project resource mapping、静态instance facade、project log selection/metadata、project semantics与decoder profile常量；当前手工维护，未来可由FCCG重写 |
| Target | `Targets/SilverStar_F407/` | 选择STM32F4、SilverStar 0.5、JY901B、M9N、SX1281、FreeRTOS port、F407 flags/linker/HAL/FatFs source set |

## 连接关系

```text
System / APP
    |
Interfaces
    |
Device Adapter、Device-owned service或内部硬件服务
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

未来FCCG必须区分Physical Device插件实例与Capability Endpoint实例。对每个物理模块，Generated glue需要产生：

- 稳定且项目内唯一的`physical_device_id`；
- 每个`SystemDeviceClass`内从0连续编号的`instance_id`；
- 含descriptor/physical/class/instance/flags/capability/rate/hash的Capability Endpoint Descriptor；
- `device_class + instance_id`到Canonical Adapter的静态direct binding case；
- 维护协议`LIST`所需的device/model/共享物理metadata；
- Native log的`source_descriptor_id + instance_id`来源metadata。

同一个物理JY901B应生成同一source index下的`IMU N + BARO N + ATTITUDE N`，以及显式启用时的`MAG N`，这些端点共享一个`physical_device_id`和JY901B context，不是多个物理插件实例。JY901B、NEO-M9N和SX1281的manifest/build contract现明确`multi_instance_ready=true`，每类/插件最多4实例；类型化Generated resource table保证一个selected instance的全部requirement使用同一source index。Generated facade必须为每类生成Count和有界`switch(instance_id)` direct case，不得使用function pointer registry、vtable、heap或动态注册；同插件源码仍只进入Source Graph一次。Canonical默认从配置主源开始，运行时仅允许已定义的pre-start IMU锁定、GNSS liveness单向切换和AIR本地TX-timeout单向切换。AIR M0继续使用既有`sensor_id + instance_id`且只通过一个active transport收发，FCCG不得为多传感器扩展增加M0 wire字段。

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
| Calibration | Mode/operation | 空选=NONE/单位校正；OneFace、SixFace可独立或组合选择 |
| Alignment | Strategy | GravityKnownYaw |
| INS | Strategy | Coning2Sculling2 |
| Estimator/Fusion | Strategy | KF6；None不编译KF6 |
| Landing | Strategy | BarometerImuWindow |
| Deployment | Strategy + Modes | MultiTrigger；Apogee/Tilt/Delay为可组合trigger Modes |

Mode由已编入Component的runtime/project配置选择。Mode Set可以按contract允许0..N项；Deployment `selection: []`/mask=0合法且不自动部署。Calibration空选由FCCG确定性映射为`NONE`与单位校正，是该Mode slot的合法empty set。FCCG负责选择Strategy并生成source graph，runtime只选择Mode；不得生成runtime registry、vtable或函数指针dispatch。

`SilverStar.ssproject`只保存上述human/FCCG reference metadata，不参与Make解析。当前构建truth是Target与module manifests；配置头只保存已编入Component的Mode/参数。

Device组件拥有细粒度构建资格，Target只负责映射为通用`SYSTEM_SELECTED_*`能力。Hardware Quaternion的六轴/九轴preflight alignment资格与任务期authoritative资格必须分别建模；IMU的Landing stillness与impact资格也必须分别建模。FCCG不得因为选择了hardware quaternion Alignment Strategy就自动授予飞行全程姿态权威，也不得因为IMU能判断静止就自动授予冲击捕获资格。

## Deployment硬件动作边界

```text
MultiTrigger decision
 -> FlightRecovery
 -> System Mission Action Interface
 -> Board/SilverStar_0_5 mission_action_service
 -> output_service
 -> PlatformGpio_Write
 -> Generated P_CONTROL2 mapping / physical MOS
```

Deployment Strategy不得包含HAL、Platform GPIO、GPIO port/pin、MOS或PWROUT物理知识。active level、pulse/latched、one-shot、START/PWROUT1与Deploy/PWROUT2语义由既有Board动作链保持，必须另做台架验收。

## Target Memory组件职责

FCCG的MCU/Target插件应携带memory capability、vendor-neutral placement映射、linker、startup初始化、DMA/cache规则、Make/EIDE forced include和artifact预算。Component Source只表达CPU-fast/DMA-accessible意图。F407当前把CPU-only大对象与静态栈置于CCMRAM，DMA对象留主SRAM；这不是可复制到其他MCU的固定地址算法。

## FCCG阶段仍需实现

当前未提供plugin manifest、插件依赖/版本解析、资源冲突检查、toolchain管理、组件升级合并或自动配置摘要生成。当前EIDE native source graph只是手工reference镜像，未来FCCG仍需按选择生成/覆盖；这些能力属于独立FCCG工程，不是0.0.12 firmware运行依赖。
