# SilverStar Storage与Log Sink接口

> **文档版本：0.0.12**
> **适用范围：SilverStar 0.0.12**

## 1. 两层接口

`system_storage_if.h`表示文件型存储能力：mount/open/write/sync/close。`system_log_sink_if.h`表示日志字节流目的地：session begin/write/flush/end。LoggerTask只依赖Log Sink直接接口。

```text
SilverStar 0.5 File Log Sink Service
    ↓ SystemStorage_* direct calls
SilverStar 0.5 SDIO Storage Service
    ↓
FatFs + SDIO + DMA

未来UART Stream Log Sink
    ↓
UART DMA，不需要mount或文件名
```

因此更换TF、SPI Flash或eMMC时只替换Storage Device；换为串口记录模块时替换Log Sink Service，飞行日志格式0.0和电脑解析器保持不变。

维护协议中的抽象模块名固定为`LOG`，不因当前介质是TF而改变。`LOG INFO`只暴露Device名称和通用接口标识，`LOG STATUS`读取`SystemStorageHealth`。维护协议不公开`LOG HEALTH`，也不接受任何`TF`模块别名。公共接口没有独立Transport统计，因此当前的`LOG IO`和`LOG IO CLEAR`返回`SYSTEM_DEVICE_UNSUPPORTED`，不得从System层泄漏SDIO、FatFs或卡类型。

## 2. Log Sink直接接口

```c
const char *SystemLogSink_NameGet(void);
SystemDeviceResult SystemLogSink_Init(void);
SystemDeviceResult SystemLogSink_SessionBegin(const SystemLogSessionInfo *session);
SystemDeviceResult SystemLogSink_Write(const uint8_t *data,
                                       uint32_t length,
                                       uint32_t *written_length);
SystemDeviceResult SystemLogSink_Flush(void);
SystemDeviceResult SystemLogSink_SessionEnd(void);
SystemDeviceResult SystemLogSink_HealthGet(SystemLogSinkHealth *health);
```

Log Sink不得解释Record payload，只接收完整飞行日志格式0.0字节流；该字节流的文件magic为`SSLOG0`。短写必须返回错误并报告实际长度。

## 3. Storage直接接口

保持静态不透明句柄：

```c
const char *SystemStorage_NameGet(void);
SystemDeviceResult SystemStorage_Init(void);
SystemDeviceResult SystemStorage_Mount(void);
SystemDeviceResult SystemStorage_Open(const char *path,
                                      SystemStorageOpenMode mode,
                                      SystemStorageFileHandle *handle);
SystemDeviceResult SystemStorage_Write(SystemStorageFileHandle *handle,
                                       const uint8_t *data,
                                       uint32_t length,
                                       uint32_t *written_length);
SystemDeviceResult SystemStorage_Sync(SystemStorageFileHandle *handle);
SystemDeviceResult SystemStorage_Close(SystemStorageFileHandle *handle);
SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *health);
```

两个接口都由选中Storage Device唯一实现，不存在Ops对象或运行期注册。

## 4. TF目录边界

目标组合代码位于：

```text
Devices/Storage/SdSdioFatFs/Src/storage_service.c
Devices/Storage/SdSdioFatFs/Src/log_sink_service.c
```

CubeMX快照的胶水保留在`HardwareGenerated/STM32CubeMX/`下，以下为快照内相对路径：

```text
Core/Src/sdio.c
FATFS/App/
FATFS/Target/
```

这些CubeMX文件不是System接口的一部分。当前`storage_service.c`是唯一包含FatFs类型的第一方板级组合文件；System、APP、Interfaces和通用Device不得出现`FIL`、`FRESULT`、`SD_HandleTypeDef`。

## 5. 所有权

- LoggerTask是Log Sink唯一调用者；
- SilverStar 0.5 File Log Sink Service是Storage文件操作唯一调用者；
- 生产任务只能向LoggerBus提交记录；
- 任何Storage错误不得阻塞InsTask或EstimatorTask；
- 所有对象静态分配。

## 6. 公共辅助类型

```c
#define SYSTEM_STORAGE_INVALID_SLOT UINT16_MAX

typedef enum
{
    SYSTEM_STORAGE_OPEN_CREATE_TRUNCATE = 0,
    SYSTEM_STORAGE_OPEN_CREATE_NEW,
    SYSTEM_STORAGE_OPEN_APPEND
} SystemStorageOpenMode;

typedef struct
{
    uint16_t slot;
    uint16_t generation;
} SystemStorageFileHandle;
```

句柄由Storage Service填写并拥有其有效性规则；调用方只能按值保存和回传，不能解释为FatFs对象或自行修改。`SystemStorage_Close()`成功后句柄失效。generation必须阻止已关闭旧句柄误操作新文件。

## 7. Storage函数语义

| 直接函数 | 形参与输出 | 成功返回 | 错误、NULL与幂等语义 |
|---|---|---|---|
| `SystemStorage_Init` | 无 | `SYSTEM_DEVICE_OK` | 初始化静态后端；重复调用幂等；不支持后端返回`SYSTEM_DEVICE_UNSUPPORTED` |
| `SystemStorage_Mount` | 无 | `SYSTEM_DEVICE_OK` | 未初始化返回`NOT_READY`；重复挂载返回`ALREADY_MATCHED`或`OK` |
| `SystemStorage_Open` | `path`只读NUL结尾路径、`mode`、`handle`输出 | `SYSTEM_DEVICE_OK` | `path/handle=NULL`、空路径或mode非法返回`INVALID_ARGUMENT`；失败不留下有效句柄 |
| `SystemStorage_Write` | 有效`handle`、只读`data`、非零`length`、`written_length`输出 | `SYSTEM_DEVICE_OK`且`*written_length==length` | 任一指针NULL或length=0返回`INVALID_ARGUMENT`；短写返回`IO_ERROR`并保留实际长度；不得越过调用返回持有`data` |
| `SystemStorage_Sync` | 有效`handle` | `SYSTEM_DEVICE_OK` | NULL返回`INVALID_ARGUMENT`；重复同步幂等；失效句柄返回`BAD_STATE` |
| `SystemStorage_Close` | 有效`handle` | `SYSTEM_DEVICE_OK` | NULL返回`INVALID_ARGUMENT`；重复关闭返回`ALREADY_MATCHED`或`BAD_STATE`且不得关闭别的文件 |
| `SystemStorage_HealthGet` | `health`输出 | `SYSTEM_DEVICE_OK` | NULL返回`INVALID_ARGUMENT`；复制自洽快照，不触发挂载或文件I/O |

不支持操作返回`SYSTEM_DEVICE_UNSUPPORTED`。接口不暴露HAL、FatFs、SDIO、UART或具体介质类型。Storage只描述初始化、挂载、打开、写入、同步、关闭和健康，不扩展当前没有需求的目录遍历、删除、重命名或随机访问。

## 8. Log Sink函数语义

Log Sink直接函数统一返回`SystemDeviceResult`。`SystemLogSink_SessionBegin(NULL)`返回`INVALID_ARGUMENT`，重复开始返回`ALREADY_MATCHED`或`BAD_STATE`；`SystemLogSink_Write()`的NULL/零长度规则与Storage写入相同，成功必须完整接受；`Flush`与`SessionEnd`幂等且不阻塞生产任务；`SystemLogSink_HealthGet(NULL)`返回`INVALID_ARGUMENT`。输入缓冲区所有权始终属于调用方，Device/FlightLogic实现只在调用期间读取。任何日志错误只更新计数/健康，不得阻止START。
