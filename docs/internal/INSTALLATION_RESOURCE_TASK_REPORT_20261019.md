# 安装标定资源与任务交接（2026-10-19）

Owner：`installation_followup_20261019_v1`。用户批准复用预留区后的实现草案；**尚未验收**。
分支 `feature/usb-transport-0.1.3-20261013`，HEAD `7896c1d09a7f9138c41cdac35beef38347d94b78`，
以证据目录的脏工作区输入散列为准。未接触硬件、稳定 main、暂停的 M9N 任务；未推送或清理历史文件。

## F407VET6 同配置 OFF/ON 实际链接结果

同一参考模型、JY 磁数据配置、维护协议及 Release 编译参数；唯一选择差异为 `silverstar.installation.capture`。
执行原样生成的 Makefile，保留两套构建输出。数字只覆盖当前可链接功能，不能外推到未来真实上传、应用或拟合实现。

| 项目（字节） | OFF | ON | 增量 |
|---|---:|---:|---:|
| Flash 加载内容合计 | 349888 | 391280 | **41392** |
| `.text` | 317092 | 343156 | 26064 |
| `.rodata` | 31248 | 46576 | 15328 |
| `.data`（同时占 Flash 加载空间） | 1140 | 1140 | 0 |
| 主 SRAM `.data + .dma_bss + .bss + MSP/heap预留` | 102292 | 102292 | **0** |
| CCM 静态内容（包含任务栈） | 62904 | 64896 | **1992** |
| 所有任务配置栈合计，均位于 CCM | 27648 | 27648 | **0** |

主 SRAM 分项：`.data=1140`、`.dma_bss=10952`、`.bss=89176`、MSP预留1024；heap预留0。
物理主 SRAM 为131072，物理余28780；项目静态上限为102400，**项目预算只余108**。
物理 CCM 为65536，ON 后余640。CCM任务栈以外的静态内容由35256增至37248。
Flash为512 KiB，本次ON余133008。不得将192 KiB总RAM或主SRAM物理余量当成项目预算放宽。

最初独立状态方案148 B超出主SRAM余量。本次最终把已有 Control 预留80 B、Frozen尾部预留80 B
用于协调状态，共160 B，包含延迟释放、依赖失效及CRC字段；**新增静态分配仍为0 B**。
这与整个可链接模块新增1992 B CCM、41392 B Flash是两个不同口径。
`s_capture=1960 B`、`s_wire=28 B`，独立分组对齐导致整张ELF的CCM差额为1992 B。
`s_mailbox=304 B`，新增lease标志占原有填充。没有新任务、动态分配或独立大缓冲。

## 在哪个任务执行

| 执行路径 | 已分配栈 | 作用 |
|---|---:|---|
| `AppTask_Serial → SystemConsole` | 6144 B | 维护命令、INFO及有界事件输出；不做FatFs I/O |
| `AppTask_Device → ImuSampleBus_Process → SystemInertial_NextGet` | 2560 B | IMU采样tap |
| `AppTask_Ins → SystemMagnetometer_LatestSampleGet` | 3072 B | MAG最新样本tap；Device启动检查也调用此入口 |
| `AppTask_Logger → SystemInstallationStore_Service` | 3072 B | 64 B分块TF工作、校验、发布及候选head提交 |
| `AppTask_Flight` | 4096 B | 既有CAL/ALIGN、排队START处理 |

上述任务栈本身均在CCM。`s_capture`/`s_wire`是静态CCM数据，不属于某个任务栈。
PC拟合在上位机进程，未放入MCU任务。MAG入口是按调用取得最新值，尚无“每个原生帧”硬件证明。

当前失败门禁在拒绝输入指纹前形成的调用图诊断如下，**不是已接受的栈证明或实测高水位**。
估算另外计256 B上下文保存；剩余仍受回调、库、动态帧、main/MSP及ISR嵌套完整审查约束。

| 任务 | 最长已知静态链 | 加上下文后的诊断余量 |
|---|---:|---:|
| Device | 1888 B | 416 B |
| INS | 1984 B | 832 B |
| Estimator | 3100 B | 740 B |
| Flight | 3392 B | 448 B |
| Logger | 1728 B | 1088 B |
| Serial | 4216 B | 1672 B |
| Telemetry | 1896 B | 1944 B |
| Idle | 0 B | 256 B |

Logger最高诊断链经过候选发布的`f_rename → dir_register → disk_write → SD_write → RTOS等待`；
Serial最高诊断链经过原有CAL FACE/ALIGN失效及INS诊断快照，并非PC拟合。
`main`已知诊断564 B；HAL DMA/UART间接回调、Reset/libc及ISR嵌套仍NOT PROVEN。
没有进行硬件栈高水位测量，不能把诊断余量或CCM空余当成安全栈证明。

## 已落地且保持关闭的实现

安装插件私有预留区承载六类操作token和TF协调状态；结束事件只发布匹配token，后续入口排空释放。
MAG Apply/Load/Save/Clear实际入口已接入，异步保存只有匹配request完成才释放；迟到完成不能释放新操作。
CAL/ALIGN、直接/排队START、LOGFILE会话和配置入口已接入，但下述回归阻止完成验收。

TF复用Logger及已有FIL/双槽对象scratch：SHA全长生成8.3安全路径，只追加staging，完整SHA/CRC验证后
发布不可覆盖blob，再次读回验证，最后以SSOB双槽kind5提交候选head（68 B）。原MAG槽不变，不删除旧数据。
关闭或head提交结果不确定时保持lease并报`CLEANUP_UNCONFIRMED_REBOOT_REQUIRED`。
候选仍为SSIC v1 kind2，不另造维护协议或SSLOG版本，不把控制命令塞进SSLOG。
此MCU字节通道不验证JSON内拟合质量，也不应用标定。真实snapshot为offline=0，typed Begin拒绝；
真实BEGIN/APPLY/SAVE及GUI均未开放。链接器目前也移除了没有真实调用者的typed Begin/Write/Verify。

## 验证与阻碍

证据根：`.work/dev013_installation_followup_20261019_v1/implementation/`，禁止据此执行固件。

- `ab_OFF4`/`ab_ON4`：原样Make、实际ARM编译和链接成功；`resource_comparison_v4.json`记录节区、任务栈、ELF散列及工具版本。
- `analysis02`：15个受影响目标TU用严格警告、真实`-O0 -fanalyzer -c`通过。
  `analysis01`失败完整保留；修复对象路径空prefix/length的显式错误路径，未抑制诊断。
- `r2`：相关完整回归515项、5子测试通过，152.48秒；`r1`的长路径失败完整保留，未拼接为一次全套通过。
- `mag_lease01`：真实MAG入口、完整保存生命周期、错误/迟到完成及8个原有模式通过；保留原始负例及修复后证据。
- `store_checks04`：17个真实C/FatFs/SSOB/diskio用例通过：正常、同blob续传、坏头/CRC、代次冲突、撕裂head、
  真机门关闭、取消、超时、依赖变化、迟到完成、关闭/读写/sync故障、丢失完成及真实LOGFILE互斥。
  卡、时间及RTOS为Host模型；不等于真实重启、电源故障或硬件验证。
- `power10_04`：7010项文本检查通过，仍明确`Critical-contract review NOT PROVEN`；未扩大任何例外。
- `architecture_03`：362项通过。先前错误cwd及紧凑投影缺许可证的失败保留；已补入上游原始许可证。
- **FAIL：`cal_align03`实际ALIGN回归。** CAL415项通过；ALIGN302项出现12项失败，其中负例的Start优先级预期
  尚需厘清，原有CAL Reset/Start与ALIGN长期lease冲突的失败不可忽略。未修改原有业务期望或测试以消除失败。
- **NOT PROVEN：`stack_gate_02`退出1。** 首个拒绝输入为`system_mag_calibration.h`；
  `callback_inputs_review.json/.diff`列出41个当前编译输入及参考差异，未自动接受散列或修改栈检查器。
  `stack_review_preview_v4.json`只读提取失败前诊断，不能替代门禁成功。

最小后续批次：先修复并证明CAL Reset/ALIGN长会话的兼容取消/释放顺序，加入真实生命周期入口的冲突和迟到完成回归；
再逐项完成41个输入及实际linked callback、main/MSP/ISR审查，保持未知项NOT PROVEN。
通过这些门禁前不得启用真实安装标定或宣称完整安全验收。当前无未决权限/连接拒绝；硬件操作未请求、未执行。
