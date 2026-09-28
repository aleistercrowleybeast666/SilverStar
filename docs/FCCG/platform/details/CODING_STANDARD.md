# SilverStar 第一方嵌入式编码约束

> 文档版本：0.0.12
> 适用范围：SilverStar 0.0.12第一方运行时代码

## 1. 适用边界

强制目标覆盖`APP`业务代码、`Algorithm`、`Board`、`Common`、`Devices`（含`Adapter`）、`FlightLogic`、`Generated`薄胶水、`Interfaces`、`Modules`、`Platform`第一方代码、`Protocol`和`System`。STM32 HAL、CMSIS、FreeRTOS Kernel、FatFs和原始第三方库属于记录在案的第三方偏差；不得为满足第一方规则而私改官方源码。

## 2. 内存与控制流

- 禁止运行期`malloc/calloc/realloc/free`、`pvPortMalloc/vPortFree`；
- 任务、queue、bus、ring、descriptor、parser和协议buffer均使用编译期容量；
- 第一方诊断文本使用`CommonFormat_Print/VPrint`有界静态格式器，不调用会带入newlib heap路径的`snprintf/vsnprintf`；
- 禁止递归；
- 循环必须有静态上界、容量上界或可证明的deadline；周期函数不得无限等待外设；
- ISR短小，只记录字节/计数/事件；不解析协议、不打印、不执行System动作；
- switch/default和状态机必须处理未知值，不能依赖未初始化fall-through。

## 3. 函数与返回值

- 函数名沿用项目“名词_动宾”风格，中间使用大驼峰，例如`Lora_TryStartNextTx`；
- 被上层调用且返回成功/错误的新增函数优先定义明确enum，类型名大驼峰并以`Result`结尾；
- 不忽略具有行为意义的返回值；可用`warn_unused_result`强化；
- 输出参数先校验NULL，成功时完整覆盖；
- 函数保持单一职责，复杂事务拆为可测试的有界步骤；长函数需说明所有权/状态原因并优先逐步收敛；
- 不用assert替代可恢复运行期错误；真正不变量可使用编译期`_Static_assert`或目标fail-stop断言。

## 4. 全局状态

- 优先模块私有`static`状态；
- 必须跨模块读取时提供窄接口和快照，不暴露可写全局；
- ISR与任务共享状态使用Platform临界区或清晰单生产者/单消费者结构；
- 禁止运行期对象注册表、可变函数指针表和callback registry；
- FreeRTOS任务入口所需的`TaskFunction_t`属于OS API边界，不能扩展为业务插件机制。

## 5. 依赖边界

- System/Algorithm/Protocol/Interfaces不得包含vendor或具体Device头；
- Device不得包含HAL、FreeRTOS、System Interface或MCU生成头；
- Platform公共API不得包含vendor类型；MCU backend不得认识具体Device；
- 每个Device组件内的`Adapter`是该Device native类型到公共Interface的唯一转换层；Adapter不得包含HAL、具体Board或Target头；
- `Board/<Board>`保留物理事实和固定映射；电源/存储由Device拥有，指示/任务动作由对应FlightLogic实现拥有；
- AIR、SSLOG等Protocol不直接操作transport；
- SSLOG多字节wire字段只经`sslog_records.*`逐字段显式endian codec；禁止`memcpy`/cast整个C struct作为payload；
- 新源文件必须登记显式manifest，禁止目录扫描和IDE-only source selection。

## 6. 常量与版本

- 禁止无语义magic number；协议offset、长度、token、设备寄存器和超时使用命名常量；
- header guard按`__文件名大写_扩展名`，`.`替换为`_`；
- 固件版本、AIR profile、SSLOG format和Record version分别管理，不能机械联动；
- 当前`Generated/`只允许保存FCCG拥有的已评审薄胶水：项目资源映射、日志默认配置和descriptor metadata；不放算法、飞行判定或设备驱动；
- 当前authoritative Make不运行Python或生成器。SSLOG codec为普通受控源码，schema只作离线解析器参考。

## 7. 单位、坐标与时间

- 公共字段名必须带单位后缀，例如`_us`、`_mps2`、`_radps`、`_pa`；
- `q_nb`固定表示body到ENU；不得用注释外的隐式四元数方向；
- 区分sample timestamp、receive timestamp、monotonic time、mission time和UTC；
- 定点/raw与物理单位同时存在时用不同字段和valid bit；Device Adapter负责转换。

## 8. Warning与验证

- Host测试使用C11、`-Wall -Wextra -Werror -pedantic`；
- ARM构建至少把未检查结果、隐式声明、incompatible pointer和return type设为error；
- 修改后运行与风险成比例的Host测试、architecture check和目标构建；
- 协议改动补长度、offset、endian、CRC和unknown输入测试；
- 硬件结论必须来自实测证据，静态检查/Host/ARM编译分别报告。

## 9. Power of Ten强制门禁

Power of Ten在0.0.12中是第一方安全关键运行时C代码的强制标准。自动检查范围为`APP/Algorithm/Board/Common/Devices/FlightLogic/Generated/Interfaces/Modules/Platform/Protocol/System/OS`中的第一方`.c`，明确排除`backup/`、CubeMX/HAL、CMSIS、官方FreeRTOS Kernel、FatFs和原始第三方库。

| Rule | 强制要求 |
| --- | --- |
| 1 | 简单控制流；禁止`goto`、递归和不可证明退出的业务循环。OS调度循环和确定性fail-stop单独记录。 |
| 2 | 所有有限循环具有静态迭代上界；deadline只能提供提前退出。 |
| 3 | 全静态内存；禁止allocator、`heap_*.c`、`sysmem.c`，linker heap为0。 |
| 4 | 规范化函数长度不超过60行。 |
| 5 | 超过20行的函数至少两个有意义的release-on运行时断言；断言表达式无副作用。 |
| 6 | 最小作用域；模块状态为`static`并通过窄接口访问。 |
| 7 | 检查有意义的返回值和参数；有意忽略必须显式`(void)`。 |
| 8 | 第一方`.c`避免条件编译；配置用普通常量分支，不兼容性用`_Static_assert`。 |
| 9 | 每个表达式最多一级解引用；禁止第一方runtime function pointer/registry。固定task entry直接传给`xTaskCreateStatic()`及Idle memory hook的双指针签名是精确记录的FreeRTOS API偏差，不得存储、转发或扩散。 |
| 10 | 第一方严格warning为error，并通过Arm GCC `-fanalyzer`。 |

`SilverStarAssert_Fail()`保存固定大小fault record、设置故障状态并执行deterministic fail-stop；它不使用heap、formatter或callback，release构建不可关闭。硬件上下文不安全时timestamp保持invalid，不能为了记录SSLOG而继续执行不可信代码。

验证入口：

```powershell
mingw32-make power10-check
mingw32-make static-analysis
```

不得用无意义assert、全局warning suppression或把第一方源码移出检查范围来取得通过。

## 10. 内存放置规则

第一方Component使用`PLATFORM_CPU_FAST_BSS`等vendor-neutral语义，具体section由Target定义。F407的CCMRAM只允许CPU-only确定性对象和任务栈；DMA buffer、HAL/DMA handle、Logger聚合buffer、SDIO/FatFs DMA对象和第三方radio DMA候选必须位于DMA可达主SRAM。任何新增placement都要通过map/ELF artifact检查，不能只凭attribute源码判断。
