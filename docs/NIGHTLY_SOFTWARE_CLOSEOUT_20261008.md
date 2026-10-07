# 本机软件收尾与仍未完成的验收（2026-10-08 夜间批次）

本次从 `fix/nightly-user-ready-20261003`、`a2617964bfdb1c062f4265776c3c15fc23e63597` 开始，保留既有 FLP `cc5fb52`、SCG `5821058` 及文档 `a261796`。源代码/测试提交为 `4b511e5`、`2716d6c`、`0a2a561`。本报告与证据的提交只增加文档及诊断附件；`source_hashes_v4.json` 和最终核对记录绑定相同应用源码。SCG/GSHC在后续FLP修复间无源码或测试变化，哈希核对将其4b511e5记录绑定最终版本；不称为重新执行全库套件。原[首发报告](RELEASE_GUI_CLOSEOUT_20261008.md)的历史失败和证据保留，不能把独立阶段通过拼成合并通过。

没有连接/操作硬件，没有生成最终外场工程，没有 push、tag、Release、烧录、串口/探针/飞控指令或关机。三个未跟踪 `work_*_20261006` 盘点文件保留。没有清理数据、改 ACL/沙盒、复制 vendor 或修改本地 memory。开始时没有观察到 Python/pytest/编译进程；应用任务列表中 `Complete logger checkpoint验证` 为 idle。17:34 UTC 再查仍为 idle，除本任务外所列 SilverStar 任务均 idle。WMI 命令行枚举被系统拒绝，不能宣称已证明所有外部进程都不会写入；测试串行执行，没有重复该 Logger 重负载验证。

17:51 UTC 收到执行环境短暂断连的复查要求：原120项exec session仍RUNNING，同一启动时刻的driver/子进程存在、CPU累计、日志继续更新，尚无退出JSON；没有重复启动或判为PASS。进程观察记录保留，最终结论仍以结束摘要及真实退出记录为准。

## 1. FLP：已证实的所有权缺陷与尚未归因的崩溃

修复前 pyqtgraph `PlotItem.ctrlMenu` 和 `ViewBox.menu` 没有 QObject parent，Shiboken 报告 Python ownership。原生 PlotWidget 删除后，两个原生菜单仍有效，销毁依赖后来 Python 引用释放/GC。这是可重复的生命周期缺口：新回归的 `menu.parent() is plot` 在原源码失败，修复后通过。

`ui/plot_helpers.py::_Plot_Prepare` 给菜单设置 PlotWidget parent，同时保留 `windowFlags()`，防止 Popup 变成普通子部件。4b511e5诊断仍有18个timer告警，Python栈明确显示GC发生在worker的工件JSON验证，以及测试显式worker GC中。再次盘点发现 `ui/gnss_integrity.py` 第二Y轴独立 `pg.ViewBox()` 的菜单未经过helper。新增回归在其 `parent() is quality_plot` 断言失败（1 FAIL、exit1），2716d6c将它绑定到quality_plot后，两条菜单回归2 PASS、exit0，无timer告警。没有删除测试、放宽断言、禁用GC或修改算法/Worker完成协议。

原生GUI父对象现在负责这些菜单销毁。回归保留GC启用，用DirectConnection记录destroyed的真实执行线程，检查各一次、父/菜单wrapper失效、worker GC后不再销毁；也检查主题重复准备及Popup flags。这证明具体对象的所有权和销毁合同，不能证明整个Qt对象图或历史fatal abort均已解决。

修复前合并 15 个 GUI 测试返回 exit 0，但出现大量 `QBasicTimer::start: Timers cannot be started from another thread`。记录的 Qt/Shiboken 模块+RVA离线解析到：

`QMenu::~QMenu → QWidgetAction::releaseWidget → QWidget::setParent → QWidgetPrivate::inheritStyle/setStyle_helper → QListView::doItemsLayout/updateGeometries → QBasicTimer::start`。

这是**跨线程菜单销毁/样式路径的定位证据**，不是历史 Aborted 时的崩溃 dump。只有 DLL 导出符号及位移，没有源码级 PDB，不能把最近导出名当作精确内部栈帧。最小原生前后探针也没有复现错误线程销毁：修复前菜单稍后在 GUI 引用释放时销毁，修复后在父删除时销毁。故“所有历史 Aborted 都由此缺陷造成”仍 **NOT PROVEN**；原生崩溃归因/完整问题关闭仍 **FAIL（未完成）**。

诊断干扰另记：一次在线 DbgHelp/CRT 扩展诊断停滞后被中断；加入大量 GC/QObject 观察器的批次为 13 PASS、2 FAIL、2 ERROR（等待后台保存超时），不算产品通过，也不据此认定产品根因。该观察器用默认 AutoConnection，不能用其回调线程判定真实销毁线程。普通 112 项矩阵第一次执行无结束摘要/退出码且进程已不在，标为 INTERRUPTED/NOT COMPLETED，原因未知，不能当 PASS 或已捕获的 native abort。

早期owner最小探针曾临时关闭自动GC来隔离引用释放时机，再主动worker collect并恢复GC；这些实验没有复现native abort，不属于最终验收。产品修复、最终回归及新增断言均保持GC启用，不靠该实验机制掩盖问题。

## 2. 最终软件检查

下表按实际完整执行记录核定。完整日志、命令、实际退出码、时间、版本与哈希保存在 [evidence/nightly_software_20261008](evidence/nightly_software_20261008/manifest.json)。日志中的失败、warning 和中断均保留；该证据目录用局部`.gitattributes`禁用文本换行转换，以保留manifest绑定的原始字节。

| 检查 | 状态与范围 |
| --- | --- |
| FLP 同进程 GUI+工件合并矩阵（4b511e5） | PASS：114项、exit0、469.06s；第二Y轴后续修复前的结果，不能代替最终回归 |
| FLP 原生消息诊断 GUI 批次（4b511e5） | 测试17 PASS、exit0、115.93s；仍有10次跨线程timer及8次非QThread timer告警，生命周期验收FAIL |
| FLP同进程原生诊断合并批次v2（2716d6c，较长根目录） | FAIL：117 PASS、3 FAIL、exit1、474.23s；无timer/fatal，三个260字符目标文件失败，不以短根结果替换 |
| FLP同进程原生诊断合并批次v3（2716d6c，短根目录） | PASS：同一120项、exit0、498.00s；未改测试或断言，仅basetemp较短；不代表全面长路径支持 |
| FLP最终合并v4（0a2a561，含长路径失败保护与语言回归） | PASS：同进程124项、exit0、525.41s；0 QBasicTimer、0 QtFatal；包含实际长路径故障预期错误、未提交与旧工程保护 |
| GNSS页功能/主题/语言/量测范围 | PASS：15项、exit0、7.05s；此处source未随0a2a561改变 |
| FLP实际返回/信号发布/旧worker隔离 | 4b511e5独立5 PASS、exit0、17.44s；同时纳入最终合并批次 |
| SCG 四档矩阵 | PASS：86项、exit0、306.07s；Unknown config option cache_dir warning保留 |
| GSHC M0/READY/NRF兼容回归 | PASS：53项、exit0、4.22s；Unknown config option cache_dir warning保留 |
| 修改文档本地链接 | PASS：116个链接、无缺失、exit0；最终记录doc_links_final.json |
| 历史 FLP native abort 完整根因 | FAIL / NOT PROVEN，未取得崩溃现场 dump |
| 固件 Host 全套、真实静态分析、ARM编译链接、power10-check、链接/全路径栈报告 | NOT_RUN；未修改固件 payload/模板，不生成最终外场工程；不借用历史结果 |
| 硬件/可视原生桌面/MCU时序及飞行 | NOT_RUN；GUI检查为 offscreen，没有实机动作 |

FLP 矩阵包括真实字节/阶段进度，成功仅在原子提交后 GUI 发布；慢写完成/取消/关闭，已提交后取消，磁盘满、路径逃逸、数组/manifest/记录块损坏、单次写入凭据、重开所有四算法/多个 run/主副源及有效/损坏/失配缓存。新增保存期间重复保存、打开项目、导入日志不得替换 active worker、项目或提前产生文件。均为小型合成输入，不是长实机日志或全 ESKF15 重算，也不是硬件验证。

当前菜单生命周期缺陷的具体合同和所列合并回归通过；原版本102次跨线程timer、第一处修复后18次、第二处修复后的v2/v3/v4均为0（逐条统计见qt_messages.json）。Qt font目录和offscreen OpenGL不支持消息保留；不据此称原生桌面渲染已验收。v4预期长路径错误的日志是故障注入/真实故障回归的执行证据，不能因有ERROR日志便忽略测试断言，也不能因测试PASS宣称全面长路径支持。

SCG 按源码建立四档矩阵：中文/内部标识、算法允许集、纯惯导保留、legacy/schema roundtrip、载入与配置 reconcile、源图拒绝、GUI 切换/删除/添加/恢复、保存/导入重开、各日志策略/资源。新增12种冲突（轻量/最简 × IMU/GNSS/气压/磁/电压/遥测）保留实例并拒绝源图；四档单 GNSS 仅最简拒绝。普通/估计器队列仍是 80/48、80/48、56/16、24/16；导航队列/栈未动。没有发现需要再次修改 SCG 产品规则的已证实缺陷。GSHC 布局/协议源码未改。

### Windows长路径：明确的可记录限制与已修复的提示/状态

v2三个失败目标均为260字符，临时源为191字符。当前宿主的独立288字符探针普通replace、stat、read都失败；扩展路径replace成功但普通stat/read仍失败，因此不能只给rename加前缀就宣布完整支持。真实用户选择合法目录及短项目文件后，SHA256命名的工件也可跨此边界；新GUI回归在约145字符项目目录中实际触发故障，不仅是pytest环境。

修复前同步/后台两例已先证明旧项目字节、parse/result引用、旧run重开及源日志均保留，但提示为“找不到路径”，同步分支还显示此前“工程已保存”。0a2a561仅在GUI保存边界把**实际**WinError3/206且异常路径达到260 UTF16码元的错误解释为可操作的“缩短目录或工程文件名，本次保存未完成”，保留原异常链及日志；同步失败状态也置为失败。没有预先一刀切禁用长路径、改相对引用/身份、系统设置或全路径加前缀。两例故障回归与语言检查4 PASS、exit0、20.25s，旧工程可用且新文件未提交，进度不到100%。

当前可用方案是在短项目保存目录使用短工程名，原日志/decoder不搬动、不修改。全面长路径支持仍未实现，标为**限制（不支持/FAIL）**；需要统一读写/验证/备份/清理路径策略及安全审查后另行实现。明确报错且旧数据保留的该限制，与数据损坏、虚假保存成功或未解决当前原生崩溃分开处理。短根同进程PASS只覆盖其记录路径；历史Aborted根因NOT PROVEN和当前版本实际回归结果也分开，不把旧失败改写成新版失败或完整根因证明。

## 3. 复现方式及测试环境

从仓库根目录运行证据中的 `run_v2.py` / `run_final.py`；诊断脚本使用本机现有 Python/Qt DLL，不安装调试软件。按 `flp_combined_v4.json` 等命令数组逐项执行，不要把 driver 退出码代替每个子进程结果。环境 `QT_QPA_PLATFORM=offscreen`、`PYTHONIOENCODING=utf-8`。FLP 必须用 `apps/FLP/.venv/Scripts/python.exe`，其 NumPy 为2.4.1；根 `.venv` 的2.4.0仅用于SCG/GSHC，不能冒充 FLP 数值环境。FLP runner仅在sys.path尾部借用根环境的pytest-qt4.5.0，NumPy/Qt仍由FLP环境优先加载；Python3.14.0、pytest9.1.1、Qt/PySide6/Shiboken6 6.10.1、pyqtgraph0.14.0，详见env附件和各日志开头。

```powershell
& .venv/Scripts/python.exe docs/evidence/nightly_software_20261008/run_v2.py flp_combined_v4 gnss_views_v2
& .venv/Scripts/python.exe docs/evidence/nightly_software_20261008/run_final.py gshc_final scg_final
& .venv/Scripts/python.exe docs/evidence/nightly_software_20261008/check_docs.py
```

附件脚本会使用全新的 `.work` basetemp（重跑时自动随机后缀），输出完整日志/JSON。`normal_test_paths.py` 仅使本机 pytest9/Python3.14测试目录通过普通 `mkdir` 继承权限；pytest默认0700目录在此受限执行器不可读。没有改变已存在目录权限或用户路径。FLP测试私有 QSettings 和 decoder cache，保留产品校验/取消/断言，禁用 pytest缓存写入。最早两次目录失败、一次菜单探针 import失败、一次导出解析编码失败均作为诊断失败保留，不能算测试PASS。

## 4. 文档阅读顺序和四算法覆盖

[用户流程总览](USER_WORKFLOW.md) → [硬件与四档建议](SilverStar_Recommended_Configurations.md) → [SCG配置生成](FCCG/USER_GUIDE.md) → [GSHC采集](GSHC/APP_README.md) → [FLP分析/工件](FLP/Project_Artifacts.md) → [算法数学与当前实现](algorithms/NAVIGATION_IMPLEMENTATION.md) → 本文验证边界/故障排查。根README和docs索引均补入口。

算法章第1节给 ENU/Body、Hamilton WXYZ、单位、Calibration/Alignment/INITIAL_STATE；第2节 Pure INS 圆锥/划桨及离散传播；第3节 SF6当前revision2固定增益、年龄/序列以及历史revision1分流；第4节 KF6 状态/量测、Joseph/NIS、版本化过程噪声、固定滞后及掉线恢复；第5节 ESKF15 右乘误差、Body传播、F/Phi/Q、杆臂量测、注入及右Jacobian reset、初始化身份和容量；第6节调度/日志缺口/fidelity。每节链接当前固件声明式payload及FLP源码。ESKF受限 Recorded parity EXACT 分支明确记录容差、缺失交叉协方差及实机边界，不能笼统称所有算法永远APPROXIMATE。数学未修改。

SF6旧固定滞后文档保留为revision1章节。推荐配置表保留原证据/数值并明确：H7尚无当前builtin生成支持；F407/ESKF15实际运行失败未解决；F103/NRF未实物验证；Logger栈结论仅限历史RET6配置；无GNSS水平漂移；20% RAM是建议。没有新增限频/400Hz/BMI088/JY901B气压禁选规则。

## 5. 明天最小静态验收

由用户接好硬件并明确硬件操作范围后才执行；今晚未执行以下项目。

1. 核对实板型号/版本、实际运行镜像 build/commit、精确 `.ssdecoder`/Descriptor及配置；旧 `28b168f/mission000041` 只能作为旧证据。无需今晚重新生成或猜测引脚。
2. 保持执行器隔离，在用户授权范围只观察连接、M0/CMD/ACK身份和控制器权威READY；Calibration/Alignment未READY不得用ACK替代。停止在未解决F407/ESKF15故障，不声称可外场。
3. 采集一段静止日志，检查CRC/序号/时间、普通日志overflow可检测、导航缺口不隐藏、初始化/校准记录、NRF RSSI/SNR空值；不以静止短日志证明无漂移、MCU WCET或栈裕量。
4. 严格Coordinator载入原log/decoder，查看Recorded及四算法可用性/参数来源，保存全部run和主副源后重开；缺身份/缺初始化/坏缓存要给真实错误，不能fallback或伪造持久确认。

历史FLP native abort的完整关闭需要再获得原生崩溃现场（模块/RVA及最好对应PDB/调试dump）与有界复现。现有导出符号定位只足以支持菜单所有权修复，不能据此宣布整个GUI生命周期已证明安全。
