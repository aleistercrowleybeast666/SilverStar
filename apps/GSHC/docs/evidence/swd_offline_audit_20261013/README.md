# SWD 离线阻碍核对证据

基线 `2aa9f27874fdcd56b4f0300ee85c9419a9f0c9fd`。
[逐项结论与最小台架条件](../../../../../docs/public/GSHC/SWD_OFFLINE_AUDIT_20261013.md)。

本机 EXE 及两份关键配置与官方 20250710 归档逐字节一致。二进制报告的 libusb commit
已定位；供应商发布日期前最后 OpenOCD commit 只能作为源码候选，不能当正式构建映射。
对照该候选的纯 SWD/MEM-AP 初始化及正常退出路径，没有 CPU halt/reset/resume 请求，
正常退出仍会转换 SWD/JTAG 链路模式并发送 DAP_Disconnect。

WinUSB 单接口的官方并发限制不能覆盖 Horco 的 HID/WinUSB 两条调试路径。
bulk claim 失败仅警告并继续是明确的 fail-fast/错误语义缺口；本轮没有改造、构建或替换
外部程序，也没有假称共享 CreateFile 就证明 WinUSB 可多进程并发。

代码改动仅在 owning GSHC adapter：固定 bulk interface 0，并替换三个废弃 port 命令。
gate 未改。`configuration01/02/03` 使用本机已有 EXE，先 noinit、移除 init、末 shutdown，
序列号虚构。最终解析退出码 0，无 deprecated 提示；没有请求 adapter/目标初始化。
后端/API/CLI 模拟回归 **47 passed，1.34 秒，退出码 0**。没有本轮 141 项全套或硬件结果。

`evidence.zip` 保留 PE 元数据、发布包条目比较、公开固定源码及原许可证、检索元数据、
配置解析命令/输出、测试命令/源哈希/日志和本轮源快照。`manifest.json` 保存哈希。
下载的官方归档仅在 `.work/dev013_swd_audit01` 保留，未提取或运行它的 EXE/驱动，
不把归档再复制进 Git。归档 URL 最终跳转 HTTP CDN、包未给出签名/源码映射，已明确记录。

早期 sandbox DNS 不可达、两次 SWD 源路径 404 和 ARM objdump 无法解析 x86 PE 的探索
结果已记录；正确路径通过 PE 内嵌源名定位为 `src/target/adi_v5_swd.c`。
本轮无设备连接、没有台架动作、没有占用或查询其他项目的调试会话、没有驱动/程序安装、
没有固件构建、发布、推送或清理。冻结 v0.1.2 保持原 tag object 与 commit。

源码级判断不证明 Horco 固件或实物引脚行为。后续应先处理 fail-fast/双接口保护，
再申请明确独占、安全接线、NRST 不接的只读台架验证；不得直接给现有 gate 加一个哈希。
