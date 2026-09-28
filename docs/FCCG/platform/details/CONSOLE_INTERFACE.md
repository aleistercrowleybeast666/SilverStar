# SilverStar Console 接口

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

## 1. 范围

Console Interface只负责非阻塞字节输入、字节输出和链路健康。它不解析维护命令，不知道`SYSTEM`、`IMU`等模块名，也不暴露UART、DMA、HAL句柄或具体Console设备类型。System只调用直接接口，具体UART实现由`Devices/Console/UART/Adapter`在链接期唯一提供。

维护命令的分帧、词法解析、权限检查、请求路由和响应格式由System Console与SerialTask负责。

## 2. 能力与健康

```c
#define SYSTEM_CONSOLE_CAP_RX      (1UL << 0)
#define SYSTEM_CONSOLE_CAP_TX      (1UL << 1)
#define SYSTEM_CONSOLE_CAP_STREAM  (1UL << 2)

typedef struct
{
    uint64_t last_receive_timestamp_us;
    uint64_t last_transmit_timestamp_us;
    uint32_t received_byte_count;
    uint32_t transmitted_byte_count;
    uint32_t receive_overrun_count;
    uint32_t transmit_error_count;
    uint8_t initialized;
    uint8_t started;
    uint8_t online;
    uint8_t healthy;
} SystemConsoleHealth;
```

`online`表示链路或后端能够工作；`healthy`还要求没有阻止正常收发的持续错误。没有收到用户字节不等于离线。

## 3. 直接接口

```c
const char *SystemConsoleDevice_NameGet(void);
SystemDeviceResult SystemConsoleDevice_Init(void);
SystemDeviceResult SystemConsoleDevice_Start(void);
SystemDeviceResult SystemConsoleDevice_Stop(void);
void SystemConsoleDevice_Process(void);
SystemDeviceResult SystemConsoleDevice_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemConsoleDevice_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemConsoleDevice_HealthGet(SystemConsoleHealth *health);
SystemDeviceResult SystemConsoleDevice_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult SystemConsoleDevice_SelfTestRun(
    SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemConsoleDevice_Read(uint8_t *data,
                                            uint16_t capacity,
                                            uint16_t *length);
SystemDeviceResult SystemConsoleDevice_Write(const uint8_t *data,
                                             uint16_t length);
```

除纯调度型`SystemConsoleDevice_Process()`外，所有可失败操作统一返回`SystemDeviceResult`。本接口没有Ops对象、函数指针或运行期注册；后端不支持的自检或方向返回`SYSTEM_DEVICE_UNSUPPORTED`。

## 4. 函数语义

| 直接函数 | 形参和输出 | 成功返回 | 其他返回与要求 |
|---|---|---|---|
| `SystemConsoleDevice_Init` | 无 | `SYSTEM_DEVICE_OK` | 初始化静态上下文和私有硬件；UART DMA接收启动失败返回`SYSTEM_DEVICE_IO_ERROR`且不得标记已初始化；重复调用返回`SYSTEM_DEVICE_ALREADY_MATCHED`或保持`SYSTEM_DEVICE_OK`，不得重复启动DMA |
| `SystemConsoleDevice_Start` | 无 | `SYSTEM_DEVICE_OK` | 开始异步收发；未初始化返回`SYSTEM_DEVICE_NOT_READY`；重复调用幂等 |
| `SystemConsoleDevice_Stop` | 无 | `SYSTEM_DEVICE_OK` | 停止收发并使待发送状态安全；重复停止幂等 |
| `SystemConsoleDevice_Process` | 无 | 无 | 推进非阻塞收发状态机，不解析维护命令，不长时间阻塞 |
| `SystemConsoleDevice_InfoGet` | `info`输出 | `SYSTEM_DEVICE_OK` | NULL返回`SYSTEM_DEVICE_INVALID_ARGUMENT` |
| `SystemConsoleDevice_CapabilitiesGet` | `capability_mask`输出 | `SYSTEM_DEVICE_OK` | NULL返回`SYSTEM_DEVICE_INVALID_ARGUMENT` |
| `SystemConsoleDevice_HealthGet` | `health`输出 | `SYSTEM_DEVICE_OK` | 复制自洽快照；NULL返回`SYSTEM_DEVICE_INVALID_ARGUMENT` |
| `SystemConsoleDevice_IoDiagnosticsGet` | `diagnostics`输出 | `SYSTEM_DEVICE_OK` | 返回底层累计I/O快照；NULL返回`SYSTEM_DEVICE_INVALID_ARGUMENT`；只读且不得重启、清零或访问维护命令状态 |
| `SystemConsoleDevice_SelfTestRun` | `result`输出 | `SYSTEM_DEVICE_OK`或`SYSTEM_DEVICE_UNSUPPORTED` | NULL返回`SYSTEM_DEVICE_INVALID_ARGUMENT`；FLIGHT/RECOVERY不得执行破坏性测试 |
| `SystemConsoleDevice_Read` | `data`输出缓冲区、`capacity`容量、`length`实际长度输出 | `SYSTEM_DEVICE_OK` | 只返回完整可用字节批次；无数据返回`SYSTEM_DEVICE_NOT_READY`并令`*length=0` |
| `SystemConsoleDevice_Write` | `data`只读字节缓冲区、`length`长度 | `SYSTEM_DEVICE_OK` | 必须完整接受本次字节串；发送队列暂满返回`SYSTEM_DEVICE_NOT_READY`，不得部分接受后仍报失败 |

`read()`的`data`或`length`为NULL、`capacity`为0，以及`write()`的`data`为NULL或`length`为0时，返回`SYSTEM_DEVICE_INVALID_ARGUMENT`且不得访问硬件。

## 5. 生命周期与所有权

- Console Device唯一拥有其底层收发DMA、环形缓冲区和发送状态机；
- IRQ只搬运字节并更新私有状态，命令解析在SerialTask上下文执行；
- System Console消费`read()`字节并生成维护请求，响应编码后通过`write()`发送；
- FLIGHT/RECOVERY的命令权限由System Console和Lifecycle检查，Console Device不根据命令内容实施权限；
- Console配置中的波特率、UART实例和DMA缓冲区属于具体Device私有配置，不进入本接口。

## 6. System Console公共语义

System Console按[`MAINTENANCE_PROTOCOL.md`](MAINTENANCE_PROTOCOL.md)使用固定5-token数组解析两套grammar：能力端点为`<CAPABILITY> <INSTANCE> <COMMAND> [SUBCOMMAND]`，系统/算法模块为`<SYSTEM_MODULE> <COMMAND> [SUBCOMMAND] [EXTRA]`。它通过Generated descriptor/facade实现`LIST`、`INFO`、`STATUS`、`CAPABILITIES`、`SAMPLE [DETAIL]`、`IO [CLEAR]`和`CONFIG SHOW/READ/VERIFY/APPLY`；不存在实例返回`NOT_PRESENT`且不回退到0。维护协议不公开独立`HEALTH`命令；`STATUS`同时提供当前运行状态和健康摘要。`SHOW`只读软件缓存，`READ`是真实硬件事务，两者不得互换。不支持的公开能力返回`SYSTEM_DEVICE_UNSUPPORTED`对应的`UNSUPPORTED`响应。

正式日志模块名为`LOG`，不接受`TF`别名。BARO、MAG和ATTITUDE的`IO`由endpoint descriptor取得`physical_device_id`，再在同物理设备的端点中解析公共I/O owner；当前显示`owner=IMU owner_instance=0`，不通过模块名硬编码访问JY901B。`IO CLEAR`按物理ID保存只读接口快照作为共享显示基线；Device原始计数、断流序号、Parser、健康和数据流保持不变。GNSS硬件查询由SerialTask有限等待direct instance facade事务结果，但SerialTask不得推进GNSS Parser。

算法观测命令为`ESTIMATOR STATUS`、`ESTIMATOR GNSS`、`ESTIMATOR BARO`、`KF STATUS`和`INS STATUS`。EstimatorTask与InsTask通过System层无HAL类型的静态快照发布既有状态和计数，System Console只复制并格式化，不直接调用APP或Algorithm函数，也不改变原点、融合许可、KF门控/reacquisition或INS传播。`ESTIMATOR GNSS`和`KF STATUS`必须逐字保留旧字段及顺序，只在末尾追加分组NIS/innovation/R/P/counter/reacquire诊断；静态响应容量必须覆盖完整尾部且不得使用动态内存。`SYSTEM READY`追加的`gnss_ready`、`gnss_origin_ready`和`gnss_fusion_enabled`同样来自只读快照；GNSS为Optional，三个字段不得改变既有`ready`和`start_blocking_mask`。

预飞准备命令分为`CAL STATUS/DETAIL/START/FACE/STOP/RESET`和`ALIGN STATUS/DETAIL/START/STOP/RESET`。SystemCalibration独占Mission IMU Correction；SystemAlignment以32-bit capability/selected/required/ready mask负责任务姿态与原点。`ALIGN STATUS/DETAIL`、完成事件和`SYSTEM READY`的source字段只遍历selected sources，Console主框架不得硬编码attitude/GNSS/baro。所有写命令只在START前允许。依赖严格单向：CAL变更立即使Alignment失效，ALIGN操作不得清除Calibration。`SYSTEM READY`从两个只读快照显示Calibration、Alignment和AIR Capability会话字段；AIR握手不得改变本地总体ready。

System Console还消费两个只读边沿：Calibration diagnostic的`face+reason`变化输出一次`EVENT CAL DIAG`，reason清除时允许输出NONE；Alignment首次进入STALE输出一次`EVENT ALIGN STALE`。这些异步文本不得按IMU采样频率刷屏，也不得由Console重新判断运动、改变Calibration/Alignment状态或直接访问Device私有硬件。
