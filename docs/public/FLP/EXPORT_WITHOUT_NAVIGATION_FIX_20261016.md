# FLP 无导航解导出修复 — 2026-10-16

这是导航冻结提交 `cd3fd065` 之后的独立 FLP 小修复。导航源码、模型、ELF、
既有导航证据及主动恢复禁用状态均未改变；v0.1.2 发布和 tag 不变。

## 行为

- 没有 Recorded 导航位置解时，通用“飞控记录”仍可导出审计清单、事件、
  解析诊断、概览和已有原始通道 CSV；不需要补造位置或运行算法。
- 缺少有效、有限的位置样本时，水平/三维轨迹及飞行 GIF 明确跳过，记录
  `navigation_solution_unavailable`，不调用对应绘制器，也不生成空轨迹代替。
- 无导航解的通用来源所需三个导航曲线同样跳过，原始数据导出不被全局阻断。
- GUI 的导出来源列表在没有导航来源时提供通用“飞控记录”；GUI 和后端共用
  同一个来源快照判定。它不会改变主分析来源，也不把导航来源标为可用。
- 显式选择不存在、已删除或不可用的具体 Recorded/Replay 来源继续报错；
  不借用别的算法或历史结果。需要原始数据时明确选择通用“飞控记录”。
- 审计清单追加 `active_source_available` 与 `shared_recorded_data_only`，说明
  通用原始数据导出并不等于已有 Recorded 导航解。原有来源标识保留。

没有修改 `LogOpenCoordinator`、精确 Descriptor/`.ssdecoder` 检查、解码器、
算法、导航来源解析器或原始数据。异常来源也在创建输出目录之前拒绝。

## 实际证据

原失败测试保持不变：
`test_decoder_profiles.py::test_log_open_coordinator_builds_immutable_semantics_and_none_calibration`。
它的精确包打开和 NONE 校准本来已成功，旧实现随后在导出阶段被全局来源门禁阻断。

| 执行 | 结果 | 范围 |
| --- | --- | --- |
| `prefault01` | 8 失败、1 通过 | 原失败及新增导出/GUI/不可用来源反例 |
| `postfix01` | 54 通过、1 失败 | 暴露缺少三个导航曲线仍被作为失败的路径，随后修正为跳过 |
| `final04` | **100 通过，无跳过** | 下列七个文件在同一次执行中完成 |

最终命令的测试文件：`test_export_without_navigation.py`、
`test_decoder_profiles.py`、`test_analysis_source.py`、`test_primary_source_policy.py`、
`test_gnss_export_dependencies.py`、`test_export_theme.py`、`test_project_export.py`。
不是全 FLP 测试套件通过声明。

新增用例覆盖真实精确包打开后的仅审计/原始 CSV、缺失轨迹绘制器不被调用、
不可用具体来源拒绝且不创建目录、GUI/后端一致、GUI 原始来源选项不改主来源、
空/全无效位置不生成轨迹，以及正常可用 Recorded 来源身份不变。
日志和解码包在用例结束时逐字节 SHA256 不变。

整文件 AST 审查确认：导出器只修改 `export`、`_Manifest_Write` 并新增来源快照
方法；GUI 只修改两个导出方法。其他 AST 节点完全不变。冻结导航清单的 60 个
文件逐项哈希不变。新增测试 Ruff 检查通过；原有大文件的既存格式诊断没有被
隐藏或通过整文件重排处理。

## 验收点选

从仓库根目录运行 `.\.venv\Scripts\python.exe .\FLP.py`。
打开没有导航解、但含有效原始记录的日志时仍须选精确解码包。导出界面选择
“飞控记录”，先只选审计/CSV；应得到真实原始通道与审计清单。再选轨迹/GIF，
应看到缺失产品的跳过原因，不能出现补造轨迹。选择已删除具体回放来源应拒绝。
有导航解的正常来源导出继续保留其来源身份。

机器清单和哈希位于
`docs/evidence/flp_export_boundary_20261016/manifest.json`；修复前后日志、命令、
源码和输出清单由其索引。`.work/dev013_flp_export01` 保留完整本地测试产物，
没有清理授权。旧导航报告中的导出失败是冻结时点的历史记录，此增量报告说明
该问题的后续修复；主动恢复及其四时长矩阵仍未完成、保持关闭。
