# SilverStar 移植与发布规范

> 文档版本：0.0.12
> 适用范围：SilverStar 0.0.12

## 1. 当前边界

0.0.9建立vendor-independent Platform contract，但当前唯一实现、ARM编译和既有硬件事实仍是`SilverStar_F407`。不得把“无需修改通用层的设计目标”写成“已支持STM32H7/GD32/NXP/RP2040/RISC-V”。

## 2. 同板更换设备

同类别设备替换应只涉及：

1. `Devices/<Class>/<Model>/` native driver；
2. 该Device组件内`Adapter/`的native-to-Interface映射；
3. `module.mk`和Target选择；
4. Board逻辑资源连接；
5. Target qualification与descriptor；
6. Device/Adapter/系统契约Host测试和硬件验收。

不得在System散布`#if DEVICE_MODEL`，不得新增Device×MCU port，不得通过运行期Ops/Registry选择。若换设备需要改System，先判断公共Interface是否确有缺口并单独评审。

设备包最低交付：

- native header/source及私有config；
- 只依赖Platform/Board逻辑ID；
- parser/config/state-machine Host测试；
- 真实、保守的build qualification与noise recommendation；
- explicit `module.mk`；
- Adapter字段/单位/error mapping测试；
- UART/SPI/I2C/GPIO/时钟、供电、启动恢复和实测证据文档。

## 3. 新MCU/Board移植

新增MCU目标通常增加：

```text
Platform/<MCU>/
Board/<Board>/
Targets/<Target>/
Generated/                  项目资源、日志配置和metadata薄胶水
Cube/vendor generated tree  按该生态维护
```

Platform backend必须实现目标实际使用的UART、SPI、GPIO、ADC、Time、Critical等API，保持公共头无vendor类型。DMA、cache、interrupt、tick、clock和启动文件属于backend/Target；Device不能感知。

新Board改变物理约束、固定映射和目标描述；业务服务仍由Device/FlightLogic拥有，不复制System/Algorithm/Protocol。若同一MCU多板共享backend，物理资源表应由项目胶水提供，不能把设备名或板名写入Platform backend。

## 4. OS移植

当前OS依赖是官方FreeRTOS-Kernel V11.3.0。新Target必须：

- 选择正确官方port并只编译所需Kernel模块；
- 保持static allocation和无heap；
- 提供Idle task静态内存hook；
- 定义目标interrupt priority和SysTick路由；
- 保持HAL/vendor tick与RTOS tick职责清晰；
- 复核七个APP任务的优先级、栈深和周期，不机械复制F407数值；
- 不引入CMSIS-RTOS2或大型OS abstraction。

## 5. 发布构建

发布候选必须在干净工作输出上执行：

```powershell
mingw32-make TARGET_PROFILE=<target> CONFIG=Debug clean all
mingw32-make TARGET_PROFILE=<target> CONFIG=Release clean all
mingw32-make host-tests
mingw32-make architecture-check
mingw32-make power10-check
mingw32-make static-analysis
```

核对：目标版本与构建tag、ELF/MAP/HEX/BIN、Flash/RAM、层级对象、无duplicate、无heap/CMSIS对象、只含选中backend/driver、任务栈高水位、`Generated/`文件集合受控，以及固件编译不运行Python/生成器；独立离线stack-report可使用Python。

## 6. 协议与文档版本

Firmware、AIR profile、SSLOG format、SSLOG Record version和Maintenance version分别管理。平台/OS/构建重构不自动提升wire版本。若wire确实改变，必须按对应协议文档分配version/profile/Record version并增加双端测试。

发布同步更新：

- `CHANGELOG.md`和根`README.md`；
- `docs/platform/SilverStar_<version>.md`及`DOCUMENT_LIST.md`；
- `AGENTS.md`当前规范入口；
- `TARGETS.md`路线/当前状态；
- `VALIDATION.md`实际执行结果；
- 所有仍把旧版本描述为“当前”的细节文档。

历史版本规范和patch note保持历史，不把旧架构机械改写成新事实。

## 7. 验证表述

发布报告分开列出：

- 已实现；
- 已静态检查；
- 已Host测试；
- 已ARM编译；
- 已HIL/台架；
- 已上板/飞行验证。

没有串口日志、示波器/逻辑分析仪、双机或实际飞行证据时，不得把backend可编译写成硬件已验证。CubeMX重新生成风险、第三方改动、hardware-only路径和未完成目标必须列入剩余问题。

## 8. Target Memory职责

Component Source只能声明vendor-neutral用途（例如CPU-fast BSS或DMA-accessible），不能写`.ccmram_bss`、DTCM、具体地址或cache维护。MCU/Target插件负责：

- 把语义映射到实际section或普通SRAM；
- 提供linker MEMORY/section布局、load/zero符号和startup初始化；
- 声明DMA可达性、cache/coherency、对齐和容量预算；
- 配置Make/EIDE forced include与相同linker；
- 提供map/ELF artifact规则，验证关键symbol而非只检查源码attribute。

F407的CCMRAM仅CPU可访问，所以任务栈、Estimator和Alignment大上下文可迁入，而UART/SDIO DMA、HAL/DMA handle、Logger aggregation和DMA参与的第三方buffer不得迁入。新的MCU若没有CCMRAM可以把CPU-fast宏定义为空；若有D-Cache/TCM，必须独立评审DMA coherency，不能照搬F407结论。

CubeMX重新生成可能覆盖startup、linker选择或`.ioc`派生源码。发布必须重新检查CCMRAM清零、heap=0、UART DMA/NVIC、从生成源发现的HAL timer timebase及GPIO映射，并运行Debug/Release artifact-check。

## 9. EIDE与FCCG

当前`.eide/eide.yml`与Make从严格JSON项目及manifest解析出的同一Source Graph生成。新Target发布前必须同步EIDE源、include、define、CPU/FPU ABI、linker、forced memory include和隔离输出目录，并由architecture-check比对。FCCG根据已选MCU/Board/Device/Strategy生成或覆盖EIDE YML与Target memory配置，但不在运行时生成或选择算法，也不得修改已复制并归工程所有的Component Source。
