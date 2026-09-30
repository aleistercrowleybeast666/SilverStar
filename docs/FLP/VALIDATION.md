# Validation

## 2026-09-22 — 联合新日志、fixed-lag 与时间输出

起始/当前 HEAD `26abf3033f92b1dac7b607ae722eefff2ecee9bc`，初始工作区干净；
本轮没有 commit、push、tag 或 Release。当前文件清单由 FCCG 联合报告的 Git 快照记录。
新契约见 [Field Log Replay](Field_Log_Replay.md)。历史验收段落仅适用于其日期。

### 实施与输入边界

- 正式输入为 FCCG decoder 1.2 的 corrected IMU、inertial increment、实际 estimator
  operation/present/epoch、GNSS/Barometer observation/measurement、恢复及 landing 诊断。
  退役的 IMU_NATIVE/HW_QUAT_NATIVE 不再作为新契约输入，KF6 不依赖 Pure INS 旁路。
- GNSS/Barometer 共用有界 replay：600 ms、144 IMU、48 GNSS、160 BARO、208 总量测、
  8 checkpoints、560 propagation steps；历史 clone 覆盖 x/P/内部滤波状态，receive 证据只计一次。
  重复操作拒绝、缺失操作诊断、跨 epoch 需要可关联的初始 state/P，不能用当前 P 冒充历史 P。
- faithful 路径消费实际增量/操作；独立 corrected-IMU mechanization 核对 dt、增量、
  区间和首个分歧，不重复校准。四组 GNSS 更新、inflation 和 group re-anchor 与 C 对照。
- Recorded / Replay / What-if 统一 Analysis Source；项目保存配置、结果编号和时间范围，
  重开后台重算并恢复。显式 Compare 仍独立。临时 analysis-only 诊断不写入生产参数。
- 共享双柄时间条覆盖五页、表格、轨迹和导出；5/10/30/60/120/Full/Custom 与 Start/End/
  Duration 一致。默认短于等于 30 s 为 Full，否则前 30 s。显示保留峰值、缺测和重锚断点。
- PNG 默认整段按 30 s 分页、类别目录；GIF 当前范围或 Full、30 fps、最多 30 s 匀速运动、
  精确源终点及 30 个物理末尾帧，逐帧进度/取消；CSV 保留完整数据。

### 实际验证

- 完整 pytest：**329 passed, 8 skipped in 279.39 s**，日志
  `D:/python_software/SilverStar_FCCG/tests/artifacts/joint/flp-full28.log`。
  8 skip 为未提供 hash 锁定的 SS0000/SS0007/SS0014/SS_TEST_0 历史真实日志。
  本轮实际生成 C golden 通过环境变量接入，未跳过。
- 全 src/tests Ruff：All checks passed，`flp-ruff-all.log`。
- 中英/Light/Dark/1000×700、范围控件和项目恢复：完整 suite 已覆盖；200% DPI 独立
  **5 passed in 19.13 s**，`flp-dpi27.log`。offscreen 显式加载系统字体，已审阅可读截图。
  Qt offscreen 不支持真实 OpenGL，不能据此宣称实际 GPU/触屏硬件通过。
- 后台扫描测试用工作线程与 GUI 定时器 Event 握手，验证 UI 工作发生在任务进行期间；
  修复原先短任务先于首个 10 ms tick 完成的测试竞态，不改变生产调度。
- 61 s PNG 为 0–30 / 30–60 / 60–61；实际 GIF 编码验证帧数与视觉一致 hold；
  10/30/31/60/300 s 计划、取消、目录、表格完整导出与断点均有回归。
- delayed BARO 与准时到达 reference 的 x/P 一致；“只改 timestamp + 当前 x/P 更新”负例
  明确不通过；GNSS/BARO 不同延迟排序、native/configured delay 不重复补偿都有覆盖。

### FCCG C → decoder → FLP 数值链

使用真实生成工程 SS_TEST_19 / SS_TEST_20、真实 C codec 和 generated descriptor，
不是 Python 手工拼 wire。三组质量 clean，operation/result/generation mismatches 均为空，
mechanization 验证全部通过；q 的最大误差均为 0。

| C 场景 | 对照数 | position max error (m) | velocity max error (m/s) | covariance max error |
|---|---:|---:|---:|---:|
| 常规 | 400 | 2.24e-8 | 9.43e-8 | 1.20e-7 |
| pos 40 / vel 270 / baro 100 ms | 400 | 3.73e-8 | 9.45e-8 | 3.58e-7 |
| 长 outage / 公里漂移重锚 | 2000 | 5.59e-9 | 1.40e-9 | 1.20e-7 |

重锚计数 [1,0,1,0]，最大位置 5607.916 m，最终重跑结果见 `reanchor19/flp-comparison.json`。
文件均位于上述 FCCG `tests/artifacts/joint`；golden/decoder SHA256 在 FCCG 根 VALIDATION。
当前仍标注 **APPROXIMATE**：这些有限场景不是任意日志、多 epoch、多硬件的普遍 EXACT 证明。
离线 landing 的真实 FlightTask tick 未完整记录，重算明确近似；物理门限来自实际配置。

### Existing Time Synchronization vs Fixed-Lag Replay

固件已有 SystemTime 负责统一时间坐标及 wrap/offset/mission 转换；FLP 直接使用日志中
resolved measurement time、receive 和 operation present，不建立平行时钟系统。
可信 native 时间直接使用；没有可信 sample epoch 时按 receive - configured delay，
不对已经转换好的时间再减一次。replay 则恢复历史 x/P/内部状态、按量测时间 update、
重放后续事件到 present。时间同步与历史状态重放是上下游关系。

## 2026-09-17 — KF6 V2 真实日志诊断与 GUI

本轮只修改 FLP。开始时 FLP/FCCG/GSHC 的 `git status --short` 均为空。
FLP 起始 HEAD `07835302709c9dcdebfbb6641a76b469c5d18e2e`；没有 commit/push。
FCCG HEAD `34e16ef282402e3800c20492b32255143c0da67b`、GSHC HEAD
`62656da1fa035bff344165c8857a932e644ddbae` 与状态均保持不变。
没有修改日志、decoder、工程 schema、固件、生产参数/门限、P0/Q/INS/姿态/部署/着陆。

### 修改文件与行为

- `plugins/algorithms/kf6/diagnostics.py`（位于 src/silverstar_flp，下同）：新增独立临时诊断选项、
  请求包装、5组量测权重审计和专用JSON导出，未向参数/schema增加字段。
- `plugins/algorithms/kf6/plugin.py`：复用正常resolver之后施加精确Baro R覆盖、速度时移及冻结初始化；
  diagnostics/provenance明确Analysis-only。无覆盖的原路径保持不变。
- `plugins/algorithms/kf6/filter.py`：分析开关真正跳过GNSS pU，E/N仍执行原更新。
- `plugins/algorithms/kf6/field_analysis.py`：复用扫描，补充zero/best/improvement/采样谷宽和结果元数据，
  子回放共享取消事件，避免嵌套进度倒退。
- `ui/offline_diagnostics.py`：KF6子页、双语模式/结果摘要、量测表、后台操作入口、Reset Charts和JSON导出。
- `ui/pages/replay.py`：仅增KF6子tab、请求分发、模式标签和忙状态；同一数据集完成复算后保留参数草稿。
- `ui/main_window.py`：沿用FunctionWorker/QThreadPool、进度/取消/错误处理；工程保存不持久化分析结果配置。
- `core/analysis_source.py`、`ui/pages/charts.py`：传递临时Analysis-only来源标签。
- `export/service.py`：普通导出保留诊断元数据、来源及Full-P标签。
- `i18n/en_US.json`、`i18n/zh_CN.json`：诊断文字、单位、时移方向和原点项/覆盖边界。
- `tests/test_offline_diagnostics.py`：数值行为、隔离、合成时延、后台线程和四种语言主题组合回归。
- `docs/KF6_FIELD_ANALYSIS.md`、`docs/GUI_STYLE_GUIDE.md`、本文件：行为契约及验收。

GUI入口：复算→选择KF6→高级离线诊断；不增加第六个主页面。
默认Firmware-faithful。自动扫描仅展示结果，Apply Best才应用到当前analysis并回放。
手动shift=0保留完整原调度；自动扫描0档与其他shift共享内部窗口，二者评分窗口不同。
Baro覆盖为精确sigma²，不叠加原点项；禁用pU不使用巨大R。
Restore清除临时值/开关/scan，已经完成的Analysis-only结果继续保持原标签。
正常项目参数草稿可保存，临时shift/Baro覆盖/pU禁用均不进入.ssflp或decoder。

### 测试覆盖与限制

新增测试含7个pytest case（其中4个为中英文×深浅色组合），覆盖提示词18项：

| 要求 | 验证 |
| --- | --- |
| 默认模式/覆盖关闭/shift0（1–3） | GUI真实控件初始值 |
| 手动真实平移/恢复（4–5） | KF6状态确实变化；去掉覆盖后与基线逐位相同 |
| 合成已知latency（6） | +80ms信号恢复到−80ms±5ms；进度单调并完成 |
| Apply Best隔离（7） | Scan不改选项；显式Apply后才发replay请求 |
| Baro有效R/恢复（8–9） | native R25→分析R4；KF6实际通道R4；恢复原输出 |
| pU跳过/E-N不变（10–11） | pU更新数和NIS样本数0；E/N状态逐位相同 |
| 工程/decoder/Recorded隔离（12–14） | 真实_Project_Write、decoder SHA256、原日志SHA256、记录参数和原生variance未变 |
| 导出标签（15） | JSON analysis_only字段及AlgorithmResult.provenance；拒绝覆盖已存在导出文件 |
| GUI后台计算（16） | 线程ID与主线程不同、QTimer继续tick、禁重复、成功/异常/取消后恢复 |
| 中英文/主题/布局（17–18） | Qt offscreen四组合，1000×700尺寸、无页面横向溢出，截图人工复核 |

Windows offscreen QPA未自动发现字体，截图测试显式只读加载系统微软雅黑，并验证“中”字有字形；
未改产品字体或系统字体配置。Qt offscreen不支持QOpenGLWidget，未宣称实体CF-33触摸或OpenGL硬件验收。
初次compileall递归进入历史pytest产物，遇到清理测试故意写入的无效`preserve-or-clean`代码；
未修改/删除这些产物，最终源码检查排除隐藏测试输出目录。

完成检查：

- `.venv/Scripts/python.exe -m pytest -q --basetemp=tests/.pytest-v2-final -o cache_dir=tests/.pytest-cache-v2`：
  **287 passed, 8 skipped，110.54s**。8项分别为历史SS0000、SS0007、SS0014及SS_TEST_0手动数据gate，
  未设置各自精确匹配环境变量，不能拿本轮同名SS0007或合成数据替代。
- `.venv/Scripts/python.exe -m ruff check src tests tools`：通过。
- `PYTHONPYCACHEPREFIX=tests/.compile-v2-cache`，
  `.venv/Scripts/python.exe -m compileall -q -x '[\\/]\.' src tests tools`：通过。
- `git diff --check`：通过。去掉无关格式变化时逐块验证AST完全一致，未整文件回退。

### 真实日志V2证据

输出仅在用户指定的新目录：
`D:/stm32_project/SS_0_5_TEST_0/LOG/KF6_PARAMETER_OPTIMIZATION_V2/`。
主报告`KF6_PARAMETER_OPTIMIZATION_V2.md`，交互报告`VU_LATENCY_INTERACTION.md`，
冲击报告`SS0008_IMPACT_RECOVERY.md`，全部要求的CSV、逐日志JSON/NPZ/Markdown及8张PNG已生成。
V1及输入共1994文件SHA256前后一致。未改原固件参考工程。

- 四条真实日志SS0005–8，exact decoder 1.2配对，APPROXIMATE复算，不宣称旧固件bit-exact或Host Golden已验证。
- 54位置配置×4日志=216回放；12组latency共684回放；3时序×7速度倍率×4日志=84回放。
  另有4基线、24次气压floor等效性验证和同shift参照回放；主计数不冒充全部运行总次数。
- native Baro variance25导致配置sigma1.5/2/2.5/3/4/5均等效，24次状态逐位相同。
- 位置稳定区域选择GNSS pU2.5 / Baro有效sigma2.5；vU scale1、shift0下聚合分0.935264。
- B位置候选最优shift分别−255/−375/−290/−220 ms；median−272.5、IQR65、MAD35、range155 ms，同号100%。
  timing mismatch证据YES；固定固件补偿依据NO。common诊断shift−270ms。
- 三时序最低分scale均2.0；唯一外场验证候选采用邻近稳定点1.75、GNSS pU2.5、Baro有效2.5、shift0、outage300。
  完整候选**NOT CURRENTLY IMPLEMENTABLE**，因当前native floor5；不把离线覆盖包装成可下发字段。
- SS0008候选末段vU RMS0.2997，相对基线0.2663增加12.6%，同时回高残差绝对值2.6797降至1.3167m。
  最低总分不代表所有指标改善。单例报告不被普通日志平均掩盖。
- GNSS最大epoch间隔46.975/46.203/47.240/47.986ms，无>300ms outage；基线/位置/速度扫描均无误inflation。
  保持outage300不重新优化。
- 一份当前默认固件足够用于下一轮采集/离线候选比较；不表示这个完整候选已可部署。机上六项默认不变。

## 2026-09-17 — 外场前工程默认根目录一致性收尾

本节是本轮路径修改的验收；下方较早的 KF6 修改记录属于历史基线，不是本轮改动。
初始 HEAD：`98cc422`；初始 `git status --short` 为空。
只改 FLP 工程文件对话框路径；没有 commit/push，没有删除、覆盖用户未提交内容。
GSHC 无改动。与 FCCG 独立实现，不增加跨仓库依赖。

### 文件与原因

- `src/silverstar_flp/core/path_preferences.py`：给已有 PathPreferences 添加
  `DefaultProjectRoot_EffectiveGet`，共享有效配置 → Documents → Home → cwd 的现存目录 fallback。
  不增加设置系统、字段或 schema；读取不创建目录、不回写偏好。
- `src/silverstar_flp/ui/main_window.py`：New/Open/Save As 与默认根目录选择入口复用 helper。
  Open 不再固定 Home；Save As 不再沿用旧工程所在目录或 cwd，而是新 root + 原文件名。
  首次 Save 补用已有 _Overwrite_Confirm，拒绝覆盖时不写文件；已有项目的普通 Save 不变。
- `tests/test_path_preferences.py`：拦截 QFileDialog/NewProjectDialog，验证实际入口的建议路径、
  Unicode、取消无副作用、缺失/损坏/空/相对/已删除/文件/缺失磁盘偏好。
  比较工程序列化前后、偏好原始字节和既有工程内容，保持普通 Save、导入、导出规则。
- `docs/GUI_STYLE_GUIDE.md`：补充工程路径规则。
- `VALIDATION.md`：本轮验收记录。

### 最终规则

假设默认目录为 D:/SilverStarFlightLogs：
New 保持 <root>/<name>/<name>.ssflp；Open 从 root 开始；
旧路径 D:/Other/Flight_001.ssflp 的 Save As 建议为
D:/SilverStarFlightLogs/Flight_001.ssflp，未保存工程建议 flight.ssflp。
Unicode 文件名原样保留，用户仍可选择其他目标；普通 Save 写当前文件。
Open/Save As 不静默修改默认目录。无效偏好只选择现存 fallback，不创建任何目录。
新建工程在用户接受目标后创建目录的原有流程不变。

日志导入仍优先当前/待建工程目录；结果仍按 ExportDirectory_Default 放在工程或日志旁的
Result_<logstem>，不会集中到默认根目录顶层。既有覆盖确认、项目兼容校验、单日志引用均保留。

### 检查结果

- 定向：
  `.venv/Scripts/python.exe -m pytest tests/test_path_preferences.py tests/test_project_export.py tests/test_gui_smoke.py -q --basetemp=tests/.pytest-root-focus-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **36 passed, 42.13 s**。
- 全量：
  `.venv/Scripts/python.exe -m pytest tests -q --ignore-glob='tests/.pytest-*' --basetemp=tests/.pytest-root-full-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **280 passed, 8 skipped, 75.27 s**，日志 `tests/.pytest-root-full-20260917.log`。
  跳过：SS0000 一项、SS0007 三项、SS0014 一项、SS_TEST_0 三项，
  均因指定的真实日志未提供；本轮未伪造实测验证。
- 将无效盘符 fixture 加强为机器上实际缺失盘符后：
  `.venv/Scripts/python.exe -m pytest tests/test_path_preferences.py -q --basetemp=tests/.pytest-root-drive-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **12 passed, 2.86 s**。随后为首次 Save 补充覆盖确认，最终重跑见下。
- `.venv/Scripts/python.exe -m ruff check --no-cache src tests tools --exclude '.pytest-*' --output-format concise`：
  **All checks passed**。仅修复新增测试的导入顺序与长行，没有批量格式化源代码。
- `.venv/Scripts/python.exe -m compileall -q src`：通过；
  PYTHONPYCACHEPREFIX 限 tests/.pytest-root-compile-20260917。
- 最终完整运行（含首次 Save 覆盖确认）：
  `.venv/Scripts/python.exe -m pytest tests -q --ignore-glob='tests/.pytest*' --basetemp=tests/.pytest-root-final-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **280 passed, 8 skipped, 68.91 s**；日志 `tests/.pytest-root-final-20260917.log`。
  跳过原因同上。覆盖确认定向检查 **12 passed, 2.87 s**；最终 Ruff 通过。
- `git diff --check`：通过。没有为本轮新增 mypy 等强制工具。
- 所有对话框测试拦截 exec/静态选择方法，没有弹出真实文件选择框；不声明实体 GUI/硬件验收。

### 未修改的问题与边界

未修改 KF6/GNSS/INS、reacquisition、NIS、任何算法默认参数、
.ssflp v3/schema、FCCG project/schema、protocol、日志格式或 decoder。
GNSS CONFIG READ/SHOW 的既有差异没有在本轮诊断或修复，按提示词留待新固件外场复核。
没有发现需要在本轮顺手修改的其他产品问题。最终工作区保留上述文件的未提交修改，不 push。


## 2026-09-17 — KF6 outage、独立 U 速度权重、离线扫描与工程工作流

初始 HEAD：`2a301d8c6c0c7f37568998acc675a0c5d68b9d3c`；初始 `git status --short` 为空。
本轮按附件分别本地中文提交，不 push；未 reset/checkout/clean。FLP 0.0.2、.ssflp v3、
decoder/project-semantics 1.2、算法参数 schema 1.0 均未升级，无 FCCG/GSHC 运行时依赖。
详细行为与 CLI 见 [KF6 分析与工程路径](KF6_FIELD_ANALYSIS.md)。

### 改动与兼容结论

- Python KF6 同步 C：position EN/U、velocity EN/U 各自跟踪有效时间戳和恢复状态；
  连续有效 GNSS 即使 hard reject 仍刷新可用性，不触发 inflation。
  仅严格超过 outage 阈值才允许恢复；正常融合返回直接解除，无需膨胀。
  真掉线后五次 hard reject + 三个一致间隔可启动 DPD'，factor=2、间隔五次 reject、
  上限八次与三次融合退出保持。重复掉线/非法数据/重复和回退时间戳有回归覆盖。
- 新增 `gnss_reacquire_outage_ms`（整数，默认 300）和
  `gnss_velocity_vertical_scale`（默认 1）；保留既有 `gnss_velocity_std`。
  EN sigma=max(receiver sigma*1.25, floor)，U 再乘独立 scale，R 平方；
  receiver uncertainty 不被固定 R 代替。P0、Q、NIS 阈值、gravity、INS/姿态保持。
- Barometer 直接更新 pU，通过交叉协方差间接修正 vU；GNSS pU、vU 分别量测更新。
  正式默认仍为 GNSS pU floor 2.5 m、Barometer 5 m、velocity floor 0.15 m/s、U scale 1。
  这些是兼容的保守候选，不是本轮新证明的飞行最佳参数。
- 旧工程只接受精确的旧 KF6 参数身份，只有两个新字段允许缺失 fallback；
  原有必需参数缺失仍报错。Recorded Configuration 不可变，What-if 使用独立实际值，
  int 参数保持整数。旧 GNSS 日志使用新恢复策略明确标为 approximate；
  不能把新策略宣称为旧固件 exact replay。新实际参数继续走原 exact matching 和哈希校验。
- 保留 GNSS NIS max(EN 2D,U 1D) 展示、稀疏 PRE-FLIGHT、时间戳匹配、Pure INS、full P、
  replay cadence、导出。未改 AIR/GSP、SSLOG、FCCG project 12、部署或着陆逻辑。

### 离线能力与证据边界

`tools/kf6_field_analysis.py --pair LOG DECODER [--pair ...] --output NEW_DIRECTORY`
对每个日志独立 exact-pair 打开与复算，前后核对源 SHA256，输出逐日志 JSON 和 comparison.json。
无多日志 .ssflp schema 或跨仓库运行时依赖。扫描使用实际 KF6：

| 扫描 | 候选 |
| --- | --- |
| 恢复门禁 | 旧 reject-only comparator / 新 outage-required |
| outage | 160 / 200 / 250 / 300 / 500 ms |
| GNSS pU floor | 2.5 / 3 / 4 / 5 / 6 m |
| Barometer floor | 1.5 / 2 / 3 / 5 m |
| velocity U scale | 1 / 1.25 / 1.5 / 2 |
| velocity latency | -500…+500 ms，20 ms coarse，最优附近 5 ms refinement |

延迟扫描在原 GNSS epoch 网格上重采样 velocity 和 receiver variance，正值表示延后，
所有候选使用共同内部时间窗，不越过大 source gap、不外推。position/Baro/IMU 时间不变；
每个候选重跑 KF6。这是 approximate 离线试验，不是 OOSM，也不是简单移动结果曲线。
评分为实际 EN/U hard 阈值归一化 p95 NIS 与 hard-reject 比例。
INITIAL_STATE/P0 冻结仅限显式 analysis；正常 What-if 仍保留初始化证据门禁。
缺少匹配 native uncertainty 时 R sweep 明确 unavailable，不虚构固定方差。

统计含逐组 accept/soft/hard/invalid/numeric、NIS max/p50/p90/p95/p99、inflation 次数、
最终 p/v、P 对角峰值、同时间戳 Recorded residual 与 Pure INS。
Recorded residual 不是 ground truth；静止 RMSE 只在显式已知区间计算，
reference RMSE 只在有参考序列时计算，否则 null。

合成验证：

- 已知 +80 ms velocity 延迟，57 次实际重跑找回 **-80 ms**，score=0。
- 连续 fresh GNSS 拒绝对照：新策略四组 inflation=[0,0,0,0]；
  旧 comparator=[0,0,5,0]。这说明旧策略会把动态不一致当作恢复，不表示旧输出更准确。
- 显式 native uncertainty 合成 fixture 覆盖全部权重候选；U scale=1.5 时对应 R×2.25，
  EN 不变；缺 native 的 fixture 如实拒绝权重重建。
- 输出在 `tests/.pytest-closeout-0917/` 下相应 test 目录：
  `latency_synthetic.json`、`continuous_rejection_comparison.json`、
  `native_weight_sweeps.json` 和 `c_python_equivalence.json`。

三仓库、D:/python_software 与用户 Desktop 搜索未找到真实 SS0005–SS0008 BIN/SSLOG；
少数历史测试缓存 ACL 不可读。**未执行真实 SS0005–8 baseline/A/B**。
四组真实日志的最佳 shift、手持最优参数均未知；无稳定物理延迟证据，
不支持 firmware compensation，本轮没有加入固定补偿。地面候选不能自动推广为火箭飞行参数。

### 工程工作流示例

默认根目录 JSON 位于应用 AppLocalDataLocation 下 `path_preferences.json`，UTF-8、原子 replace、
schema_version=1。独立于 .ssflp 和 compatibility hash。坏 JSON、缺失文件/根目录安全 fallback；
设置偏好不创建未确认的大目录。名称自动跟随，实际手改或 Browse 后使用所选目录本身。

例如默认 root=`D:/SilverStarFlightProjects`、name=`FieldTest_0917`：

```text
D:/SilverStarFlightProjects/FieldTest_0917/
├─ FieldTest_0917.ssflp
├─ SS0005.BIN
├─ SS0006.BIN
├─ Flight.ssdecoder
├─ Result_SS0005/
└─ Result_SS0006/
```

这表示同一目录可依次处理不同日志；.ssflp 仍只保存一个当前日志。
Import 默认 folder_search，当前或待建工程目录优先，打开另一工程时刷新；
无工程按 default root → 最近成功导入目录 → 安全现存目录。
Browse 从当前搜索目录开始，manual pair 仍可用且语言切换不丢模式。
默认 Result_<logstem> 正确处理 BIN/SSLOG 大小写、中文/空格/括号；Windows 非法字符替换。
碰撞自动 _2/_3，手工目的地保持；非空导出目录拒绝，不覆盖旧结果。
新工程接受路径时创建子目录，取消后续导入不留下 .ssflp；Save/Open 原路径语义保留。

### 数值等价与测试

C 真实生成 fixture 十场景×64帧=640帧，FLP 使用独立仓库本地固定数据。
最大 position deviation=**7.499018093992671e-09 m**；
velocity=**4.881515330845687e-11 m/s**；
P=**3.7143001591077862e-09**。
所有恢复状态/计数逐帧相同；C 文本序列化精度带来这些差异，符合 float32 等价。

- `.venv/Scripts/python.exe -m pytest tests -q --basetemp=tests/.pytest-closeout-0917 --ignore-glob='tests/.pytest-*' -o cache_dir=tests/.pytest-cache/0917`：
  **272 passed, 8 skipped, 62.42 s**，日志 `tests/.pytest-cache/0917-closeout.log`。
  覆盖 KF、replay、参数、NIS、sparse preflight、比较、export、GUI、路径/导入/结果目录。
- 跳过八项：SS0000 一项、SS0007 三项、SS0014 一项、SS_TEST_0 三项；
  缺少各自 hash-locked 实测日志与 decoder，不能伪造通过。
- `.venv/Scripts/python.exe -m ruff check --no-cache src tests tools --exclude '.pytest-*' --output-format concise`：通过。
  排除一次性测试输出中故意非法的 fixture，不排除正式源/测试。
- `git diff --check`、`git diff --cached --check`：通过。
- Qt offscreen Light/Dark × zh_CN/en_US 新工程对话框渲染，测试进程加载 Windows 字体；
  检视英文 Dark、中文 Light 无裁切，图在 `tests/.pytest-visual-0917/`。
  未完成实体触屏、真实飞行或新安装包验证；无对应支持声明。

### 提交前 Git 快照（不含本报告）

初始 HEAD 复核：2a301d8c6c0c7f37568998acc675a0c5d68b9d3c

```text
M	README.md
M	docs/CXYL_Python_GUI_STYLE_GUIDE.md
M	docs/GUI_STYLE_GUIDE.md
A	docs/KF6_FIELD_ANALYSIS.md
A	src/silverstar_flp/core/path_preferences.py
M	src/silverstar_flp/core/project.py
M	src/silverstar_flp/export/service.py
M	src/silverstar_flp/i18n/en_US.json
M	src/silverstar_flp/i18n/zh_CN.json
A	src/silverstar_flp/plugins/algorithms/kf6/field_analysis.py
M	src/silverstar_flp/plugins/algorithms/kf6/filter.py
M	src/silverstar_flp/plugins/algorithms/kf6/plugin.py
M	src/silverstar_flp/plugins/api/algorithm.py
M	src/silverstar_flp/ui/main_window.py
M	src/silverstar_flp/ui/new_project.py
M	src/silverstar_flp/ui/pages/export_settings.py
M	src/silverstar_flp/ui/pages/replay.py
A	tests/fixtures/kf6_outage_vectors.json
M	tests/fixtures/parameter_contracts/kf6_fccg_1_2.json
M	tests/parameter_fixtures.py
M	tests/test_gui_smoke.py
A	tests/test_kf6_field_analysis.py
A	tests/test_kf6_outage.py
A	tests/test_path_preferences.py
M	tests/test_replay_page.py
A	tools/kf6_field_analysis.py

 README.md                                          |   3 +
 docs/CXYL_Python_GUI_STYLE_GUIDE.md                |   4 +-
 docs/GUI_STYLE_GUIDE.md                            |   4 +-
 docs/KF6_FIELD_ANALYSIS.md                         |  86 ++++++++
 src/silverstar_flp/core/path_preferences.py        |  82 +++++++
 src/silverstar_flp/core/project.py                 |  23 +-
 src/silverstar_flp/export/service.py               |   2 +
 src/silverstar_flp/i18n/en_US.json                 |   9 +-
 src/silverstar_flp/i18n/zh_CN.json                 |   9 +-
 .../plugins/algorithms/kf6/field_analysis.py       | 244 +++++++++++++++++++++
 .../plugins/algorithms/kf6/filter.py               |  77 ++++++-
 .../plugins/algorithms/kf6/plugin.py               | 149 ++++++++++---
 src/silverstar_flp/plugins/api/algorithm.py        |  13 +-
 src/silverstar_flp/ui/main_window.py               |  59 ++++-
 src/silverstar_flp/ui/new_project.py               |  26 ++-
 src/silverstar_flp/ui/pages/export_settings.py     |  66 +++---
 src/silverstar_flp/ui/pages/replay.py              |  82 +++----
 tests/fixtures/kf6_outage_vectors.json             |   1 +
 .../fixtures/parameter_contracts/kf6_fccg_1_2.json |  47 +++-
 tests/parameter_fixtures.py                        |   5 +-
 tests/test_gui_smoke.py                            |  14 +-
 tests/test_kf6_field_analysis.py                   | 168 ++++++++++++++
 tests/test_kf6_outage.py                           | 184 ++++++++++++++++
 tests/test_path_preferences.py                     | 106 +++++++++
 tests/test_replay_page.py                          |   4 +-
 tools/kf6_field_analysis.py                        |  61 ++++++
 26 files changed, 1353 insertions(+), 175 deletions(-)
```

最终提交后的工作区状态另在交付消息核验。


## 2026-09-16 — GNSS NIS semantics and sparse PRE-FLIGHT closeout

Clean initial source worktree at `f4b10f8`; user attachment explicitly authorized independent
FLP changes. No reset, checkout, commit or push. Version 0.0.2, .ssdecoder/project-semantics
1.2, SSLOG 0.0 and existing project formats remain unchanged.

### Root cause, fix and scope

KF6's recorded/recomputed position and velocity NIS are max(horizontal EN 2D, vertical U 1D).
Visualization metadata incorrectly named nis_3d_soft/hard as the thresholds for these aggregates.
`last_group_nis` exists inside the numerical filter, but the current exposed/recorded semantic
channels provide the aggregates; this patch does not invent group channels or extend log fields.

`NisThresholdSpec` plus optional MeasurementGroupSpec description/reference metadata supply the
shared GUI/export renderer. GNSS position/velocity now show:

| Reference | Default actual value |
| --- | ---: |
| U / 1D soft | 6.635 |
| U / 1D hard | 10.828 |
| EN / 2D soft | 9.210 |
| EN / 2D hard | 13.816 |

The title explains `max(EN 2D, U 1D)` and explicitly says the lines are group references,
not a unified aggregate pass/fail gate. Values use the source's actual parameter mapping;
float32 representation is preserved. Barometer keeps its existing pair of 1D thresholds.
English/Chinese labels and PNG titles use the same metadata. Other algorithms keep the
existing two-threshold fallback; fake future-estimator tests pass without page branches.
The 3D parameter declarations are retained because this is a presentation correction,
not a change to filter mathematics, parameters or historical data.

The parser/replay already accepts sparse preflight correctly. No parser, sequence-gap,
timestamp, required-stream, comparison-sampling or numerical code was changed or weakened.

### Files and regression coverage

- `src/silverstar_flp/plugins/api/algorithm.py`: generic NIS reference metadata and fallback.
- `src/silverstar_flp/plugins/algorithms/kf6/plugin.py`: visualization declarations only;
  position/velocity no longer reference nis_3d_* gates.
- `src/silverstar_flp/ui/pages/state_estimation.py`, `src/silverstar_flp/export/service.py`:
  metadata-driven reference lines and explanatory title for both surfaces.
- `src/silverstar_flp/i18n/en_US.json`, `zh_CN.json`: four reference names and aggregate meaning.
- `tests/test_estimator_visualization.py`, `tests/test_flight_state_pages.py`: four GNSS
  references, correct actual values, 1D barometer, both languages, generic-renderer regression;
  the GNSS plot contains one data curve plus four references instead of the old three curves.
- `tests/synthetic_parameter_navigation.py`: optional sparse preflight/flight length and missing
  IMU fixture switches; its original default fixture and frozen numerical outputs remain intact.
- `tests/test_sparse_preflight.py`: exact matching synthetic decoder/log, 120 s sparse preflight,
  20 s corrected IMU plus selected Baro inputs; CRC/header/record sequence clean, Data Quality
  CLEAN, KF6/Pure INS replay available, all four pages render, CSV/PNG/export succeeds.
  A separate exact package with missing mission IMU remains unavailable/rejected despite
  continuous SSLOG record sequences. The fixture selects IMU/Baro; it is not a GNSS hardware test.
- `docs/GUI_STYLE_GUIDE.md`, this report: interpretation and acceptance boundary.

### Verification

All output, TEMP/TMP and MPLCONFIGDIR are local to `tests/.pytest_cache/nis_0916/`;
QT_QPA_PLATFORM=offscreen, PYTHONDONTWRITEBYTECODE=1.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_estimator_visualization.py tests/test_sparse_preflight.py -q --basetemp=tests/.pytest_cache/nis_0916/run4 -o cache_dir=tests/.pytest_cache/nis_0916/cache
.venv/Scripts/python.exe -m pytest -q --basetemp=tests/.pytest_cache/nis_0916/full2 -o cache_dir=tests/.pytest_cache/nis_0916/cache
.venv/Scripts/python.exe -m ruff check src/silverstar_flp/plugins/api/algorithm.py src/silverstar_flp/plugins/algorithms/kf6/plugin.py src/silverstar_flp/ui/pages/state_estimation.py src/silverstar_flp/export/service.py tests/test_sparse_preflight.py tests/test_estimator_visualization.py tests/synthetic_parameter_navigation.py --no-cache
```

Focused **9 passed**. Full **257 passed, 8 skipped in 74.54 s**; ruff passes and
`git diff --check` passes. Full coverage includes replay, timestamp semantics, comparison
sampling, touch, state GUI, export and the unchanged frozen `legacy_dynamic_outputs.npz`
comparison for every default algorithm result channel. No golden file was regenerated.
All KF6 plugin callable implementations match HEAD structurally (AST comparison).

Eight skips require unavailable explicitly named real logs: current SS0000, SS0007 (3),
SS0014 and SS_TEST_0 (3). These are not synthetic acceptance passes or hardware claims.

Artifacts: `tests/.pytest_cache/nis_0916/full2.log`; sparse exact .BIN/.ssdecoder pair, four
page screenshots and exported files under
`tests/.pytest_cache/nis_0916/full2/test_sparse_120_seconds_import0/`.
English GNSS reference PNGs under
`tests/.pytest_cache/nis_0916/full2/test_configured_without_valid_0/configured_no_updates_export/Plots_EN/`
were visually inspected: title, reference legends and lines fit without clipping. This fixture
correctly leaves the data plot empty when no valid GNSS updates exist.

The unavailable real logs and hardware acceptance remain the only unverified data sources.
No GNSS quality/reacquisition algorithm, covariance inflation, deployment or sampling logic changed.

<!-- closeout-git-begin -->
### Final Git snapshot

Tracked diff (new files are listed separately by status):

```text
 VALIDATION.md                                      | 122 +++++++++++++++++++++
 docs/GUI_STYLE_GUIDE.md                            |  15 +++
 src/silverstar_flp/export/service.py               |  20 +---
 src/silverstar_flp/i18n/en_US.json                 |   7 +-
 src/silverstar_flp/i18n/zh_CN.json                 |   7 +-
 .../plugins/algorithms/kf6/plugin.py               |  19 +++-
 src/silverstar_flp/plugins/api/algorithm.py        |  23 ++++
 src/silverstar_flp/ui/pages/state_estimation.py    |  27 ++---
 tests/synthetic_parameter_navigation.py            |  53 +++++----
 tests/test_estimator_visualization.py              |  42 ++++++-
 tests/test_flight_state_pages.py                   |   2 +-
 11 files changed, 273 insertions(+), 64 deletions(-)
```

```text
 M VALIDATION.md
 M docs/GUI_STYLE_GUIDE.md
 M src/silverstar_flp/export/service.py
 M src/silverstar_flp/i18n/en_US.json
 M src/silverstar_flp/i18n/zh_CN.json
 M src/silverstar_flp/plugins/algorithms/kf6/plugin.py
 M src/silverstar_flp/plugins/api/algorithm.py
 M src/silverstar_flp/ui/pages/state_estimation.py
 M tests/synthetic_parameter_navigation.py
 M tests/test_estimator_visualization.py
 M tests/test_flight_state_pages.py
?? tests/test_sparse_preflight.py
```
<!-- closeout-git-end -->


## 2026-09-14 — GUI touch-scrolling closeout

Scope: GUI registration/helper, GUI tests and documentation only. Initial working tree was clean;
no reset, checkout, commit, push, version change or cross-repository dependency was introduced.

<!-- touch-git-snapshot -->
### Modified files and Git snapshot

- `VALIDATION.md`
- `docs/GUI_STYLE_GUIDE.md`
- `src/silverstar_flp/ui/main_window.py`
- `src/silverstar_flp/ui/pages/data_explorer.py`
- `src/silverstar_flp/ui/pages/export_settings.py`
- `src/silverstar_flp/ui/pages/overview.py`
- `src/silverstar_flp/ui/pages/replay.py`
- `src/silverstar_flp/ui/pages/state_estimation.py`
- `src/silverstar_flp/ui/plugin_manager.py`
- `src/silverstar_flp/ui/touch_scroll.py`
- `src/silverstar_flp/ui/widgets.py`
- `tests/test_touch_scroll.py`

`git diff --stat` (tracked files only; new files are listed above):

```text
 docs/GUI_STYLE_GUIDE.md                         | 16 ++++++++++++++++
 src/silverstar_flp/ui/main_window.py            |  2 ++
 src/silverstar_flp/ui/pages/data_explorer.py    |  6 ++++++
 src/silverstar_flp/ui/pages/export_settings.py  |  3 +++
 src/silverstar_flp/ui/pages/overview.py         |  5 +++++
 src/silverstar_flp/ui/pages/replay.py           |  4 ++++
 src/silverstar_flp/ui/pages/state_estimation.py |  2 ++
 src/silverstar_flp/ui/plugin_manager.py         |  2 ++
 src/silverstar_flp/ui/widgets.py                |  3 +++
 9 files changed, 43 insertions(+)
```

`git status --short`:

```text
 M docs/GUI_STYLE_GUIDE.md
 M src/silverstar_flp/ui/main_window.py
 M src/silverstar_flp/ui/pages/data_explorer.py
 M src/silverstar_flp/ui/pages/export_settings.py
 M src/silverstar_flp/ui/pages/overview.py
 M src/silverstar_flp/ui/pages/replay.py
 M src/silverstar_flp/ui/pages/state_estimation.py
 M src/silverstar_flp/ui/plugin_manager.py
 M src/silverstar_flp/ui/widgets.py
?? VALIDATION.md
?? src/silverstar_flp/ui/touch_scroll.py
?? tests/test_touch_scroll.py
```
<!-- /touch-git-snapshot -->

### Cause and repair

Ordinary scrolling widgets had no native touch-scroller registration. Added the local
`TouchScroll_Enable` allowlist helper and explicit constructor calls. Coverage: Overview page
and calibration/alignment/timeline tables; Replay form and stored-result/comparison tables;
Data Explorer channel list and channel/record/diagnostic/sequence-gap tables; State Estimation
update table; Export Settings item scroll and failure details; navigation and Plugin Manager
table; StandardComboBox popup views. Existing pixel/item scroll modes stay unchanged.

2D PlotWidget/QGraphicsView, GLViewWidget and the playback slider are not registered, and runtime
coverage tests confirm they have no registered page-scroll ancestor. Flight/State Estimation
charts keep their expandable plotting layout. No Dataset, decoder, semantic adapter, timestamps,
KF6/Pure INS replay, comparison sampling, chart values, export logic or project format changed.

### Executed checks

- `.venv/Scripts/python.exe -B -m pytest tests/test_gui_smoke.py tests/test_comparison_sampling_gui.py tests/test_replay_page.py -q --basetemp=tests/.pytest-work-touch-focused -o cache_dir=tests/.pytest-cache-touch`: **14 passed**.
- `.venv/Scripts/python.exe -B -m pytest tests/test_touch_scroll.py -q --basetemp=tests/.pytest-work-touch-new2 -o cache_dir=tests/.pytest-cache-touch`: **18 passed**.
- Full pytest via `pytest.main(['-q', '--basetemp=tests/.pytest_cache/touch-validation/full', '-o', 'cache_dir=tests/.pytest_cache/touch-validation/cache'])`: **254 passed, 8 skipped**, 58.86 s.
- `.venv/Scripts/python.exe -B -m ruff check src tests --no-cache`: **passed**.
- `git diff --check` and static scroll/graphics inventory: **passed**.

Full-run wrapper sets `QT_QPA_PLATFORM=offscreen`, `PYTHONDONTWRITEBYTECODE=1`, process-local TEMP,
TMP and MPLCONFIGDIR below `tests/.pytest_cache/touch-validation`; QSettings uses IniFormat and
that directory's settings subtree. The full log is `tests/.pytest_cache/touch-validation/full.log`.
New tests cover native viewport registration/type, exclusion of inputs/graphics/headers, retained
mouse row selection and scrollbar movement, actual synthesized finger swipes on page/list/table/text,
main-window coverage and Plugin Manager construction.

### Remaining validation limits

The eight existing opt-in real-log gates skipped because `SILVERSTAR_CURRENT_LOG_ROOT`,
`SILVERSTAR_SS0007_PATH`, `SILVERSTAR_SS0014_ROOT` and `SILVERSTAR_SS_TEST_0_ROOT` were not supplied.
No CF-33 physical touchscreen/stylus or hardware-driver acceptance is claimed. No known remaining
failure in the executed GUI, comparison, replay or export regression suite.

## 2026-09-25 — Four-group NIS, receiver GNSS closure, and display/export follow-up

This round changes only FLP Python, UI, tests and documentation. Recorded GNSS NIS/update
diagnostics now show Position EN/U and Velocity EN/U separately, with matching 2D/1D references;
legacy aggregate channels remain available for compatibility. GNSS Integrity computes an
analysis-only receiver-native position/velocity closure over 1/2/5/10 s trailing windows.
Flight/3D/GIF visual bounds use final successful landing candidate start when recorded; State
Estimation keeps Landing Confirmed and Data Explorer keeps all source records. The shared
TimeRange is visible only on Flight and State Estimation, with three handles and one-window
shift buttons. Both GUI theme modes and resolved export theme are recorded in the manifest.

Local read-only 2026-09-24 input pair was exact-paired with decoder 1.2:

- `D:/stm32_project/SS_0_5_TEST_2/LOG/SS0000.BIN`: 1,103,483 B, SHA-256
  `b20da913ffc599a92eafb8191841b4bdd1d1e81277ed5ffc39ce81384c986d9b`, 369 GNSS_NATIVE epochs.
- `D:/stm32_project/SS_0_5_TEST_2/LOG/SS0001.BIN`: 28,296,615 B, SHA-256
  `d5297f7a901684922360e0c3158c6759d9725755df5959dd0018059bc9b7def3`, 9,518 GNSS_NATIVE epochs.
- `D:/stm32_project/SS_0_5_TEST_2/HARDWARE/SS_0_5_TEST_2.ssdecoder`: SHA-256
  `3fc7000fc027b153b604596850d516eb7960892afc22a6c6681da9d57a95d7bd`.

Both opened with `data_quality.status=clean`. These accessible files lack the `(3)` suffix
from the requested filenames; no identity with those unavailable copies is assumed. Closure
statistics below use metres. Coverage is valid trailing windows / eligible epochs; EN uses
`|Residual_EN|`, U uses `|Residual_U|`. No value is a formal NIS or firmware gate.

| Log | Window | EN valid / coverage | EN median / P95 / max | U valid / coverage | U median / P95 / max |
|---|---:|---:|---:|---:|---:|
| SS0000 | 1 s | 313 / 90.99% | 1.055 / 1.953 / 2.138 | 313 / 90.99% | 1.383 / 4.400 / 4.809 |
| SS0000 | 2 s | 263 / 82.45% | 2.217 / 3.521 / 3.648 | 263 / 82.45% | 1.458 / 8.427 / 8.832 |
| SS0000 | 5 s | 148 / 60.66% | 4.817 / 6.291 / 6.384 | 148 / 60.66% | 1.400 / 5.190 / 5.329 |
| SS0000 | 10 s | 23 / 19.33% | 10.152 / 10.509 / 10.544 | 23 / 19.33% | 4.375 / 4.749 / 4.783 |
| SS0001 | 1 s | 9493 / 100.00% | 0.144 / 1.069 / 2.244 | 9493 / 100.00% | 0.181 / 1.240 / 4.774 |
| SS0001 | 2 s | 9468 / 100.00% | 0.250 / 2.101 / 3.732 | 9468 / 100.00% | 0.304 / 2.354 / 8.661 |
| SS0001 | 5 s | 9393 / 100.00% | 0.560 / 5.330 / 7.258 | 9393 / 100.00% | 0.611 / 5.388 / 9.765 |
| SS0001 | 10 s | 9268 / 100.00% | 0.982 / 10.416 / 11.719 | 9268 / 100.00% | 1.000 / 11.178 / 17.329 |

The final SS0000 export smoke generated three categorized `GNSSIntegrity/` PNGs plus
`Summary_ZH.csv`, `Summary_ZH.txt` and selected-window sample CSV: **6 files, 0 failures**.
The manifest recorded `theme_mode=follow_ui`, `resolved_theme=dark`. Generated smoke files
were removed after verification; the BIN and decoder were never modified or copied into Git.

Verification: `ruff check src tests` **passed**; product and tracked test Python compilation
**passed**; full pytest **351 passed, 9 opt-in external-data skips** in 234.36 s. Focused
GNSS Integrity export tests passed in both languages; landing, time-range, NIS and theme
regressions passed. No commit, push, tag or release was made.

## 2026-09-25 — FCCG/FLP GNSS position self-check joint candidate

**Joint decision: 存在阻塞，不应使用该候选固件.** FLP UI, diagnostics and independent export are implemented and regression tested; the enabled-KF6 firmware resource gate and same-version replay/log contract remain incomplete. FCCG `main` HEAD `f062e078f18fac847453a6039ca104555683f348`, FLP `main` HEAD `dc5a36dd932768137387e80d9f7bd93dfb5a8b01`; both contain this round's uncommitted changes. Frozen GSHC `main` HEAD `cbee51e1f259d56a8e9dcdb7c3b236f9b054e4fb` is clean. No push, release, flash, shutdown, or physical output occurred.

FLP's receiver-position self-check display now aligns position/velocity by their independently resolved effective times, computes causal trailing windows, requires valid endpoint positions and continuous bounded velocity interpolation, and retains the velocity integral and reference across a short invalid-position run. It exposes warmup, position/velocity invalidity, time/sequence/source discontinuity and reference-segment markers without filling missing samples with zero or future data. The page remains five single-chart tabs with separate calculation/display windows and unit-correct accuracy plots. GNSS fusion detail routes Recorded directly from logged GNSS updates, switches to KF6 replay diagnostics when present, and falls back with explanation for Pure INS; source identity, four named groups, NIS vs non-execution, and empty-range counts/reasons are explicit. The independent Export Settings source selector freezes selected source/result and time/topic/theme snapshot before background export; the manifest records requested/resolved source and result IDs, algorithm revision/parameters, log/decoder hash, time ranges and topics. It does not mutate the active GUI source. Prior 30 s paging/full-trajectory GIF compression and landing visual cutoff regressions remained in the full suite.

The standalone user-visible `Integrity-assisted` ReplayMode was removed. Old persisted results with that provenance/configuration are explicitly rejected rather than silently reclassified as faithful KF6. A revision-0 KF6 log defaults self-check off in recorded replay; revision-1 requires the complete 20-field self-check parameter group. FLP mirrors FCCG's names/types/ranges/defaults; the complete table and formula are in FCCG `docs/ALGORITHM_PARAMETERS.md`. New enabled KF6 replay currently raises the localized `kf6_integrity_replay_not_implemented` error. The old internal prototype code is not presented as a faithful replacement. Thus there is no enabled new-log faithful replay or genuine old-log new-strategy What-if result. No `.ssdecoder` is rewritten to invent missing parameters.

### Read-only real-input acceptance

Exact-paired accessible inputs are `D:/stm32_project/SS_0_5_TEST_2/LOG/SS0000.BIN` (`b20da913ffc599a92eafb8191841b4bdd1d1e81277ed5ffc39ce81384c986d9b`), `SS0001.BIN` (`d5297f7a901684922360e0c3158c6759d9725755df5959dd0018059bc9b7def3`), and `HARDWARE/SS_0_5_TEST_2.ssdecoder` (`3fc7000fc027b153b604596850d516eb7960892afc22a6c6681da9d57a95d7bd`); paired `SilverStar.ssproject` SHA-256 is `9d60045175d4df9980a583b5a4e194980e0362df4f6b70305c032b347f01f35a`. Hashes remained unchanged before/after analysis. Their names omit `(3)`; no identity with missing copies is claimed.

At 5 s, SS0000 has 228 valid horizontal rolling values among 368 consumed epochs. Its initial warmup is task +0.019–4.989 s (125 epochs); the initial endpoint-invalid band is +5.029–5.274 s (7); valid +5.309–11.120 s (146); the native horizontal-position invalid period yields endpoint-invalid +11.160–11.441 s (8); and the **tail is valid** +11.481–14.728 s (82), without another 5 s warmup. Its cumulative reference resets once at initialization and does not silently restart during the short invalid-position run. SS0001 has 9385 valid windows among 9517 consumed epochs, with initial warmup +0.012–4.981 s (125), initial endpoint-invalid +5.022–5.262 s (7), and valid +5.302–381.286 s thereafter. Median evidence age is 270 ms for both. Full horizontal/vertical rolling/cumulative reason intervals are in ignored `tests/.integrity-generated/real_log_gap_reasons.json`; they are display diagnostics, not firmware state evidence.

Both original revision-0 BINs were actually replayed through normal KF6 with self-check disabled. Results are `APPROXIMATE` with firmware-build and fixed-lag validation warnings; they are not asserted to reproduce target x/P/q exactly. SS0000 replay output 1478 snapshots, raw-time endpoint horizontal closure 8.013 m, speed 1.679 m/s, 0 reanchors. SS0001 output 38206, closure 52.825 m, speed 0.870 m/s, 0 reanchors. Raw input hashes were rechecked. Full run metrics are in ignored `tests/.integrity-generated/real-replay/legacy-replay.json`. New-strategy endpoints, intervention times, P/error counts and visual-cutoff comparisons are unavailable because enabled replay is deliberately blocked. The approximately 1 m return-to-start description was not used for online selection or as full-trajectory truth.

### Executed validation and limitations

FLP full pytest: **379 passed, 9 skipped, 0 failed** (final run, 284.75 s). Nine skips are opt-in external-data gates; the two accessible BINs above were exercised by a separate read-only replay and gap analysis. Focused source/export selection and retired-mode tests passed. The generated **disabled** KF6 C SSLOG golden round-tripped with its matching decoder into FLP (1 passed); enabled C golden parses, but the enabled replay is correctly rejected. `ruff check src tests --no-cache`, `compileall -q src`, and `git diff --check` passed. No raw log, generated executable, or complete export package was committed.

FCCG generated-project Power of Ten and architecture checks: enabled/disabled KF6 each **6157 checks, 96 C files, 2308 functions, 0 failures**, architecture **262/0**; Fusion=None **5786 checks, 93 C files, 2173 functions, 0 failures**, architecture **262/0**. All six Release/Debug images linked and stack reports passed, but enabled KF6 artifact-check failed: main SRAM Release **113,216/102,400 B**, Debug **113,240/102,400 B**. Disabled KF6 and Fusion=None artifact gates passed. Host KF6 matrix runs each reached **68 executables, 4,386,469 checks, 0 failures**; Pure INS **66 executables, 4,352,291 checks, 0 failures**. FCCG full pytest **425 passed, 1 skipped, 1 failed**; its failure is the enabled artifact budget. The first final Host rerun was interrupted by two extra test-only decoder copies in project roots, violating the Host test's single-decoder precondition; those copies were moved to the ignored matrix parent, with no source/checker edit. Gate details, stack/Flash/CCM numbers, commands and exact failures are in FCCG `VALIDATION.md` and the ignored `tests/.integrity-generated/final-matrix` logs.

The new per-epoch versioned decision/transaction record and C→new-log→FLP parity test are absent; consequently record bytes/s and queue impact of that proposed stream were not measured. Existing Host logger normal/overload HWM is 76/44 and 80/43 respectively, and is only a host scheduling model. After loss of an independent trusted reference, the firmware may remain conservatively RECOVERING; a freshly created local reference must not be treated as proof that a stable absolute position bias disappeared. Full healthy/high-dynamic/biased-position real-flight discrimination, target CPU/rate, and field hardware behavior remain unverified. The candidate must not be used for field firmware until the resource gate and those replay/recovery contracts pass.

Reproduce FLP checks from this repository root: `.venv/Scripts/python.exe -B -m pytest tests -q --basetemp=tests/.integrity-generated/full-suite-work`, `.venv/Scripts/python.exe -m ruff check src tests --no-cache`, `.venv/Scripts/python.exe -m compileall -q src`, `git diff --check`. The C golden test requires the exact generated disabled KF6 `.sslog` and matching decoder, as described in `tests/test_joint_c_golden.py`. FCCG matrix commands and expected enabled artifact failure are recorded in its `VALIDATION.md`. No claim of flight safety certification is made.

## 2026-09-26 — GNSS integrity simplification, revision 2 (FLP)

This section supersedes the 2026-09-25 integrity-candidate behavior above. FCCG and FLP were edited; GSHC was frozen. FLP now replays the receiver-native, horizontal, constant-state GNSS position/velocity closure defined by FCCG revision 2. Position and velocity from one GNSS_NATIVE solution epoch are compared before KF6 fixed-lag scheduling. A short invalid-position run leaves velocity integration and its anchor intact; a velocity/sequence/time/source break creates a visible reference reset. After a break in SUSPECT or REJECTED, a new monitoring anchor does not by itself restore NORMAL. The displayed closure is GNSS internal consistency, not external position truth.

Recorded Configuration accepts revision 0 with integrity off and revision 2 with the recorded ten parameters. Revision 1 is explicitly rejected as an unsupported legacy candidate. A revision-0 What-if can explicitly enable revision 2. The normal KF6 replay path applies Pos EN admission and R scaling before its scheduled update, and retains the existing KF6 group-reacquisition mechanism. Old persisted Integrity-assisted projects/results are rejected; the product ReplayMode exposes only Recorded Configuration, Offline and What-if. Historical optional assistance implementation files remain unreachable; an automatic review denied their deletion and no alternate deletion was attempted.

State Estimation now has six tabs: State Uncertainty, Innovation, NIS, Measurements, GNSS Position Integrity and Landing. NIS includes a compact four-group Accepted/Soft/Rejected/P95/Latest summary; the epoch table and large GNSS fusion detail table were removed. Measurements has two X-linked, left-aligned plots (input/effective sigma and receive-age/fixed-lag timing). GNSS Position Integrity has exactly three pages: horizontal position versus integrated-velocity displacement, horizontal closure and thresholds/states, and receiver hAcc/vAcc/sAcc/satellites. It starts at the first valid anchor with no fixed five-second warmup. Independent export freezes source/result/parameters/range/theme/language at start and emits only GNSS_Position_Vs_Integrated_Velocity, GNSS_Horizontal_Closure_Error and GNSS_Receiver_Quality; current GUI source may differ.

Cross-language evidence: the 600-epoch C/Python stream fixture matched state, actual Pos EN mask, R scale, closure, reason, reset and evidence at every epoch. The revision-2 C SSLOG golden from `../SilverStar_FCCG/tests/.tmp_final_matrix/KF6IntegrityOn` contains actual GNSS_NATIVE and GNSS_MEASUREMENT records plus two transition-only EVENTs. Its matching generated decoder and FLP replay passed the joint test for state/mask/R and x/P/q, Pos EN update result and NIS; a changed revision-2 What-if threshold changed the disabled-position count as expected. No per-epoch integrity record was added.

Read-only exact-paired inputs were `D:/stm32_project/SS_0_5_TEST_2/LOG/SS0000.BIN`, `SS0001.BIN` and `HARDWARE/SS_0_5_TEST_2.ssdecoder`. Their SHA-256 hashes before and after replay matched: SS0000 `b20da913ffc599a92eafb8191841b4bdd1d1e81277ed5ffc39ce81384c986d9b`, SS0001 `d5297f7a901684922360e0c3158c6759d9725755df5959dd0018059bc9b7def3`, decoder `3fc7000fc027b153b604596850d516eb7960892afc22a6c6681da9d57a95d7bd`. These accessible files do not have the `(3)` suffix; identity with absent copies is not claimed. The old revision-0 replay and explicit revision-2 What-if yielded:

| Log | GNSS consumed | Old final horizontal (m) | Revision-2 What-if final horizontal (m) | First SUSPECT (mission s) | First REJECTED (mission s) | Pos EN disabled |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SS0000 | 368 | 8.013 | 8.013 | none | none | 0 |
| SS0001 | 9517 | 52.825 | 8.380 | 10.1494 | 15.1604 | 9139 |

Both real-log replays are `APPROXIMATE` with firmware-build and fixed-lag cross-validation warnings; endpoint displacement is an output of replay, not truth or an algorithm input. No return-to-start target was used to tune the online decision. The original BINs and decoder were not changed. Detailed counters and hashes are in `tests/.tmp_revision2_real/results.json`.

Final FLP regression: **385 passed, 8 skipped, 0 failed**; the skips require unrelated manually supplied historical inputs (SS0007, SS0014, SS_TEST_0 or the separate current-log gate). `ruff check` on product source and top-level test modules, `compileall` on source, and `git diff --check` passed. No physical UI device, flight truth or target timing was tested. No commit, push, tag, release, flash, physical output or shutdown was performed.

### Joint closeout

FCCG's final complete regression passed 426 tests with one pre-existing skip and zero failures after syncing the protocol reference overlay and routing Save As through the workspace safety layer's bounded Windows replacement retry. The three generated project matrices each passed Release/Debug artifact, stack, memory, architecture, Power of Ten and Host gates. KF6 ON/OFF Power of Ten: 6,133 checks each, zero failures; Fusion=None: 5,792 checks, zero failures. FLP remained at 385 passed, 8 skipped and zero failures, with C golden parity and real-log What-if exercised. Joint software decision: **READY FOR CONTROLLED FIELD RETEST**. The FCCG report records the small RAM margins and target-measurement limits. GSHC was unchanged; no push, tag, release, flash, physical output, or shutdown occurred.

## 2026-09-26 — SilverStar_FLP 0.0.4 GUI cleanup

This round starts from FLP `ce743f4a8ae4043556a3232cffd9a4087347df78` and paired FCCG `def2fb99f565f71a6be7f954f6227d87e5d2c6d4`. FLP product version is **0.0.4** with `src/silverstar_flp/app/version.py` as its sole authority; `src/silverstar_flp/version.py` only re-exports it. Package import, About, CLI `--version`, pyproject dynamic metadata and the staged test wheel resolve to 0.0.4. Firmware GNSS integrity remains revision 2. This GUI/version round did not change navigation thresholds, KF6 math, landing decisions or SSLOG wire layout.

### Product GUI and export

State Estimation still has one top-level NIS tab. Its `StandardComboBox` has exactly NIS Curve and Four-Group Statistics. The full NIS chart and an independent six-column Pos EN/Pos U/Vel EN/Vel U table occupy separate `QStackedWidget` pages. Statistics explicitly use the current TimeRange. The chart retains dimensional thresholds, Recorded/Selected comparison and Soft/Hard references. GUI tests cover selection, range counts, Reset Charts, touch scrolling, 1000×700 and approximately 200% text scaling.

GNSS Position Self-Check uses one `StandardComboBox` with exactly Horizontal Consistency, Vertical Consistency and GNSS Receiver Information; it has no inner QTabWidget. Horizontal displays the norm of receiver-native ΔP_EN minus integrated V_EN, error/recovery thresholds, recorded revision-2 transition EVENTs when available, visibly labeled offline states for old logs, and reference resets. This internal consistency is not external position truth. The vertical plot shows signed ΔU minus trapezoidally integrated receiver-native V_U and a 0 m line. It continues integrating through short Pos U invalid intervals and resets its reference on actual velocity, timestamp, sequence, source, epoch or gap breaks. It is explicitly offline-only and does not gate onboard integrity, KF6 or NIS. Receiver information has hAcc/vAcc in m, sAcc in m/s and satellite count in a separate linked plot. Offscreen zh/en × Light/Dark tests exercise the three pages.

The Landing page now reads only recorded `LANDING_DIAGNOSTIC` transactions and the confirmed LANDING event; the recompute button, signal and MainWindow recompute path were removed. It always shows the complete mission regardless of global 0–30 s TimeRange, uses `candidate_start_timestamp_us` and the actual confirmed timestamp for its summary, and presents explicit disabled/no-data messages. On the read-only SS0000/SS0001 logs, it showed **8/304** transaction rows even with 0–30 s globally selected. The former estimated/confirmed times were **11.763/14.767 s**, the latter **378.312/381.315 s**; both had an approximately 3.0 s recorded window. The new C golden has no Landing record and correctly shows the no-data state; that fixture cannot establish a positive Landing case.

Independent export still freezes its own source/result/range/theme/language. Its GNSS Integrity category now emits only `GNSS_Horizontal_Consistency_Error`, `GNSS_Vertical_Consistency_Error` and `GNSS_Receiver_Information`, with localized item names and no old duplicate plot classes. Recorded Landing export, 30 s PNG pages, full-range GIF compression and visual cutoff regressions stayed in the full suite. zh/en translation key sets match and direct product references resolve.

### Compatibility and test evidence

The new FCCG 0.0.12 KF6 Integrity ON generated project produced a real C-codec **13,513-record** SSLOG and matching 0.0.12 `.ssdecoder`. Its header, CRC/framing and revision-2 replay passed the opt-in joint test, including Recorded vs replay, measurement timing, integrity state/admission/R, x/P/q, selected What-if and the new export manifest labels. The opt-in 600-epoch C/Python integrity parity test passed. The existing 0.0.10 revision-2 C golden also parsed and replayed with its exact old decoder. These synthetic fixtures do not establish target CPU timing or flight truth.

The read-only 0.0.10 `SS0000.BIN` and `SS0001.BIN` exact decoder pair imported with **11,823/301,192 records**, valid headers and **0 record CRC failures**. Revision-0 Recorded Configuration and explicit revision-2 What-if both ran. Input SHA-256 before/after remained: SS0000 `b20da913ffc599a92eafb8191841b4bdd1d1e81277ed5ffc39ce81384c986d9b`; SS0001 `d5297f7a901684922360e0c3158c6759d9725755df5959dd0018059bc9b7def3`; decoder `3fc7000fc027b153b604596850d516eb7960892afc22a6c6681da9d57a95d7bd`. The accessible file names lack the `(3)` suffix; identity with absent copies is not asserted. Old-log What-if remains marked APPROXIMATE and no return-to-start target entered the algorithm.

Final top-level FLP pytest: **371 passed, 10 skipped, 0 failed** in 300.95 s. The 10 skips are opt-in external-input gates; the new C golden, C/Python parity and two accessible real logs were separately exercised. Ruff on product source, tools and top-level tests passed; `compileall` and `git diff --check` passed. The staged 0.0.4 wheel is under `tests/.tmp_release_0_0_4_package/`; no package was published. The PytestCacheWarning was a local Windows cache-directory collision, not a test failure.

### Cleanup accounting

**Removed files:** `src/silverstar_flp/analysis/integrity_assistance.py`, `src/silverstar_flp/analysis/gnss_integrity.py`, `src/silverstar_flp/ui/offline_diagnostics.py`, `tests/test_integrity_assistance.py`, and `tools/integrity_assisted_field_analysis.py`. `GeoLocal_ToEnu` moved to `analysis/geodesy.py`; revision-2 stream imports it there.

**Removed dead code paths:** the old five-page GNSS Integrity plot layout and three obsolete export classes; Landing recompute button/signal/source rows; unreachable Integrity-assisted summary export/replay branch; 98 obsolete translation keys in each locale; and current-product documentation for retired diagnostics. A static regression rejects recurrence of retired UI feature strings. `tests/test_offline_diagnostics.py` remains because it tests active KF6 replay diagnostic options and source behavior, not the removed `ui/offline_diagnostics.py` widget.

**Retained legacy compatibility:** `analysis/landing_window.py` is reached by the public `RecoveryReplay_Run` → `analysis.recovery._Landing_Replay` path for approximate recovery replay, so it remains after the GUI button removal. `core/project.py` and `core/analysis_source.py` explicitly reject persisted Integrity-assisted configurations/results instead of silently reclassifying them. Revision-0 logs remain readable, revision-1 integrity is rejected, and fixed-lag/measurement-time/normal What-if infrastructure remains active. Historical VALIDATION/CHANGELOG entries retain their original version facts. The only remaining `0.0.2` matches outside historical reports are in historical `docs/Actual_Parameters_Validation.md`; there is no current runtime, manifest, package, CLI or UI identity at 0.0.2.

**Joint software decision: READY FOR CONTROLLED FIELD RETEST**, contingent on the FCCG matrix and complete regression described in its paired `VALIDATION.md`. GSHC stayed frozen. No commit, push, tag, release, flash, physical output, reset, clean or shutdown was performed.

## 2026-09-27 — joint ESKF15 / navigation revision 3 closeout

This new entry supersedes no historical result. FLP baseline is `c4605f4`; the
single runtime/package authority is now **0.0.5**, the minimum for new 35-record
decoders. Historical decoder 1.2 and KF6 revision 2 retain their meanings.
The FCCG-owned `navigation_v1.json` and both FLP copies have SHA256
`68d4e3edc6be4c110c4c973990c12a1464290d28e1c9254a51c96a1f41832b5e`.

### Implementation and compatibility

The registered ESKF15 plugin implements float64 nominal p/v/q/bg/ba, full 15×15
P, right multiplicative Hamilton scalar-first body-to-ENU attitude, independent
Jacobian checks, second-order Phi, positive-weight Simpson Q, Joseph update and
SO(3) right-Jacobian reset. Calibrated BODY half-interval input belongs to the
filter; it removes residual biases and applies coning/sculling exactly once.
The bounded delayed replay preserves body inputs and repropagates bias changes;
capacity, step-limit and callback failure roll back the transaction.

Quality revision 3 uses bounded satellite/R degradation, two native-epoch
10 s windows offset 5 s, 120 ms gap handling and 6 s evidence TTL. Each of five
groups tracks actual outer effective-fusion evaluation time; received or
internally replayed samples cannot reset that clock. The 2 s / 10 s policy is
degradation / INVALID without an unsupported automatic reset. MODEL_MISMATCH
is latched. Legacy revision-2 integrity remains separately reproducible.
Six obsolete KF parameters remain in historical/project snapshots but become
read-only for revision 3; its 30 effective parameters and R cap <=4 are explicit.
Out-of-range old configuration is rejected, not silently clamped.

New records preserve source, epoch, calibration generation and algorithm
identity. ESKF_INITIAL_STATE plus four complete initial P pieces supply the
numerical initialization; a legacy KF INITIAL_STATE is not required to invent
that state. Full-P pieces assemble by identity rather than adjacency. Initial
P always remains mandatory. Flight may explicitly disable periodic full P;
then cross-covariance comparison is **unavailable**, while nominal state,
P diagonals and measurement decisions remain compared. Enabled or unknown
periodic policy, missing/conflicting pieces, CRC/gaps or identity mismatch
prevent a FAITHFUL claim.

Unattempted operations have no defined innovation/NIS/effective R. C leaves
those wire slots zero, Python uses undefined values; only matching explicit
`admitted=0` and exact result code allow these diagnostics to be reported
unavailable. Physical validity, admission and result still compare exactly.
Attempted diagnostics keep strict numeric comparison; no tolerance was widened.

### Final commands and executed gates

All commands ran in this repository with `.venv/Scripts/python.exe`,
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=src`, `QT_QPA_PLATFORM=offscreen`.
The opt-in C tests used `SILVERSTAR_FCCG_ROOT=D:/python_software/SilverStar_FCCG`
and `SILVERSTAR_ESKF_GENERATED=.../tests/joint_rework_20260927/verified_matrix/eskf15_flight`.

| Gate | Final command / scope | Result |
|---|---|---|
| Complete product suite | `python -m pytest` on every top-level `tests/test_*.py`, `-q --basetemp=tests/joint_rework_20260927/final_complete_temp -o cache_dir=tests/joint_rework_20260927/final_complete_cache` | **426 passed, 9 skipped, 0 failed; 382.54 s; exit 0** |
| Style | `python -m ruff check src tools` and every top-level `tests/*.py` | exit 0 |
| Syntax | `compileall` over src, tools and top-level tests; pycache prefix below tests | all true, exit 0 |
| Whitespace | `git diff --check` | exit 0 |
| Real logger product closure | `python tests/joint_rework_20260927/audit_actual_backend_logger.py` | exact import / FAITHFUL comparison / GUI / export, exit 0 |
| Offline package | `python tests/joint_rework_20260927/package_final_smoke.py` | offline no-deps/no-index wheel build and extracted-package GUI/plugin smoke, exit 0 |

The nine skips are unchanged opt-in historical inputs: one
`SILVERSTAR_CURRENT_LOG_ROOT`; one old joint C golden requiring its separate
generated project/BIN; three `SILVERSTAR_SS_TEST_0_ROOT`; three
`SILVERSTAR_SS0007_PATH`; one `SILVERSTAR_SS0014_ROOT`. Their absent inputs are
not replaced. All newly introduced ESKF C/codec/window/delay/golden tests ran.
The five supplied SS_0_5_TEST_3 logs were independently processed in this task.

Compact logs, numerical JSON, hashes and inspected GUI PNGs are in
`tests/joint_rework_20260927/evidence_final/`. The clause-by-clause matrix is
`tests/joint_rework_20260927/REQUIREMENTS_TO_TESTS.md`.

### C / Python / actual log closure

Four direct actual-C versus float64 scenarios execute 2000 predictions and
1000 grouped updates. Maximum absolute p/v/q/bg/ba/P/NIS differences are
`1.0312e-5 / 9.4158e-6 / 7.5329e-6 / 5.6799e-7 / 5.1747e-7 / 3.1266e-6 / 1.6924e-5`.
The unchanged tolerance is absolute 2e-4, relative 3e-4, selected for float32
rounding at sub-mm/sub-mrad scales; discrete decisions are exact. Independent
finite-difference Jacobians and analytic dynamics provide a separate oracle.
Delayed 100/250 Hz tests cover 200 epochs and 18 mid-interval events, 600 ms
history and caller-owned 192-entry C buffer; max differences are 3.17e-6 and
5.39e-6, max C replay work 72 and 178 steps. The native-window test covers
750 samples/12 completed windows, max R-scale difference 4.87e-7.

The final **659-record** direct actual-C-core/codec fixtures pass both ordered
and deliberately interleaved BODY/P arrival cases against the final decoder
SHA256 `cff101c71022b6ecd05dba1d37c84f717f446215e79b952cabedd274a74aad36`.
Maximum full-P difference is 1.633e-6. Missing P, unknown policy, altered bias,
calibration mismatch and admission mismatch remain explicit negative tests.

A separate **491-record / 58,931-byte** actual production bridge uses real NONE
calibration, production FlightTask calibration snapshot, generated descriptor,
production LoggerTask header/append/flush, actual ESKF backend and LoggerBus.
Its BIN hash is `a7c93727e53b9b6220479137a6e04f0ff51729da4f690861bf4beb127469549c`;
exact decoder hash is `15c53b534e3c5f643f765a2468b9870015d440875224abec263a5115bb6101d8`.
FLP reports clean framing/CRC/sequence and FAITHFUL, with maximum p/v/q/P
differences `9.512e-9 / 1.2761e-7 / 8.663e-8 / 7.302e-7`. Per GNSS group two
unattempted rows, and one baro row, have numeric diagnostics explicitly
unavailable after exact admission/result checks. Actual input hashes are
unchanged. This bridge uses synthetic input/clock and a host fwrite/fflush sink;
separate FCCG FatFs/DMA tests cover storage timing/admission. Neither is flight.
Earlier marker-only throughput BINs were correctly rejected for absent READY
calibration and were not relabeled as faithful data.

The real BODY-only bridge opened the actual ESKF state-estimation GUI, showing
Recorded and Replay bias XYZ and 15-dimensional uncertainty. Inspected 1000×700
en/light and zh/dark snapshots are retained. Product export generated **361
files, zero failures**; two absent legacy corrected-IMU plots are explicitly
skipped, without synthesizing legacy IMU data from half-interval means.
The full suite additionally exercises GUI switching during an independent
explicit-source export, cancellation/restart, category directories, GIF frame
duration, both languages/themes and existing text-scale/touch simulations.
These offscreen checks are not physical monitor/touchscreen validation.

The offline 0.0.5 wheel is 348,590 bytes, SHA256
`2c376ae831b155c3358b96881157cfb03fdaeba6593773ae1ad04d5242d4dabb`.
The unpacked package, not the source tree, loaded the ESKF plugin and bundled
contract/translations and started the GUI. No package was installed or published.

### Long counterexamples and five immutable logs

The 600 s correct-position / 0.2 m/s biased-velocity case executes 30,000
predictions, accepts all 6000 position attempts, and completes 118 windows with
R scale 1; no cumulative position ban occurs. The 300 s 1.2 m/s drifting-position
case has bounded R 1.44, 140 accepted / 2860 NIS-rejected position attempts and
ends INVALID. That is a retained fault outcome, not proof of drift correction;
the 10 m window threshold cannot detect arbitrary tiny drift. Severe tilt,
bad baro prediction, independent bad groups, all-aid-invalid, history bounds,
callback failure, invalid P and clipped/time-invalid IMU cases also run.

All five original BINs and the original exact decoder were read-only and
SHA256-checked before/after. Per-log reports retain A recorded output,
B old-revision replay, C revision-3 KF6 What-if and D ESKF15 What-if. Old same-
revision replay remains APPROXIMATE wherever recorded parity is incomplete.

| Log | KF6 old / revision-3 replay | ESKF15 final health | Interpretation |
|---|---|---|---|
| SS0000 | completed, approximate | INVALID | Severe drift and long rejected-fusion intervals retained. |
| SS0001 | completed, approximate | HEALTHY | Health reflects available internal evidence, not external accuracy truth. |
| SS0002 | both fail `gnss_origin_unavailable` | INVALID | No origin was inserted; no GNSS fusion evidence. |
| SS0003 | completed, approximate | HEALTHY | Four-way differences and complete diagnostics retained. |
| SS0004 | completed, approximate | INVALID | Severe drift / long rejection retained; no performance PASS. |

Four-way plots/results live under `four_way_comparison/SS0000` through `SS0004`;
ESKF q/bias/all-15-P diagnostics under `five_logs_contract_final/`. All five D
outputs are finite, P minimum eigenvalues positive, q norm error below 2.3e-16;
these mathematical properties do not establish flight performance. The logs
lack the new raw-body contract/actual range/clip flags and trusted native time.
Legacy source identity is unknown/single-canonical unless real NAV_QUALITY
supplies it; no source is guessed. New-policy runs are approximate What-if.
No endpoint truth or future sample corrected the online algorithm.

FLP implementation status: **IMPLEMENTATION_COMPLETE / SOFTWARE_GATES_PASS**.
Joint target resource/driver/readiness decisions belong to the paired FCCG and
GSHC reports. Physical status remains **HARDWARE_UNVERIFIED / NOT_FIELD_VALIDATED**;
successful joint software gates permit the next JY901B+M9N bench validation,
not a launch-readiness claim. No original input, external installation, hardware,
flash, physical output, or NVM was modified by FLP work. Existing untracked
`tests/.tmp_*` data were preserved. Large BIN/NPZ/build caches stay local with
compact hash manifests; root coordinates authorized repository pushes.

### Final independent-review delta

The read-only cross-repository review found that C BODY prediction previously
trimmed old history before rejecting a new CLIPPED/invalid input. At exactly
600 ms, a rejected sample left live state unchanged but moved the authoritative
anchor by 10 ms. The final `navigation_eskf_replay.c` first plans the prefix and
replays it into the existing `working` scratch; only successful core prediction
allows anchor/history commit. No full-state/global buffer or ABI was added.
Scratch and genuine failure counters are distinguished from authoritative
live state, anchor, body/event storage and counts.

After this C-only implementation change, **20 targeted tests passed in 18.82 s,
exit 0** (`evidence_final/transaction_delta.log`). They cover CLIPPED, NaN,
live non-PSD and prefix non-PSD failures at the trim boundary with byte-identical
authoritative state/history; successful two-prefix commit and removal of its
old event; 192-slot overflow rejection; existing C/Python math, 100/250 Hz delay,
window, final two decoder/codec golden cases and identity policies. Ruff and
diff checks pass. The earlier 426-pass full suite is retained with its actual
scope; it is not falsely relabeled as a later full rerun. Firmware health/source
review findings and final target gate reruns are recorded by FCCG's owner.

### Final bridge refresh and pending quality integration

The latest frozen production bridge remains **491 records / 58,931 bytes**.
BIN SHA256 is
`253dd88e57bb7f672ad2ed174979f19f632cee58e71a36eb6d7452455bc20e07`;
exact decoder SHA256 is
`2c58fa36a1e40a27801e775b02640f6a460df00d12b58a0640bc3331b4102c46`.
A fresh current-source product import/replay/export completed with exit 0 in
`tests/joint_rework_20260927/bridge-final-review.log`. Framing, CRC, sequence and
decoder validation are clean. The product reports EXACT / FAITHFUL numerical
replay; the 99 physical/admission/result decisions agree exactly. Maximum
position / velocity / quaternion / complete-P absolute differences remain
`9.51171e-9 / 1.27610e-7 / 8.66238e-8 / 7.30176e-7`.
Unattempted numeric diagnostics retain the explicit unavailable handling
specified above; attempted values use the unchanged strict comparator.

A separate exact-timestamp health audit compares **20 ESKF15_STATE plus 20
NAV_QUALITY samples: 40/40 equal, no missing sample**, including WARMUP, HEALTHY
and DEGRADED. Health is not silently included in the existing numerical-parity
claim. The approved supervisor change recognizes actual SOFT results, which is
sufficient for this fixture's changed C health samples. It does **not** establish
coverage of an ACCEPTED update with R>1 whose multiplier is still absent from
one pending consumer path. The repeated BODY-only product export produced
361 files, zero failures, and the same two explicit unavailable legacy
corrected-IMU plot skips. No equivalent legacy IMU inputs were fabricated.

Old bridge outputs and four pending product files were SHA256-protected before
and after: **1,086 files unchanged**. Full audit lists remain local under
`bridge_final_review/protected_before.json` and `protected_after.json`; compact
results, the separate health audit and protection-summary hashes are listed in
`COMMIT_EVIDENCE_LIST.txt`. Earlier hashes and results above retain their original
scope and were not overwritten or relabeled.

Current final-review state is **QUALITY_INTEGRATION_PENDING_APPROVAL**, superseding
the earlier implementation-complete statement for these newly found cases.
Two already approved changes exist: the common supervisor validates finite
positive gain and supports quality-aware degradation; KF6 exposes an opt-in
finite/nonzero-float32-gain guard with legacy-default behavior preserved.
Existing focused tests passed 38 cases in 10.68 s after those two changes.
The four remaining integration files (KF6 plugin/fixed-lag, revision-3 policy
adapter, ESKF15 plugin) remain unchanged after automatic approval review rejected
their writes. Root has an outstanding user confirmation; no retry or patch
application was performed. Thus the guard is not yet enabled by the revision-3
KF6 product path, and total variance scales are not yet fully wired to health.
This bridge pass does not close those missing branches.

The earlier 426-pass full suite and five-log results are historical evidence,
not a full rerun of this partial integration. In particular, the old SS0001/3
HEALTHY labels are not final acceptance under the pending scale-aware policy.
Nominal ESKF arithmetic is expected unchanged because health is observational;
KF6 numerical changes should be confined to zero/nonfinite actual-gain cases.
These are expectations, not measured post-patch results. SS0002 origin failure
and the prior INVALID/drift outcomes remain visible. The exact four-file scope,
new regression cases, fresh five-log output directories, complete-suite commands
and offline package procedure are in
`tests/joint_rework_20260927/APPROVAL_VALIDATION_PLAN.md`.

### Authorized quality-integration final results

The user explicitly approved continuing FLP changes. The four pending integrations
are now applied; the preceding approval-hold status is historical. Revision 3
enables the actual finite/nonzero float32-gain guard through live filters, clones,
checkpoints and explicit epoch restoration. Revision 2 retains its original
default arithmetic/admission. Zero and nonfinite K fail before x/P mutation;
a tiny nonzero K is not rejected merely because K*K underflows. The effective-
fusion clock requires finite positive gain and an actually accepted result.

Health receives actual satellite, PosEN-only window and robust variance factors.
Ordinary ACCEPTED uses robust factor 1, avoiding a float32 effective-R/base-R
roundtrip slightly below 1. SOFT results retain their actual robust factor.
No threshold or covariance gate was loosened. Physical rejection, independently
required groups, initial unknown quality, timeout priority and callback/replay
ownership remain explicit. `tests/test_navigation_quality_gain.py` adds 52
focused cases. The final focused run passed 90 tests; its four deliberately
injected NaN/Inf matmul warnings were subsequently asserted locally with
`pytest.warns`. The initial fixture failures and logs remain preserved.

The final complete suite passed **483 tests, 9 skipped, 373.07 s, exit 0**.
A prior 483-pass run and intermediate wheel were retained before restoring
three acceleration-bias unit strings to their original UTF-8 m/s² spelling.
That correction is display metadata only; all five long runs serialize numeric
arrays/parameters/diagnostics without these unit labels, so their numerical
evidence remains valid. Final unit/spec assertions and the complete suite run
on the corrected source, and the final wheel below contains that source.
No warnings occur in that final run. Skips are the unchanged optional external
fixtures: current-log (1), old joint C golden (1), SS_TEST_0 (3), SS0007 (3),
SS0014 (1). The new C oracle, native history/window tests and both 659-record
ordered/interleaved actual-codec fixtures all ran. Full source/tool/top-level
test Ruff and source compileall passed. These results supersede the earlier
partial-integration software status; that earlier evidence was not overwritten.

Fresh KF6 revision-3 and ESKF15 regressions read all five original BINs with the
original exact decoder. SS0002 KF6 still fails `gnss_origin_unavailable`.
All four successful KF6 runs preserve all **165 existing arrays** exactly.
ESKF SS0000/1/3/4 preserve all **141 non-health arrays** each; SS0002 has 45
such arrays because GNSS measurements are absent. All are exactly equal (including
nominal state, q/bias/P and measurement diagnostics, with NaNs compared in place).
Health arrays are compared separately, and newly added KF6 health channels are
compared to the saved old supervisor archive. No new diagnostic metadata is
misrepresented as an unchanged old field.

| Log | KF6 final health | ESKF previous → final | KF6 / ESKF changed health epochs |
|---|---|---|---|
| SS0000 | INVALID | INVALID → INVALID | 117 / 130 |
| SS0001 | DEGRADED | HEALTHY → HEALTHY | 192 / 181 |
| SS0002 | `gnss_origin_unavailable` | INVALID → INVALID | unavailable / 0 |
| SS0003 | INVALID | HEALTHY → DEGRADED | 761 / 865 |
| SS0004 | INVALID | INVALID → INVALID | 1183 / 769 |

The full old/new health counts, first timestamps for every health state and
five-group longest-no-fusion durations are in `approved_quality_comparison.json`.
All ESKF longest-no-fusion durations remain identical. KF6 SS0001/3 VelU
initial gaps change from 280000 to 290321 us and 290000 to 304296 us:
the old offline-derived report started its supervisor at the first output,
whereas the current product starts at the actual navigation START epoch.
Formal immutable-log imports confirm those exact 10321/14296 us offsets in
`approved_quality_clock_basis.json`; no fusion/state outcome changed.
Other KF6 group maxima remain identical. SS0000/2/4 ESKF INVALID and severe
drift remain failures,
not performance PASS. SS0003 is now DEGRADED. Internal HEALTHY on SS0001 is not
external accuracy or flight readiness. The 73-file old-report/NPZ/plot hash
snapshot and all original input hashes remain unchanged.

The frozen actual production bridge remains clean and FAITHFUL numerically:
491 records; 99 measurement physical/admission/result outcomes exact;
40/40 exact-timestamp recorded/replay health values match. Its entire numerical
parity diagnostic object is identical to the previous audit; maximum full-P
error remains 7.30176e-7. BIN/decoder hashes are the final pair documented above.
Unattempted numeric fields are unavailable only after exact outcome comparison.
Export implementation and channels are unchanged; the prior 361-file product
export is retained rather than repeated.

The final offline 0.0.5 wheel is **349,169 bytes**, SHA256
`8526dff3f49dd1bc9f4722f73881e9357745b9d2a91068610c34487b3fdf7869`. Build and extracted-wheel GUI/plugin smoke both exit 0.
All 102 current Python/JSON product source files match the wheel extraction byte-for-byte.
No package was installed or published. New compact evidence is explicitly listed
in `COMMIT_EVIDENCE_LIST.txt`; large regression NPZ/JSON artifacts stay local with
hashes in `approved_quality_evidence/large_artifact_hashes.json`.

Current FLP status: **IMPLEMENTATION_COMPLETE / SOFTWARE_GATES_PASS** for the
authorized scope, with **HARDWARE_UNVERIFIED / NOT_FIELD_VALIDATED** unchanged.
No original data, hardware, NVM, physical output, flash, or shutdown was touched.
