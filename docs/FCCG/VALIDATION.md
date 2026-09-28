# Validation — 2026-09-27 joint navigation / ESKF15

本节记录本轮执行结果；后续历史章节保持当时语义。联合行为、数学、状态机与下一次台架计划见
[JOINT_REWORK_REPORT.md](JOINT_REWORK_REPORT.md)。精确执行日志及哈希位于
`tests/joint_rework_20260927/evidence_final/`，新驱动逐型号证据见
[SENSOR_LIBRARY_VALIDATION.md](docs/SENSOR_LIBRARY_VALIDATION.md)。

六配置最终固件门禁、三产品完整回归、五日志重算和目标计时工具补验已完成。
本节区分全量基线与最后修复补测，没有任何实机验证声明。

## 身份、实现与交付边界

- 起点 FCCG `d013ae10924a308e95478445f91c370601871f19`；配套 FLP `c4605f4`、GSHC `cbee51e`。
- FCCG/Platform 0.0.12、GSHC 0.0.3；FLP 0.0.5。Project format 12、decoder/semantics 1.2，
  新 decoder 的 FLP 最低版本为 0.0.5；ESKF15 revision 1、公共质量 revision 3，历史 KF6 revision 2 保留。
- 65 个 builtin packages，包括真实 ESKF15 与 26 条新增传感器型号/接口编译路径。
  三仓库 `docs/contracts/navigation_v1.json` byte-identical；35 个 ESKF 实参均由项目/manifest 产生。
- 新导航记录 0x21–0x27 与状态事件 0x2F；原 28 条记录布局及基础 AIR 9-byte 帧不变。
- SS_0_5_TEST_3 五份原始 BIN 与 HARDWARE 中 matching decoder 只读，六个 SHA256 保持不变。
  本轮所有固件构建在 FCCG `tests/` 内完成，没有改写用户测试固件目录。
- 用户后续授权三个仓库提交/推送，并取消关机。没有烧录、物理输出、tag、Release 或发布。

## 正式生成工程与全路径门禁

入口 `tools/validate_joint_navigation.py` 通过真实 FccgService 生成/校验工程；
`Gates_Run` 在同一已解析 source graph 执行 Release 和 Debug：

```text
mingw32-make -j4 SHELL=cmd.exe CONFIG=Release all stack-report memory-report artifact-check
mingw32-make -j4 SHELL=cmd.exe CONFIG=Release architecture-check power10-check static-analysis
mingw32-make -j4 SHELL=cmd.exe CONFIG=Debug all stack-report memory-report artifact-check
mingw32-make -j4 SHELL=cmd.exe CONFIG=Debug architecture-check power10-check static-analysis
mingw32-make -j4 SHELL=cmd.exe CONFIG=Release host-tests
```

工具链为 Arm GNU 14.3.Rel1 / MinGW Host GCC；没有变更全局 PATH、安装环境或扩大内存预算。
完整运行 `FinalMatrix_20260927_081706_010978` 与最终修复 `FinalDelta_20260927_085218_568926`
全部 exit 0；最终 source audit 对六配置的产品输入逐字核对，差异为 0。
Host 仅在生成配置选择日志时执行相关 codec/storage fixture；
关闭日志仍执行真正的 kernel、START、选源、故障和遥测检查，不虚构 logger mock 的使用。

以下是最终 linked ELF 的字节数；Flight/Test 分别生成和验证，资源相同。

| 配置 | Release Flash / main SRAM / CCM | Debug Flash / main SRAM / CCM |
|---|---:|---:|
| KF6 Flight/Test | 286184 / 101840 / 56216 | 303192 / 101864 / 56216 |
| ESKF15 Flight/Test | 272320 / 100440 / 65080 | 287888 / 100464 / 65080 |
| ESKF15 无日志 | 233444 / 68060 / 62008 | 249284 / 68100 / 62008 |
| Pure INS | 253592 / 82512 / 44800 | 268976 / 82536 / 44800 |

Flash/主 SRAM 物理/CCM 容量分别 524288/131072/65536 B；主 SRAM reviewed budget 102400 B。
最紧 CCM 余量 456 B；最紧 reviewed main-SRAM 余量 536 B。预算不变，runtime heap symbols 为 0。
ESKF Debug 配置/静态估计：Device 2048/1328、INS 3072/2096、Estimator 4096/2000、
Flight 4096/2320、Logger 3072/1336、Serial 6144/3008、Telemetry 4096/1904、Idle 512/256 B。

完整基线 Host（本轮真实执行，均 0 failures）：KF6 每配置 72 executables / 4392885 checks；
ESKF Flight/Test 每配置 71 / 4360252；无日志 61 / 152301；Pure INS 70 / 4358689。
每配置另有 8 compile-pass / 16 expected-compile-rejection cases。
最后 C 修复后全部 R/D 门禁重跑，并按影响重跑 Host：health 每配置 1853 checks；
KF6 air 706、replay 33531、实际准备 288；ESKF logging backend 1575、准备 241；
无日志准备 241；Pure INS 准备 231。以上不冒称第二次全量 Host。

最终 R/D Power of Ten 的 checks / first-party C files / functions 分别为 KF6 6459/99/2427、
ESKF logging 6270/99/2354、无日志 5938/95/2238、Pure INS 6118/96/2303。
architecture 启用日志各 318 checks、无日志 184；全部 0 failures；GCC `-fanalyzer` 通过。

目标工具 `Tests/Target/timing_bench*` 为显式 opt-in，默认生产 graph 无这些源，资源表不受影响。
真实 CMSIS DWT/PRIMASK adapter 和 APP snapshot/HWM 示例在 ARM O2/Og 下以 `-Werror` 编译、
生成 `.su` 并核对 PRIMASK 指令；Host O2/Og 各 2089 checks / 0 failures。
六项新工具测试加六项文档检查合计 **12 passed / 14.42 s / exit 0**，
覆盖 wrap、owner、嵌套、系统异常拒绝、时钟错误、饱和、导入归属、默认图排除与实际源码导出。
未链接的三对象 text 合计 O2 1412 B / Og 1516 B，BSS 各 272 B；不是生产 ELF 增量预算。
首次专项 2 failed / 10 passed 原因为测试未支持 generated Make 变量位于 EOF，修正读取后重跑通过。
该工具没有运行于实机；snapshot getter 成本示例不代表算法执行时间，完整 INS/ESKF/Logger/ISR
插桩说明见 `Tests/Target/TIMING_BENCH.md`。真实 CPU、最坏耗时、ISR、SD 和动态 task HWM 仍待测。

## 数学、健康与实际日志闭环

- C/Python float32/float64 四种运动情景：2000 prediction / 1000 measurement groups，
  最大 p/v/q/bg/ba/P 差 `1.032e-5/9.416e-6/7.533e-6/5.680e-7/5.175e-7/3.127e-6`，
  保持 absolute `2e-4`、relative `3e-4`，包含独立 Jacobian/边界反例。
- 250 Hz 混合延迟最大差 `5.383e-6`，178 replay steps；100 Hz 最大差 `3.16e-6`。
  CLIPPED/NaN/P/prefix/capacity 失败不得提前提交 anchor/history，最终跨仓库针对性 20 tests 通过。
- 双 10 s/错位 5 s 窗口 context ARM sizeof 184 B；ESKF state/workspace/history 为
  992/3980/16992 B，BODY/event 64/72 B。192 BODY + 208 events，600 ms history。
- 新的真实 APP correction/pairing/frontend/ESKF C fixture：801 raw → 400 BODY / 2 s，
  200 Hz BODY、120/192 history、0 overflow，4413 checks / 0 failures。2/3 ms proxy 保留 TIME_UNCERTAIN。
- 最终 health C fixture 1853 checks / 0 failures；model mismatch 锁存，不同 source 同 tick 可区分，
  同源重复/倒序不计证据。2 s DR / 10 s INVALID；有限非零 gain 的实际 commit 才刷新最后成功时刻。
- KF6 有限且至少一个非零 Kalman gain 才能提交更新，零创新但正常增益仍可成功；
  浮点下溢为全零 gain 返回 NUMERIC_ERROR，状态/P/成功计数不变。所需组软降权、R>1 或最新物理无效
  使总体 DEGRADED；失辅 DR/INVALID 优先。生产者记录 satellite×Pos-EN-only-window×actual-robust 的倍率。
- 659-record direct C codec/当次 generated decoder，正序及跨队列乱序均可 FAITHFUL；
  full-P 最大差 `1.633e-6`。491-record 实际校准/ESKF backend/LoggerBus/LoggerTask 闭环另行核验，
  99 条量测准入及结果严格匹配，FLP p/v/q/P 最大差约 `9.512e-9/1.2761e-7/8.663e-8/7.302e-7`。
  后者为实际生产 C + 合成 Host 时钟/输入/文件 sink，不是目标机飞行或 DMA 时序证明。
- 最终桥接重新编译 2078 checks / 0 failures；491 records / 58931 B，strict audit 通过。
  BIN SHA256 `253dd88e57bb7f672ad2ed174979f19f632cee58e71a36eb6d7452455bc20e07`；
  decoder SHA256 `2c58fa36a1e40a27801e775b02640f6a460df00d12b58a0640bc3331b4102c46`。
  与上一轮仅 descriptor/设备 identity 及最后两轮健康字段不同，p/v/q/bias/P 和量测 payload 逐字相同。
  最终 pair 由现有 FLP 产品重新导入为 clean / EXACT / FAITHFUL；99 条量测严格匹配，
  20 STATE + 20 NAV_QUALITY 的健康值按精确时间比较 40/40 一致。361 导出零失败，
  两幅缺少旧 IMU_CORRECTED 流的图明确不可用。
  此 fixture 覆盖软加权结果；ACCEPTED 且 R>1、KF6 零 gain 拒绝另由最终 FLP 针对性用例验证。

## Storage 的真实负载与失败恢复

完整 FatFs/diskio/Logger/DMA Host 模型，80 ordinary / 48 estimator 容量未扩充。
Flight/Test 正常运行均 0 drop、0 producer failure：HWM 分别 `65/80,46/48` 与 `77/80,46/48`。
有限超载分别 449/453 drops，frame 1500 的累计即最终累计，恢复后无新 drop；sequence gaps 保留。
BODY 100 Hz，四 GNSS group 各 25 Hz，Baro 100 Hz；Test 额外 25 Hz×4 full-P 分片。
Host 注入最大 write 126 ms / sync 108 ms / iteration 316.12 ms；不能作为目标 WCET。
119 B @ offset 37 与 partial-sector、prefix/关键 flush/uncertain-write 真实 LoggerTask 533 checks；
LoggerBus 2,102,778 checks。CRC/framing 审计不重同步取得 PASS。

## 传感器与 GUI/打包

69 项传感器合并测试通过，包含 26 个实际生成 ARM source/include/resource 路径；
原 Power10 对驱动路径 2897 checks / 66 C files / 1106 functions，0 failures。
BMI088 Sync400 I2C/SPI 使用 6144 B 官方 BSD 配置块、明确同步网绑定、完整初始化/readback与IRQ负测。
ARM sample/driver/adapter ABI 80/112/256 B；Sync400 O2 对象 7325 B text/const、0 data/BSS。
普通 BMI088 raw200 不宣称同步资格；ST320X 高 g 独立，MPU6050 不提供假 SPI。
所有新传感器：MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED。
默认 RAM 配置；JY 无盲 SAVE，M8 持久层无法独立比较时 UNSUPPORTED，M9/M10/F10 显式分层差异持久化。

FCCG 导出源包离线启动 8 s，发现 65 插件与 ESKF/Sync400 资源；4 张中英/Light/Dark 截图实际
1000×700 logical / 2000×1400 pixels，英文完整产品标题换行。C fixtures 位于永久 tests/fixtures，源包保留。
FLP 最终完整套件 **483 passed / 9 原条件 skipped / 373.07 s / exit 0**；
针对性回归 90 passed，最终套件无 warning，NaN/inf 负例局部断言预期告警。
最终 wheel 349169 B、SHA256 `8526dff3f49dd1bc9f4722f73881e9357745b9d2a91068610c34487b3fdf7869`，
离线解包后的真实 GUI/ESKF 插件启动通过，102 个 Python/JSON 产品文件与当前源码逐字一致。
此前 293.61 s 套件与旧包保留；最终套件和包已包含三处 `m/s²` 显示单位编码修复及其断言。
九项 skip 为原有外部条件 fixture：current-log 1、旧 joint C golden 1、SS_TEST_0 3、SS0007 3、SS0014 1。
本轮新 C oracle、两个 659-record golden、五真实日志及实际 backend bridge 已另行执行。
GSHC 最终窗口修复后 425 passed + 3 subtests；1000×700/200% 的中英 Light/Dark 共 16 张实际全窗口截图。
GSHC PyInstaller 包启动 8 s 存活、stderr 0；九项导航准备可见，任务状态卡使用垂直滚动。
实体触屏、OpenGL 驱动及无线网关没有在本轮硬件认证。

## 五份真实旧日志与尚缺证据

四路 A recorded / B old-revision / C quality-revision-3 KF6 What-if / D ESKF15 What-if 均保留。
SS0002 的 B/C 继续报 gnss_origin_unavailable，D 无 GNSS 操作，不补造 origin。
D 的 SS0000/2/4 最终 INVALID，SS0001 HEALTHY、SS0003 DEGRADED 是内部诊断，无真值不能称定位精度通过。
五份 finite/P-PSD/q-normalized 不等于物理正确；新质量 flags、硬件读回与采样时间证据缺失，均明确近似。
最终新目录 five_logs_quality_fix_kf6 / five_logs_quality_fix_eskf 与旧结果独立保存。
四份成功 C 各 165 个既有非健康数组完全一致；D 的 SS0000/1/3/4 各 141 个、SS0002 的 45 个
非健康数组完全一致。D 的健康变化 epoch 数依次 130/181/0/865/769，SS0003 末状态由 HEALTHY 修正为 DEGRADED。
D 五组最长失辅均不变；C 仅 SS0001/3 VelU 的初始最大间隔分别由 280000/290000 改为 290321/304296 us，
因为旧离线 helper 从首输出起计，产品从实际 START 起计；正式原日志导入核对差值 10321/14296 us。
该差异不是融合结果变化。73 份旧报告/NPZ/图和全部原始输入哈希不变。
完整比较、逐组计数和时间见 FLP approved_quality_comparison.json / approved_quality_clock_basis.json，
窗口/bias/15P 与失败曲线仍保留于 five_logs_contract_final、four_way_comparison。

## 回归命令、修复记录与最终状态

完整产品回归显式枚举 `tests/test_*.py`（受维护顶层套件），生成的临时项目不是产品 pytest。
冻结前一轮 519 passed / 5 failed / 1 skipped：4 个 63→65 插件目录数量断言及 1 个文档命名检查失败，
均保留失败日志并修复；随后针对性 9 tests passed。
最终完整 rerun：**533 passed / 1 skipped / 0 failed，2306.98 s，exit 0**，
`fccg_delivery_final.log/.exit`。最后 C 修复由独立六配置 delta 覆盖；随后新增目标计时工具的六项测试
及六项文档回归单独通过，没有把这次补测描述为第二次全量运行。
原 1 skip 原因：旧只读 reference firmware 工作树非 clean，原 skip 条件未改。五份实际任务日志来自 SS_0_5_TEST_3。
一次宽泛递归收集误入历史 generated fixture 导致 collection errors，保留日志；没有删除用户旧临时数据。
首个 wheel 命令误用相对 TEMP 路径，pip 使用系统临时目录；已以严格错误处理、repo-local TEMP/no-cache 重跑通过，
没有全局安装或配置修改。此操作失误不被描述成首次就符合临时输出约束。
变更 Python Ruff `E4,E7,E9,F,I`、134 Python files compileall、80 JSON 解析及 git diff --check 通过。

此前 FLP 四个 revision-3 接入文件的自动审批阻塞已由用户“可以继续修改flp”的明确回复解除。
四个产品调用点已实际接入，最终五日志、完整产品回归与实际桥接复验通过。
目标计时工具补充验证已通过。当前软件状态为 IMPLEMENTATION_COMPLETE / SOFTWARE_GATES_PASS，
可进入 READY_FOR_JY901B_BENCH_VALIDATION；这不是已执行台架或实飞验收。
GSHC 已本地提交 `8be9fd6a7d03be8a7edd96a78454b33701869ad0`；最终 Git 交付以三仓实际提交/远端核对为准。
新传感器仍 HARDWARE_UNVERIFIED，整套 NOT_FIELD_VALIDATED。

---

# Validation — 2026-09-22 joint field-log contract

## FCCG 当前验收

本节替代此前本轮未完成的草稿。正式契约见
[FIELD_LOG_REPLAY_CONTRACT.md](docs/FIELD_LOG_REPLAY_CONTRACT.md)。
FCCG 与 FLP 的生成日志数值链已经验证；GSHC 完整回归与原 spec 打包启动通过，见联合报告和 GSHC 根 VALIDATION.md。
没有 commit、push、tag、Release、烧录或修改只读参考固件。

### 代码与正式记录

修改范围包括公共惯性前端、KF6/replay、GNSS quality、landing、APP 日志生产路径、
SSLOG codec/Catalog/semantics、日志策略、导入器 ownership 和对应 Host/Python 测试。
SAMPLE、RAW_SENSOR、IMU_NATIVE、HW_QUAT_NATIVE 退出生产类型、codec、Catalog 和生成别名；
原 ID 空洞保留，不重新编号。KF6 不再维护 Pure INS 导航旁路，不产出 PURE_INS。
Pure INS 选择仍单独运行、记录；KF6 自身提供 q/p/v/线加速度。

正式 Catalog 共 28 项：

EVENT, STATS, ESTIMATOR, SYSTEM_CONFIG, PURE_INS, KF6_DIAGNOSTIC, KF6_FULL_P, POWER, HEALTH, TELEMETRY_DIAG, INITIAL_STATE, GNSS_NATIVE, BARO_NATIVE, MAG_NATIVE, INERTIAL_INCREMENT, GNSS_MEASUREMENT, BARO_MEASUREMENT, IMU_CORRECTED, CALIBRATION_RESULT, ALIGNMENT_RESULT, MISSION_CONFIG, DEVICE_DESCRIPTOR, ALGORITHM_DESCRIPTOR, LOG_STREAM_DESCRIPTOR, DECODER_PROFILE_DESCRIPTOR, ESTIMATOR_STEP, GNSS_RECOVERY, LANDING_DIAGNOSTIC

GNSS、BARO 各自保留 observation 与 estimator measurement；ESTIMATOR_STEP 给出实际预测
操作序号、源 increment、present、epoch、结果；GNSS_RECOVERY 与 LANDING_DIAGNOSTIC
保留分组恢复事务及低流量着陆状态变化。EVERY 输入不得设置 decimation/period。

### GNSS 与 landing

Pos EN、Pos U、Vel EN、Vel U 独立 quality/update/NIS/recovery。hAcc=4.06 m、vAcc=10.01 m
仍允许 Pos EN。飞前 origin 门禁保持严格，未建立 origin 的本次任务不启用 GNSS 融合。
失联、质量无效与估计器 NIS 拒绝分别表达。

恢复顺序为 outage → 连续一致返回 → 正常更新 → inflation → controlled group re-anchor。
重锚须有真实 availability outage、至少 3 个一致样本、1 s 持续返回、8 次膨胀尝试耗尽，
并保持原恢复间隔。仅 NIS 连续拒绝不能授权。受影响 state 设置到观测、R 构造其协方差块、
cross covariance 清零，有限阶 Cholesky 检查后提交。历史量测在历史 x/P/内部状态上重锚，
再重放，不改变其他组、姿态、origin 或时钟。Host 覆盖公里漂移、单点异常、组隔离、SPD。

Landing 物理门限仍是 gyro 0.10 rad/s、|a|-g 0.5 m/s²、baro slope 1.0/0.30 m/s、
span 1.0 m、candidate 3 s。固定时间累计 bucket 要求 IMU valid coverage >=90%、
有效时间中 still >=95%、连续 bad <=200 ms、末尾近期合格。短暂 baro miss 在原
100 ms freshness 内等待。100/200/400 Hz、尖峰、短缺测、持续运动、20 Hz baro 有覆盖。
FlightTask 先读 snapshot 后读 evaluation time，时间竞争的实际 APP fixture 通过。
200 Hz / 60 s BARO 正常 WAIT↔ACCEPTED 共 12000 次接受、0 次调度 EVENT。

### Existing Time Synchronization vs Fixed-Lag Replay

已有时间链为 sensor native/receive → provider/adapter → sensor hub → SystemTime
统一 MCU/estimator measurement timestamp → estimator → SSLOG。原 SystemTime 负责既有
计数扩展、wrap/offset、MCU/mission 转换和量测时间解析，不复制第二套时钟系统。
当前 JY901B 没有可信 native sample epoch，使用 receive - configured baro delay；
可信 native 时间经已有同步机制转换后直接使用，不重复减 delay。NEO-M9N 当前 solution
以 MCU receive epoch 进入此链；iTOW 本身不意味着已完成历史融合。

Time synchronization 确定时间坐标；fixed-lag 引擎恢复历史 x/P/内部恢复状态，在量测
时刻 update，再 replay IMU/GNSS/BARO 到 present。GNSS/Barometer 共用同一有界引擎，
delay=0 保留 fast path。本轮新增真实 operation/present/epoch/result 日志与分组重锚，
FLP 直接消费这些时间与执行事实。错误的“修改 timestamp + current-state update”有负对照。

### 真实生成、构建与完整测试

生成工程 `tests/artifacts/joint/SS_TEST_19`，由 ReferenceProject_Create/Project_Save 创建。
参数延迟混合对照工程 `SS_TEST_20` 为 pos 40 ms / vel 270 ms / baro 100 ms。
两者保留 project format 12、decoder/semantics 1.2、Platform 0.0.10、AIR/GSP wire 不变。

| 检查 | 实际结果 |
| --- | --- |
| FCCG 全套 Python | 415 passed / 1 skipped，963.12 s |
| 生成工程 Release | all、stack-report、memory-report、artifact-check 通过 |
| 生成工程 Debug | all、stack-report、memory-report、artifact-check 通过 |
| Architecture | 262 checks，0 failures |
| Power of Ten | 6072 checks，95 files，2278 functions |
| Host | 68 executables，4386469 checks，0 failures |
| Host 编译契约 | 8 compile-pass，16 expected compile-rejection |
| Storage integrity | 4/4，通过实际 codec/FatFs/diskio 与延迟 DMA |

Python skip 为既有只读参考固件任务仍活跃的保护分支，未停止该任务。
日志：`tests/artifacts/joint/pytest-full19.log`、`ss19-release.log`、`ss19-debug.log`、`ss19-host.log`。
本轮未执行实机烧录/飞行、物理 SD 卡延迟/耐久或新的全图 static-analysis 验收。

### Logger 速率、RAM 与抖动

模型输入为 IMU 200 Hz、increment/step 100 Hz、baro observation 200 Hz/measurement 100 Hz、
GNSS observation/measurement/recovery 各 25 Hz。导航与简要 KF 诊断各 25 Hz、full P 5 Hz、
POWER 10 Hz、telemetry/stats/health 各 1 Hz：**843 records/s，79908 bytes/s**（含每帧 28 B
开销，不含事件/关键快照/启动描述符）。MAG 无当前 producer；不同实际设备率需重新测量。

正常配置 20–100 ms storage jitter：normal HWM **76/80**，estimator HWM **44/48**；
163694 accepted、0 drops、0 producer failures、254 次 jitter。max write 128000 us、
max sync 108000 us、max logger iteration 316120 us（包括多步调用及模型驱动开销）。
有限过载 163759 accepted / 436 observable drops / 14 producer failures，CRC/framing 完整，
序号缺口与 drop 计数一致。Host 调度模型不是实机最坏时延保证。

64/32 初测溢出后才调整为 80/48；并修复 CommonSpscQueue uint16 计数回绕对非 2 次幂容量
的索引错误。独立 head_index/tail_index 按 capacity 回绕，队列计数与同步语义保留。
容量 1/3/48/64/80 各 140000 个值跨两次计数回绕逐值核验。修复前曾出现 CRC 合法但
重复/缺失记录，修复后严格预期条数通过；未放宽验收计数。

| bytes | Release | Debug |
| --- | ---: | ---: |
| FLASH / bin | 272312 | 289568 |
| ELF file | 2869532 | 4256728 |
| main SRAM | 101728 | 101752 |
| main SRAM 剩余 | 29344 | 29320 |
| CCMRAM | 64160 | 64160 |
| CCMRAM 剩余 | 1376 | 1376 |
| heap / runtime allocator symbols | 0 / 0 | 0 / 0 |
| INS stack estimate / margin | 2152 / 920 | 2048 / 1024 |
| Estimator stack estimate / margin | 2676 / 1420 | 2700 / 1396 |
| Logger stack estimate / margin | 1328 / 1744 | 1320 / 1752 |

相对同轮日志改造前 SS_TEST_10，main SRAM 增加 4560 B，CCM 增加 48 B；
normal/estimator record storage 为 16000/9600 B。artifact 软预算由 96 KiB 调为 100 KiB，
明确容纳本轮全速记录和有界队列；物理 128 KiB、CCM、heap 和栈门禁不变。CCM 余量仍小。

最终文档检查：`tests/test_documentation.py` **6 passed，0.27 s**，`fccg-doc-final2.log`。
联合报告位于根 [JOINT_FIELD_REWORK.md](JOINT_FIELD_REWORK.md)，保留用户指定的时间同步/重放英文章节。

### 最终 GUI 补验与现有边界

中英 / Light / Dark × 100% / 200% DPI 共 8 个 offscreen 场景，五页切换完成；
截图在 `tests/artifacts/joint/fccg-gui-dpi1` / `fccg-gui-dpi2`，加载系统字体并处理 Qt deferred-delete 后抓取。
请求 1000×700 时，既有 `MainWindow.setMinimumSize(1080, 700)` 使实际窗口为 **1080×700**。
因此不宣称 FCCG 1000×700 通过；本轮没有修改 FCCG 窗口布局。实际 GPU/触屏不在验收内。

### C → decoder → FLP 数值验证

`tests/joint_navigation_support.py` 编译生成工程真实 C frontend、KF6、replay、SSLOG codec，
`tests/fixtures/joint_navigation_golden.c` 输出日志。FLP LogOpenCoordinator 严格匹配同源 decoder。

| 场景 | 输出数 | p 最大绝对差 | v 最大绝对差 | P 最大绝对差 |
| --- | ---: | ---: | ---: | ---: |
| 常规基准 | 400 | 2.24e-8 | 9.43e-8 | 1.20e-7 |
| pos 40 / vel 270 / baro 100 ms | 400 | 3.73e-8 | 9.45e-8 | 3.58e-7 |
| 公里漂移恢复 | 2000 | 5.59e-9 | 1.40e-9 | 1.20e-7 |

q 完全一致；operation/result/replay generation mismatch 均为空。公里漂移最大位置约
5607.916 m，重锚次数 [1,0,1,0]；垂直组未重置。corrected IMU → increment 独立逐区间
dt/边界/增量核验通过，无再次 calibration。日志 CRC、解码、序号缺口、重同步均无错误。
FLP 仍为 APPROXIMATE，数值验收不扩展成未测硬件/外场/全部边界的 EXACT 承诺。

| 产物 | SHA-256 |
| --- | --- |
| `SilverStar.ssproject` | `95d649d450f42a0cba11dad5a0b7488e6012d9867d0860b3969371ade297b2de` |
| `JointContract.ssdecoder` | `1ff6699a4584f9ace43763daa84541ade7df475712655ac7e32c4f5dedfd4631` |
| `build\FCCG\SilverStar_F407\Debug\SilverStar_0_0_10.elf` | `1e2b214e1f33e125bef7052d1099a3e8160c527e2df373bc70dfde33b9aaaa90` |
| `build\FCCG\SilverStar_F407\Release\SilverStar_0_0_10.elf` | `b494e756b1b8dcd7c9d3cf4f4088ac5ac2f22140df9270e5b02eea3b56cd56ce` |

旧/新惯性 frontend 的 1000 次 C 轨迹逐字节相同，SHA-256
`2708f4f20b758ea7b4ca4963bc8cae97f59ca47a45d365bc2315e3078b2ace22`。

## 2026-09-18 — architecture-check 与 KF6 Power of Ten 合规修复

起始 HEAD：`8671cab2ccbeeaffeeaef7aea8d9ffd31c7db8b3`，起始 `git status --short` 为空。
本轮只在 FCCG 内进行检查器修复和结构重构；没有调整算法参数、默认值、history 容量、
checkpoint stride、排序、时间语义、NIS/P0/Q/R/reacquisition 数学、INS、任务状态机、
日志/decoder/project schema、GUI 或版本。`check_power_of_ten.ps1` 文件完全未改。
本节是本轮验收；下方上一轮日志诊断缺项不属于本次获准修改范围。

### 复现与检查器修复

使用修改前新生成的 `tests/artifacts/compliance/baseline`，实际执行 Release 的
`architecture-check` 和 `power10-check`，分别得到 **270 checks / 1 failure** 与
**16 failures**。架构误报准确定位 `System/Inc/system_time.h:38` 的 `provider's` 注释；
该注释未改动。Power of Ten 的七个 while、长函数与缺少断言问题全部复现。

Architecture 的 `Assert-NoArchitecturePattern` 增加可选 `-SanitizeRuntimeCode`，仅旧
Provider/VTable/callback 运行时 token 规则启用。sanitizer 沿用原 Power of Ten 的词法
状态处理方法；其他规则仍使用原 `Select-String` 原文扫描，include/path 检查不受影响。
原 `provider`、`ProviderOps`、`RegisterCallback`、`DioIrqHandler`、`Radio.` 模式均保留；
额外识别明确的 `provider_runtime...` 标识符。已有声明式 `provider_instance_hash` 等
身份字段不属于旧运行时回调架构，未引入宽泛 provider 前缀禁令。

实际生成工程 fixture 证明：block/line comments、含转义引号的 string 不误报；
FooProviderOps、ExampleProviderOps、RegisterCallback、DioIrqHandler、Radio.foo、
provider_runtime_identifier 和独立 provider token 全部命中，诊断行号正确；
`#include "stm32f4xx_hal.h"` 仍被原边界规则拒绝。

### 合规重构及数学不变证据

- 七个 while 全部改为显式 checkpoint/IMU/event capacity 上界的 for；循环后验证原
  条件已不成立，内部 invariant 损坏时断言，不静默越过未完成操作。
- Prune 顺序仍是 checkpoint → oldest → IMU → aiding events。
- Predict 拆分输入、时间、容量校验和历史保存；dt rounding、checkpoint stride、
  prediction_count 和状态提交次序保持不变。
- Insert 拆分输入/历史校验、索引查找、事件提交、checkpoint 选择及应用/失败处理；
  fast path、错误码、outcome reset、fault latch 和成功才提交 current state 均保留。
- Rebuild 拆出区间内量测处理，排序仍为 measurement time → position → velocity →
  barometer → source → sequence。全部大型 state/event 仍通过 pointer 传递。
- GnssEpochTrack 拆出重复 epoch reset 和 consistency 阶段；APP 仅拆出结果复制。
  同包不同 measurement time 仍先插入较旧分量，真实 receive-time outage 逻辑不变。
- 对内部对象、alignment、容量、索引及 loop postcondition 加真实断言。外部非法输入
  仍由原返回路径拒绝；新增空指针 fixture 证明不会由普通 INVALID 变成 fatal assert。

修改前生成工程完整保留。Host trace 对 **21,548 次操作**记录返回码及完整初始化后的
KF context、history（剔除 storage 指针地址）、storage/checkpoints、outcome 内容摘要，
包括 x/P、NIS、group result、计数和事件索引顺序。逐操作 FNV64 帧再计算 SHA256；
基线重复运行一致，11 组场景与最终版本全部一致。期望值固定在
`tests/fixtures/replay_compliance_trace.json`，不是从修后代码反推。
原 zero-delay 每步 x/P memcmp 测试继续保留。

另从修改前/后 APP 提取实际 GNSS 派发函数与原 work 类型进行编译，0/270、270/0、
0/0、100/100 ms 四种测试配置各 450 步轨迹一致，覆盖分量次序及结果复制。
测试配置只用于 Host 编译覆盖，不写回产品默认值。

历史数值故障注入验证 current state 不提交、outcome 为 NUMERIC_ERROR、faulted 锁存；
work-limit 分支使用临时源码副本注入一轮工作预算，原版/修后均通过 10 项断言。
生产 `NAV_REPLAY_MAX_STEPS=560` 与所有容量不变。history miss、overflow、epoch mismatch、
时间不连续、重复 receive epoch、真实 outage 和假 outage 回归均保留并通过。

### 最终标准工程与验证结果

标准工程：`tests/artifacts/compliance/SS_TEST_0`，项目名 `SS_TEST_0`。

| 验证 | 结果 |
|---|---|
| architecture-check Release | **PASS：270 checks，0 failures** |
| power10-check Release | **PASS：6036 checks，95 first-party C files，2264 functions** |
| Python 完整回归 | **411 passed，1 skipped，1145.98 s**；只读参考固件工作树非 clean，原 reference payload 同步测试按既有条件跳过，无失败 |
| 最终专项 pytest | **3 passed，99.69 s**；包含真实 architecture fixture、完整 KF trace、APP trace、work-limit 注入及原 replay fixture |
| 全部 Host tests | **68 executables，42672 checks，0 failures**；8 compile-pass，16 expected compile-fail；storage-integrity 4/4 |
| 其中 replay fixture | **28175 checks，0 failures** |
| ARM Release / Debug | **PASS / PASS** |
| stack-report Release / Debug | **PASS / PASS**，原 256-byte minimum margin 门限未改 |
| memory-report / artifact-check | **PASS / PASS**，heap reserved=0、runtime heap symbols=0 |
| git diff --check | **PASS** |

主要日志位于标准工程下 `architecture-check.log`、`power10-check.log`、
`validation-host.log`、`validation-Release.log`、`validation-Debug.log`；完整 Python
日志为 `tests/artifacts/compliance/python-full.log`。全量命令使用当前 Make 的
`TARGET_PROFILE=SilverStar_F407 CONFIG=Release/Debug`，没有跳过质量门禁。
Python 命令为 `python -m pytest -q --ignore-glob=tests/.pytest*`，basetemp 和 cache
均在 `tests/artifacts/compliance/`；ignore 只排除历史临时目录，不排除真实测试。

### 资源与有界工作量对比（字节）

| 项目 | 修改前 Release | 修后 Release | 修改前 Debug | 修后 Debug |
|---|---:|---:|---:|---:|
| FLASH / bin | 266968 | 268432 | 284680 | 286400 |
| main SRAM | 95288 | 95288 | 95304 | 95304 |
| `.data` | 1128 | 1128 | 1128 | 1128 |
| main `.bss` | 85072 | 85072 | 85088 | 85088 |
| CCM `.ccmram_bss` | 61936 | 61936 | 61936 | 61936 |
| Estimator worst-known stack | 2348 | 2348 | 2436 | 2524 |
| Estimator stack margin | 1748 | 1748 | 1660 | 1572 |

FLASH 增加 Release **1464**、Debug **1720**（均小于 0.7%），来自有界循环、真实断言和
函数拆分；main SRAM、CCM、history **27232** 字节及 heap 均无增长。
Debug 栈增加 **88**：旧 Insert/Rebuild 调用链帧合计 184，新 Insert/InsertedApply/
Rebuild/IntervalApply 合计 272；未增加 NavigationKfContext 大对象栈副本。
Release 优化后的 Estimator worst-known stack 不变。

| 200 Hz IMU + 200 Hz Baro + 25 Hz GNSS | 基线/修后 max replay steps | 基线/修后 event HWM | history miss / overflow |
|---|---:|---:|---|
| Baro 0 ms，GNSS 0/270 ms | 151 / 151 | 168 / 168 | 0 / 0 |
| Baro 100 ms，GNSS 0/270 ms | 131 / 131 | 148 / 148 | 0 / 0 |
| Baro 550 ms，GNSS 0/270 ms | 171 / 171 | 58 / 58 | 0 / 0 |

Release ELF SHA256：`861f3c49c06f9da868a47503d930cbb38a76b88b7c61d9e385b52e4845b8399d`。
Debug ELF SHA256：`a4a5a9632524f7f3afda59947ea3163ccca9adfb8b98183a6afb3e5f7d8394bd`。
这是 Host 数学等价、静态资源和编译验收，不是板上周期测量；on-target timing、动态
stack HWM 与外场飞行尚未实机验证。

### 外场参数核对

最终 `Generated/Inc/project_algorithm_parameters.h` 与本轮 baseline **逐字节相同**。
`SilverStar.ssproject` 实际参数：GNSS horizontal/vertical/velocity sigma=1.5/2.5/0.15，
GNSS vU scale=1.75，Baro=2.5，outage=300 ms，position/velocity/baro delay=0/270/0 ms。
600 ms history、144/48/160/8 容量、18 checkpoint stride、560 work bound 全部未改。

本轮软件门禁外场候选状态：**FIELD TEST READY = YES（软件门禁候选，非实机飞行认证）**。

### 修改文件

- `plugins/builtin/silverstar_core_0_0_10/payload/Tools/check_architecture.ps1`
- `plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Src/navigation_kf.c`
- `plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Src/navigation_kf_replay.c`
- `plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/estimator_task.c`
- `plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_navigation_kf_replay.c`
- `tests/test_compliance_refactor.py`
- `tests/replay_compliance_support.py`
- `tests/fixtures/replay_compliance_trace.json`
- `tests/fixtures/estimator_replay_trace.c`
- `tests/fixtures/replay_work_limit.c`
- `VALIDATION.md`

生产源、Host fixture 和 architecture checker 已属于 reference importer 的 FCCG-owned
清单，本轮未新增生产文件，不需要改变导入源图；原 Power of Ten checker、schema、
manifest 和 replay header 未修改。


## 2026-09-17 — KF6 fixed-lag replay 与传感器建议值（诊断日志未闭环）

本轮只修改 FCCG，基于 HEAD `34e16ef282402e3800c20492b32255143c0da67b`；起始工作区干净。
未修改 FLP、GSHC、参考固件、全局环境或原有未提交内容；未 commit/push。
实现契约、时间链和推荐值审计分别见 [KF6 replay](docs/KF6_FIXED_LAG_REPLAY.md)、
[参数契约](docs/ALGORITHM_PARAMETERS.md)、[插件契约](docs/PLUGIN_FORMAT.md)。

### 完成范围与未完成项

- JY901B 原 5 m 人工保守值改成 1.5 m recommendation；无原生逐样本 variance 的事实用
  unsupported/invalid 标记表达，不能再把建议值平方伪装成原生 R。KF setter 的 1.5 m
  隐式钳制已删除；气压量测 R = configured sigma²，1.0/2.5/5.0 均可保存和生成。
- 建议值是 Device 的声明式 metadata，UI 只显示来源/数值/单位；不进入 shared-key
  compatibility，不覆盖工程实际值。JY901B process sigma、NEO-M9N sigma recommendation
  保持 descriptor/fallback 语义；真实 hAcc/vAcc/sAcc 保留原生不确定度语义。
- 保留算法自身合法数值域、真实设备速率/量程、协议/C 表示范围、资格/质量门限及资源
  限制。非有限输入、非法 R、超历史/容量和时间不连续显式拒绝，不以静默 clamp 放行。
- 新建工程 GNSS sigma = 1.5/2.5/0.15，vertical scale = 1.75，baro sigma = 2.5，
  outage = 300 ms；position/velocity/baro delay = 0/270/0 ms。旧工程显式值优先；
  已有 owner 缺失的新 delay 补 0，缺失 baro/vertical scale 分别补旧默认 5/1。
- 一套 engine 同时处理 GNSS position、velocity 和 Barometer；完整 KF context 检查点
  恢复后，在 measurement time update，再按时间重放 IMU 与 aiding events 到 present。
  保存导航系 IMU 增量，姿态不重复传播；回放不重复发日志、遥测或任务副作用。
- GNSS 原接收侧 availability/consistency 只按 receive time 执行一次；历史中携带其
  不可变证据。270 ms 算法延迟不参与 outage 时钟；真实失联恢复数学规则保持原样。
- Barometer 在算法参数页 advanced 参数 `baro_measurement_delay_ms` 设置非零即进入
  同一 engine；0 使用旧 fast path（无可信历史 epoch 时）。可信 MCU sample timestamp
  优先，绝不再减 configured delay。参数合法范围 0–550 ms，历史窗口 600 ms。
- **尚未完成：SSLOG replay 汇总诊断输出。** 内部 replay/history-miss/overflow/rejection、
  steps/runtime/HWM 已记录；decoder 已包含三个实际 delay，旧 native/measurement record
  仍保留输入时间。自动审批按早期“日志不变”限制拒绝了新的诊断 record，并拒绝了保留
  原 29 个 record 布局、仅追加 EVENT 含义的兼容方案；已请求本轮追加 EVENT 授权，尚未
  收到答复，因此没有落地这些日志改动。不能宣称第十四节诊断要求或整项任务全部完成。

### 时间同步与 Fixed-Lag Replay 的衔接

原 Platform/System Time 负责统一 MCU 单调微秒、计数器回绕、任务原点和外部提供的 UTC
对应关系。惯性 hub 当前只运行 PASSTHROUGH；JY901B 压力帧和 NEO-M9N NAV-PVT 的 sample
时间均来自接收解析时钟，iTOW 尚无自动 MCU epoch 映射。原机制不恢复历史状态。

本轮在原 SystemTime 中增加 measurement time 解析，而没有复制时钟系统：
可信且已转 MCU 轴的 native sample → 直接使用；否则 receive − configured delay →
统一 replay engine → 历史完整 KF x/P/internal state → measurement update → 后续事件
重放 → present。只修正 timestamp 后在 current x/P 更新的实现被测试作为错误负面对照。

### 自动化验证

所有生成、编译和临时文件均在 `tests/artifacts/fixed_lag/`，未降低原有内存、栈、
编译拒绝或 golden 验收门限。

| 检查 | 结果与证据 |
|---|---|
| 全部 Python tests | **409 passed, 1 skipped**, 1075.85 s；`python-full-03.log` |
| 唯一 skip | 只读参考固件工作树非 clean，原测试自行跳过 reference payload 精确同步检查；未为通过测试修改参考目录 |
| 推荐值/UI/参数与 replay 定向回归 | `pytest-05` 35 passed；随后边界/文档/source-graph `pytest-07` 8 passed |
| 最终引擎 + 最大 delay 补验 | `pytest-09` 1 passed；实际 C fixture **28,160 checks, 0 failures** |
| 最终生成固件完整 Host | `integration-04/validation-host.log`：**68 executables, 37,569 checks, 0 failures**；8 compile-pass、16 expected compile-fail；storage-integrity 4/4 |
| Golden/deterministic | 全部 Python/Host 回归中的原测试通过；原 golden fixture 未修改，以相同旧实际参数验证旧输出 |
| ARM Release / Debug | 均通过 `all stack-report memory-report artifact-check`；最终产物 `integration-04` |
| 差异检查 | `git diff --check` 通过 |

完整 Python 命令：
`python -m pytest -q --ignore-glob=tests/.pytest* --basetemp=tests/artifacts/fixed_lag/pytest-full-03 -o cache_dir=tests/artifacts/fixed_lag/pytest-cache`。
完整 Python 运行期间最终优化了高频 Barometer 的紧凑存储，因此另外用最终生成固件完整
Host 和 `pytest-09` 验证该 C 版本。`integration-04` 包含 0/100 ms 满速压力场景；此后
仅增加 550 ms 测试场景，未改生产代码，由 `pytest-09` 编译最终 fixture 执行。

C 测试覆盖：相同参数/输入下零延迟 x/P 逐步 memcmp；GNSS 及气压历史更新；IMU 区间
中间的气压采样；多 delay 到达乱序；同时间确定排序；环多次回绕；真实/伪 outage；
重复 GNSS receive epoch；太旧量测、epoch/reset、容量/速率溢出、时间不连续、NaN；
64 位时间边界；可信 native 时间不双减 delay；P finite/对称/对角非负与状态计数一致。
零延迟等价指相同实际参数和 R 的旧 KF 数学路径；不能把新默认值或本轮明确修改的
Barometer R 语义变化描述成旧默认输出完全不变。

### ARM 静态资源（字节）

基线来自本轮修改前重新生成的 `baseline`，不是沿用旧报告数值。

| 项目 | 基线 Release | 最终 Release | 基线 Debug | 最终 Debug |
|---|---:|---:|---:|---:|
| FLASH / bin | 261728 | 266968 | 279224 | 284680 |
| main SRAM | 78032 | 95288 | 78048 | 95304 |
| `.data` | 1128 | 1128 | 1128 | 1128 |
| main `.bss` | 67816 | 85072 | 67832 | 85088 |
| CCM `.ccmram_bss` | 51112 | 61936 | 51112 | 61936 |
| main + CCM SRAM | 129144 | 157224 | 129160 | 157240 |
| Estimator worst-known stack | 1964 | 2348 | 1868 | 2436 |
| Estimator stack margin（4096 配置） | 2132 | 1748 | 2228 | 1660 |

main SRAM 增加 17,256；CCM 增加 10,824；总 SRAM 增加 **28,080**。
History/context 两个静态对象为 `s_replay` **17,248 main SRAM** 与 `s_replay_storage`
**9,984 CCM**，合计 **27,232**；其余增量包括 KF group generation、快照字段及对齐。
最终 Release/Debug main SRAM 余量分别 35,784/35,768，CCM 余量 3,600；保留原产品
reviewed resource gates。heap reserved = 0，linked runtime heap symbols = 0。

静态容量：144 IMU + 48 GNSS + 160 compact Barometer + 8 full KF checkpoints，共用
有序事件索引。理论单次 replay 预测分段/量测更新上限 **560**，全部循环也有固定容量
边界。200 Hz IMU + 200 Hz Barometer + 25 Hz GNSS 实测合成事件流：

| Barometer delay | GNSS position/velocity delay | 最大 replay steps | event HWM | overflow / history miss |
|---|---|---:|---:|---|
| 0 ms | 0 / 270 ms | 151 | 168 | 0 / 0 |
| 100 ms | 0 / 270 ms | 131 | 148 | 0 / 0 |
| 550 ms | 0 / 270 ms | 171 | 58 | 0 / 0 |

Release ELF SHA256: `a95cb8c0f161a9bd04be00027835b4f2a0ea48f251475e8397086eaa2bd2d6cf`。
Debug ELF SHA256: `70bab162b91005ecd9cc77c1df90015e931d699217f7dd7b6484c05da7997ac5`。

**ARM 编译通过，但 on-target cycle timing 尚待实机验证。** 本轮无上板运行结果，
没有 CPU 利用率、真实任务周期、动态栈 HWM 或外场精度承诺。Host 步数与静态栈分析
不能证明 200 Hz 实时 deadline；下一轮需板上压力测试，尤其 CCM 仅余 3,600 字节。

### 本轮文件清单

- `VALIDATION.md`
- `docs/ALGORITHM_PARAMETERS.md`
- `docs/KF6_FIXED_LAG_REPLAY.md`
- `docs/PLUGIN_FORMAT.md`
- `docs/README.md`
- `plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Inc/navigation_kf.h`
- `plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Inc/navigation_kf_replay.h`
- `plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Src/navigation_kf.c`
- `plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Src/navigation_kf_replay.c`
- `plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/module.mk`
- `plugins/builtin/silverstar_algorithm_estimator_kf6/plugin.json`
- `plugins/builtin/silverstar_core_0_0_10/payload/APP/Inc/estimator_bus.h`
- `plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/device_task.c`
- `plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/estimator_task.c`
- `plugins/builtin/silverstar_core_0_0_10/payload/Interfaces/Inc/system_barometer_if.h`
- `plugins/builtin/silverstar_core_0_0_10/payload/Interfaces/Inc/system_gnss_if.h`
- `plugins/builtin/silverstar_core_0_0_10/payload/System/Inc/system_time.h`
- `plugins/builtin/silverstar_core_0_0_10/payload/System/Src/system_time.c`
- `plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/run_tests.ps1`
- `plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_air_kf.c`
- `plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_jy901b_adapter.c`
- `plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_navigation_kf_replay.c`
- `plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_profiles.c`
- `plugins/builtin/silverstar_device_gnss_neo_m9n/plugin.json`
- `plugins/builtin/silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B/Adapter/Inc/jy901b_barometer_build_capabilities.h`
- `plugins/builtin/silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B/Adapter/Src/jy901b_barometer_adapter.c`
- `plugins/builtin/silverstar_device_imu_jy901b/plugin.json`
- `schemas/plugin.schema.json`
- `src/silverstar_fccg/i18n/en_US.json`
- `src/silverstar_fccg/i18n/zh_CN.json`
- `src/silverstar_fccg/plugins/algorithm_parameters.py`
- `src/silverstar_fccg/plugins/manifest.py`
- `src/silverstar_fccg/plugins/recommendations.py`
- `src/silverstar_fccg/project/algorithm_parameters.py`
- `src/silverstar_fccg/ui/main_window.py`
- `src/silverstar_fccg/ui/pages/algorithm_parameters.py`
- `tests/test_algorithm_parameters.py`
- `tests/test_fixed_lag_replay.py`
- `tests/test_project_domain.py`
- `tests/test_sensor_recommendations.py`
- `tools/import_reference_components.py`


## 2026-09-17 — 外场前工程默认根目录一致性收尾

本节只记录本轮路径修改；下方较早的 KF6 报告属于历史基线，本轮未改算法。
初始 HEAD：`bad4167`；初始 `git status --short` 为空。
没有 commit/push、reset/checkout/clean，没有删除或覆盖用户原有未提交内容。
GSHC 未修改；FCCG 和 FLP 分别复用本仓库 PathPreferences，无新的跨仓库依赖。

### 修改文件与原因

- `src/silverstar_fccg/core/path_preferences.py`：给既有 PathPreferences 增加
  `DefaultProjectRoot_EffectiveGet`，提供统一、只读的有效默认根目录。
- `src/silverstar_fccg/ui/main_window.py`：New/Open/Save As 与默认目录设置入口复用 helper；
  Open 不再用 service.workspace_root，Save As 不再固定 Documents。
  Save As 用 Qt 目录对话框分别设置现存初始 root 与当前工程名；即使同名目录存在，
  也不会自动进入该目录而丢失 root 初始位置。用户仍可选择其他目录。
- `src/silverstar_fccg/ui/dialogs/new_project.py`：自动推导状态下 Browse 从 root 开始；
  手动路径后保留原自定义目录/最近现存父目录行为。
- `tests/test_path_preferences.py`：实际入口拦截测试，覆盖默认根目录、Unicode 名称、
  同名目录已存在、取消、无效偏好 fallback、插件/工具链入口保持原目录。
- `tests/test_device_capability_architecture.py`：原 Save As 完整复制集成测试改为拦截
  QFileDialog.exec/选择结果；捕获错误提示并断言无错误，避免自动化停在隐藏模态框。
  继续检查完整工程复制与设备源码保留，没有降低原有验收条件。
- `docs/GUI_STYLE_GUIDE.md`：说明统一路径规则。
- `VALIDATION.md`：本轮验收与检查限制。

### 最终路径规则

有效配置 → 现存 Documents → 现存 Home → cwd；不存在、不再是 directory、缺失盘符、
空/损坏/相对路径配置安全 fallback，读取不 mkdir、不重写 JSON。
设置位置仍为独立 `.fccg/path_preferences.json`，schema_version 1 不变。

例如 root=D:/SilverStarProjects、name=SS_TEST_0：
New 保持自动目标 D:/SilverStarProjects/SS_TEST_0，自动 Browse 从 D:/SilverStarProjects 开始；
Open 从 D:/SilverStarProjects 开始；
Save As 的目录视图从 D:/SilverStarProjects 开始，名称预填 SS_TEST_0。
目录不存在时用户可明确创建或改选；仅显示对话框不会创建目录或移动工程。
已存在同名目录仍受原 Save As 嵌套/非空目标及生成安全检查约束，不静默覆盖。
普通 Save、手工自定义路径不变，Open/Save As 不更新用户的 Default Project Root。

插件安装/导出、工具链 executable、CubeMX IOC、source-package 对话框没有被改到 root。
语法树对比确认 MainWindow 仅四个方法发生变化：
_DefaultProjectRoot_Select、_NewProject_Show、_Project_OpenDialog、_Project_SaveAs。

### 检查结果

- 定向路径测试：
  `python -m pytest tests/test_path_preferences.py -q --basetemp=tests/.pytest-root-drive-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **10 passed, 1.50 s**。包含实际缺失盘符、删除后的目录、普通文件、坏 JSON、空配置、
  首次启动、Documents/Home/cwd 逐级 fallback；前后偏好字节、工程模型不变。
- 保存相关完整文件：
  `python -u -m pytest tests/test_device_capability_architecture.py -vv --basetemp=tests/.pytest-root-save-debug-20260917 -o cache_dir=tests/.pytest-root-cache-20260917 -o faulthandler_timeout=60`：
  **22 passed, 49.77 s**。日志保留于 `tests/.pytest-root-cache-20260917/.pytest-root-save-debug-20260917.log`。
- 首次定向测试错误地直接赋值冻结的 ProjectIdentity，报 FrozenInstanceError；
  新测试已改用既有 ProjectDraft_Create，不修改产品模型或解除冻结。
- 第一次全量收集遇到旧 `tests/.pytest_cache/sparse0916` ACL 拒绝；后续使用
  `--ignore-glob='tests/.pytest*'` 排除历史测试缓存，不删除缓存，也不跳过正式测试文件。
- 随后的全量运行在保存服务错误提示处停滞，超时栈确认是 _Error_Show 的模态提示；
  只终止本次自有测试进程。未完成运行不计通过。保存源工程独立复制和整个保存测试文件均通过，
  随后改进测试错误捕获并重新执行全量检查。产品保存服务未作猜测性修改。

- 最终完整复验：
  `python -u -m pytest tests -x -vv --ignore-glob='tests/.pytest*' --basetemp=tests/.pytest-root-diagnose-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **398 passed, 1 skipped, 711.13 s**。虽然启用首错停止，但本次没有失败，399 项均完成判定。
  日志保留于 `tests/.pytest-root-cache-20260917/.pytest-root-diagnose-20260917.log`。
  唯一跳过：`test_prompt_acceptance.py:287`，只读参考固件任务仍活跃，本轮未中断或改写参考工程。
- `git diff --check` 通过；没有为 FCCG 添加未在开发环境要求中的 Ruff/mypy 工具。
- 最终报告写入后，`python -m pytest tests/test_documentation.py -q --basetemp=tests/.pytest-root-docs-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：**6 passed, 0.27 s**。

### 未修改的问题与交付边界

一次未完成的全量运行出现既有服务复制测试失败，后续 GUI 错误提示导致停滞；没有保留到该次
会话最终异常摘要，不能据此确定根因。独立复制、保存测试文件及最终全量复验均通过。
保存服务完全无 diff；若用户实际保存时再次遇到错误，建议独立收集异常后处理，不做推测性重构。
本轮将自动化错误提示转成明确断言失败，避免以后隐藏弹窗掩盖错误。

GNSS CONFIG READ/SHOW 差异未在本轮诊断或修改，按提示词留待下一轮新固件外场核验。
未改 KF6、INS、GNSS 融合/质量门/reacquisition、算法默认参数、NIS、P/Q、协议或日志格式。
FCCG project 12、decoder semantics 1.2、FLP .ssflp v3/schema 均不变；没有自动移动用户工程。
最终保留上述文件的未提交修改，无 push。测试产物均位于 tests 的忽略目录内。


## 2026-09-17 — KF6 外场反馈第二轮与默认工程根目录

初始 HEAD：`60dd1f3d4d92cfaf308771e3e2d92890592cf048`。
初始 `git status --short` 为空。未 reset/checkout/clean；本轮分别本地中文提交，不 push。
参考固件只读，三个产品无跨仓库运行时依赖。下方文件清单与 diff 统计是不含本报告的提交前快照。

### 算法结论与边界

旧实现仅用连续 hard reject 和 GNSS 自身一致性授权恢复，导致连续有效 GNSS 的动态不一致
也会触发 inflation。现在 position EN/U、velocity EN/U 分别保存有效时间戳、outage/loss latch
和恢复计数。有效样本即使 NIS 拒绝也刷新该组可用时间；距该组上次有效样本严格超过
`gnss_reacquire_outage_ms` 才允许掉线恢复。完整缺失在下一个 epoch 返回时识别；单组无效独立计时。
position 的可用性不依赖 velocity；其返回一致性检查仍可要求对应 velocity。

默认 300 ms，可配 100–10000 ms。25 Hz 下约 7.5 个周期，100 ms 小缺口不算掉线；
候选 160/200/250/300/500 ms 通过合成回放扫描，未宣称真实飞行最优。
正常连续 high-NIS 不 inflation；真正 outage 后先正常 NIS，能融合则直接恢复，不膨胀。
否则需五次连续 hard reject、三个一致间隔和真实 outage，才启动选择性 DPD'。
factor=2、最多八次、两次尝试间至少五个 reject、三个融合返回后退出均保留；
大误差用例需要多次尝试，因此没有无依据把上限减为一次。
新掉线清除旧恢复计数；重复、回退、零时间戳及非法 sigma 不可积累恢复授权。

保持六状态、Q、P0、重力、INS/姿态、NIS 阈值、GNSS 质量门、部署与着陆逻辑。
Barometer 观测 pU，并通过 P(vU,pU) 修正 vU；GNSS pU 与 vU 分别做独立一维更新。
速度噪声保持 receiver uncertainty 与 accuracy scale：
`sigma_EN=max(receiver_sigma_EN*1.25, gnss_velocity_std)`；
`sigma_U=max(receiver_sigma_U*1.25, gnss_velocity_std)*gnss_velocity_vertical_scale`；
R 为最终 sigma 的平方。新 scale 只作用量测，P0 不变。

| 参数 | 正式默认 | 离线候选 |
| --- | ---: | --- |
| GNSS pU sigma floor | 2.5 m | 2.5 / 3 / 4 / 5 / 6 m |
| Barometer sigma floor | 5 m | 1.5 / 2 / 3 / 5 m |
| GNSS velocity floor | 0.15 m/s | 保留原参数 |
| GNSS velocity U scale | 1.0 | 1 / 1.25 / 1.5 / 2 |
| GNSS outage | 300 ms | 160 / 200 / 250 / 300 / 500 ms |

无实测日志，不能给出手持最优或飞行最优；保守飞行候选仍是兼容默认。所有候选需真实飞行确认。
未改 AIR/GSP、SSLOG/schema、project 12、decoder semantics 1.2、参数 schema 1.0、
Platform 0.0.10；保留 sparse-preflight、分组 NIS 展示与存储完整性规则。
新参数缺失由 manifest default 补齐，生成常量和 decoder actual values 同源。
导入器登记 FCCG-owned C/H 与 Host fixture，防止重新导入参考源覆盖修复。

### 路径工作流

File → 默认工程根目录 / Default Project Root 写入独立 UTF-8 原子 JSON：
生产位置 `.fccg/path_preferences.json`（测试注入路径位于 tests）。
例如 root=`D:/SilverStarProjects`，name=`Test01`，最终目录=`D:/SilverStarProjects/Test01`。
名称自动跟随，实际手动编辑或 Browse 后保持自定义目录。Browse 从最近存在的父目录开始。
JSON 缺失/损坏、schema 不符或根目录不存在均安全 fallback，不自动创建未经确认的根目录。
偏好不进入 project/decoder hash，不影响 Dirty 或既有 Save/Open。

### 测试命令与结果

下列为本次命令入口及可复验的隔离目录参数；日志、生成物均在 tests 下。

- `python -m pytest tests -q --ignore-glob='tests/.pytest-*' --basetemp=tests/.pytest-full-0917`：
  **389 passed, 1 skipped, 679.78 s**。日志 `tests/.pytest-cache/0917-full.log`。
  唯一跳过：`test_prompt_acceptance.py:287` 的只读参考固件任务仍活跃，不修改或中断参考工程。
- 全量收集后新增了非默认 U scale 的生成 C 测试，并收紧导入器的已声明 owned header 条件。
  最终 `python -m pytest tests/test_kf6_outage.py tests/test_path_preferences.py tests/test_algorithm_parameters.py -q`
  **28 passed, 59.49 s**，日志 `tests/.pytest-cache/0917-final-focus.log`；
  `python -m pytest tests/test_reference_import_progress_adapters.py tests/test_kf6_outage.py tests/test_path_preferences.py -q`
  **5 passed, 24.13 s**，日志 `tests/.pytest-cache/0917-last.log`。
  不把这些后续测试合并冒充一次完整 390 项运行。
- `FccgService.ReferenceProject_Create("Kf6Outage")` 后 `Project_Save` 生成
  `tests/.pytest-outage-0917/generated`，由测试辅助函数编译真实生成 C fixture。
- 生成目录内 `./Tests/Host/run_tests.ps1 -HostCompiler D:/msys64/ucrt64/bin/gcc.exe`：
  **67 executables / 14484 checks / 0 failures / 8 compile-pass / 16 expected compile-fail**；
  日志 `tests/.pytest-outage-0917/host-0917.log`。包含 estimator、KF、storage、sparse preflight。
- 生成目录内，Arm GCC 14.3.1，
  `D:/msys64/ucrt64/bin/mingw32-make.exe -j4 SHELL=cmd.exe CONFIG=Release all stack-report memory-report artifact-check`，
  Debug 同命令改 `CONFIG=Debug`：两者通过。日志
  `tests/.pytest-outage-0917/target-release.log`、`target-debug.log`。
- `python -m pytest tests/test_documentation.py -q --basetemp=tests/.pytest-doc-final-0917`：最终文档检查 **6 passed, 0.27 s**。
- `git diff --check` 与 `git diff --cached --check`：通过。
- Qt offscreen：Light/Dark × zh_CN/en_US 新建窗口均渲染，测试进程显式加载 Windows 字体；
  检视中文 Light 和英文 Dark 无布局裁切。图在 `tests/.pytest-visual-0917/`；不等于实体屏验收。

| 配置 | FLASH bytes（相对上一轮） | main SRAM | CCM RAM | heap |
| --- | ---: | ---: | ---: | ---: |
| Release | 261720 (+416) | 78032 (+0) | 51112 (+48) | 0 |
| Debug | 279224 (+384) | 78048 (+0) | 51112 (+48) | 0 |

均检查 138 个 .su、八个任务；heap symbols=0。任务栈余量顺序为
Device/INS/Estimator/Flight/Logger/Serial/Telemetry/Idle：
Release=552/1032/2132/668/1696/1944/2116/256 bytes；
Debug=728/1264/2228/1804/1704/3216/2436/256 bytes。
linked ELF 与静态预算通过；未做实机时序、刷机、EIDE 或飞行认证。

Release ELF SHA256：
`ded64a42ddc58bafd70a5a737b7229cba75583956673ab224812fa27345b9316`；
Debug：
`753686f28769715cf966e2e032f2a88412d18d8fc06cf3f026e8162e4d4d9be9`。

### 跨仓库数值与缺失实测

独立固定 fixture：十个场景、每场景 64 帧，共 640 行，C 输入/状态为 float32。
FLP 数值比较最大差：position **7.499018093992671e-09 m**，
velocity **4.881515330845687e-11 m/s**，P **3.7143001591077862e-09**。
恢复状态与计数完全一致；偏差来自 C 文本数值序列化精度，达到 float32 等价要求。
fixture 是各仓库本地验证数据，无运行时相互导入。

在三仓库、D:/python_software 与用户 Desktop 含隐藏/忽略路径搜索 SS0005–SS0008，
未找到真实 BIN/SSLOG；少数历史测试缓存 ACL 不可读。不宣称扫描了所有磁盘。
**未执行真实 SS0005–8 A/B**；四组日志最佳 shift 均未知，无稳定 GNSS 物理延迟结论。
FLP 合成已知 +80 ms 延迟找回 -80 ms，只证明工具，不支持固件补偿。本轮未加入固定延迟。

### 提交前 Git 快照（不含本报告）

初始 HEAD 复核：60dd1f3d4d92cfaf308771e3e2d92890592cf048

```text
M	docs/ALGORITHM_PARAMETERS.md
M	docs/GUI_STYLE_GUIDE.md
A	docs/KF6_OUTAGE_RECOVERY.md
M	docs/README.md
M	docs/platform/details/NAVIGATION_AND_ESTIMATION.md
M	plugins/builtin/silverstar_algorithm_estimator_kf6/docs/NAVIGATION_AND_ESTIMATION.md
M	plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Inc/navigation_kf.h
M	plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6/Src/navigation_kf.c
M	plugins/builtin/silverstar_algorithm_estimator_kf6/plugin.json
M	plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/estimator_task.c
M	plugins/builtin/silverstar_core_0_0_10/payload/System/Inc/system_estimator_profile.h
M	plugins/builtin/silverstar_core_0_0_10/payload/System/Src/system_estimator_profile.c
M	plugins/builtin/silverstar_core_0_0_10/payload/System/User/system_user_config.h
M	plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_air_kf.c
M	plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_algorithm_parameters.c
A	plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/test_kf6_outage.c
A	src/silverstar_fccg/core/path_preferences.py
M	src/silverstar_fccg/i18n/en_US.json
M	src/silverstar_fccg/i18n/zh_CN.json
M	src/silverstar_fccg/ui/dialogs/new_project.py
M	src/silverstar_fccg/ui/main_window.py
M	tests/algorithm_parameters_support.py
A	tests/fixtures/kf6_outage_vectors.json
M	tests/test_algorithm_parameters.py
A	tests/test_kf6_outage.py
A	tests/test_path_preferences.py
M	tools/import_reference_components.py

 docs/ALGORITHM_PARAMETERS.md                       |  8 ++-
 docs/GUI_STYLE_GUIDE.md                            |  9 +++
 docs/KF6_OUTAGE_RECOVERY.md                        | 66 +++++++++++++++++
 docs/README.md                                     |  1 +
 docs/platform/details/NAVIGATION_AND_ESTIMATION.md |  5 +-
 .../docs/NAVIGATION_AND_ESTIMATION.md              |  5 +-
 .../Algorithm/Estimator/KF6/Inc/navigation_kf.h    |  3 +
 .../Algorithm/Estimator/KF6/Src/navigation_kf.c    | 70 ++++++++++++++++--
 .../silverstar_algorithm_estimator_kf6/plugin.json | 47 +++++++++++-
 .../payload/APP/Src/estimator_task.c               |  8 +--
 .../payload/System/Inc/system_estimator_profile.h  |  3 +-
 .../payload/System/Src/system_estimator_profile.c  |  8 ++-
 .../payload/System/User/system_user_config.h       |  7 ++
 .../payload/Tests/Host/test_air_kf.c               |  8 +++
 .../payload/Tests/Host/test_algorithm_parameters.c | 11 +--
 .../payload/Tests/Host/test_kf6_outage.c           | 84 ++++++++++++++++++++++
 src/silverstar_fccg/core/path_preferences.py       | 45 ++++++++++++
 src/silverstar_fccg/i18n/en_US.json                |  3 +-
 src/silverstar_fccg/i18n/zh_CN.json                |  3 +-
 src/silverstar_fccg/ui/dialogs/new_project.py      | 25 +++++--
 src/silverstar_fccg/ui/main_window.py              | 20 +++++-
 tests/algorithm_parameters_support.py              |  4 +-
 tests/fixtures/kf6_outage_vectors.json             |  1 +
 tests/test_algorithm_parameters.py                 |  2 +-
 tests/test_kf6_outage.py                           | 43 +++++++++++
 tests/test_path_preferences.py                     | 46 ++++++++++++
 tools/import_reference_components.py               | 11 ++-
 27 files changed, 510 insertions(+), 36 deletions(-)
```

最终提交后的工作区状态另在交付消息核验。


## 2026-09-16 — Sparse preflight logging closeout

Initial source worktree clean at `b5904e3`. No reset, checkout, commit or push. Production
change is limited to the two defaults and explicit compiler-override guards in the builtin
System/User/system_user_config.h. Platform 0.0.10, project format 12, decoder/project-semantics
1.2, SSLOG/AIR/maintenance layouts and versions are unchanged. KF6/INS mathematics, Q/R/P0,
GNSS qualification/reacquisition, START transaction and deployment algorithms were not edited.

### Root cause and producer audit

Both existing preflight macros defaulted to 1, allowing continuous native/corrected sensor records
through their existing producer-side gates. They now default to 0 under #ifndef guards.

- DeviceNativeLog_Process / ImuProcess return before logging snapshot reads, dedup advancement
  or LoggerBus push outside FLIGHT/RECOVERY. IMU_NATIVE, GNSS_NATIVE, BARO_NATIVE, MAG_NATIVE
  and HW_QUAT_NATIVE are gated. Underlying DeviceTask startup/device processing still runs.
- ImuSampleBus continues SystemInertial_NextGet, source-sequence validation,
  SystemCalibration_ImuSampleProcess and consumer queueing; only CorrectedLog skips IMU_CORRECTED.
- InsTask's pre-existing mission/lifecycle gate controls flight mechanization outputs; preflight
  alignment remains active. EstimatorTask's pre-existing prediction gate controls measurement,
  state/covariance/diagnostic output; GNSS/Baro origin collection remains separate and active.
- Power/Health/Stats and event-driven diagnostics retain their original cadence/policies.
  No LoggerBus admission policy, queue capacity, drop counter or writer integrity code changed.

Preserved: file header; decoder profile, SYSTEM_CONFIG, DEVICE_DESCRIPTOR, ALGORITHM_DESCRIPTOR,
LOG_STREAM_DESCRIPTOR; boot/self-test/config diagnostics; calibration and alignment start/result/
failure; final GNSS/Baro origins; mission config, INITIAL_STATE, START/START_REJECTED and fault events.
LoggerTask still creates the session at boot and drains throughout preflight.

START still performs Prepare → origin freeze → navigation initialization → flight-queue reset
before committing FLIGHT; FlightTask then writes the start snapshots/events. The change introduces
no queue reset and does not advance native dedup while gated. Host tests confirm the first native,
corrected and navigation-output records at START and each 10 ms IMU sample throughout 20 s.
This is a Host boundary result, not a target task-scheduling guarantee.

LANDING retains the original lifecycle gates, 1000 ms grace, drain, flush, finalize and fault
behavior. The fixture enters LANDED and arms real LoggerBus finalization with the landing time;
ordinary native/corrected flight logging ends and low-rate tail records continue until closure.

Diagnostic full preflight remains available by changing the generated header values to 1U, or
passing `-DSYSTEM_LOG_PREFLIGHT_NATIVE_ENABLE=1U` and
`-DSYSTEM_LOG_PREFLIGHT_CORRECTED_IMU_ENABLE=1U` to the compiler. Both Release and Debug otherwise
use sparse defaults. No new checkbox, manifest parameter, project field or decoder field was added.
See [policy and producer ownership](docs/PREFLIGHT_LOGGING.md).

### Files and regression coverage

- `plugins/builtin/silverstar_core_0_0_10/payload/System/User/system_user_config.h`: defaults/guards.
- Its `Tests/Host/storage_integrity/test_sparse_preflight.h`: Host device/inertial/calibration-state
  facades and preflight/flight/landing workload; calls real native producer, ImuSampleBus and
  calibration correction implementation. Sampling and calibration-consumer calls continue for
  all 14,100 samples in the 120 s case, with zero sample-bus source gaps or overflow.
- Its `Tests/Host/storage_integrity/test_logger_storage.c`, `run_storage_integrity.py`: link actual
  producer sources into the existing real LoggerBus→LoggerTask→codec→FatFs→diskio delayed-DMA
  chain; build both default and explicit diagnostic macro configurations; retain prior corruption,
  storage-fault, 200 Hz startup and finite-overload recovery cases.
- `tests/test_storage_integrity.py`: generated-header defaults, exact decoder matching, critical
  records, first START timestamps, complete task IMU cadence, sequence/CRC/no-overflow checks,
  30/120 s duration comparison, and machine-readable size/record report.
- `tools/import_reference_components.py`: register the new Host fixture as FCCG-owned for reference
  re-import; runtime config remains the existing FCCG-owned source of truth.
- `docs/PREFLIGHT_LOGGING.md`, `docs/README.md`, this report: policy, operational instructions and evidence.

### Exact generated-project comparison

Reference project is actually generated below `tests/.pytest-sparse-0916e/storage-integrity0`.
The same selected-stream policy is used in both configurations. Size workload: 100 Hz IMU/native
attitude, 25 Hz native Baro, 12.5 Hz native GNSS, 50 Hz modeled navigation outputs, 1 Hz low-rate
status; no selected standalone magnetometer. 20 s FLIGHT then 1 s existing landing grace.
The navigation outputs and device source values are Host models; this byte-integrity workload
is not presented as a physically meaningful navigation golden trajectory.

| Mode / preflight | Whole file bytes | Whole records | Preflight bytes including header | Preflight records |
| --- | ---: | ---: | ---: | ---: |
| Normal / 30 s | 1,679,603 | 15,303 | 10,140 | 190 |
| Normal / 120 s | 1,696,523 | 15,573 | 27,060 | 460 |
| Diagnostic / 30 s | 2,623,263 | 25,745 | 923,244 | 10,294 |
| Diagnostic / 120 s | 5,385,183 | 56,390 | 3,685,164 | 40,939 |

120 s preflight bytes decrease by **99.27%**. Extra waiting only adds retained low-rate status:
normal IMU_NATIVE/IMU_CORRECTED/HW_QUAT_NATIVE remain 2,000 records each, BARO_NATIVE 500,
GNSS_NATIVE 250 for both durations. First record timestamp equals START for each; mission IMU
samples exactly match range(START, LANDING, 10000). All four runs have zero record-sequence gaps,
zero LoggerBus overflow, intact CRC/framing, one successful session and safe finalization.
No audit resynchronization or sequence renumbering is used.

The comparative fixture is explicitly 100 Hz. An exploratory 200 Hz combined diagnostic workload
with the delayed-card model exceeded the existing queue near START; this was not hidden or treated
as a pass, and queue capacity was not enlarged. Diagnostic logging remains bounded by real SD latency
and stream load. The independent existing 200 Hz startup fixture passed its normal zero-drop case;
its intentional overload remains observable and recovers with valid CRC/framing. Neither result
certifies all possible 200 Hz target/card workloads.

### Commands and acceptance

All temporary/generated/build output is below tests; test PYTHONDONTWRITEBYTECODE=1,
QT_QPA_PLATFORM=offscreen, TEMP/TMP point below tests. No reference firmware or other source tree
is modified by FCCG generation/testing.

```powershell
python -m pytest tests/test_storage_integrity.py -q -x --basetemp=tests/.pytest-sparse-0916e -o cache_dir=tests/.pytest_cache/sparse0916
& tests/.pytest-sparse-0916e/storage-integrity0/Tests/Host/run_tests.ps1
python -m pytest -q --basetemp=tests/.pytest-work-closeout0916 --ignore-glob='tests/.pytest-runtime*' --ignore-glob='tests/.pytest-sparse-*' --ignore-glob='tests/.pytest-env-*' -o cache_dir=tests/.pytest-cache/closeout0916
```

Focused storage: **11 passed in 69.97 s**.
Generated Host: **67 executables, 14,484 checks, 0 failures**, 8 positive compile cases,
16 expected compile rejections; all storage cases pass. Full pytest: **386 passed, 1 skipped in 816.00 s**.
The one skip is `tests/test_prompt_acceptance.py:287`: its read-only reference firmware
working tree is not clean (the test labels this "task is still active"). No reference files
were changed; this comparison is not claimed as a pass.
The complete suite includes logging streams, generation, decoder/SSLOG, algorithms and frozen
C trajectory/golden checks. Golden fixtures were not modified.

Release and Debug were also built from this generated project with Arm GNU Toolchain 14.3,
using the existing Make graph and strict first-party warnings:

```powershell
# Working directory: tests/.pytest-sparse-0916e/storage-integrity0
D:/msys64/ucrt64/bin/mingw32-make.exe -j4 SHELL=cmd.exe CONFIG=Release all stack-report memory-report artifact-check
D:/msys64/ucrt64/bin/mingw32-make.exe -j4 SHELL=cmd.exe CONFIG=Debug all stack-report memory-report artifact-check
```

Both commands exit 0. Each configuration supplies 138 .su files plus linked-ELF analysis;
all eight enabled tasks (including Idle) pass their stack budgets. Artifact checks verify
ELF/MAP/BIN/HEX, FLASH, main SRAM, CCMRAM and zero heap symbols.

| Configuration | FLASH bytes | Main SRAM bytes | CCMRAM bytes | Minimum task stack margin |
| --- | ---: | ---: | ---: | ---: |
| Release | 261,304 / 524,288 | 78,032 / 131,072 | 51,064 / 65,536 | 256 bytes (Idle) |
| Debug | 278,840 / 524,288 | 78,048 / 131,072 | 51,064 / 65,536 | 256 bytes (Idle) |

Release ELF SHA-256: `fe0588625ca6e293445cde623ae35eec2ac86c985729fbc797717bf71baa332e`.
Debug ELF SHA-256: `611bd41b843f3baa6752ded893664142ffba7fb562cee3e1898092d4ca7e2d74`.
Stack budgets are static bounds, not measured hardware high-water marks.

Evidence:
- `tests/.pytest-cache/target-release-closeout0916.log`, `target-debug-closeout0916.log`
- Generated `build/FCCG/SilverStar_F407/{Release,Debug}/stack-budget.json` and ELF/MAP/BIN/HEX
- `tests/.pytest-cache/sparse0916-final.log`
- `tests/.pytest-cache/host-closeout0916.log`
- `tests/.pytest-cache/full-closeout0916.log`
- `tests/.pytest-sparse-0916e/storage-integrity0/build/FCCG/Host/Tests/StorageIntegrity/`:
  `integrity.log`, four preflight-*.sslog files and `preflight-comparison.json`.

No board flash, physical SD, GNSS-origin convergence or flight acceptance is claimed. Real target
START scheduling, sensor rates and card latency remain hardware validation items. FLP's separate
exact synthetic import/replay acceptance is recorded in its own VALIDATION.md.
`git diff --check` passes; protocol/schema/version and protected algorithm files are outside the diff.

<!-- closeout-git-begin -->
### Final Git snapshot

Tracked diff (new files are listed separately by status):

```text
 VALIDATION.md                                      | 180 +++++++++++++++++++++
 docs/README.md                                     |   1 +
 .../payload/System/User/system_user_config.h       |  10 +-
 .../storage_integrity/run_storage_integrity.py     |  18 +++
 .../Host/storage_integrity/test_logger_storage.c   |  54 +++++--
 tests/test_storage_integrity.py                    |  61 ++++++-
 tools/import_reference_components.py               |   1 +
 7 files changed, 313 insertions(+), 12 deletions(-)
```

```text
 M VALIDATION.md
 M docs/README.md
 M plugins/builtin/silverstar_core_0_0_10/payload/System/User/system_user_config.h
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/storage_integrity/run_storage_integrity.py
 M plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/storage_integrity/test_logger_storage.c
 M tests/test_storage_integrity.py
 M tools/import_reference_components.py
?? docs/PREFLIGHT_LOGGING.md
?? plugins/builtin/silverstar_core_0_0_10/payload/Tests/Host/storage_integrity/test_sparse_preflight.h
```
<!-- closeout-git-end -->


## 2026-09-14 — Protocol GUI mapping and touch-scrolling closeout

Scope: GUI/helper, translation strings, GUI tests and documentation only. The initial working
tree was clean. No model/schema, generator semantics, builtin payload, firmware runtime, algorithm,
KF6/INS/GNSS, log format/semantics, protocol wire, version, commit or push was changed.

<!-- touch-git-snapshot -->
### Modified files and Git snapshot

- `VALIDATION.md`
- `docs/GUI_STYLE_GUIDE.md`
- `src/silverstar_fccg/i18n/en_US.json`
- `src/silverstar_fccg/i18n/zh_CN.json`
- `src/silverstar_fccg/ui/main_window.py`
- `src/silverstar_fccg/ui/pages/base.py`
- `src/silverstar_fccg/ui/pages/build.py`
- `src/silverstar_fccg/ui/pages/components.py`
- `src/silverstar_fccg/ui/touch_scroll.py`
- `src/silverstar_fccg/ui/widgets.py`
- `tests/test_protocol_gui_mapping.py`
- `tests/test_touch_scroll.py`

`git diff --stat` (tracked files only; new files are listed above):

```text
 VALIDATION.md                              | 104 +++++++++++++++++++++++++++++
 docs/GUI_STYLE_GUIDE.md                    |  16 +++++
 src/silverstar_fccg/i18n/en_US.json        |   1 +
 src/silverstar_fccg/i18n/zh_CN.json        |   1 +
 src/silverstar_fccg/ui/main_window.py      |   2 +
 src/silverstar_fccg/ui/pages/base.py       |   2 +
 src/silverstar_fccg/ui/pages/build.py      |   3 +
 src/silverstar_fccg/ui/pages/components.py |  27 +++++++-
 src/silverstar_fccg/ui/widgets.py          |   3 +
 9 files changed, 157 insertions(+), 2 deletions(-)
```

`git status --short`:

```text
 M VALIDATION.md
 M docs/GUI_STYLE_GUIDE.md
 M src/silverstar_fccg/i18n/en_US.json
 M src/silverstar_fccg/i18n/zh_CN.json
 M src/silverstar_fccg/ui/main_window.py
 M src/silverstar_fccg/ui/pages/base.py
 M src/silverstar_fccg/ui/pages/build.py
 M src/silverstar_fccg/ui/pages/components.py
 M src/silverstar_fccg/ui/widgets.py
?? src/silverstar_fccg/ui/touch_scroll.py
?? tests/test_protocol_gui_mapping.py
?? tests/test_touch_scroll.py
```
<!-- /touch-git-snapshot -->

### Cause and repair

Protocols_Set previously used Qt findData(selected_tuple) and max(0, index), conflating a failed
mapping with a genuine None selection. A missing plugin/profile therefore silently looked like
"not used". It now normalizes selection and tuple/list itemData to string pairs and compares
items explicitly. An unmapped existing selection gets a disabled, localized unavailable item,
tooltip and validation marker while retaining its identity. Signal connections are made only
after restoration; refresh leaves ProjectModel intact. Existing availability, transport and
logging-enable handling is unchanged.

The current PySide6 6.10.1 probe returned list itemData and successfully matched an equal fresh
tuple using findData. Thus the exact field-only QVariant failure was not reproduced here;
tests explicitly simulate a failed Qt lookup and exercise both tuple and list representations.
The proven defect is GUI failure-to-None fallback. No underlying model corruption was observed
or repaired; genuine model None and valid telemetry/maintenance/logging selections are all tested.

Touch coverage: all ScrollableLocalizedPage viewports (the normal configuration pages),
SmoothTableWidget/EngineeringTable including plugin and configuration tables, navigation list,
build summary/detail logs, and StandardComboBox popup views. The local helper only registers
QScrollArea, ordinary item views and text views; it excludes headers and leaves pixel-scroll modes,
mouse handlers, inputs, sliders and graphics alone. No cross-repository runtime dependency added.

### Executed checks

- `python -B -m pytest tests/test_gui_smoke.py tests/test_service_gui.py -q --basetemp=tests/.pytest-work-touch-focused -o cache_dir=tests/.pytest-cache-touch`: **14 passed**, 94.94 s.
- `python -B -m pytest tests/test_protocol_gui_mapping.py tests/test_touch_scroll.py -q --basetemp=tests/.pytest-work-touch-new2 -o cache_dir=tests/.pytest-cache-touch`: **25 passed**, 9.41 s.
- Full `python -B -m pytest -q --ignore-glob='tests/.pytest-runtime*' --basetemp=tests/.pytest-work-touch-full -o cache_dir=tests/.pytest-cache-touch`: **382 passed, 1 skipped**, 665.03 s; includes existing configuration/protocol/generation regression tests.
- Additional final Protocol tests (three model-None cases were added after full-run collection): `python -B -m pytest tests/test_protocol_gui_mapping.py -q --basetemp=tests/.pytest-work-touch-mapping-final -o cache_dir=tests/.pytest-cache-touch`: **10 passed**, 9.47 s.
- GUI compileall, `git diff --check`, static scroll inventory and protected-source diff audit: **passed**.

New tests exercise all three Protocol categories, tuple/list itemData, simulated QVariant miss,
missing-profile display, zero refresh signals, unchanged ProjectModel, model None, real-window
scroll coverage, excluded input/graphics/header targets, preserved mouse row selection/scrollbars,
and synthesized finger swipes that actually move page/list/table/text scrollbars.

Runs use offscreen Qt and repository-local test output directories. The full-run log and source
scope audit are `tests/.pytest-cache-touch/full.log` and `scope-audit.json` under the same directory.
The original full collection attempt encountered nine access-denied errors in existing
`tests/.pytest-runtime*` generated-cache directories; its log is `collection-error.log`.
Only these cache directories were excluded on retry; no source test was removed or disabled.

### Remaining validation limits

The existing reference-payload test skips when read-only reference firmware provenance reports
an unclean working tree. Its legacy message "task is still active" does not establish another
agent's status. No reference firmware was edited. No physical CF-33 touch/stylus, target hardware,
flash or new numerical algorithm acceptance is claimed. No failing executed GUI regression remains.


## 2026-09-12 — Algorithm actual parameters / decoder 1.2 closeout

Baseline commit: `b2e05fb`. This working-tree change keeps SilverStar Platform **0.0.10**;
Project format is **12**, parameter declaration schema is `silverstar.algorithm-parameters/1.0`,
and `.ssdecoder` package/project-semantics are **1.2**, rejecting package 1.1.
The selected Pure INS/KF6 manifests declare **22 actual parameters** (1 + 21).
See [parameter inventory and semantics](docs/ALGORITHM_PARAMETERS.md).

### Executed checks

- Full pytest: **356 passed, 1 skipped**, **692.14 s**. The skip at
  `tests/test_prompt_acceptance.py:287` is the pre-existing reference-payload synchronization
  check: the read-only reference firmware working tree is not clean. Its legacy message says
  “task is still active”; this is not an inspection of other Codex tasks.
- Focused parameter/schema/project/UI/decoder/documentation regressions: **58 passed**.
  An additional **8 passed** cover strict decoder schema-lock validation and invalid values.
- Release and Debug: `all artifact-check stack-report` passed using Arm GNU Toolchain
  **14.3.Rel1**, compiler **14.3.1 20250623**. Both have **138 .su files** and all **8 static tasks**
  meet the linked-ELF stack budget. Heap symbols: **0**.
- Architecture: **270 checks, 0 failures**. The new parameter header is explicitly registered
  in the reviewed thin-glue set; Make/EIDE source-graph consistency remains enforced.
- Power of Ten: **5,930 checks, 94 first-party C files, 2,223 functions**, passed.
- Host: **67 executables, 14,484 checks, 0 failures, 8 compile-pass cases and 16 expected
  compile failures**. Golden logs use the actual C codec; storage byte audit and delayed-DMA
  fixtures also passed against the schema-1.2 package. Negative missing-noise cases explicitly
  remove generated actual noise before testing absence; capability assertions are retained.
- Release static analysis passed with the original analyzer flags and policy intact.
- Reference importer ownership audit passed for both parameter declarations/algorithm sources,
  system/task bindings, Host fixtures and decoder/architecture tools. Reference files were read only.
- New page rendered and inspected in Simplified Chinese/English and Light/Dark; it precedes
  Hardware Connection. Parameter edits preserve advanced-section disclosure; old widgets are
  hidden before deferred deletion. Save/reopen/Save As and Dirty behavior are covered.

### Default numerical equivalence

The old project sources and full Host Golden were frozen under `tests/artifacts/parameters24/baseline`
before firmware bindings changed. The same C trajectory fixture runs against those frozen old sources
and the new generated default project with GCC **16.1.0 x86_64-w64-mingw32**, C11, `-O2`.
It covers **2,000 IMU steps / 1,000 updates**, quaternion, Pure INS position/velocity, KF6 state
and complete covariance, with GNSS/barometer updates. **52,045 float outputs**, **5,005 lines**,
**1,109,911 normalized bytes** are **bit-identical**; there is no rounding-tolerance exception.
Changing saved gravity/P0/process sigma/GNSS sigma/barometer sigma changes the compiled trajectory.

Trajectory SHA-256: `ad64bc875b4ec87f0bafdd65e868bb99822b79dfe79fc0debf13ec9484486aa1`.

Only configuration references and the KF6 initialization/reset constants changed. Mathematical
equations, structure dimensions, operation/update order, fusion timing and GNSS reacquisition policy
were preserved. Pure INS mechanization source is unchanged. Logger, Calibration, Alignment,
Board/MCU/hardware binding, AIR and SSLOG record-layout sources were not changed. FLP/GSHC were not modified.

### Target resources and stack budgets

| Configuration | FLASH used / available | Main SRAM used / available | CCM used / available |
|---|---:|---:|---:|
| Release | 261,232 / 524,288 B | 78,032 / 131,072 B | 51,064 / 65,536 B |
| Debug | 278,816 / 524,288 B | 78,048 / 131,072 B | 51,064 / 65,536 B |

| Task | Configured bytes | Release worst known / margin | Debug worst known / margin |
|---|---:|---:|---:|
| Device | 2048 | 1496 / 552 | 1320 / 728 |
| INS | 3072 | 2040 / 1032 | 1808 / 1264 |
| Estimator | 4096 | 1964 / 2132 | 1868 / 2228 |
| Flight | 4096 | 3428 / 668 | 2292 / 1804 |
| Logger | 3072 | 1376 / 1696 | 1368 / 1704 |
| Serial | 6144 | 4200 / 1944 | 2928 / 3216 |
| Telemetry | 4096 | 1980 / 2116 | 1660 / 2436 |
| Idle | 512 | 256 / 256 | 256 / 256 |

Release ELF SHA-256: `9fceecd3b5db4b42a1046205355bca5aebf3e3245a9040dab2f0f98b3337d703`.

Debug ELF SHA-256: `5d62999c65ee93fddb778e2cb832b34d7b58fa71a0577e8ca5fe5dc3257f30be`.

Record Catalog SHA-256 (equal to pre-change baseline): `a3fb7bd69a6f9d13a99e0654a9a74c14f057d4c0625af68da913884a427f5795`.

Project semantics SHA-256: `cccae38b7e2e365a1918a7f6ef5829984130ab5bdedba571e056bff8bbf473e6`.

Generation profile SHA-256: `2edc759219fc2b23bd20512895d40c001559ffb18253426ea86980cc11140de4`.

### Scope and reproduction

Acceptance outputs/logs/screenshots remain under `tests/artifacts/parameters24/`; temporary helpers
are under its ignored `helpers/` directory. The reproducible numerical regression is
`python -B -m pytest tests/test_algorithm_parameters.py`; run `python -B -m pytest -q` for the suite.
Generate a fresh reference project, then run Release/Debug `all artifact-check stack-report`,
`architecture-check power10-check host-tests` and Release `static-analysis` from its directory.
Development outputs and compiler temporary files must stay below repository `tests/`.

Normal Apply preserves project-owned C. Older generated projects must deliberately port the
documented bindings or use a fresh output before relying on actual parameter configuration.
No target flashing, hardware timing/flight acceptance or live FLP compatibility run is claimed.
All edits remain uncommitted for review. No shutdown was requested or executed in this round.

---

## Historical snapshot — 2026-09-12 Logger startup burst closeout (prompt 22)

以下保留上一轮验收时的版本与结果；本轮算法参数 / decoder 1.2 验收见文首。

本轮基线为 `90c14dc`，开始时工作区干净。只修改FCCG；外部reference、FLP/GSHC均未写入。
SilverStar 0.0.10、AIR M0、Maintenance/SSLOG 0.0、`.ssdecoder`/Project Semantics 1.1不变。
SDIO、FatFs、Storage/LogSink实现、SSLOG IDs/layout/CRC与独立审计判定均未改动。
当前结论仍是软件验证，不能替代SS0.5实卡验收。

## 根因与证据边界

旧Logger在session成功打开后仍无条件delay 10 ms；普通周期流在header、decoder和集中自检报告
落盘前已可入队。报告尚未完成时，旧代码还会关闭已成功打开的session并等待重开。这些窗口
使单个低优先级consumer暂时无法跟上启动producer。修复不通过增加队列或调整飞控任务优先级完成。

`tests/artifacts/startup22/baseline`保存修改前生成的生产源码及Release/Debug产物。将本轮相同
多流Host输入/延迟模型接到旧生产Logger/Bus，移除fixture中旧API不存在的新诊断断言，仅将旧版本
验收期待改成“有真实drop”，复现 **629次overflow、3段gap/629 IDs**，CRC/length/framing仍正确。
这次比较保留旧writer，未给旧代码添加bootstrap。原始日志为`baseline-startup-repro.log`。

用户提供的新实机日志摘要为CRC/length/sync/unknown均0、START后连续、启动3段gap/12 IDs、
logger overflow39、IMU overflow0；本轮没有该BIN与匹配decoder的本地输入，因此**没有复测这组39/12**，
也不声称629就是该实机的丢失量。日志可能受首条记录前drop、末条STATS和采集窗口影响；
仅凭摘要无法逐条归因。上一轮字节修复与本轮启动队列修复必须分开判断。

## 实现与持久所有权

- `APP/Src/logger_bus.c` / `APP/Inc/logger_bus.h`：唯一BOOTSTRAP/STREAMING_READY准入状态；
  普通周期流未准入计数与实际accepted、overflow、state/capacity拒绝分开。关键事件/descriptor/
  Calibration/Alignment/Mission/Initial State保持可入队，producer无等待。
- `APP/Src/logger_task.c` / `APP/Inc/logger_task.h`：成功open立即drain；保留pending自检的session；
  decoder排空后补启动System/Device/Algorithm/Stream配置，写完整自检并sync后，在临界区确认两队列
  为空才开放streaming。已排队BOOT/关键记录仍保持原FIFO顺序，满队列仍可消费并重试decoder。
  START原有配置/Initial State记录保留。Mission config纳入关键flush批次。
- 增加iteration/drain、open尝试/失败/session、append/flush/serialize/close失败、discarded_bytes、
  write count/total/max、ready时间内部诊断。Storage原有health与延迟诊断保留。64-bit延迟更新受保护。
  capacity拒绝也包含尚未提交的SystemConfig批次预检；真正drop仍只来自queue overflow，并沿用原序号
  增量算法。没有成功写入后重排sequence、重放不确定aggregate或将错误收尾伪装成finalized。
- 修改的C/H、Host fixture、runner及两份包内Storage文档已在既有`fccg_owned_files`/owned-doc映射中；
  本轮扩展`test_storage_sources_survive_reference_reimport`验证其逐字节回导保留。
  这些builtin路径本来就是FCCG-owned真源，不是只修一个生成工程。没有运行外部reference写操作。

## 真实C writer与Host模型结果

最终运行文件位于`tests/artifacts/startup22/final`；日志见`final-host.log`和`final-storage.log`。
实际LoggerBus → LoggerTask → LogSink → Storage → FatFs → diskio → 延迟DMA模型 → 文件读回 →
真实C codec与严格metadata审计；未用Python重写writer布局。后补的恢复断言要求step 1500后drop不再增长。

| 模型 | 写出records | overflow / gap IDs | gap段数 | normal/estimator HWM |
|---|---:|---:|---:|---:|
| 旧生产代码，同一200 Hz多流启动输入 | 291037 | 629 / 629 | 3 | 64 / 8 |
| 正常200 Hz多流启动与START | 291359 | 0 / 0 | 0 | 62 / 8 |
| 相同多流输入，START后有限过载 | 291367 | 517 / 517 | 2 | 64 / 26 |
| 原有100→500 records/s慢卡模型 | 40079 | 0 / 0 | 0 | 55 / 2 |
| 慢卡+有限过载 | 40121 | 558 / 558 | 保留真实缺口 | 64 / 32 |
| 满critical启动队列+有限过载 | 40188 | 692 / 692 | 保留真实缺口 | 64 / 32 |

所有模型存活记录的header/record CRC、length、framing、unknown和尾部未校验字节均0错误；
sequence reorder=0，匹配生成的decoder。每个文件仅一个decoder descriptor。没有resync取得通过。
正常/过载默认多流均保留1个Calibration、Alignment、Mission config和Initial State，2组SystemConfig
（bootstrap与START）；故意过载的drop与最终STATS严格对应，并恢复至结束不再增加。

默认多流模型：200 Hz IMU/BARO/HW quaternion、25 Hz GNSS、50 Hz Power；START前保留默认流策略，
START后加入IMU corrected、100 Hz INS相关记录、生成配置中的Estimator/KF抽取、GNSS/Baro量测和
STATS/Health/Telemetry诊断。自检报告延迟完成、session open注入300 ms停顿，运行40000个5 ms步，
约200秒。Device/Flight模拟工作计数各40000，普通生产路径无等待；IMU overflow fixture值为0。
这不是完整FreeRTOS调度器，也未执行真实传感器/Calibration/Alignment求解；真实FlightTask的NONE结果
映射由既有lifecycle Host测试另验，实际IMU总线overflow与任务执行时序仍须上板确认。

默认模型bootstrap suppression=351，绝不计作drop/sequence。session/open尝试=1/1，首个task delay=2 ticks，
没有成功open后的10 ms暂停。normal/overload的append/flush/serialize/close/storage错误及aggregate discard均0。
Storage最大write/sync=30000/8000 us；sink write平均正常14895 us、过载14893 us；最大Logger迭代316120 us
含300 ms开文件注入，不能独立当作CPU饥饿时间。模型ready绝对时刻1110520 us，包含测试准备时钟。
原有慢卡模型最大write/sync=90000/26000 us、最大迭代126260 us；bootstrap suppression=22。

## Queue与RAM/FLASH

队列深度 **64/32 → 64/32**，`sizeof(FlightLogRecord)=224` bytes；分别14336/7168 bytes，合计21504 bytes，
队列RAM增量0。aggregate仍4096 bytes、DMA bounce仍512 bytes。正常多流峰值62/8，对应空余2/24槽；
这仅覆盖本次延迟/负载模型，普通队列余量较小，实卡需测最大延迟与HWM，不能宣称任意卡均零丢弃。

| 构建 | FLASH基线→本轮（Δ） | main SRAM基线→本轮（Δ） | CCMRAM |
|---|---:|---:|---:|
| Release | 262112→261232（-880） | 77944→78032（+88） | 51064不变 |
| Debug | 278040→278808（+768） | 77960→78048（+88） | 51064不变 |

Release剩余FLASH263056、main SRAM53040、CCMRAM14472 bytes；Debug分别245480、53024、14472。
无heap符号。编译器Arm GNU 14.3.Rel1；Release/Debug全部8个静态task含Idle的`.su`+ELF预算通过。
Logger配置3072 bytes，最坏已知栈Release1376 / Debug1368，余量1696 / 1704；所有task均满足256-byte
最小静态余量。它们不是运行时HWM/MSP嵌套的实测值，assert/stack overflow/HardFault保护保持开启。

Release ELF SHA-256：`6baa96224d0fc008981e6c1723edc31a7ad3bc7db4f780a8d65a3feb858e1e7e`。
Debug ELF SHA-256：`2663072c207e6bbea45b3fa7eab2c60daf0f0fdd03b72d707d5ae2c8dd0661e3`。

## 执行门禁与交付状态

- fresh默认SS0.5 Generate：通过；产物位于本仓库tests下，不触碰外部参考工程。
- compileall `src main.py tools`：通过，cache重定向至tests内。
- 专项pytest（Storage/文档）：16 passed，57.17 s。
- 全量pytest：**334 passed、1 skipped，761.06 s**，退出码0；一次被中断的运行不计通过。
  跳过项为`tests/test_prompt_acceptance.py:287`的只读参考工程验收，触发条件是外部参考工作树不干净；
  该测试的“task is still active”提示不等于Codex任务状态查询，
  关机条件必须另用任务工具核对。其余门禁不依赖修改该外部参考工程。
- Release / Debug + Artifact + stack-report：均通过。
- Host：67 executables、14484 checks、0 failures；8 compile-pass、16 expected compile-failure。
  随后增加纯Host恢复断言并再次执行完整Storage runner：通过。
- Architecture：270 checks、0 failures。Power of Ten：5930 checks、94 first-party C、2223 functions，通过。
- Release `-fanalyzer`：完整独立目录编译/链接通过，未发现warning；退出码0。
- 源码确定性导出：两份ZIP逐字节一致，849个源文件；已检查build/acceptance/cache与编译产物排除，
  Host/Target真实源码及corruption fixture保留。最终文档收尾后重新导出，hash留在tests内export-result.json，
  避免把自身archive hash写回归档内容造成循环。
- `git diff --check`：通过。20个跟踪文件修改，均在FCCG内，修改保持未提交；未commit/push/tag/release。

仍需实机：SS0.5单IMU/GNSS/telemetry，NONE及所选procedure，反复preflight/alignment/START/正常收尾；
至少两次或两张卡，保留BIN、匹配decoder、独立审计、START前后及停止时诊断、任务HWM和最大存储延迟。
正常目标必须为logger/IMU overflow、gap、CRC/length/resync全0；故意过载仅允许真实drop且须恢复。
无真实硬件结果时不关闭该验收项；没有声称EIDE builder、烧录、飞行或其他MCU已通过。

# Validation — 2026-09-06 SSLOG storage integrity repair

本轮依据20号prompt实现并验证FCCG内部修复，基准HEAD：`346756111e6f6a9050dcfc7bb206117fae93b9e5`。
所有开发/测试写入均在FCCG内；生成、编译、日志、临时文件与源码包在`tests/artifacts/storage20/`
及仓库已有的tests临时目录。没有修改外部参考固件、FLP、GSHC，没有commit/push/Tag/Release。

## 根因与证据边界

- 可复现的底层缺陷：原SS0.5 `sd_diskio.c`禁用scratch，直接把任意FatFs byte pointer交给
  word-aligned SDIO DMA。FatFs跨partial/full sector后，即使应用buffer原先对齐，传递指针也可能偏移。
  原禁用的scratch-write分支还等待READ completion；原超时/错误completion和CTRL_SYNC的结果处理不可靠。
- 使用真实FatFs、原diskio与延迟到completion才消费buffer的word-DMA Host模型，完成10000次指定长度写入。
  以32-byte aligned buffer、512-byte读取隔离读侧影响，旧实现仍在offset **172032**（sector 336起点）
  字节不一致；完成写入时已提交5次未对齐DMA。该基线是期望失败，保留`baseline-integrity.log`。
- 独立的上层缺陷：partial write失败后Close再次尝试整个aggregate，可能重复已经写入的前缀。
  现已禁止错误关闭重放、禁止writer在不确定write/sync后重开疑似损坏文件，并区别fault与finalized。
- Queue增长与byte corruption分开处理：原关键记录逐条sync会放大等待，现合并排队中的critical批次，
  以queue空或首条20ms deadline触发；已有storage操作可延迟实际完成。普通/Estimator容量仍是64/32，
  aggregation仍是4096 bytes，任务优先级不变。增加HWM、accepted/dequeued、最大write/sync/迭代间隔诊断，
  writer按新观察到的累计overflow推进sequence，保留明确gap。
- 额外复现启动满队列停滞：SD打开后Required decoder descriptor入队失败会关闭session，唯一consumer
  因而始终无法排空queue。使用已修复diskio但保留旧Logger启动逻辑的独立基线，模型超过300秒完成期限
  并按预期失败（`baseline-startup-queue.log`）。现保持session打开，在dequeue后补入descriptor。
- **没有拿到SS0014.BIN及精确匹配decoder，也没有真实SDIO/TF卡上板。** Prompt中1152 CRC candidates、
  50 oversize、1222 gaps、overflow 110和START后3.318ms均为用户提供的历史事实，不能称为本轮重新测得。
  Host模型证明确定的软件契约缺陷，不单独证明SS0014所有损坏和溢出的硬件成因。

## 修复与所有权

`tools/reference_overlays/storage/`持有Board diskio/BSP覆盖；固定512-byte main-SRAM bounce每次传1 sector，
匹配completion且card-ready后才复用，等待有30秒整体边界。错误/超时锁存不可用直到reset，迟到IRQ不能解锁。
FatFs仍拥有partial sector与RMW，CPU源buffer不要求4/32-byte alignment，F407没有DCache处理。
Logger/Storage/LogSink C/H、Host/Target fixtures、离线audit均在importer的FCCG-owned/overlay映射中。
正常Apply仍保留project-owned源文件；老项目须新生成或明确移植这些修复。自定义CubeMX glue须独立移植和验证。

SSLOG payload/Record ID/version/framing/CRC、AIR M0、Maintenance 0.0、decoder 1.1、平台0.0.10均未变化。
MISSION_CONFIG仍是91-byte payload / 119-byte record，没有补齐。
共同Calibration契约与HEAD逐字节一致，SHA-256：`ffb8013cb9e1f254872255f8e4dc86abd374af5199ece39963fc90a0301f1f40`。

## 实际执行的质量门

| 项目 | 本轮结果 |
| --- | --- |
| 默认verified SS0.5 Generate | passed；最终输出`tests/artifacts/storage20/final`，只生成时不编译 |
| Release / Debug all + Artifact + stack-report | passed；两个配置均无heap symbols，所有静态task及Idle预算通过 |
| Host Tests | 67 executables、12423 checks、0 failures；8 compile-pass、16 expected compile rejection |
| Architecture | passed，270 checks；首次注释中的provider单词触发既有扫描，修正注释后通过 |
| Power of Ten | passed，5915 checks、94 first-party C files、2216 functions；拆分Logger诊断/周期flush保持函数行数限制 |
| `CONFIG=Release static-analysis` | passed，第一方严格warnings + `-fanalyzer`；最终Logger改动后增量重跑通过 |
| 额外ARM `-fanalyzer -Werror` | diskio、BSP callback glue、Target bench分别编译通过，补足vendor分类默认不加fanalyzer的边界 |
| 初次完整 `python -m pytest -q` | **333 passed, 1 skipped**，708.83 s |
| 启动queue修复后完整回归 | **333 passed, 1 skipped**，657.08 s，`pytest-full-final.log` |
| 启动queue修复定向回归 | **9 passed**，35.64 s |
| storage/docs/runtime定向 | **30 passed**，78.79 s；覆盖fixture/forensic audit及持久化修改 |
| `python -m compileall -q src main.py tools` | passed；缓存限定`tests/artifacts/storage20/pycache` |
| deterministic source export | 两次独立ZIP逐字节相同；保留真实unit/Host/Target/fixture源，排除build/tests临时与二进制产物 |
| `git diff --check` | passed |

唯一skip仍是`tests/test_prompt_acceptance.py:287`的只读外部reference工作树非clean，
提示`read-only reference firmware task is still active`。这是既有测试对外部工作树的保护，
不是对另一Codex任务是否完成的最终状态判断。没有为通过测试而改写外部reference。
首次完整pytest运行中调整了Logger函数组织及后续测试检查；启动queue修复后再次执行完整回归，
最终Host包含全部三个队列负载场景。

## Storage/Logger字节与队列结果

- 实际FatFs任意长度序列：1,2,3,4,7,31,60,88,91,119,127,255,256,257,511,512,513；
  源offset轮换1..31，跨512/4096，10000次小写与间歇sync，共**1668166 bytes**逐字节读回一致。
  无未对齐DMA提交。额外40000条真实C mixed records共**3850972 bytes**，header/记录逐字节重建、C CRC、
  sequence及EOF全部通过，不依赖resync。
- 读/写timeout、错误completion类型、提交失败以及CTRL_SYNC busy timeout共7种故障，每种单独进程，
  验证错误返回、initialize不能解锁、迟到callback不能复用scratch或发起新DMA。
- Target bench同样在Host实际FatFs模型中运行，返回Ok；此外完成ARM编译与fanalyzer。
  Target bench不在production SourceGraph，**尚未在真实硬件执行**。
- 真实LoggerBus→LoggerTask→LogSink→Storage→FatFs→diskio链路模拟START前约100 records/s、之后约500 records/s。
  正常模式accepted=40002、wire records=40004（含直接startup events），drop/gap=0；
  normal/estimator HWM=56/2，CRC全部正确、decoder三hash匹配、EOF无余字节。
- 故意向两个queue额外突发600条：accepted=40071，wire records=40073，**drop=531，gap records=531**，
  HWM=64/32；保留记录CRC全部正确、无sequence reorder，STATS计数精确对应gap。
  模型最大write=90000us、sync=26000us、Logger迭代=116060us，**这些是Host模型时间，不是实卡延迟**。
- lifecycle Host额外验证partial write只调用一次失败写，不在Close重放或重开；final sync失败不伪报finalized。
- 启动满队列加飞行中突发：accepted=40132、wire records=40134、drop/gap=671，
  Required decoder descriptor只出现一次且三hash精确匹配；全部记录CRC与EOF仍通过。
- synthetic fixtures覆盖512边界重复/缺1 byte、payload CRC翻转、oversized length、未解释sequence gap、extra tail，
  全部被严格审计拒绝；可选candidate scan只报告forensics，不改变pass/fail，也不修复输入文件。

## Release/Debug内存差值（bytes）

基线与修复使用相同默认Board/工程名/配置及Arm GNU 14.3.Rel1。

| 区域 | 基线 | 修复 | 差值 |
| --- | ---: | ---: | ---: |
| Release FLASH | 260864 | 262112 | +1248 |
| Release main SRAM | 77360 | 77944 | +584 |
| Release CCMRAM | 51064 | 51064 | +0 |
| Debug FLASH | 277192 | 278040 | +848 |
| Debug main SRAM | 77384 | 77960 | +576 |
| Debug CCMRAM | 51064 | 51064 | +0 |

main SRAM容量131072，CCMRAM容量65536，FLASH容量524288；均通过实际ELF/产物检查。
增加固定512-byte scratch、内部诊断和状态；queue/aggregate/task allocations不变。

| Task | 配置bytes | Release估计 / 余量 | Debug估计 / 余量 |
| --- | ---: | ---: | ---: |
| Device | 2048 | 1496 / 552 | 1320 / 728 |
| INS | 3072 | 2040 / 1032 | 1808 / 1264 |
| Estimator | 4096 | 1964 / 2132 | 1868 / 2228 |
| Flight | 4096 | 3428 / 668 | 2292 / 1804 |
| Logger | 3072 | 1376 / 1696 | 1344 / 1728 |
| Serial | 6144 | 4200 / 1944 | 2928 / 3216 |
| Telemetry | 4096 | 1980 / 2116 | 1660 / 2436 |
| Idle | 512 | 256 / 256 | 256 / 256 |

这是`.su`+linked ELF保守预算；不是实测HWM/MSP/IRQ nesting。最小要求256-byte余量继续满足。

## 仍需真实硬件与历史样本

按`docs/platform/details/STORAGE_AND_FLIGHT_LOG.md`执行verified SS0.5+已知良好卡：
preflight→NONE calibration→alignment→START→室内2–5分钟→正常停止，至少两次运行或两张卡，
保存前后诊断、HWM、BIN、精确decoder与独立audit JSON。对SS0014使用严格audit，必要时另加
`--scan-candidates`复核历史candidate统计。FLP能打开或GSHC正常不能替代TF文件CRC/字节验收。
本轮未flash、未执行EIDE、未上板/飞行；未声称其他MCU/自定义CubeMX的存储硬件支持。

下方保留历史验收快照，不将其测试数/硬件范围当作本轮新结果。

---

# Validation — 2026-09-05 final documentation alignment

本节是按19号prompt校对FCCG文档的实际验收快照。工作基准HEAD为
`5997babf0025a377f7bb9184da73a6da9e3f05c8`（修改栈大小，初始化灯等问题）。
采用用户替换后的docs作为基线，没有从Git恢复旧docs；没有commit、push、Tag或Release。

## 范围与结果

- FCCG应用规范入口：[docs/README.md](docs/README.md)；完整平台规范入口：
  [docs/platform/README.md](docs/platform/README.md)。平台当前为0.0.10，AIR M0、
  Maintenance/SSLOG 0.0、decoder package/project-semantics 1.1保持独立版本。
- 修正文档正文中的固定NOT_SELECTED/0x07、Reset后灯状态、仅instance 0、未来FCCG、
  Board通用storage/power/action归属、手工EIDE、默认Debug和旧构建路径等过期描述。
- 新增平台RUNTIME_SAFETY规范，根README/AGENTS/TARGETS链接统一入口；
  DOCUMENT_LIST包含详细规范与两组PDF/TEX。
- 代码仅修改`tools/import_reference_components.py`的包文档标注流程：通过WorkspacePolicy
  限定builtin根、拒绝文档越界、幂等标注package-local implementation note，指向当前平台规范。
  组件包文档不是第二套平台authority；Core包VALIDATION仅索引本根文件。
- 新增`tests/test_documentation.py`，检查内部相对链接、当前版本/Calibration旧说法、
  共同契约与索引、公式配对、包文档归属及重复标注不改时间戳。
- 没有修改固件C/H、AIR字段/命令/CRC、SSLOG Record或decoder schema。
  既有Calibration实现已经符合NONE常驻、四种mask、build门禁与真实事务语义，未做重构。

## 本轮实际执行

| 检查 | 实际结果 |
| --- | --- |
| `pytest tests/test_documentation.py tests/test_runtime_safety.py tests/test_stack_budget.py -q` | 26 passed，57.47 s |
| `pytest -q` | 324 passed，1 skipped，667.22 s |
| 最后文档/快照整理后，`pytest tests/test_documentation.py tests/test_runtime_safety.py::test_runtime_sources_survive_reference_import -q` | 7 passed，6.56 s |
| `compileall`：由`rg --files src tools tests -g '*.py'`列出受维护Python文件后逐文件编译 | passed，缓存仅在`tests/.pycache-docs19/` |
| `git diff --check` | passed |
| 文档链接、清单、公式检查 | passed；当前docs共52份Markdown，两组PDF/TEX；无网络依赖 |
| 共同Calibration契约 | 与GSHC同名文件逐字节一致 |
| 三份用户提供的历史文档 | SHA-256与本轮开始保存的基线一致，未改写历史版本 |

唯一skip为`test_reference_payload_sync_and_environment_templates_are_read_only`：
外部只读参考固件的working tree非clean，测试按现有规则报告
`read-only reference firmware task is still active`。本轮未修改、清理或重新导入该外部工作区。

完整pytest包含现有PySide6 offscreen GUI、生成/decoder、构建配置与安全回归。
定向runtime测试实际以Host GCC运行四种Calibration procedure mask及真实Telemetry命令路径，
并覆盖生产Indicator初始化与栈分析工具。没有单独重新运行生成固件的完整Host/SSLOG Golden、
ARM Release/Debug、EIDE构建、static-analysis/artifact或真实ELF stack-report门；
本轮没有运行时C变更，不能把下方历史结果当成本轮新执行结果。

日志保存在忽略的`tests/artifacts/docs19/pytest-full.log`及`pytest-final-docs.log`。
初次对整个tests树进行compileall遍历时遇到旧临时目录无法枚举提示，随后限定到
`rg --files`列出的受维护源码重新执行并通过；不将历史测试产物作为源码验收对象。

## 契约与保留证据

共同契约SHA-256：`ffb8013cb9e1f254872255f8e4dc86abd374af5199ece39963fc90a0301f1f40`。

| AIR calibration mask | 本次构建与运行行为 |
| --- | --- |
| 0x01 | 无采样procedure；boot/成功RESET自动NONE/Identity/READY，无需GSHC发送NONE |
| 0x03 | 默认NONE + OneFace；boot等待显式事务 |
| 0x05 | 默认NONE + SixFace；boot等待显式事务 |
| 0x07 | 默认NONE + OneFace + SixFace；boot等待显式事务 |

有采样procedure时，默认NONE通过真实CAL_START(NONE)选择/锁定active IMU、失效旧Alignment
并发布READY。非法mode为BAD_PARAM，合法但未编入为REJECTED，状态不允许为BAD_STATE，
互斥占用为BUSY，接受为OK；具体契约正文只由[共同文档](docs/AIR_CALIBRATION_CONTRACT.md)维护。

历史文件SHA-256：

- 0.0.7：`684a28da6d39b36f3aa5b660eca5cdb9e8b1ec91856b8d62545e1f3af57c4f02`
- 0.0.8：`96a45150466b79d9fd77d2df5045c736c7ea69b284f697145469c85164ec03d5`
- 0.0.9：`cf9d2a4df6e79a3ed9e644de2f594baef49e52fe6ea484e04c7eec968ae678a8`

## 仍待实机与Git状态

SS0.5冷启动/指示灯极性、反复AIR/Serial校准与对准/Reset、全部任务HWM、MSP与中断嵌套、
真实多设备失效切换、SD长写/掉电恢复、I2C/PWM电气路径和实际飞行验证仍待实测。
没有修改外部固件、GSHC或FLP，没有烧录或硬件结果声明。

变更保留在FCCG工作区：用户提供的新docs树、根文档、builtin文档备注、导入器及文档测试。
测试缓存/日志/编译产物均被忽略，未进入待提交文件。

---

以下保留此前runtime修复验收快照，执行范围和基准属于各自当时记录。

# Validation — 2026-09-05 runtime indicator, stack and calibration repair

本节记录本轮实际验证。仍为 **0.0.10 Software Release Candidate / Pre-Hardware-Validation**，
适用范围为 STM32F407VET6 / SS0.5 默认组成。没有烧录、HIL 或飞行验证。

## 工作区与持久归属

- Branch：`main`；基准 HEAD：`ad7ee8acb4677a45bfbcf2d27d555b02a1623a9a`，主题“修改硬件连接问题”。
- 修改仍在工作区，没有 commit、push、Tag 或 Release。
- 所有修改和验证输出均在 FCCG 仓库；测试、编译器临时文件和生成工程位于 `tests/`。
  外部参考固件、GSHC、FLP 未修改。参考固件导入审计为 clean，commit 为
  `cc0b377ded690556d037a412a55f87fe334c42d0`。
- Core 的运行时 C/H、Host fixtures、任务配置和架构检查器，以及 OS overflow hook，
  已在 `tools/import_reference_components.py` 登记 FCCG-owned source-of-truth。
  `check_task_stacks.py` 和运行时文档由 `tools/reference_overlays/` 持有。
- 最终连续两次只读参考导入：**629 个文件，第二次 0 个哈希变化**。
  同时修复导入文档重放：已修正的 Storage ownership 不再被当作未知内容，附加章节不重复，
  Board 固定映射、多实例说明和当前版本文档不被旧参考说明覆盖。

## 修复与命令语义

主要实现入口：

- `plugins/builtin/silverstar_core_0_0_10/payload/APP/Src/app_tasks.c`：production init、正常 HWM 缓存、稳定故障任务映射。
- 同一 Core payload 的 `APP/Inc/app_task_config.h` 与 `APP/Src/estimator_task.c`：静态栈配置和非等待式 origin reset。
- 同一 Core payload 的 `System/Calibration/{Inc,Src}/system_calibration*`：build mask、中心门禁和 NONE 初始化/重置。
- 同一 Core payload 的 `System/Alignment/Src/system_alignment.c`：立即校验和延后完整 Process。
- 同一 Core payload 的 `Common/{Inc,Src}/silverstar_assert.*` 与 OS payload 的
  `OS/FreeRTOS/freertos_hooks.c`：静态 fault record 与 overflow hook。
- `src/silverstar_fccg/generator/render.py`、`tools/reference_overlays/check_task_stacks.py`、
  `tools/import_reference_components.py`：Make 栈报告、调用链预算和持久导入归属。

`AppTasks_Init()` 原先遗漏 `SystemIndicator_Init()`，因此周期 Process 在写 GPIO 前就返回。
现在生产路径先初始化 Calibration、Alignment、Indicator，再创建任务。启动集成测试调用
真实 App Init、真实 Indicator 和 GPIO service，没有测试侧补 Init；验证 GPIO6 的低电平
点亮与周期翻转。SS0.5 的 `IMU_CAL_LED` / PA1、Board fixed mapping 和 polarity 未改变。

空选校准原先在 Alignment Init 之前调用 CAL_START(NONE)，还依赖开机阶段未必已经存在的
新鲜 IMU 样本。现在 Calibration Init 直接建立 NONE、零 bias、单位 scale、READY；RESET
也恢复该状态并推进生效快照 sequence。启用 Logging 时 Required `CALIBRATION_RESULT`
继续描述实际生效校正，不代表执行过物理采样。

| 校准选择 | build procedure mask | AIR calibration_mode_mask |
| --- | ---: | ---: |
| 空选 | 0x00 | 0x01 |
| OneFace | 0x02 | 0x03 |
| SixFace | 0x04 | 0x05 |
| OneFace + SixFace | 0x06 | 0x07 |

共享 header 在编译时拒绝 procedure mask 的未知位；bit0 只由 capability getter 添加。
`SystemCalibration_Start()` 在锁定来源或使校准/对准失效之前执行 build gate。不支持的
procedure 返回现有 UNSUPPORTED；非法参数、生命周期状态和 BUSY 仍使用现有结果。
AIR/Serial 共同受这一中心入口约束，ACK result mapping、token 和 framing 未改变。

`SystemAlignment_Start()` 保留立即状态、calibration-ready、build/source capability、
source lock、action 和 backend-reset 检查；不再调用完整 `SystemAlignment_Process()`。
后续由现有 FlightTask 周期路径推进。真实 Telemetry task/service/codec 和 Alignment runtime
集成测试验证 ACK OK 后没有 backend status/guard 重处理；再调用生产周期 operation 验证其推进，
并由最终 ELF 证明该 operation 属于 FlightTask 路径。这里没有把 Host stub 当作完整 RTOS 调度验证。

CAL_START/CAL_FACE/CAL_RESET 与 Serial 共用路径已审计：通信端保留有界验证/重置，采样仍在
IMU 路径，求解仍在 FlightTask。`EstimatorTask_OriginsReset()` 将“冻结后等待另一个任务”
改为临界区内检查 collection busy，忙时立即返回 BUSY，空闲时执行原有短重置。

Overflow hook 保留原始 task handle 和 task_name 地址，并通过静态任务表记录稳定 task ID、
有限可信名称、system state 和带有效标志的缓存 HWM；Idle 单独识别，未知任务显式标记。
原始名称指针即使为无效地址也不解引用，hook 不扫描可能损坏的 TCB。HWM 来自正常上下文
最近一次 snapshot，未采样时为 invalid，不伪装成故障时测量。静态 fault record、assert、
`configCHECK_FOR_STACK_OVERFLOW=2` 和 HardFault fail-stop 保留；没有 heap 或诊断 I/O。

## 最终生成与自动检查

最终工程：`tests/acceptance_runtime16_verified/`；详细日志：`tests/artifacts/runtime16/`。

- 默认 Generate：523 个文件，未编译；第二次 Apply：0 added / 0 modified / 490 preserved。
  Generate、reload、second apply 均 Ready。Source Graph 为 **138 C + 1 ASM**。
- `python -m compileall -q src main.py tools`：通过；Python cache 重定向到 `tests/`。
- 冻结源码后的定向测试：**21 passed**，含本轮 20 项测试和工程计划一致性复验。
- `python -m pytest -q --basetemp=tests/.pytest-runtime16-complete`：**318 passed in 627.45 s (0:10:27)**。
- Release / Debug：`mingw32-make -j8 CONFIG=<config> stack-report artifact-check` 均返回 0，
  ELF/MAP/HEX/BIN 齐全；每个配置有 138 份对应当前 C source graph 的 `.su`。
- Host：`pwsh -NoProfile -File Tests/Host/run_tests.ps1`，**67 executables / 12415 checks /
  0 failures / 8 compile-pass cases / 16 expected compile rejections**。
- Architecture：**270 checks，0 failures**。独立 stack-report 只读取已经链接的 ELF；
  精确许可该目标，不允许编译目标依赖它；新增反例验证依然拒绝构建期 Python generator。
- Power of Ten：**6008 checks，94 first-party C files，2258 functions**。
- `mingw32-make -j8 CONFIG=Release static-analysis`：first-party `-fanalyzer`、依赖编译和链接通过。
- 两个配置的 Artifact Check 均通过，runtime heap symbols 为 0。

最终目标固件构建使用匹配的 Arm GNU Toolchain **14.3.Rel1 / GCC 14.3.1 20250623**。
Host 使用本机 GCC；PowerShell、TEMP/TMP 仅使用本次进程设置，未修改全局环境或 PATH。

## Release / Debug 静态任务栈预算

| Task | Configured B | Release estimate B | Release margin B | Debug estimate B | Debug margin B |
| --- | ---: | ---: | ---: | ---: | ---: |
| Device | 2048 | 1496 | 552 | 1320 | 728 |
| INS | 3072 | 2040 | 1032 | 1808 | 1264 |
| Estimator | 4096 | 1964 | 2132 | 1868 | 2228 |
| Flight | 4096 | 3428 | 668 | 2292 | 1804 |
| Logger | 3072 | 1336 | 1736 | 1296 | 1776 |
| Serial | 6144 | 4200 | 1944 | 2928 | 3216 |
| Telemetry | 4096 | 1980 | 2116 | 1660 | 2436 |
| Idle | 512 | 256 | 256 | 256 | 256 |

单位均为 bytes；estimate 已包含 256 B Cortex-M4F exception/FPU context reserve，margin
是在此基础上额外剩余的空间。规则要求 margin >= 256 B。原 Device 1536 B、INS 2048 B
在 Release 下仅余 40 B / 8 B，因此也增大；Serial 从 2048 B 增至 6144 B，Telemetry 从
1536 B 增至 4096 B。全部静态任务栈总量为 27136 B，比原配置增加 8192 B。

工具读取真实 `.su`、匹配的 linked ELF `objdump` 与 `nm`。每个当前 C source 必须有 `.su`，
遗漏直接失败；不会把缺失报告的工程源码当库汇编估计。Inline frame 由 `.su` 计入；direct
和 tail-call 都保守相加。无 `.su` 的链接库汇编按 constant pushes/SP decrements 累加，包含
`strd [sp, #-16]!`；单一 FatFs SD_Driver callback 经实际绑定校验后闭合。未知间接调用、
无界 frame、递归和不能解释的 SP 操作会拒绝报告。新增测试覆盖缺失报告、库 SP 占用、
不足余量、未知 indirect 与递归。它是可复现的 worst-known 静态预算，不是运行 HWM 或任意
未来插件的数学证明；MSP 上的嵌套中断仍需另行实测。

完整逐函数路径、frame bytes、compiler、ELF hash 和检查结论见：
`tests/artifacts/runtime16/stack-budget-release.json`、`stack-budget-debug.json`。
Release Serial 最深已知路径仍经过 Console formatting；Telemetry 最深路径为 IMU stream
读取，已经没有同步完整 Alignment Process；Flight 预算覆盖 Alignment 的深层路径。

## 内存和最终 ELF

| Config | text B | data B | bss B | FLASH (text + data) B |
| --- | ---: | ---: | ---: | ---: |
| Release | 259736 | 1128 | 127296 | 260864 |
| Debug | 276064 | 1128 | 127320 | 277192 |

Release 主 SRAM 使用 77360 / 131072 B，剩 53712 B；Debug 使用 77384 B，剩 53688 B。
两者 CCMRAM 使用 51064 / 65536 B，剩 **14472 B**；heap reserved/runtime symbols 都为 0。
FLASH 容量 524288 B，Release 剩 263424 B，Debug 剩 247096 B。

- Release ELF SHA-256：`bea64d4c292578b06ea445a00ef8481e93a85f90531817a7760018fe1ec163f8`。
- Debug ELF SHA-256：`257770a5ce8adb5693256eeb9ec1d75665a93601d54dc8aa79e6e3a175d6710e`。

两个最终 ELF 的下列检查全部为 true：

1. `main -> AppTasks_Init` 闭包包含 `SystemIndicator_Init`。
2. `SystemAlignment_Start` 闭包不包含完整 `SystemAlignment_Process`。
3. Telemetry 和 Serial task 闭包均不包含完整 Alignment Process。
4. FlightTask 闭包包含 Alignment Process。
5. 7 个应用静态任务及 Idle 均有 stack budget；当前 timer task 未启用。

## 协议与剩余实机验证

AIR M0、Maintenance 0.0、SSLOG 0.0、`.ssdecoder` 1.1 的版本、字段布局、CRC、endianness、
Record size 和现有 command tokens 均未改变；没有 breaking wire change。修正的是既有
calibration_mode_mask 的广告值。参考导入仍逐项核对四个协议/Console C 文件的 SHA-256，
Host/Python 覆盖四种 handshake bytes、Golden/codec round-trip、Required calibration snapshot、
decoder、source selector、多实例和 verified-board mapping 回归。

仍需真实 SS0.5 持续验证：上电指示灯及 polarity、重复 AIR/Serial ALIGN/CAL/RESET 命令、
所有任务的长期 HWM、MSP/中断嵌套、来源锁定/失效场景、SD 会话中的实际校准快照。
本轮没有实际运行 HWM、native EIDE build、烧录、电气、HIL 或飞行验证，不扩大硬件支持范围。

下文保留此前轮次的历史验证数据；其 HEAD、测试数量和内存数值不属于本轮。

---

# Validation — 2026-09-02 SS0.5 verified Board fixed-resource mapping repair

This section records validation actually performed for the verified-Board fixed-resource mapping
repair. The result remains an internal **Software Release Candidate / Pre-Hardware-Validation**
result. It is not a flash, electrical, HIL, dual-platform, or flight qualification.

## Current commit and worktree identity

- Branch: `main`
- Base `HEAD`: `533b4aa091d37bc6f6980a27f470e053fcbd49f5`
- Base subject: `新增IMU，GNSS，遥测的新增接口`
- Worktree at validation time: intentionally dirty with this repair, tests, and documentation. No
  commit, push, Release, or Tag was requested or performed.
- External reference firmware and SilverStar_FLP remained read-only and were not built, modified,
  formatted, committed, or pushed.

## Root cause and repaired contract

The verified SS0.5 Board `connections.json` mapping was merged with imported CubeMX inventory
metadata, and the renderer then consumed the inventory `logical_index`. Inventory enumeration order
could therefore override the Board plugin's stable ABI and place correct physical aliases into the
wrong `PlatformGpioId` slots.

For a verified Board, `connections.json` is now the sole authority for logical ID, `c_id`, fixed
index, and purpose. The bundled `.ioc` and generated STM32 symbols only resolve and validate the
declared physical alias. Duplicate JSON keys, duplicate fixed aliases, missing aliases, kind drift,
symbol drift, and selected-requirement closure failures are rejected before publication. Custom
CubeMX projects retain their existing imported/manual `logical_index` behavior and do not inherit
the verified-Board contract.

The validated SS0.5 GPIO mapping is:

| Logical ID | Physical alias |
| ---: | --- |
| 0 | `RADIO_NSS` |
| 1 | `RADIO_RST` |
| 2 | `RADIO_BUSY` |
| 3 | `RADIO_DIO1` |
| 4 | `P_CONTROL1` |
| 5 | `P_CONTROL2` |
| 6 | `IMU_CAL_LED` |
| 7 | `GNSS_RST` |
| 8 | `GNSS_TIMEPULSE` |

## Python and generation validation

- `python -m compileall -q src main.py tools`: passed.
- `python -m pytest -q --basetemp=tests/.pytest-prompt15-full`: **298 passed in 577.04 s
  (0:09:37)**.
- Focused fixed-resource suite: **9 passed in 9.31 s**; the final combined mapping/lifecycle slice
  was **15 passed in 13.02 s**.
- A broader resource/generator regression slice was **73 passed in 189.41 s**.
- Fresh SS0.5 acceptance project: first apply added **518 files**; the second deterministic apply
  added 0, modified 0, and preserved 485 project-owned files. Readiness was `Ready` after generate,
  reload, and second apply.
- Source Graph: **138 C + 1 ASM source**. Optional platform sources: none.
- Generated decoder: **103122 bytes**, SHA-256
  `df885c2b48a62baa2cac15fb780797c1e90895d913d26a9ea2c462f701f9d657`.
- Resource-binding fingerprint in both hardware-preparation and ownership metadata:
  `b8af03e219b3412f1f7d42331a954bb1f7533e092e474dddcd8e8af80343991d`.

Focused tests cover the exact golden mapping, shuffled/wrong inventory indexes, verified-versus-
custom index authority, missing-alias rejection without fallback, duplicate fixed-alias rejection,
generated-table closure rejection, binding-fingerprint inputs, readiness invalidation, and custom
CubeMX compatibility.

## Generated-project builds and quality gates

Both Arm GNU configurations returned 0 and produced ELF, MAP, HEX, and BIN artifacts:

| Config | text | data | bss | text + data (FLASH) | data + bss |
| --- | ---: | ---: | ---: | ---: | ---: |
| Release | 259408 | 1072 | 119064 | 260480 | 120136 |
| Debug | 275656 | 1072 | 119088 | 276728 | 120160 |

- Host Tests: **56 executables, 9123 checks, 0 failures**, 8 compile-pass cases, and 16 expected
  compile rejections.
- Architecture Check: **255 checks, 0 failures**.
- Power of Ten: **5895 checks** over 94 first-party C files and 2206 functions.
- Arm GCC `-fanalyzer` Static Analysis: passed first-party analysis, dependency compilation, link,
  size, HEX, and BIN stages; `text=259408`, `data=1072`, `bss=119064`.
- Artifact Check: passed; ELF **2781544 bytes**, BIN/FLASH **260480 bytes**, main SRAM
  **77264/131072**, CCMRAM **42872/65536**, heap reserved 0, runtime allocator symbols 0.

This repair changes resource binding and validation only. AIR M0 wire values, maintenance and SSLOG
containers, calibration behavior, GSHC semantics, FLP behavior, decoder schemas, and multi-instance
semantics were not changed. Real GPIO electrical behavior, I2C/PWM electrical validation, hardware
flashing, HIL, dual-platform testing, and flight validation remain not done.

## Prior validation — 2026-09-01 bounded multi-instance follow-up

This document records validation actually performed for the bounded same-model multi-instance and
minimal failover follow-up on FCCG 0.0.10. The result remains an internal **Software Release
Candidate / Pre-Hardware-Validation** result. It is not a public release, tag, flash result,
electrical qualification, redundant-hardware qualification, dual-platform qualification, or
flight qualification.

## Current commit and worktree identity

- Branch: `main`
- Base `HEAD`: `f44f49e7e7163e4260a186d409fd1cdaa6f1ec1b`
- Base subject: `修改测试与文档，完成基础功能`
- Worktree at validation time: intentionally dirty with the current multi-instance implementation,
  tests, and documentation. This follow-up was not committed or pushed, and no Release or Tag was
  created.
- External reference firmware and SilverStar_FLP remained read-only and were not built, modified,
  formatted, committed, or pushed.

## Current multi-instance acceptance

- `python -m compileall -q src main.py tools`: passed.
- `python -m pytest -q`: **289 passed in 524.38 s (0:08:44)**.
- Focused multi-instance/prompt acceptance: **34 passed in 16.79 s**.
- Fresh single-device and `2 x JY901B + 2 x NEO-M9N + 2 x SX1281` projects each materialized
  **518 files**. The multi-instance Source Graph resolved to **138 C + 1 ASM source**, 46 include
  directories, and 12 defines.
- Final generated `.ssdecoder`: `SilverStar_Multi_Instance_Acceptance.ssdecoder`, **114272 bytes**,
  SHA-256 `cb735adfe49221ac61f3c3d35bd950668ab2c0f2634769222d98fdb91fb066c0`.
  Package schema and Project Semantics remain `silverstar.ssdecoder.package-schema/1.1`; the AIR M0,
  Serial Maintenance 0.0, SSLOG container 0.0, and existing Record IDs/layouts remain unchanged.

Final Arm GNU builds from fresh generated projects all returned 0:

| Project | Config | text | data | bss | text + data (FLASH) | data + bss |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| single device | Release | 259408 | 1072 | 119064 | 260480 | 120136 |
| multi instance | Release | 260000 | 1072 | 133664 | 261072 | 134736 |
| single device | Debug | 275656 | 1072 | 119088 | 276728 | 120160 |
| multi instance | Debug | 276720 | 1072 | 133688 | 277792 | 134760 |

The bounded multi-instance Release delta is **+592 bytes FLASH** and **+14600 bytes data+bss**;
the Debug delta is **+1064 bytes FLASH** and **+14600 bytes data+bss**. The increased static storage
is the compile-time-bounded per-instance parser, FIFO, driver, HAL, and selector state; no runtime
heap was introduced.

Final multi-instance quality gates:

- Host Tests: **56 executables, 9139 checks, 0 failures**, 8 compile-pass cases, and 16 expected
  compile rejections; observed wall time was about **123 s**. The new direct context tests report
  JY901B 25, NEO-M9N 29, SX1280 HAL 21, SX1281 28, and source selector 221 checks.
- Architecture Check: **255 checks, 0 failures**.
- Power of Ten: **5895 checks** over 94 first-party C files and 2206 functions.
- Arm GCC `-fanalyzer` Static Analysis: passed strict first-party analysis, dependency compilation,
  link, size, HEX, and BIN stages; result size `text=260000`, `data=1072`, `bss=133664`.
- Artifact Check: passed; ELF **2778856 bytes**, BIN/FLASH **261072 bytes**, main SRAM
  **91864/131072**, CCMRAM **42872/65536**, heap reserved 0, runtime allocator symbols 0.

Software tests verify independent resource tables and mutable contexts, all-instance IMU/GNSS
native logging, pre-alignment IMU selection followed by a lock, one-way GNSS liveness failover, and
one-way AIR transport failover after 10 consecutive real TX timeouts. Exhausted/single telemetry
chains keep retrying the last source once per normal send period; they do not stop or enter an
unbounded retry loop. TX completion is only local-radio success and does not prove ground-station
reception or antenna health.

Physical dual-IMU, dual-GNSS, dual-radio electrical/EMC/RF, HIL, and flight validation remains not
done. I2C pull-up and PWM waveform/polarity/safe-level electrical testing and a second real hardware
platform also remain not done.

## Prior 2026-08-31 freeze commit identity

- Branch: `main`
- Commit: `f44f49e7e7163e4260a186d409fd1cdaa6f1ec1b`
- Subject: `修改测试与文档，完成基础功能`
- Parent: `0fb9101a31ab949c25e41da3c0d61dbb6b9f8efd`

## Environment

- Windows PowerShell 7.6.4
- Python 3.14.0
- PySide6 6.10.1
- Arm GNU Toolchain 14.3.Rel1, GCC 14.3.1
- GNU Make 4.4.1 (`mingw32-make`)
- MSYS2 UCRT64 Host GCC 16.1.0, target `x86_64-w64-mingw32`
- Builtin catalog: 36 strict packages
- Platform/FCCG/generated-firmware release identity: 0.0.10
- Project format: 11
- Decoder package/project-semantics schema: 1.1

AIR M0, Serial Maintenance 0.0, Flight Log Format/SSLOG container 0.0, FreeRTOS 11.3.0,
SS0.5, STM32F407VET6, CubeMX, and STM32Cube FW retain their independent versions.

## Read-only reference and reproducibility

- Path: `C:/Users/chdxm/Desktop/stm32-1/Flight_Controller0.5`
- Branch: `main`
- Commit: `cc0b377ded690556d037a412a55f87fe334c42d0`
- Subject: `完善同能力多实例与日志配置契约`
- Working tree: clean
- Snapshot digest: `7998cace3e609d4e0c3f16f8d9e4cdf531f3f82939670638d4fe4d02f3c4e942`
- Deterministic recorded UTC time: `2026-08-27T18:07:29+00:00`, derived from the commit

The importer was run repeatedly against that exact read-only snapshot. Each run completed the
required-file and maintenance-document audits with no missing files/findings, and the second
publication produced no further tree change. The external repository was not modified, formatted,
built, committed, or pushed.

The four frozen wire-source SHA-256 values still match the read-only reference:

- `Protocol/Src/air_protocol.c`:
  `4537b3588b65baa051c13605eed5715a42f530abe5a0bdfad11a4925a2a0b418`
- `System/Src/system_console.c`:
  `c1efc4849c33c9fca361015ec6068d027eeac95bd275f56d139146ea3c781d99`
- `Protocol/SSLOG/Src/sslog_protocol.c`:
  `b065b6733fe87dea5e220e8eaed4ef61569fff831e3dd3d14f1c218fc6aaa3bc`
- `Protocol/SSLOG/Src/sslog_records.c`:
  `871b73bd1cecf9a39a2b95006f34bb32d303a5cba23d55aa02aedb934fe03d30`

## Python, schema, GUI, and model regression

- `python -m compileall -q src main.py tools`: passed
- `python -m pytest -q`: **276 passed in 478.64 s (0:07:58)**
- Strict builtin/plugin/project/schema loading passed.
- Root-CWD portable-path tests passed while actual `WorkspacePolicy` root authorization remained
  rejected; traversal, absolute/drive/UNC, dot/empty segment, backslash, control, reserved-name,
  trailing-space/dot, and unsafe build-field cases remained rejected.
- F407 target lock, mismatch/tamper detection, save/reload/reconcile, render paths, and a fully
  test-only synthetic `SilverStar_H743_Test` MCU/Board/OS/storage fixture passed. The fixture is
  architecture coverage only and is not an H7 product-support claim.
- Calibration GUI/model/migration/semantics tests passed for empty, OneFace, SixFace, and both;
  the pre-release Existing combinations migrate deterministically and are never serialized again.
- Host-level NONE/identity/READY/corrected-IMU/Required `CALIBRATION_RESULT` field checks passed.

## Fresh default generation and deterministic outputs

Fresh project: `tests/acceptance_final_freeze_0_0_10_r2`.

- First materialization: **504 generated/copied files**
- Resolved Source Graph: **136 C + 1 ASM source**
- Readiness before second apply: Ready, no missing or stale paths
- Second apply: 0 files added, 0 files modified, 472 project-owned component files preserved
- Release, Debug, static-analysis, EIDE, and VS Code consume this same Source Graph

Generated decoder package:

- File: `FCCG_Final_0_0_10.ssdecoder`
- Size: **102390 bytes**
- SHA-256: `696d09226fc8a574602514e342667b46e7cf4e707c1f580740b62640927482d3`
- Package schema ID: `silverstar.ssdecoder.package-schema/1.1`
- Entries: only `README.md`, `checksums.sha256`, `manifest.json`, `project_semantics.json`, and
  `record_catalog.json`; no executable code

Generated Host golden log:

- File: `FCCG_Final_0_0_10_golden.sslog`
- Size: 1350 bytes
- SHA-256: `bf0ffeb23344390764377807ce6e4aa9a4a02ad4416687e7fe9516edccb69fed`

The `.ssdecoder.algorithms` list is verified/documented as onboard composition, not an FLP offline
algorithm whitelist. FCCG did not modify FLP or implement old-log compatibility.

## Eight optional-Protocol combinations

`tools/check_optional_protocol_combinations.py` freshly generated every Telemetry/Maintenance/
Logging combination below `tests/acceptance_optional_protocols_0_0_10_final_freeze/`. All 16
Release/Debug builds returned 0. `arm-none-eabi-nm` found every enabled task function/stack/TCB and
found none of those three allocation symbols for each disabled Protocol.

Each row also contains one startup ASM source.

| Telemetry | Maintenance | Logging | C sources | Release | Debug | task symbol audit |
| --- | --- | --- | ---: | --- | --- | --- |
| 1 | 1 | 1 | 136 | passed | passed | passed |
| 1 | 1 | 0 | 126 | passed | passed | passed |
| 1 | 0 | 1 | 132 | passed | passed | passed |
| 1 | 0 | 0 | 122 | passed | passed | passed |
| 0 | 1 | 1 | 133 | passed | passed | passed |
| 0 | 1 | 0 | 123 | passed | passed | passed |
| 0 | 0 | 1 | 129 | passed | passed | passed |
| 0 | 0 | 0 | 119 | passed | passed | passed |

## Calibration build combinations

The default empty selection completed both Release and Debug plus the full Host suite. Three fresh
additional projects supplied representative toolchain coverage:

| Calibration procedures | Configuration | Source Graph | Result |
| --- | --- | --- | --- |
| empty → NONE/identity | Release + Debug + Host | 136 C + 1 ASM | passed |
| OneFace | Release | 136 C + 1 ASM | passed |
| SixFace | Debug | 136 C + 1 ASM | passed |
| OneFace + SixFace | Release | 136 C + 1 ASM | passed |

Empty selection retained the calibration subsystem and required result producer. No Record ID,
72-byte payload layout, endian, CRC, or SSLOG 0.0 container change was made.

## Generated firmware quality gates

All commands ran against the fresh default F407/SS0.5 project and returned 0.

- Release: `text=248680`, `data=1072`, `bss=118976`, `dec=368728`
- Debug: `text=262472`, `data=1072`, `bss=118992`, `dec=382536`
- Host Tests: 51 executables, 8799 checks, 0 failures, 8 compile-pass cases, and 16 expected
  compile rejections. Expected rejections retained raw GCC details and counted as successful gates.
- Architecture Check: 250 checks, 0 failures
- Power of Ten: 5601 checks over 92 first-party C files and 2074 functions
- Static Analysis: full first-party Arm GCC `-fanalyzer` build with strict warnings, link, size,
  HEX, and BIN stages passed
- Artifact Check: ELF 2630264 bytes, BIN/FLASH 249752 bytes; FLASH 249752/524288, main SRAM
  77176/131072, CCMRAM 42872/65536, heap reserved 0, runtime allocator symbols 0

## Source-package and repository closeout

The final documentation snapshot is followed by two consecutive deterministic source-package
exports. Both contain **757 entries**, are byte-for-byte identical, and contain no absolute/drive
entry names, acceptance/build/cache directories, or binary/object/dependency/listing artifacts.
The final archive size and SHA-256 are reported in the handoff after the last export because the
archive includes this document itself; embedding its own hash would change that hash.

## Remaining validation

- Physical I²C external-pull-up and PWM waveform/polarity/safe-level electrical tests are not done.
- Dual real-hardware-platform internal testing is not done; the synthetic H743 fixture is not a
  substitute.
- Flash/upload, SD-card media endurance, radio link, actuator bench, HIL, and flight tests are not
  done.
- A normal Classic CAN consumer/filter/router/bus-off contract is not implemented.
- SilverStar_FLP single-log import, exact decoder matching, rejection of unpublished old logs, and
  offline-algorithm comparison remain a separate follow-up task.

## 2026-09-12 shared algorithm-parameter closeout

Scope: generic `selection.ui_order` owner ordering, declarative `shared_key`, one shared GUI editor,
strict format-12 equality, and decoder required-FLP correction only. Platform 0.0.10, package and
project semantics 1.2, Record Catalog, AIR M0, Maintenance/SSLOG 0.0, firmware algorithm formulas
and timing remain unchanged. FLP was not modified.

Observed default generation resolves both `SYSTEM_INS_GRAVITY_MPS2` and
`SYSTEM_KF_GRAVITY_MPS2` to `9.779999733e+00f`; both decoder parameter sets contain binary32
`9.779999732971191`. Strict package verification reports package schema 1.2 and
`required_flp_minimum_version=0.0.2`.

| Check | Result |
|---|---|
| `python -m compileall -q src main.py tools` | PASS |
| builtin catalog scan and shared resolve/generate script | PASS (36 plugins; INS then KF6; equal gravity) |
| default SS0.5 assembler generation below `tests/.runtime-shared` and `.ssdecoder` strict verify | PASS |
| `python -m pytest -q tests/test_algorithm_parameters.py tests/test_gui_smoke.py` | ENVIRONMENT BLOCKED before collection: PySide6 loader requires unavailable `libGL.so.1` |
| Release / Debug / Host Tests / Architecture Check / Power of Ten / static analysis | ENVIRONMENT BLOCKED: generated Windows gates require unavailable `powershell` (and target toolchain) |
| frozen 52,045-float numerical trajectory | ENVIRONMENT BLOCKED: fixture requires `D:\\msys64\\ucrt64\\bin\\gcc.exe`; test remains present and now checks shared-only 9.81 change plus restored-default identity |

No GUI screenshot was captured because the same missing `libGL.so.1` prevents starting PySide6 in
this container. No hardware/toolchain/flight validation is claimed.

## 2026-09-24 optional estimator and Enter-only numeric commit

The user's generated project is under `D:/stm32_project/SS_0_5_TEST_2/HARDWARE/`,
not the parent directory. Its format-12 `SilverStar.ssproject` persists
`components.strategies.estimator = null`, INS Coning2Sculling2, Landing
Baro+IMU Window, and logging enabled. `Generated/project_sources.mk` and EIDE
both select `SYSTEM_FUSION_NONE` / `SYSTEM_BUILD_ESTIMATOR_ENABLED=0U` and omit
KF6 sources/includes. The existing project was kept read-only. A read-only
Arm GCC `-fsyntax-only` invocation with Core includes and those defines
reproduced `APP/Inc/estimator_task.h:7:10: fatal error: navigation_kf.h`.
The saved None selection is genuine; this evidence does not establish why the
user previously expected KF6. FCCG save/reload tests retain both selections.

Core now owns the public measurement-result enum (wire values 0..4), and the
KF6 implementation maps internal results explicitly. Only KF6 state, replay,
updates, and logs are conditionally compiled; origin collection, Pure INS,
mission start, snapshot publication, rollback, and abort remain available in
None builds. The Power of Ten checker permits only the exact estimator build
macro in `APP/Src/estimator_task.c`; four positive/negative tests enforce that
scope. No Record Catalog, SSLOG layout, decoder schema, AIR protocol, or
checker threshold changed.

Fresh generated SS0.5 configurations were built with `all stack-report
memory-report artifact-check` in each mode. All four gates returned 0 in each
row. KF6 includes `navigation_kf.c` and `navigation_kf_replay.c`; None includes
neither their sources nor `-IAlgorithm/Estimator/KF6/Inc`. Make and EIDE render
the same selected graph.

| Estimator | Configuration | ELF bytes | BIN bytes | Build / stack / memory / artifact |
| --- | --- | ---: | ---: | --- |
| KF6 | Release | 2870344 | 272520 | pass / pass / pass / pass |
| KF6 | Debug | 4255600 | 289056 | pass / pass / pass / pass |
| None / Pure INS | Release | 2700668 | 246200 | pass / pass / pass / pass |
| None / Pure INS | Debug | 4068084 | 261520 | pass / pass / pass / pass |

| Estimator | Power of Ten checks | C files | Functions | Power of Ten failures | Architecture checks / failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| KF6 | 6075 | 95 | 2279 | 0 | 262 / 0 |
| None / Pure INS | 5780 | 93 | 2171 | 0 | 262 / 0 |

Host: KF6 68 executables / 4386469 checks / 0 failures; None 66
executables / 4352291 checks / 0 failures. Both had 8 compile-pass and 16
expected compile-rejection cases. A fresh copy regenerated from the *actual*
saved user project, entirely below FCCG `tests/`, independently passed Release
(ELF 2700568, BIN 246200), Debug (ELF 4067996, BIN 261520), stack/memory/
artifact, Power of Ten 5780/0, architecture 262/0, and Host 66 executables /
4352291 checks / 0 failures. The original generated project was not modified;
its old payload requires regeneration to receive this repair.

The full FCCG pytest suite, explicitly collecting all 43 top-level test
modules to avoid inaccessible historical test-output directories, passed:
**425 passed, 1 skipped, 0 failed**. The existing skip is the active read-only
reference-firmware task. `compileall` passed for `src`, `main.py`, `tools`, and
changed test support. Ruff passed on every changed Python file. Repository-wide
Ruff still reports 192 findings in untouched files; the tracked HEAD snapshot
has 205 findings with the same installed Ruff 0.16.8. Neither lint rules nor
Power of Ten gates were weakened to hide findings.

GUI tests cover mode/algorithm/logging numeric drafts, invalid intermediate
input, Enter-only commit, focus-loss restore, step/wheel draft behavior,
unchanged immediate dropdown selection, and one validation/display transaction
per accepted Enter. Read-only FLP compatibility smoke passed 8 SSLOG parser
tests plus its generated C golden → exact decoder → replay/mechanization test;
read-only GSHC AIR smoke passed 14 tests. FLP and GSHC have no product diff.
No flash, EIDE GUI invocation, or physical hardware test is claimed.

## 2026-09-25 — FCCG/FLP GNSS position self-check integration candidate

**Gate decision: 存在阻塞，不应使用该候选固件.** This is a software candidate and is not flight validated. Only FCCG and FLP were edited; GSHC was frozen. Initial/final HEADs are FCCG `f062e078f18fac847453a6039ca104555683f348` on `main`, FLP `dc5a36dd932768137387e80d9f7bd93dfb5a8b01` on `main`, GSHC `cbee51e1f259d56a8e9dcdb7c3b236f9b054e4fb` on `main`. The first two working trees contain this round's uncommitted changes; GSHC has no diff. No push, release, flash, shutdown, or physical output was performed.

### Implemented candidate and contract

The new KF6 plugin source `navigation_integrity.c/.h` consumes one received GNSS epoch at a time. Its horizontal position/velocity comparison uses resolved position and velocity measurement times, a causal trailing window, bounded interpolation, receiver quality and evidence age. Separate evidence validity prevents a poor-quality interval from voting a SUSPECT state back to TRUSTED. A short position-invalid interval does not destroy a still-continuous velocity integral. A genuine velocity/time/sequence/epoch gap invalidates the trusted reference and resets timers and pending reanchor. Position EN alone can receive normal R, conservative R, or pause; velocity and vertical groups retain their existing policy. The finite reference-age rule uses `anchored_threshold_m + velocity_bias_bound_mps * reference_age_s` and permits renewal only while trusted and within the renewal bound. A position reanchor request now also requires current valid evidence and an admitted position group. KF6 fixed-lag replay freezes admission, R and reanchor intent for its event, applies eligible reanchor at the historical position measurement time, then replays forward. No checkpoint copies the 272-sample evidence history.

The full **20-parameter table**, types, units, ranges and new/legacy defaults are in `docs/ALGORITHM_PARAMETERS.md`. New KF6 selection defaults to `gnss_integrity_enable=1`; existing KF6 owners missing these fields reconcile to 0. The generated project/decoder metadata declares `navigation_replay.gnss_integrity_revision=1`; revision-0 FLP replay stays disabled. The ordinary KF6 source graph includes the new C file. The unchanged SSLOG container and existing record versions were preserved.

The receive-side static sample capacity is 272 for a declared maximum 10 s/25 Hz window with 550 ms allowance; `s_integrity` occupies **11,088 B** of main SRAM. Full-capacity admission returns `NAV_INTEGRITY_PROCESS_CAPACITY` instead of silently truncating evidence. Per receive, four history searches inspect at most 272 samples each and full-buffer compaction copies at most 271 samples. The separate fixed-lag replay bound is `144 + 2*(48+160) = 560` steps. There is no heap allocation or recursive path. Actual target execution time, GNSS rate acceptance across the full configured range, and flight load are **not measured**.

### Generated projects and gates

Fresh SS0.5 projects are under `tests/.integrity-generated/final-matrix/{KF6-on,KF6-off,PureINS}`. The final reanchor guard source was hash-synchronized into the two test-only generated KF6 projects (SHA-256 `BA715B1B6A6FCC6C29B39E7D51DFCF0CC85A1E573B51542796DB3ACDA9749862`) and their quality and Release/Debug gates rerun. `PureINS` was generated after all shared C changes and does not compile the integrity or KF6 sources. The original user project and logs were not rewritten.

| Project | Power of Ten checks / C files / functions / failures | Architecture checks / failures | Host checks / failures | Release / Debug artifact |
| --- | --- | --- | --- | --- |
| KF6 enabled | 6157 / 96 / 2308 / **0** | 262 / **0** | 4,386,469 / **0** (68 executables) | **FAIL / FAIL**, main SRAM budget |
| KF6 disabled | 6157 / 96 / 2308 / **0** | 262 / **0** | 4,386,469 / **0** (68 executables) | PASS / PASS |
| Fusion=None / Pure INS | 5786 / 93 / 2173 / **0** | 262 / **0** | 4,352,291 / **0** (66 executables) | PASS / PASS |

Power of Ten and architecture checkers were not changed. All six Release/Debug configurations compiled, linked, passed stack-report, and had heap reserve/runtime symbols 0. The enabled artifact gate rejected Release main SRAM **113,216/102,400 B** (over by 10,816 B) and Debug **113,240/102,400 B** (over by 10,840 B). Physical capacity is 131,072 B, but that is not the reviewed full-rate logging limit. Disabled KF6 uses 102,128/102,152 B; Pure INS uses 82,808/82,832 B. CCMRAM is 64,160 B for both KF6 builds and 53,080 B for Pure INS, all under 65,536 B. FLASH Release/Debug is enabled 279,344/296,696 B, disabled 273,784/290,488 B, and Pure INS 246,192/261,520 B. The minimum linked static task-stack margin in enabled Release is Idle 256 B; Flight 668 B; all eight task budgets passed. These are linked/static reports, not measured target high-water marks.

The generated Host logger model's normal full-rate case accepted 163,694 records, dropped 0, and saw queue HWM 76/44; finite overload accepted 163,759, counted 436 drops and HWM 80/43. These are host-model results, not target timing or the proposed new diagnostic record's load. The new decision record is **not implemented**, so measured added record rate and bytes/s are unavailable; no 0-load claim is made. Expected compile rejection cases: 16; compile-pass cases: 8, for each KF6 Host run.

FCCG full top-level suite: **425 passed, 1 skipped, 1 failed**; the single failure is `test_estimator_build_matrix[KF6]` asserting the enabled artifact gate. The focused C integrity fixture passed **13 checks, 0 failures**, including invalid-quality pending-reanchor suppression and high acceleration with 270 ms position/velocity effective-time separation. Changed Python Ruff, `compileall`, and `git diff --check` passed. Repository-wide Ruff still has pre-existing findings in untouched files; no lint or Power of Ten policy was relaxed.

### Joint and real-log evidence

The existing C codec golden from the **disabled** generated KF6 project round-tripped through its exact `.ssdecoder` and FLP parser/replay test (1 passed). The enabled C golden and matching decoder parse, but FLP correctly rejects enabled faithful/What-if replay with `kf6_integrity_replay_not_implemented`; there is no new per-epoch integrity decision record and no C→new-log→FLP comparison of state, reason, mask/R, reanchor, x/P/q. A metadata revision by itself is not that record. This is a release blocker, not a passed joint gate.

Read-only real inputs at `D:/stm32_project/SS_0_5_TEST_2/` were exact-paired using descriptor and SHA-256. `SS0000.BIN` = `b20da913ffc599a92eafb8191841b4bdd1d1e81277ed5ffc39ce81384c986d9b`; `SS0001.BIN` = `d5297f7a901684922360e0c3158c6759d9725755df5959dd0018059bc9b7def3`; decoder = `3fc7000fc027b153b604596850d516eb7960892afc22a6c6681da9d57a95d7bd`; project = `9d60045175d4df9980a583b5a4e194980e0362df4f6b70305c032b347f01f35a`. Input hashes were unchanged after read-only replay. These files do not have the `(3)` suffix; identity with absent copies is not asserted. FLP's new causal display analysis gives SS0000 228 valid horizontal 5 s windows over 368 consumed epochs, including valid tail 11.481–14.728 s after the 11.160–11.441 s position-invalid endpoint interval. It gives SS0001 9385 valid windows over 9517 consumed epochs; its long tail remains valid. The per-segment reason list is in FLP's ignored `tests/.integrity-generated/real_log_gap_reasons.json`.

Revision-0 legacy KF6 replays actually ran on both BINs. They are flagged `APPROXIMATE` because firmware/reimplementation and fixed-lag golden equivalence are not established. Raw-time replay endpoint closure/speed: SS0000 **8.013 m / 1.679 m/s**; SS0001 **52.825 m / 0.870 m/s**. Neither reported a reanchor. No new enabled-KF6 real What-if was produced because FLP intentionally fails closed; there is no supportable new-vs-old improvement number. The user's approximately 1 m return-to-start observation was never used as an algorithm input and does not provide trajectory truth.

### Blocking work before controlled field retest

1. Reduce or redesign the 11,088 B static receive-history cost, or otherwise recover reviewed SRAM within the existing resource contract; rerun enabled Release/Debug artifact and full matrix. Do not raise the budget just to obtain a pass.
2. Implement a versioned integrity decision/transaction SSLOG record, decoder and FLP same-version causal streaming replay, then compare generated C golden state/reason/reference/mask/R/reanchor/x/P/q and run real old-vs-new What-if. Current revision-1 metadata alone cannot provide faithful replay.
3. Prove a reference-loss recovery exit against both correct recovery and stable biased-position counterexamples. Current conservative behavior can remain RECOVERING after losing an independent trusted anchor; do not treat a freshly zeroed local residual as absolute recovery.
4. Measure target CPU/receive rates, record bytes/s, queue HWM and flight behavior in controlled bench/field work after software gates pass. No open-area or high-dynamic ground-truth log was available here.

Reproduction from each generated project root: `mingw32-make -j4 SHELL=cmd.exe CONFIG=Release architecture-check power10-check host-tests`, then `mingw32-make -j4 SHELL=cmd.exe CONFIG=Release all stack-report memory-report artifact-check` and repeat the latter with `CONFIG=Debug`. The enabled artifact command is expected to exit nonzero until item 1 is fixed. Full FCCG suite: `python -m pytest (Get-ChildItem tests/test_*.py).FullName -q --basetemp=tests/.integrity-generated/full-suite-work`; run the focused fixture with `python -m pytest tests/test_navigation_integrity_host.py -q --basetemp=tests/.integrity-generated/integrity-host-work`. Host/gate logs are beside each ignored generated project. No generated binary or raw log was added to Git.

## GNSS Integrity Simplification

2026-09-26. This section supersedes the blocked 2026-09-25 integrity candidate. FCCG and FLP were edited; GSHC was frozen. This is software acceptance evidence for a controlled retest candidate, not target CPU timing or flight truth.

### Algorithm and firmware integration

The 272-sample 1/2/5/10-second receive history, its searches/interpolation/compaction, and the integrity-specific historical KF re-anchor were removed. NavigationIntegrityContext is **112 B**, down from **11,088 B** (10,976 B saved). Processing uses fixed two-axis arithmetic per native GNSS solution epoch, no dynamic allocation, no recursion, and no unbounded loop. Receiver-native EN position displacement is compared with trapezoid-integrated receiver-native EN velocity; the KF6 270 ms scheduling delay is not treated as a sensor epoch offset. Short position-invalid intervals preserve the velocity integral and anchor. Velocity, sequence, time, source, or replay-epoch breaks reset the integration reference. A new anchor after SUSPECT/REJECTED cannot by itself restore NORMAL. Recovery against the original trusted anchor is hysteretic; existing KF6 group reacquisition remains the position recovery mechanism. No velocity-derived position measurement or high-frequency integrity record was added. The C fixture passed eight scenarios, including drift, one-point jump, position gap, chain break, original-anchor recovery, lost-anchor sticky state, and healthy 20-second/25 Hz high dynamics. Actual target execution time was not measured.

The manifest has **10** integrity parameters instead of 20 and declares revision 2. FLP accepts revision 0 as legacy integrity-off, revision 2 as this stream algorithm, and explicitly rejects revision 1. GNSS_NATIVE preserves raw receiver validity; GNSS_MEASUREMENT records actual KF6 Pos EN admission and R. EVENT 0x2E records only state transitions. KF6_DIAGNOSTIC remains decodable but defaults off. GNSS_RECOVERY is emitted when its recovery state, generation, update result, or other meaningful fields change. Existing SSLOG wire layouts and the reviewed 102,400 B main-SRAM budget were not changed.

### Generated Release/Debug and quality matrix

Three generated SS0.5 projects live in tests/.tmp_final_matrix/{KF6IntegrityOn,KF6IntegrityOff,PureINS}. Production and generated C source hashes were matched before final gates. For each project, Release and Debug all, stack-report, memory-report, artifact-check, plus architecture-check, power10-check, and host-tests all exited **0**; exact exit codes are in tests/.tmp_final_matrix/results-final.json. All eight linked static task-stack budgets passed. The minimum was Idle **256 B**; KF6-on Release Flight **668 B** and Estimator **1,036 B**. Linked stack estimates are not measured target high-water marks.

| Project | Release FLASH / main SRAM / CCMRAM (B) | Debug FLASH / main SRAM / CCMRAM (B) | Reviewed main-SRAM margin Release / Debug (B) |
| --- | ---: | ---: | ---: |
| KF6 integrity ON | 276,288 / 102,120 / 64,424 | 293,288 / 102,144 / 64,424 | **280 / 256** |
| KF6 integrity OFF | 273,152 / 102,120 / 64,312 | 289,952 / 102,144 / 64,312 | **280 / 256** |
| Fusion=None / Pure INS | 246,200 / 82,808 / 53,080 | 261,520 / 82,832 / 53,080 | 19,592 / 19,568 |

FLASH capacity is 524,288 B, physical main SRAM capacity 131,072 B, and CCMRAM capacity 65,536 B. KF6-on has **1,112 B** CCMRAM headroom and only **280/256 B** reviewed main-SRAM headroom. The gate passes, but later source or buffer growth requires a fresh linked resource review. Heap reserve/runtime symbols remained zero. The previous enabled candidate used 113,216/113,240 B main SRAM and failed the unchanged review gate.

**Power of Ten:** KF6 integrity ON and OFF each passed **6,133 checks, 96 first-party C files, 2,299 functions, 0 failures**. Fusion=None passed **5,792 checks, 93 C files, 2,175 functions, 0 failures**. **Architecture:** all three passed **262 checks, 0 failures** each. Both KF6 conditional paths and Fusion=None were checked; neither checker nor budget was changed. **Host:** each KF6 project passed **68 executables, 4,386,471 checks, 0 failures**; Pure INS passed **66 executables, 4,352,291 checks, 0 failures**.

### Logging and joint replay

The comparable Host normal full-rate logger model before/after the KF6_DIAGNOSTIC default change accepted **163,694 → 158,845** records over **199.7058 → 199.7418 s**, or **819.68 → 795.25 records/s**. Validated bytes were **15,513,371 → 14,873,215**, or **77,681.12 → 74,462.21 B/s**. Normal/estimator queue high-water marks were **76/44 → 77/38**; both runs had **0 drops and 0 producer failures**. In finite overload, the final run had HWM **80/39**, **436 drops**, and **14 producer failures** (before: **80/43**, **436**, **14**). The Host fixture deliberately still emits GNSS_RECOVERY each epoch, so this rate comparison measures the diagnostic default and does not quantify the production change-driven producer. Host scheduling is only a model.

The separate 16-second real-C-codec golden measured the recovery producer: **391 → 1 GNSS_RECOVERY** records, **13,903 → 13,513 total records**, and **1,482,220 → 1,422,940 encoded bytes** (390 records and 59,280 B saved, or 24.375 records/s and 3,705 B/s). It contains three EVENT records, exactly two of them new integrity transitions; the latter contribute 80 encoded B. No per-epoch integrity stream was added. The matching generated decoder parsed without CRC, framing, or sequence failure. FLP compared the 600-epoch direct C/Python stream state, closure, mask, R, reason, reset and evidence, then the SSLOG golden's logged mask/R, x/P/q, Pos EN update result and NIS. A revision-2 What-if changed the Pos EN disable count as expected. This synthetic golden is not universal real-log fidelity; FLP marks the real replays APPROXIMATE.

### Read-only real inputs and limits

SS0000.BIN, SS0001.BIN and their exact decoder at D:/stm32_project/SS_0_5_TEST_2/ retained SHA-256 b20da913ffc599a92eafb8191841b4bdd1d1e81277ed5ffc39ce81384c986d9b, d5297f7a901684922360e0c3158c6759d9725755df5959dd0018059bc9b7def3, and 3fc7000fc027b153b604596850d516eb7960892afc22a6c6681da9d57a95d7bd after replay. Their accessible filenames omit (3); identity with absent copies is not claimed. Endpoint horizontal values below are replay outputs, not external trajectory truth or algorithm inputs.

| Log | GNSS epochs | Revision-0 endpoint horizontal (m) | Revision-2 What-if endpoint horizontal (m) | First SUSPECT / REJECTED (mission s) | Pos EN disabled |
| --- | ---: | ---: | ---: | ---: | ---: |
| SS0000 | 368 | 8.013 | 8.013 | none / none | 0 |
| SS0001 | 9,517 | 52.825 | 8.380 | 10.1494 / 15.1604 | 9,139 |

FLP VALIDATION.md records the six-tab State Estimation UI, two Measurements plots, three GNSS integrity plot/export classes, independent frozen export source, revision handling, parity, and **385 passed / 8 skipped** FLP tests. The original BINs were not modified and return-to-start was never used as an algorithm input. No commit, push, release, flash, physical output, or shutdown was performed.

### Final regression and disposition

The first complete FCCG run exposed four failures: two stale default-on assertions, one Host storage expectation for KF6_DIAGNOSTIC, and one missing reference-import overlay default. The overlay now declares default_enabled=false and the assertions check protocol-owned defaults; the four focused cases passed. The next complete run exposed an intermittent Windows Save As PermissionError while moving a staged System directory. Save As now commits through the existing WorkspacePolicy.Path_Replace path validator and bounded five-attempt Windows retry. The regression injects one transient directory lock and passed; a persistent replacement error still propagates through the existing rollback. No Power of Ten checker, resource budget, or C source was changed for these test repairs.

The final complete FCCG pytest command was: python -B -m pytest (Get-ChildItem tests/test_*.py).FullName -q -x --basetemp=tests/.tmp_full_revision2_accept_final -p no:cacheprovider. Result: **426 passed, 1 skipped, 0 failed** in 1,460.97 s. The skip is the pre-existing active read-only reference-firmware task; pytest also emitted the existing unknown cache_dir configuration warning. Focused Save As, reference-import, logging-default and storage-pressure reruns passed. Critical Ruff F/E9 on changed Python, JSON parse, and git diff --check passed; broader Ruff style findings in untouched test sections remain outside this gate.

**READY FOR CONTROLLED FIELD RETEST.** This is a software-gate decision with only 280/256 B of reviewed main-SRAM margin and 1,112 B of KF6-on CCMRAM margin. A controlled target retest must measure actual CPU load, task high-water marks, storage throughput, and GNSS behavior before any operational use. No flash, hardware output, push, tag, release, or shutdown was performed.

## 2026-09-26 — SilverStar 0.0.12 release-candidate cleanup

This round starts from FCCG `def2fb99f565f71a6be7f954f6227d87e5d2c6d4` and paired FLP `ce743f4a8ae4043556a3232cffd9a4087347df78`; GSHC `cbee51e1f259d56a8e9dcdb7c3b236f9b054e4fb` remained frozen. SilverStar Platform and FCCG product move from **0.0.10 to 0.0.12**. `src/silverstar_fccg/app/version.py` remains the single runtime authority and derives `SilverStar_0_0_12`, `silverstar.core.0_0_12`, `silverstar_core_0_0_12`, `SILV0012` and profile ID `0x0000000C`. The official builtin Core package directory is now `plugins/builtin/silverstar_core_0_0_12/`; all current builtin dependencies and source-graph references use it. The old Core directory is absent as a current builtin. GNSS integrity **revision 2** is a separate algorithm revision and was not changed.

Freshly generated firmware has `SILVERSTAR_VERSION_MAJOR/MINOR/PATCH = 0/0/12`, version string 0.0.12 and build target `SilverStar_0_0_12`. The new `.ssdecoder` manifest and project semantics declare firmware 0.0.12 and required FLP minimum 0.0.4. Project format stays 12 and decoder/project-semantics stay 1.2; platform logger records and SSLOG layout are unchanged. New generated projects were checked for stale active 0.0.10 identity in saved project, Generated headers/semantics, decoder, console, Make target and component graph. FCCG package import/About/dynamic pyproject version and a test-only wheel all resolve to 0.0.12.

### Compatibility and remaining old-version references

A format-12 project migrates on open only when it has the exact official triple `firmware_version=0.0.10`, `build_target=SilverStar_0_0_10` and `components.core=silverstar.core.0_0_10`. It then generates, saves and reopens as 0.0.12 without changing project format. Unknown third-party Core IDs are not silently migrated. An open → generate/save → reopen regression and the unknown-Core negative case passed. FLP continues to parse exact-matched old 0.0.10 revision-0 real logs and the earlier 0.0.10 revision-2 C golden.

The final old-version scan of current FCCG `src`, builtin manifests, tools, tests and current docs found only the three explicit migration guard values in `src/silverstar_fccg/project/model.py` and their positive/negative fixtures in `tests/test_final_freeze_0_0_12.py`. Historical VALIDATION, CHANGELOG, dated TARGETS notes and package-local historical validation keep the versions they actually described. They are historical records, not active product identity. The architecture checker had a stale exact `SILVERSTAR_VERSION_PATCH 10` expectation; it now requires patch 12, with a regression proving acceptance of 12 and rejection of 10. The Power of Ten checker, resource limits and C quality rules were not relaxed.

### Fresh generated project and firmware gates

Three new projects are under `tests/.tmp_revision_0_0_12_accept2/{KF6IntegrityOn,KF6IntegrityOff,PureINS}`; `results.json` and each `build/FCCG/Matrix/*.log` retain exact commands and outcomes. Each Release and Debug ran `all stack-report memory-report artifact-check`; each project separately ran `architecture-check power10-check host-tests`. **All 12 matrix gate commands exited 0.** The six firmware images linked and all eight static task-stack budgets passed; the minimum linked margin was Idle **256 B**. Linked estimates are not target high-water measurements.

| Generated project | Release FLASH / main SRAM / CCMRAM (B) | Debug FLASH / main SRAM / CCMRAM (B) | Reviewed main-SRAM margin Release / Debug (B) |
| --- | ---: | ---: | ---: |
| KF6 integrity ON | 276,288 / 102,120 / 64,424 | 293,288 / 102,144 / 64,424 | **280 / 256** |
| KF6 integrity OFF | 273,152 / 102,120 / 64,312 | 289,952 / 102,144 / 64,312 | **280 / 256** |
| Fusion=None / Pure INS | 246,200 / 82,808 / 53,080 | 261,520 / 82,832 / 53,080 | 19,592 / 19,568 |

The reviewed main-SRAM budget remains **102,400 B**; KF6 ON CCMRAM headroom is **1,112 B** against 65,536 B. Heap reserve/runtime symbols remain zero. These very small KF6 SRAM margins require a new linked review on any later source or buffer growth. No target CPU load, in-flight stack watermark, or physical storage throughput was measured in this round.

**Power of Ten results (separate gate):**

| Build path | Checks | First-party C files | Functions | Failures |
| --- | ---: | ---: | ---: | ---: |
| KF6 Integrity ON | 6,133 | 96 | 2,299 | **0** |
| KF6 Integrity OFF | 6,133 | 96 | 2,299 | **0** |
| Fusion=None / Pure INS | 5,792 | 93 | 2,175 | **0** |

**Architecture:** 262 checks, **0 failures** for each of the three paths. **Host:** both KF6 variants passed 68 executables / 4,386,471 checks / **0 failures**; Pure INS passed 66 executables / 4,352,291 checks / **0 failures**. The KF6 ON/OFF conditional paths and Fusion=None passed the same source-quality policy. After the Core rename, comparison of 181 C/header payload blobs found only the version header, console expected-version text and a versioned static-assert message changed; no navigation arithmetic, allocation, recursion, loop or task behavior was altered.

### Joint and repository regression

The 0.0.12 KF6 ON project generated a **13,513-record** real-C-codec SSLOG and exact matching decoder. FLP 0.0.4 parsed it with no CRC/framing failure and passed the opt-in revision-2 parity/replay/export test; the direct 600-epoch C/Python integrity stream parity gate passed separately. FLP also reopened read-only 0.0.10 SS0000/SS0001 with their exact old decoder, ran revision-0 Recorded and explicit revision-2 What-if, and verified unchanged source SHA-256. FLP `VALIDATION.md` records the GUI/export details and measured read-only results. No raw input or generated binary was committed.

Final FCCG top-level pytest: **428 passed, 1 skipped, 0 failed** in 1,688.79 s. The one skip is the pre-existing active read-only reference-firmware task; pytest emitted the existing unknown `cache_dir` warning. After clearing nine previously present critical Ruff findings in two already-touched Python files without behavior change, their focused parameter/importer rerun passed **25/25**. Critical Ruff E4/E7/E9/F on every modified Python file, `compileall`, 40 selected JSON manifests/templates, and `git diff --check` passed. A default repository-wide Ruff audit still reports unrelated older style findings because this repository has no configured Ruff baseline; it is not claimed as a clean all-file audit. The test-only 0.0.12 wheel was built under `tests/.tmp_release_0_0_12_package/` and not published.

**READY FOR CONTROLLED FIELD RETEST** on software evidence. The narrow SRAM/CCMRAM margins and absent target CPU/stack/storage measurements remain practical limits for a controlled retest. FCCG/FLP changes remain uncommitted; GSHC has empty `git status --short` and `git diff --stat`. No push, tag, release, flash, physical output, reset, clean or shutdown was performed.


## 2026-09-26 — Logging purpose profiles and generated logger acceptance

This FCCG-only round starts from `ec5e1a3` (SilverStar/FCCG 0.0.12). FLP 0.0.4 and GSHC have no tracked edits. The original `D:/stm32_project/SS_0_5_TEST_3` project was read only; its equivalent configurations were generated below `tests/.tmp_logging_purpose_acceptance_20260926/`. No firmware version, project format 12, decoder semantics 1.2, Record ID, SSLOG payload/wire layout, navigation/KF6/fixed-lag mathematics, integrity revision 2, SRAM budget, or Power of Ten checker changed.

### Cause and correction

The SS_TEST_3 logger Host failure came from a test assertion that `KF6_DIAGNOSTIC` must initially be disabled, even when the generated project's own `project_log_config.c` explicitly enabled it. The GUI's ordinary availability-refresh path also called `LoggingProfile_SelectAllAvailable()`, which could turn all newly available records on after a component or algorithm change and erase metadata defaults. Either an explicit user choice or that refresh could produce a valid enabled diagnostic stream. The test now compares all 28 runtime streams with the generated configuration across record type, enabled, policy, decimation, and period; its temporary KF6 runtime policy tests remain. The storage Host fixture now conditions bootstrap/jitter expectations on the generated POWER/IMU streams and enables STATS only in deliberate overload scenarios that require durable drop-accounting evidence. Normal profile-throughput scenarios retain the exact generated settings.

All 28 metadata records now declare a strict, independent `purpose`: 26 Flight and two Test. Only `KF6_DIAGNOSTIC` and `KF6_FULL_P` are Test, Optional, and disabled by default; `KF6_DIAGNOSTIC` moved from Recommended to Optional. Replay inputs such as `INERTIAL_INCREMENT`, `ESTIMATOR_STEP`, native sensors, measurements, and `GNSS_RECOVERY` remain Flight. Missing or unknown purpose fails metadata validation. Both the builtin parser metadata and FCCG reference overlay carry the same classification.

The Logging table has a translated Purpose column and exactly three one-shot configuration actions, in order: Enable All, Flight Logs Only, Required Only; decoder-profile export remains alongside them. The actions write only existing `logging.streams[].enabled` values, so subsequent manual edits persist and no project-profile enum or migration was added. An available stream retains its choice across an unrelated change; loss of availability disables it; newly available streams recover their metadata default. Required records stay enabled. Protocol removal/reselection follows the same transition semantics. At 1000×700 with 200% Qt scale, all four action/export buttons fit within the 759-pixel group (rightmost at 737); table scrolling is per pixel.

### Generated projects, firmware gates, and Host

| Generated configuration | Test streams in generated C | Build/resource gates | Final Host result |
| --- | --- | --- | --- |
| Fresh KF6, Flight Logs Only | both OFF | Release and Debug: all, stack, memory, artifact, architecture, Power of Ten PASS | 68 executables, 4,386,845 checks, 0 failures |
| KF6, Enable All | both ON | Release: all, stack, memory, artifact, architecture, Power of Ten PASS | 68 executables, 4,386,845 checks, 0 failures |
| KF6, Required Only | both OFF | Host profile fixture | 68 executables, 4,386,845 checks, 0 failures |
| Fusion=None / Pure INS | both unavailable/OFF | Release and Debug: all, stack, memory, artifact, architecture, Power of Ten PASS | 66 executables, 4,352,665 checks, 0 failures |
| SS_TEST_3 equivalent, Test enabled | both ON | Host regression fixture | 68 executables, 4,386,845 checks, 0 failures |
| SS_TEST_3 equivalent, Flight Logs Only | both OFF | Host regression fixture | 68 executables, 4,386,845 checks, 0 failures |

Every final Host run also passed eight expected compile-positive and 16 expected compile-rejection cases. All six storage-integrity runs used the real FatFs/diskio/Logger/codec Host model and strict decoder audit, including bounded DMA delays and finite overload accounting. No normal startup log had drops or a sequence gap.

**Power of Ten results (separate gate):**

| Build path | Checks | First-party C files | Functions | Failures |
| --- | ---: | ---: | ---: | ---: |
| KF6 Flight Release | 6,133 | 96 | 2,299 | **0** |
| KF6 Flight Debug | 6,133 | 96 | 2,299 | **0** |
| KF6 Enable All Release | 6,133 | 96 | 2,299 | **0** |
| Fusion=None Release | 5,792 | 93 | 2,175 | **0** |
| Fusion=None Debug | 5,792 | 93 | 2,175 | **0** |

Architecture-check passed **262 checks, 0 failures** on each of those five paths. The checker and its tests were not changed. New/modified C is confined to bounded Host fixtures and the generated golden fixture; it adds no dynamic allocation, recursion, unbounded loop, hidden error return, or conditional bypass. All eight static task-stack budgets passed on each linked Release/Debug build. KF6 Release/Debug main SRAM is **102,120/102,144 B** against the unchanged reviewed **102,400 B** limit (280/256 B margin), CCMRAM **64,424 B** (1,112 B margin), and FLASH **276,288/293,288 B**. Pure INS Release/Debug main SRAM is **82,808/82,832 B**, CCMRAM **53,080 B**, FLASH **246,200/261,520 B**. Heap reserve/runtime symbols remain zero.

### Comparable Host logging throughput

Each profile used the same KF6 configuration and 40,000-step startup-burst model, with about 199.706 simulated seconds. Rates include the encoded file header and bootstrap/descriptors. The matching generated decoder strictly audited each entire file with CRC/framing and no sequence gap, no queue drop, and no unvalidated tail.

| Profile | Audited records | File bytes | Records/s | Bytes/s | Normal queue HWM | Estimator queue HWM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Enable All | 163,746 | 15,513,371 | 819.94 | 77,681.12 | 76 | 44 |
| Flight Logs Only | 157,926 | 14,764,531 | 790.80 | 73,931.53 | 73 | 38 |
| Required Only | 149 | 7,039 | 0.75 | 35.25 | 48 | 0 |

Required Only intentionally lacks ordinary state and measurement evidence and does not guarantee faithful FLP replay. The Host fixture still produces `GNSS_RECOVERY` every epoch; these numbers are model comparisons, not target SD/CPU/flight throughput measurements.

### FLP 0.0.4 read-only joint check

The generated C codec produced an integrity-scenario Flight golden with **11,913 records, 1,243,740 B, zero KF6_FULL_P**, and an Enable All golden with **13,513 records, 1,422,940 B, 1,600 KF6_FULL_P**. Both passed whole-file strict audit with matching generated decoders and zero gaps. FLP's existing C-golden integrity replay test passed against Enable All. Flight Logs Only imported with valid header/record CRC and sequence, provided **1,600 Recorded trajectory** samples and **1,600 recorded covariance-diagonal** samples, and replayed KF6 from Recorded Configuration with **1,600 recomputed full-P** samples. It reported revision-2 GNSS integrity, NIS, input/effective variance, receive age and fixed-lag latency channels, zero mask/R mismatches, and a What-if response (position-disabled count **165 → 114**). Export produced 27 files including GNSS position-integrity and Recorded position-uncertainty plots. Its fidelity label remains **APPROXIMATE**, consistent with the existing replay contract. The synthetic golden contains no LANDING_DIAGNOSTIC record; the independent FLP landing-diagnostics UI test passed 1/1. FLP files and raw logs were not modified.

### Repository regression and disposition

Complete FCCG top-level pytest with explicit source modules and short `tests/.t26` temporary path: **433 passed, 1 skipped, 0 failed** in **1,957.23 s**. The skip is the pre-existing active read-only reference-firmware task. Pytest emitted one existing unknown-`cache_dir` configuration warning. Changed Python passed `compileall` and Ruff `E4,E7,E9,F,I`; default Ruff on these touched files retains 36 pre-existing broader style findings, down from 41 at the starting HEAD, with no new finding. `git diff --check` passed after this report update. Test and generated outputs remain below `tests/` and were not added to Git.

**READY FOR CONTROLLED FIELD RETEST** on software-gate evidence. A target retest must still measure actual CPU, task-stack high-water marks, storage throughput and queue margins, especially with KF6's narrow linked SRAM/CCMRAM headroom. No flash, release, physical output or shutdown was performed.
