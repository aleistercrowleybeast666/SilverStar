# 安装标定互斥修复、执行路径与静态栈结论（2026-10-19，v6）

Owner：`installation_followup_20261019_v1`。本页接续 v4 交接报告，历史失败和数字不覆盖。
**CAL/ALIGN 兼容冲突已修复；配置栈完全不变；全固件栈及关键契约仍未验收。**
功能默认 OFF，真实 BEGIN/APPLY/SAVE 关闭；未操作硬件、修改 GUI、推送或改动稳定 main。
暂停的 M9N INT32_MIN 任务未处理。本轮未修改栈检查器或其白名单、Power10 阈值和例外。

## 修复的边界与验证

原问题是 ALIGN 长会话持有 owner5 后，CAL Reset 无法先取得 owner4，因而到不了原有 ALIGN 失效流程。
现在 CAL Start/Reset 保持自己的动作锁，按以下顺序处理：

1. CAL 申请失败时，仅允许 ALIGN 在自己的动作锁内确认仍持有匹配 owner5/token 后交接。
   其他资源所有者、活跃 ALIGN 动作及并发 START 均不被绕过。
2. ALIGN 保持租约直到停止采集、撤销 READY、完成 backend reset；backend reset 不在 IRQ 临界区内执行。
   失败发布 FAILED，CAL 参数不更新。动作结束后才发布 owner5 的匹配 token 释放事件。
3. CAL 再申请 owner4。若竞争者先获得资源，返回 Busy，不发布 CAL 成功或参数。
   成功交接后记录本次已完成失效，避免再调用一次 backend reset。
4. Stop/Face 不使用交接特例。迟到的旧 ALIGN 结束不能释放新 owner 的 token。

修改位于 owning Core CAL/ALIGN 和安装插件租约接口；没有增加静态状态。
`cal_align05`：CAL417、ALIGN304项零失败，原有业务断言保持不变。
`yield_fault03`：29项零失败，覆盖取消期间的捕获争用、CAL重入、ALIGN Process争用、reset失败不留READY、
CAL参数不部分发布、其他owner保护、旧结束事件及每次交接恰好一次backend reset。
Host仅模拟原有传感器/lifecycle/调度端口，不能据此声称真实epoch或硬件验证。

## F407VET6 当前整张 ELF 的 OFF/ON 对照

同一模型、传感器、维护/日志协议、Release配置及工具链；只改变安装采集选项。
运行原样生成的 Makefile，实际 ARM 编译/链接；OFF/ON各自输入、命令、二进制及散列分别保留。

| 字节 | OFF | ON | 净增量 |
|---|---:|---:|---:|
| Flash加载内容合计 | 349904 | 391584 | **41680** |
| `.text` | 317108 | 343460 | 26352 |
| `.rodata` | 31248 | 46576 | 15328 |
| `.data`，同时有Flash加载副本 | 1140 | 1140 | 0 |
| 主SRAM静态内容及MSP预留 | 102292 | 102292 | **0** |
| CCM静态内容，含任务栈 | 62904 | 64896 | **1992** |
| 任务栈配置合计 | 27648 | 27648 | **0** |

**41680 B是当前整个已链接功能的净Flash载荷差额**，包括采集模块、受选项影响的Core调用点、INFO数字序列化/Ryu
常量表、CRC/SHA、候选TF服务及新增链接依赖；不是仅数插件C文件或排除库的数字。
共享库中OFF已占用的部分不会重复计增量。PC拟合在PC上，不计MCU Flash/任务栈。
OFF也包含两边共有的无条件公共存储/接口改动；开关差额不计这些共有字节。因此41680B不是相对开发前冻结候选的全部仓库改动成本。
未接入真实调用者的typed store Begin/Write/Verify被GC移除；未来上传、应用和保存入口的完整成本不能由此外推。

主SRAM：`.data=1140`、`.dma_bss=10952`、`.bss=89176`、MSP预留1024；heap预留0。
项目上限102400，余108；物理主SRAM131072，余28780。二者不可混同或自动放宽预算。
CCM为65536，ON余640，其中任务栈27648、其他静态内容37248；Flash为512KiB，ON余132704。
初步独立方案148B未分配；最终使用原有两块80B预留区（共160B），新增静态分配仍为0。
`s_capture=1960`、`s_wire=28`，整张ELF的对齐后CCM差额1992。没有新任务或动态分配。

## 每个任务实际承担的调用路径

以下针对本次**日志已启用**的F407配置；所有八个任务的栈地址、字节数及总额在OFF/ON间完全一致，均位于CCM。
采集缓冲也是CCM静态数据，但不属于某个任务栈。

| 任务与配置栈 | 执行内容 |
|---|---|
| `AppTask_Device`，2560B | 设备驱动处理与IMU原始入口：`ImuSampleBus_Process → SystemInertial_NextGet → SystemInstallationCapture_ImuObserve → InstallationCapture_SourcePush`。启动通信检查也会调用MAG latest入口。 |
| `AppTask_Ins`，3072B | 原有INS传播；MAG入口：`SystemMagnetometer_LatestSampleGet → SystemInstallationCapture_MagObserve → SourcePush`。它是latest读取，不证明每个原生MAG帧均被消费。 |
| `AppTask_Estimator`，4096B | 原有融合、估计快照；不运行安装拟合或TF传输。 |
| `AppTask_Flight`，4096B | 原有`SystemCalibration_Process`、`SystemAlignment_Process`及排队START；PC安装拟合不在此任务。 |
| `AppTask_Serial`，6144B | 维护串口命令：`SystemConsole_Process/ExecuteLine → SystemInstallationCapture_ExecuteLine`，包括INFO、FACE、CANCEL、POLL及原有CAL控制。后台`SystemInstallationCapture_Process`执行超时状态机、`EventPeek → SystemConsoleDevice_Write → EventCommit`。 |
| `AppTask_Logger`，3072B | 既有MAG加载/保存、LOGFILE服务；`SystemInstallationStore_Service → WorkTake → Storage_Execute → WorkComplete`，每次一个有界工作项，数据块64B；实际FatFs读写、sync、rename和双槽head提交均在此任务。 |
| `AppTask_Telemetry`，4096B | 原有AIR状态/命令分发，也可能同步进入CAL/ALIGN/START控制；不承担安装bulk数据或PC拟合。 |
| `prvIdleTask`，512B | 原有FreeRTOS idle路径。 |

`SourcePush`在调用它的生产者任务内检查序号/时间/stride并写有界CCM pending/两槽配对队列；不写TF。
当前真实源资格未证明、BEGIN关闭；上表说明已链接入口归属，不代表当前真机正在采集。

外部合法POLL在Serial解析SID/RID并调用`RequestTouch → Poll`，只检查队列/阶段/计数/超时，不读取物理传感器、
求解或执行FatFs。Serial后台周期`Poll`不刷新外部命令保活时间，断线不会靠后台tick续命。
事件输出在Serial消费生产者队列，成功提交后才前移；GUI/PC worker保留原有维护传输所有权。
LOGFILE请求也由Serial提交、Logger执行，互斥覆盖会话和关闭确认。当前TF候选保存没有开放新的真实串口入口。
另一个“无Logger/关闭日志”的既有构建分支在Serial服务MAG持久化；本次资源数字和Logger归属不外推到该分支。

## 已执行的真实栈检查与能交付的静态结论

`stack_gate_04`原样执行拥有者检查器，**退出1**：首个拒绝的是更新后的`System/Alignment/Inc/system_alignment.h`身份。
没有添加散列来使其变绿。`callback_inputs_review_v6.json/.diff`保留42个变化输入的逐文件完整差异及精确编译依赖。

另在原检查器拒绝时只读保留其已解析的**本次真实ELF**、`.su`和反汇编调用图；未替换或跳过门禁操作。
当前任务可达图的间接调用已由既有实际表/指令校核解析：Device的7个startup操作槽以及Logger的5个SD diskio入口；
其他任务可达图没有未解析的间接调用。逐个遍历所有任务可达边，未见递归环或未定/动态栈帧。
无`.su`的已链接库/编译器clone按反汇编常量SP增量之和保守计帧，完整清单保留在JSON。

| 任务 | 配置 | 保守调用链 | 上下文预留 | 诊断余量 |
|---|---:|---:|---:|---:|
| Device | 2560 | 1888 | 256 | 416 |
| INS | 3072 | 1984 | 256 | 832 |
| Estimator | 4096 | 3100 | 256 | 740 |
| Flight | 4096 | 3392 | 256 | 448 |
| Logger | 3072 | 1728 | 256 | 1088 |
| Serial | 6144 | 4248 | 256 | 1640 |
| Telemetry | 4096 | 1928 | 256 | 1912 |
| Idle | 512 | 0 | 256 | 256 |

这是**给定已解析回调目标及当前编译输入的保守静态结果**，不是原项目门禁PASS或实测高水位。
函数级图不传播常量实参：例如FACE的`allow_alignment_yield=0`本不进入Yield，但共享helper的该分支仍计入最深链；
因此串口/AIR链是保守组合，不是一条实际执行时间轨迹。尾调用同样保守叠加。
Logger的最深组合经过`f_rename → disk_write → SD_write → RTOS等待`。
Serial/AIR的最深组合经过CAL admission、ALIGN软件reset和INS诊断快照；不是POLL或PC拟合。

### 42个输入的栈相关审查边界

- 新安装API、状态、租约、stream/SHA/INFO代码及新增ALIGN Yield均为直接调用；新增头文件数据结构没有回调成员。
  新Yield保持原ALIGN动作锁和生命周期预留；按上述Host反例验证释放顺序。
- Core采样转发/console/CAL/ALIGN/LOGFILE/配置与Logger改变了直接调用可达性；本次ELF和静态图包含这些调用，
  没有借用旧二进制或把旧栈报告归给新实现。
- TF使用既有FatFs/SD驱动表；新候选对象类型/路径/head不添加驱动回调或FIL。MAG snapshot/Owned加载只增数据/直接函数，
  原有设备/startup/SD回调ABI及只读目标表未扩展。
- Ryu是已记录的固定上游版本和本地fail-stop桥；表是只读数据，未加入malloc、libc assert或运行时回调注册。
  生成文件改变身份/日志定义/安装常量；没有新增硬件回调表。

上述语义核查及实际目标表检查提供当前静态结论；**不等于42个版本已被原门禁登记接受**，也不代替其最终评审。
关键契约语义、最小作用域、所有错误处理及Power10其他规则仍不能从一个调用图自动证明。

### 尚不能给出的完整证明

- HAL DMA/UART ISR的运行期句柄回调目标集合、各生命周期赋值及可抢占组合尚未全部绑定；Reset/libc init间接调用也未建模。
  `main`当前已知静态链564B，不能据此完成Reset到调度器及MSP全程证明。
- 尚需把上述回调、NVIC优先级/启用状态、硬件异常/FP帧及MSP活跃区间合并，覆盖全部可达嵌套。
  这些源级/链接级内容可继续静态审查；当前模型不能给出其已证上界，故保持NOT PROVEN。
- 真实高水位、STM32运行负载覆盖及WCET不是静态`.su`或剩余RAM能提供的信息；本轮没有硬件测量授权或结果。

## 证据索引

证据根：`.work/dev013_installation_followup_20261019_v1/implementation/`。
`project_payloads_v6.json`为当前输入散列；`ab_OFF6/ab_ON6`是实际Make、ARM编译/链接；
`resource_comparison_v6.json`记录节区、任务栈及工具版本；`stack_review_preview_v6.json`记录全部链、库帧、间接点与未知根。
`cal_align05`、`yield_fault03`、`analysis04`、`mag_lease02`、`store_checks05`、`r3`各自保存命令、退出码与完整日志。
此前失败、源码差异和旧版本构建均保留，没有拼接为一次未运行的全套成功，也没有清理旧工作目录。
