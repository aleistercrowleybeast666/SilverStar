# SilverStar 三仓库联合重构验收

执行日期：2026-09-27。本报告覆盖软件实现、模拟、真实旧日志分析及生成固件的静态/Host 验证。
最终命令、数量、资源及哈希以本仓库 [VALIDATION.md](VALIDATION.md) 的本轮章节为准；
FLP、GSHC 各自的 VALIDATION 保留产品级证据。原始固件、五份 BIN 和 matching decoder 均只读。
用户后续明确授权三个仓库提交和推送，并已取消关机。没有烧录、物理输出、tag 或发布。

## 1. 基线、版本与共同契约

| 仓库 | 起始提交 | 本轮应用版本 |
|---|---|---|
| FCCG | `d013ae1` | 0.0.12，Platform 仍为 0.0.12 |
| FLP | `c4605f4` | 0.0.4 → 0.0.5 |
| GSHC | `cbee51e` | 0.0.3 |

Project format 12、decoder/project-semantics 1.2、AIR M0 数值及基本帧长度不变。
ESKF15 算法 revision 1，公共质量策略 revision 3；旧 KF6 revision 2 离线语义仍保留。
新生成 decoder 明确要求 FLP 0.0.5；旧 decoder 不被改写成新算法。
三仓库相同的 `docs/contracts/navigation_v1.json` 以及
[导航契约](docs/NAVIGATION_CONTRACT.md) 规定 ENU、Hamilton `q_nb`、误差顺序、量纲、时间、
source/generation、质量、日志和预飞状态。35 个 ESKF 实参来自插件声明、项目持久化值和 generated header，
FLP 从 exact decoder 读取，不以另一套私有默认替换记录值。

主要实现位于 FCCG builtin 的 Algorithm/Common、Algorithm/Estimator/ESKF15、Core APP/System、
SSLOG/AIR、设备插件和生成器；FLP 增加真正的 ESKF 数学/延迟重放、记录解析、诊断、比较和导出；
GSHC 增加导航准备事务、五组健康与新会话协议消费。最终 Git 清单由提交及 VALIDATION 记录。

## 2. 预飞与导航健康

`ALIGN_START` 同步校验请求，实际静态对准、原点采集与所选 kernel 初始化由 FlightTask 完成。
Calibration NONE 也是 READY identity correction；不绕过校正链。START 再次检查当前代次、设备准备、
姿态、GNSS 当前解、GNSS/Baro 原点和 kernel q/P 初始化。ACK 只代表请求被接收。
Host 中实际 KF6/Pure INS/ESKF 初始化路径均执行，SS0002 式“准备后立即 START”明确拒绝。

GSHC 使用新连接 nonce、准备 generation、扩展序列和逐字段 TTL；重连、BOOT、重新校准、重新准备、
陈旧/乱序/重复包不能延长 READY。准备 TTL 为 2 s，健康/融合年龄 3 s，低频详情 10 s。
旧固件不支持扩展时显示 UNKNOWN/UNSUPPORTED。现有 9-byte AIR 帧和网关封装未改长，
实体网关是否透传新 type 仍需台架确认。

Pos EN、Pos U、Vel EN、Vel U、Baro U 分别保留 receive/physical-valid/attempt/success/recovery 时刻。
成功仅指实际接受且 gain 有限、至少一项非零的已提交更新；历史 replay 不反复刷新现实成功时钟。
不同 source 的相同 receive tick/sequence 是不同证据，同 source 重复/倒序不计入。
2 s 未成功进入 dead reckoning，10 s 进入 INVALID。有效量测恢复真实融合后可记录 reacquisition；
IMU 丢失硬故障或 MODEL_MISMATCH 单独锁存，后续一个正常 GNSS 不会把它恢复成 HEALTHY，须显式重初始化。

## 3. 低卫星数、R 与双窗口

对仍物理有效的解，卫星数方差倍率为 `min(4, 1 + 0.5 max(0, 6-n)^2)`；6→5→4→6 对应
1→1.5→3→1。无 fix、坏 CRC、NaN、不支持字段、过期数据仍拒绝。预飞 origin 门禁保持独立严格。
先取 receiver/profile sigma floor 并形成 variance，再依次乘 quality、Pos EN consistency、robust 倍率；
variance 倍率不再次平方。各组独立，不因低卫星数量单独切断所有辅助。

两个窗口各 10 s、错位 5 s，完成证据 TTL 6 s。以 GNSS native epoch、端点位移与速度梯形积分计算 closure，
对边界进行插值，不累计全任务误差。丢 native time、跨 source/generation、跨长缺口重建窗口；
无效新窗口不刷新旧证据。10 m threshold、最高 4 倍 variance 仅作用于 Pos EN，不能证明哪个 GNSS 量错误，
不能永久关组或重置状态。ARM 实测 `sizeof(NavigationWindowContext)=184` B，无样本历史数组。
600 s 的 +0.2 m/s 速度小偏差反例不会永久关闭位置；慢位置漂移反例仍保留拒绝和 INVALID。

## 4. 恢复权限与失败路径

超时主管授权明确降级，不授权无条件增大 P/R、伪造 ACCEPTED 或强融无效数据。
KF6 原通信失联后的有界回归/冷却/重锚事务仍保留；纯 NIS 拒绝不等价于失联重锚资格。
ESKF 以真实 robust 更新恢复，无法恢复时保持 INVALID，不承诺 small-angle 模型能修正严重姿态错误。
NEAR_RANGE/TIME_UNCERTAIN 将过程 variance 乘 4；CLIPPED、时间断裂、未知量程、配对偏斜是硬故障。
JY901B 近量程负值按原始有符号数据保留，不翻号。

最终独立审查补充了三项回归：拒绝 BODY 不得提前裁剪 600 ms 历史；模型不一致锁存与 Python 相同；
不同物理 source 可具有相同 receive tick。C 的工作区 scratch 与权威 anchor/body/event/live state 明确分开。
CLIPPED/NaN/P 非法/prefix 重放失败/满容量均不能部分提交权威历史。

进一步审查修复 KF6 浮点下溢全零 gain 仍计成功的问题：要求全部 gain 有限且至少一个非零，
否则返回 NUMERIC_ERROR，状态/P/成功计数保持不变；零创新但正常 gain 仍可成功。
所需组的软降权或实际 variance 倍率大于 1 使总健康为 DEGRADED，DR/INVALID 的超时优先级不变。
生产者记录卫星数、Pos EN 专属窗口及真正 robust 更新三者的完整倍率。

## 5. ESKF15 数学、所有权与延迟

名义 `[p,v,q,bg,ba]`，误差 `[dp,dv,dtheta,dbg,dba]`；ENU，Hamilton 标量在前，右乘局部小角误差。
输入为校准后的 body SI 双半区间均值；残余 bias 每半区间扣除，coning/sculling 只有一个所有者。
传播含姿态/加速度/bias 交叉项、二阶离散 transition/Q；噪声幅度密度仅平方一次。
更新使用 Joseph P、右乘 Exp 注入及 SO(3) right-Jacobian reset。GNSS 杆臂位置/速度 Jacobian 包含姿态与
gyro bias 项，Baro U 不套 GNSS 杆臂。有限性、PSD、q 归一化、bias 与注入范围在候选提交前检查。

600 ms 固定历史、192 BODY、208 events、最多 608 replay 操作；最大配置延迟 550 ms。
重放保存 body 输入，在修正后的 q/bias 下重新传播，不重复使用旧 ENU delta-v。
只有一个 anchor/working pair；ARM sizeof：state 992 B、workspace 3980 B、history 16992 B、
BODY 64 B（共 12288 B）、event 72 B。未给每个 IMU epoch 保存 15×15 P。
source/generation 不连续、缺早期历史、重复、满容量、callback/数值失败都有显式结果。
时间同步和测量延迟是两个层次；M9N iTOW 存在不等于已证明 MCU 精确采样时间。

## 6. C/Python/日志数值证据

独立 float64 与 Jacobian、C/Python 逐 epoch 对照涵盖静止、bias、动态、杆臂、q/-q、接近 180°、
分组异常、延迟排序和失败事务。2000 prediction epochs / 1000 measurement groups 的最大绝对差：
p `1.032e-5` m、v `9.416e-6` m/s、q `7.533e-6`、bg `5.680e-7`、ba `5.175e-7`、P `3.127e-6`。
既定 absolute `2e-4` / relative `3e-4` 容差没有事后放大。250 Hz 混合延迟对照最大差 `5.383e-6`，
最大实际 replay 步数 178；100 Hz 对照最大差 `3.16e-6`。

真实 C codec + 当次 generated descriptor 的 659-record 正序及跨队列乱序 golden 均可 FAITHFUL。
另有真实初始化/ESKF backend → LoggerBus → LoggerTask → Host sink 的 491-record 闭环：99 条量测
physical/admitted/result 精确一致，p/v/q/full-P 最大差约 `9.52e-9 / 1.28e-7 / 8.67e-8 / 7.31e-7`。
未尝试量测在结果/准入精确一致后将 NIS/innovation/R 标 unavailable；实际尝试仍严格比较。
导出 361 文件，0 失败；2 幅依赖不存在旧 IMU_CORRECTED 流的图明确不可用，BODY-only bias/P 图正常。
此 Host sink 不是实机 FatFs 时序测试；FatFs/diskio/DMA 压力由另一个实际完整链验证。
最后 C 健康修复后重新生成的 exact pair 已由现有 FLP 复验：数值差异不变，
20 STATE + 20 NAV_QUALITY 的健康值按精确时间全部一致。该 fixture 以软加权 result 表示降权；
ACCEPTED 且实际 R>1、零 gain 拒绝及 checkpoint/restore 另由最终 FLP 针对性用例验证。

## 7. 传感器、初始化和成熟度

逐型号资料 URL、固定源版本/许可、寄存器/默认 profile、请求/响应/readback/persistence、mock 与
实生成接口矩阵见 [SENSOR_LIBRARY_VALIDATION.md](docs/SENSOR_LIBRARY_VALIDATION.md)。
覆盖 MPU6000/6050/6500/9250、BMI088/BMI323、ICM42605/42688-P/45686、LSM6DSV32X/320X，
以及 M8N/M9N/MAX-M10S/F10N。MPU6050 无假 SPI；ST320X 高 g 保持独立；MPU9250 磁力计非六轴必需。
只有实际选中的 source/include 与实例状态进入生成图；未知 PCB 接线显示缺资源，不猜引脚。

BMI088 raw200 与 Sync400 为独立选择；raw200 不获导航同步资格。Sync400 I2C/SPI 使用 Bosch
固定提交的 6144 B 配置块及完整 BSD-3-Clause 许可，必须绑定 gyro INT3→acc INT1 同步网及
acc INT2 ready 网，缺 label/时序/配对证据即拒绝。实际 driver 加载、读回、IRQ 次序、跨 epoch、
重入与错误返回均有 Host 负测；26 个型号/接口的真实生成 ARM 编译通过。
400 Hz raw 经真实 APP 校正、两样本配对与惯性前端输出 200 Hz BODY，600 ms history 最大 120/192，
4413 checks 无失败。2/3 ms receive-proxy 间隔仍明确 TIME_UNCERTAIN，不声称硬件边沿精度。
Sync image 占 Flash，sample/driver/adapter 的 ARM ABI 分别 80/112/256 B，没有增加软件队列。

正常启动 RAM 配置、差异写入、真实读回、稳定等待及 sample verify 才 READY。JY901B 不盲 SAVE，
M8 无法独立比较持久层时明确 UNSUPPORTED；不发送不可验证 CFG-CFG。
M9/M10/F10 按实际层能力、差异比较、有界 transaction 和保存后读回处理显式持久化。
型号/协议族、ACK/NAK、错波特率、重复/乱序/错误长度/checksum 都有负例。
传感器没有实物的部分一律 HARDWARE_UNVERIFIED；mock/ARM 编译不构成硬件通过。

## 8. F407 资源与调度边界

Release/Debug 的 ELF、`.su`、map 和 stack/memory/artifact gate 对同一 source graph 检查。
主 SRAM reviewed budget 102400 B、物理 131072 B，CCM 65536 B，Flash 524288 B；预算未提高。
ESKF logging 的 CCM 余量接近 456 B，KF6 Debug reviewed main-SRAM 余量接近 536 B，属于必须注意的紧余量；
最终精确表见 VALIDATION。runtime heap symbols 为 0。

所有静态任务含 Idle 检查。ESKF Debug 配置/估计 bytes：Device 2048/1328、INS 3072/2096、
Estimator 4096/2000、Flight 4096/2320、Logger 3072/1336、Serial 6144/3008、
Telemetry 4096/1904、Idle 512/256；已由最终 delta linked ELF 与 `.su` 确认。
Host 调度和静态调用链不是目标 WCET，也不代替实机 task HWM、ISR 占用和 SD 延迟测量。
显式 opt-in 的 [DWT 目标工具](plugins/builtin/silverstar_core_0_0_12/payload/Tests/Target/TIMING_BENCH.md)
已完成真实 ARM O2/Og 编译与 Host wrap/owner/异常/饱和测试，能采集真实任务、Logger 及队列诊断。
它不进入默认生产图；示例只测 snapshot getter，完整有限处理区间接入点另列，不冒称本轮测得 CPU/WCET。

## 9. Flight/Test 日志吞吐与完整性

原 28 条记录 wire layout 不变，新增 0x21–0x27 的 7 条导航记录及 0x2F 状态变更事件。
full P 四分片、统一一次 cadence；初始 state/P、BODY、measurement 为所选 ESKF 必需证据。
周期 full P 可由用户合法关闭，缺片或 CRC/sequence gap 不被忽略；FLP 按 snapshot identity 拼片。

80 ordinary / 48 estimator 槽容量保持原值。STATE/周期 P 使用 ordinary，QUALITY/BODY/MEAS/initial 使用
estimator；按归一化占用与连续最多 3 次同队列出队实现有界公平。4096 B 聚合在 streaming write 时先写至
512 B 文件偏移边界，余下最多 511 B 留缓存；关键/周期/final flush 仍完整写，119 B record 不填充。
DMA 未完成/卡未 ready 不复用；partial-write/sync 不确定失败不 reopen/replay aggregate。

真实 ESKF 正常负载含 100 Hz BODY、25 Hz×4 GNSS、100 Hz Baro、25 Hz state/quality；Test 再加
25 Hz×4 full-P parts。Flight queue HWM 65/80、46/48；Test 77/80、46/48，正常阶段 drop/producer failure=0。
有限超载 Flight/Test 分别 449/453 个可审计 drop；frame 1500 的累计值即最终值，后续恢复无新增丢失。
同 epoch 峰值 Flight/Test 为 ordinary 7/11、estimator 7。Host 最大 write 126 ms、sync 108 ms、
iteration 316.12 ms 是注入模型结果。严格 framing/CRC/sequence 审计不靠重同步取得 PASS。
119 B @ offset 37、prefix/强制 flush/partial uncertainty 的实际 LoggerTask 测试 533 checks；
完整 LoggerBus 测试 2102778 checks；数值仅属于本轮真实执行日志。

## 10. 五份真实旧日志

全部使用 `SS_0_5_TEST_3/LOG/SS0000..4.BIN` 和 `HARDWARE/SS_0_5_TEST_3.ssdecoder`。
全部 clean、CRC/framing/gap/decoder failure 为 0；输入哈希前后相同。
A=Recorded，B=旧 KF6 对应版近似复算，C=revision3 KF6 What-if，D=ESKF15 What-if。
旧日志缺少新 BODY 质量/量程读回/native-time 证据，所以 B/C/D 不冒充新固件实飞或全条件 FAITHFUL。

| 日志 | records / 时长 s | D 最长失辅 s | D 末位置 ENU m（约） | D 末状态与解释 |
|---|---|---|---|---|
| SS0000 | 17408 / 23.217 | 19.050 | 603, -1443, -2497 | INVALID；C/D 仍明显漂移，不能称性能改善 |
| SS0001 | 20267 / 27.242 | 0.560 | 3.55, 1.27, -0.12 | HEALTHY 为内部状态；无真值，不能称定位精度通过 |
| SS0002 | 211965 / 296.385 | 296.385 | -10197, 8262, -1.51 | INVALID；B/C 因缺 GNSS origin 失败，D 不造原点，只有 Baro 操作 |
| SS0003 | 149060 / 201.805 | 0.799 | -6.78, 209.23, 3.14 | DEGRADED；修正实际降权的健康判定，不代表已知真值改善 |
| SS0004 | 197904 / 267.724 | 51.178 | 3263, -9961, -5503 | INVALID；坏末段保留，未强融或隐去曲线 |

五份名义值/P 均有限、P 最小特征值为正，q norm 最大偏差约 2.22e-16；这些数值性质不等于物理正确。
所有 D reset_count=0。逐组可用/尝试/接受/软加权/拒绝、首告警/降级时间、末速度、窗口、bias/P 曲线及
原始 GNSS/Baro 对照见 FLP `tests/joint_rework_20260927/four_way_comparison/SS0000..4/` 和
`five_logs_contract_final/SS0000..4/`。C 保留旧日志实际操作/时序，只研究明确声明的质量/窗口/监督变化。
SS0002 的真正预防验证是新固件 START 门禁，绝非补一个 origin 后重标原日志成功。

最终健康接入后重新执行五日志×两算法，输出到独立的新目录。四份成功 C 的各 165 个既有非健康数组、
D 的 SS0000/1/3/4 各 141 个及 SS0002 的 45 个非健康数组与旧结果完全一致。D 的末健康依次为
INVALID、HEALTHY、INVALID、DEGRADED、INVALID；各日志 D 五组最长失辅均不变。
C 仅 SS0001/3 VelU 初始最大间隔增加 10321/14296 us，正式输入核对确认来自实际 START 与旧 helper
首输出起点的差异，并非融合改变。最终逐 epoch 健康和各组时间在 FLP `approved_quality_comparison.json`
及 `approved_quality_clock_basis.json` 中；73 份旧证据和全部原始输入哈希未改变。

## 11. GUI、导出与兼容

FCCG 保持五页与 Enter 参数提交，退休 KF6 revision2 控制只读标识；内部协议库不变成物理 Device。
批量 Required/Flight/Test 只操作可用记录，切算法不打开全部日志。默认初始化和成熟度可查看。
GSHC 准备与运行健康分离，GNSS 在线、origin 已冻结、实际融合与 INVALID 分别显示。
FLP 支持 15 维 P、两组 bias、NIS 分组、三个 GNSS 诊断、Landing 摘要、两算法图例/union bounds。
导出开始时冻结实际 source/参数/算法/语言主题，后台期间 GUI 改变不改变导出，取消/重启和 GIF 时长有回归。

三产品执行中英/Light/Dark、1000×700 和约 200% DPI offscreen 验证；截图和本地包启动不等于实体触屏/GPU认证。
旧 decoder/旧算法历史实现、公共 landing 调用链保留；未删除原始记录或历史报告。
本轮仅清理自己创建且已停止使用的临时生成目录，旧用户缓存保留并排除提交。

## 12. 门禁命令与反例

可重现正式生成/门禁入口为 `tools/validate_joint_navigation.py`，包含 KF6 Flight/Test、ESKF Flight/Test/off、Pure INS。
生成在 repository `tests/` 下，执行 R/D `all stack-report memory-report artifact-check`、
`architecture-check power10-check static-analysis` 及实际 generated-config `host-tests`。
产品完整 pytest 使用所有受维护 top-level `tests/test_*.py`，不递归执行历史生成 fixture；
递归误收旧临时目录造成的 collection errors 原样记录，不通过清空缓存/修改 skip 隐藏。
Ruff 遵循各仓库既定范围，compileall 缓存放在 tests；最终 `git diff --check`。

检查器变更只识别实际合法 no-logging 图，并增加 literal/semantic/source/payload/package 双向不一致负例；
关闭日志不能以缺文件自动跳过验证。35 项 Catalog 正反例保持旧 28 项身份不可变。
被自动审查拒绝的噪声门禁绕过提案未实施；新 GNSS 使用真实完整项目及其已有算法参数满足原门禁。
指示器改为必须有 generated 0/1 选择，缺定义/非法值硬拒绝，不再由另一份硬编码 1 覆盖。
完整通过/失败/skip 原因、各路径 Power of Ten 数量和 exit code 在最终 VALIDATION 与紧凑证据中列明。

## 13. 下一次 JY901B + M9N 台架（本轮未执行）

1. 确认 SS0.5 真正接线、JY/M9 型号及固件版本、UART 波特率、RAM 配置读回、无自动 NVM 写入；保持功率输出隔离。
2. 先用默认 Flight profile 验证多次上电、Calibration NONE/实际选定程序、静态对准、GNSS/Baro origin、
   kernel readiness、准备立即 START 被拒与完成后 START 接受；断线/重启/旧包不能恢复 READY。
3. 比较 KF6 与 ESKF 独立运行；同时记录实际 BODY 时间/质量/读回量程、四 GNSS 组与 Baro 操作。
   270 ms velocity delay 是待核实实验设置，不能当成所有 M9 固有延迟。
4. 先静止再受控地面运动，测量真实 INS/Estimator/Logger CPU、每任务 HWM、SDIO write/sync 延迟、两队列 HWM，
   再单独开启 Test/P 分片；核对零正常丢失、可解释故障、有限过载后恢复、strict FLP 比较。
5. 验证 6/5/4 卫星有效解降权、独立 no-fix 拒绝、真实失辅告警/INVALID 和受控重新初始化；不触发点火/开伞。
6. 核对真实无线网关新 type 的透明传递与时延。没有独立真值时仅报告一致性/回环量，不宣称定位精度。

## 14. 最终状态

BMI088 Sync400、GSHC GUI 和六配置完整固件矩阵已完成；最后 C 修复的所有 R/D 门禁及受影响 Host 补测通过，
最终 generated source audit 零差异。FCCG 产品全量回归 533 passed / 1 原条件 skipped，exit 0。
现有任务/队列 HWM 与显式目标 DWT 工具的编译、模拟、默认图排除和导入/导出验证均已完成。
此前自动审批拒绝四个新版 revision-3 接入文件；用户随后明确回复“可以继续修改flp”，该权限阻塞已解除。
有限非零增益/实际倍率健康逻辑的四个产品调用点已实际接入，五日志×两算法和最终实际桥接复验完成。
FLP 最终完整回归 483 passed / 9 原条件 skipped；GSHC 425 passed + 3 subtests；各产品 lint、
编译检查和本地包启动验证通过。原失败、skip 条件、近似复算边界和旧证据均保留。
本轮软件状态为 **IMPLEMENTATION_COMPLETE / SOFTWARE_GATES_PASS / READY_FOR_JY901B_BENCH_VALIDATION**。
GSHC 已本地提交 `8be9fd6a7d03be8a7edd96a78454b33701869ad0`；最终 Git 交付以三仓实际提交及远端核对为准。
所有新硬件继续 **HARDWARE_UNVERIFIED**，整套新实现 **NOT_FIELD_VALIDATED**；本轮没有执行台架或实飞。
