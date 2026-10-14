# SCG / GSHC 目标描述与 ELF：2026-10-14

## 结论及验收入口

软件实现完成并形成独立本地提交；不包含 ST-Link/OpenOCD 实现或 Android/DeviceService 迁入。
[操作与兼容矩阵](../../public/GSHC/TARGET_ELF_0_1_3.md)给出 SCG 生成/绑定、GSHC 导入和离线 CLI 验收步骤。
新增描述不写飞控 C 源码；没有修改导航/开伞算法，也没有发行、push、tag 或烧录。

**实机全量 ELF 匹配及相应诊断正例仍未验收。** 401 个型号是元数据覆盖，未逐板验证。
用户反馈 DAPLink 连接通过，属于用户手验反馈；不等同于本轮生成固件的匹配证据。

## 可复核的执行结果

每次实际执行的命令、工作目录、UTC 时间、退出码及完整 stdout/stderr 位于
[evidence.zip](evidence.zip) 的 `task/<attempt>.json/.log`。不将下面不同范围拼成未执行的全仓库通过。

| 尝试 | 范围 | 结果 |
|---|---|---|
| `swd_regression04` | 8 个 GSHC 文件：会话、只读 guard、真实 pyOCD 类的模拟链路、UI、ELF、探针枚举和串口布局 | **205 passed**，138.62 秒；不是全 GSHC 测试全集 |
| `scg_tests04` | 描述生成、生成集成、维护合同、构建进度、GUI target 构建进度 | **27 passed**，98.37 秒；不是全 SCG 测试全集 |
| `build_service02` | 新 project02 实际 SCG 生成、ARM Release 编译/链接、BuildRunner.Run 绑定 | 退出 0，4/4 诊断可解析；159 处 ARM gcc 命令记录，0 个 compiler warning |
| `target_runner03` | 已建 project02 的实际 GUI Target_Run 增量入口 | 退出 0；Make 无需重编译，仍重新核对实际 ELF 并绑定；不冒充第二次全编译 |
| `gates02` | project02 原样发出的 `architecture-check power10-check artifact-check` | 退出 0；architecture 356 检查；Power10 6447 检查、113 C、2813 函数、847 非阻断推荐；artifact ELF 3388512 / bin 343196 字节 |
| `analyzer02` | project02 原样 static-analysis，实际 ARM GCC `-fanalyzer` 编译/链接 | 退出 0，日志包含 110 处 `-fanalyzer`，0 个 compiler warning；不是 syntax-only |
| `host02` | project02 原样 host-tests，实际本机 GCC | 退出 0，80 个 Host test group，包含预期编译失败用例；日志明确 All SilverStar host tests passed |
| `core_compile01` / GSHC 回归 | 小型编译器生成 fixture：Cortex-M3、M0+，另有 M4 主 fixture | 真实 ARM 编译；全部离线，无目标执行 |
| `app_offscreen05` | 实际 app.main/Controller 的 7 步应用流程，模拟探针和内存 | 退出 0；导入、模拟匹配四行、断开、坏描述拒绝、旧 ELF 模拟不匹配、连接中关闭；UART opens=0，DAP packets=0，线程/owners/library 释放记录均正常 |
| `input_audit01` | 新 ELF、已知 FINAL Make/EIDE ELF、已知历史候选路径的离线审计 | 退出 0，记录各自 SHA、LMA/VMA/大小；历史 bench08c 指定文件不存在 |
| `pre_post01` | 空可执行 PT_LOAD 的真实前后行为 | 旧源码接受非法映像，修复后拒绝；正常 ELF 保持接受、四行可解析 |

`app_offscreen05` 在最终诊断列宽调整后执行；205 项回归在该两行显示宽度调整前执行，
没有宣称同一大命令重跑过。两路波特率标签的文字/几何在最终应用流程中检查。
截图为 [离屏内存模型](preview_offscreen_simulated.png)，不是实机诊断或 Windows 鼠标操作。
离屏字体回退使波特率数值在该截图中出现方框，实际字段值和解析有独立测试；
不能据此宣称 native 字体视觉验收完成。用户正在验收其他程序，本轮没有拉起可见窗口抢桌面。

Power10 原样输出 **Critical-contract review NOT PROVEN; manual acceptance pending**。
这批主机软件变更没有提供全固件原始 Power of Ten 合规、有效断言密度证明、
全程序栈/WCET、导航精度或硬件飞行资格。没有放宽源覆盖、例外或门禁。

## ELF 完整覆盖与失败解释

精确新 ELF SHA-256：
`786daca9a0687109d8792ed9c825666c2f6be2d4d74b5ce8872f210aa69b52e4`。

- `[0x08000000,0x08053828)`：342056 字节。
- `[0x08053828,0x08053C9C)`：1140 字节的 `.data` 初值，RAM VMA 为 `0x20000000`。
- 共 343196 字节；两个 `p_filesz=0` 的 RAM/CCM 段不比较。
- 测试比较的是每个加载字节的地址集合，且没有重复或 RAM 地址；不是抽样/仅检查字节总数。
- 非空可执行段、大小、重叠和可信 flash 边界均检查；描述不能扩大目标目录的内存权限。
- `.data` 尾字节故障测试验证新报告的首个差异地址及 expected/actual 字节。

前后证据使用旧 `elf.py` 的**已记录 SHA**
`2ae23bafc60b85d4de7a3e0060c16b2d43c03fa4a0ed3374470bcba871a396b8`：
按本轮明确变更反向重建后，只有哈希完全匹配才执行旧代码。旧读者允许“可执行段零文件字节、
仅非执行 .data 有内容”的 ELF；当前读者明确返回 `No executable flash image`。
完整脚本、旧源码、fixture 哈希和结果保存在归档内，未修改用户 ELF 或目标。

## 实机与关闭证据边界

较早已获授权的 `bench01` 在既有台架上执行，目标 CPUID `0x410FC241`，
family ID `0x413`、REV `0x1007`。该 ID 是 F405/407/415/417 共用，不代表自动识别完整订货型号。
三个会话全部释放 OK，共 160 个独立审计的 DAP TX 包，errors=[]，library_released=true、owners=0。
没有 target memory writes、halt/reset/resume、烧录、START 或执行器动作；DP/AP 寻址和调试电源握手
仍有协议层写入，不能描述成“USB 从不发写命令”。DHCSR sticky 位读取的影响在操作说明中披露。

新 ELF（未烧录）及保留 FINAL Make ELF
`86f951ac3dab0611232d1177ea649c2c219f9afdd47bd923d6ab716de93ffd4a`
都在首个块 `[0x08000000,0x08000400)` 不匹配并拒绝诊断，随后释放。
该代码段 LMA 与 VMA 相同，排除这两次首块失败由 `.data` 地址混用引起。
旧记录没有 RX 字节，因此**历史首个差异字节无法恢复**；没有编造实际字节或断言硬件坏了。

FINAL EIDE ELF `bcd2c8d66aaea93ecff9fbff2dfadacc32c8e2fe9ffe3842088f0071f83e1c69`
只有离线解析和模拟不匹配；没有实机验证。四行中日志新符号缺失，保留 3/4 可解析结果。
恢复后只读进程检查发现用户 GSHC 正在运行；未终止它、未再次抢占探针或读取 flash。
正例仍需用户板上精确 ELF 及空闲探针；本轮不通过改 ELF 或新烧录制造正例。

## 失败尝试全部保留

- `gates01` 退出 2、`scg_tests01` 1 failed/9 passed：初始方案把 binder 放进 Generated 并从 Make 调用，违反22文件边界。改成 metadata + 主机 BuildRunner 后通过，未改门禁期待。
- `firmware_tests01`：31 passed、2 errors；超大参数 ID 形成 Windows 超长 fixture 目录。仅添加短参数 ID，故障内容和拒绝期待不变。
- `swd_regression01`：102 passed、1 failed；子进程缺少测试模块 PYTHONPATH。随后使用完整显式环境重跑。
- `native01` 退出 1：辅助测试模块把 Qt 设成 offscreen，windows/exposed 断言失败；0 DAP 包，关闭/释放记录正常。没有将其伪报 native PASS。
- `app_offscreen02` 退出 1：模拟身份仍与旧实物常量比较；修正测试身份后 03/04/05 通过。03 缺字体，04 加显式字体，05 为最终列宽截图；均为模拟。
- `scg_tests03`：17 passed、1 failed；新增 DIAGNOSTICS 状态日志未进入旧输出期待。保留原进度检查并明确断言 unavailable 状态和完整新增日志后，27 项通过。
- 早期沙箱网络失败后，只下载两个官方 PDSC（共304590字节），没有下载 SDK；恢复时沙箱 CIM 查询权限不足，改为已授权只读查询，没有杀进程。

## 复核、来源和存储

[verification.json](verification.json)记录归档 SHA、基线、冻结 tag 和各证据成员哈希；
[source_manifest.json](source_manifest.json)记录每个新增/修改源文件的精确字节哈希。
归档 `source_snapshot/` 包含这些文件和相对基线的 tracked.patch；基线为
`034e491bc6e4c6f4e69a59d467db677640c23e8e`。这是可审核的 dirty snapshot；
本地最终提交包含同一实现，Git 的 CRLF/LF 规范化可能改变工作副本字节表示。
旧 bench01 自带其执行时的源文件哈希，不把后来扩充的差异字节报告归给旧台架结果。
复用的 DAP 包守卫源码及原路径/哈希另外保存在 packet_guard_reference.py / external_reference.json。

[输入审计](input_audit.json)记录 ARM GNU 14.3.Rel1 / GCC 14.3.1、Host GCC 16.1.0、
GNU Make 4.4.1、Python 3.14.0。运行环境复用 pyOCD 0.45.1、pyelftools 0.33、PySide6 6.10.1，
未安装新依赖。PDSC 为 F1 2.2.0 / F4 3.1.1 / C0 2.4.0，保留 URL/版本/原始文件 SHA，
不归档 SDK、HAL、pack算法或大环境副本。

`.work/dev013_target_elf01/inventory.json` 是本轮路径/用途/所有者/大小/SHA 清单，归档也包含它。
全部生成工程、编译结果和失败日志均保留；正式归档只收小型记录、脚本、源差异和测试 fixture。
本轮工作目录清单合计 489.2 MiB，正式 evidence.zip 为 2223513 字节。
没有任务末清理，没有旧 .work 清理，没有来源目录删除。三份用户原有未跟踪清单不加入提交。
v0.1.2 tag 对象保持 `942f20ef64df3cb1aa65be7349361c409418aa0f`，
其 commit 保持 `c31c13cc0686a56a3184d4f207fd3816c5d39696`。

ST-Link/OpenOCD 最小后续阶段见操作文档；两独立项目仅只读调查，来源文件哈希保存在本轮
`migration_survey.json`，不混入此 ELF 提交。没有真实 ST-Link 验证，没有迁移后构建宣称。
