# ST-Link 只读后端 — 0.1.3

GSHC 的统一 SWD 会话现在可选择受限 ST-Link 后端，复用已安装 pyOCD 0.45.1。
这是**软件实验支持**，没有 ST-Link 实物验收；不保证所有探针固件、驱动或板型可用。
顶部选择探针、型号及可选 ELF/描述后，仍须用户显式连接。界面在连接前显示实验提示。
本轮所有测试使用模拟 USB，不用 DAPLink 的通过替代 ST-Link 验证。

## 支持矩阵

| 范围 | 当前准入与证据 |
|---|---|
| ST-Link V2 / V2-1，V2J28+ | 受限软件路径；模拟 V2 PID3748、V2-1 PID374B；没有实物 |
| ST-Link V3 / V4 | 使用固定0.45.1驱动；模拟 V3 PID374E、V4 PID3757；没有实物 |
| VID0483 的 PID3748/374A/374B/374E/374F/3752/3753/3754/3755/3757 | 来自固定依赖的 USB/endpoint 元数据；其余PID仅静态准入，不是全部实测 |
| V1 PID3744、DFU PID374D、其他VID/PID | 拒绝 |
| 既有 JTAG/debug、DFU、SWIM、未知 mode | 拒绝改变状态；JTAG返回busy，不发送退出/进入命令 |
| 没有稳定 serial、重复身份、设备身份变化 | 拒绝，不挑选另一个探针；V2十二字符serial沿上游规则转换为24位hex |
| Windows接口不能被已有libusb访问/claim | 失败即停止，无协议命令；不装驱动、不detach或重配置设备 |
| DP1/DP2、单一AP0 AHB MEM-AP | 只读路径；M3/M4/M0+使用实际依赖类模拟。目标目录仍是401项元数据，不是401种实机通过 |
| 其他AP/多核/TrustZone/其他内核或特殊认证/唤醒 | 当前未准入 |
| Horco CMSIS-DAPv2 | 保留此前审查/台架范围，使用独立后端 |
| OpenOCD及其他适配器 | 扩展接口预留，默认关闭；不执行用户Tcl/config，也不退回旧初始化路径 |

## 边界与生命周期

`transport/swd_backends.py` 的固定枚举/工厂在同一 `configure/open/read/close` 接口上
选择后端，没有运行时插件/回调注册或任意 debugger command API。
`transport/_swd_stlink.py` 使用 StlinkProbe/STLinkMemoryInterface，创建 options-only
Session(None, auto_open=False, no_config=True)，不创建 Board/CortexM/目标，不执行配置脚本、
pack debug sequence或完整目标初始化。

仅选定 VID/PID/规范化 serial 的interface0可以被claim，claim失败返回busy。
claim完成以前无ST-Link协议命令。已审查bulk endpoint来自固定依赖表，不改USB配置，
不抢驱动。上游无界RX清空被替换为最多64包；每步检查截止和取消，USB读写超时500ms。
接口是同步I/O，没有后台RX线程。每次后端操作10秒预算，释放协议阶段2秒预算；
操作系统原生调用任意卡死的硬实时终止仍未证明。

发送边界检查命令、参数、读长度，并禁止data-out。只允许版本/模式/电压、受限SWD时钟、
自身SWD进入/退出、AP0 NO_CORE、IDR读取，以及当前已批准地址窗口中的memory read。
V2时钟950kHz，V3/V4请求1MHz；不是界面串口波特率。内存传输再次检查可信范围、
当前窗口、最大1024字节、APSEL0、CSW0及必要对齐。
复用既有RAM/flash/core-ID读取规则；MMIO和任意watch仍未开放。

禁止NRST、halt、resume、target memory/register write、SWV、DFU/SWIM切换、
其他AP及CortexM core初始化。AP fault仅允许上游固定SWD DP_ABORT=0x1E清sticky错误，
不允许DAPABORT/DBGRESET；它是传输寄存器写，不能描述成“从不发写命令”。
现有DHCSR sticky read-clear影响仍适用。命令静态审查不证明探针固件所有内部副作用。

未知mode在上游自动enter_idle之前拒绝。未发送自身进入命令时，失败释放只关闭主机接口，
不盲调上游link.close去退出已有debug状态。自身进入尝试后的退出与主机资源释放分别处理；
退出/释放失败明确返回ReleaseFailed并保留进程所有权，不报告成功断开或自动重连。
取消、断链和错误继续使固件matched失效，旧GUI工作线程不能更新新会话。
进程锁/USB claim只提供其记录范围，不是对所有厂商通道/进程的完整排他证明。

ELF/诊断使用相同 SwdSession：实际完整flash LMA比对通过后才读有限字段；每连接重新验证。
详见[目标与ELF](TARGET_ELF_0_1_3.md)。未找到板载精确ELF的实机正例仍是独立验收缺口。

## 测试与依赖

[执行报告](../../evidence/stlink_readonly_20261014/REPORT.md)记录命令、完整日志、基线与源哈希。
模型执行实际固定依赖类，覆盖V2/V2-1/V3/V4、M3/M4/M0+、claim拒绝零命令、
版本/mode/AP/身份拒绝、清空容量、短回复、timeout/unplug/cancel、sticky错误、
部分失败释放、禁用命令、越界窗口以及共同ELF/诊断服务。它们不是MCU或Windows驱动实测。

依赖保持pyOCD0.45.1/现有libusb；pyOCD Apache-2.0及底层依赖许可证沿原安装保留。
本轮没有下载新SDK/包、改变驱动、发真实USB/串口操作、上板或修改飞控C源码。
若实际host缺兼容驱动/权限，只报告失败并停止；另行决定安装，不自动处理。
