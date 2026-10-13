# SWD 软件拒绝与释放保护，2026-10-13

基线 `659ec97445a86af4e18a3f2e36cf4f8e50cc0572`。
本轮修复软件拒绝路径的具体缺陷，**没有实现跨应用 / 跨 HID 接口的物理独占，也未放行实机 gate**。

## 已修复且可验证的范围

- attach / 读取时由 backend 抛出的 Busy、InvalidRequest 等错误，现在先释放本会话拥有的
  部分资源，再返回失败。之前 Busy 和 InvalidRequest 被误当成本地参数拒绝而跳过清理。
- 本地重复 attach / 并发方法调用不会释放已有所有者。非法内存请求和限频在 I/O 前直接返回，
  不与“backend 已部分 claim 后失败”混用。backend open/close 的非预期返回值也不能被忽略。
- 同一 Python 进程内，经 `SwdSession` 进入的不同实例按物理 USB parent identity 协调。
  第二个实例在 backend 创建之前返回 Busy；最多 32 个所有者。释放失败保留所有者并阻止重开。
- OpenOCD 子进程需输出固定 init-complete 标记才可进入 API 读取。已知 claim 失败日志为
  终止错误；Resource busy / LIBUSB_ERROR_BUSY 返回 Busy，其他 claim 错误返回 TransportError。
  第一个原因被保留，已观测到失败后不再发送 RSP 内存读取或发布目标快照，没有自动重试。
- stdin 的 BrokenPipe 不再跳过进程回收及其他流关闭；其他关闭失败仍尝试其余资源，并明确
  返回 ReleaseFailed、保留所有者供显式重试。不把“尝试过清理”说成“OS 一定已释放”。

进程内协调仅覆盖 `SwdSession` 的调用路径：**不覆盖另一 CLI / Python 进程、外部调试器、
直接 HID 客户端或绕开 API 的调用**。专门的双进程模拟测试明确证明第二个进程可以独立
通过它自己的进程内协调，防止将此机制错误描述为跨应用锁。

## 旧外部后端的实质限制

[离线源码核对](SWD_OFFLINE_AUDIT_20261013.md)记录的 stock OpenOCD bulk claim 失败仅警告
并继续初始化，仍未在外部 EXE 内修复。读取 stderr 是事后观察，不能保证外部 EXE 没有在
警告前后尝试 DAP 指令。init-complete 屏障只约束本软件的读取和状态发布，不是底层设备锁。

Horco 有 MI_00 WinUSB 和 MI_01 HID；本轮未取得这两个接口的 OS 独占句柄。WinUSB 单接口
的并发限制不能扩展成整个复合探针独占。源码 commit 到供应商二进制的正式映射也仍不足。
因此不能靠添加 EXE 哈希、常见进程列表为空或这次台架许可直接解除 `_ADMITTED_EXECUTABLES`。

可维护的下一步是保留 `SwdSession` / CLI / GUI，替换私有 adapter 的拥有权实现：

1. 由同一个受控 backend 在任何 DAP 指令前获取指定探针的 WinUSB / HID 相关句柄，
   任一 claim 失败即 Busy/失败返回，释放本次已取得部分；不能抢占既有所有者。
2. 实际 bulk I/O 必须复用该所有者持有的句柄，直到断开才释放。先打开检查再关闭并另起
   OpenOCD 是有竞争窗口的做法，不作为原子独占保证。
3. 可复用成熟 CMSIS-DAP 协议层，但具体库/版本及其可注入 transport、句柄和生命周期
   仍需选定并审计；本轮没有安装新库、修改驱动或大规模构建外部程序。
   另一条路线是具备明确源码映射、claim fail-fast 及双接口保护的受控后端构建，不能只修 wrapper 日志。

这属于有限的后端替换工作，不需要重做 GUI、飞控算法或建立完整 IDE。本轮不擅自扩大实现范围。

## 台架授权与本轮真实检查

任务进行中已收到用户台架确认：只接飞控、外部 5V，DAPLink 仅三线 SWDIO/SWCLK/GND，
NRST 与 DAP 供电未接，物理执行器已断开。用户报告非竖直姿态，对此只读核对无关。
这些是用户报告的接线条件，没有实际测量；无需重复请求已经提供的同一确认。

按后续授权只读检查相关进程和 PnP 元数据，时间 `2026-10-13T17:12:44Z`：

- Horco CMSIS-DAP，`FAED:4870`，serial `132765403520`，PnP OK。
- root `USB\VID_FAED&PID_4870\132765403520`，MI_00 WINUSB，MI_01 HidUsb。
- 查询列出的常见调试器名称（OpenOCD、pyOCD、ST-Link、J-Link、Ozone、UV4 等），结果为空。
  未杀进程。未覆盖任意改名工具、Python 内嵌客户端或内核句柄占用，不能据此证明未占用。

**真实 F407 身份、running/halted、RAM 响应均未取得；没有打开 USB/HID/串口或发送 SWD 指令。**
本轮停在连接前的原因是上述后端技术缺口，台架接线/执行器确认已经收到。实机 gate 继续关闭。
设备释放证据仅覆盖主机元数据 helper 和模拟子进程，不能冒充真实探针释放证据。

## 验证

保留的修复前故障测试 `pre_fix01`：4 failed / 2 passed，复现 Busy/InvalidRequest attach
部分资源不释放、读取 Busy 不失效、stdin 关闭错误跳过回收。原断言保留，未降低要求。
正常与故障包括已知 claim 消息分片/EOF、启动超时/取消、正常启动与只读报文、释放失败、
同进程冲突、跨进程限制、重复请求，以及 GUI 关闭/迟到结果。

本机已有 EXE 的 marker 解析仅使用 `noinit`、禁用全部端口、echo 和 shutdown，无 adapter
配置、无目标 init，退出 0，验证固定标记确实输出 stderr。它不验证 target 初始化。
最终同一次回归结果和源哈希见正式证据说明；所有 target 数据及调试子进程为模拟。

证据保留 `.work/dev013_swd_guard01`，不执行清理。正式摘要：
[`swd_software_guards_20261013`](../../../apps/GSHC/docs/evidence/swd_software_guards_20261013/README.md)。
