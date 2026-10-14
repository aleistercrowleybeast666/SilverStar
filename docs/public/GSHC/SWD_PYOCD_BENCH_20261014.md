# SWD 只读连接：pyOCD 与 Horco 台架结果，2026-10-14

指定 Horco 的真实只读连接和释放已验证。GSHC 的 Python API、CLI 和维护页
现在默认使用这个低层后端；原 OpenOCD 后端仍保留原拒绝准入策略。
这是一项 0.1.3 本地开发变更，冻结 v0.1.2、发布包和飞控固件均未修改。

## 已执行的台架范围

用户明确允许隔离安装 pyOCD 0.45.1，并授权只读测试。现场条件由用户提供：
仅连接飞控、外部 5 V 供电、SWDIO/SWCLK/GND 三线，NRST 和探针供电未连接，
物理执行器全部断开。飞控姿态不作为此读取测试的判断条件。
每次测试前均核对当前 PnP 身份及常见调试程序进程；未终止其他调试器。

| 项目 | 2026-10-14 实测结果 |
|---|---|
| 指定探针 | Horco `FAED:4870`，USB serial `132765403520`，MI00 WinUSB |
| CMSIS-DAP 协议 | v2.0.0 bulk，1 MHz SWD；设备未提供独立 firmware version |
| DP / AP0 | DPIDR `0x2BA01477`，AHB-AP IDR `0x24770011` |
| 核心识别 | CPUID `0x410FC241`，Arm Cortex-M4 |
| STM32 识别 | ID `0x413`，REV `0x1007`；只可归入 F405/F407/F415/F417 家族 |
| SRAM | `0x20000000` 起 16 字节，返回原始数据；没有符号解释 |
| DHCSR | 首次 `0x03010000`；读取后及首次释放再连接后为 `0x01010000` |
| 运行控制 | 上述样本的 C_DEBUGEN、C_HALT、S_HALT 均为 0；后两次状态为 running |
| 释放 | 两次 API 会话均返回 Ok，库所有者锁释放；最后通过 CLI 读取再释放也为 Ok |
| 命令审计 | API 成功测试 92 包、最终 CLI 44 包；均通过逐包检查，无目标地址写或复位引脚命令 |

首次样本的 `reset_observed` 来自 DHCSR 的历史 S_RESET_ST 读清位，不能据此
声称连接过程触发了复位；发送记录没有 ResetTarget/SWJ_Pins 或 DP debug-reset 请求。
DHCSR 读取会消费 S_RESET_ST/S_RETIRE_ST。运行样本和未发送控制指令是所记录范围的
证据，不是连续运行、时序无扰动、WCET、飞行安全或 READY 的证明。
没有与固件精确匹配的 ELF，始终 `symbols=unmatched`、`non_atomic_live_read`。

## 后端边界

入口为 `SwdSession`，维护页的 `SwdWorker` 在专用线程使用同一接口。
连接必须由明确的按钮/API 请求触发；启动和探针枚举不会连接目标。
AIR M0 和维护串口的 READY/命令状态继续独立决定飞控准备状态。

后端仅加载固定 pyOCD 0.45.1，明确选择相同 VID/PID/serial 的唯一 USB 设备，
只 claim MI00 的 CMSIS-DAPv2 bulk 接口，禁用 HID 回退和自动选第一个探针。
claim 失败立即拒绝，不发送 DAP 命令。`Session(None)` 只提供选项，不构造 Board，
不加载用户脚本、配置或 packs，不调用 Session.open、target/core.init 或核心断开钩子。
DebugPort 不执行 pack/user debug sequences；连接失败始终解锁，且检查 power-up 的布尔结果。
AP0 初始化及读取使用实际 pyOCD MEM-AP 实现。

只读指不写目标地址空间、不进行 CPU 控制。SWD 协议选择/线路序列、时钟、DP power-up、
sticky error 清理、AP CSW/TAR 配置和 DAP Disconnect 是必要的传输操作。
DP/AP 配置可能由库编码为 DAP_TransferBlock；不能把所有块写误称为目标内存写。
关闭直接释放保留的 USB 接口和接收线程，不调用 DP power-down、core.disconnect 或 resume。
即使 probe/link 的 open 标志尚未置位，初始化中途失败也会释放已 claim 的接口。
释放失败返回 ReleaseFailed 并保留所有权，不能展示成功断开或立即重连。

USB 单次 I/O/队列等待 500 ms，接收线程 join 2 s，操作期限 10 s，并在 I/O 及枚举中检查取消。
枚举最多 32 个匹配 VID/PID 设备，接收缓存最多排空 64 包；期限检查可能多等待一个
正在执行的底层调用。驱动调用的异常挂起不能由 Python 保证硬实时终止。
公共 API 原有上限保留：每次 1..1024 字节、会话最多 65536 字节/600 样本/600 秒、
最多 10 次请求/秒，无待执行队列。只允许已识别家族的 SRAM/CCM RAM；识别阶段只读
CPUID、DBGMCU_IDCODE、DHCSR 三个固定寄存器。外设 MMIO、flash 和任意调试命令不开放。

`SwdSession` 的所有者登记只协调同 Python 进程的 API；附加库锁保护 pyOCD 的全局
current-session 选项。底层 claim 的拒绝行为用真实库/模拟 USB 故障验证；本次真实
测试没有故意启动竞争调试会话。常见进程预检、用户单会话约束和 WinUSB claim 是
本次操作边界，不能保证任意外部 HID/bulk 客户端永远无法并发访问。

| 兼容范围 | 当前结论 |
|---|---|
| 上述 Horco + Cortex-M4 / STM32 ID 0x413 / DPv1 / AP0 | 已完成所列台架读取和释放 |
| 同家族其他实物、其他 Horco 序列号 | 代码 profile 可识别，未经本次实物测试 |
| ST-Link、J-Link、HID-only CMSIS-DAP、其他 STM32/ADIv6 | 明确拒绝；没有推断兼容 |
| GUI 实机交互 | 路由复用已验证 API；Qt 交互测试为模拟，未操作真实 GUI 连接 |

USB CDC、TF 日志文件服务/删除、固件刷写、校准、START、导航/开伞算法均不在本轮范围。

## 本机使用与隔离依赖

已安装位置为仓库 `.work/dev013_swd_pyocd01/deps`，共 26 个官方 PyPI 包，
安装文件合计 54,807,485 字节，约 52.27 MiB；wheel 大小估算约 18.75 MiB。
使用现有 `.venv` 的 Python 3.14.0，没有创建新 venv、改系统 Python/PATH/驱动或下载 SDK/packs。
可选的 [requirements-swd.txt](../../../apps/GSHC/requirements-swd.txt) 固定本次解析的完整依赖版本。
安装由用户批准后进行；运行时不会自动联网安装。

```powershell
# 仅在另行安装时使用用户指定的隔离目标目录；不要把 deps 混入系统环境。
.venv/Scripts/python.exe -m pip install --index-url https://pypi.org/simple --only-binary=:all: --no-cache-dir --target <isolated-deps> -r apps/GSHC/requirements-swd.txt
$env:SILVERSTAR_SWD_PYOCD_PATH='<isolated-deps>'
.venv/Scripts/python.exe apps/GSHC/swd_cli.py inventory
.venv/Scripts/python.exe apps/GSHC/swd_cli.py snapshot --probe 'USB\VID_FAED&PID_4870\132765403520'
.venv/Scripts/python.exe apps/GSHC/swd_cli.py read --probe 'USB\VID_FAED&PID_4870\132765403520' --address 0x20000000 --length 16
```

本机默认目录已可用，不必再次安装。缺依赖或 pyOCD 版本不符会明确拒绝。
GUI 仍由 `.venv/Scripts/python.exe apps/GSHC/main.py` 启动，在维护页显式连接，
状态显示核心运行状态、时间、非原子读取及符号未匹配，不提供暂停或恢复操作。

pyOCD 与 libusb-package 包装代码为 Apache-2.0，PyUSB 为 BSD-3-Clause；
bundled libusb 的许可另见[官方 COPYING](https://github.com/libusb/libusb/blob/v1.0.30/COPYING)。
官方 wheels 的许可证、版本及原文件保留；不把整个依赖目录打包入 Git。
审计依据为安装的 [pyOCD v0.45.1 源码](https://github.com/pyocd/pyOCD/tree/v0.45.1/pyocd)，
不是一般 attach 选项的推断。

## 回归与证据

一次完整命令执行 SWD pyOCD/session/guard/UI 及 probe inventory/UI 六个文件，
**143 passed，49.28 s，退出 0**。使用实际 CMSIS-DAP 编码器、bulk 接收线程、Probe、
DP 和 AP，底层 USB/寄存器为模拟；覆盖 claim 拒绝零 DAP 包、部分初始化失败释放、
DP 失败解锁、power ACK 失败、取消、缓存界限、显式 USB 超时、故障读取和释放重试。
GUI 交互含原有中英文及串口独立性测试。此次没有修改固件，未运行 ARM、firmware Power10
或 MCU 静态分析，也未把 Python 回归称为固件/硬件资格认证。

初次 17 项通过但带 cache 配置警告；旧默认路由/测试路径造成 2 项失败，随后一次
缩进错误在收集阶段失败；全部原日志保留。首次实机尝试因辅助检查器一律拒绝
DP/AP 块写而提前停止，释放 Ok，无完整目标识别；修正检查器并补真实编码测试后，
才完成上表成功测试。失败和通过结果没有拼接成未执行的全套通过。

正式材料见 [证据目录](../../../apps/GSHC/docs/evidence/swd_pyocd_20261014/README.md)。
成功 API 台架记录对应当时的精确 dirty-source 哈希；随后补枚举取消/超时处理，
最终 CLI 台架使用当前源代码且哈希一致。原台架结果不会归属于未运行的后来修改。
证据含命令、版本、pip 源/归档哈希、完整失败/通过日志、当前源快照、两个阶段包记录和
读取/释放结果。任务目录用途、所有者、文件哈希和保留路径有清单；没有进行清理。
历史 [首版](SWD_READ_ONLY_20261013.md)、[OpenOCD 审计](SWD_OFFLINE_AUDIT_20261013.md)、
[软件 guards](SWD_SOFTWARE_GUARDS_20261013.md) 的当时未连接事实及准入限制继续保留。
