# 产品、格式与证据身份

## 导航安装、实验估计器与任务阶段增量（2026-10-24）

本批在 `2ecd7a96` 之上修正胶囊含义：胶囊编辑有序任务阶段，原开伞规则恢复普通参数编辑。新流程以原生工程格式 22、`.ssmission` v2 和共享桌面解释器保存、校验、参考执行；GSHC/FLP 可展示同摘要的参考记录。安装文本框已移除，新安装采用固定导航点；无下标 xyz（兼容 XYZ）为箭体系，设备原生轴带 s_i 下标，世界轴标 E/N/U。实际位置图、24 种正交右手安装映射、磁力计入口和三种实验估计器的选择/生成已接通。

### 当前能力边界

- 安装位置 `runtime_applied=false`，尚无逐设备杆臂补偿。旧安装基准不自动平移/旋转；用户显式确认采用导航点也不会改变原数字。主 IMU 不强制位于 O。
- ESKF20/InEKF15/InEKF20 可选择、生成和实验构建；未验证时序降为警告，真实资源/参数/物理模型错误仍拒绝。新配置的软件验证标记默认 1，初始化确认仍为 0，旧显式值保留。数值内核未在本批改写；无 H7 整板 link、时序、电气或飞行验收。
- 任务阶段每个只有一个进入条件，最多 32 个顺序阶段；组合条件、分支、并发和循环待实现。START 与物理起飞默认分开，可显式合并，已定制的 START 阶段不会被静默删除。
- 解释器记录模拟动作请求，不产生硬件输出或确认开伞。trace 校验检查摘要、顺序、时间和进入/动作配对，不能证明输入条件、物理检测或板端执行。
- **自定义流程尚未绑定固件 owner、AIR 新消息或 SSLOG 新记录**；带该流程的固件生成明确拒绝。GSHC 的离线导入不改变 READY/START 权限，FLP 不回填 Recorded、不修改源日志。真实运行过程仍须由固件事件与快照报告，接入设计见[架构](MONOREPO_ARCHITECTURE.md)。

### 本批检查与复现

环境沿用仓库 `.venv`、Qt offscreen 与 Host GCC；所有案例均为合成输入，无硬件操作。证据保存在忽略目录，源码、测试和合同提交到仓库。后文 711/744 等是对应历史批次的结果，不能视为本次全套回归。

任务流程分组入口（仓库根目录，输出目录须不存在）：

```powershell
.\.venv\Scripts\python.exe -B tools/verify_navigation_baseline.py --group mission_scg --group mission_flp --group mission_gshc --output .work/mp013_recheck
# 公开工程 Schema、版本与启动检查；独立的新输出目录
.\.venv\Scripts\python.exe -B tools/verify_navigation_baseline.py --group root --group scg --output .work/mp013_schema_recheck
```

本次任务流程同一次分组运行 **61 passed**：SCG 50、FLP 5、GSHC 6，无失败/skip，证据 `.work/mp013_final2/summary.json`。包括真实 GUI 增删/排序/弹窗取消与保存、START 模式、生成拒绝、摘要匹配、数据缺口以及六个既有生成后 Host 调度场景。随后收尾发现公开项目 Schema 仍停在 21，补齐 22、安装 v2、任务阶段和安装轴定义；`schema_before.json` 保留新样例修复前被拒绝的结果。生产解析器额外补上非法安装轴类型的明确错误。

其它已执行检查（每份报告保留其各自源码身份，不拼接成未执行的全量回归）：

| 范围 | 结果 | 证据 |
|---|---|---|
| 最后 Schema/解析器增量：版本/桌面入口与 SCG | root 33、SCG 58，共 91 passed，无失败/skip | `.work/mp013_schema_final/summary.json` |
| 安装保存/恢复、实际磁力计声明和生成 | 42 passed | `.work/mproc013_20261024/fix_junit.xml` |
| 数学/源码隔离与新默认实验标记 | 12 passed | `.work/mproc013_20261024/isolation_junit.xml` |
| 最新下标标注、24 种右手映射、实际 GUI 编辑和保存重开 | 6 passed | `.work/mproc013_20261024/final_subscript_junit.xml` |
| JY901B 安装预设和新生成资源的严格 Host 编译/执行 | 7 passed | `apps/SCG/.work/mp013_compat/fix_junit.xml` |
| GSHC 磁预览与已有校准几何 | 3 passed | `.work/mproc013_20261024/notation_fix_junit.xml` |

前次较宽增量运行 `.work/mp013_final/summary.json` 为 root 33、SCG 45、mission_scg 47、mission_flp 5、mission_gshc 6 项通过，之后又调整了标注、边界和 trace 校验，故不将该报告称为最终源码的完整回归。Schema 与安装轴类型的最后增量另运行 `root`/`scg`，结果见 `.work/mp013_schema_final/summary.json`。

初次增量运行的失败报告保留：安装 GUI 测试临时目录超出应用策略；磁声明的头文件单元夹具缺少维护通道；JY901B Host 链接夹具缺少 CubeMX UART handle；磁预览旧断言仍期待无下标轴名。修正测试作用域和真实 Host 资源夹具后重跑，未放宽生产资源/时序校验。UART handle 仅在 Host 夹具翻译单元中私有定义，不进入固件。

九阶段合成输入实际通过 `tools/replay_mission_process.py`，最终源码重跑输出 `.work/mp013_schema_final/uncontrolled_demo.ssmissiontrace`：9 个阶段、complete=true、hardware_actions=0。浅/深主题的最终真实 Qt 截图为 `.work/mproc013_20261024/*_notation_final.png`；截图中的安装数字为独立 QA 合成数据，不写入正式样例。

## 离线基线收口（2026-10-24，H7 硬件待就绪）

基线提交为 `54baba43`。之后飞行配置快照基础保存为 `c5a73382`；当时同一入口共 **744 passed，另 3 subtests passed**，9 组均退出 0，无 skip；证据在 `.work/ss013_20261024_final/summary.json`。源码哈希在该次运行期间未变化。随后胶囊界面另做针对性回归，见下节；没有把多次选组结果拼成一次未执行的全量通过。功能范围见[飞行配置首批](MONOREPO_ARCHITECTURE.md)。下列 711 项是完成基线时的结果，保留其检查范围与硬件待测清单。

### 旧触发规则胶囊增量检查（2026-10-24，历史结果）

`.work/caps013_20261024/summary.json` 记录 root 33、SCG 45、mission_scg 34 项均通过。随后补充胶囊编辑后的原生保存/重开和完整窗口中英文、浅深主题、960/1440 宽度检查，最新 `mission_scg` **34 passed**，证据在 `.work/caps013_20261024_final/summary.json`。该组含实际参数到 C 宏/精确 decoder、快照拒绝和故障保存、弹窗取消/精度、增删恢复、schema 扩展、不可用/必选约束，以及六个生成后的 Host 调度场景。

旧 GUI 兼容检查的命令在 `apps/SCG` 下执行（临时目录必须在该应用的 WorkspacePolicy 范围内）：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
..\..\.venv\Scripts\python.exe -B -m pytest -q tests/test_configuration_reconcile.py::test_mode_clicks_are_deferred_and_reconcile_exactly_once tests/test_selection_restoration_20261005.py tests/test_gui_smoke.py::test_devices_page_is_physical_and_capabilities_are_on_flight_page tests/test_enter_commit_gui.py::test_mode_parameter_enter_commits_once_and_dropdown_stays_immediate -o addopts= -o cache_dir=.work/capsule013_recheck/cache --basetemp=.work/capsule013_recheck/tmp --junitxml=.work/capsule013_recheck/junit.xml
```

先创建本次专用的 `.work/capsule013_recheck` 父目录，采用新的目录名避免重用前次临时目录。兼容检查将旧复选框断言改为真实胶囊，同时保留延迟合并/恰好一次重建及 IMU 恢复/保存断言。初次发现两处测试在 BMI088 替换后忽略 UART/I2C 冲突，另一处写死旧维护协议 0.0 显示名及只有一个可选 profile；现在明确验证错误绑定仍拒绝生成，协议核对稳定 ID、实际 0.1 显示和声明的完整选项。未放宽资源解析或自动编造 I2C 硬件。修正后的同次兼容检查 **8 passed**、无 skip，证据在 `apps/SCG/.work/capsule013_20261024_compat/junit_final.xml` 与 `summary.json`；前几次失败 JUnit 保留，未当作通过报告。

上述均为当时的离线检查，不包含 H7 实板、触屏驱动、舵机或输出电气行为。当时胶囊只编辑既有三个触发条件；该界面已由本页首节的阶段胶囊替代，旧检查数字不描述当前界面。独立舵机组件和板端阶段执行仍属后续工作。

### 基线复现与范围

在 `5794dab7` 之上，原 10 项失败已通过按权威合同校验和显式合成夹具身份修复。没有放宽生产解析器、猜测旧日志的算法版本或为新插件补造默认初始状态。可复现入口为仓库根目录：

```powershell
.\.venv\Scripts\python.exe -B tools/verify_navigation_baseline.py
# 或指定新的短输出目录；已存在的目录会拒绝覆盖
.\.venv\Scripts\python.exe -B tools/verify_navigation_baseline.py --output .work/nav013_recheck
```

该命令使用当前解释器、当前 owner 源码和仓库测试，不依赖历史验证目录。每组保存命令、stdout、JUnit、源码 SHA-256、提交/dirty 状态及退出码。Windows 请采用短的 `.work` 路径；FLP 原有的过长工程路径拒绝仍有效，不能把测试临时目录过长误报为算法计算失败。

本轮最终选定检查共 **711 passed，另 3 subtests passed**，无失败或 skip；按模块分别为 root 33、SCG 45、FLP 197、GSHC 62、Host/ARM-object 55、Python math 319。证据在 `.work/n013_20261024_03/summary.json`、`.work/n013_20261024_m7/summary.json`，以及 `.work/b013_20261024_02/id2t/` 的 19 项显式算法身份回归；后者补充了默认已知身份和未知身份夹具的区别。下方保留初次 668/10 结果及定位经过，不再代表当前剩余失败。

新增验证实际覆盖：

- 当前 C 核心 O0/O2 各 41 组（33 独立数学检查 + 8 参考对照），包含完整协方差、有限差分、SPD、失败不改状态和输入/工作区重叠拒绝。
- 三模型 O0/O2 的当前 C session/replay/journal：奇数微秒 IMU 对、延迟插入与顺序处理一致、重复观测不重复更新、固定历史退休、历史不足拒绝、日志存储失败破坏完整性资格。
- C 写出的分片经过真实 SSLOG 合成文件、匹配 Descriptor/`.ssdecoder`、LogOpenCoordinator 和 FLP journal reader，再核对位置、速度、旋转和完整 P；缺片、未封口、事务 CRC 损坏被拒绝。结果继续是 Derived/APPROXIMATE，不提升目标端一致性资格。
- 当前 C 磁质量的静止窗口、协方差下限、未验证延迟拒绝、声明时限计算、重复帧、校准代更换、传输失效和非法输入边界。
- 六个独立模块完成 Cortex-M7 / FPv5-D16 的严格 warning、实际 GCC analyzer 和 `.su` 生成。使用测试 logger 边界，仅为对象级准备；没有 H743 板级 startup/link、HAL、FreeRTOS 运行或完整栈证明。

### H7 就绪后的验收清单

| 项目 | 当前状态 | 需要补测/完成的证据 |
|---|---|---|
| 精确板卡与全工程构建 | 独立 M7 模块已编译；整板未验收 | 按实际 H7 订货号、RAM/TCM、时钟、FPU、DMA/cache、IRQ/RTOS 与传感器配置生成、link、analyzer、资源/完整栈门禁；不能沿用 F407 数字 |
| 实时性与容量 | Host 可核对有界行为 | 实板各任务执行时间/抖动、最坏延迟回放负载、deadline、队列峰值、栈 HWM、故障/饱和退化；先冻结实际频率和预算再判断 |
| 测量时间与生产者 | 软件拒绝/质量逻辑已验证 | 实际 IMU/GNSS/MAG 的测量时刻、接收/解码延迟、抖动、序号/重启代、磁时延上界测量；不能用配置 verified 位代替测量 |
| 坐标、安装与校准 | 数学与协议有明确合同 | 实板安装轴、单位、校准代切换、启动初始状态、GNSS 原点、天线杆臂/明确不支持项验证 |
| 日志与回放 | 合成 C→SSLOG→FLP 路径通过 | 实际 logger 队列、TF 长时吞吐、断电/存储满/丢片、完整操作 journal；真实同输入板端与桌面数值误差和健康判定对照 |
| 估计性能 | 合成数值验证通过 | 静态、受控动态、缺测/重获、异常测量、独立留出数据；明确参考仪器、指标及先验阈值，随后安排飞行验证 |
| 飞行流程 | 本轮基线阶段不改运行逻辑 | 后续配置逐项做 Host 检查和整板闭环观测；实际阶段判定、落地与动作结果仍需实测，软件预览不等于固件已执行 |

基线整理的退出条件是：当前选定离线检查可重跑、已知失败得到处理、硬件与未覆盖集成有明确边界；它不等于飞控已获飞行资格。后续先实现基于现有策略/参数的飞行配置追溯与编辑，不以 H7 硬件未完成阻塞桌面工作。

## 首次开发基线核对（2026-10-24，历史结果）

当前产品仍为 **0.1.3 development**，已发布版仍为 v0.1.2；以下结论不构成飞行资格。原工作区的 567 个源码、测试、合同、文档及正式样例文件已保存为本地提交 `1b3704f3`，父提交 `4c1b382b`。原始内容先冻结，再单独整理测试和文档；没有推送、操作硬件、修改控制算法或实现下面的任务周期草案。三个根目录 `work_*_20261006` 清单保留未提交，不当作产品源码。

**当前问题主要是实现、文档和验证证据不同步，不能概括成“算法未写”，也不能概括成“全部完成，只差上箭”。** 本轮没有发现所运行 Python 数学检查失败，但没有据此推断所有 C 集成正确。

| 内容 | 当前源码事实 | 尚不能宣称的能力 |
|---|---|---|
| PureINS / SF6 / KF6 / ESKF15 | 已有 C 后端、SCG 配置和 FLP 回放；KF6 有恢复/完整性检查，ESKF15 有独立参数与质量合同 | 全部板卡、全部配置均通过；台架/手持记录不能替代真实飞行验证 |
| ESKF20 / InEKF15 / InEKF20 数学 | Python 参考和实际有界 double C 内核均存在；InEKF 是 invariant，不是 iterated；三插件通过共同 owner 选择不同模型 | 新模型完整包线的精度、收敛性或目标板实时性 |
| 新模型固件接入 | 实际 backend、IMU 输入、SCG manifests 已接入；无合格 timing profile，默认软件验证开关关闭 | 选择成功或编译成功即有生产/飞行资格 |
| 延迟处理与操作日志 | 当前 owner 新增 `navigation_replay.c`、`navigation_journal.c`，backend 实际调用；存在固定容量历史和操作记录 | 不能继续说“尚未实现”；但本轮未复验这些新增 C 路径的完整延迟/容量/故障组合和目标端预算 |
| 磁观测 | 当前已有 `navigation_mag_quality.c`、质量/校准/时序输入及 backend 接入 | 配置 delay/uncertainty 或设置 verified 位本身不能产生传感器时延测量证据；真实生产链仍需验收 |
| FLP 新模型 | 三插件注册，已有严格操作日志读取与 Recorded-configuration 分支，以及离线显式配置路径 | 仅完整且匹配的 sealed journal 才能进入该路径；重算结果仍标 Derived/APPROXIMATE、firmware equivalence NOT_PROVEN，不能冒充板端原记录 |

源码定位：SCG 的 `silverstar_algorithm_augmented_common/payload/Algorithm/Estimator/Augmented`；FLP 的 `plugins/algorithms/navigation_reference_v1`。旧 README 中“新插件无 firmware IDs”“仅 co-timed”“没有 Recorded 路径”等描述已落后于当前源码，相关入口已补充状态说明。旧数学说明仍适用于其所描述的原型，不作为当前集成验收结论。

### 本轮运行结果与复现

环境：Windows；仓库 `.venv`，Python 3.14.0、NumPy 2.4.1、SciPy 1.16.3、PySide6 6.10.1、pytest 9.1.1；Host GCC 为 `D:\msys64\ucrt64\bin\gcc.exe`。GUI 检查使用 Qt offscreen，不连接设备。

| 检查范围 | 最终选定检查结果 | 范围说明 |
|---|---|---|
| `apps/SCG/experiments/navigation_0_1_3/test_*.py` 顶层文件 | 319 passed | 更新了过期的插件隔离断言；保留实验目录隔离，并增加共同 owner/默认验证限制检查 |
| SCG `test_navigation_v1`、`test_project_schema_current`、`test_product_patch_identity`、`test_firmware_identity_gate` | 44 passed / 1 failed | 旧官方项目迁移期望随当前产品版本；剩余参数合同测试见下 |
| 根 integration 的 product version、desktop inventory、monorepo baseline 三模块 | 32 passed / 1 failed | 独立插件版本不再假定全为 0.1.0；修复 Windows 启动测试只终止 launcher、遗留 FLP 子进程的问题；三个启动器 offscreen 检查通过 |
| FLP navigation plugins/body inputs/firmware configuration、magnetometer decoder routes、actual parameters、project artifacts，以及一个精确打开节点 | 164 passed / 8 failed | 具体失败分类见下；不能称 FLP 全量回归通过 |
| GSHC navigation readiness、START ACK state | 62 passed，另 3 subtests passed | ACK 与导航可用状态区分检查 |
| SCG navigation delayed health、KF6 integrity Host C | 47 passed | 实际编译执行选定健康状态/KF6检查；不等于新三模型 C 全量回归 |

总计选定检查 **668 passed / 10 failed**，另有 3 个通过的 subtests；没有将初次失败或中间调试尝试重复计入。原始命令、JUnit、stdout 和日志哈希位于本机 `.work/dev013_baseline_20261024_01/`，最终组为 `math_final`、`scg_final`、`root_final`、`flp`、`gshc`、`host`。它们是本次本地输出，不是仓库内永久测试依赖。

复现方式：使用同一环境，在对应应用目录运行表中的 pytest 模块，覆盖各应用默认临时目录；例如从根目录执行：

```powershell
$repo = (Get-Location).Path
$python = Join-Path $repo '.venv/Scripts/python.exe'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:SILVERSTAR_GSHC_DATA_ROOT = Join-Path $repo '.work/baseline-recheck/gshc'
& $python -B -m pytest -q tests/integration/test_product_version_metadata.py tests/integration/test_desktop_version_inventory.py tests/integration/test_monorepo_baseline.py -o addopts= -o cache_dir=.work/baseline-recheck/cache --basetemp=.work/baseline-recheck/tmp
Push-Location apps/SCG/experiments/navigation_0_1_3
$mathTests = Get-ChildItem -File test_*.py | ForEach-Object Name
& $python -B -m pytest -q @mathTests -o addopts= -o "cache_dir=$repo/.work/baseline-recheck/math-cache" "--basetemp=$repo/.work/baseline-recheck/math-tmp"
Pop-Location
```

剩余 10 个失败应单独收口，不能降低生产校验来“修绿”：

- 根测试仍禁止任何应用内 `navigation_v1.json`，而 FLP 已有受信任打包快照，本轮确认与 canonical 字节一致。应改为验证快照来源/一致性，保留对额外副本的拒绝。
- SCG 的参数测试仍把插件的完整参数列表直接等同旧导航基础合同（并固定数量 35）；当前还包含时序、horizon、恢复等扩展，且基础合同有消费者元数据。需要按各自权威合同核验扩展集合，而非删除参数或仅取交集。
- FLP 一项测试未纳入 `fusion_horizon_ms`；六项旧用例因未提供所需 KF6 algorithm revision 被拒绝；一项工程回开测试遍历所有插件却没给新插件必须的 `configuration_json`。应补正确的版本化夹具和新模型显式配置/拒绝案例，再核实真实工作流；不能用默认值绕过版本或初始状态要求。

### 历史证据与当前提交的边界

已读取本机 `C:\Users\chdxm\Documents\Codex\2026-10-22\task-9\silverstar_nav_boundary_v2` 的 `VERIFICATION_INDEX.json` 和 `FINAL_SOURCE_IDENTITY.json`。记录包括 C O0/O2 各 41 组、session 36 项、独立 Schur/Pdot 和实际生产者检查、参考 F407 编译/link/analyzer 等；这些是**历史记录，本轮未重跑该整套流程**。

历史清单 67 个文件均存在，但 **19 个当前 SHA-256 已不同，且不能仅由 CRLF→LF 解释**，涉及后端、session、输入头文件、estimator task、插件和 FLP 适配。因此不能把旧记录作为当前整个集成的通过证明；新增 replay/journal/magnetic quality 文件也不能被旧清单自动覆盖。外部验证目录不随 Git 克隆，需把可重跑的最小 harness、夹具及输入身份归入仓库测试，再对当前 commit 运行，避免只留机器绝对路径。

核对使用的历史文件 SHA-256：index `bb9c8424c3a6774df88556ed45916d3006cc9d850e732d83b6dd40999f9f6587`；source identity `2c74ca04d8dceff2521852e8fcc1a4629d109bdfb6c8cd327c97331ac45614a4`。它们只定位当时证据，不是当前源码摘要。

历史记录把 ESKF15 及以上的目标设为 H743，并明确 H7 工作暂停。F407 的资源/栈失败只属于那个参考配置，不能直接推成 H743 失败；反过来也不能推成 H743 已通过。本轮没有解除暂停、生成或运行 H743，也没有飞行实测。

### 推荐次序

1. **先完成估计链路的验收收口，不继续堆新算法。** 冻结一个主验收模型、板卡/传感器/输入配置；先解决上述测试/夹具分歧，再复验当前 C kernel→session→backend→生产者→日志→FLP 全链。现有 15 维路径与 20 维磁扩展分开验收；不把所有算法、所有板卡一次性列为完成条件。
2. 补时间与坐标、校准与源身份、缺测/重获、延迟/队列容量、完整协方差及故障不污染状态的证据；对新的 journal 做真实解析与重放一致性检查。随后按获准目标完成时序/栈/RAM、台架、留出数据和飞行验证，阈值先冻结，结果再评价。
3. **第二、第三步先做接口设计，不先重写状态机。** [任务周期草案](MONOREPO_ARCHITECTURE.md#任务周期与三端配置草案2026-10-24尚未实现) 将生命周期、物理阶段、事件、阶段任务和连续估计/调度分开；SCG 声明配置，固件发布实际状态，GSHC 展示，FLP 按精确日志重放。估计验收过程中可并行准备日志和只读展示所需合同。
4. 在估计状态及健康输出可靠之后，再引入控制算法。TreeDiagram 以后先承担可重复输入/故障场景与模型对照，不能替代实测或作为当前飞行资格证明；Underline/移动端的通信、回收定位和只读展示可独立推进，不必等待主动控制。

下方 2026-10-19 规划保留原日期和当时判断；其中“当前只有原型”和“先修普通生成版本身份”已经被后续源码进展部分取代。普通生成的版本入口现在已存在，见 [版本管理](VERSION_MANAGEMENT.md)；历史候选 ELF 不因此被修复。

## 十二月版本规划（2026-10-19，尚未执行）

用户已同意下一次正式更新目标命名 **SilverStar v0.2.0**，定位为面向 MEMS IMU 与低成本模块的可追溯导航、标定、记录和诊断工具链；本期不加入姿态/轨迹/推力等新闭环控制。**ESKF20与InEKF均为这次十二月发布必须加入的目标，发布前安排上箭测试**，不是可有可无的实验保留。产品目标是少量组合实测可靠、跨平台配置方便，不以算法原型数量计完成度。现有正式版仍为 v0.1.2；根 `VERSION` 当前为 0.1.3 开发身份。本轮仅更新本规划，**不改 VERSION、tag、源码、协议或已有工程**。

发布命名路径：`v0.2.0-alpha.1` → `v0.2.0-beta.1` → `v0.2.0-rc.1` → `v0.2.0`；各应用同步同一产品版本，日期/提交放在构建身份中。0.1.3 不必为凑序号单独发布；只有需要独立交付 v0.1.2 的兼容修复时，才另立范围有限的 v0.1.3 修补版。用户同意的是目标版本规划，本轮仍不改变实际VERSION/tag。

“200 元以下模块”作为候选传感器模块的采购准入目标；不能据此宣称整套飞控/地面站总价低于 200 元。本规划未选择货号、核验现价或安排采购。候选先看原始量、轴向/单位、native ODR/序号、测量时间、饱和和自检证据，再看价格与上手成本；无法解释的内部融合/校正输出不能冒充 raw MEMS。先验收一套可复现推荐组合，再扩展第二种 IMU；不承诺任意廉价模块都有同等性能。

### 每种身份一个权威，不把所有版本改成同一个数

| 身份 | 当前事实 / 十二月原则 | 唯一来源与人工维护边界 |
|---|---|---|
| 产品发布 | 正式 v0.1.2，当前开发 0.1.3；十二月目标已同意为 v0.2.0 | 根 `VERSION` 是产品版本唯一手填值；SCG/GSHC/FLP、源码包/安装包、普通新生成固件从它派生。实际实施/发布才变更；不得改历史包或二进制。 |
| SCG 工程 schema | 基础 14；按功能扩展至 20：radio 15/16、档位 17、NIS 18、native USB 19、安装位置 20 | 现有 `project/model.py` 常量及 `schemas/project.schema.json`，由 serializer 选最低可表达格式，用户不手填。仅真实数据语义变化才增格式；产品升版不强制旧项目升格式。 |
| 无线应用协议族/版本 | **现役 AIR M0 / wire profile0**；`H2S-RANGE v0` 仅为未来规划名称 | 现有 AIR 机器契约/codec 是当前权威；未来若落实新族，应先在 `contracts/` 定义独立 family+version，再做双端实现/协商/测试。不可把 M0 简单改名后声称已切换。无线芯片/频段/PHY/MTU 另属 transport 配置，不等于应用协议版本。 |
| 地面站 PC framing | 按现有 GSP/bridge 契约 | 与无线应用帧和 USB/UART 传输分层；换传输不自动变更 framing，也不把虚拟 COM 波特率当 USB 容量证明。 |
| 维护、文件服务、诊断 | maintenance0.1 兼容0.0；LOGFILE v1；DIAG schema1 | 各自现有契约/codec；能力协商决定可用操作。产品0.2.0不要求 maintenance0.2。INSTALL 扩展继续复用维护通道，控制命令不进入 SSLOG。**TF日志串口只读，不做删除**；DELETE保持不支持/拒绝，GUI可隐藏该能力，由GSHC独立任务处理。这不取消MAG/安装标定等另有授权、权限和事务边界的维护写入/保存。 |
| 日志、record、decoder/语义 | SSLOG0.0；decoder/project-semantics1.2；各 record 与算法身份有独立版本 | `contracts/`、record 定义、精确 `.ssdecoder`+Descriptor；只在真实不兼容数据/语义变化时分配新身份。新增完整标定 companion 优先独立有版本对象和内容绑定，不为控制命令升级日志容器。 |
| 算法/组件包 | 当前 KF6/ESKF15 manifest0.4.0、SF6 0.2.0 等各有身份；不是 Suite 版本 | owning `plugin.json`、参数/数学语义及实际 payload/hash；有语义/接口变化才更新所属组件。包版本不证明生成工程内旧用户源码已升级。**当前事实：ESKF20/InEKF仅隔离Python原型，无固件准入；十二月目标：两者都完成正式C backend及全链验证后纳入。** |
| 构建与工件身份 | 产品版本、源码提交/dirty 快照、配置/编译输入、工具链、ELF/HEX/BIN hash 分开 | 构建自动产生 receipt；`.ssdiag` 由实际成功链接的工件绑定。禁止另手填版本、build号、tag、source_commit 来充当源码证明；git lineage 不是 dirty snapshot。 |

### 先修普通生成的身份分裂

真实缺陷：项目可写 `firmware_version=0.1.3`、target `SilverStar_0_1_3`，普通 C 默认仍是 `0.1.2 / build0 / SILV0102`，INFO/DIAG/CAPS 因而显示 0.1.2。原因是 `generator/render.py` 只在显式 `reference_provenance.test_build` 路径输出版本覆盖；owning `System/User/system_user_config.h` 保留旧默认，`system_version.h` 默认 build identity 为空。已核对精确候选 ELF，**不是据字符串推断烧错旧固件**。详见[现状及证据](../../internal/RELEASE_IDENTITY_FOLLOWUP_20261018.md)。

建议最小修正批次，不借机迁移协议：

1. 在 SCG 设一个 `BuildIdentity_Resolve` 式公共解析入口，普通生成也必经它。新工程的产品版本来自根 VERSION；旧项目保留其请求身份，若与当前生成器不同须明确报告。发布构建不允许冲突静默通过，开发复现可明确保留旧身份并记录差异；不偷偷重写旧项目。
2. 复用现有受管 `Generated/Inc/project_flight_config.h` 输出统一版本/build宏，元数据、INFO/DIAG/CAPS、SSLOG 短 tag 和诊断声明均消费同一解析结果。短 tag/固定整数只作自动派生兼容字段，不能代替完整 prerelease/build 身份；字段超长明确拒绝，不能改 wire 长度或默默截断。test_build 作为显式测试渠道的覆盖/出处，不能成为唯一正确路径。
3. 扩充既有生成/构建 receipt，自动冻结 `product_version`、channel、source commit、dirty、确切源/头/依赖清单 hash、配置/组件/工具链身份。build_id 从这些**编译前输入**的规范摘要派生；链接后再追加 ELF/HEX/BIN 的完整 hash，避免把 ELF hash 嵌回自身造成循环。运行时只携带有界标识，完整清单随工件保留。
4. 正常再生成不得覆盖工程拥有的旧 payload。生成配置与旧 payload 不能形成真实一致身份时拒绝发布，给出受控副本迁移/显式升级路径；不能只换 metadata，让旧 C 冒充新版。普通 Make 不执行 SCG/Python 生成器；成功构建后由已有主机工作流绑定实际 `.ssdiag`，失败/取消先撤销旧绑定。
5. 发布包装对项目、有效预处理宏、运行时字面量、log tag、receipt、decoder 及 `.ssdiag` 作一致性检查；版本/工件缺失、冲突、意外 dirty 一律阻断正式发布。开发 dirty 构建仍可验证，但必须带精确快照和开发标记。

必要离线测试：普通生成与 test_build 两路径；正式/prerelease字符串和最大字段；显式旧项目/不一致/缺失身份拒绝；不改输入则重现同一输入身份，改源/头/配置/工具链则身份改变；实际 Host/ARM 编译核对 INFO/DIAG/CAPS/tag；失败/取消不保留旧 `.ssdiag` ready；Flash LMA/HEX/ELF 篡改拒绝；普通再生成保留用户源码及原日志/包。涉及 owning C 后必须另生成小验证工程，执行原样 Power10、相关 Host、真实 analyzer/ARM link、architecture/artifact/stack；不能只用 Python 字符串断言完成验收。

### 十二月路线图与退出条件

近期任务优先级为：**先完成GSHC修复，再推进SwiftThrust采集器的非点火采集软件，导航按正常排期推进**。这只安排工作次序，不把采集器扩成点火/动作控制，也不因本文启动硬件测试或改变现有暂停任务。

| 优先级 / 时间 | 最小批次 | 可验收的完成条件 |
|---|---|---|
| 必做：今晚定口径，10月剩余时间先打基础 | 统一上述版本/构建身份；明确支持矩阵、预算和测量指标；冻结一套 F407+MEMS+GNSS 基线 | 身份修正的普通路径可复验；基准数据、设备/安装/时序/参数/工件一一对应。静态噪声/偏置、重复性、动态误差、GNSS断失恢复、延迟和丢帧各有测试方法及待冻结阈值；不先编造精度承诺。 |
| 必做：11月前半 | **C071 地面站 + F407 飞控实测闭环**；按实际选定的PC连接方案验收，可优先使用外部串口桥接 | 验证所选桥接/连接方案的端口与framing、断连重连、背压/吞吐、双机AIR数据/状态、长时TF记录及导出校验；F407严格原样门禁及硬件HWM/时延。**原生USB仅为实验项，几款静态验证即可保留，不以C071 native USB EP0全验证作为整版十二月发布前提**；未过时采用已验收桥接方案。旧F103或离线ABI成功不能替代实际C071链路；实板操作另获授权。 |
| 必做：11月 | 多 MEMS 的身份、raw、坐标/单位、native sequence/epoch 与测量时间资格；磁旋转→六面并复用原数据；启动与安装标定分开 | 先一套、再第二种 IMU 各自端到端验收；有激励/多解检查、独立留出、取消/断线/重启/旧代保留、完整快照与 TF-only 提交/恢复；真实源不合格仍拒绝。六面不宣称完整陀螺尺度标定；新安装 XYZ 不因保存成功就算补偿生效。 |
| **必做：十二月发布前** | **ESKF20与InEKF生产C backend、SCG/日志/FLP接入及台架、上箭验证** | 先冻结各自状态/误差/磁模型与输入合同；从Python数学参考逐层完成有界C、真实SCG生成/选择、全P/故障/旧版本回归、真实ARM/analyzer与资源栈门禁、台架，最后发布前上箭测试。当前只有原型，不能提前标可用；任一未完成则该必做目标未达成，不以留在实验目录冒充交付。 |
| 必做：11月后半 | GNSS重捕获、时序、源切换和诊断/FLP追溯 | 选定发布 backend 完成1/5/30/120s失锁/重获及错误/时序反转/容量测试，明确参考原点与连续性；完整P/真实时序记录可用精确decoder复算。未完成 active recovery 的路径仍关闭并标不支持；不能以孤立kernel测试代替集成。 |
| 必做的目标验证批次：11月并行准备、12月决策 | **H743 飞控移植与实板资格**，从具体订货号/板开始 | 当前无 H743 MCU/Platform 插件，先补memory/clock/IRQ/FreeRTOS/FPU、DMA可达性/D-cache/TCM、timebase、存储/总线及源图，再实际ARM/analyzer/栈与实板验证。若列为十二月正式支持，这些是硬条件；缺板或门禁未过则明确“实验/不支持”，不能借H743大RAM跳过F407问题或宣称全STM32支持。 |
| 必做：12月冻结、RC、发布 | 按选定精确板卡/传感器组合跑完整集成矩阵，做可安装工具链、最短使用流程与支持边界 | 小范围推荐组合从配置→生成→构建→标定→记录→导出→精确回放可复现；CN/EN关键操作/错误可读，ACK/READY/保存完成分开；完整失败/skip与硬件缺证列明。源码/安装包/固件/decoder/receipt配套；任何未过组合不进入正式支持清单。 |
| 候选增强，先接口规划 | 单级机械开伞：PWM舵机与STS3215-C018总线舵机两个独立实例配置 | 收拢角/开伞角、机械有效范围、供电与启动输出边界明确；送达/舵机位置/机械打开分开。先模型/离线拒绝与故障测试，另获授权才实测。本轮不实现驱动/动作，不因列入候选就宣称可用。 |
| 可选增强 | 第二组合、重复性/温漂评估、按实例杆臂运行补偿、桌面操作简化及长时统计 | 先冻结数学参考点/误差预算/资源代价，保持原始数据与旧工程；只在不挤占必做验收时纳入。温度补偿、动态多IMU融合和自动冷备不能从“多实例可配”推定已完成。 |
| 实验保留 | 原生USB的几款静态验证候选、mode2 horizon、SX1278独立驱动、跨平台后端 | 原生USB不承诺全平台支持，不占用正式桥接链路的发布准入；继续隔离/默认关闭，分别保留静态编译、数学和资源证据。未通过的实验配置不能宣称已接受，也不按原型数量宣传完成或替代基线实测。ESKF20/InEKF已移至十二月必做目标。 |
| 延期 | 新有控功能、H2S-RANGE v0正式替换M0、SPI Flash、无限MCU/模块覆盖 | 另行立项、合同和授权；十二月不绑定这些迁移。TF日志串口删除是明确不做的范围，不是已排期的延期功能。 |

### ESKF20与InEKF必做目标的分层完成条件

目前两者仍只有 `apps/SCG/experiments/navigation_0_1_3/` 内的Python数学参考；现有InEKF9/15/20原型不等于三个生产backend。实现前冻结本次实际采用的InEKF状态维数、偏置/磁模型、误差坐标及其适用条件，不把bias-free的理论性质直接归给增广模型。两算法均按以下顺序验收：

1. 数学/合同：定义输入、单位/坐标/时间、状态与完整交叉P、初始化/注入/reset Jacobian、可观性、磁扰/缺测/恢复规则；与固定双精度参考及既有ESKF15在可比较的共同误差坐标下对照。
2. 有界C backend：owning declarative payload、固定内存与受控调用图，验证数值/非法输入/事务回滚/故障撤销READY；不移植Python/SciPy到目标，也不靠增加状态凑名称。
3. 正常产品接入：独立组件/语义身份、SCG真实选择/参数/源图/生成、日志完整身份及精确decoder、FLP Recorded/What-if与回归；旧工程/日志不能被重新解释为新模型。
4. 软件/台架：在选定F407/H743实际配置分别完成正常/故障回归、完整P与时序对照、原样Power10/architecture、真实analyzer/ARM链接、artifact/任务及MSP/ISR栈和资源审查，再做实际传感器/时钟/失锁/磁扰/持续运行台架。F407余量和H743新平台资格均不能跳过。
5. 发布前上箭：按用户计划安排，保留精确固件/配置/标定/设备身份、原始日志与decoder，验证实际运行、时间连续性、数值/健康和离线复算，完整记录失败与尚缺证据。具体硬件及上箭动作另行安排和授权，本轮不执行。上箭一次正常也不替代此前故障矩阵或证明任意工况安全。

两者均为这次发布的必做范围；若任一层失败，修复并重验，或向用户说明未达成并调整日程/明确重新决定范围。不得以禁用后照常宣称“本版已加入并可用”，不得将Host/静态结果写成实飞结果。

### 机械开伞候选：只规划接口，未实现动作

现有 `SystemMissionAction` 有 `PARACHUTE_DEPLOY` 和GPIO mission-action owning plugin；平台也有PWM抽象。这些**不构成舵机开伞实现**：当前未找到STS3215设备插件/总线驱动。建议复用任务动作的语义边界，具体Device/Adapter/FlightLogic各归其owner，不在System散布型号条件，不增加运行期回调注册表。动作接口将来若有变化，独立评审其兼容性，不在本轮改现有enum/协议。

| 规划项 | 必须表达的字段/结果 |
|---|---|
| 两个实例 | 独立instance ID：PWM实例和STS3215-C018实例，各自绑定资源、供电、角度、状态；可单选或显式组合，不默认同时动作，不共享未验证总线ID/定时器输出。 |
| 通用配置 | `folded_angle_deg`、`deploy_angle_deg`、零位/方向、机械有效min/max、位置模式、速度/动作时限策略、供电来源/允许范围/电流预算、配置hash及人工装配验收状态。两个角必须有限且落在模型与安装有效范围交集内；不能默默clamp，也不能一概假定0–180°。 |
| PWM实例 | 明确型号、脉宽/周期及角度映射、输出极性、安全inactive电平、使能/供电gate与上电次序；现有duty API不能自动当微秒脉宽契约。无反馈时只能报告接受/输出已提交/到达配置时间等事实，**实际角度和机械打开保持UNKNOWN**。 |
| STS3215-C018实例 | 固定具体C018修订、半双工TTL电气/收发所有权、已配置唯一bus ID、波特率/工作模式、角度编码/回绕/中位、限位及供电。厂商将C018列为12V型并提供位置等反馈，不能误套同名C001的供电参数；最终范围/时序以所购实物与固定协议资料复核。[厂商型号页，2026-10-19核对](https://www.feetechrc.com/525603.html)。不假定MCU引脚可直接驱动其供电或总线。 |
| 状态/错误 | 区分配置有效、未使能、请求接受、队列/驱动送达、设备回执、位置反馈到位、超时/供电/协议错误、结果不确定。即使STS有位置反馈，也只证明对应轴位置读数；机构脱落/卡扣/伞包状态需要独立反馈或人工确认，**不得把servo ACK/到位标成已开伞**。 |

上电不误动作是候选准入条件：软件Init、连接、配置加载、普通重启/掉电恢复不能隐式发送收拢/开伞目标或开启PWM/torque；默认未使能，未知配置/位置/供电保持禁止动作并报原因。输出pin复位电平、外部上下拉、独立电源开关和舵机自身上电行为必须共同验证，不能声称“不发命令就必然不动”。不自动重放上次命令或默认归零；收拢同样是实际动作，不能在Init里偷做。

未来动作事务应绑定boot/session、instance、command ID和配置摘要；同请求可查询终态，冲突重试拒绝，送达不确定不能盲目重新运动。机械回执与日志记录独立，不把动作控制塞入SSLOG，不自动增无线profile。角度/供电缺失、冲突资源、CRC/超时、断线、重启、重复请求、半完成、旧回执、无反馈PWM等先做离线故障测试；实际机械验证需用户提供舵机/独立电源/可断开负载和安装结构后另获授权。**本轮只有本文规划，没有连线、动作、烧录或新增控制接口。**

### 有控与多级的先后

十二月仍为**单级、无新有控功能**。之后优先做“多级数据”：明确stage ID/事件时间、记录来源、状态展示和离线分析，先验证时间连续性、数据归属和兼容读取；它不授权任何级间执行。有控需另立模型/闭环/执行器/失效评审；自动分离与再点火也独立延期。本规划不实现或安排多级执行控制，也不把机械开伞候选扩大为级间分离接口。

### 真实阻断、资源与硬件依赖

- **身份缺陷先修**：上述普通生成0.1.3/运行时0.1.2分裂与公共文档旧“当前0.1.2”说法；后续版本收尾只更新当前口径，保留历史记录和冻结发布。
- **USB实验项保留失败，非整版必做阻断**：2026-10-16 11:09 UTC 的精确实验派生扫描，F103 exit1/7组，F407 exit1/10组；含原生循环/条件编译/函数长度/heap-support源策略，以及另行实证的F103 CDC Setup把65535长度交给512B类存储。当前相关9个USB文件和gate仍匹配该快照。本规划没有新跑失败，也不把它扩为所有UART/STM32失败。C071完整生成曾遇ST登录/包环境，USBX适配仍未实现；保留几款静态验证及未接受状态，不扩allowlist、不承诺全平台。正式地面站按选定外部串口桥接等连接方案实测，**无须先完成上述native USB全验证才发布**。[精确说明](../../../apps/SCG/docs/USB_CDC_COMPATIBILITY_20261015.md)。
- **标定/重现缺口**：真实安装BEGIN仍拒绝资格，wire UPLOAD/APPLY/SAVE关闭；全入口lease/端到端取消时限、完整磁系数随历史日志保存尚欠缺。候选Commit成功被晚cancel覆盖的缺陷已在v9修复，列回归保护，不重复称未修。GNSS主动恢复关闭、H743未实现属于能力缺项，不伪称已发生运行故障。
- **F407资源非常紧**：最新v9特定配置主SRAM102292/102400B，余108B；CCM64896/65536B，余640B；Flash load391592B。条件化MSP模型844/1024B，余180B，仍非整机栈/WCET证明。不得调阈值、扩大任务栈或复用DMA禁区来掩盖新功能代价；每个发布配置重测，先优化可证明的重复状态/配置，再选择硬件。C071声明128KiB Flash/24KiB SRAM；不能迁入F407的假设。H743数字待具体part/板冻结，不先引用泛化容量。
- **可离线先完成**：身份与兼容回归、协议codec/原始数据重放、候选/TF故障模型、数值/可观性、源图与生成、真实ARM/analyzer/链接/静态栈、UI模拟、包装和文档；这些不证明物理时钟/测量时间/精度。
- **需要用户提供实物或新板**：明确C071地面站板/原理图、所选连接方案所需工程及外部串口桥接/接线；具体H743板/订货号/时钟和外设接线；可保留的F407基准板；两种拟验收MEMS与配套MAG/GNSS、TF卡/读卡器、安装/旋转夹具。优先复用已有板和已知良好模块；未知现有库存不自动变成采购清单。真实采样/同步、所选PC/RF链路、TF断电、HWM/中断/时延及环境重复性须另获硬件操作授权；本轮不连接。原生USB实验不额外设为整版必需的新硬件条件。

实现状态、精确提交及测试快照索引见[发布后改进清单](../../internal/SCG_POST_V0_1_2_INVENTORY_20261019.md)。尚未证明的关键合同、库/间接调用/MSP/ISR栈、WCET、精度和飞行资格继续记录NOT PROVEN；十二月是否发布由精确支持矩阵的证据决定，不由日历或新版本名字决定。

## 正式0.1.2的历史口径（保留，不代表当前开发状态）

| 身份 | 0.1.2 源码中的口径 | 权威来源 |
|---|---|---|
| Suite 产品版本 | 0.1.2 | 根 VERSION，各应用读取它 |
| SCG 基础项目 | 14 | `project/model.py:PROJECT_FORMAT_VERSION` |
| Ground radio 扩展 | 15 | `PROJECT_GROUND_RADIOS_FORMAT_VERSION` |
| Radio variant 扩展 | 16 | `PROJECT_RADIO_VARIANTS_FORMAT_VERSION` |
| 四档项目 | 17 | `PROJECT_FEATURE_TIERS_FORMAT_VERSION` |
| FLP `.ssflp` 项目 | 3 | `core/project.py:PROJECT_VERSION` |
| Decoder / Project Semantics | 1.2 | strict decoder coordinator / 生成声明 |
| SSLOG / Maintenance | 0.0 | 具体 wire 契约与 codec |
| AIR | M0 / wire Profile 0 | GSHC AIR_PROTOCOL 与实际协议 |
| 插件 manifest | 各自独立，参见组件清单 | builtin plugin.json |
| 上游库 | 各自独立 | vendor 文件头、LICENSE、实际来源 |

产品补丁版本不能机械改写 wire、源日志、decoder、插件版本、既有项目拥有的 payload 或历史二进制。SCG 接受 14/15/16/17 的明确边界，旧版本迁移以实际 loader 为准；“当前基础常量14”和“四档17”可以同时成立。

### 软件验证的口径

本次三应用合并曾有25项针对性Python检查通过；三个实际窗口离线启动/事件循环/退出通过。源码分发另有解压文件哈希/入口/帮助/离线烟测，最终结果绑定最终包的 receipt。不能把这些结果写成全套测试、全部固件配置、桌面GPU、串口无线、TF、栈、WCET或飞行资格均通过。

F103C8/C071FBP6 classic CDC 是 EXPERIMENTAL 私有候选，普通完整生成入口 BLOCKED；F407 private TIM1/Ground 不替代首批 C071。USB EP0 独立审查没有通过结果；不能重标已审或据此正式放行依赖。PoT critical-contract review 是 NOT PROVEN。保留未知配置和失败检查。

历史报告、原日志、构建文件和证据保留原日期/源码/命令/配置身份，不纳入公共文档包，公共目录不复制它们。原文内具有日期、旧固件/Golden或旧格式身份的段落仍按各自历史范围阅读；当前说明另明确源码边界，不将旧结果重新归属本版。
