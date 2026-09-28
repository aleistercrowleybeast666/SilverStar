<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

# SilverStar Device Interface 与构建期Adapter

> 文档版本：0.0.12
> 适用范围：SilverStar 0.0.12

0.0.12删除运行期Provider Ops、VTable、Registry和`GetOps()`。System与具体Device之间只有独立公共Interface和随Device组件选择的直接Adapter；链接器在每个固件目标中解析唯一一套`System*`符号。

## 1. 三层类型

```text
Interfaces/Inc/system_*_if.h
    System公共类型与直接函数

Devices/<Class>/<Model>/Adapter/Src/*_adapter.c
    结果、配置、能力、时间戳与字段转换

Devices/<Class>/<Model>/Inc/*_device.h
    设备native类型、命令、parser和状态机
```

Device native类型不得包含System结构；Interface不得包含具体Device结构；Adapter是唯一允许同时看到两者的层。Adapter与Device core随同一`module.mk`选择，但Adapter不得包含HAL、具体Board或Target头。

## 2. 公共返回值

`Interfaces/Inc/system_device_types.h`定义统一`SystemDeviceResult`：

| 值 | 语义 |
|---|---|
| `SYSTEM_DEVICE_OK` | 请求完成且结果有效 |
| `ALREADY_MATCHED` | 当前状态/配置已满足，无需重复动作 |
| `NOT_READY` | 已选择但尚未达到执行条件 |
| `OFFLINE` | 设备存在但当前通信离线 |
| `UNSUPPORTED` | 当前Adapter、Device-owned service或内部硬件服务不实现该公共能力 |
| `INVALID_ARGUMENT` | NULL、范围或组合非法 |
| `TIMEOUT` | 有界事务超时 |
| `IO_ERROR` | transport/外设失败 |
| `VERIFY_FAILED` | 写后真实回读不匹配 |
| `BAD_STATE` | 生命周期、所有权或冻结状态不允许 |
| `VALUE_ADJUSTED` | 请求已执行但被合法量化/调整 |
| `INTERNAL_ERROR` | 不应出现的内部一致性错误 |
| `CONFIG_NO_ACTION` | 配置项无需动作 |
| `CONFIG_DELEGATED` | 由共享物理owner统一处理 |
| `NOT_EXECUTED` | 前置阶段失败而未运行 |
| `BUSY` | 运行所有者或非阻塞事务占用中 |
| `NOT_PRESENT` | capability类别存在，但请求的静态实例未生成/未启用 |

可由上层调用并需要检查结果的新增函数，按项目命名规则使用`...Result` enum或`SYSTEM_WARN_UNUSED_RESULT`。禁止以`bool`掩盖错误原因。

## 3. 基础信息与健康

采样类Interface通常提供：

```c
const char *SystemXxx_NameGet(void);
SystemDeviceResult SystemXxx_Init(void);
SystemDeviceResult SystemXxx_Start(void);
SystemDeviceResult SystemXxx_Stop(void);
void SystemXxx_Process(void);
SystemDeviceResult SystemXxx_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemXxx_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemXxx_HealthGet(SystemDeviceHealth *health);
```

约束：

- `NameGet()`返回静态存储字符串；
- `Init()`可幂等报告`ALREADY_MATCHED`，不得动态分配；
- `Process()`必须有确定线程owner、非阻塞或有界；
- 成功时完整覆盖输出结构，失败时不得伪造有效字段；
- `SystemDeviceHealth`区分initialized、started、online、healthy、last sample/receive time与累计错误；
- 禁用capability时System Startup不会调用对应Interface；Adapter不需要通过空函数模拟“已启用”。

## 4. Sample契约

IMU、GNSS、Barometer、Magnetometer、Hardware Quaternion和Power分别定义公共sample。共同规则：

- `sample_timestamp_us`表示物理测量或Device可确定的采样时刻；
- `receive_timestamp_us`表示完整数据进入主控的时刻；
- `sequence`只在发布新样本时递增；
- `valid_mask`逐字段声明有效性，不能用全零值代替“不支持”；
- `LatestSampleGet()`返回快照，不消费序列；`NextSampleGet()`只用于明确的单消费者流；
- Adapter负责单位、坐标、raw宽度和有效位映射；不得在System重复解析设备frame；
- native快照共享时必须在Platform临界区内整结构复制，不能暴露半更新状态。

IMU公共样本是Calibration、Alignment、Inertial和Telemetry的唯一逻辑输入。APP不直接读取JY901B native全局结构。

## 5. 配置与验证

有配置能力的Interface使用类别专用Config和`SystemDeviceConfigReport`：

```c
SystemDeviceResult SystemXxx_ConfigApply(
    const SystemXxxConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult SystemXxx_ConfigVerify(
    const SystemXxxConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult SystemXxx_EffectiveConfigGet(SystemXxxConfig *config);
```

`requested_mask`、`required_mask`、`supported_mask`、`applied_mask`、`matched_mask`、`delegated_mask`、`verify_failed_mask`和`failed_mask`必须分别表达阶段结果。Apply成功不等于Verify成功；软件cache不等于真实硬件回读。

共享物理设备只能由唯一owner执行写入和持久化。例如当前JY901B的IMU Adapter负责UART配置；Barometer/Magnetometer/Hardware Quaternion Adapter返回`CONFIG_DELEGATED`或读取共享effective snapshot，不重复unlock/save/parser。运行owner激活后，可能破坏stream的维护配置事务返回`BUSY`。

正常启动默认不得自动修改或保存传感器配置。持久化必须由明确策略启用并记录目标层、ACK、回读结果和恢复方案。

## 6. I/O诊断

`SystemDeviceIoDiagnostics`只包含vendor无关累计量和有效掩码。UART DMA细节由Platform backend汇总，Adapter映射为公共诊断；逻辑共享接口可设置`owner=IMU`等owner字段，但不得访问第二条物理链路。

`supported_mask`声明实现能力，`valid_mask`声明本次值是否有效。`IO CLEAR`只在System Console保存显示基线，绝不清除Platform/Device累计量、parser、序列或运行状态。

## 7. Runtime owner

具有持续字节流的IMU/GNSS提供`SystemImu_RuntimeOwnerActivate()`和`SystemGnss_RuntimeOwnerActivate()`。激活后：

- 对应APP任务是唯一`Process()`调用者；
- 维护命令只能提交到owner可安全执行的有界事务；
- 不允许Abort/DeInit UART来抢占正常数据流；
- 逻辑共享Adapter只读快照；
- ISR只进入Platform缓冲/事件，不直接调用Device或System。

## 8. Build-time qualification

运行期capability说明“当前实例能输出或执行什么”；构建期qualification说明“该设备/配置是否被评审用于某算法”。两者不能互相替代。

Device包可提供`*_build_capabilities.h`，Target在`target_system_config.h`映射到通用`SYSTEM_SELECTED_*`宏；`system_user_capability_validation.h`集中校验。例如：

- Gravity alignment要求可用且合格的accel/gyro；
- TRIAD要求合格absolute magnetic vector；
- hardware quaternion静态Initial Alignment要求对应6/9轴preflight qualification，任务期权威姿态另用authoritative qualification，二者不得混用；
- Stillness和Baro/IMU landing要求通过IMU静止判断资格，impact landing还要求通过冲击捕获资格；
- KF6要求选中IMU/GNSS/Baro的静态噪声推荐或完整User override；
- 非零deploy trigger要求Mission Action支持deploy动作。

System源码只读取通用qualification宏，不包含设备名。具体宏映射只允许在Target组合层。

## 9. Descriptor接口

`system_descriptor_if.h`提供按索引读取的项目静态描述；当前表由`Generated/Src/project_metadata.c`实现：

- `SystemDescriptor_DeviceCountGet/DeviceGet`；
- `SystemDescriptor_DeviceClassInstanceCountGet`；
- `SystemDescriptor_DeviceFind(device_class, instance_id, ...)`；
- `SystemDescriptor_AlgorithmCountGet/AlgorithmGet`；
- `SystemDescriptor_ConfigDigestGet`。

`SystemDeviceDescriptor`同时携带`descriptor_id`、`physical_device_id`、`device_class`和类别内`instance_id`。相同`physical_device_id`表示多个Capability Endpoint共享一个实际模块；它不能由driver/model hash推断，也不等于instance ID。descriptor表有公共编译期上界，但每个实例写成独立SSLOG Record，不把设备ID塞入固定长度payload数组。descriptor接口是只读project metadata，不是运行期Device Registry，也不包含函数地址。

`Generated/Inc/project_device_instances.h`提供Maintenance、Sensor Status、Native Log和FCCG使用的按实例静态facade。每个正式能力具有Count及其实际支持的Info/Health/Sample/Config/I/O操作；实现先验证descriptor，再使用有界`switch(instance_id)`静态direct case，不存在实例明确返回`NOT_PRESENT`。JY901B、NEO-M9N和SX1281声明`multi_instance_ready=true`并各自最多4实例，Generated resource accessor将每个source instance绑定到独立硬件资源；实际Driver Host测试覆盖context隔离，fixture不进入Target图。不得把facade扩展成运行期注册表、function pointer dispatch或动态选择器。算法侧仍只有一个Canonical输入：IMU只在Calibration/Alignment前选择并锁定，绝不在飞行中自动切换，也不实现Voting、Multi-INS或Multi-EKF。

## 10. 新设备流程

新增同类设备：

1. 在`Devices/<Class>/<Model>/`实现native driver，Host mock下验证parser/config/state machine；
2. 只通过Platform/Board逻辑资源访问外设；
3. 声明真实构建资格、推荐噪声和`multi_instance_ready`；未验证能力与同插件重复资格保持0；
4. 在该Device的`Adapter/`实现现有直接Interface和native-to-common映射；
5. 创建`module.mk`并只由选中Target include；
6. 更新`Generated/`中的project descriptor和物理资源映射、Board资源、Profile能力及相关文档；
7. 运行Host、architecture-check及目标clean Debug/Release构建；
8. 通过实际硬件证据再声明online、性能或算法资格。

换同类设备不应修改System、Algorithm或Protocol。若公共Interface确实缺字段，先进行跨设备接口评审并补兼容测试。

## 11. 类型专用规范

- [IMU_INTERFACE.md](IMU_INTERFACE.md)
- [GNSS_INTERFACE.md](GNSS_INTERFACE.md)
- [BAROMETER_INTERFACE.md](BAROMETER_INTERFACE.md)
- [MAGNETOMETER_INTERFACE.md](MAGNETOMETER_INTERFACE.md)
- [HARDWARE_QUATERNION_INTERFACE.md](HARDWARE_QUATERNION_INTERFACE.md)
- [POWER_INTERFACE.md](POWER_INTERFACE.md)
- [OUTPUT_INTERFACE.md](OUTPUT_INTERFACE.md)
- [TELEMETRY_INTERFACE.md](TELEMETRY_INTERFACE.md)
- [CONSOLE_INTERFACE.md](CONSOLE_INTERFACE.md)
- [STORAGE_INTERFACE.md](STORAGE_INTERFACE.md)
- [TIME_SERVICE.md](TIME_SERVICE.md)
