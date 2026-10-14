# ST-Link只读后端：2026-10-14

本轮完成独立GSHC后端，基础提交43ee0e82d421be52b8f3b38935104baae96c778c。
[支持矩阵与使用边界](../../public/GSHC/STLINK_READONLY_0_1_3.md)给出具体PID、固件、mode及AP条件。
**没有ST-Link实物，所有新连接是模拟USB；没有用用户DAPLink替代验收。**
没有实际USB/串口连接、驱动改变、新依赖/SDK安装、飞控C修改、push/tag/Release。

## 实现

固定工厂保留configure/open/read/close接口：Horco CMSIS-DAP后端继续使用既有路径；
ST-Link使用已安装pyOCD0.45.1的StlinkProbe/STLinkMemoryInterface。OpenOCD枚举预留，
实际路径继续关闭，未知探针在后端构造前拒绝，不接受用户Tcl/config，不回退旧初始化路径。

协议命令在已claim的interface0发送边界检查；data-out禁止。进入/退出仅限自身SWD尝试，
AP0只以NO_CORE初始化。初始debug/DFU/SWIM/未知mode在上游自动enter_idle前拒绝，
claim失败不发任何协议命令。已有driver/libusb不兼容时失败，不安装/抢驱动。
内存读取先验证可信范围，再发布临时读窗口；发送层独立复核窗口/范围/1024字节上限、
APSEL0、CSW0和对齐。控制、target writes、NRST、SWV和其他AP命令均拒绝。
只许可读取故障中的固定DP_ABORT=0x1E清sticky位，不允许DAPABORT或DBGRESET。

上游无限RX清空改为64包上限，每次I/O检查取消和截止，USB超时500ms。
释放只管理自身已claim资源，不盲调link.close去改变原有模式。退出或释放失败返回
ReleaseFailed并保留所有权；已释放主机接口而协议退出未确认也不伪报成功。
这些程序门禁不证明探针固件全部内部副作用、所有进程排他或OS任意卡死的硬实时终止。
无硬件验证的路径保持实验声明，未知mode/版本/AP/身份/命令拒绝。

## 实际执行

完整命令、时间、环境、退出码和日志位于 [evidence.zip](evidence.zip) 的task/目录。

| 尝试 | 结果与范围 |
|---|---|
| stlink_tests01 | 35 passed，7.05秒；初始模拟后端 |
| stlink_tests02 | 40 passed，4.08秒；补充精确身份、窗口、失败释放及UI实验提示 |
| regression01 | 253 passed / 1 failed，153.91秒；英文1280顶部连接组截断 |
| header_repro01 | 同一失败独立复现：1 failed / 5 passed / 8 deselected，7.29秒 |
| header_post01 | 修复后6 passed / 8 deselected，6.59秒；原几何断言未改变 |
| regression02 | **254 passed，153.31秒**；最终十个相关GSHC测试文件 |

最终范围含ST-Link44项以及既有会话、CMSIS-DAP、OpenOCD故障隔离模型、ELF/DWARF、
探针元数据、离屏UI、串口布局和i18n。不是全GSHC或整个monorepo全集。
没有把单项/不同时刻通过拼成一个未执行的大套件通过。

实际固定依赖类在fake USB端点上覆盖V2/V2-1/V3/V4，M3/M4/M0+及DP1/DP2；
正常读取、精确区间、完整ELF加载内容及四行诊断共同服务；claim拒绝零命令；
重复/变化身份、版本/mode/AP/短回复拒绝；timeout/unplug/cancel；AP fault清理；
释放失败保留owner及重试；窗口外/MMIO/非法读、NRST、写内存、其他AP、core初始化拒绝。
V2J28边界也在模型中通过。其余PID仅元数据审查，非实物或逐PID功能通过。

RX容量前后用同一真实依赖实现证明：上游_flush_rx在66个fake包后超时，读取67次并正常返回；
新包装在64包时明确拒绝且不发协议命令，随后释放。它是主机模型，不是MCU故障恢复。

布局故障诊断观察到：同一mode=2下，连接组旧宽668，更新后的minimumSizeHint=738；
网格invalidate后即按738重新分配。原重排仅按mode早退，现缓存签名也包括三个组的
最小宽高，翻译/样式变化重新插入网格项。保留既有位置/对齐，所有原几何断言通过；
没有打开可见窗口抢用户桌面。

## 证据和剩余边界

[verification.json](verification.json)记录压缩包与成员哈希、基线、源快照及冻结tag。
task/tested_source_snapshot.json与source_snapshot/包含最终源码；source_delta.patch给出
相对基础提交的已跟踪差异。归档前再次验证源码哈希与本次测试快照一致。
依赖源码四个SHA在reviewed_dependencies.json；许可证按已有pyOCD Apache-2.0/libusb依赖保留，
未复制SDK/依赖环境。原HANDOFF是实施前审查记录，不能当当前完成状态。

未做本轮ARM构建/生成门禁：没有固件C/模板/SourceGraph更改，先前355b3df2的固件证据
保持其原范围，不冒充此后端的硬件资格。Power10关键合同审查NOT PROVEN、完整栈/WCET、
板载精确ELF匹配正例及飞行资格的既有缺口未消失。

本轮不清理旧或新.work；inventory记录路径/用途/所有者/大小/SHA，三份原用户未跟踪清单
哈希保持不变。没有并入迁仓修改（迁仓已独立43ee0e82提交），v0.1.2仍冻结。
