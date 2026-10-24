# 采集功能 MSP/ISR 静态收尾（2026-10-19，v7）

仅复用 v6 的当前 F407VET6 ELF、167份源级栈报告和回归日志；本轮无生产代码、白名单、栈大小或硬件改动，未重跑原门禁/回归。
**任务静态边界已列明；运行期MSP仅得到条件包络；启动全过程仍NOT PROVEN，停在此阻碍。**

## 门禁失败与输入状态

复用 `stack_gate_04` 的真实退出1：
`Changed or missing reviewed callback compilation input: System/Alignment/Inc/system_alignment.h`。
该文件**存在**，当前规范化SHA-256为`6c0d5853b6c5bd70f6c670210e3120abb8aee1d5e8ebdf21d3d1751265371f30`；
失败是版本身份未获原记录认可，**不是缺失文件**。门禁在此短路，不能把后续项目称为已通过。

本次复查167份C源对应的`.o/.d/.su`均齐全，所有`.d`引用文件均存在；缺失编译产物0、缺失编译输入0。
另有42个尚未获现有版本记录认可的源/头输入，逐项路径、散列及完整差异保留在v6清单；没有自动加散列。
原检查器、阈值和例外未修改。源级关键契约审查及全固件接受状态仍NOT PROVEN。

## 任务上界及保留量

单位B；“上界”仅指v6已解析回调目标、当前编译输入下的保守函数级调用图，不是门禁PASS或实测。
256B是PSP上下文预算，未借用其他任务、主SRAM闲置字节或CCM余量。

| 任务 | 配置 | 静态调用链 | 加256后 | 保留量 |
|---|---:|---:|---:|---:|
| Device | 2560 | 1888 | 2144 | 416 |
| INS | 3072 | 1984 | 2240 | 832 |
| Estimator | 4096 | 3100 | 3356 | 740 |
| Flight | 4096 | 3392 | 3648 | 448 |
| Logger | 3072 | 1728 | 1984 | 1088 |
| Serial | 6144 | 4248 | 4504 | 1640 |
| Telemetry | 4096 | 1928 | 2184 | 1912 |
| Idle | 512 | 0 | 256 | 256 |

八项配置、地址及总额27648B均不变，全部在CCM。原始IMU入口在Device、MAG latest入口在INS/启动检查，
POLL/事件输出在Serial，TF工作在Logger；PC拟合不进入MCU任务。完整路径见v6报告。
函数级模型保守叠加尾调用和不做常量实参细化；因此最大组合不必是一条可实际走通的轨迹。

## IRQ与FPU假设及新的MSP结论

实际源/链接审查：Group4，DMA/UART/EXTI=5，SDIO=6，SysTick/PendSV/HAL TIM1时基=15；SVC=0用于启动。
同组同优先级不互抢，正常可屏蔽IRQ最多按15→6→5三级嵌套。未取tail-chain或BASEPRI缩小峰值的收益。

按[ST PM0214 §2.3.7、Figure12、§4.6](https://www.st.com/resource/en/programming_manual/dm00046982-stm32-cortexm4-mcus-and-mpus-programming-manual-stmicroelectronics.pdf)：
基本硬件帧32、FP扩展72，另留最多4对齐，共108B。FreeRTOS开启ASPEN/LSPEN，**lazy不等于无需预留空间**。
PSP再有r4-r11/LR的36B和s16-s31的64B，合计208B，低于既有256B预算48B。

MSP特别核对了实际汇编：

- `prvPortStartFirstTask`重置MSP并清CONTROL；SVC用人工PSP帧返回首任务，留下32B基本SVC帧作为运行期MSP基线。
- PendSV的`r0!`保存是PSP，不能再算到MSP；但`push {r0,r3}`真实占MSP **8B**，其naked函数`.su=0`未包含此项。
- 对HAL DMA/UART，仅把本次**仍被链接的函数**中回调字段赋值取保守并集：完成4种、半完成2种、错误2种、abort3种；
  不把已被GC的通用注册/SPI/DMAEx API作为目标。未知目标会保持未证，并非让原门禁接受一个新白名单。
  此并集仍以有效句柄、所有权及现有生命周期为条件，不是已接受的精确可达集。
- `.preinit_array`空，`.init_array`只有`frame_dummy`；实际TM范围为空且弱hook为零。
  因而libc初始化已知软件峰值24B，Reset/main最大已知软件链仍564B。

| MSP模型 | 条件包络 | 对1024B保留量的余量 |
|---|---:|---:|
| 调度器运行后，正常可屏蔽IRQ | **628** | **396** |
| 再保守加入HardFault和NMI各一层 | **844** | **180** |
| 未做初始化阶段IRQ掩码/活跃区间细化的启动包络 | **1268** | **超244，未闭合** |

628 = SVC基线32 + 低优先级软件96 + SDIO软件104 + 高优先级软件180 + 两层硬件帧216。
其中96已补PendSV的8B；故障模型再加216。启动粗包络为main564 + 上述中断软件/内层硬件596 + 首次MSP硬件帧108。
这些组合有过度估计，不代表实际溢出；**1268>1024意味着该粗模型无法证明保留量足够**。
1024只是链接配置保留量，并非硬件/MPU强制栈界限；未用链接闲置RAM把它扩大。

当前IRQ可达图没有安装采集函数；本功能没有新增IRQ、回调或ISR软件帧。这个**增量结论**不等于既有MSP全程已证明。
HardFault/NMI取当前终止循环，不声称递归fault、压栈失败或MCU恢复已覆盖。

## 停止点与确切测量需求

静态阻碍是：尚无被接受的初始化阶段“哪些外设中断实际可触发、外设中断掩码与MSP活跃帧”的联合证明；
HAL句柄/回调生命周期模型也尚未获正式接受。不得把条件628/844B或实测未触及某边界改写成全程安全结论。
本轮在此停止，不重跑相同门禁、不扩大栈或功能。后续如另获硬件授权，需至少取得：

1. 与v6完全绑定的仪器化镜像、编译参数、探针开销及散列；从Reset→HAL/外设初始化→AppTasks_Init→MSP重置/SVC→稳态分阶段记录最小MSP。
2. MSP保留区canary **及数值最小SP/最坏调用点探针**，同时记录活动异常号/嵌套深度；只扫描canary会漏掉lazy FP或未写入的预留槽。
3. 对IRQ5/6/15组合及UART错误/重启、DMA回环、TF正常/超时/abort/sync、维护POLL/事件负载记录覆盖；保持当前真实BEGIN/APPLY/SAVE门关闭，不借测量擅自启用。
4. 同步保存AIRCR/IRQ优先级与使能、PRIMASK/BASEPRI/CONTROL、CCR/CPACR/FPCCR、PSP/MSP；各任务HWM明确以4B字为单位换算。
   未覆盖的HardFault/NMI情形仍未证，不能为取数而自行注入硬件故障。有限测量只能验证已记录覆盖，不能替代所有路径证明。

## 最终回归数量与实际命令

本轮不重跑。复用v6实跑记录，单位不混加：CAL417检查、ALIGN304检查、交接故障29检查；MAG10个模式；
真实C/FatFs/SSOB17场景；相关pytest515测试+5子测试；真实ARM analyzer15个TU；
OFF159C+1ASM、ON167C+1ASM均编译链接成功；Power10文本7020检查、architecture362检查通过，栈门禁退出1。
Power10仍输出关键契约NOT PROVEN；不是全仓库全套测试或硬件通过。

仓库根曾实际执行的驱动命令如下，完整编译器/测试argv及退出码共83条见
`.work/dev013_installation_followup_20261019_v1/implementation/msp_isr_v7/final_executed_commands_index.json`。

```powershell
python -B .work/dev013_installation_followup_20261019_v1/implementation/resource_ab.py OFF6
python -B .work/dev013_installation_followup_20261019_v1/implementation/resource_ab.py ON6
python -B .work/dev013_installation_followup_20261019_v1/implementation/run_cal_align_lease.py cal_align05
python -B .work/dev013_installation_followup_20261019_v1/implementation/run_yield_faults.py yield_fault03
python -B .work/dev013_installation_followup_20261019_v1/implementation/run_mag_lease.py mag_lease02
python -B .work/dev013_installation_followup_20261019_v1/implementation/run_store_checks_v6.py store_checks05 store_host05
python -B .work/dev013_installation_followup_20261019_v1/implementation/analyze_changed.py analysis04
python -B .work/dev013_installation_followup_20261019_v1/implementation/related_checks.py r3
```

原生成project目录的门禁命令（最后一条退出1）已实跑并保留：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File Tools/check_power_of_ten.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File Tools/check_architecture.ps1
python -B Tools/check_task_stacks.py --project . --config Release --prefix "D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-"
```

本轮新增只读分析结果在`msp_isr_v7/analysis.json`、`conclusions_final.json`及`disassembly.txt`。
v6源输入/ELF散列保持不变；无硬件、推送、GUI或生产代码修改，没有权限/连接拒绝。
