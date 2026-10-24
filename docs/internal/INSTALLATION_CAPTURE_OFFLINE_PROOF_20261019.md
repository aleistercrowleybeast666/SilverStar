# 安装采集：完整快照与全链离线证明记录

2026-10-19；owner：`installation_stream_offline_proof_20261019_v1`。本批按用户要求在6.1sol继续，以[1960 B隔离模型](INSTALLATION_CAPTURE_STREAMING_EVALUATION_20261019.md)为基线补契约和有界验证。**本批发现的软件缺口已修正；目标固件接入停止。** 完整C INFO编码、采集tap、owner及全局执行路径仍有未知栈/时限，已触及用户的停止条件，不能消耗剩余672 B来替代证明。

没有改变正常IMU采样率、现有CAL/ALIGN/MAG/TF事务、GUI布局、已烧录候选或结果操作门禁；未连接硬件、烧录或推送。没有生成整套固件工程，没有复制仓库/SDK/工具链。

## 已修正的离线缺口

共享权威仍为[installation_calibration_v1.json](../../contracts/installation_calibration_v1.json)，维护0.1、AIR M0、SSLOG0.0、sample format1和已有命令不变。尚未部署的INSTALL INFO增加必需的`capture_provenance`；缺少该资格时关闭新采集，不猜测或回退旧控制命令。

1. **完整、不可变INFO。** 原实现会接受缺少采集时间资格、未绑定的额外顶层字段和重复JSON键。本批先复现3项失败，再加入字节≤8192、深度≤16、节点≤1024、字符串≤128、ASCII规范序列化和无重复键检查。源、identity、内参、坐标约定、采集策略均要求完整字段。完整SHA覆盖新增资格，B-只作为短上下文；所有可变声明都进入digest，原始规范字节另存，禁止使用活配置指针代替快照。
2. **如实时间与身份。** 每源明确`sample_time_basis`、`sample_time_provenance`、测量时间误差上界、epoch及native序列来源。无测量证据使用UNKNOWN/null；wire format1的UINT32_MAX不确定度为未知，不能获得资格。`DECLARED_ENDPOINT`和`CHIP_UNIQUE`分开，缺少芯片UID时保留null/UNKNOWN，不能用型号、配置或MCU UID冒充传感器唯一身份。合成时间只允许显式offline授权。通过声明检查不等于硬件真实性已验证。
3. **原始样本资格。** GSHC采集与重放都核对样本没有小报INFO冻结的时间误差界，再做既有CRC、角色、序号、skew及窗口检查。异常原始part先保留，整FACE不发布成功。没有修改拟合算法或HOLDOUT使用规则。
4. **主机生命周期。** 已修正的安装后端在远端cleanup未知时阻止新会话，即使本地transport已经释放；本地释放失败则继续持有owner。Request超时或期间取消后才返回的回复会被拒绝。provider仍须协作遵守deadline；返回后检查不提供强制中断能力。

修改范围为安装专用Python后端/重放/契约/验证脚本、新的资格模块与测试、隔离模型和文档。没有修改owning firmware payload/template。

## 固定选样与整会话互斥的证明范围

5 Hz只作为待验证输出档位。参考模型使用200 Hz合成native序列、固定stride40及冻结phase；1200个native帧固定选出30个样本。将数据值替换为极值、NaN或不可读取对象，选择的序号完全相同。模型逐个检查native帧，故意在未选中的区间漏一帧也会失败；32位source序号回绕不重置独立选样phase。静态/质量验证只能拒绝完整固定窗口，不得挑掉不利值并补入其他样本。

首个native帧缺失从窗口开始即有时限；native健康超时与选择后输出周期分开检查。这些测试没有更改硬件输出速率，也没有证明真实200 Hz/5 Hz噪声、稳定时间、传感器内部延迟或重复性。当前CAPS/INFO中的输出频率是声明，不是资格结果。

整会话模型从申请到清理覆盖INSTALL、LOGFILE、MAG_WRITE、CAL、ALIGN、START、CONFIG、CONSOLE、IDLE_STATUS、DIAGNOSTIC。穷举10×10种顺序入口竞争、6种producer/consumer/reader清理确认次序；活动consumer持有的槽不能提前回收，取消后不再发布，未知远端/本地释放不准新owner，旧generation不能获得新lease。安全恢复可立即撤销INSTALL发布。

**这些是有限顺序参考模型。** 当前GSHC `MaintenanceOwner`仍按job管理`_claimed`，没有注册INSTALL会话adapter或有界sample dispatcher；固件Serial/AIR/内部START/CAL/ALIGN/MAG/LOGFILE/config入口没有共用INSTALL gate。没有证明RTOS临界区、ISR快照一致性或真正单reader覆盖所有入口。保留现有业务owner与缓冲，不能通过抢占或改现有事务补齐。

## JY901B当前事实与500 ms目标

实际[JY901B MAG adapter](../../apps/SCG/plugins/builtin/silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B/Adapter/Src/jy901b_magnetometer_adapter.c)的0x54不含测量时间；sample/receive都取本地解析的`MagTimestampUs`。真实字段应写`TARGET_RECEIVE_DECODE_PROXY`、测量时间误差上界null、epoch/native gap资格UNKNOWN，不能写传感器同步时间或uncertainty=0。本批测试证明，即使给接收代理伪造0误差，也无法获得安装采集资格。候选epoch qualification仍为0，真实INSTALL继续禁用。

500 ms目标明确包含从GSHC发起取消，到目标确认清理及主机reader安静的全链；target逻辑清理、ACK出队/到达是分段，不能缩小口径使其通过。当前115200下4095 B普通队列+1023 B priority+192 B ACK的8N1线时向上取整为460938 μs，尚未加执行延迟。源停止、consumer握手、RX解析、ISR/调度、持续其他writer、HAL/DMA异常和主机reader均没有已证明的上界。优先队列还能在128 B DMA块之间插入长样本行，尚无完整帧仲裁证明。

主机原有active Request deadline可达5 s，cleanup deadline为1 s/最多8次exchange；即使provider遵守这些deadline，也不能据此认定500 ms全链目标成立。已修正的late-return检查保证不发布迟到成功，但不缩短阻塞。取消计算模型要求每项显式给出界，任何unknown保留NOT PROVEN；含5 s阻塞的合成完整路径反例为5.460938 s。**500 ms仍NOT PROVEN。**

## ARM、资源、栈与全局最坏路径

[最新v5 ARM结果](../../.work/dev013_installation_stream_20261019_v5/results.json)使用ARM GNU14.3.1进行严格warnings-as-errors编译、真实`-fanalyzer`编译、独立ARM链接；host GCC16.1.0完成参数边界和逐字节438 B golden检查，7类有界分片/队列检查通过。原6208 B同区域链接反例按预期exit1，完整错误保留。v4是先行同C源码结果，未删改或拼接成完整固件通过。

| 项目 | 已证范围 | 未证范围 |
|---|---|---|
| 内存 | C/linker字节与v3完全相同；实测1960 B CCM、0 B新增主SRAM，剩672 B；feature cap2048 B不变 | 完整INFO字段映射/编码、源epoch及owner实现尚未装入；不能承诺最终仍放得下 |
| INFO | Python规范字节、不可变完整digest、48 B分片；当前合成快照3432 B/72页；0/0.0/-0.0及指数和转义向量覆盖 | C浮点规范化、完整metadata到序列化字段映射、SHA执行路径及其资源尚无实现 |
| 孤立栈 | `.su`和实际反汇编4函数：16/20/32/24 B；entry链76 B，encoder子树52 B | 真实caller/context、INFO/SHA、tap、UART、RTOS及IRQ嵌套不在该链 |
| 原候选栈 | 只读已有绑定同ELF的报告：Serial4688+256=4944/6144，Device1888+256=2144/2560 | 旧报告不是新采集路径证明；原报告本身MSP/main/ISR/hardware margin即NOT PROVEN |
| WCET/取消 | 固定循环/有限调度模型、确定字节数和理论线时；unknown项不能变成0 | 全局STM32执行上界、调度服务间隔、HAL异常与实际HWM无证明 |

需闭合的真实路径分别为：`GSHC Cancel → active Request → target RX → owner → producer/consumer stop → TX/HAL/ISR → host reader`；`SerialTask → SystemConsole_Process/dispatch → INFO/stream → UART/DMA`；`DeviceTask → native producer → selector/pair → Serial consumer`。没有把孤立76 B简单加到旧Serial最大链来宣称新最大链，也没有把Host运行时间换算成STM32 WCET。

本批没有新生成目标固件、目标`power10-check`、完整固件Host/ARM-link/stack或上板时序/HWM结果。没有修改固件C来源，隔离ELF也缺启动代码，绝不可烧录。下一目标接入仍须从owning payload重新生成一个小验证工程，并原样跑这些门禁；当前按用户的未知栈/资源规则停止，没有用新缓冲、扩栈、预算变更或业务事务改动填补。

## 可复现证据与剩余边界

- [修正前3项失败](../../.work/dev013_installation_stream_proof_20261019_v1/pre_fix.stdout)和[原始输入](../../.work/dev013_installation_stream_proof_20261019_v1/before_source.json)：exit1；修正后最初22项、后续164项局部检查均保留。
- [最终完整离线回归](../../.work/dev013_installation_calibration_20261018/streamproof03_20261019_results.json)：**316 passed，exit0**，完整日志、命令、依赖版本、源码字节/哈希和GUI指纹均保存。覆盖安装worker/协议/原始记录/拟合/重放、现有MAG/maintenance/owner回归、release布局、旧安装实验与新有限模型。追加CRC正确且paired record一致的低报时间误差重放反例，确认不能升格为合格记录。此前313项和315项完整结果也保留，不拼接不同执行结果。
- [边界审计](../../.work/dev013_installation_stream_proof_20261019_v1/boundary_audit.json)：真实相关源文件快照、ARM调用边、候选原有任务链、取消unknown项及停止理由。
- [保留清单](../../.work/dev013_installation_stream_proof_20261019_v1/retained_inventory.json)：本批新增/修改文件、全部版本证据的用途/owner/路径/哈希。HEAD及精确dirty源码快照记录在各验证结果中。GUI指纹未变，已烧录候选ELF/BIN/map/stack报告及两个ssdiag共6项hash未变。

共享契约hash已经因完整资格字段而变化。旧原始文件、旧契约快照与软件结果保留原字节；现有replay按精确记录契约hash拒绝跨契约重放，不能将历史文件重签成新资格证据。

具体剩余缺口是：JY真实测量时间/延迟及native epoch、选样相位起点冻结和gap资格；完整C INFO及冻结字段表达；覆盖所有真实入口的双端会话owner和typed dispatcher；取消强制协作/清理与帧完整性；完整新增调用图、任务/MSP/ISR栈和STM32 WCET。**目标接入、critical-contract review和500 ms全链接受均NOT PROVEN。** APPLY/SAVE/UPLOAD保持关闭。

期间收到环境短暂断连通知；[03:13 UTC完整性复核](../../.work/dev013_installation_stream_proof_20261019_v1/reconnection_integrity.json)确认本地执行可用、没有半写文件、最终可执行源与316项回归快照一致，v4/v5完整清单及候选6项hash相同。没有把中断或缺失结束记录的测试计为通过。当前无权限拒绝、连接阻断或执行结果不明；未进行清理。
