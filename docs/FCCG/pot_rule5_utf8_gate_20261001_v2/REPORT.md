# 2026-10-01 JY 边界修复与 Rule 5 平均门禁

本批从干净 HEAD `9065ae0d91356077b8bd11a5249649f3f2f03e99` 接续，保留此前 selector 批次、171 清单及全部历史证据。实际固件修改只在 JY901B 插件 payload；另修改 owning core 检查器、断言宏的计数说明、AGENTS、标准说明及测试。没有添加运行时断言，没有改 GUI、ESKF、导航资源配置、最终外场工程或任何硬件。

## 用户变更与最终门禁

用户 2026-10-01 06:31 UTC 明确改为“平均每函数2个，不要求长函数都2个”。因此采用 [2006 原论文 Rule 5](https://spinroot.com/gerard/pdf/P10.pdf) 的平均形式；历史 N=2/M=20 是当时项目门禁，保留原结果，不改成通过。其他九条阈值、路径范围、受控例外和失败行为不放宽。所有识别出的短函数和零断言函数进入分母；Flight/Ground 不合并。

| 目标 | 第一方 .c 文件 | 函数分母 | 语法合格候选断言 | 候选平均 | 当前工具结果 |
|---|---:|---:|---:|---:|---|
| Flight | 108 | 2605 | 1591 | 0.610749 | FAIL，一项平均门禁失败 |
| Ground | 15 | 148 | 106 | 0.716216 | FAIL，一项平均门禁失败 |

**1591/106 是机械筛选候选数，不是已经逐条认证的有意义断言数。** 剩余语义有效性 NOT PROVEN，不能以工具结果证明有效密度或整固件合规。代码分类、函数列表和各函数计数见 `flight_rule5_functions.csv`、`ground_rule5_functions.csv`、`rule5_summary.json`。Flight 1670、Ground 95 个零候选函数都包含在分母。长函数稀疏诊断当前为 499/4，非阻断，不是实际缺陷清单；不得称“当前171个错误”。旧 Ground 0 通过适用旧的长函数门禁，不能沿用到新平均门禁。

候选计数排除数值常量、明显自比较恒真/恒假、固定局部/静态地址、已类型化指针的自然对齐、同函数重复谓词、明显副作用及未识别纯函数调用。一个运行时对象宏至多给非空谓词一条信用。多行和嵌套首参数完整读取。语法检查不能自动证明所有宏常量、路径前置检查、别名、同义条件、并发一致性或状态合同；未判定条件仍须人工审查，不能借增加无效断言补足密度。

范围沿用原项目门禁：Flight=`APP/Algorithm/Board/Common/Devices/FlightLogic/Generated/Interfaces/Modules/OS/FreeRTOS/Platform/Protocol/System/Targets`；Ground=`Common/Devices/Generated/Ground/Platform` 下全部 `.c`。这是生成目录的第一方文本扫描，包含范围内未链接/被配置编译掉的函数，未借配置或低计数排除抬平均；头文件、汇编、HAL/CMSIS、官方 RTOS Kernel、FatFs、C 运行库等不进入此分母。函数识别器不是 C AST 或全程序证明。配置为隔离 SilverStar F407 Release、F103C8 Ground，KF6、JY901B、NEO-M9N、SX1281、FreeRTOS；精确配置副本在相邻 v1 的 `input_configuration.ssproject`，哈希与实际命令在各 `result.json`。

## 实际固件缺陷与合同

1. `IMU_Poll` 原先在解析前获取 now，解析期间跨毫秒发布较新时间戳会使无符号相减下溢，刚收帧反而离线。现在在有界解析结束后采样 now。`LastUpdateTickMs==0` 也不能代表“从未收帧”，因为 uint32 毫秒合法回绕到0；Poll/IsOnline 以既有 ValidMask 区分未收帧，保留既有超时阈值与正常轨迹。模计时仍要求调用间隔小于完整计数器周期；不声称异常倒退时间或内部损坏均已证明安全。
2. `IMU_EnsureQuaternionOutput` 初次读取要求 DEFAULT 全集及 QUAT，但写后只检查 QUAT。现在写后的 readback 必须同时满足 DEFAULT 全集与 QUAT；额外位保持允许。only-QUAT、缺 ACC/GYRO/PRESSURE 时返回 `IMU_RESP_INVALID`，不返回初始化成功；cache 如实记录回读寄存器，不伪造 READY。
3. `IMU_WriteRegister` 和 `IMU_SetBaudrate` 的 RxStop 原先丢弃结果。实际 F4 HAL AbortReceive 可以失败，RxStop 仍清除 rx_active；原流程会继续发送配置。现在停止失败先尝试一次有界恢复，返回 `IMU_UART_RX_ERROR`，不发 KEY 或寄存器、不发布 cache 成功。所有 WriteRegister 退出路径检查重启；TX 失败且恢复成功保留 TX 错误，恢复失败返回 RX 错误，成功写但 RX 未恢复也不报告成功。
4. 实际 F4 `PlatformUart_BaudSet` 成功路径已返回 `RxRestart` 结果，因此不额外重复重启。主机测试包装器明确模拟这一 F4 合同；不是 STM32 HAL 实机试验。F1 UART RxStop/RxRestart 当前不支持，所选 F103 是 Ground，未声称 JY/F1 生命周期受此证明覆盖。

NEO-M9N 未修改：F4 DiagnosticsGet 仅在 context/output 无效时失败，非空局部输出、成功 Init、固定有效实例及稳定生成 UART 映射下总会在 critical section 复制快照，没有新的 HAL I/O 失败分支。GetData 对非空 out 无论 online 如何都会复制 snapshot；丢弃 online 返回值并不导致该局部未初始化。此结论限所选有效资源/实例及 F4 合同，不是所有 backend、失效资源或内存损坏证明。未将异常不可达假设包装成 GNSS 故障注入通过；这些异常边界仍 NOT PROVEN。`IMU_SaveConfig` 中尚有未检查 stop/restart；F4 BaudSet 失败恢复中的部分 HAL 返回值也未证明，此批未扩展修复。

## 前后验证及版本归属

完整固件运行记录在 `../pot_jy_rule5_average_batch_20261001_v1/result.json`。该 run 确实执行生成、旧源码负例、ARM、Host、真实 analyzer、架构、链接产物、栈报告；所有退出码/命令/耗时/工具版本/日志哈希及产物哈希均保留。baseline JY bytes 来源前批未改的生成文件，并断言换行归一化后与上述 HEAD 一致；保留 Windows 原字节，旧 checker 得171项历史失败。baseline 22 场景中12通过、10按相同期待失败：跨ms、回绕到0、only-QUAT、缺ACC/GYRO/PRESSURE、stop失败、restart失败、TX+restart双失败、baud-stop失败。修复后22全部通过；包括正常帧、无帧、精确超时边界、跨wrap经过时间、完整/额外位/无需写配置、TX失败恢复及baud重启失败。

| 验证 | 实际记录 |
|---|---|
| v1 相关 pytest | 107 passed，exit0，无 skip |
| v1 生成 Flight Host | 72 executables，4393820 checks，0 failures；8 compile-pass、16 expected compile-fail；exit0 |
| v1 F407 Release / F103 ARM 编译链接 | 均exit0；GCC14.3.1；F407无warning，F103有下面4条链接warning |
| v1 F407 static-analysis | 实际 `-fanalyzer -c` 编译并链接，exit0，无warning；非 syntax-only |
| v1 F103 first-party analyzer | 14个源单独 `-fanalyzer -c`，全部exit0 |
| v1 analyzer negative canary | double-free 报错并exit1，证明不是未执行 analyzer |
| v1 architecture / artifact / stack-report | 工具均exit0，仅其声明范围 |
| v2 最终 Rule5/UTF8 checker pytest | 46 passed，exit0 |
| v2 全部相关 pytest | 109 passed，exit0，无 skip |
| v2 新隔离生成 Flight/Ground power10 | 各make exit2（checker exit1），平均不足；其他原文本规则未报失败 |
| v2 新隔离生成 architecture-check | exit0 |

v2只修改 checker 输入解码及测试，未改变固件。v2 `result.json` 记录 v2/v1 全部 `.c/.h/.ld` 路径与 SHA256 相同，以及对应完整 v1 运行引用；没有将旧二进制说成 v2 重新构建，也没有声称执行了拼接的综合full-suite。所有 Host/ARM/analyzer结果按 v1 的精确源码与配置归属报告。

## 覆盖修复、开发失败与保留证据

PowerShell 5.1 默认按本地编码解码 UTF-8 源文件；真实 JY 源码仅改变 LF/CRLF 就从50个函数变成96个。旧 baseline 直接 git-show 得 LF 的早期 run只报告165项，不能将少6个严格诊断当作修复。旧日志完整保留在 `../pot_jy_boundary_batch_20261001_v2/`；另一次 baseline 编译失败在 `../pot_jy_boundary_batch_20261001/`，不是通过。后续 baseline 用归一化确认与 HEAD 相同的原始 Windows 字节得到171项，二者边界清楚。

最终 owning checker 使用 strict UTF-8 decoder；坏编码明确 FAIL，不能静默缩小分母。真实整份 JY 的 LF/CRLF 函数行列表相等测试，前版失败且缺46行（`before_utf8_regression.log`），最终通过。另保留 escaped literal newline 的物理行，避免转义换行吞掉定位。v1 standalone coverage失败和 UTF8诊断日志保留于相邻目录，v1统计不冒充解码稳健版本；本次原生生成的最终数字碰巧与v1相同，仍重新执行了v2门禁。

fixture 开发中曾缺 Adapter include、未设置合法 local gravity、引用不存在 system_user_config；分别修正并保留正式失败run。平均 checker 首轮开发有4失败（31通过），涉及数值识别把a/b当hex字符、空扫描处理、多行probe误用字面backtick-n；修正后35，再44，最终46通过。未改变期望来放行缺陷。旧 run/result/log 不覆盖、不染绿。

## 资源、第三方与未证明项

F407实际链接 artifact report：FLASH used316068/rem208220；main SRAM used101280/rem29792；CCM used55432/rem10104；heap reserved0/runtime_symbols0。F103 size：text21884/data12/bss14112。仅是链接静态占用，不能证明任务栈余量。栈报告输出是其启发式估计；任务路径、HAL/RTOS/C库间接调用、动态帧、main/MSP与ISR嵌套完整上界仍 NOT PROVEN；STM32 WCET、导航精度、板端/飞行资格均 NOT PROVEN。

F103链接有4条 newlib warning：`_close/_lseek/_read/_write` 未实现。完整日志保留，未抑制或扩大例外。ARM退出0不等于严格Rule10无warning，因此整固件原十条不能声明PASS。F407及F407 analyzer本轮无warning。

HAL/CMSIS、FreeRTOS11.3.0、FatFs及libc/libc_nano/libm/libgcc/libnosys沿用上游许可证与版本来源，未修改。相邻v1 `third_party_inventory.json` 保存实际map、库名、版本marker及源哈希。HAL callbacks、RTOS task entry/Kernel内部间接调用、库未解析路径受控排除于第一方文本门禁，但其递归/栈/时序后果仍须证明；不声称vendor满足原十条。未使用GUI隐藏功能绕过门禁，未刷机/START/执行器操作，未push/tag/Release或打包。

所有当前源码和新证据将独立本地提交，最终HEAD由任务回报提供；历史源码基线/dirty快照、生成配置、命令、退出码、完整失败与哈希保存在上述记录。本批完成后停止，等待下一指令，不批量给低密度函数补断言。
