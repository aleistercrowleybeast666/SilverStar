# SWD 只读接口：0.1.3 开发状态

**当前交付为代码及模拟验证阶段，真实目标连接仍被阻止。**
点击维护页的“连接 SWD 目标（只读）”不会绕过准入检查。默认后端返回
`SafetyNotProven`，且在启动 OpenOCD、打开探针之前返回。没有启用不安全连接的
命令行参数或环境变量。不能将此阶段描述为“已连接实机”或“外场已可用”。

## 架构与最小范围

GUI 显式连接按钮 → 专用 `SwdWorker` → 无 Qt 的 `SwdSession` → 私有
OpenOCD MEM-AP / stdin-stdout GDB 管道。Codex 和本地脚本共用同一 Python API，
CLI 仅包装 API 和 JSON。没有 TCP、Tcl、Telnet 服务，没有后台自动连接或重连。
顶部布局保持原样，连接按钮和目标信息放在维护页。

主机探针发现、目标连接、核状态、固件符号匹配是独立状态。只有连接请求通过准入且
CPUID/DBGMCU 检查成功后，才显示目标已连接。维护串口及 AIR M0、READY 判定完全独立。
断线、超时、协议错误、目标不匹配和预算耗尽会使会话失效并释放资源，不重试接管。

| 范围 | 实现状态 | 真实硬件证据 |
|---|---|---|
| 主机 CMSIS-DAP / ST-Link / J-Link 元数据枚举 | 已有功能，选择不连接 | 历史主机枚举仅证明发现探针 |
| Horco FAED:4870、稳定 USB 序列号、CMSIS-DAP v2 bulk | 受限适配及模拟验证；准入未放行 | 本轮未打开设备 |
| Cortex-M4 + STM32 ID 0x413、AP0 | 识别及读取逻辑已实现 | 未上板；不能仅据此区分 F405/F407/F415/F417 |
| 其他 STM32、ST-Link、J-Link、HID-only CMSIS-DAP | 明确拒绝，不能推断兼容 | 无 |
| ELF / 命名诊断快照 | 下一阶段；始终 symbols=unmatched | 未解释任何旧 ELF |
| USB CDC、TF 文件下载/删除、烧录、飞控算法 | 本任务不涉及 | 无变更 |

## 后端核验与阻塞

后续[离线阻碍核对](SWD_OFFLINE_AUDIT_20261013.md)已确认本机 EXE 与供应商发布归档完全一致，
区分了纯 SWD 的复位路径与 WinUSB/HID 排他边界；下述首次实现记录仍保留历史范围。
真实 gate 未解除，台架前仍需处理明确 Busy 拒绝及双调试接口占用。
后续[软件拒绝与释放保护](SWD_SOFTWARE_GUARDS_20261013.md)修复部分 claim 失败清理，
明确进程内协调和日志屏障的实际范围。台架条件已收到，跨接口后端技术阻塞仍未闭合。

本机 `.venv` Python 3.14.0；未安装 pyOCD、pyusb、hidapi 或 pyelftools。
已有 `D:/OpenOCD-20250710-0.12.0/bin/openocd.exe`：
`Open On-Chip Debugger 0.12.0 (2025-07-10) [https://github.com/sysprogs/openocd]`，
SHA256 `3ee2ce721e7c2b0c0359b7a6a6b2a1f9a7c9a8dca3ad11db16b1085d57229cf7`。
未安装包、修改驱动或下载 SDK。

默认 `target/stm32f4x.cfg` 在 examine-end 改写 DBGMCU_CR、DBGMCU_APB1_FZ，
因此不能直接复用。拟用的独立配置不加载板级脚本、不创建 cortex_m、不分配 flash
工作区；只创建 MEM-AP，并禁用网络服务。上游 MEM-AP 的 run-control 方法只修改
OpenOCD 内部状态，所以不能把其合成运行状态当作 MCU 状态；本接口读取 DHCSR。

**仍为 NOT PROVEN：** 本机 Sysprogs 构建与精确源码的对应关系、实际初始化和关闭路径
是否保持 nRESET 引脚、对其他调试工具的排他访问。空的可准入集合是显式安全阻塞，
不能只加入一个哈希就宣布安全。需要审计精确后端版本、证明独占失败时不发 DAP 指令，
并取得条件明确的台架验证授权，才能以另一次审查变更放行。不能接管另一仓库的调试会话。

SWD “只读”指不写目标地址空间、不进行 CPU 控制；DAP 连接仍需调试端口供电请求、
DP/AP 配置和 SWJ 线序列，并非电气意义上的零影响。DHCSR 的 S_RESET_ST、S_RETIRE_ST
存在读清除语义；本接口明确记录此局限，不作无副作用或连续运行轨迹的保证。
若电源、复位线或排他访问条件未知，不应尝试实机连接。

官方参考：[OpenOCD GDB 管道](https://openocd.org/doc/html/GDB-and-OpenOCD.html)、
[MEM-AP 源码](https://github.com/openocd-org/openocd/blob/v0.12.0/src/target/mem_ap.c)、
[CMSIS-DAP 源码](https://github.com/openocd-org/openocd/blob/v0.12.0/src/jtag/drivers/cmsis_dap.c)、
[ADIv5 源码](https://github.com/openocd-org/openocd/blob/v0.12.0/src/target/arm_adi_v5.c)。
OpenOCD 是独立外部 GPL-2.0-or-later 程序；本次不复制或分发其代码/二进制。
[pyOCD 官方选项](https://pyocd.io/docs/options.html) 也说明默认连接会 halt、默认断开会
resume；仅改 attach 选项并不能免除全部生命周期审计。未把它作为新依赖。

## API 与 CLI

从仓库根目录设置 `PYTHONPATH=apps/GSHC`。API 是同步的，GUI 在专用线程调用；
其他调用者也应避免在 UI 线程执行。

```python
from threading import Event
from transport.probe_inventory import ProbeInventory_Read
from transport.swd_session import SwdSession, SwdResult

inventory = ProbeInventory_Read(Event())  # 主机元数据，不打开 USB/SWD
identity = r"USB\VID_FAED&PID_4870\132765403520"  # 调用者显式选择
probe = next(p for p in inventory.probes if p.identity == identity)
with SwdSession() as swd:
    reply = swd.Swd_Attach(probe)
    if reply.result == SwdResult.Ok:
        print(reply.snapshot)
    else:
        print(reply.result.value, reply.detail)
# context manager 总会尝试释放；释放失败会抛出 SwdError，不能视作成功断开。
```

```powershell
$env:PYTHONPATH='apps/GSHC'
.venv/Scripts/python.exe apps/GSHC/swd_cli.py inventory
.venv/Scripts/python.exe apps/GSHC/swd_cli.py snapshot --probe 'USB\VID_FAED&PID_4870\132765403520'
.venv/Scripts/python.exe apps/GSHC/swd_cli.py read --probe 'USB\VID_FAED&PID_4870\132765403520' --address 0x20000000 --length 64
```

后两条当前返回 `safety_not_proven`、退出码 2。成功退出码 0，失败/拒绝退出码 2；
JSON 另含 release 结果。CLI 每次显式连接、完成一次请求后释放，没有常驻网络进程。
探针标识必须精确且唯一；禁止自动挑选第一个设备。

`Swd_ReadMemory(address, length)` 仅允许单次 1..1024 字节，落在
`0x20000000..0x2001FFFF` 或 `0x10000000..0x1000FFFF` 内。禁止外设、Flash、别名和
跨区读取；这些 RAM 边界仅用于已识别的 0x413 配置。状态读取只访问三项固定诊断寄存器。
每个会话限 600 秒、600 次采样、65536 字节、最多 10 请求/秒；GUI 每秒采样一次。
没有待处理请求队列；并发 API 调用返回 Busy，频率超限返回 RateLimited。
每次管道请求限 5 秒，不重传；标识/状态共三次请求，最坏 15 秒加释放时间。
取消每 50ms 检查；关闭只结束自己创建的子进程，先 EOF，再有界 terminate/kill，
不发 GDB detach/resume/reset 命令。操作系统拒绝释放会明确返回 ReleaseFailed，GUI
阻止再次连接；不能保证 OS 故障时资源已释放。

所有快照包含接收时间、UTC 时间、读取耗时及 `non_atomic_live_read`；暂停核的 RAM
仍可能由 DMA/其他总线主设备变化，因此也不声称原子一致。没有可信固件内容匹配前，
不接受 ELF 路径或时间戳作为匹配依据，不解释任何命名变量。

## 验证记录

最终统一关联回归：141 tests + 7 subtests，通过；另有一条禁用 pytest 缓存插件引起的
既有配置警告。中英文离屏目标状态图像已检查。完整范围、曾发生的失败和原生 Qt 崩溃
限制见[正式证据说明](../../../apps/GSHC/docs/evidence/swd_readonly_20261013/README.md)。

执行命令、源文件 SHA256、完整日志及图像保留在 `.work/dev013_swd01`；正式证据摘要
随此实现提交。所有 target 数据为模拟数据，不是实机或外场资格证明。先前状态文案
单独回归：52 tests + 7 subtests，日志保留于 `.work/dev013_probe03`。
