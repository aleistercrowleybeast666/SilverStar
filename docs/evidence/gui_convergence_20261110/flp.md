# FLP 本轮收敛与单次完整回归

本轮保留既有发布候选，源修复提交为 `284c6634`、`331c85bf`、`38076105`，
接受关闭时释放窗口树及对应事务回归提交为 `ea0f587d`。
所有接收路径仍需生产 `LogOpenCoordinator` 校验精确 `.ssdecoder` 和 Descriptor；
没有回退解码、伪造实录默认值、降低数值阈值或放宽 Qt 异常/150 秒 watchdog。

## 实际产品修复

- 可选记录 NIS 字段缺失时保持缺失，不再按必填字段索引。
- 分析结果随工程保存时仅排除临时诊断序列，保留会话中的有效结果；恢复仍校验身份。
- SF6 先确定模式和有效实现，再设置版本控件，键盘切换离线模式实际使用 revision 2。
- KF6 旧协方差元组的兼容判断回到算法 owner；通用 GUI 按插件契约消费所选结果。
- 窄窗口工程名保留“未保存”后缀，并处理 CJK/ASCII 字体省略后的实际像素越界。
- 项目根有界扫描同时识别任务 `Log` 与生成器 `Logs/Golden`，仍排除固件和第三方树。
- 接受关闭时销毁 Qt 原生窗口树，取消和 worker 延后关闭仍保留窗口。
  真实重复关闭探针中，旧实现每轮遗留 2576 个控件，三轮累计 7728 个；
  使用 Qt 接受关闭销毁机制后，每轮归零，构造时间由 4.03→6.51→9.35 s
  的增长收敛为约 3 s。没有修改全局样式或放宽时间门禁。

算法 API 源身份改变会使旧缓存保守地要求重算；没有把旧结果重新标成当前计算。
本轮没有改动物理内核，也没有将 analysis-only、历史算法或合成日志扩大为可部署能力。

## 旧失败和夹具更新

旧 1953 项报告是四个不重叠片段的汇总：1678 passed、85 failed、155 error、
32 skipped、3 interrupted，不是一次完整通过。275 个旧非通过节点的原结果保留，
逐节点分类见 `flp/old-1953-causes.json`；本轮通过不回填旧结果。

夹具调整与产品修复分开：补齐明确的合成语义上下文、设备/记录版本、协方差和
进程模型 revision；修正迁仓后的 SCG C bridge 路径；异步与保存测试改用实际
导航日志对和真实保存/关闭按钮。未尝试的诊断序列保持 NaN + invalid，只有有效行
要求有限，导航位置/速度/姿态仍要求全部有效且有限。没有用默认值补齐实录输入。

`SS_TEST_0` 是软件 Golden，不属于硬件阻断。 owning C producer 原先输出错误 profile
并缺校准身份；当前正常生成后使用真实 C codec 写出 14 条记录，经精确 package/Descriptor
打开、expected 全量比较、GUI 和 CSV/JSON 导出。没有修改生成副本或事后修补日志字节。

当前 v2 记录重放采用记录的实际 mask/R，缺当前质量窗口证据时明确不可用，质量 What-if
被拒绝。joint C 回归保留所有状态、全协方差、NIS、执行时序及独立旧完整性 helper
对照；不把这个 kernel harness 当作 revision-3 packet-policy 执行证明。

## 本轮输入身份与范围

全部软件输入是本轮正常 SCG service 生成、Host C 实际编译运行得到的合成数据。
当前 mode0 KF6/ESKF15、mode1 legacy replay、staged horizon 和 native horizon 分开：

| 输入 | 实际范围 |
| --- | --- |
| KF6 / ESKF15 current traces | 正常生成 mode0，调用实际 estimator backend |
| SF6 trace | 当前 SF6 backend 和精确 decoder |
| joint / ESKF replay | 独立正常生成 mode1，C kernel/codec 合成回归 |
| aggregation existing / imported / pure / ESKF | 正常生成或真实 CubeMX 导入的配置、严格合成配对 |
| `horizon-traces-final` | 主 Host fixture 的编译 receipt 为 mode2 / 30 ms；故障注入另列 |
| `native-horizon` | 正常生成 mode2 / 300 ms，无 timing `-D` 覆盖 |

不能把 staged 的记录重标为 native，不能把 mode1 当 mode0。
两个曾只留在 `.work/dev013_horizon01` 的唯一 C trace 源已迁到
`apps/FLP/tests/fixtures/current_{kf,eskf}_backend_trace.c`，只调整可移植 include 和私有状态名；
本轮重新编译并消费新输出。原来源与内容哈希见 `flp/fixture-migration.json`。

## 验证记录

环境为 Windows 11、Python 3.14.0、PySide6/Qt 6.10.1、pytest 9.1.1；
offscreen 使用 `QT_QPA_FONTDIR=C:/Windows/Fonts`，没有把 fallback 字体的布局当作原生结果。
新 Python 改动的 fatal Ruff `E9,F63,F7,F82` 和 diff 检查通过。
全默认 Ruff 的旧诊断不作为本轮新增门禁，也没有批量改写旧文件来消除它们。

阶段性回归：root 首批 51 passed；后续 69 passed / 762.55 s；输入/目录检查
18 passed + 1 旧图形断言失败，修正为精确缺失理由后 joint 完整数值/导出用例
1 passed / 47.47 s。这些次数不相加成一次完整结果。

第一次全量尝试的整仓身份为 `d797a19bc68ef6ad4456fe207b0041921a49533e`，
其中 `apps/FLP` 与 `38076105` 的差异为空。该次收集 1964 项，实际完成
902 passed、6 failed、1 skipped；1 项触发 150 秒门禁中断，1054 项未执行。
379 个源码与 109 个输入文件前后哈希均相同。这是失败的全量尝试，不是完整通过。
六项失败是 staged KF6 旧 helper 把首条记录当运行输出；当前真实 C 先写 timestamp=0
的初始化 x/P。修复明确校验初始化时间、operation/epoch、零状态、姿态、配置 P0 和完整 P，
然后仍要求首运行输出/首 body 为 1005000 us，全部后续数值比较保持原阈值。
中断在 Qt 全局 Fusion 样式重建，真实关闭探针证明旧窗口树累积，已从接受关闭的
生命周期修复。Windows 的超时进程退出后仍被 launcher 等待，核对 PID/argv 后只终止
该自有已超时进程；没有延长 watchdog 或继续拼接剩余节点。

恢复执行时完成了关闭生命周期的夹具收尾。原 `lifecycle10` 单批177项为
173 call passed、4 failed、15 teardown errors；不能称177项通过。
这些错误分别来自已销毁窗口的重复清理、读取已销毁的进度控件以及在已关闭窗口中重启任务。
pytest-qt 4.5 的弱引用注册不会自行识别原生销毁，因此使用限定 MainWindow 的注册 helper：
只在真实 QObject.destroyed 信号时移除该唯一注册，live 窗口仍由原机制清理。
没有修改第三方库、捕获并吞掉 Qt 异常或撤销产品销毁行为。
接受关闭的进度测试校验真实 valueChanged 记录的最终值并要求销毁；取消分支继续读取 live
控件、验证后续任务可启动。四个完整文件随后单次 **33 passed / 212.90 s**。

`ea0f587dd3364b850e5ad07e7544d0bd934dcb12` 上的独立完整 `full2` 已正常结束：
实际收集1968项，**1963 passed、5 skipped / 2827.38 s**，runner exit 0（2832.64 s）；
没有 failed、error、interrupted 或未执行项。381源码与109输入前后 SHA-256 全部相同。
五个跳过均为下述缺原始输入节点，没有软件 Golden 跳过。
旧275个非通过节点在此次完整执行中为270 passed、5 skipped；旧报告保持原始结果。
所有完整尝试保持原 runner、150 秒 watchdog 和
`--max-continuations 0`。`tests.qt_exception_probe` 只在异常发生时记录堆栈，
始终把原异常转给 pytest-qt 失败门禁，没有替换正常 Qt 回调或隐藏异常。
本次没有 Qt 异常记录，watchdog 原始日志为空。完整 JSONL 使用无损 gzip 保存，
逐字节解压回读核验；命令、环境、收据、精确跳过节点和旧275项逐节点对照见
`flp/full2-summary.json` 与 `flp/current-suite-evidence.json`。

该完整结果只归属于上述精确源码。随后针对普通首启适屏的入口修改及对应原生/生命周期
回归必须另列源码身份与范围，不能把 `full2` 重标为后续提交的完整套件。
首启适屏入口修改后的两完整文件 `test_main_window_disposal.py` 和
`test_measurement_plot_layout.py` 单次 **11 passed / 39.90 s**，runner exit 0；
运行前后 `app/application.py` SHA-256 均为
`48c47781c00fa490cb62204cd185749b2101f9742963bce2f41fa886f8ca4759`。
该次仍使用150秒 watchdog 和原 Qt 异常门禁。真实生产入口的原生多缩放检查另见
主负责人汇总的首启适屏证据，不能用 offscreen 绘图检查代替。

## 本任务测试产物清理

先盘点明确归属本轮 FLP 的20个测试根目录：21243个普通文件，234668740字节；
测试生成的嵌套 `.git` 和两个链接树不遍历、不计入该普通文件总数。
`gcf-full2` 的133022170字节、所有唯一内容、raw log、精确 decoder、归档、源夹具、
失败的 lifecycle8/9/10 树及原 horizon/header 失败复现保留。

仅删除与完整 `full2` 保留副本逐字节一致的旧再生输出：629个 PNG、311个 CSV，
合计940文件、37486196字节。每项先记录绝对作用域、SHA-256、大小、时间与文件身份；
614种唯一内容实际解压到磁盘后重新打开核验，再逐文件复核身份和内容后删除。
940个 `full2` 对应副本在删除后再次验证，0错误，不删除目录、不改权限、不跟随链接。
归档为 `D:/SilverStar_Archive/20261110/task/flp-duplicates/exact-duplicate-objects.zip`，
15894996字节，SHA-256 为
`3c4c235f90a1d754ccd0a0ca200689abe00126b3283b8ea165dbb17ce9509db4`。
源和归档同在D盘；上述删除字节是逻辑文件量，不能称为实际腾出的磁盘空间。
逐项清单、真实恢复收据、删除日志及保留范围见 `flp/cleanup/evidence-index.json`。

## 精确未完成范围

- 指定 SS0000 原始记录与精确 decoder、SS0007、SS0014 不在可读工作区中；
  共五个验收节点缺原始输入。六个旧合成 SS0000 不能代替它们。
- 曾出现 pyqtgraph `LabelItem._sizeHint` 间歇生命周期异常；独立压力探针、69 项
  阶段回归及本次1968项完整 suite 均未复现。没有单独证明该异常的根因，不能宣称
  对该 pyqtgraph 内部缺陷已有直接修复。
- 原生 GUI、统一三应用打包和硬件动作由主负责人记录。Host 数值一致、完整测试通过
  均不等于目标 WCET、实物传感器/控制链路或飞行合格。
