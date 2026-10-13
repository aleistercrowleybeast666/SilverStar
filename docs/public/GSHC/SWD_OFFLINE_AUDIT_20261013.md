# SWD 实际可用性：离线阻碍核对，2026-10-13

基线 `2aa9f27874fdcd56b4f0300ee85c9419a9f0c9fd`。本次仍未连接探针、未发 DAP 指令。
**已有可行的无 CPU 控制连接路径，但真实 gate 不能仅凭离线结果放行。**
本次结论缩小了上一阶段的“全都未证明”，并没有把模拟实现称为实机可用。

## 三项结论

| 核对项 | 已证明 / 源码可判定部分 | 仍缺的证据 |
|---|---|---|
| 二进制来源与源码 | 本机 EXE、stm32f4x.cfg、cmsis-dap.cfg 与供应商官方 20250710 归档逐字节一致；不是任意同名 EXE。二进制报告 libusb commit d52e355… | 发布包没有 OpenOCD build commit / 构建清单；b97cfd… 是日期之前的最后提交，属于候选而非正式映射。官方链接最终转向 HTTP CDN，无签名校验声明 |
| 初始化 / 退出 | 固定候选源码中，纯 SWD + reset_config none + MEM-AP 不发 CPU halt/reset/resume，不写 DHCSR/AIRCR，不加载 STM32 board/flash 脚本。下面详述 | 这些源码到该 EXE 的精确构建映射；Horco 固件实际执行 DAP_Connect/Disconnect 的引脚和链路行为；正常退出及超时强杀的实物状态 |
| 排他访问 | WinUSB 官方限制不支持同接口多应用并发；仅看到共享 CreateFile 不能反向证明没有排他。Horco 的双 DAP 接口是具体边界 | 同一物理探针的 HID/WinUSB 跨接口排他；claim 失败后必须在发送任何 DAP 指令前立即退出。现有 bulk 源码仅警告并继续初始化，未满足项目的明确拒绝语义 |

来源：[供应商下载页](https://gnutoolchains.com/arm-eabi/openocd/)、
[libusb Windows 官方限制](https://github.com/libusb/libusb/wiki/Windows#known-restrictions)、
[Microsoft WinUSB 架构](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/winusb-architecture)。
WinUSB 的限制针对设备接口 / PDO；同一个复合设备的 HID 子接口不能据此一并视为独占。

## 本机及发布包

EXE：`D:/OpenOCD-20250710-0.12.0/bin/openocd.exe`，32-bit PE，4,623,886 bytes，未签名。
SHA256 `3ee2ce721e7c2b0c0359b7a6a6b2a1f9a7c9a8dca3ad11db16b1085d57229cf7`。
官方归档通过下载页的实际链接获取，仅在内存中读取指定条目进行哈希比较，没有提取、
安装或运行下载的 EXE / 驱动。归档 7,521,194 bytes，SHA256
`3edc276463840e0545e957d4349d2c002d57a58244bf3d7496558e42dc849757`。

供应商仓库 2025-07-11 之前最后提交为
`b97cfd65051e40d60585b1f5fb335c04d81cbe2e`，日期 2025-07-09 19:24:52 UTC。
“发布日期前最后提交”只是可复核的源码候选，不是完整二进制构建证明。包内没有映射清单；
EXE 没有可用 COFF 符号表，内嵌源路径 / 日期也不能替代 commit 证明。
libusb commit `d52e355daa09f17ce64819122cb067b8a2ee0d4b` 是 EXE 自己报告的版本信息。

## 初始化与退出路径

核对固定候选源码，而非把上游 v0.12.0 或今天的 master 当成本机精确源码：

1. `handle_init_command → adapter_init → cmsis_dap_init`：bulk open / 元数据 / 状态、
   DAP_Connect(SWD)、时钟、传输及 SWD 配置。`cmsis_dap_get_status` 的 SWJ_PINS mask=0，
   是读取引脚状态；显式写 nRESET 的初始化分支要求 connect-under-reset，当前配置没有该标志。
2. `transport init → swd_init` 不执行 reset；`dap init → swd_connect` 的
   `adapter_assert_reset` 同样受 connect-under-reset 条件约束。**不能把 JTAG 的
   jtag_init 强制释放复位路径误套在纯 SWD 配置上。**
3. MEM-AP 初始化读取 AP 配置、设置 DP/AP 传输状态；其 halt/resume/reset 方法只改变
   OpenOCD 的内部模拟状态。GDB attach/detach event 被配置为空，没有 cortex_m、flash bank、
   RTOS 或用户脚本。API 只发固定诊断与 RAM 的 RSP `m` 请求。
4. GDB EOF 关闭事件不发 resume；正常 DAP 清理的 `swd_quit` 会发送 SWD→JTAG 或 dormant
   链路序列，随后 `cmsis_dap_quit` 发送 DAP_Disconnect、关 LED 并释放 USB。退出不是仅仅
   CloseHandle，也不承诺保持原 SWD/JTAG 链路模式。
5. 现有 API 的有界强杀仅终止自有主机进程，不是 MCU reset/resume。但是强杀可能来不及
   完成 DAP_Disconnect；host 资源已释放不等于探针固件正常退出流程已完成。仍需台架核对。

源码：[OpenOCD 入口](https://github.com/sysprogs/openocd/blob/b97cfd65051e40d60585b1f5fb335c04d81cbe2e/src/openocd.c)、
[SWD](https://github.com/sysprogs/openocd/blob/b97cfd65051e40d60585b1f5fb335c04d81cbe2e/src/target/adi_v5_swd.c)、
[MEM-AP](https://github.com/sysprogs/openocd/blob/b97cfd65051e40d60585b1f5fb335c04d81cbe2e/src/target/mem_ap.c)、
[CMSIS-DAP](https://github.com/sysprogs/openocd/blob/b97cfd65051e40d60585b1f5fb335c04d81cbe2e/src/jtag/drivers/cmsis_dap.c)。
上述结论是主机代码路径结论，没有测量 MCU、NRST 或探针固件实际输出。

## 排他访问的具体边界与修正方向

候选 bulk 后端的 `libusb_claim_interface` 失败只输出警告，随后创建传输缓冲。
固定 libusb 源码用共享 CreateFile，并通过 WinUsb_Initialize 建立接口句柄。
在真正 WinUSB 驱动下，失败后的提交通常会因无有效接口句柄被拒绝；这不等于 OpenOCD
已实现项目要求的明确 Busy / fail-fast。libusbK、libusb0 不能套用 WinUSB 的并发限制。

Horco 历史主机枚举显示 MI_00=WINUSB、MI_01=HID。即使 MI_00 独占成功，也没有证明
其他程序不能从 MI_01 给同一支探针发调试命令。应用内 Lock、仅本软件遵守的 named mutex、
或枚举进程名称，都不能单独解决该边界。不查询或关闭另一个项目的真实调试会话。

源码：[bulk open](https://github.com/sysprogs/openocd/blob/b97cfd65051e40d60585b1f5fb335c04d81cbe2e/src/jtag/drivers/cmsis_dap_usb_bulk.c)、
[libusb Windows 后端](https://github.com/libusb/libusb/blob/d52e355daa09f17ce64819122cb067b8a2ee0d4b/libusb/os/windows_winusb.c)。

无需为此更换芯片支持架构或引入完整 IDE。可行的最小后续修正是沿用 MEM-AP 与固定 bulk
接口，采用可明确对应源码的后端，把 claim 失败变为立即退出，并在 DAP 指令前处理同一支
探针的 HID 占用边界（例如正确的独占 HID 句柄保护，失败返回 Busy，保持已有所有者）。
后者需要具体 Windows 句柄路径及驱动行为验证。可审计的局部后端构建应放在独立目录，
不替换本机安装、不改驱动；本次没有构建或安装它。
pyOCD 的低层 CMSIS-DAP 接口也是候选，但高层 Session 的默认 halt/resume/auto-unlock
不能直接使用；换库不自动解决双接口排他，也需要明确版本与生命周期核对。

## 本轮最小修改和验证

只修改 owning GSHC adapter 配置：指定 Horco bulk MI_00，并将废弃的
`gdb_port/tcl_port/telnet_port` 改为本机支持的 `gdb port/tcl port/telnet port`。
gate 仍为空；没有新增绕过参数，也没有增加读取/控制功能。

本机真实 EXE 的 config-only 验证使用**首命令 noinit、移除 init、末命令 shutdown**，
并用虚构序列号 OFFLINE_NO_DEVICE。源码检查说明这会在配置阶段结束，adapter 未初始化，
网络服务未启动。旧配置解析退出 0、产生三个废弃命令提示；修正后的 configuration03
退出 0、无这些提示。它只证明语法及注册项有效，不证明 USB、SWD 或目标兼容。
相关 backend/API/CLI 模拟回归 **47 passed，1.34 秒，退出码 0**；没有重跑或冒称全套 141 项。

## 下一次台架所需最小确认

本轮按离线授权结束，不自行上板。下一次如要验证实际 ID/read-only attach，需用户确认：

- 明确指定这支 Horco 和 F407 安全台架的独占时间，确认另一项目未使用同一支探针；
  明确目标供电、SWDIO/SWCLK/GND 接线，执行器和点火输出处于安全隔离状态。
- 首轮 NRST 不接，先核对独占获取 / Busy 拒绝，再只读一次 CPUID、DBGMCU_IDCODE、DHCSR
  并正常断开；不发 halt/reset/resume、Flash 或 RAM 写命令。保留目标运行 / 心跳前后证据。
- 需要验证“已有暂停目标保持暂停”时，由用户另行准备已暂停的安全目标；我们的 API
  不自动制造暂停状态。HID/WinUSB 冲突和强杀退出测试用专门的受控占用进程，不接管已有会话。

现有未修复后端不得直接解除 gate 进行上述测试。先完成明确 fail-fast / 双接口保护或
获得清楚限定的独占测试条件及后端审查，再申请具体台架操作授权。没有要求无穷的零风险
证明，也没有把离线测试当作实际硬件行为的证明。

证据保留 `.work/dev013_swd_audit01`；正式摘要在
[`apps/GSHC/docs/evidence/swd_offline_audit_20261013`](../../../apps/GSHC/docs/evidence/swd_offline_audit_20261013/README.md)。
