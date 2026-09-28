# SilverStar Build 与 Targets

> 当前平台：SilverStar 0.0.12。当前生产验证限于SilverStar_F407 / SS0.5。

## 1. 唯一Source Graph

`SilverStar.ssproject`严格JSON与安装的manifest共同确定配置。FCCG解析一次Source Graph，Make、原生EIDE和VS Code共享sources、includes、defines、libraries、CPU/FPU、linker及forced include。VS Code任务调用生成的Make，不独立扫描文件。

生成Make显式包含`Targets/<Target>/target.mk`及`Generated/project_sources.mk`。Target提供MCU构建属性，后者提供已经解析的源图。源文件存在不代表应当编译；禁止wildcard、递归扫描、重复源或独立IDE exclude重新决定图。

## 2. Target与组件选择

匹配的MCU/Platform manifest拥有Target Profile。项目中的`build.target_profile`是派生完整性锁，不是GUI选择或Python MCU型号默认值。当前目标`SilverStar_F407`、MCU `STM32F407VET6`与Board `SilverStar 0.5`是三个不同概念。

默认配置为Release；Debug仍可选。更换Device、Strategy或Mode应修改FCCG项目并重新生成，不通过临时Make变量选择另一套未物化的源图。Calibration correction常驻，OneFace/SixFace采样procedure按选择编入；空选保留NONE/Identity/READY。Estimator空选不编译KF6。Deployment空Mode Set合法，不自动部署。

Alignment插件包括GravityKnownYaw、GravityMagTriad、HardwareQuat6AxisKnownYaw和HardwareQuat9Axis。实际可选项取决于完整qualification契约，不能由raw能力或设备型号推断。JY901B静态hardware-quaternion alignment资格不等于任务期姿态权威，也不自动授予magnetic TRIAD资格。

## 3. 生成与编译

Generate Code先物化工程，不自动编译或执行质量门。用户随后打开VS Code/EIDE，或运行生成工程中的命令：

```powershell
mingw32-make CONFIG=Release all
mingw32-make CONFIG=Debug all
mingw32-make list-sources
mingw32-make host-tests
mingw32-make architecture-check
mingw32-make power10-check
mingw32-make static-analysis
mingw32-make artifact-check
mingw32-make memory-report
mingw32-make CONFIG=Release stack-report
mingw32-make CONFIG=Debug stack-report
```

Release使用`-O2 -g`，Debug使用`-Og -g3`，均保留assert、静态分配、section GC与严格warning。Arm GNU用于固件，Host GCC用于电脑端测试；`GCC_PATH`指定Arm工具目录，`HOST_CC`可指定含空格的Host GCC完整路径。工具路径是主机配置，不进入generation fingerprint。

正常固件编译不运行FCCG/Python生成器。独立离线`stack-report`需要Python读取真实`.su`和ELF call graph，具体预算及局限见[运行时安全](RUNTIME_SAFETY.md)。它不是GUI中一个独立BuildAction。SSLOG codec是生成工程中普通受控C源码；声明式schema由FCCG用于生成decoder与校验，不能由另一套Python wire encoder代替真实C Golden测试。

## 4. 输出与增量Apply

```text
build/FCCG/<Target>/Release/
build/FCCG/<Target>/Debug/
build/FCCG/<Target>/StaticAnalysis/<Config>/
build/FCCG/Host/Tests/
```

所有生成构建产物均位于`build/FCCG/`；EIDE也使用此边界内的隔离输出。默认固件身份为`SilverStar_0_0_12`，输出ELF/MAP/HEX/BIN；来源是FCCG `src/silverstar_fccg/app/version.py`。对象保留源码目录层级，不能用`notdir`压平同名文件。listing仅在`LISTING=1`时生成。

普通Apply保护工程自有Component Source，保持未变化managed文件时间戳及build依赖文件。质量结果时间戳属于项目本地元数据，不改变生成状态。

## 5. FreeRTOS与内存

当前选择官方FreeRTOS-Kernel V11.3.0的`list.c`、`queue.c`、`tasks.c`和Cortex-M4F port。使用静态任务分配与Idle memory hook，不引入heap、CMSIS-RTOS2、旧CubeMX defaultTask或无消费者的Kernel模块。

F407 Target通过forced include映射vendor-neutral placement，linker/startup负责CCMRAM段及清零。CPU-only静态栈及算法上下文可进入CCMRAM；UART/SDIO DMA、HAL/DMA handles和DMA参与的buffer必须在主SRAM。新的MCU必须独立定义DMA/cache、placement及预算，不能照搬F407物理地址。

## 6. CubeMX与资源闭合

Imported vendor快照位于`HardwareGenerated/STM32CubeMX/`，替换须经危险计划确认。当前STM32F4插件采用CubeMX 6.15.0、FW_F4 V1.28.3及插件拥有的HAL/CMSIS精确策略。CubeMX提供外设初始化和FatFs App/Target glue，MCU/Platform提供受控HAL与FatFs core，Storage Device拥有存储业务。

HAL timer timebase从生成源发现，验证频率/IRQ契约，不硬编码TIM1，不静默接受SysTick，也不能与PWM共用timebase timer。只按inventory和所选consumer启用provider。I2C/PWM已有软件实现；Classic CAN为reserved，不能提供给普通consumer。

Verified Board以`connections.json`为唯一logical ID→固定alias权威，经snapshot symbol闭合到生成Platform表。CubeMX扫描顺序不能重排logical ID；映射或snapshot变化必须使binding fingerprint失效。Custom CubeMX仍使用手工分配及其inventory-index语义。

## 7. 验证与工具进度

Host tests验证真实C模块和协议codec；architecture检查解析源图及Make/EIDE一致性；Power-of-Ten、static-analysis、artifact和stack门各自报告结果。构建成功不等于flash、硬件或飞行验证，实际执行快照只记录在[根VALIDATION](../../VALIDATION.md)。

长任务使用`FCCG_PROGRESS|<TASK>|PLAN|<total>`及成对BEGIN/DONE，只有DONE推进进度。成功到100%，失败/取消保留最后实际进度。预期的Host编译拒绝是成功测试结果，原始编译诊断仍保留在详细日志。

## 8. 新Target流程

新增Target须提供MCU/Platform、Board约束、所需Device/Adapter、资源胶水、OS port和构建参数，并证明源图唯一、对象路径无冲突、Release/Debug可构建、时间/IRQ契约正确及内存预算通过。通用System不得识别具体Target名称；其他MCU在各自插件和验证完成前仅为扩展目标。
