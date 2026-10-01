# 2026-10-01 首个本地实验检查点

稳定基线：`d410f4a7254f0433e91a22adb237b2944939fd99`。开始时 `main` 工作区干净；实施分支为 `feature/post-field-firmware-20261001`，未操作 main、push、tag、Release、烧录或外部硬件。额度无可核实读数。今日真实外场日志未收到。

本批只实施 A 的一个白名单对象放置切片，以及验证时发现的 0.1.1 检查脚本版本衔接修复。B 多遥测、C 固定增益算法、传感器冷备均未开始。这里没有通用自动布局优化器，也没有 FIELD READY、原始 Power of Ten 合规或完整安全接受声明。

## 使用与回退

在新生成的 F407/ESKF15 Flight 工程中：

```powershell
mingw32-make CONFIG=Release MEMORY_LAYOUT=eskf_window_sram artifact-check
mingw32-make CONFIG=Release MEMORY_LAYOUT=eskf_window_sram static-analysis
```

默认 `MEMORY_LAYOUT=legacy`。恢复默认时不传实验参数，输出继续使用原目录；实验输出单独位于 `build/FCCG/SilverStar_F407/Release/eskf_window_sram`，分析输出也单独隔离。未知参数、其他目标、未选择 ESKF15 时明确拒绝。链接超容量、原有 100 KiB SRAM 审查预算和其他门禁阈值保持原样，不自动换布局、不缩任务栈。

宏 `PLATFORM_ESKF_WINDOW_BSS` 只作用于 ESKF 私有 `s_eskf_window`。默认仍进 `.ccmram_bss`；实验进 `.bss.silverstar_eskf_window`，保持 8 字节对齐，由原 linker 的 `.bss*` 收集、原 startup 的 `_sbss/_ebss` 清零。linker/startup、初始化逻辑、算法数学、15-state/float/200 Hz、协议、记录身份和任务栈未改变。没有运行时搬移或堆。

该上下文不含指针；读写均在 ESKF backend 内，其地址只传入同步的 `NavigationWindow_Reset/Receive/VarianceScale` CPU 数值路径。日志构建按字段复制到记录，未把对象地址交给驱动或 DMA。生命周期沿用原复位、GNSS 源变化复位和一致性窗口更新。未增加并发访问者或更改任务/ISR 所有权；已有序列化假设仍需全系统审查，不能从本次放置检查推导所有并发路径已证明。

`s_work` 的 3140 字节完整计算工作区曾作为候选；迁移会超过保留的 102400 字节 SRAM 审查预算，因此撤销该原型。`s_io_baselines` 没有改动。当前机制是显式选择一个经审计布局，不会按余量颜色自动决定对象去向。

旧工程用户 payload 正常保留。默认 Make 产物检查调用不新增参数，兼容旧脚本接口；新实验需要支持该标记的 payload。旧目标 header 请求实验会编译失败；保留的旧 backend 无标记时实验产物检查失败。不要把只执行 `all` 当作放置接受，应执行 `artifact-check`。旧 0.1.0 描述身份仍被支持。

## 记录结果

新生成的合成验证配置见两个 `*_configuration.ssproject`；不是用户外场最终候选。以下是实际同一 ESKF 配置的 Release 链接结果：

| 布局 | 主 SRAM used / remaining | CCM used / remaining | 窗口对象 |
|---|---:|---:|---|
| legacy | 99864 / 31208 | 63456 / 2080 | 184 B，`0x10009580` |
| eskf_window_sram | 100048 / 31024 | 63272 / 2264 | 184 B，`0x20013EC0` |

容量分别为 131072 / 65536 字节。CCM 余量仍小于 10%，仍是红色提示。184 字节收益不证明栈裕量、MCU 时序或硬件可靠性。

| 执行范围 | 结果与证据 |
|---|---|
| 初始原型修改前 | `pre_tests.log`：9 个预期失败；当时原型名为 workspace，随后因预算收窄为 window |
| 初次综合 Python 回归 | `regression.log`：41 passed / 2 failed，两个失败复现生成 0.1.1 目标被旧硬编码脚本拒绝 |
| 最终布局/身份契约 | `contracts_v5.log`：18 passed，包括旧版本、错配、错误选项、旧 target、ARM section/size/alignment 和旧脚本默认接口 |
| 修复后架构选择回归 | `regression_v3.log`：架构 11 个用例通过；该次整体 26 passed / 2 failed，失败来自身份测试脚本执行策略，已在 contracts_v5 中修正并验证实际拒绝原因 |
| KF6 Host | `validation_v3/kf6_host-tests.log`：72 executables，4393820 checks，0 failures，7 编译正例 / 17 预期编译负例 |
| ESKF Host | `validation_v3/eskf_host-tests.log`：71 executables，4361109 checks，0 failures，7 编译正例 / 17 预期编译负例 |
| Flight 架构与 PoT | `validation_v3` 两个架构与两个 PoT 日志：exit 0；PoT 原样输出 Critical-contract review NOT PROVEN |
| ESKF 真静态分析 | `validation_v3/eskf_static_analysis.log`：exit 0，`-fanalyzer` 实际编译和链接，不是 syntax-only |
| 实际错误布局负例 | `validation_v3/wrong_layout_fault.log`：checker exit 1；真实 legacy ELF 被当作 SRAM 布局检查，因区域和清零边界两项失败而拒绝 |
| 最终模板 ARM 重链 | `checkpoint_final/*arm_final*.log`：KF6、ESKF 默认与实验输出；命令及 exit 见 `commands.json` |
| Ground Host | `ground_host_regression.log`：9 passed，覆盖 F103 资源冲突、桥接有界处理及 UART/USB 队列 |
| Ground 编译/链接/区域与单函数栈报告 | `checkpoint_final/ground_arm_all.log`、`ground_build_audit.json`；这是链接范围与 `.su` 检查，不是全栈证明 |
| Ground 原样 PoT | `validation_v3/ground_power10-check.log`：exit 0，Critical-contract review NOT PROVEN |

早期 root 和 validation_v3 的三个 Ground Flight 专用目标调用均 exit 2（No rule），是验证命令选择错误，不是一个执行过的 Ground 全套门禁。它们完整保留，之后执行实际支持的 Ground `all`、PoT、Host 和 `BuildAudit_Run`。初次 v2 runner 还因预期旧名字的 artifact copy 不存在而结束；不计为完整成功。没有将这些选择性结果拼成未运行过的全套 PASS。

版本修复来源是实际失败：平台 0.1.1 生成 `SilverStar_0_1_1`，两个旧脚本硬编码 `SilverStar_0_1_0`。新的 `FirmwareIdentity_Read` 从 `SilverStar.ssproject` 读取并严格核对 numeric 三段版本与 build ID；架构检查精确匹配 Make，产物检查使用相同身份查找文件。没有压掉失败或放宽源码覆盖。

`validation_v3/results.json` 保存完整命令、工具版本、时间、exit、日志及产物哈希。它的 `source_unchanged_after=false` 明确记录后续测试执行策略/旧接口修正；不掩盖源码差异。最终重生成计划 `checkpoint_final/*regeneration.json` 只改 Makefile 和 ownership 元数据，没有改任何编译 C/header/assembler 输入。随后已重编/重链最终模板。最终 snapshot、输入/产物哈希、完整 Host 编译详情见 `checkpoint_final/`。基线 + source_delta + 本次提交新增文件组成可审计源码状态；记录过的失败、警告和未执行范围均保留。

ARM GCC 14.3.1、Host GCC 16.1.0、GNU Make 4.4.1；Python 3.14.0。严格警告沿用原模板。历史 PoT N=2/M=20 与平均密度报告未修改，当前文本扫描器未修改。

完整调用图、间接调用/第三方路径、任务与 MSP/ISR 嵌套栈、STM32 WCET、SRAM/CCM 实际访问性能及硬件/飞行验证仍 NOT PROVEN。未运行用户取消的新全栈证明工具；`.su`/链接区域或 Host 时间不替代该证据。没有真实 RF 或设备动作。

下一步交父任务选择新的小批：先讨论 A 后续静态策略与更大对象的预算取舍，再推进 B 多实例资源/唯一命令 owner；C 需独立实验 ID 和显式实验参数，真实日志缺席时不设正式增益。传感器冷备另行审查 IMU 对准后锁源、姿态连续性、源稳定门限、校准所有权与故障恢复，不能宣称已经具有冷备能力。
