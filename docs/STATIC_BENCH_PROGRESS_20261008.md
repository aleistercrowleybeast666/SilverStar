# 2026-10-08 静态台架准备与阻塞记录

本记录接续[软件收尾](NIGHTLY_SOFTWARE_CLOSEOUT_20261008.md)。本轮已识别设备、修复并验证 SCG 生成问题、生成隔离 KF6 候选并执行软件检查；**未烧录、未解锁、未 START**。当前栈门禁 FAIL，不能将已经完成的编译或其他检查拼成整套 PASS，也不能声称最新候选已上板。

## 设备与授权范围

用户报告 Ground 串口、Flight DAPLink 和 TF 已接好，设备静止、+Y 摆放，执行机构全部断开。只允许该组合的有限静态准备和任务；不进行带负载动作、显式开伞/点火指令、多面翻转、运动、拔插、串口/探针以外的系统修改或 Ground 重刷。本轮实际只做接收和只读 SWD 识别。

COM3 为 CH340 `1A86:7523`，位置 `1-1`；230400、8N1，打开前 DTR/RTS=false，30 秒被动记录没有发送字节，187 个 GSP 帧，CRC/resync/discard=0。接收到 Capability；未执行 Capability ACK，故没有以 ACK 或缺失 preflight 推断 READY。

DAP 序列号 `132765403520`，CMSIS-DAP v2、Horco 0.2；SWD 确认 Cortex-M4、ID `0x10076413`、flash=512 KiB。这些寄存器识别家族/修订与容量，不单独证明封装后缀。没有 halt/reset/flash/option-byte 操作。完整 512 KiB 只读备份 SHA256 为 `e72caaa5adbb92d69854d824ce05ee086a2a1deb83f2e79a3d70ed01aebe8aa1`；前 330132 字节与旧 28b168f BIN 的 `dcd7c68eced49c0cf2e6a9654ac99738aeebbad24f10b7ad6ee5ec6c5cd9bd7e` 精确匹配。旧 000041 任务不作为本轮任务证据。

## 软件修复及候选身份

应用源提交为 `f045d8c3e2b1cafb951702335fe1693b59d72275`，分支 `fix/nightly-user-ready-20261003`。未回退原有提交，三个 `work_*_20261006` 盘点文件保留。修复前后的完整回归日志、初次生成 stdout 及来源快照见本轮证据目录；初次生成 stderr 原始堆栈仅由工具返回、未完整落盘，此证据限制记于 manifest。

1. Windows Python 3.14 的 `mkdtemp` 创建 mode0700 目录，原实现随后尝试 `icacls /inheritance:e`，实际被拒绝，清理又以 WinError5 遮盖原错误。`WorkspacePolicy.StagingDirectory_Create` 改为在 Windows 下直接以普通 mkdir 继承项目目录权限，以随机名字、最多 16 次碰撞重试建立目录；验证单段 prefix 和工作区边界，真实访问拒绝继续报错。未修复旧失败目录的 ACL，也未调整系统权限。POSIX 保留私有 mkdtemp 行为。
2. 首次 catalog provenance 与第二次排序过的 ownership provenance 键顺序不同，引起无语义变化的 `SilverStar.ssproject` 和 ownership 哈希改写。Metadata renderer 首次即规范化该嵌套字段，原有文件保护和 provenance 内容不变。旧电压 adapter 测试路径及条件编译夹具的权威 target linker 清单一并修正；原断言及非法配置失败期待保留。

前置扩展回归为 26 PASS / 5 FAIL，原日志保留；修复后的相关整套为 **65 PASS、exit0、308.46 秒**，保留一条 pytest `cache_dir` 配置警告。涵盖工作区路径、碰撞与拒绝、插件攻击、保存幂等、托管文件 mtime、生成/构建入口、目标 linker 和 Windows 长路径拒绝。

隔离工程为 `.work/bench08b_f407`，名称 `KF6_Static_20261008_f045d8c`。源配置 `.work/Q2F407_7fa06c4/SilverStar.ssproject` SHA256 `92fa295afa7c97325f85a5be9fef6756b84393355b5a5e16604949cafb5333d6`。保留 SS0.5/F407VET6、JY901B vertical ORIENT、M9N、SX1281、SD_SDIO、OneFace、原矢量对准、KF6/二子样圆锥划桨、Delay10、原 200 Hz 和 Full 队列 80/48；未猜测或修改引脚、算法数学、导航队列/栈。迁移为当前 schema/default Full，另改候选显示名。设备/模式/参数/能力/资源配置逐项相等，资源分配不变，Core、`.ioc`、`app_task_config.h` 哈希相同。生成不覆盖外部用户工程或旧工程。

| 候选产物 | SHA256 |
| --- | --- |
| Release ELF，3326520 B | `d7e05c8bd87d070cf2c928db29c72f7f03c4a2ccf072edf4d085efabe50ff783` |
| Release BIN，331020 B | `5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3` |
| 配套 `.ssdecoder`，144321 B | `46b449244dcfde73baa5faaa795ac496d34f097bd095824959f53210067fafe2` |
| 新 `.ssproject` | `067d8d9750c28c41d32b052d161595a6fc44d2b60c8a8ea8e9cb3ea40f941ef5` |

decoder 内 `project_semantics.json` 与本次生成文件逐字节相等。这是候选的配套关系，尚不是实机 Recorded Descriptor/TF 内容验证。

## 本轮检查与具体阻塞

| 检查 | 结果与边界 |
| --- | --- |
| SCG 相关整套 | PASS，65 项、exit0 |
| 当前源四档完整运行 | 83 PASS / 3 setup ERROR、exit1、237.23 秒；本轮 basetemp 放在仓库根 `.work`，GUI 偏好夹具被 SCG 应用根路径安全检查拒绝；保留错误日志 |
| 四档 GUI 正确路径独立复验 | 3 PASS / exit0 / 55.69 秒；只改运行路径为 `apps/SCG/.work/q08g`，原测试/断言/路径检查未改；不拼成一次 86 PASS |
| 新生成 architecture-check | PASS，356 checks、0 failures、exit0 |
| 原样 power10-check | 文本 PASS，6329 checks、111 第一方 C 文件、2761 函数；815 个非阻塞 recommendation；关键契约审查明确 NOT_PROVEN |
| ARM Release 编译/链接 | 实际完成，产物见上表；严格 warning 构建，artifact-check 观察到 PASS，heap_symbols=0 |
| Release 完整命令含 stack-report | **FAIL / exit2**，不能拆出上述完成项称整体 PASS |
| 真实 static-analysis | PASS / exit0 / 124.31 秒；108 条带 `-fanalyzer` 的实际编译命令，无 syntax-only，无编译 warning；仅记录执行的编译范围 |
| Host 全套 | PASS / exit0 / 354.887 秒；80 executables、4446469 checks、0 failures；11 compile-pass、18 expected compile failures、8 NOT_APPLICABLE；存储完整性四阶段完整结束 |
| FLP decoder 严格结构加载 | PASS；`DecoderProfilePackage.Load` 解析本次精确候选包，不代表实际日志/Descriptor 匹配或生产打开 |
| 烧录、最新任务、TF 原始文件及 FLP 实际重开 | NOT_RUN；新任务 ID 尚不存在 |
| 全程序栈/ISR/MSP、WCET、关键契约人工接受、飞行资格 | NOT_PROVEN |

栈检查器首先拒绝 `Generated/Src/project_metadata.c` 的整文件来源哈希。只读盘点发现 155 个已编译 C 源的 GCC `.d` 依赖图全部匹配现有证明记录，仅两个来源/编译输入整文件哈希未知：

- `Generated/Src/project_metadata.c`：`ae4706ff828b966e517972f147eee2d5ca938a144ff437ef3b71d32a9f186181`；与原硬件工程只差项目摘要常量和一空行。
- `Generated/Src/project_log_decoder_profile.c`：`e66c2a4581505fdb114a88f7ff65c866c0e2c0b9b4c99186d0922960bbe98da4`；只差两个身份哈希数组。

按 assembler 相同的 `ProjectView_Get` 实例/variant 解析，在内存中将实际候选恢复原名称 `KF6_Logger7000_F407_20261005`：metadata 哈希变为 `8f2d00143a8e043a95a5af4816266486bfc988b9abae4c9e64dee7401a29fa7e`，decoder source 变为 `340975ee13d13d1093a206f8d9a55be7481aa9e9cf7fc92e3d14191615e7b983`；两者仍未收录。metadata 与旧工程仅差一空行，decoder 仍不同，因为当前语义记录的 component manifest 锁、physical-device 编号、部分日志 availability/reason、源图身份等已更新；完整差异见 `original_name_resolved_diagnostic.json`。这些差异不能由项目名消除，需新的精确 decoder；旧 metadata/decoder 哈希也不在当前检查器中。早期使用未解析基础 catalog 的诊断已明确标注 superseded，不能据其能力列表推断本次真实工程。

未修改检查器、未隐藏来源、未改阈值或容许未知输入。`stack_gate_exact_hash_proposal.patch` 是未应用的、仅加入这两个精确来源哈希的可审查提案。用户提供的 AGENTS.md 禁止 broaden allowlists，需明确授权后才能修订；未答复不视为同意。即使授权修订，也需新生成输出、重新运行门禁及实际链接/间接调用/栈检查；不能把现有失败改写成 PASS。没有删除空行、伪造项目身份或复用不相符来源哈希绕过检查。

## 继续顺序与最小静态验收

先决定是否授权该精确证明记录修订。若不授权，保留本轮 FAIL 并暂停刷写。若授权，固定已盘点的候选配置/身份，审查其确定来源及所有依赖，重新生成验证 owning payload，不仅替换 disposable 检查器；重新执行软件门禁并在烧录前回报实际 target、配置、ELF/BIN/decoder 哈希与检查结果。Ground 继续保持现状。

软件门禁满足后，只对已确认 Flight 主镜像做一次受控刷写、verify/readback；有限握手，以权威 preflight 校验 selftest、calibration、alignment、logger/storage 和 READY。已有 READY 校准不覆盖；非 IDLE 的校准/对准不自行重启。确需新静态 OneFace 时使用固件自身静止/方向检查；不造样、不换数学、不要求擅自翻转。TF admission 后重新取得新鲜 READY，再单次 UNLOCK/START，不自动重试。Delay10 的逻辑 deployment 和 landing 可观测，但不代表执行机构负载动作验证。

记录新的 mission ID、START snapshot generation/ack、普通和导航队列损失/错误、写入与 sync/close 状态。任务结束后确认关闭、finalized 和队列为空；动态计数仅是观察，debugger halt 的时间不作为运行时间。若只能由用户取卡获取文件，待确认任务关闭后请用户交付完整 `missions/<本轮新 ID>/`，包括 `flight.sslog`、manifest 和全部 snapshot/object sidecars，以及本次精确 decoder；不得格式化、清理或用旧 000041/遥测/合成日志替代。通过 FLP `LogOpenCoordinator` 精确匹配，检查 Recorded、原始主/副数据源和全部 run 的保存重开，再决定对应范围的接受。

## 文档阅读与算法覆盖

继续采用[用户流程总览](USER_WORKFLOW.md)的顺序：总览 → [硬件与四档](SilverStar_Recommended_Configurations.md) → SCG 配置生成 → GSHC 采集 → FLP 分析 → [算法原理与当前实现](algorithms/NAVIGATION_IMPLEMENTATION.md) → 验证边界/故障排查。算法文档第 1 节说明坐标/单位/输入，第 2 节 Pure INS，第 3 节 SF6 固定增益，第 4 节 KF6，第 5 节 ESKF15 右乘姿态误差，第 6 节调度/记录/边界；包含传播、更新、状态/量测、初始化校准、时间戳、噪声/门限和源码映射。本轮没有修改这些算法或文档中的数学。

H7 无当前生成支持；F407/ESKF15 运行失败未解决；F103/NRF 未实物验证；RET6 Logger 栈结论限原配置；无 GNSS 水平漂移；20% RAM 仍是建议而非硬门槛。此前 GUI 合并回归通过不解除历史 native abort 未归因边界。GSHC 布局和 M0/CMD/ACK 保持，NRF 无 RSSI/SNR 时为空值。

本轮原始命令、UTC、exit、版本、日志和 SHA 清单见[正式证据清单](evidence/static_bench_20261008/manifest.json)，原始执行路径为 `.work/static_bench_20261008`。日志按原字节保存；Windows 子进程混合编码仅在展示/ASCII marker 盘点时用替代字符解码，不改变原日志或哈希。完整 flash 备份和候选构建留在原受控工作路径，未复制 vendor。父线程消息工具重复返回 `thread not found`；没有可调用的 `cloud_threads` 工具，本轮通过本对话状态和最终交付报告进度。

已执行命令（仓库根目录；驱动器拒绝覆盖已有工程和日志，不应对现有证据目录重复运行）：

```powershell
.venv/Scripts/python.exe docs/evidence/nightly_software_20261008/run_scg.py apps/SCG/tests/test_workspace_policy.py apps/SCG/tests/test_plugin_security.py apps/SCG/tests/test_project_lifecycle.py apps/SCG/tests/test_hardware_and_variants.py apps/SCG/tests/test_windows_generation_path_boundary.py -vv -s --basetemp=.work/b08_reg2
.venv/Scripts/python.exe .work/static_bench_20261008/generate.py --apply
.venv/Scripts/python.exe .work/static_bench_20261008/run_gates.py versions architecture power10 release analyzer host
# 上一命令在 release/stack-report 失败后停止；其余两个门禁另行实际执行：
.venv/Scripts/python.exe .work/static_bench_20261008/run_gates.py analyzer host
# 当前四档完整运行（83 PASS / 3 setup ERROR），及正确路径的 GUI 独立复验：
.venv/Scripts/python.exe docs/evidence/nightly_software_20261008/run_scg.py apps/SCG/tests/test_feature_tiers.py apps/SCG/tests/test_feature_tier_logging_policy.py apps/SCG/tests/test_tier_device_boundaries.py apps/SCG/tests/test_tier_device_gui.py -vv -s --basetemp=.work/b08_tiers_final
.venv/Scripts/python.exe docs/evidence/nightly_software_20261008/run_scg.py apps/SCG/tests/test_tier_device_gui.py -vv -s --basetemp=apps/SCG/.work/q08g
```

当前栈失败可以在现有候选的 `Flight_Controller` 中复现：`D:/msys64/ucrt64/bin/mingw32-make.exe stack-report GCC_PATH="D:/Arm GNU Toolchain/14.3 rel1/bin"`。本记录没有再次执行该命令。所有原始 make 参数、cwd、UTC 和子进程 exit 以归档 `*_result.json` 为准。四算法和 GUI 历史测试保持原范围，不将本轮结构加载或固件 Host 检查替代实际 TF 打开。
