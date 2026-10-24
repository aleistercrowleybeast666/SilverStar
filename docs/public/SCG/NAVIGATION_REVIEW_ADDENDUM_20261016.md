# 导航验收补充：启动入口与 FLP 导出限制

导航冻结提交：`cd3fd0652a4162639a1ade55f5f1994f3b666544`。
本文件是交接补充，不改源码、模型、ELF 或已封存证据；没有因断连重跑测试。
共享工作区还包含其他任务的改动，当前 GUI 启动不等于纯净提交检出。

## 启动与可点选项目

在仓库根目录，分别用 PowerShell 窗口启动：

```powershell
Set-Location 'D:\python_software\SilverStar'
.\.venv\Scripts\python.exe .\SCG.py
```

```powershell
Set-Location 'D:\python_software\SilverStar'
.\.venv\Scripts\python.exe .\FLP.py
```

SCG：文件 → 打开项目，可只读检查
`.work/dev013_navclosure02/eskf15_0_default03/SilverStar.ssproject`，以及同级
模式 1/2 工程；算法参数中核对融合时序模式与 `gnss_recovery_enabled=0`。
这些冻结工程采用后端直接生成目录，GUI 构建动作另使用 `Flight_Controller`
文件夹契约，不能把 GUI 构建按钮当作同一已验证入口。不要保存、重生成或修改
冻结样本来演示；六配置构建结果及准确命令在主验收入口中。

FLP：打开日志时必须同时选对应的精确 `.ssdecoder`：

| 项目 | 日志（相对仓库根目录） | 精确解码包 |
| --- | --- | --- |
| ESKF 模式 0 | `.work/dev013_navclosure02/eskf15_current_default03.sslog` | `.work/dev013_navclosure02/eskf15_0_default03/NavClosure02_OriginFinal_0.ssdecoder` |
| ESKF 模式 2 | `.work/dev013_navclosure02/nl02/native_eskf150/native.sslog` | `.work/dev013_navclosure02/eskf15_2_default03/NavClosure02_OriginFinal_2.ssdecoder` |

可检查精确包匹配、ESKF_15 的 Recorded 回放、姿态/位置/速度及协方差；模式 2
还可对照显式 What-if 的 horizon=100 ms 与记录的 300 ms 区别。CPU 测试已经验证
相应打开和数值路径，未把 GUI 全部点选行为列为已自动验证。原始日志/包不可改写。

## 未解决的 FLP 导出项（必须保留在验收清单）

测试全名：

`apps/FLP/tests/test_decoder_profiles.py::test_log_open_coordinator_builds_immutable_semantics_and_none_calibration`

异常：`ValueError: export_source_unavailable:recorded`，发生在
`FlightExporter.export()` 的来源可用性检查，而不是精确包打开或 NONE 校准解析。

该样本只有事件和原始 IMU 数据，没有可用的 Recorded 导航位置解。
`ChannelResolver.Source_Get("recorded")` 因没有位置解返回不可用，导出入口无条件
拒绝。因此即使关闭图、CSV、事件等全部内容、只想导出审计清单，也会被拦截。
GUI 的导出入口也有同类预检，会显示该错误而不启动导出。

影响边界：无 Recorded 导航解的原始/审计数据导出未通过验收。不是所有日志都
无法打开，也不能据此说所有导出均失败或均正常。已验证的新导航样本精确包打开、
回放与完整协方差比对仍通过，所有导出选项没有因此自动获得通过结论。

与此前四项修复不同：此前四项是 ESKF golden 的 `[False]`/`[True]` 两项
（合成 C 生产器缺少已采用 v2 的实际时序证据），以及 KF 正常控制的 `[1]`/`[2]`
两项（历史状态指纹形状与新增 NIS 开关的覆盖）。它们修正测试生产器/历史控制，
未修改 `export/service.py` 或 `ChannelResolver` 的导出来源策略。
参见 `docs/evidence/flp_regressions_20261016/REPORT.md`；该项不属于当时的四例。

本次已用修复前 HEAD 的四个相关生产模块覆盖对照，重现同名测试、同样异常。
这支持“不是本批 GNSS/元数据新增造成”的判断；不代表这项旧问题已修复。
原始失败和对照分别保留在 `.work/dev013_navclosure02/deadline_flp_short02.log`
和 `deadline_flp_baseline01.log`。没有补造导航解、回退解码或降低断言。

## 哈希入口与未开放范围

完整清单：`docs/evidence/navigation_receipt_default_off_20261016/validation.json`
（7047 个验证产物条目、六个实际 ELF 哈希及源码条目），以及同目录 `manifest.json`。

- `sources.zip` SHA256：`a69e9aeb9ce1f13ee545f9add73d2cc807861866e3161b0432033369a9f4be0b`
- `validation.zip` SHA256：`6102c5e2ff70f43ddfe2ea23bc0d088865eba29704e2563112bcd6c957fbe422`
- 模式 2 示例日志 SHA256：`d9afa58ba5ccf1683f6bb7afac451e58949a44ac0722171d50d5639d07950a61`
- 对应解码包 SHA256：`d49bc5519acb9cf630199e7946c408f056dd69f5f1ed459ddafe76bf07b18789`

主动恢复后端、动作日志及 1/5/30/120 秒完整矩阵未完成，生成继续禁止启用。
主/MSP/ISR、WCET、完整关键合同和硬件/飞行证据未证明。上述无导航解导出项未解决。
USB 共享补丁继续不应用，等待续作后的一致交接；其 Power10 失败仍保留。
GSHC/展示任务结果不并入本导航通过范围，未操作硬件、推送、tag 或发布。
