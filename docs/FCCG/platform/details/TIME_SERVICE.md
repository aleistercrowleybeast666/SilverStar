# SilverStar Time Service

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

> `0.0.12` 表示协议、接口和实现均处于首次发布前阶段。文档中的结构可以在评审后调整，不提供跨版本兼容承诺。

## 1. 时间域

SilverStar区分三种时间：

1. **Monotonic Time**：上电后单调递增微秒时间；
2. **Mission Time**：相对START的时间；
3. **UTC/GNSS Time**：可选绝对时间映射。

IMU积分、KF、超时和队列排序只能使用Monotonic Time。


## 2. 底层时间源接口

`SystemTime`只负责Mission Time、UTC映射和通用并发保护，不得直接包含HAL、具体定时器句柄或MCU寄存器。底层单调时钟由Platform接口提供：

```c
PlatformResult PlatformTime_Init(void);
uint32_t PlatformTime_Ms(void);
uint64_t PlatformTime_Us(void);
void PlatformTime_DelayMs(uint32_t delay_ms);

PlatformCriticalState PlatformCritical_Enter(void);
void PlatformCritical_Exit(PlatformCriticalState state);
```

约束：

- 当前Target必须且只能链接一个Platform时间/临界区backend；
- `PlatformTime_Init()`必须返回可检查的`PlatformResult`；
- Platform backend负责底层计数器溢出扩展和单调性；
- System层不得知道底层使用SysTick、TIM、DWT或其他计数器；
- 更换MCU或时间基准时，替换`Platform/<mcu>/`实现并保持公共接口不变。

SilverStar 0.0.12当前实现位于：

```text
Platform/STM32F4/Src/platform_time_stm32f4.c
Platform/STM32F4/Src/platform_critical_stm32f4.c
```

它使用STM32F407的HAL毫秒Tick和TIM1的1 MHz子毫秒计数器形成64位微秒单调时间。

## 3. 必须接口

```c
SystemDeviceResult SystemTime_Init(void);
uint64_t SystemTime_GetMonotonicUs(void);
uint64_t SystemTime_GetMonotonicUsFromIsr(void);

void SystemTime_MissionStart(uint64_t timestamp_us);
void SystemTime_MissionStop(uint64_t timestamp_us);
void SystemTime_MissionReset(void);
uint8_t SystemTime_IsMissionStarted(void);
uint64_t SystemTime_GetMissionUs(void);
uint8_t SystemTime_GetMissionUsAt(uint64_t monotonic_us,
                                  uint64_t *mission_us);
```

`SystemTime_Init()`调用并检查`PlatformTime_Init()`，再检查连续读取不倒退；失败结果传播给System Startup。核心单调时间不可用属于允许硬停止的安全致命错误。

UTC接口可以预留：

```c
typedef enum
{
    SYSTEM_UTC_SOURCE_NONE = 0,
    SYSTEM_UTC_SOURCE_GNSS,
    SYSTEM_UTC_SOURCE_EXTERNAL
} SystemUtcSource;

typedef struct
{
    uint64_t monotonic_timestamp_us;
    int64_t utc_time_us;
    uint32_t uncertainty_us;
    SystemUtcSource source;
} SystemUtcMeasurement;

typedef struct
{
    uint64_t monotonic_timestamp_us;
    int64_t utc_time_us;
    uint32_t uncertainty_us;
    SystemUtcSource source;
    uint8_t valid;
} SystemUtcSnapshot;

SystemDeviceResult SystemTime_UpdateUtcMapping(
    const SystemUtcMeasurement *measurement);
SystemDeviceResult SystemTime_GetUtc(SystemUtcSnapshot *snapshot);
```

`measurement`或`snapshot`为NULL时返回`SYSTEM_DEVICE_INVALID_ARGUMENT`。在尚未建立UTC映射时，`SystemTime_GetUtc()`返回`SYSTEM_DEVICE_NOT_READY`且不得伪造绝对时间。重复提交同一有效映射必须保持幂等；任何UTC更新只改变映射快照，不得回拨或校正Monotonic Time。

## 4. 时间戳语义

所有传感器样本必须区分：

```c
uint64_t sample_timestamp_us;
uint64_t receive_timestamp_us;
```

- `sample_timestamp_us`：估计的物理量测时刻；
- `receive_timestamp_us`：完整数据被飞控接收并接受的时刻。

当前允许二者暂时相等，但接口不得合并。未来可利用GNSS iTOW、PPS或固定传输延迟修正sample time。

Power Interface同样遵循该规则。当前同步ADC采样可以暂时令两个时间戳相等；未来CAN BMS、SMBus智能电池等后端必须按各自测量和接收时序分别赋值。

## 5. 单调性和溢出

- 时间不得倒退；
- 若底层基于32位计数器，必须在服务内部扩展到64位；
- ISR与任务读取必须原子安全；
- GNSS校时不得修改Monotonic Time；
- 所有日志公共头统一使用Monotonic Time；
- AIR协议使用Mission Time或明确标记的Boot Time。

## 6. 禁止事项

System和Algorithm之外的业务代码不应自行保存多个`start_tick`。Algorithm不得直接调用HAL时间函数。
