# SilverStar 0.0.7 平台规范

SilverStar 是面向 STM32F407VET6 探空火箭飞控的静态嵌入式软件平台。当前工程使用 HAL、CMSIS-RTOS2/FreeRTOS、Provider Registry、Pure INS、六状态位置速度 KF、固定 AIR 帧和飞行日志。本文描述 0.0.7 软件的有效边界、启动语义、配置入口和规范索引。

## 1. 版本域

工程同时存在四个独立版本域：

- 软件版本：`0.0.7`，用于固件标识、构建目标、Provider 驱动版本和维护信息；
- AIR 二进制布局：0.0.7历史固定帧集合，固定帧长度、字段偏移和 token 保持兼容；
- 飞行日志格式版本：`SYSTEM_LOG_FORMAT_VERSION=5`，文件头 Magic 仍为 `SSLG0005`，旧记录可继续解析；
- 维护命令语义：由维护协议文档定义，不作为 AIR 二进制布局的一部分。

软件版本变化不自动改变 AIR 二进制布局或飞行日志格式。任何二进制布局变化都必须单独更新对应规范、文档和两端测试。

## 2. 分层边界

- `APP/`：线程入口、静态队列、任务间编排和持续调度；
- `Algorithm/`：不依赖 HAL 或 FreeRTOS 的数学算法；
- `System/`：Provider 接口、Registry、Profile、启动、生命周期、时间、健康和维护控制台；
- `Devices/`：具体设备后端和 STM32 私有端口；
- `Modules/`：Telemetry 等跨接口服务；
- `Protocol/`：AIR 等纯字节协议；
- `Common/`：静态容器和通用工具；
- `Core/`、`Drivers/`、`FATFS/`：CubeMX/HAL 生成区及其胶水层。

公共 System 接口不得暴露 HAL、UART、SPI、SDIO、FatFs 或具体设备类型。工程不使用动态内存；共享 Bus、Queue 和任务对象只初始化一次。

## 3. 当前硬件组合

- MCU：STM32F407VET6；
- IMU、磁力计、气压计、硬件四元数：单一物理 JY901B，通过四个逻辑 Provider 交付；
- GNSS：NEO-M9N，UBX NAV-PVT；
- Telemetry：E28-2G4M12SX/SX1281；
- Console：USART3 字节流 Provider；
- Power：ADC1_IN10；
- Storage/Log Sink：SDIO、FatFs、TF 文件；
- Output：两路逻辑安全输出。

设备初始化由 System Startup 和 Registry 编排；持续处理由架构规范指定的 APP 线程调用。每个物理设备只有一个运行期硬件/解析所有者：NEO-M9N由DeviceTask消费UART和推进UBX Parser，JY901B由IMU Provider消费唯一UART流，SX1281由TelemetryTask推进Radio/SPI状态机。ISR只生产字节或标志；逻辑Provider和状态查询读取缓存快照；运行期配置与诊断通过静态所有者事务串行化。

## 4. 启动、自检与降级

正常启动中的初始化、启动、可选配置写入、可选真实回读验证、基础通信检查和安全输出检查共同构成启动自检。正常启动不得调用 Provider 的 `run_self_test()`；该接口仅供维护命令显式触发。

启动结果保存在固定静态 RAM 的 `SystemStartupReport` 中。报告记录总体完成、通过、任务可用、降级、Required/Optional 失败掩码，以及每个 Provider 的初始化、启动、配置、持久化、验证、通信和配置掩码。每个设备的`apply_failed_mask`、`persist_failed_mask`和`verify_failed_mask`分别描述三个阶段，兼容`failed_mask`为三者按位或。Required/Optional 属性来自`SystemProfile.required_capabilities`与`optional_capabilities`。

- Required 能力失败：自检不通过，系统不得进入 READY 或接受 START；
- Optional 能力失败：系统可保持任务可用，同时置 `degraded` 和 warning；
- Output 无法初始化或无法保持 SAFE：安全致命错误；
- LOG 后端、日志队列、文件打开、写入、同步或关闭失败：仅产生健康告警和计数，不得阻止或回滚 START；
- Console 不是 Required 时，其失败不构成启动致命错误；
- 硬件四元数是否 Required 完全由当前 Profile 决定。

完整报告通过维护串口查询；LoggerTask 在日志文件成功打开后以事件记录写入同一份静态报告。AIR 只发送总体自检完成及通过位，不发送设备明细。

## 5. 启动写入策略

用户启动策略集中在 `System/User/system_user_startup_config.h`：

- `WRITE=1, VERIFY=0`：每次启动直接写入，不预读、不回读；
- `WRITE=1, VERIFY=1`：直接写入后执行真实硬件回读；
- `WRITE=0`：该设备不执行配置读、比较或写入，只启动通信和数据流；此时`VERIFY`不触发配置I/O；
- `WRITE=1, VERIFY=1`中的验证必须读取真实硬件状态，不能用软件缓存代替。

GNSS Provider 将通用写入请求映射到 NEO-M9N 的 RAM、BBR 和 Flash 层；System 通用接口不暴露 u-blox 持久化层。JY901B 的物理配置由 IMU Provider 统一执行并只保存一次，磁力计、气压计和硬件四元数 Provider 报告委托关系。SX1281 配置是易失的，启用写入时每次启动重写。

0.0.7 的 GNSS 默认策略暂定为 `SYSTEM_GNSS_BOOT_WRITE_CONFIG=1`、`SYSTEM_GNSS_BOOT_VERIFY_CONFIG=1`。NEO-M9N 的启动事务顺序固定为 UART 波特率配置、至少 100 ms 链路稳定等待、I/O 协议、NAV-PVT、导航率、动态模型、星座/信号，最后等待一帧严格晚于信号配置完成时刻的新 NAV-PVT；星座/信号配置之后不得再发送其他配置命令。新 PVT 必须同时满足 sequence 大于事务基线且 receive timestamp 大于信号配置完成时间，任意 ACK、NMEA 或其他 UBX 帧均不能代替。

## 6. 导航与估计

共享惯性增量总线只传递共享机体系补偿后增量：

```c
uint64_t timestamp_us;
uint32_t sequence;
float dt_s;
float delta_theta_b_corrected[3];
float delta_velocity_b_sculling_corrected[3];
```

Pure INS、KF 导航支路和后续姿态支路分别使用自己的姿态把机体系速度增量转换到 ENU。Pure INS 是独立基线，不接受 KF 回注。系统本地重力唯一用户配置为 `SYSTEM_LOCAL_GRAVITY_MPS2`。

启动静态偏置支持 X+/X-/Y+/Y-/Z+/Z- 六个重力方向。状态机持续等待有效数据并无限重试，不设置总超时或终止回退；方向、静止度、模长、连续性或方差不满足时保持 PREFLIGHT，完成前不得 READY。

六方向只用于加速度计/陀螺仪零偏校准。零偏完成后允许把飞控移动到任意实际安装姿态；当前 0.0.7 PREFLIGHT 只保存最新一帧合法硬件四元数及其完整时间戳和 sequence，START 在同一临界区内检查并原子冻结该完整帧。该帧必须数值合法、可归一化、sample/receive timestamp 非零且年龄不超过 100 ms；当前运行路径不等待、平均或冻结 100--128 帧窗口。任务软件传播从该冻结姿态开始，`SYSTEM_ATTITUDE_SOFTWARE_ALWAYS`禁止 START 后硬件四元数回注或渐近切换。移动和更新任务姿态候选帧不得重算已经冻结的零偏。

SystemAlignment统一管理预飞零偏、姿态候选、GNSS原点和气压原点的状态及START冻结编排，但不迁移或重写各所有者中的算法。总体状态为`IDLE/COLLECTING/CHECKING/READY/FAILED`，四个子项分别使用`NOT_READY/COLLECTING/READY/FAILED/DISABLED`。当前必需项为IMU零偏与姿态；GNSS和气压保持Optional。`ALIGN START/STOP/RESET`只允许START前执行，`ALIGN STATUS/DETAIL`可只读查询；Estimator仍只负责飞行中的状态估计。

## 7. AIR 与维护链路

AIR 应用层不附加帧尾 CRC，不改变既有固定长度。Parser 检查长度、type、command/status ID、token 和字段合法性；当前 SX1281 Transport 使用射频链路层 CRC。未来 Transport 必须自行提供 CRC 或等效完整性保护，不得静默修改 AIR 固定帧。

`AIR_STATUS_SELFTEST_COMPLETE=0x02` 只在启动报告完成且IMU零偏校准完成后发送一次；`arg0`表示任务可用的总体通过状态，`arg1`固定为0。Required IMU已形成终止失败时允许以`arg0=0`完成该事件；Optional LOG失败不得把`arg0`置0。`AIR_CMD_PING`只返回ACK，不补发任何状态事件。

`AIR_STATUS_GNSS_POSITION=0x09`以`SystemGnssSample.position_usable`为唯一判据，初始逻辑状态为0且不发送事件；首次0→1、之后1→0和再次0→1分别发送一次边沿事件。事件队列满时只累计Telemetry丢弃计数，不阻塞任何任务。

`AIR_STATUS_ALIGNMENT=0x0A`追加在全部旧事件编号之后，继续使用既有9字节STATUS帧：`arg0`为总体`alignment_state`，`arg1`最低位为`ready`，其后四位为IMU、ATTITUDE、GNSS和BARO的`failed_mask`。总体进入READY或FAILED时发送一次，不周期发送；`ALIGN START/STOP/RESET`本身不触发事件。SELFTEST仍只表示系统初始化检查，ALIGN只表示飞行前导航准备。PING只返回ACK，不补发任何状态。

Console Provider 只负责字节输入输出和链路健康；维护命令解析属于 System Console。Storage Provider 只描述初始化、挂载、打开、写入、同步、关闭和健康，FatFs 仅由 LoggerTask 的存储后端调用。

本机维护协议只公开`INFO`、`STATUS`、`CAPABILITIES`、`SAMPLE`、`SAMPLE DETAIL`、`IO`、`IO CLEAR`和`CONFIG SHOW/READ/VERIFY/APPLY`等正式语义；不公开独立`HEALTH`命令。`STATUS`同时给出模块当前运行状态和健康摘要。日志模块统一命名为`LOG`，不接受`TF`模块别名。

导航观测命令增加`ESTIMATOR STATUS`、`ESTIMATOR GNSS`、`KF STATUS`和`INS STATUS`，并保留`ESTIMATOR BARO`。这些命令只读取EstimatorTask/InsTask发布的现有状态、原点、计数和最近结果，不改变Pure INS、KF6、气压或GNSS融合策略。`SYSTEM READY`追加`gnss_ready`、`gnss_origin_ready`和`gnss_fusion_enabled`；GNSS仍为Optional，不阻止READY。GNSS融合许可只在START按预飞原点一次性冻结，未冻结原点的任务明确报告`NO_PREFLIGHT_ORIGIN`，飞行中获得fix不自动启用融合。

## 8. 正式规范索引

- [ARCHITECTURE.md](../details/ARCHITECTURE.md)
- [SYSTEM_PROFILE.md](../details/SYSTEM_PROFILE.md)
- [SYSTEM_LIFECYCLE.md](../details/SYSTEM_LIFECYCLE.md)
- [ALIGNMENT_INTERFACE.md](../details/ALIGNMENT_INTERFACE.md)
- [TIME_SERVICE.md](../details/TIME_SERVICE.md)
- `DEVICE_PROVIDER_INTERFACE.md`（历史文件，0.0.9平台化后已删除）
- [IMU_INTERFACE.md](../details/IMU_INTERFACE.md)
- [GNSS_INTERFACE.md](../details/GNSS_INTERFACE.md)
- [MAGNETOMETER_INTERFACE.md](../details/MAGNETOMETER_INTERFACE.md)
- [BAROMETER_INTERFACE.md](../details/BAROMETER_INTERFACE.md)
- [HARDWARE_QUATERNION_INTERFACE.md](../details/HARDWARE_QUATERNION_INTERFACE.md)
- [TELEMETRY_INTERFACE.md](../details/TELEMETRY_INTERFACE.md)
- [CONSOLE_INTERFACE.md](../details/CONSOLE_INTERFACE.md)
- [STORAGE_INTERFACE.md](../details/STORAGE_INTERFACE.md)
- [AIR_PROTOCOL.md](../details/AIR_PROTOCOL.md)
- [MAINTENANCE_PROTOCOL.md](../details/MAINTENANCE_PROTOCOL.md)
- [STORAGE_AND_FLIGHT_LOG.md](../details/STORAGE_AND_FLIGHT_LOG.md)
- [NAVIGATION_AND_ESTIMATION.md](../details/NAVIGATION_AND_ESTIMATION.md)
- [COORDINATE_FRAMES.md](../details/COORDINATE_FRAMES.md)
- [POWER_INTERFACE.md](../details/POWER_INTERFACE.md)
- [OUTPUT_INTERFACE.md](../details/OUTPUT_INTERFACE.md)
- [PORTING_AND_RELEASE.md](../details/PORTING_AND_RELEASE.md)
- [VALIDATION_REQUIREMENTS.md](../details/VALIDATION_REQUIREMENTS.md)
- [DOCUMENT_LIST.md](../details/DOCUMENT_LIST.md)

## 9. 验证边界

Host 测试和 ARM 编译只证明静态实现、接口与可执行测试满足规范。GNSS 配置持久化、JY901B 六方向安装、SX1281 空口、TF 长时间写入和安全输出必须通过上板日志、示波器/逻辑分析仪或双机测试确认；未执行的硬件项目不得描述为已经验证。

VALGET请求使用version 0，接收机响应使用version 1；响应按class/id、layer、position、key和key类型长度真实分类，不能用目标缓存推断成功。启动阶段在任务接管前可使用同步有限等待。运行期CONFIG READ、NAV-SAT和MON-RF只向单槽事务提交请求，由DeviceTask每周期最多推进有限一步；等待响应、逐key回退和超时均跨周期完成，SerialTask不得消费Parser。NAV-SAT/MON-RF仅作为本地维护与LOG诊断能力，不改变AIR；MON-RF明确区分flags中的`jamming_state`与偏移+16的`cw_suppression`。

## 10. 持续 I/O 与通用诊断

USART1/JY901B、USART2/NEO-M9N和USART3/Console的RX DMA固定为`DMA_CIRCULAR`，TX DMA及既有波特率、引脚、Stream/Channel和优先级不变。每个端口只在初始化、UART错误恢复或显式波特率重配置时启动`HAL_UARTEx_ReceiveToIdle_DMA()`；普通IDLE/TC回调只依据`dma_last_position`和本次DMA位置搬运新增字节，不重新启动DMA。软件层继续使用既有`common_ringbuf`，GNSS为128字节DMA/1024字节ring，JY901B为128/512，Console为128/1024，不通过扩大缓冲区掩盖连续接收问题。

各物理端口维护独立32位累计计数，包括接收字节、IDLE/TC事件、ring丢弃、UART ORE/FE/NE/PE、DMA错误、重启、重启失败和`rx_discontinuity_count`。UART错误或ring溢出使断流序号递增；重启失败时`rx_active=0`且当前健康下降。累计历史错误本身不永久锁死健康，健康由当前数据新鲜度、解析状态和链路活动状态决定。

`SystemDeviceIoDiagnostics`是无HAL类型的公共只读诊断结构，以`supported_mask`和`valid_mask`声明可用字段，并标明UART、SPI或无Transport。IMU、GNSS、Telemetry和Console Provider Ops均提供非NULL的`get_io_diagnostics()`；不支持的能力清除对应掩码并返回`SYSTEM_DEVICE_UNSUPPORTED`，不得伪造零值。BARO、MAG和ATTITUDE的`IO`明确返回同一JY901B物理链路并标记`owner=IMU`。GNSS和IMU分别通过`get_io_detail()`追加UBX/NMEA和JY901B帧解析统计。SX1281是SPI分组Transport，不使用UART循环DMA；其诊断只读取TelemetryTask缓存的SPI、BUSY超时和LoRa完整性计数，不从Console路径直接访问SPI。

`<MODULE> IO CLEAR`通过System Console保存当前累计快照作为新的维护显示基线；之后`IO`显示相对于该基线的32位增量。它不改写Provider内部累计计数、断流序号、Parser状态、DMA状态、数据流或健康状态，也不重启设备。IMU、BARO、MAG和ATTITUDE共享同一JY901B基线；GNSS、Telemetry和Console使用各自基线。没有公共I/O诊断能力的模块返回`SYSTEM_DEVICE_UNSUPPORTED`。`SYSTEM CONSOLE IO CLEAR`是唯一合法的四token命令。

正式公共签名为：

```c
SystemDeviceResult (*get_io_diagnostics)(
    SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult (*get_io_detail)(SystemGnssIoDetail *detail);
SystemDeviceResult (*get_io_detail)(SystemImuIoDetail *detail);
```

`diagnostics==NULL`或`detail==NULL`返回`SYSTEM_DEVICE_INVALID_ARGUMENT`。成功时Provider完整覆盖输出结构；`supported_mask`表示实现能力，`valid_mask`表示本次快照有效字段。所有权仍属于Provider，调用方只获得值拷贝，不得保存内部指针。读取操作只读、幂等，不启动DMA、不清零累计计数、不重启Transport，也不直接访问其他任务拥有的硬件。不支持整个查询时Ops函数仍必须非NULL并返回`SYSTEM_DEVICE_UNSUPPORTED`。
