# 控制任务限定合同复核（2026-11-01）

本批把既有 PID/LQR 数学核心接入显式启用的研究任务。它没有电气执行器驱动，
`deployable=false`；研究快照的 `ready` 不代表部署或硬件 READY。普通 GUI 参数导入
默认不启用任务；纯核心导入仍保留原先的周期能力，包括 20 ms 旧参数包。

任务使用固定功能表索引 **4**，PID/LQR 只允许选中一个实例。生成器直接调用所选
核心，没有运行时回调注册表。现有 FlightTask 的 2 ms 轮询负责调用，控制离散周期
固定 **10 ms**，不新增 RTOS 任务。控制实例只 Start 一次，跨阶段保留状态；窗口停止、
落地/任务结束或故障后撤销输出并终止，本次任务中不能重新启动。

输入来自实际 Estimator 快照及实际校准后的惯性陀螺。ENU、body+Z、Hamilton wxyz
`q_nb` 转为 body-Y 小角度俯仰（rad），角速度使用校准后的 body-Y rad/s。研究域
限定 |pitch|≤0.35 rad、|qx|/|qz|≤0.01、|rate|≤20 rad/s，并检查有限值及四元数范数。
允许晚到不超过 **2 ms**（包含计算到发布的时间），输入年龄不超过 **20 ms**，两输入
时间差不超过 **10 ms**，输出快照最长 **12 ms**；不补跑错过的周期。

来源证明由真正获准进入 INS 的校准样本沿初始对准、聚合、队列及成功预测传播至
本次 Estimator 提交。source instance、sensor epoch 和 calibration generation 必须
一致，不能在 getter 中读取当前 selector 并冒充历史来源。对准窗口中途换源、队列满/
未就绪、来源未知等情况会撤销证明。未被这个令牌覆盖的独立磁/硬件四元数初始姿态
不能启用研究控制。新增 Estimator health bit 11 为 INPUT_PROVENANCE_INVALID；
原 uint32 wire 宽度、原位号及历史记录字节不变，与 SS-TM 独立 health 映射无关。

发布边界在同一临界区复核 lifecycle、任务窗口、当前来源证明和时间，再一起发布输出
及推进 64 位调度时间。getter 先检查局部副本，确认后才写调用方；内部损坏不会部分
写出快照。停止时在一个锁内清除 backend_started、撤销输出、发布终态，锁外执行
已决定的 Stop，避免合法停止被并发 getter 误判为内部损坏。坏外部输入/超时保持普通
错误和 lifecycle FAULT；内部状态损坏走既有有界断言 fail-stop。Host 仅为测试拦截
真实终止 trap，不能据此声称 MCU 能从断言恢复。

输出字段为 **`requested_body_y_torque_nm`**：箭体 Y 轴请求力矩（N*m）。任务明确采用
**1 N*m / core-output-unit** 映射，总研究域为 **±1 N*m**，所选 output_limit 可以更小。
这与 TreeDiagram 的 body-Y 力矩输入一致；泛型数学核心 ABI、参数单位及算法 C/H
没有随单位标注修改。它是有界的最新值内存出口，不会驱动硬件。

## 已执行证据及范围

- [task-v7b.log](task-v7b.log)：同一完整命令 **62 passed / 206.92 s，exit 0**。
  两个新生成的实际 PID/LQR backend、mission、校准及运行模块经 GCC
  `-O2 -Wall -Wextra -Werror -pedantic -fanalyzer` 编译，含正常、坏样本、时间/来源、
  停止/发布交错、内部损坏、数值单位及旧包兼容测试。传感器/估计器端口在该任务组中
  是注入输入，不能冒充真实 producer 或硬件。
- [task-v7b-receipt.json](task-v7b-receipt.json)：精确命令、36 个 owning 文件 hash、
  生成源码及二进制 hash、实际输出。0.01 rad 和 0.002 rad/s 时，PID 实测
  **−0.0325199999 N*m**，LQR **−0.0320941508 N*m**。
- [task-v7.log](task-v7.log)：保留 **60 passed + 2 failed**。两失败为新 metadata
  测试未指定 UTF-8，触发 Windows GBK 解码错误；修正读文件编码后完整重跑 v7b，
  没有把两轮选择性通过拼成一次全组通过。
- [units-pre-v1.log](units-pre-v1.log)：修改前两项输出单位契约缺失的真实失败。
- [getter-pre-v1.log](getter-pre-v1.log)：修改前 PID/LQR 的四个真实失败：损坏输出
  部分写入调用方、lifecycle 读交错可取得过时有效快照。
- [boundary-fault-v2](boundary-fault-v2)：同一实际 harness，停止状态发布、调度时间
  发布及初始对准来源历史 **3 fail → 3 pass**，保留隔离前后源码、命令及退出码。
- [queue-boundary-v2](queue-boundary-v2)：实际 INS/EstimatorBus 满队列和未就绪边界
  **2 fail → 2 pass**。旧队列不能重新授权已经撤销的 provenance。
- [host-v6.log](host-v6.log)：上一单位标注 epoch 的真实 emitted Host 选择组完整执行，
  3 个 executable、1146 个计数检查及 runner 必跑 storage tail 全通过；包含真实
  INS/KF6/队列 7 个进程用例。lifecycle_logging 明确为 control-disabled 回归，不能
  计作启用控制验证。该日志不是默认/installation 全 Host，也不是 v7b 新单位源码
  的全固件验收。
- root 的 [mission-combined-after-v2.log](../critical/mission-combined-after-v2.log)
  是独立 **31 passed** 的 mission/runtime 回归（13 + 18），不与本组拼接计数。

复现入口：设置 `PYTHONPATH=apps/SCG/src`，将 `D:/msys64/ucrt64/bin` 加入 PATH，运行
`D:/python_software/TreeDiagram/.venv/Scripts/python.exe -m pytest
apps/SCG/tests/test_control_research.py -q --basetemp=<新的隔离目录>`。
当前归档的精确目录和编译命令在 receipt 中；不要覆盖旧证据目录。

## 未由本组证明

默认/installation 完整 Host 结果见下方新 C epoch；各 ARM 构型、实际链接资源及全程序
栈证明由独立最终构建批次记录，本报告不替代那些执行结果。既有队列容量和 RAM/CCM 预算未放宽；
五个已审查 CPU-only INS 对象使用既有 CPU_FAST placement，不迁移 DMA 对象。
硬件 WCET、实机 ISR 时序、物理传感器资格、执行器驱动和飞行验证仍未具备。

Power-of-Ten scanner 的全程序 critical-contract 状态仍是 **NOT PROVEN**；上述限定
边界复核不把文本扫描、Host 通过或空余 SRAM 当成完整安全证明，不宣称原始 Power of
Ten 全合规、NASA 认证或全系统 acceptance 完成。失败、setup 错误和旧 epoch 日志
全部保留，具体历史说明见 [CONTRACT_REVIEW.md](CONTRACT_REVIEW.md)。

## 完整 Host 集成的新 C epoch

首次默认 B 完整 Host 在旧 `test_interfaces.c` 的结构大小断言处实际编译失败，
原日志 [full-host-b-default.log](full-host-b-default.log)、退出码及 receipt 均保留。
当时运行器还把新生成的 Python bytecode cache 计为源漂移；这两项没有被记成通过。

修复仅更新 owning Host fixture 的精确 `==` 大小/偏移断言，增加 32 位来源/代际字段
和零初始化 `valid=0` 检查。生产 C/header、队列容量、内存预算均不变。
[layout-probe-arm.json](layout-probe-arm.json) 保存真实 Cortex-M4 ARM GCC 编译命令与
汇编，[layout_probe.c](layout_probe.c) 保存探针原始源：provenance 为 16 字节、valid
偏移 12、increment 中 provenance 偏移 40；base/ESKF/augmented increment 分别为
56/112/120 字节，ESKF gyro/accel/quality 偏移 56/80/104，augmented interval 偏移 112。

两份 C 工程经新 catalog/model 和正常生成入口生成，未手改生成代码。执行源身份为
`e7c42b7c4971fddb02c6d5c60864b50dffaa3f1a` 加上述单个 Host fixture 的可审计差异；
[generation/source-snapshot](full-host-c-generation/source-snapshot.json) 记录前后源 hash
完全一致。新增 fixture SHA-256 为
`cceebe76f5c8618f35ce3522d1186110274ffb880756a87fc574deac7c235600`；当前 owner 名单共
37 个文件，下面原 v7b 的 36 文件身份保持其原 epoch。

[full-host-c-vs-b.json](full-host-c-vs-b.json) 逐项核对正常生成 C 与 stack v5 B 的目标
source graph、生产 C/ASM、头文件、forced includes、linker 和 Make 输入：默认 481 个
文件、安装 502 个文件全部字节相同。这建立已有 ARM 编译输入的对应关系，不冒充重跑
ARM，也不把新 Host fixture 归到旧 GUI 测试快照。

`run_full_host_c.py` 分别执行两份 emitted `Tests/Host/run_tests.ps1`，没有 `-Only`。
生成代码、相关 controller/plugin/contracts 在执行前后校验；期间其它 owner 的 USB
Python 改动单列记录，不冒充本次冻结目标的输入。`PYTHONDONTWRITEBYTECODE=1` 防止新
bytecode；快照仅排除 build 和明确的 bytecode cache。默认/安装模型均未启用控制任务，
其 actual producer 与 disabled adapter 回归不能替代上文完整 v7b 的启用 PID/LQR 证据。

两次实际完整执行均成功，原日志与 receipt 分别为
[默认](full-host-c-f407.log) / [默认身份](full-host-c-f407.json)、
[安装](full-host-c-installation.log) / [安装身份](full-host-c-installation.json)。

| 配置 | Executables | Checks | Failures | Compile-pass | Expected compile-fail | 主 Host N/A | 耗时 | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 默认 F407 | 77 | 5,509,758 | 0 | 12 | 17 | 20 | 511.72 s | 0 |
| 安装 F407 | 78 | 5,509,951 | 0 | 12 | 17 | 20 | 630.46 s | 0 |

两者均包含 emitted runner 强制执行的 storage-integrity **4/4**，编译 warning 为 0，
生成源码及 controller/plugin/contracts 前后变化均为 `[]`。安装组另外实际运行
`installation_active_integration`。主 Host 的 20 条 N/A 及存储尾部的 63 条 N/A
（9 种未被当前 profile 支持的 record 正例，每种重复 7 次；拒绝路径已执行）在
[full-host-c-summary.json](full-host-c-summary.json) 完整单列，不能把 N/A 当成正例通过。
该汇总还记录工具版本、产物 SHA-256 和两套独立日志的 hash。

初次汇总脚本误把存储尾部 N/A 纳入主 runner 的 20 条计数比较，审计断言失败；
保留 [full-host-c-summary.log](full-host-c-summary.log) 和 `capture_full_host_c_v1.py`。
按实际两个运行器的统计范围分别记录后，汇总 v2 exit 0。没有更改任何测试、期望、
完整执行日志或重新拼接部分结果。

完整复现命令是 `D:/python_software/TreeDiagram/.venv/Scripts/python.exe
docs/evidence/software_completion_20261101/control/run_full_host_c.py f407`，以及同命令
最后参数 `installation`。当前路径保留已完成证据；再次执行应先用新的版本目录正常
生成，不能覆盖已有日志。全部底层 PowerShell 命令及 source inventory 已写入 receipt。

## 36 个 owning 文件最终字节身份

以下与 v7b receipt 的实际输入逐项核对；这是可审计的工作区快照，不声称所有文件在
执行时属于干净提交。元数据已由 root 单独固定，最终代码/证据提交由 root 统一负责。

| 文件（仓库相对路径） | SHA-256 |
| --- | --- |
| `contracts/mission_functions_v1.json` | `5a53e865b8eac6a094f0cba949ff163e7772a98693d20881a6a9c903537e52bb` |
| `apps/SCG/plugins/builtin/silverstar_algorithm_control_pid/plugin.json` | `b3b99ec45ca7aec8eafc6aaf8954d60ed50309a57a604383e6999de058f12d31` |
| `apps/SCG/plugins/builtin/silverstar_algorithm_control_lqr/plugin.json` | `8cd7344d27bc1c33c2fbcfdb905bc45a536d45c3a381e98653b058ca8a9e39d4` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/plugin.json` | `4784850a31cf93453627d5b541beb2b7fbbf801718114f76d9a28bccd640d33e` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Inc/control_research.h` | `8c3b32147497e7a43c31b5636d82a38a0f94967f2cacd50d89e2e5e3e42dad7f` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Inc/estimator_task.h` | `c53877cadd1a4d7d59e58a49f070dc653ff23a8d796efbb2874eb6e1ce6ca9d3` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/control_research.c` | `f44e1a66f42cac9f88ac611d65755be185ef721085b4422d4548f5c992804663` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/control_research_runtime.c` | `b06a48929c0401217ce7aa7496c4c5752944a5b3138195e1d5c5b9a61535901b` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/estimator_task.c` | `1dbb706342cd3c972452fdd7b0a72d15bfa497f4e3597f24bae7e9e75a8772d8` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/flight_task.c` | `8875c0987db3d03186c414be7888b751102a029ba0bcad3198354f46a7c75315` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/ins_task.c` | `899fe48fa6e8e58c795fe2c2db85d4ec6b5d59316a4276344465360903118a84` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Interfaces/Inc/system_device_types.h` | `9bdaf1805b43c9148ad357bff0067c1938db8a2be26b5205dcfaa54790b86e4d` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Interfaces/Inc/system_navigation_provenance.h` | `d96d16e0e6e1ca5229e3cb0fff44f3537645259e9531329bc49d874162883f66` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Inertial/Inc/system_inertial_types.h` | `c23036d30e0f16ce9acc5051cef811c8580b8918cc7671b9d19615705ca47978` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Inertial/Src/system_inertial.c` | `b55ad2d8db2999394a9e832e26f22b20227afb83752210611762c3564ff541dd` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/Fixtures/MissionLegacy/project_mission_process.h` | `99c63d18735d5abb0e3ec7f69189a753d579a96d1c512ca2ec693ef3e8a2edef` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/Fixtures/ControlResearch/project_mission_process.h` | `03586eeccebdda6a22ee7b18194eead6ba608941a558bd006ee07c22aedf254a` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/Fixtures/ControlResearch/project_mission_process.c` | `4283ce248cbb26f49ec41a02ebd168cb4e1c7dc6f9b2a6869677d41be5a84498` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/Fixtures/ControlDisabled/project_mission_process.h` | `a726aac241b12ab550b4a38fd97f177526622e7484b737126c62a4cc06fda7c5` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/control_provenance_bus.c` | `6f11479801f7b6ab31f43bdaf7e1c7eb2b6475820b206cf9cd09d390ad527035` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/control_provenance_ins_inputs.c` | `f63b4aa15993c759474597a1f698262a2739438217239b8a9b11cc56ee9d0f56` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/control_research_unavailable_navigation.c` | `015276e915e72443d040e3ba01e36b9d080c14054c4d940ad64089da13a4f718` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/test_control_provenance.c` | `3e7ac47baef391373e13a49721da702f80c7e106831b06df382bbe2fca281ec5` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/test_control_research.c` | `91ea303f9a0fdbaa22772df0d2c5d3c0308c25a80384ed701a2059d22c40e25b` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/run_tests.ps1` | `663ef3768fcf638ec2432e4991dc498acfa83c18821cf6c27ec354396df5a5f9` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/test_optional_gnss_start.c` | `f71d88718d40a94ee7adc8954da4d4b0590b3bcae63ed154729bb84793d5dd91` |
| `apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/test_system_inertial.c` | `9d31e573406af101f6f8cef1d2d160f9546a0bacb263f24296ab1e47d152287e` |
| `apps/SCG/src/silverstar_fccg/generator/control_research.py` | `170f2064332b23f1e3d60accd71d032146c7a1d260dcf1554892fb984a179db8` |
| `apps/SCG/src/silverstar_fccg/generator/mission_process.py` | `c50a2e587e8d4c76c349dcbc8df5516b94fc0573866dcf18f2f4f99cfa301497` |
| `apps/SCG/src/silverstar_fccg/generator/render.py` | `6e362dc227c6f6138a4051de9473877eb5b0fff0ea7908d9415f108850514435` |
| `apps/SCG/src/silverstar_fccg/generator/source_graph.py` | `80a7682b7ce056d89152e0a01874ebe53d9e3a0fd3bcf60a5f98476bf6417dae` |
| `apps/SCG/src/silverstar_fccg/project/control_research.py` | `a4dc7507bae8079511673c5405611f56244885c7aba985fe09a0068d6bb6f6fe` |
| `apps/SCG/src/silverstar_fccg/project/mission_functions.py` | `2a518ec715a5dbf3f53c0ef0d35cd63b864a68fc45eca1fe938b1992d3047605` |
| `apps/SCG/src/silverstar_fccg/project/tuning_bundle.py` | `4e217ec7b74cf5f7d2c6e03a7a2f88fc5f4b25df4f81d1261a368dbfb3880b80` |
| `apps/SCG/tests/estimator_health_support.py` | `9a729eb914833f3f260a7efd53ae22cea4d646ecc5292a35ccd50e6658a08cba` |
| `apps/SCG/tests/test_control_research.py` | `3a9f22ba7cb18f2c9a075824cf4b6f25311e60296c792cbefdc4c80318a91110` |
