# 2026-10-08 实际 TF 文件与 FLP 离线验收

用户报告日志已原位替换后，从既有输入位置只读取新 `D:\stm32_project\missions.zip`，验收实际任务 `000044`、`000045`。两份日志的严格解码、snapshot 身份、已记录导航输入连续性，以及同一原生 Windows GUI 进程内的分析、保存、全部 run 重开均通过。**这关闭的是实际文件与软件持久化验收；此前的 logger 停收拒绝身份、空口完整性、启动期约 94.3 ms 间隔归因仍为 NOT PROVEN。** 本阶段没有串口、DAP、复位、烧录或飞控命令。

## 身份与输入保护

本阶段开始 HEAD 为 `684026533bc779f795c5ca5e19d20150394efa19`，分支 `fix/nightly-user-ready-20261003`。应用源码仍是 `cac7bd29bf6f6aec5297715ea14893b4b7684953` 所验证的内容；提交前逐文件比对前次 2233 个应用文件和三个 `work_*_20261006` 用户输入。此次不修改应用、算法、固件、四档配置或门禁，也不重复前次全套 ARM/Host/GUI 长测试。

原 ZIP 为 54,152,267 B，修改时间 `2026-10-08T05:06:14Z`，SHA-256 `6a71fed719424e392c7335dec18af46d74cb840f38147c9f64e4dc9b18c06381`。两任务各取 `flight.sslog`、`manifest` 和 `snap00.0` 至 `snap07.0`，共 20 个成员；解压读取同时验证所选成员 ZIP CRC，保存逐成员长度与 SHA-256。原 ZIP 未修改；不扫描其他成员，不使用旧 `000041` 代替本次输入。ZIP 内成员日期均为 1980，不能据此推断采集 UTC。

精确 decoder 为 `.work/bench08c_f407/KF6_Static_20261008_f045d8c.ssdecoder`，144321 B，SHA-256 `46b449244dcfde73baa5faaa795ac496d34f097bd095824959f53210067fafe2`。两次均经生产 `LogOpenCoordinator` 得到 `exact_generation_profile`，没有 fallback 解码。Descriptor 的 catalog/semantics/generation 三组 128-bit 值依次为 `7af595f2376c22dc57cd63a34340d685`、`3ccbafd3475a4ed8ebaa343307447651`、`c449dcc18ba6e22774fb32038152c810`。包名、包内历史 commit、GUI 版本标签以及日志头 `0.1.0.0/SILV0100` 都不单独证明实际编译源码；实际源码/BIN/读回关系沿用[本次台架记录](STATIC_BENCH_ACCEPTANCE_20261008.md)和[复查记录](STATIC_BENCH_REPEAT_20261008.md)。

## 实际文件结果

| 项目 | 000044 | 000045 |
| --- | --- | --- |
| `flight.sslog` 字节数 | 885023 | 878123 |
| SHA-256 | `c5f123ccc6b0390b869412f6e0a09d834999f8be621b876f43298bb5028a1fb2` | `b9b6244f0103b02d98e3389c10661043fe7f22aa84f701bd456ea255e425308f` |
| 记录数 / 解码数 | 10227 / 10227 | 10166 / 10166 |
| CRC、长度、未知类型/版本、解码、resync、序号缺口、尾部损坏 | 全部 0；header CRC 正确 | 全部 0；header CRC 正确 |
| manifest / 8 个 SSOB 对象 | 身份、长度、CRC 正确 | 身份、长度、CRC 正确 |
| SSMS 6 个 section 的 generation / FNV 链 | 全部匹配 | 全部匹配 |
| Snapshot ↔ SYSTEM_CONFIG / 日志身份 / 校准 | 匹配 | 匹配 |
| START / LANDING，MCU us | 258315528 / 272317722 | 30170521 / 44174724 |
| 最终 snapshot，MCU us | 273319666 | 45176640 |
| 最终状态 | LANDED、storage valid、logger fault 0 | 相同 |

最终 snapshot 分别在记录的 LANDING 后 1,001,944 / 1,001,916 us。其 deploy/landing 动作结果为成功，start blocking/warning/storage unhealthy 为零。它与前次板上收尾一致，但不包含被拒绝 push 的调用身份，也不独立证明所有 I/O 尝试成功。板上 serialized 记录数与实际文件记录数、written bytes 与文件大小相符；bus accepted 计数的范围不同，不能直接当作文件总记录数。

两任务各有一个与记录 START 同时刻的 INITIAL_STATE，quaternion 与已 READY 的 ALIGNMENT_RESULT 及首条 ESTIMATOR 一致，P0 与首条协方差一致且有限正值。仅 barometer origin 有效，GNSS sample 为 0；起始气压高度采用 START 的 INITIAL_STATE，不能用先前 ALIGNMENT_RESULT 尚未填充的零值覆盖。OneFace READY 也不证明六面校准、绝对航向或物理安装准确。

## 导航输入、时间与遥测边界

| 连续性审计 | 000044 | 000045 |
| --- | --- | --- |
| IMU_CORRECTED | 2801 条，sequence 51590–54390 | 2805 条，5951–8755 |
| INERTIAL_INCREMENT | 1399 条，sequence 1–1399 | 1401 条，1–1401 |
| ESTIMATOR_STEP | 1399 条，source_sequence 1–1399 | 1401 条，1–1401 |
| IMU 时间间隔范围，us | 2996–7014 | 2988–7004 |
| 增量/step 时间间隔范围，us | 7997–12003 | 7995–12004 |

以上三个流各自序号增量均为 1，时间戳严格递增。增量与 step 的 `(sequence, interval_end)` 一一对应，相邻增量 `next.start - previous.end` 全为 0；replay epoch 均为 2，ESTIMATOR prediction queue overflow 和 STATS IMU/logger queue overflow 均为 0。operation_sequence 还包含量测操作，step 中有 1/2 的差值，不应误报为惯性增量丢失。间隔有实际抖动，不宣称每周期精确 5/10 ms；这些记录也不能回溯 START 前启动最大间隔或证明 WCET。

两任务各有 350 条 GNSS_NATIVE，定位与速度可用数均为 0，GNSS 融合量测为 0；无外部位置真值，导航精度未验收。GUI 保留未定位和分析末端“融合超时 / 导航不可信”提示。飞行页标明预计着陆点，默认曲线显示受该分析边界约束；全日志连续性另用全部真实记录检查，不能把显示裁剪当成原始记录缺失或据图宣称飞行精度。

两任务各有 14 条 TELEMETRY_DIAG。000044 的 transmit_error_count 为 44301→46804，000045 为 8727→11262；这是记录时窗内的适配器聚合计数，不等同于前次 live SWD 的 preSTART→final 全窗口差值。receive_error_count 分别为 1343→1402、160→216；[SX1281 适配器](../apps/SCG/plugins/builtin/silverstar_device_telemetry_sx1281/payload/Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c)将 `rx_timeout + rx_error + rx_dropped` 纳入此字段，不能与原始 `LoraStats.rx_error=0` 混同。integrity_error_count 为 0，receive_packet_count 保持 5；online 由 1 变 0，只能按接收活跃性定义解释，不能据此证明发射失败。TF 不记录地面端实际收全情况；原日志、AIR 收到的帧和不同统计窗口需分别看待。

已接受记录和导航输入连续性为 PASS。关闭后拒绝的 1/2 次调用是否对应应写记录、具体调用者/类型、空口遗漏比例、启动最大间隔原因仍为 NOT PROVEN，不由本次零 CRC/序号缺口覆盖。

## 原生 GUI 与持久化

采用既有 `apps/FLP/.venv/Scripts/python.exe`：Python 3.14.0、NumPy 2.4.1、PySide6/Qt 6.10.1，平台强制 `windows`，语言 `zh_CN`。独立 QSettings、路径偏好、decoder cache、可信插件目录置于 `.work`，避免用户偏好污染。调用真实窗口入口和 worker，在一个进程顺序执行两个任务；不是手工菜单/文件对话框全覆盖，也不是 offscreen。

每个任务创建两个 KF6 run：Recorded Configuration + recorded inertial increment；显式 What-if + corrected IMU、`gravity_mps2=9.81`。这只验证短实际输入和多 run 保存，不修改 recorded 参数或算法；两 run 的 fidelity 均如实保留 **APPROXIMATE**，不宣称 MCU 位级复现。先以 recorded 为主、重算为副，再交换主副，保存完整数据与结果，程序读回并通过实际 GUI 重开。重开期间禁止算法自动执行作为审计钩子。

两工程各恢复全部两个 result/source/run identity，参数、fidelity、provenance、warnings、missing inputs、诊断、全部 channel 的 dtype/shape/时间戳/值/valid/metadata 与保存前一致，数组 SHA-256 一致。保存后的主源为 `replay:kf6:recomputed:1`，副源为 `recorded:kf6`；位置/速度/四元数/协方差/NIS 曲线数分别为 6/6/8/6/1，重开前后相同。两任务各保存并目视核对概览、飞行、状态估计三张原生截图；缺失的次源量测曲线继续明确提示。此次原生 GUI Qt message 列表为空，未发生原生崩溃；历史 Qt/Shiboken 原生 abort 的未归因 FAIL 不被本次短日志 PASS 消除。

保存与重开工作产物保留在 `.work/flp08tf/p44_v2/mission44.ssflp`、`.work/flp08tf/p45_v2/mission45.ssflp` 及各自 `.artifacts` 目录，不覆盖用户工程。

## 失败、回归与可复现命令

初次 GUI 使用仓库根 `.venv` 的 NumPy 2.4.0，现有安全门禁拒绝重算，未生成 run，exit1；不是 Qt 原生崩溃。初始 harness 的 DONE/PASS 文案并非 run 成功依据，后续真实断言已确认失败，原脚本与日志均保留。正确环境再执行完整两任务 GUI，exit0。

小型回归首次 38 项在 pytest 专用临时目录权限处报错，exit1；正常继承目录插件复跑为 17 PASS/21 fixture ERROR（应用环境无 qtbot）；显式加载已安装插件与自动发现重复的一次在收集前失败，exit1。最终运行仅复用根 `.venv` 中已存在的 pytest-qt，保持应用 NumPy/Qt，保留全部失败证据；没有安装、更新、改 ACL、改沙盒或弱化测试。

最终同一原生 Windows 进程完整运行 **38 PASS / 0 FAIL / 0 ERROR，151.88 s，exit0**，见[证据清单](evidence/static_log_file_20261008/manifest.json)。涵盖真实阶段进度、GUI 发布后完成、缺失/损坏缓存严格重读、取消/关闭、不允许重叠保存/打开/导入、慢数组写完成/取消/关闭、提交前故障保留旧工程、提交后取消语义、主副身份/兼容性及选组恢复。这是 tiny fixture 回归，不能说故障注入是在实际 TF/MCU 上执行；不是把前面的部分 PASS 拼成完整运行。

本机已执行的主命令（日志保留完整输出与 exit）：

```powershell
.venv/Scripts/python.exe .work/flp08tf/inspect_logs.py
.venv/Scripts/python.exe .work/flp08tf/audit_sidecars.py 44
.venv/Scripts/python.exe .work/flp08tf/audit_sidecars.py 45
apps/FLP/.venv/Scripts/python.exe -X faulthandler .work/flp08tf/gui_roundtrip_v2.py
apps/FLP/.venv/Scripts/python.exe .work/flp08tf/continuity_audit.py
apps/FLP/.venv/Scripts/python.exe .work/flp08tf/initial_state_audit.py
apps/FLP/.venv/Scripts/python.exe -X faulthandler .work/flp08tf/focused_regressions_v4.py
```

输入提取和 GUI/pytest harness 会拒绝重用已有工作目录；不要删掉本次证据来重跑。复现时将脚本置于同级新 `.work` 子目录，复制核对过的 20 个输入，采用新 project/cache/basetemp 目录；路径插件原文随证据保存。未运行无关 ZIP 全扫描、长日志/ESKF15 重算、已完成的完整软件套件或任何硬件动作。

## 后续最小工作

文件交付与 FLP 持久化已完成，不需要为了补 TF 再自动 START。用户已确认断电插回 TF 后上电、保持 +Y、全部执行器断开、串口/DAP 保留的准备状态；准备完成不扩大本阶段离线范围。当前没有已证实而需固件修复的根因。需要固件或实机变动时，先明确一个未证明的问题、调用/计时观测点、最小修改及有界正常/故障测试，交回父任务协调；等待用户回来再做需要物理移动或校准的动作。算法数学、四档队列、原故障行为及已有未验证硬件边界保持不变。
