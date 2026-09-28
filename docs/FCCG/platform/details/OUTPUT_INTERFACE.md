# SilverStar Output 与回收执行器接口

> **项目：SilverStar**  
> **文档版本：0.0.12**
> **状态：Draft / 未发布**  
> **适用范围：SilverStar 0.0.12**

> `0.0.12` 表示协议、接口和实现均处于首次发布前阶段。文档中的结构可以在评审后调整，不提供跨版本兼容承诺。

## 1. 范围

SS0.5提供两路GPIO功率输出。平台接口应为未来电热丝、舵机、继电器和回收装置预留，但本文件不定义具体开伞算法。

## 2. 输出接口

```c
typedef enum
{
    SYSTEM_OUTPUT_SAFE = 0,
    SYSTEM_OUTPUT_ARMED,
    SYSTEM_OUTPUT_ACTIVE,
    SYSTEM_OUTPUT_FAULT
} SystemOutputState;

typedef struct
{
    uint64_t timestamp_us;
    uint32_t sequence;
    uint32_t requested_duration_ms;
    uint32_t remaining_duration_ms;
    SystemOutputState state;
    uint8_t channel;
    uint8_t commanded_active;
    uint8_t physical_active;
    uint8_t fault;
} SystemOutputStatus;

const char *SystemOutput_NameGet(void);
SystemDeviceResult SystemOutput_Init(void);
SystemDeviceResult SystemOutput_SafeSet(void);
SystemDeviceResult SystemOutput_Arm(uint8_t channel);
SystemDeviceResult SystemOutput_Activate(uint8_t channel,
                                         uint32_t duration_ms);
SystemDeviceResult SystemOutput_Deactivate(uint8_t channel);
SystemDeviceResult SystemOutput_StatusGet(uint8_t channel,
                                          SystemOutputStatus *status);
void SystemOutput_Process(void);
```

System通过上述直接函数调用唯一Board Output Service；不存在Ops对象或运行期注册。`SystemOutput_StatusGet()`的`status`为NULL或通道超出目标范围时返回`SYSTEM_DEVICE_INVALID_ARGUMENT`。`Init`和`SafeSet`重复调用必须保持幂等；已安全关闭的通道再次`Deactivate`返回`SYSTEM_DEVICE_ALREADY_MATCHED`或`SYSTEM_DEVICE_OK`，不得产生新的物理脉冲。不支持`Arm`或定时激活的后端返回`SYSTEM_DEVICE_UNSUPPORTED`。

## 3. Mission Action接口

FlightRecovery不直接依赖Output通道或GPIO。任务动作通过以下公共接口表达：

```c
typedef enum
{
    SYSTEM_MISSION_ACTION_START = 0,
    SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY
} SystemMissionAction;

const char *SystemMissionAction_NameGet(void);
SystemDeviceResult SystemMissionAction_Init(void);
SystemDeviceResult SystemMissionAction_Execute(SystemMissionAction action);
```

完整契约如下：

- `SystemMissionAction_Init()`初始化所选静态MissionAction实现；成功返回`SYSTEM_DEVICE_OK`，已初始化返回`SYSTEM_DEVICE_ALREADY_MATCHED`。底层Output尚未就绪或缺少必需操作时返回`SYSTEM_DEVICE_NOT_READY`。
- `SystemMissionAction_Execute()`执行一个已定义动作；未知枚举返回`SYSTEM_DEVICE_INVALID_ARGUMENT`，未初始化返回`SYSTEM_DEVICE_NOT_READY`，后端不支持时返回`SYSTEM_DEVICE_UNSUPPORTED`，其余错误原样返回。
- Device/FlightLogic实现为单例、静态生命周期且不使用动态内存。`Init`幂等；`Execute`不是一般幂等写接口，物理one-shot由FlightRecovery在调用前锁存保证。
- 本接口没有输出参数或可传NULL的指针参数。未来增加不支持的动作时必须由现有函数明确返回`SYSTEM_DEVICE_UNSUPPORTED`，不得把NULL函数指针作为能力表达。
- 接口不暴露HAL、GPIO、UART、FatFs或具体执行器类型。

当前调用链固定为：

```text
System FlightRecovery（决定何时执行）
    -> System Mission Action Interface
        -> SilverStar Mission Action Service（决定如何执行）
            -> System Output Interface
                -> SilverStar Output Service -> Platform GPIO
```

第一版Mission Action Service先`SystemOutput_Arm(channel)`再`SystemOutput_Activate(channel, duration_ms)`；激活失败时尽力`SystemOutput_Deactivate(channel)`。当前映射和测试默认值位于`FlightLogic/MissionAction/GpioOutput/Inc/mission_action_output_config.h`：

| 逻辑动作 | 用户所称功率口 | Output Interface通道 | 板级输出 | 默认脉冲 |
|---|---:|---:|---|---:|
| `MISSION_START` | 0 | 1 | `PROJECT_RESOURCE_POWER_OUTPUT_1`（SilverStar 0.5为`P_CONTROL1`） | 1000 ms |
| `PARACHUTE_DEPLOY` | 1 | 2 | `PROJECT_RESOURCE_POWER_OUTPUT_2`（SilverStar 0.5为`P_CONTROL2`） | 1000 ms |

Output Interface通道为1-based，通道0始终非法。1000 ms是没有历史PWROUT脉冲参数时采用的台架默认值，尚未完成真实执行器与安全链路验证，外场前必须按实际负载复核。

## 4. FlightRecovery与失败语义

START真正提交并进入FLIGHT后，FlightRecovery只执行一次`SYSTEM_MISSION_ACTION_START`。收到START命令、START被拒绝或事务仍pending时均不得执行该动作。

Deploy只对新的有效Estimator timestamp+sequence评价；唯一例外是START-relative `DELAY`直接使用mission time。FlightRecovery在非FLIGHT阶段只登记最新快照身份而不评价判据，因此Lifecycle切换时重复读到的同一份预飞快照不算新飞行样本。`SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK`按位组合TILT/APOGEE_VZ/DELAY，多个bit为OR关系；TILT默认比较START冻结initial rocket axis，同周期成立时保存完整matched mask。当前默认APOGEE_VZ only且`SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS=0`，首个越阈新样本立即确认；配置为正数时，确认跨度来自一系列新合格样本的measurement timestamp，同一快照被2 ms FlightTask重复读取不能推进计时。条件确认后先锁存one-shot，再执行`SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY`。动作成功才生成开伞成功事件并请求`SystemLifecycle_EnterRecovery()`；动作失败保留诊断结果、不伪造成功、不进入RECOVERY，也不快速重试。

Landing默认`BARO_IMU_WINDOW`：RECOVERY直接读取健康、有效且新鲜的`EstimatorPressureSnapshot.altitude_m`，用短窗口线性回归打开candidate，再在同一个`[t0,t1]`窗口验证Baro斜率/span与corrected gyro、`abs(|a|-g)`、样本数、覆盖率和freshness。该判据不读取KF高度/vz、INS position或GNSS高度；Baro不可用时保持RECOVERY，不fallback。`STILLNESS`保留台架/HIL兼容；`IMPACT_THEN_STILLNESS`只允许明确声明可靠冲击采样能力的IMU，当前JY901B capability为0，选择该模式会在编译期拒绝。Telemetry、Logger或Console观察失败只重试各自事件交付，不得改变物理动作或状态锁存。

## 5. 安全规则

- BOOT默认安全关闭；
- System Profile用`output_channel_count`声明逻辑通道数量；READY前必须确认全部已声明通道均为`SAFE`且`physical_active=0`，不得只抽查通道1；
- 本地写命令默认禁用；
- START前测试需要编译宏和生命周期许可；
- 飞行中的输出必须由Flight/Recovery Manager调用；
- 超时激活应由设备层硬限时保护；
- START提交沿用既有MISSION_START事件；开伞与着陆成功边沿写各自EVENT，动作失败保留快照并异步输出Console诊断。
