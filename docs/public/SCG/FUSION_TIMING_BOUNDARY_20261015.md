# 融合时间策略声明与 FLP 边界（2026-10-15）

本批交付独立的声明契约和 FLP 拒绝边界。**尚未实现或启用固件 current 模式**，没有新增可选参数或控件，也没有修改 estimator 版本、默认延迟、数值内核、日志布局或历史 fixture。本批不是 MCU/飞行验证。

机器可读契约为 `contracts/navigation_fusion_timing_v1.json`，放在精确匹配 `.ssdecoder` 的 `metadata_declarations.fusion_timing`。该声明与 KF6 process-model revision、GNSS quality revision 和 ESKF algorithm revision 各自独立。

| 字段 | current（mode 0） | delayed replay（mode 1） |
|---|---|---|
| `schema_id` / `revision` | `silverstar.navigation-fusion-timing/1` / 1 | 相同 |
| `component` | KF6 或 ESKF15 的完整 estimator component ID | 相同 |
| `source_time` | `resolved_measurement_epoch` | 相同 |
| `application_time` | `estimator_present` | `legacy_algorithm_epoch` |
| `evaluation_time` | `estimator_present` | 相同 |
| `output_state_time` / `output_covariance_time` | `estimator_present` | 相同 |
| `replays_history` | false | true |

source time 指通用 SystemTime 对 sample/receive/delay 解析的 epoch，不能因选择 current 就改成 now。application time 是本次更新使用的 state/P 所处时刻；evaluation time 是外层处理与诊断的 present 时刻。未来 current 实现应只更新 present state/P。`legacy_algorithm_epoch` 保留既有算法的实际应用规则：KF6 在 untrusted 且 delay=0 时应用于 present，其余 KF6 及 ESKF15 使用原有 resolved epoch，再传播到 present。因此不能承诺所有旧输入的 application 与 source 相等，也不能为匹配声明改变旧输出。延迟为零与 current 模式不等价。模式 2（延迟融合和输出预测器）没有实现，不属于本契约可选值。

FLP 在 package 导入时拒绝字段缺失、多余字段、错误类型、未知 schema/revision/mode、错误 owner、互相矛盾的时刻或 history 声明。SF6/Pure INS 不能拥有这个声明。已知旧 estimator 版本也不能宣称 mode 0。

有效 current 声明只允许按精确 Descriptor/package 查看原始数据，不授予数值重演能力。KF6 和 ESKF15 availability 都返回 `fusion_timing_current_replay_not_implemented`，Recorded Configuration 和 What-if 均不能绕过。声明 mode 1 也不证明任意未知固件版本的实现身份；未知身份返回 `fusion_timing_identity_unproven`。

旧包缺失此声明时，仅以下已知 component version 可解释为原有 replay 行为：KF6 `0.1.0`、`0.2.0`、`0.2.1`；ESKF15 `0.1.0`、`0.1.1`。这只是版本语义解释，不会向旧包、日志或 Recorded Configuration 补写 mode 参数。未知/缺失 version 不能继承当前默认值。没有 KF6/ESKF15 owner 的输入保留原有其他算法准入。没有 package semantic context 的旧测试/What-if 输入仍由原有准入处理，本批不会因此声称它记录了某个 timing mode。

缺失新声明的旧包不新增准入限制：多 estimator 的旧参数包仍可读取原始数据，时序身份保持未知；数值回放继续受原有 process-model revision、参数与记录契约约束，不因此宣称精确时序。只有显式声明新时序契约时才执行新的 owner 唯一性和数值回放拒绝规则。最初实现过早拒绝多 estimator 旧包造成导入回归，修复与失败记录均保留，未改旧包或 golden。

本批独立 metadata 声明不接入未来的 actual `fusion_timing_mode`。带该未知 actual 参数的包继续由现有 parameter schema 拒绝，避免原始数据界面、Recorded Configuration 和可编辑参数对同一字段产生不一致解释。

## 后续完整激活的接入清单

1. **配置、身份和生成**：两个 owning estimator `plugin.json` 增加 `fusion_timing_mode` int32，0=current、1=replay，default/legacy_default=1；SF6/Pure INS 不增加。更新组件版本与声明身份；由 `generator/render.py::_LogMetadataDeclarations_Get` 从 `AlgorithmParameters_Resolve` 绑定实际 mode，而非复制静态默认。检查 `project/algorithm_parameters.py` 的严格 resolve、header 与 mission snapshot 96-entry 上限。旧工程保存/恢复与旧 manifest provenance 保持明确兼容边界。
2. **KF6 owning 路径**：`navigation_kf_replay.c/.h` 和 core `APP/Src/estimator_task.c` 分离 source 与 application。current 不恢复 checkpoint、不插入历史事件、不重放；保持 `NavigationReplay_ReceiveTrack` 的一次接收证据、physical/age/duplicate/source/epoch 检查、组更新/恢复顺序和失败事务。legacy 的 untrusted zero-delay present 特例保持在 legacy 分支。
3. **ESKF15 owning 路径**：`navigation_eskf_backend.c`、`navigation_eskf_replay.c/.h` 与配置头显式分支。current 保留 source/receive 的合法性和去重，在 present 的完整 state/P 上调用更新；杆臂角速度取实际 application boundary 的 body 输入。不能把历史时间改为 present 后继续调用 replay 以冒充 current。没有实际移除 history arrays/symbols 前不声称 RAM 收益。
4. **日志、decoder 和运行期证据**：owning SSLOG schema、parser metadata、C record declarations、logger bus 和 backend/core 日志接入新的 `(record_type, record_version)` 或新 record，记录 source/receive/application/evaluation、mode/revision 与一次 operation 身份。不能改旧 100-byte `ESKF15_MEASUREMENT` 的字段意义或复用 reserved 字节。新声明须与 actual 参数、record revision 和运行期证据一致；不够完整时回放仍 unavailable。
5. **FLP 数值与参数闭环**：扩展 `decoder_profiles/algorithm_parameters.py` 和两算法的 firmware-only/tunable schema，验证 actual mode 与声明完全一致，保留旧 project parameter-schema identity。实现 KF6/ESKF15 current 数值路径、时间输出和 replay audit 后，才能有条件撤销本批 current 拒绝；不能靠改 availability 放行。新的 What-if mode 必须进入运行身份，不能修改 source log/package。
6. **验证后开放 UI**：用非零加速度的迟到观测反例区分 current 与 replay；覆盖 trusted/untrusted、0/550 ms、未来/过旧/重复/反序、source/epoch/calibration 切换、数值故障与队列容量；比较完整 state/P 和旧默认轨迹。运行 fresh generated 的原样 `power10-check`、相关 Host、真实 analyzer 编译、ARM 编译/link、source graph 和 linked artifact/stack 报告。关键契约、栈界限、WCET 与硬件证据未完成仍为 NOT PROVEN。只有此闭环完成，才开放 current 控件；输出预测器继续独立实施。

本批验证日志与 source hashes 位于 `.work/dev013_timing01/`。没有连接串口/DAP、烧录、修改 frozen release 或执行清理。
