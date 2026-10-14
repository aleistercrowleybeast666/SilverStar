# 0.1.3 只读目标与 ELF 诊断

本轮完成 SCG 生成/构建描述、GSHC 统一导入和有限 SWD 诊断框架。
软件回归可验收；**尚无板载固件与已选 ELF 全量匹配的实机正例**。
401 项是官方元数据覆盖，不是 401 种芯片上板通过。当前设备后端仍只准入
已审查的 Horco FAED:4870 CMSIS-DAPv2，ST-Link/OpenOCD 扩展见下文。

## 验收入口

1. SCG 在用户新选定的项目中正常生成，会在项目根输出 `<项目名>.ssdiag`。
   这是未绑定的描述。成功的 SCG Flight 构建（包含 GUI `Target_Run`）将实际
   ELF 的哈希、加载段及可解析字段绑定到 **ELF 同目录、同主文件名的 `.ssdiag`**。
   构建日志 `DIAGNOSTICS|bound|...` 给出路径；`unavailable/unbound` 不表示诊断可用。
   固件编译结果和描述绑定结果分别报告。普通 Make/EIDE 构建不会自动执行 Python。
2. GSHC 顶部选择探针，进入“运行诊断 / 日志”，点击唯一的“导入固件诊断 / ELF”。
   选择已绑定 `.ssdiag` 会查找安全的同目录 ELF；也可一次选择描述和 ELF。
   直接导入 ELF 时，先在型号框中选择准确订货型号。导入在工作线程执行，不连接目标。
   失败的替换会清除旧固件；解析不全的行保持 unavailable，不猜地址或类型。
3. 用户主动“连接 SWD 目标（只读）”后才核对内核及完整 flash 加载内容。
   未匹配时禁用诊断 RAM 读取。断开/取消/关闭会取消工作并等待线程退出；释放失败明确显示并禁止重连，旧工作线程
   的回调不更新新会话。每次连接重新核对，不沿用上次 matched。
4. 导入成功可看到型号、ELF 哈希前缀和可解析诊断数。匹配后仅提供下面四组字段；
   长内容可横向滚动/悬停查看。接收年龄不等于 MCU 样本年龄，OBSERVED 不代表 READY。
   运行中的旧 GSHC 进程需要用户正常退出后再启动，才能加载本轮标签和导入界面变更。

本轮验证工程（**未烧录**）保留于仓库的
`.work/dev013_target_elf01/project02/`，配对文件位于
`build/FCCG/SilverStar_F407/Release/SilverStar_0_1_3.{elf,ssdiag}`。
不要用此工程覆盖用户 FINAL。两个串口的“波特率”标签均可见；它不是 SWD 时钟。

离线 CLI（从仓库根运行，无探针访问）：

```powershell
$env:PYTHONPATH = "$PWD/apps/GSHC"
.venv/Scripts/python.exe apps/GSHC/swd_cli.py targets
.venv/Scripts/python.exe apps/GSHC/swd_cli.py inspect --descriptor '.work/dev013_target_elf01/project02/build/FCCG/SilverStar_F407/Release/SilverStar_0_1_3.ssdiag'
```

手动构建后绑定（输入必须是本次实际成功链接的 ELF）：

```powershell
$env:PYTHONPATH = "$PWD/apps/SCG/src"
.venv/Scripts/python.exe -m silverstar_diagnostics.bind --schema 'PROJECT/PROJECT.ssdiag' --elf 'PROJECT/build/PATH/FIRMWARE.elf'
```

CLI 的 `diagnostics --probe <完整身份> --descriptor <文件>` 会实际打开选定探针，
不是离线验收步骤。API 顺序相同：`Firmware_Import` → `SwdSession(firmware=...)` →
`Swd_Attach` → `Swd_VerifyFirmware` → `Swd_Diagnostics` → `finally: Swd_Detach`。
没有自动串口连接、START、执行器、halt/reset/resume/flash 或固件文件服务操作。

## 分层与兼容矩阵

`contracts/swd_diagnostics_v1.json` 是唯一稳定诊断集合；共享解析代码位于
`apps/SCG/src/silverstar_diagnostics`，SCG 和 GSHC 使用同一实现。
目标目录独立于用户描述，取官方 PDSC 的处理器、片内存储和 AP 信息；
不执行 pack 调试序列、flash algorithm、target hook、用户脚本或外部 debug link。

| 范围 | 当前证据与限制 |
|---|---|
| STM32F1：95 项 | Keil STM32F1xx_DFP 2.2.0 元数据；F103C8 Cortex-M3 编译/模拟 DP1；未上板 |
| STM32F4：211 项 | Keil STM32F4xx_DFP 3.1.1 元数据；F407 Cortex-M4 新工程真实 ARM 链接；只读实机见证据 |
| STM32C0：95 项 | Keil STM32C0xx_DFP 2.4.0 元数据；C071 Cortex-M0+ 编译/模拟 DP2；未上板 |
| Horco CMSIS-DAPv2 | 当前实现，使用显式 USB serial、MI00 claim；用户另已反馈 DAPLink 连接验收通过 |
| ST-Link / 其他 CMSIS-DAP / OpenOCD | 扩展设计，当前运行时仍拒绝未审查后端；没有实物验证 |
| 其他内核/系列、多核、TrustZone、其他 AP、特殊复位/认证/唤醒 | 当前未准入，需要独立能力审查；不能仅增加名称即可使用 |

当前能力仅单核 little-endian Cortex-M0/M0+/M3/M4、ADIv5 DP1/DP2 AP0。
CPUID 只核对内核；型号框的型号来自用户选择，不能冒充精确硅片识别。
无显式型号时保留既有 F405/407/415/417 的 family ID 路径。
只允许可信目录内的片内 flash/RAM/CCM；排除 MMIO、OTP、系统 ROM、别名和外部存储。
目录生成工具 `tools/diagnostics/update_target_catalog.py` 是维护者离线工具；
新增来源应固定版本/哈希、审查内存和 AP，再再生目录及增加代表性测试。
不接收运行时用户 PDSC。描述只能缩小有限诊断集合，不能增加读写权限。

## 加载地址与匹配证据

比较 ELF32 ARM `ET_EXEC` 的非空 `PT_LOAD`：地址用 **`p_paddr`（LMA）**，
长度用 `p_filesz`，字节来自文件的 `p_offset`。`.data` 的运行地址 `p_vaddr`
在 RAM，但初始内容放在 flash，必须比较 flash LMA。`.bss`/其他零文件长度段
没有烧录字节，不拿实时 RAM 和零值比较。空映像、没有非空可执行段、重叠加载段、
越界/非片内 flash 段、CPU 架构不符都拒绝。检查完整区间，不抽样、不中空通过。

本轮新工程实际 ELF：
`786daca9a0687109d8792ed9c825666c2f6be2d4d74b5ce8872f210aa69b52e4`。

| flash 半开区间 | 字节数 | 用途 |
|---|---:|---|
| `[0x08000000, 0x08053828)` | 342056 | 可执行代码/只读加载内容 |
| `[0x08053828, 0x08053C9C)` | 1140 | `.data` 初值，运行地址 `0x20000000` |

总共 **343196 字节**。两个额外 PT_LOAD 的 `p_filesz=0`，不纳入比较。
单次读取最多 1024 字节，总计最多 2 MiB，每连接一次扫描、120 秒截止，支持取消。
新报告给出成功时的全部区间；失败给出首个不同字节地址、ELF/目标字节、读取块和
此前匹配字节数，并立即停止。没有全芯片原子性或文件签名认证含义。

实机 bench01 的新 ELF 和已保留 FINAL Make ELF 都在第一块
`[0x08000000,0x08000400)` 不匹配；**这块的 LMA=VMA=0x08000000**，
故这两个首块失败不由 `.data` 的 VMA/LMA 混用引起。
旧报告只保存失败块地址，没有接收字节，无法补推历史首个不同字节。
新字节报告已在离线 `.data` 尾字节故障中验证，尚未重新实机采集。
恢复后用户 GSHC 正在运行，因此未抢占探针。
已知 EIDE ELF 仅离线解析，不能称板载匹配；历史 bench08c 指定路径不存在。
未扫描其他磁盘工程、改 ELF、改 FINAL 或为制造正例烧录。

## 字段、生命周期与安全边界

| 稳定 ID | 现有源对象 | 一致性 |
|---|---|---|
| `task.preparation` | `system_health.c:s_health` | 非原子实时读；阻塞/警告/准备字段仅观察 |
| `thread.estimator` | `estimator_task.c:s_estimator_task_timing` | 已有对齐 uint32 奇偶序列，读前/后及嵌入序列一致才接受 |
| `sensor.ins_solution` | `ins_task.c:s_published_output` | 非原子实时读；时间、更新序列、有效性 |
| `thread.logger` | `system_log_file.c:s_snapshot` | 非原子实时读；完成写入、存储及收尾字段 |

解析要求唯一 source/symtab/DWARF 对象、固定 DW_OP_addr、常量结构偏移、有限整数或枚举字段。
优化消失、歧义、指针、数组、位域、动态表达式和缺 DWARF 不猜测；缺失字段显示 unavailable。
只有 ELF 内容匹配后才能读这些字段。复位观察、断链、取消和释放使匹配失效；序列不一致
丢弃该行而不是循环重试。运行时采样预算仍为 64 KiB / 600 次 / 600 秒，显式重连才重置。
不把维护口/ACK/SWD 观察转换为 AIR M0 或命令控制器的 READY，不改飞控算法。

描述限制 64 KiB/12 层、拒绝重复键/未知根字段/非法版本/不安全 sibling 路径；
ELF 限 32 MiB、表数/符号数/DWARF 数量和 20 秒解析期限。取消是合作式：
不能把底层 OS 文件或 USB 调用的任意卡死视为已经证明硬实时终止。
进程内所有权和 MI00 claim 不证明所有进程或另一 HID 接口都被排他锁住。
DHCSR 读取会消耗其 sticky read-clear 状态位，不是无影响连续追踪。

## 验证与未完成的硬件验收

完整命令、退出码、失败尝试、哈希及证据见
[本轮报告](../../evidence/target_elf_20261014/REPORT.md)。
已执行 GSHC 205 项回归、SCG 27 项回归、实际 `Target_Run` 绑定、
7 步离屏应用流程、真实 ARM 构建/链接、真实 GCC `-fanalyzer`、Host 回归和生成门禁。
离屏 UI 和内存模型不算本机鼠标操作或 MCU 实测。
生成器首次方案曾触发架构/22 文件门禁失败，现已移除 Generated 内的绑定脚本，
改由主机 BuildRunner 完成，门禁未放宽。第一次 native GUI 脚本被测试模块设置为
离屏后错误断言 windows，在任何 DAP I/O 前失败，资源释放记录完整。

Power of Ten 文本门禁通过只证明记录范围；它仍明确输出
**critical-contract review NOT PROVEN**。没有完成整体安全合同验收、全程序栈证明、
MCU WCET/飞行资格或新增板型验证。没有构建/发布新的发行包或安装新依赖。

## 依赖与后续后端

复用本机 pyOCD 0.45.1（Apache-2.0）、pyelftools 0.33（公共领域声明，其内置
construct 保留独立许可）、libusb 和既有 Qt 环境；不自动联网安装。
`SILVERSTAR_ELFTOOLS_PATH` / `SILVERSTAR_SWD_PYOCD_PATH` 可指向受信依赖目录；
源码工作区默认复用现有隔离依赖 `.work/dev013_swd_pyocd01/deps`。
PDSC 目录只发布提取的器件事实和版本/URL/SHA-256，未复制 HAL/SDK/pack 算法；
F4/C0 来源分别标示 LICENSES/LICENSE，F1 须查原包许可。后续分发整包须保留其原始许可证。

下一独立阶段优先复用 pyOCD `StlinkProbe`/`STLink`，对 `open/enter_debug/read/close`
做有界、busy 失败即停止的适配，审计 `enter_idle`、显式 USB interface claim、取消和部分失败释放，
保留当前 `configure/open/read/close` 后端分界。不得调用 Board/CortexM 完整初始化、
reset/halt/resume/写内存，不能因为没有实物就把模拟 PASS 标成实测。
OpenOCD 阶段只允许仓库审查的 adapter/target 配置和受限命令；Tcl 配置可执行，
不能接收任意用户脚本，也不能回退到已知 claim 失败后仍继续初始化的旧路径。
两者均需独立命令/故障回归和后续实物验收，此提交没有扩大后端准入。

依据：[pyOCD probes](https://pyocd.io/docs/debug_probes.html)、
[固定 0.45.1 ST-Link 源码](https://github.com/pyocd/pyOCD/blob/v0.45.1/pyocd/probe/stlink_probe.py)、
[OpenOCD adapter 配置](https://openocd.org/doc/html/Debug-Adapter-Configuration.html)、
[CMSIS-Pack device model](https://open-cmsis-pack.github.io/Open-CMSIS-Pack-Spec/main/html/pdsc_family_pg.html)。
