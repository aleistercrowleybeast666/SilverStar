# SilverStar 联合外场修改报告

本轮按 FCCG → FLP → GSHC 顺序完成。当前代码基于各仓库最新实现，保留既有工作区内容。
未提交、未推送、未创建 tag/Release；只读参考固件未修改。没有实际烧录、无线或飞行验收。
精确测试数量、资源、hash 与产物快照只位于各仓库根 VALIDATION.md；本报告汇总行为和 Git 状态。

## FCCG

- 生产日志退役 SAMPLE、RAW_SENSOR、IMU_NATIVE、HW_QUAT_NATIVE，保留原 ID 空洞。
  最终正式记录清单、默认 rates、bytes/s、FLASH/静态 RAM、stack、decoder/golden SHA256
  见 [FCCG 验证](VALIDATION.md) 的“代码与正式记录”“真实生成、构建与完整测试”等表。
- 公共惯性前端与导航拆分；KF6 不再附带 Pure INS 导航状态，独立 Pure INS 选择仍保留。
  KF6 自身记录姿态、位置、速度和线加速度。日志保留 full corrected IMU、增量、GNSS/BARO
  observation 及 actual estimator operation/present/epoch，不用接收时间猜执行次序。
- GNSS Pos EN / Pos U / Vel EN / Vel U 分别判 quality、执行 update、记录 NIS/innovation。
  origin 飞前基本门禁保持严格；没有 origin 的任务仍不启用 GNSS 融合。
- recovery 要求真实 availability outage、连续一致返回和既有 inflation 尝试耗尽，才允许
  affected-group 历史 re-anchor。只修正所属 state/P block，cross covariance 清零且 SPD 检查。
  失联、质量无效、NIS 拒绝不会互相混淆，单次异常不能触发重锚。
- Landing 使用时间覆盖率、still 占比、最大连续 bad 和末尾近期合格条件，原物理门限不变。
  短暂 baro miss 按 freshness 等待；正常调度 WAIT/ACCEPTED 不生成高频事件洪泛。
- Logger 按实际 HWM 调整小幅容量，并修复非二次幂队列在计数回绕后的索引错误。
  正常 jitter 无 drop/CRC/gap；有限 overload 保持可观测 drop 与完整 framing。
- 真实生成 SS_TEST_19 / SS_TEST_20 与 decoder；Release、Debug、Host、stack/memory、
  architecture、artifact、Power-of-ten 和完整 Python suite 已验收。生成产物位于本仓库 tests。

正式输入说明见 [Field log / replay contract](docs/FIELD_LOG_REPLAY_CONTRACT.md)。

## FLP

- 正式新输入来自 FCCG decoder；faithful replay 读取实际增量和 estimator 操作序列，
  GNSS/Barometer 共用有界 fixed-lag 历史状态引擎，重放后回到 present。
- corrected IMU 独立用于 mechanization verification，逐区间核对 dt、增量及首个差异，
  不重复校准。操作重复/缺失、epoch reset、无可靠初始 P 等都显式处理。
- Recorded / Replay / What-if 共享 Analysis Source；图表、轨迹、姿态、表格、诊断和导出
  使用同一结果源。保存工程恢复精确时间范围、结果编号和重算配置；显式 Compare 保留。
- GNSS 四组 quality/update/innovation/NIS/R/recovery 与 landing recorded/recomputed 诊断可读，
  重锚断点不连接成长线，离线 landing 重算明确为近似。
- 五页共用双柄时间条和 preset / Start / End / Duration。默认前一段时间，长任务可看 Full；
  显示保留峰值和缺测断点，统计与 CSV 不以绘图降采样替代原始输入。
- PNG 默认按完整范围分页并分类，GIF 使用当前范围或 Full、固定帧率、匀速压缩、精确源终点
  与末尾保持，提供实际帧进度/取消/元信息。没有事件慢放。
- 完整 pytest、Ruff、双语主题、最小窗口、高 DPI、工程恢复与实际 C golden 对照已通过。
  有限 golden 仍不足以宣称所有日志 EXACT，产品保持 APPROXIMATE，详见 FLP 根 VALIDATION.md。

FLP 文档：`D:/python_software/SilverStar_FLP/docs/Field_Log_Replay.md`。

## GSHC

- AIR/GSP wire、telemetry、命令/ACK、串口与握手保持不变，不新增 frame 或 decoder 依赖。
- PNG 分页与 GIF 源时长默认相同，可选预设、Custom、Full；没有加入复杂离线双柄浏览器。
  已有实时滚动窗口与有界缓存保持原有行为，输出默认时长不是任务最大长度。
- PNG 按类别进入 Position / Velocity / Attitude / Sensors / Diagnostics；文件名包含绝对
  任务时间区间与语言后缀。完整处理后 TXT、摘要及 manifest 保留在当前独立输出目录。
- GIF/ 中保存动画、时间 JSON 和帧目录。整个所选源范围按一个恒定时间比例播放，超长范围
  压缩到 motion 上限，再额外末尾保持。实际编码保留所有 hold 帧，厘秒量化不累积时长漂移。
- 绘图和编码逐帧进度/取消；编码逐幅处理，避免一次装入所有图像。取消只清理当前新输出。
- 验证覆盖时长边界、真实分页/编码/末尾帧、取消与目录；既有 protocol/Golden、telemetry、
  command、ACK、serial、GUI、touch、高 DPI、docs、headless 与打包结果见 GSHC 根 VALIDATION.md。

GSHC 文档：`D:/python_software/SilverStar_GSHC/docs/TIME_EXPORT.md`。

## Existing Time Synchronization vs Fixed-Lag Replay

既有时间链为 sensor native/receive → provider → adapter → sensor hub → SystemTime
统一 MCU/estimator timestamp → estimator → SSLOG。时间同步处理坐标转换、offset/wrap/
MCU mission 时间关系；它不保存过去的滤波状态，也不等于延迟量测融合。

当前 JY901B 没有可信 native sample epoch，采用 receive - configured baro delay。
未来可信 native 时间通过原 time-sync 转换后直接使用，不能再减同一段 configured delay。
NEO-M9N 当前以 MCU receive epoch 接入该链，iTOW 本身不授权把历史量测直接更新当前状态。

共同 fixed-lag 引擎恢复历史 x/P/内部状态，在 measurement timestamp update，再按量测时间
重放后续 IMU/GNSS/BARO 到 present；零延迟保留 fast path。本轮补齐 actual-operation 日志、
分组重锚和 FLP 重現，没有另建平行时钟。仅改 timestamp 后在 current x/P 上 update 的负例
不能通过 delayed BARO 与准时 reference 一致性检验。

## Cross-repository validation

FCCG generated project → 真实 C SSLOG codec/descriptor → `.ssdecoder` → FLP 严格解析 →
recorded operation replay → C golden 对照已通过。常规、位置/速度/气压不同 delay、长 outage
公里漂移重锚均比较 x/P/q 和执行结果；独立 mechanization 也通过。精确误差、样本数量、
SHA256 仅记录在 FCCG/FLP 根 VALIDATION.md。

仍未验收真实外场传感器、SD 卡最坏时序、实际串口/无线/GPU/触屏硬件。Host 调度模型不能
替代目标时序保证。未提供的历史真实日志不按旧格式强行兼容或伪造通过。

## 现有 GUI 边界

FCCG 既有最小窗口为 1080×700，请求 1000×700 会被最小尺寸约束扩展；本轮未修改该布局，
不将此项写成 1000×700 通过。FLP/GSHC 新控件在该尺寸和高 DPI 下已验证。

## Git 最终状态

三个仓库 HEAD 未移动。修改全部保留在工作区，无 commit SHA、push 或 tag。
以下是最终 `git status --short`，M 表示修改，?? 表示本轮新增未跟踪文件；验证临时输出保持忽略。

### SilverStar_FCCG

HEAD before: `891371dac10ba79c5daa4d4b7ab5fd322355c1d2`  
HEAD after: `891371dac10ba79c5daa4d4b7ab5fd322355c1d2`  
Branch before/after: `main`  
Commit: 未提交

```text
 M VALIDATION.md
 M docs/KF6_FIXED_LAG_REPLAY.md
 M docs/KF6_OUTAGE_RECOVERY.md
 M docs/README.md
 M plugins/builtin/reference_provenance.json
 M plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Inc/navigation_kf.h
 M plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Inc/navigation_kf_replay.h
 M plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Src/navigation_kf.c
 M plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Src/navigation_kf_replay.c
 M plugins/builtin/silverstar_algorithm_ins_coning2_sculling2/payload/Algorithm/INS/Coning2Sculling2/Inc/ins_mechanization.h
 M plugins/builtin/silverstar_algorithm_ins_coning2_sculling2/payload/Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c
 M plugins/builtin/silverstar_core_0_0_10/payload/APP/Inc/device_native_log.h
 M plugins/builtin/silverstar_core_0_0_10/payload/APP/Inc/estimator_task.h
 M plugins/builtin/silverstar_core_0_0_10/payload/APP/Inc/logger_bus.h
 M plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/device_native_log.c
 M plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/diagnostic_log.c
 M plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/estimator_task.c
 M plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/flight_task.c
 M plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/ins_task.c
 M plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/logger_bus.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Common/Inc/common_spsc_queue.h
 M plugins/builtin/silverstar_core_0_0_10/payload/Common/Src/common_spsc_queue.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Interfaces/Inc/system_gnss_if.h
 M plugins/builtin/silverstar_core_0_0_10/payload/System/Inc/system_estimator_diagnostics.h
 M plugins/builtin/silverstar_core_0_0_10/payload/System/Inc/system_flight_recovery.h
 M plugins/builtin/silverstar_core_0_0_10/payload/System/Inc/system_log_policy.h
 M plugins/builtin/silverstar_core_0_0_10/payload/System/Src/system_estimator_diagnostics.c
 M plugins/builtin/silverstar_core_0_0_10/payload/System/Src/system_gnss_quality.c
 M plugins/builtin/silverstar_core_0_0_10/payload/System/Src/system_log_policy.c
 M plugins/builtin/silverstar_core_0_0_10/payload/System/User/system_user_config.h
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/generate_golden_sample.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/storage_integrity/test_logger_storage.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/storage_integrity/test_sparse_preflight.h
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/storage_integrity/test_storage_integrity.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_device_native_log.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_flight_recovery.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_lifecycle_logging.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_logger.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_navigation_kf_replay.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_sensor_quality.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Target/storage_integrity.c
 M plugins/builtin/silverstar_core_0_0_10/payload/Tools/check_architecture.ps1
 M plugins/builtin/silverstar_core_0_0_10/payload/Tools/check_firmware_artifact.ps1
 M plugins/builtin/silverstar_core_0_0_10/payload/Tools/validate_sslog_record_catalog.py
 M plugins/builtin/silverstar_core_0_0_10/templates/generated/project_log_config.c
 M plugins/builtin/silverstar_core_0_0_10/templates/generated/project_semantics.json
 M plugins/builtin/silverstar_flight_logic_cycle_reference/payload/FlightLogic/FlightCycle/Src/silverstar_flight_recovery.c
 M plugins/builtin/silverstar_flight_logic_landing_baro_imu_window/payload/FlightLogic/Landing/BarometerImuWindow/Inc/flight_landing.h
 M plugins/builtin/silverstar_flight_logic_landing_baro_imu_window/payload/FlightLogic/Landing/BarometerImuWindow/Src/flight_landing.c
 M plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/Inc/sslog_protocol.h
 M plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/Inc/sslog_records.h
 M plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/Src/sslog_records.c
 M plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/schema/sslog_parser_metadata.json
 M plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/schema/sslog_record_catalog.schema.json
 M plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/schema/sslog_schema.json
 M src/silverstar_fccg/generator/render.py
 M src/silverstar_fccg/project/logging.py
 M src/silverstar_fccg/project/validation.py
 M tests/fixtures/estimator_replay_trace.c
 M tests/replay_compliance_support.py
 M tests/test_compliance_refactor.py
 M tests/test_device_capability_architecture.py
 M tests/test_generation_feature_completion.py
 M tests/test_gui_smoke.py
 M tests/test_internal_platform_refactor.py
 M tests/test_logging_cadence_progress.py
 M tests/test_optional_protocols.py
 M tests/test_prompt_acceptance.py
 M tests/test_service_gui.py
 M tests/test_storage_integrity.py
 M tools/compare_reference_project.py
 M tools/import_reference_components.py
 M tools/reference_overlays/generate_golden_sample.c
 M tools/reference_overlays/sslog_fccg_metadata.json
?? JOINT_FIELD_REWORK.md
?? docs/FIELD_LOG_REPLAY_CONTRACT.md
?? docs/JOINT_FIELD_REWORK.md
?? tests/fixtures/barometer_operation_timing.c
?? tests/fixtures/inertial_frontend.c
?? tests/fixtures/joint_navigation_golden.c
?? tests/fixtures/navigation_recovery_trace.json
?? tests/joint_navigation_support.py
?? tests/test_inertial_frontend.py
?? tests/test_joint_navigation_golden.py
?? tests/test_landing_snapshot_time.py
```

### SilverStar_FLP

HEAD before: `26abf3033f92b1dac7b607ae722eefff2ecee9bc`  
HEAD after: `26abf3033f92b1dac7b607ae722eefff2ecee9bc`  
Branch before/after: `main`  
Commit: 未提交

```text
 M README.md
 M VALIDATION.md
 M docs/GUI_STYLE_GUIDE.md
 M docs/Project_Format.md
 M docs/Replay.md
 M src/silverstar_flp/analysis/recovery.py
 M src/silverstar_flp/core/analysis_source.py
 M src/silverstar_flp/core/trajectory.py
 M src/silverstar_flp/decoder_profiles/semantic_adapter.py
 M src/silverstar_flp/export/service.py
 M src/silverstar_flp/i18n/en_US.json
 M src/silverstar_flp/i18n/zh_CN.json
 M src/silverstar_flp/plugins/algorithms/kf6/field_analysis.py
 M src/silverstar_flp/plugins/algorithms/kf6/filter.py
 M src/silverstar_flp/plugins/algorithms/kf6/plugin.py
 M src/silverstar_flp/ui/main_window.py
 M src/silverstar_flp/ui/pages/charts.py
 M src/silverstar_flp/ui/pages/data_explorer.py
 M src/silverstar_flp/ui/pages/export_settings.py
 M src/silverstar_flp/ui/pages/replay.py
 M src/silverstar_flp/ui/pages/state_estimation.py
 M tests/fixtures/parameter_contracts/kf6_fccg_1_2.json
 M tests/fixtures/parameter_contracts/synthetic_navigation_catalog.json
 M tests/fixtures/parameter_contracts/synthetic_navigation_semantics.json
 M tests/synthetic_parameter_navigation.py
 M tests/test_actual_parameters.py
 M tests/test_comparison_sampling_gui.py
 M tests/test_decoder_profiles.py
 M tests/test_display_quality.py
 M tests/test_estimator_visualization.py
 M tests/test_flight_state_pages.py
 M tests/test_gui_smoke.py
 M tests/test_kf6_field_analysis.py
 M tests/test_offline_diagnostics.py
 M tests/test_project_export.py
 M tests/test_replay_page.py
?? docs/Field_Log_Replay.md
?? src/silverstar_flp/analysis/landing_window.py
?? src/silverstar_flp/core/time_range.py
?? src/silverstar_flp/export/ranges.py
?? src/silverstar_flp/plugins/algorithms/kf6/fixed_lag.py
?? src/silverstar_flp/plugins/algorithms/kf6/measurement_time.py
?? src/silverstar_flp/plugins/algorithms/kf6/mechanization_verification.py
?? src/silverstar_flp/ui/navigation_diagnostics.py
?? src/silverstar_flp/ui/time_range.py
?? tests/test_fixed_lag_contract.py
?? tests/test_joint_c_golden.py
?? tests/test_joint_gui_state.py
?? tests/test_joint_ranges.py
?? tests/test_landing_time_window.py
```

### SilverStar_GSHC

HEAD before: `62656da1fa035bff344165c8857a932e644ddbae`  
HEAD after: `62656da1fa035bff344165c8857a932e644ddbae`  
Branch before/after: `main`  
Commit: 未提交

```text
 M README.md
 M VALIDATION.md
 M app.py
 M docs/CURRENT_PROGRESS.md
 M docs/GUI_STYLE_GUIDE.md
 M docs/README.md
 M processing/flight_log_processor.py
 M processing/flight_plotter.py
 M services/i18n.py
 M services/preferences.py
 M tests/test_export_features.py
 M tests/test_packet_loss.py
 M ui/main_window.py
?? docs/TIME_EXPORT.md
?? processing/time_ranges.py
?? tests/test_time_exports.py
```
