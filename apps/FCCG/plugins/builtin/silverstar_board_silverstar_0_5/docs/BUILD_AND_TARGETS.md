<!-- FCCG package-local documentation -->
> Package-local implementation note. This file may describe its reference
> snapshot; it is not the current platform specification. In the FCCG
> workspace, `docs/platform/README.md` and `docs/AIR_CALIBRATION_CONTRACT.md`
> are authoritative. Runtime rules: `docs/platform/details/RUNTIME_SAFETY.md`.
> Actual acceptance snapshots: root `VALIDATION.md`.

# SilverStar Build 与 Targets

> 文档版本：0.0.12
> 适用范围：SilverStar 0.0.12

## 1. 唯一source graph

顶层`Makefile`是正式入口，只显式包含Target和第一方通用manifest：

```text
Targets/<Target>/target.mk
BuildSystem/first_party.mk
```

Target manifest再显式选择`Platform/<MCU>/module.mk`、Device core及其`Adapter/`、`Board/<Board>/module.mk`、`FlightLogic/module.mk`、`Generated/module.mk`，并选择该Target需要的HAL、FatFs和FreeRTOS vendor source manifest。这样MCU/链接参数和vendor source资格由Target拥有，通用Make不认识任何具体MCU或板卡。

所有`.c`逐文件登记。禁止`$(wildcard ...)`、递归目录扫描、IDE手工exclude和另一个未跟踪的object列表。Make在解析阶段拒绝重复C/ASM源。

## 2. Target选择

当前唯一Target：

```make
TARGET_PROFILE ?= SilverStar_F407
CONFIG ?= Debug
```

`Targets/SilverStar_F407/target.mk`声明：

```make
IMU_DRIVER       := JY901B
GNSS_DRIVER      := NEO_M9N
TELEMETRY_DRIVER := SX1281
PLATFORM_BACKEND := STM32F4
BOARD_PROFILE    := SILVERSTAR_0_5
ALIGNMENT_STRATEGY  ?= GravityKnownYaw
INS_STRATEGY        ?= Coning2Sculling2
ESTIMATOR_STRATEGY  ?= KF6
LANDING_STRATEGY    ?= BarometerImuWindow
DEPLOYMENT_STRATEGY ?= MultiTrigger
TOOLCHAIN_PREFIX := arm-none-eabi-
TARGET_MCU_FLAGS := -mcpu=cortex-m4 ...
TARGET_LDSCRIPT  := STM32F407XX_FLASH.ld
```

其中MCU为`STM32F407VET6`，Board为`SilverStar 0.5`，固件Target为`SilverStar_F407`；三者不是同一个概念。当前`BOARD_PROFILE`值为`SILVERSTAR_0_5`。

这些变量是目标可读描述；实际选择通过该Target只include相应module manifest实现。未被include的driver/backend即使存在于仓库也不会进入固件。

## 3. 构建命令

```powershell
mingw32-make TARGET_PROFILE=SilverStar_F407 CONFIG=Debug all
mingw32-make TARGET_PROFILE=SilverStar_F407 CONFIG=Release all
mingw32-make TARGET_PROFILE=SilverStar_F407 CONFIG=Debug clean
mingw32-make TARGET_PROFILE=SilverStar_F407 CONFIG=Debug artifact-check
mingw32-make "HOST_CC=D:\msys64\ucrt64\bin\gcc.exe" host-tests
mingw32-make list-sources
mingw32-make power10-check
mingw32-make static-analysis
mingw32-make memory-report
```

Debug使用`-Og -g`，Release使用`-O2`。两者都启用section GC、基础warning和关键`-Werror`。固件工具链前缀为`arm-none-eabi-`，可用`GCC_PATH`指定目录。Host Test使用独立的Windows本机GCC，由`HOST_CC`传入完整可执行文件路径；路径可以含空格，不能传入Arm交叉编译器。

飞行日志格式0.0的Record ID、metadata和逐字段little-endian serializer/deserializer是`Protocol/SSLOG/Inc/sslog_records.h`与`Protocol/SSLOG/Src/sslog_records.c`中的普通受控源码，现有wire magic仍为`SSLOG0`。authoritative firmware build直接编译它们，不运行Python或代码生成器；`Protocol/SSLOG/schema/`仅保存离线解析器参考资料，不是固件构建输入。

`Generated/Src/project_metadata.c`与`project_device_instances.c`分别是当前project descriptor和按实例direct facade；两者进入authoritative Make及EIDE镜像，不是运行期插件表。未来FCCG可按Physical Device/Capability Endpoint组合重写它们，但必须保留静态有界调用、连续class instance编号和显式`physical_device_id`。

## 4. 输出

```text
build/FCCG/SilverStar_F407/Debug/
build/FCCG/SilverStar_F407/Release/
build/FCCG/SilverStar_F407/StaticAnalysis/Debug/
build/FCCG/SilverStar_F407/EIDE/
build/FCCG/Host/Tests/
```

目标产物名为`SilverStar_0_0_12.elf/.map/.hex/.bin`。C对象由源码相对路径派生，例如：

```text
build/FCCG/SilverStar_F407/Debug/Platform/STM32F4/Src/platform_uart_stm32f4.o
build/FCCG/SilverStar_F407/Debug/Devices/IMU/JY901B/Src/jy901b_device.o
```

不允许使用`$(notdir ...)`压平对象名。

## 5. FreeRTOS source set

`BuildSystem/freertos.mk`只登记：

```text
ThirdParty/FreeRTOS-Kernel/list.c
ThirdParty/FreeRTOS-Kernel/queue.c
ThirdParty/FreeRTOS-Kernel/tasks.c
ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM4F/port.c
```

不得登记`heap_*.c`、`Core/Src/sysmem.c`、`timers.c`、`event_groups.c`、`stream_buffer.c`或`croutine.c`，除非未来确有第一方使用、配置和验收同时变更。`.ioc`和链接脚本的C heap reserve均为0；旧`Middlewares/Third_Party/FreeRTOS`与`cmsis_os2.c`不得恢复。

## 6. EIDE、VS Code与CubeMX

`.eide/eide.yml`恢复为当前F407可直接调用Arm GNU Toolchain的开发镜像。它只列出Make正式选择的目录和显式virtual sources，使用Cortex-M4F、single-precision FPU、hard-float、C11、`STM32F407XX_FLASH.ld`和`platform_memory_target.h` forced include，输出隔离在`build/FCCG/SilverStar_F407/EIDE`。

Make manifest仍是唯一权威source graph。`architecture-check`枚举EIDE实际C/S集合并与`make list-sources`比较，同时逐项比较include和define；任何漂移都失败。当前YML为可手工维护镜像，不允许反向驱动Make。未来FCCG可以从`SilverStar.ssproject`生成/覆盖该镜像、Target/Board选择和`Generated/`薄胶水。

CubeMX只生成F407 HAL/外设初始化。`.ioc`不管理FreeRTOS和APP任务。重新生成后必须复核：

- 没有恢复`Core/Src/freertos.c`、defaultTask或CMSIS-RTOS2；
- startup/linker/Core/Drivers/FATFS路径仍与manifest一致；
- UART DMA、NVIC、TIM1 HAL tick、SysTick和GPIO映射没有漂移；
- USER CODE以外的必要手工修改已有说明或同步配置。

SS0.5是已验证Board，因此`connections.json`而不是CubeMX资源扫描顺序拥有Platform逻辑编号。
重新生成后必须保持：RADIO_NSS/RST/BUSY/DIO1对应GPIO 0–3，P_CONTROL1/2对应4/5，
IMU_CAL_LED对应6，GNSS_RST/TIMEPULSE对应7/8。`.ioc`与`main.h`只负责把这些固定别名
解析成实际handle或port/pin并进行一致性验证；不得把inventory `logical_index`重新写回
Board逻辑编号。FCCG生成前执行Platform Resource Closure Check，任何别名、符号或表项漂移
都必须失败，不得按首个资源或扫描序号回退。

## 7. 自动目标

```powershell
mingw32-make host-tests
mingw32-make "HOST_CC=C:\path with spaces\gcc.exe" host-tests
mingw32-make architecture-check
mingw32-make power10-check
mingw32-make static-analysis
mingw32-make TARGET_PROFILE=SilverStar_F407 CONFIG=Debug artifact-check
```

`host-tests`先输出所选编译器的`--version`和`-dumpmachine`，只接受能在当前Windows生成并运行EXE的GCC；脚本统一UTF-8输出，普通编译失败会保留完整命令参数与stdout/stderr，预期编译失败至少保留实际GCC错误原因。`architecture-check`同时评估manifest/EIDE镜像源集、文件存在性、重复源、目标backend、FreeRTOS精简源集、无heap/CMSIS、飞行日志普通源码的双向endian codec、禁止struct直写wire，以及authoritative manifest不调用Python/生成器。`power10-check`对第一方代码执行10条硬门禁；`static-analysis`在隔离输出目录对第一方启用`-fanalyzer`。`artifact-check`检查ELF/MAP/HEX/BIN、CCMRAM/主SRAM归属和预算，并拒绝allocator或旧OS/heap object。

## 8. Strategy source graph

Strategy变量只决定哪个组件manifest被include；runtime配置不得选择未编入实现。当前正式图包含Alignment Common + GravityKnownYaw、INS Coning2Sculling2、Estimator KF6、Landing BarometerImuWindow、Deployment MultiTrigger、Calibration及Algorithm Common。GravityMagTriad、HardwareQuat6AxisKnownYaw和HardwareQuat9Axis只由独立Host tests编译。

构建级None验收：

```powershell
mingw32-make ESTIMATOR_STRATEGY=None list-sources
```

该输出不得包含`Algorithm/Estimator/KF6/Src/navigation_kf.c`。Calibration modes与MultiTrigger trigger modes不做source-level极限裁剪；trigger mask=0表示合法空集。

## 9. CCMRAM与DMA

F407 Target用forced include把`PLATFORM_CPU_FAST_BSS`映射到`.ccmram_bss`，linker/startup负责section定义和清零。CCMRAM不可被F407 DMA访问，因此UART DMA/ring、Logger aggregation、SDIO/FatFs DMA和HAL/DMA handles必须保留主SRAM。新增Target不得复制F407 section名到Component Source；它必须自行定义placement语义、linker、startup和artifact预算。

## 10. 新Target流程

新增Target只允许增加目标所需的Target、Board、Platform backend、Device Adapter、Generated glue manifest与配置；不要修改通用System来识别Target名。必须证明：

1. source list唯一且只含选中模块；
2. 对象路径不冲突；
3. Debug/Release clean build均生成完整产物；
4. OS port、interrupt priority和tick分工正确；
5. architecture check扩展到新backend；
6. 文档只声明实际完成的编译/硬件验证范围。

## FCCG runtime safety contract (2026-09-05)

FCCG initializes the System Indicator before task creation; SS0.5 retains
logical GPIO 6 (`IMU_CAL_LED`/PA1), active-low ON. Calibration capability is
build-derived: empty/OneFace/SixFace/both advertise `0x01/0x03/0x05/0x07`.
`SystemCalibration_Start()` rejects unsupported procedures before invalidating
state. Empty builds initialize and reset to NONE identity READY, retaining the
Required effective `CALIBRATION_RESULT` snapshot.

ALIGN_START retains immediate parameter/state/capability checks and existing ACK
mapping; the full Alignment Process runs periodically in FlightTask. Calibration
solve work also stays in FlightTask, and origin reset returns BUSY without waiting
in Telemetry/Serial. Task stacks are checked with real Release/Debug `.su` and ELF
call graphs using `make CONFIG=Release stack-report` and `make CONFIG=Debug
stack-report`; the JSON report records configured bytes, estimates and margins.
Overflow diagnostics retain stable task identity, state and valid cached HWM with
no heap/I/O or unsafe TCB/name traversal; fail-stop protections remain enabled.

AIR M0, Maintenance 0.0, SSLOG 0.0 and `.ssdecoder` 1.1 retain their versions and
wire/Record layouts. Continuous SS0.5 testing is still required for boot/blink
polarity, repeated AIR/Serial calibration/alignment/reset commands, all task HWMs,
MSP/interrupt nesting, source locks and effective calibration log snapshots.
