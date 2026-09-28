<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

# SilverStar 工程架构

> 文档版本：0.0.12
> 适用范围：SilverStar 0.0.12

本文定义可执行的依赖、所有权和目录边界。平台化的判据不是目录名称，而是：System、Device与MCU三者没有反向类型依赖，构建期选择不会退化成运行期函数指针注册。

## 1. 目录职责

```text
APP/                         FreeRTOS任务、静态bus/queue、任务编排
Algorithm/                   纯数学算法
Board/SilverStar_0_5/        当前PCB特有的物理映射与连接
BuildSystem/                 公共显式构建manifest
Common/                      与设备/算法无关的静态容器和调试基础
Devices/<Class>/<Model>/     MCU无关Driver与同目录System Adapter
FlightLogic/                 FlightCycle、Deployment、Landing组件
Generated/                   薄project resource/LOG/metadata连接
Interfaces/Inc/              System/Adapter/Board共用的稳定C契约
Modules/                     跨接口服务，例如Telemetry Service
OS/FreeRTOS/                 SilverStar FreeRTOS配置与静态hook
Platform/Inc/                vendor无关MCU能力契约
Platform/<MCU>/              具体MCU backend
Protocol/                    纯字节协议；含AIR和Protocol/SSLOG
System/                      Profile、Startup、Lifecycle、Health、策略
Targets/<Target>/            模块、Board、backend、OS port的构建选择
ThirdParty/                  固定版本第三方源码
Core/, Drivers/, FATFS/      CubeMX/HAL及当前F407生成/胶水区域
Tests/Host/                  主机测试与Platform mock
Tools/                       静态架构与firmware artifact检查
```

工程不创建自建根目录`BSP/`。`FATFS/Target/bsp_driver_sd.*`是Cube/FatFs命名遗留，不代表通用BSP层。

## 2. 正式依赖方向

```text
             +-------------------+
             | System / Modules  |
             +---------+---------+
                       |
             +---------v---------+
             |    Interfaces     |
             +---------+---------+
                       |
             +---------v---------+
             | Adapter / Board   |
             +---------+---------+
                       |
             +---------v---------+
             | Device native API |
             +---------+---------+
                       |
             +---------v---------+
             | Platform public   |
             +---------+---------+
                       |
             +---------v---------+
             | MCU/Cube backend  |
             +-------------------+
```

旁路关系：

- Algorithm只接受普通数值结构，不调用System、Device、Platform、RTOS或HAL；
- Protocol只编码/解码字节，不操作transport；
- APP可调用System、Modules、Interfaces和第一方静态bus；
- Board实现PCB特有能力，调用Platform ID，不直接包含HAL句柄；
- Target可以包含设备构建资格头和MCU port配置，因为它正是组合点；
- Device Adapter可以同时看到Interface与本Device native API；硬件服务组件可以看到Interface与Generated资源配置；
- Generated是当前project组合点，只保存语义资源、physical mapping、LOG选择和metadata，不承载业务算法。

禁止依赖：

- System/Algorithm/Protocol/Interfaces包含具体Device头、型号或HAL；
- Device core包含System Interface、FreeRTOS、HAL/CMSIS、`main.h`或MCU句柄；Adapter允许公共Interface，但不允许HAL、concrete Board或Target；
- Platform公共头和MCU backend出现传感器/无线型号；
- Device注册ISR callback，或System保存Ops/vtable/function pointer；
- APP绕过Interface直接调用具体Device；
- IDE扫描文件夹形成第二套正式source graph。

## 3. Interfaces与Device Adapter

公共契约位于`Interfaces/Inc/system_*_if.h`，采用直接函数：

```c
SystemDeviceResult SystemImu_Init(void);
void SystemImu_Process(void);
SystemDeviceResult SystemImu_LatestSampleGet(SystemImuSample *sample);
```

Device组件内的Adapter提供这些符号：

```text
SystemImu_LatestSampleGet
    -> Jy901b native snapshot
    -> validity/error/time/field mapping
    -> SystemImuSample
```

同一固件目标不得链接两套同名Interface实现。选择发生在`Targets/<target>/target.mk`和各Device/Board `module.mk`，不发生在System源码的`#if device`分支，也不发生在运行期Registry。

Interface返回`SystemDeviceResult`，所有输出参数在成功时完整覆盖；`UNSUPPORTED`、`NOT_READY`、`STALE`、`INVALID_ARGUMENT`等语义见[DEVICE_INTERFACE.md](DEVICE_INTERFACE.md)。具体driver错误必须在Adapter映射，System不解释vendor错误码。

## 4. Device、Board与Platform

Device core只拥有设备本身：

- wire protocol和frame parser；
- native sample和配置结构；
- 非阻塞或有界状态机；
- 本设备的校验、超时和诊断；
- 通过Platform读取/写入字节、GPIO事件和单调时间。

Device使用`PROJECT_RESOURCE_IMU_UART`、`PROJECT_RESOURCE_RADIO_SPI`等语义资源，但不能使用`huart1`、`GPIOA`或`GPIO_PIN_x`。0.0.12语义选择在`Generated/Inc/project_resources.h`，CubeMX handle/pin物理映射在`Generated/Src/platform_resources.c`；`Platform/STM32F4`只通过opaque resource bridge读取映射。

UART DMA/IRQ模型完全由backend拥有：

```text
HAL IRQ / Receive-to-Idle DMA
        -> Platform UART static buffer/ring
        -> PlatformUart_Read()
        -> Device Process()
```

GPIO中断同理：backend只累计事件，Device在Process中调用`PlatformGpio_IrqConsume()`。ISR不执行SPI事务、协议解析、System操作或任务通知注册。

## 5. 物理设备与逻辑接口

正式模型区分Physical Device与Capability Endpoint Instance：

```text
Physical Device
    | provides
    v
Capability Endpoint Instances
    |
    +--> Raw Diagnostics / Maintenance / Native Logging
    |
    v
Sensor Selection（未来，当前未实现）
    |
    v
Canonical Sensor Stream
    |
    v
INS / Estimator
```

Physical Device是JY901B、NEO-M9N、E28等实际硬件；Capability Endpoint是`IMU 0`、`BARO 0`、`ATTITUDE 0`、`GNSS 0`等逻辑能力实例。一个物理设备可以提供多个端点，但硬件所有权仍唯一。当前JY901B物理UART和parser只由共享JY901B Adapter拥有；IMU、Barometer、Magnetometer与Hardware Quaternion Adapter读取同一静态native snapshot并委托物理配置，不创建第二个UART消费者或第二个parser。`IMU`只表示加速度和角速度，气压、磁场和硬件姿态必须是独立能力端点。

Target descriptor用明确的`physical_device_id`和`SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL`表达共享关系；逻辑`instance_id`只在同一device class内从0连续编号。Generated facade为IMU、GNSS、BARO、MAG、ATTITUDE、TELEMETRY和POWER提供类别Count及受支持操作，生成的`switch(instance_id)`直接绑定各插件Adapter；不存在实例返回`NOT_PRESENT`，不使用registry、vtable、function pointer或heap。JY901B、NEO-M9N和SX1281现已通过每实例静态context、类型化resource table和实际Driver Host隔离测试，正式允许同插件最多4实例；其他插件仍按各自manifest边界。Maintenance、Sensor Status与Native Log使用该facade，所有IMU/GNSS实例均持续Process并生成可区分Native数据。当前INS/Estimator只消费一个Canonical输入：IMU在Calibration/Alignment前按primary后稳定顺序选择首个新鲜有效源并锁定，飞行中不切换；GNSS只在基础liveness故障时单向切到后续备用，no-fix不等于故障；AIR只启用一个active Telemetry，连续10次真实本地TX timeout后单向切换，成功清零，备用耗尽后仍按正常周期重试最后source。该窄策略不实现Voting、Multi-INS、Multi-EKF、RF端到端健康、自动failback或重复AIR收发。

## 6. 启动所有权

`SystemStartup_Run()`只调用通用Interface。流程为：

1. 初始化Platform time和安全输出；
2. 按`SystemProfile.enabled_capabilities`初始化/启动当前能力；
3. 按用户启动策略执行可选配置apply/persist/verify；
4. 完成基础通信、健康和Required/Optional判定；
5. 保存静态`SystemStartupReport`。

未启用的capability必须跳过Init、Start、Process和Health，不得因为Target仍编译了共享物理Adapter而被访问。正常启动不主动执行维护self-test；配置写入、验证和持久化严格受显式startup策略控制。

启动报告用固定上界数组记录逻辑设备阶段结果；它是运行期诊断容量，不是设备选择Registry。设备/算法长期元数据由Target descriptor接口按索引读取并写成SSLOG descriptor Record。

## 7. 任务与数据所有权

| 任务 | 优先级 | 主要所有权 | 周期等待 |
|---|---:|---|---:|
| Device | 7 | Platform UART推进、IMU/GNSS/Power/Output Process、Health与STATS周期生产 | 1 ms |
| INS | 7 | Calibration correction、Alignment输入、Pure INS | 1 ms |
| Estimator | 6 | KF6预测、GNSS/Baro更新、诊断 | 1 ms |
| Flight | 5 | Calibration/Alignment/Lifecycle/Recovery/Indicator | 2 ms |
| Serial | 4 | Console transport与Maintenance | 1 ms |
| Logger | 3 | SSLOG队列消费、编码、Storage/Log Sink | 状态相关2/10 ms |
| Telemetry | 3 | AIR Service、通用Telemetry Transport推进与TELEMETRY_DIAG周期生产 | 1 ms |

所有任务由`APP/Src/app_tasks.c`使用`xTaskCreateStatic()`创建。任务栈、控制块、bus和queue均为静态对象；System不创建任务、不等待RTOS对象。

SerialTask只解析、投递和返回维护命令，不直接成为IMU/GNSS/Telemetry/Output的第二运行所有者。FlightTask是Lifecycle与Mission Action的编排者；Logger/Telemetry失败不会逆向改变already-committed动作锁存。

## 8. 主要数据通路

惯导：

```text
Platform UART1 -> JY901B Driver -> JY901B IMU Adapter
 -> ImuSampleBus -> Calibration correction -> SystemInertial
 -> Pure INS -> Estimator prediction -> Flight/Telemetry/Logger snapshots
```

GNSS：

```text
Platform UART2 -> NEO-M9N Driver -> GNSS Adapter
 -> Quality/origin -> Estimator measurement -> Telemetry/Logger
```

天地通信：

```text
Telemetry Service <-> SystemTelemetry Interface
 -> SX1281 Adapter/Driver -> Platform SPI/GPIO event
```

日志：

```text
APP producers -> bounded LoggerBus -> LoggerTask
 -> Protocol/SSLOG normal endian codec -> LogSink Interface
 -> SDIO/FatFs Storage Device LogSink/Storage Service -> FatFs
```

设备级原始日志路径为：

```text
Generated capability Count/Instance facade
 -> 遍历IMU/GNSS/BARO/MAG/ATTITUDE/POWER全部启用实例
 -> 每实例独立sequence/timestamp去重
 -> 同一Record Type + source_descriptor_id + instance_id
 -> LoggerBus -> Flight Log Format 0.0
```

Canonical算法Record不沿该循环复制，仍只有当前instance 0来源的一份。Logger session写入文件头后one-shot排队`DECODER_PROFILE_DESCRIPTOR`，使独立日志文件可匹配FCCG导出的Record Catalog与project semantics；这不改变SSLOG0容器或AIR M0。

两条周期诊断生产路径为：

```text
ImuSampleBus stats + LoggerBus overflow + Canonical INS snapshot
 -> Device Task / DiagnosticLog_StatsProcess
 -> STATS -> LoggerBus -> Flight Log Format 0.0

SystemTelemetryHealth
 -> Telemetry Task / DiagnosticLog_TelemetryProcess
 -> TELEMETRY_DIAG -> LoggerBus -> Flight Log Format 0.0
```

它们只在FLIGHT/RECOVERY日志阶段按单调时间运行。Telemetry producer只依赖`SystemTelemetry_HealthGet()`，不得穿透到SX1281私有统计；诊断入日志也不得改变AIR遥测协议M0的消息、频率或wire。

## 9. FreeRTOS边界

FreeRTOS只允许在`APP/`、`OS/FreeRTOS/`、`Targets/.../freertos_target_*`和`Core/Src/main.c`启动入口中出现。官方Kernel源码位于`ThirdParty/FreeRTOS-Kernel`，不适用第一方禁函数指针规则；但第一方不得借此建立新的callback registry。

SysTick由Target交给`xPortSysTickHandler`，HAL tick由TIM1维护。任何MCU移植必须重新实现此分工，不能让Device读取RTOS tick。

## 10. 构建图

`Makefile`、`BuildSystem/*.mk`、`Targets/*/target.mk`和各`module.mk`是唯一权威source graph。manifest逐文件登记源码；对象输出保留相对路径。`.eide/eide.yml`是当前F407可直接构建的手工镜像，`architecture-check`把其C/S源、include、define、CPU/FPU、linker和forced include与Make展开结果逐项比对；它不取得source-of-truth地位。

新增Device/Adapter/Board/backend时先建立独立`module.mk`，再由Target显式include；只把目录放进仓库不会自动进入固件。F407 toolchain、CPU/FPU flags、linker、HAL、FatFs和FreeRTOS port也由Target选择。

## 11. 自动约束

`Tools/check_architecture.ps1`检查：

- 可移植层没有HAL/STM32/CMSIS泄漏；
- System和Platform不知道具体设备；Device core不依赖System/RTOS，Adapter不依赖HAL/Board/Target；
- 旧Provider/Registry/sensor×STM32 port、Semtech vtable/callback已退出；
- 无动态内存、CMSIS-RTOS2、defaultTask和非静态RTOS创建；
- manifest无wildcard/对象压平，目标源集无重复且文件存在；
- FreeRTOS版本、精简源集和静态配置正确；
- `Bindings/`与旧generated SSLOG路径不存在，`Generated/`仅为已评审薄glue；
- SilverStar/AIR/SSLOG版本边界、无Python authoritative build、双向endian codec及禁止struct直写正确；
- STATS与TELEMETRY_DIAG存在真实APP producer，默认周期与schema一致，Telemetry日志不依赖具体射频芯片且新源码进入Make/EIDE一致source graph。

该脚本是静态架构验收，不代替ARM编译、Host行为测试或硬件验证。

## 12. Strategy与Mode边界

Strategy是构建期互斥组件，Target通过`ALIGNMENT_STRATEGY`、`INS_STRATEGY`、`ESTIMATOR_STRATEGY`、`LANDING_STRATEGY`和`DEPLOYMENT_STRATEGY`只include当前实现的`module.mk`。当前F407分别选择GravityKnownYaw、Coning2Sculling2、KF6、BarometerImuWindow和MultiTrigger；其他三种Alignment实现保留在仓库并由独立Host入口测试，但不进入当前固件或EIDE源图。`ESTIMATOR_STRATEGY=None`只保留INS输出和系统胶水，`navigation_kf.c`不进入源图。

Mode属于已编入组件内部：Calibration保留空选（NONE/单位校正）/OneFace/SixFace；MultiTrigger内部的Apogee/Tilt/Delay使用bitmask任意组合，空mask合法且不自动部署。这里允许普通mode dispatch，但不允许runtime Strategy registry、vtable或函数指针选择。

Deployment只产生“是否部署、匹配mask和reason”的判定。实际动作路径为：

```text
FlightLogic/Deployment/MultiTrigger
 -> FlightRecovery orchestration
 -> SystemMissionAction_Execute
 -> FlightLogic mission_action_service / output_service
 -> PlatformGpio_Write
 -> P_CONTROL2 physical MOS
```

FlightLogic和System generic代码不知道GPIO port、pin或active level。

## 13. Target内存域

`Platform/Inc/platform_memory.h`提供vendor-neutral CPU-fast与DMA-accessible语义；`Targets/SilverStar_F407/Inc/platform_memory_target.h`将CPU-fast BSS映射到`.ccmram_bss`。`STM32F407XX_FLASH.ld`声明64 KiB CCMRAM，startup显式清零该section。

当前CCMRAM包含Estimator大上下文、当前build-selected Alignment strategy storage、七个APP task stacks和Idle stack。UART RX DMA、UART TX rings、Logger aggregation buffer、HAL/DMA handles和其他DMA参与对象留在0x20000000主SRAM。`artifact-check`验证section范围、关键symbol归属、CCM<=64 KiB、主SRAM<=96 KiB以及heap/allocator缺失。
