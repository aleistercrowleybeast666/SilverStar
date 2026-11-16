# 三仓本轮交付：2026-11-17

本轮在现有候选成果上继续修改，没有回退到旧 main。SilverStar 源码提交为 [6fed5b639d0835de7874a74db25a63ab0da814ad](https://github.com/aleistercrowleybeast666/SilverStar/commit/6fed5b639d0835de7874a74db25a63ab0da814ad)。软件验证和本地交付的范围如下；**原生 OpenGL 显示问题仍未证明解决，整个固件的全部关键合同审计也未宣称完成**。

## 基线与保存

| 仓库 | 实际稳定目录 / 分支 | 本轮起点 | 本轮源码 |
|---|---|---|---|
| SilverStar | `D:/python_software/SilverStar`；`feature/usb-transport-0.1.3-20261013` | `d52854c4a7b12c79dbb06cf967006e599103d24e` | `6fed5b639d0835de7874a74db25a63ab0da814ad` |
| Underline_RETLDC | `D:/python_software/Underline_RETLDC`；`codex/release-candidate-20261103` | `ef964623bba5f80cff9d97e2e4c33ba491f4e3eb` | `df9446f1db40ced01d24d76e466013123dd28796` |
| TreeDiagram | `D:/python_software/TreeDiagram`；`codex/gui-convergence-20261110` | `83c90491a1a9ce4c0a42641ed0161b160632802f` | `c97c753f76b84b8bdffffcdd0cd4f11c78b78853` |

三个 remote 分别为 `GitHub_SilverStar`、`GitHub_Underline_RETLDC`、`origin`，均指向用户指定仓库。保留现有 worktree 和历史证据；未复制新的完整仓库，未合并旧 main，未强推。先前的恢复默认、GSHC 顶栏任务快照、三/五/四工作区与事务机制继续保留。

## 实际修改

- SCG 共享无线属性先选频段，仅允许现有 LoRa。两端按同一模型筛选；切换频段在私有草稿中清除不兼容模块及其专属资源，Apply 才提交。非法 PHY 与导入差异明确显示，恢复默认会刷新候选。空选与目标缺项统一，已有板卡不显示 CubeMX 导入，自定义保留该入口。
- 现有六个 E28 SPI 型号保留；新增实际 owning driver 支持的 E19-433M20S2 实验型号，修正其内部 DIO4 前端、设备名称和三个存储 reader 的 module2 消费。当前软件合格参数有明确限制，没有将相似商品名称当成已支持硬件。详见 [无线报告](radio/README_ZH.md)。
- 新增 SSFC1.0 与 SSGS1.0 完整板型、默认示例、资源和厂商子集出处。SSFC 为 H743ZIT6、BMI088、NEO-M9N、MMC5983MA、E28-2G4M27SX；SSGS 为 C071FBP6、E28-2G4M12SX、外部 USB-UART。修正 H7 TIM6 handler 真正缺少 HAL 分发的问题。连接、晶振和校准都是待实物确认的设计假设，详见 [板型与使用方法](../../public/SCG/SSFC1_0_SSGS1_0.md)。
- 严格栈分析补齐真实 Thumb-1 表跳转、返回路径、C071 与 F103 的 reset/CRT/向量/中断分析；继续拒绝不完整输入和未审查机器码。F103 原 1 KiB MSP 不足，owning linker 增至 8 KiB，在 20 KiB RAM 实际链接约束内验证；不改导入的用户链接脚本。Ground 报告独立呈现真实 MSP，不伪造 RTOS 任务。
- Logger 首次发布前补容量及布尔状态检查；增广估计器缺少 SSLOG 的组合在生成前拒绝。Source selector、Mission、SPSC 与研究控制器调度消费完成本轮有限合同检查及故障回归，详见 [合同审阅](contracts/REVIEW_ZH.md)。
- SCG、GSHC、FLP、Underline、TreeDiagram 的关闭/确认框按所属窗口居中并限制在屏幕逻辑可用区域，保留默认按钮和取消语义。SCG 组合框显式拥有条目模型，修复后续实际无线操作暴露的 wrapper 类型故障。
- 启动优化：SCG 每次使用更轻的目录扫描，仍检查链接与 junction；FLP 首次显示水平轨迹才创建隐藏绘图画布；Underline 去除重复主题初始化；TreeDiagram 实际求解 LQR 时才加载 SciPy 求解器。没有跳过科学校验。测试证明这些路径的结构变化，未给出无噪声的冷启动耗时承诺。

## 已执行验证

| 范围 | 实际结果与边界 |
|---|---|
| SCG 最终冻结 GUI/模型组合 | 一次完整 18 文件运行：**394 passed / 1 skipped**，618.98 秒；输入 SHA 前后无变化。唯一 skip 是 Windows WinError1314 不允许创建符号链接。完整命令/JUnit/输入见 `radio/root-broad-final-*`；不是整个 SCG 测试全集 |
| 固件合同与栈回归 | 合同/栈选择 167 passed；最后公共 CRT helper 的 M4/M0+/helper 32 passed；F103/Ground 回归见 boards 收据。源码、调用者、前失败和负例均保留，未靠降低门禁获得通过 |
| E19 driver / reader / 身份 | 最终组合 249 passed；正常生成的 E32/E19 architecture 正反例 14 passed；最终 E19 Flight 完整 Host：74 个程序、5,508,837 checks、0 failures，mandatory storage 4/4。17 个预期编译失败及 23 个不适用项原样记录 |
| 默认 F407 / E19 Flight | 最终正常生成各双配置 ARM、artifact、strict 六门禁全 0，共 12。每配置默认 512 / E19 506 个产物含 BIN/HEX 与上一独立 epoch 原字节一致。当前源码运行 SCG 的业务 API 验证保存重开 current=true，不能当作便携 EXE 的 GUI 验收。见 [当前生成收据](contracts_current/CURRENT_RECEIPT.json) |
| SSFC1.0 / SSGS1.0 / F103 Ground | 最终 P 从空目录普通生成，使用当前 30/4-case Tools，H7 十二、C071 十四门禁全 0，全部输入前后不变。F103 D 当前 4-case、十四门禁全 0，两次每配置 229 个编译物相同，六类破坏仍拒绝。O 的旧28-case工具结果作为独立历史记录保留，未代替 P。见 [板型最终报告](boards/README.md) |
| GSHC / FLP | GSHC 158 passed（另有 8 unittest subtests）、FLP 71 passed，均是各自一次完整所选文件运行，不是全应用全集。实际模态框、取消、临时 observer 清除和懒加载路径通过，见 [显示报告](opengl/README.md) |
| Underline / TreeDiagram | Underline 全量 421 passed + Ruff；正式打包再次执行全量及新 EXE 亮/暗 smoke。TreeDiagram 全量 174 passed，新 wheel 独立安装后完成 CLI 和真实 offscreen GUI 全流程 |
| DPI | SCG 125%/150% 各三项、Underline/TreeDiagram 150% 真实 Qt 模态框检查通过。均为 Qt offscreen，不当作物理显示验收 |

原始失败、超时、测试夹具错误和真实修复前失败继续保留。旧无线断言仍期望格式14/15/16，而起点已是24，本轮只纠正测试并使用真实 v14 夹具保留相同拒绝；未改生产版本门槛。没有把多个局部 pass 拼成未执行的全套 pass。修改文件仍有历史 lint 诊断，未报告为整个 SilverStar Ruff 全绿。

提交前的执行由完整源文件/输入 SHA 和未提交快照绑定；日志中的 baseline HEAD 不是“该旧提交的干净执行”。各次构建的工具版本、配置与失败历史保留，不能跨时代拼接。最终便携包独立绑定源码提交和自身文件清单。

源码提交范围的 `git diff --check` 退出0；最终证据的相同检查退出2，指出原始 stdout/JUnit/审阅 diff 内的尾随空格。原字节、原 SHA 与诊断均保留，没有清洗失败日志、改变 whitespace 规则或把该项报为通过，详见 [原始证据文本检查](delivery/raw-evidence-whitespace-check.json)。仓库产物门禁独立通过，二者不是同一检查。

最终精确构型的 MSP 软件上界如下；每项仍需对应完整 `.su`、ELF、库、reset/CRT 和 ISR 嵌套证明，不把 RAM 物理剩余量当栈余量。

| 构型 | 预留 bytes | Release 上界 / 余量 | Debug 上界 / 余量 |
|---|---:|---:|---:|
| 默认 F407 / E19 Flight（分别有独立证明） | 2304 | 1932 / 372 | 1932 / 372 |
| SSFC1.0 H743 | 8192 | 6828 / 1364 | 5292 / 2900 |
| SSGS1.0 C071 | 4096 | 1920 / 2176 | 1360 / 2736 |
| E19 F103 Ground | 8192 | 3912 / 4280 | 3424 / 4768 |

两类 Flight 配置的任务最小余量均为 Idle 的 256 bytes，保持原门槛。默认 F407 的 Debug RAM 审阅预算仅剩 588 bytes，CCMRAM 物理剩余 2880 bytes，详细 bank/任务表见 [资源报告](contracts/RESOURCE_SUMMARY.md)；这些数字不能外推到任意新增功能。

## 跨仓真实闭环

Underline 使用既有导出插件从仓库明确标记为 synthetic 的试验工程新导出发动机包，SHA256 `66c6232d0ccec6ceaabdec9186e9059a2f16dc9eeedea0c94221f06a8ceaed96`。TreeDiagram 新 wheel 实际导入并完成 18 秒仿真，运行 ID `b0797d0e-9229-4212-901d-3048ad8b53de`，随后导出参数 SHA256 `aec2e1b6d488c490f72f0956ffee0ceb942e8fdea5e7e4ac24272c38895a245b`。

SCG 实际 MainWindow 完成预览、取消不变、Apply，明确挂接 ControlTask 后正常生成，由 owning C 真实 GCC analyzer 编译，并执行 28 个正常/故障场景，总共 29 个命令均退出0。包括过期/超时/调度交错/停止交错/损坏状态及源撤销等。证据见 [命令](integration/commands.json)、[收据](integration/receipt.json)、[输入范围](integration/scope.json)。此为离线研究控制闭环，没有实物执行器驱动或自动部署；合成数据不是发动机实测证据。

## 交付与运行

SilverStar 正常三应用打包已完成：`D:/python_software/SilverStar/dist/pf1117b/SilverStar_0_1_3_platform-finish-20261117_Windows_x64.zip`，243,811,792 bytes，SHA256 `21f8407e22151bcca13ea6217907c2f1d50a73a731c96763d0a5a392eb9f2b6b`。保留整个便携目录，运行其中 `SCG.exe`、`GSHC.exe`、`FLP.exe`，不能只复制单个 EXE。独立读取 ZIP 与解压目录的 3,619 项全部 SHA 一致，2,471 个第一方资源已核对；实际 `SCG.exe --version` 退出0，仅证明该 frozen 入口，不代表 GUI/3D/生成验收。见 [独立包校验](delivery/package-independent-verification.json)。

首轮三个独立 PyInstaller analysis/EXE 编译成功，但使用的新版旧包缺少原始 `source_versions` 字段，许可证整理真实失败。改用 `dist/SilverStar_0_1_2_Windows_Portable.zip` 内 Qt/Shiboken6 6.10.1、Python 3.14.0 的原始匹配凭据后，在另一个空目录完整重跑三个 analysis 与正常 stage，全部成功；未复用旧二进制、跳过版本检查或改门禁。两轮完整日志及输入收据见 [打包证据清单](delivery/packaging/inventory.json)。依赖归属收据唯一未匹配项为 NumPy 的 RECORD 元数据文件，原样保留，未伪报零未匹配。

实际 `FLP.exe --version` 正常退出0并输出0.1.3；`GSHC.exe` 使用独立 data-root、offscreen，在未连接状态存活40秒后由 runner 仅终止自己持有的进程。其 exit1 是主动终止结果，不能称正常关闭通过。两个应用的用户设置值哈希和272个包内应用文件前后不变，未产生遥测/日志数据。完整有限范围见 `opengl/package-smoke/`；未用它代替原生 GUI/3D 验收。

SCG 打开 `apps/SCG/examples/SSFC1_0_SSGS1_0.ssproject`（固件交付也附可打开配置），核对硬件假设，在第三页选择实际生成目标。内置板型无需再导入 CubeMX。构建命令与工具链要求见上方板型文档。固件归档和精确时代以 boards 最终收据为准；源码运行 SCG 的 authority 不冒充便携 EXE 的生成 authority。

推荐新生成的成对固件包为 `D:/python_software/SilverStar/dist/pf1117-boards-current/SSFC1_0_SSGS1_0_Current.zip`，183,633,025 bytes，SHA256 `740098e3be7fc6ccfac6f7487b75e10ff3f64d47eba8af073e50637950bfd8b1`。内含根目录工程、完整源、两配置 ELF/BIN/MAP/.su 和严格报告。解压到短路径后在 SCG 打开 `SSFC1_0_SSGS1_0.ssproject`，按自己的位置选择输出目录并正常生成。F103/E19 软件参考另在 `dist/pf1117-boards/F103_E19_Ground.zip`，SHA256 `e105dc8068549c68d38525ff358dd1b4e3260f06c9bab264b7a3f05e94ac6b48`。旧 O 包保留历史证明，与推荐 P 包分别标注。

Underline 包：`D:/python_software/Underline_RETLDC/dist/platform_finish_20261117/Underline_RETLDC_platform_finish_20261117_Windows_x64.zip`，SHA256 `fd187372111ebe2158f239dcc93f0200dace1ad95cc6bfa92a3dfd08e6f32a0c`。解压保留完整目录后启动 `Underline_RETLDC.exe`，或在源码根目录执行 `.venv/Scripts/python.exe main.py`。

TreeDiagram wheel：`D:/python_software/TreeDiagram/dist/platform_finish_20261117/treediagram_workbench-0.1.0-py3-none-any.whl`，SHA256 `543cf3e6b04ffa663aa4c1e237a28511c21b58ec2e1492e4b37d8f2393a78489`。用 Python 环境 `python -m pip install <该wheel完整路径>` 后执行 `treediagram`；现有源码环境可运行 `.venv/Scripts/treediagram.exe`。同目录 `validation` 保留本次输入、工程、运行与参数。

## 未完成项与准确边界

**软件/环境仍未完成：** 原生 OpenGL 显示根因与最终包的原生视觉复验。真实源程序既有成功呈现，也有上下文有效、GL error0 却得到白色原生抓屏的结果；当前 Computer Use helper 两次报已有活动请求，已退出，不继续占用鼠标。离屏、framebuffer 或一次成功不能证明白屏已修复。本轮没有凭猜测加入软件渲染兜底或调整系统驱动。完整观察与复现方法在显示报告。

最终便携包的完整鼠标流程、原生125%/150%布局、正常 GSHC 关闭和稳定负载下可比较的冷/热启动耗时尚未验收。已有 offscreen 与有限启动结果只覆盖表中范围。Windows 权限导致的一项符号链接测试仍是 skip；未调整权限或将 skip 记为 pass。

全固件所有第一方/第三方函数语义、任意别名/生命周期、所有库异常和所有支持构型的穷举审计仍为 **NOT PROVEN**。本轮已闭合的是表中有限合同和精确机器码构型。P10 继续原样输出 critical-contract review NOT PROVEN；严格栈只证明对应输入字节，不代表原始 Power of Ten、NASA 认证或可飞行资格。当前包尚无完整 GUI 操作验收的部分另在打包 smoke 收据逐项标注。

**硬件待测另列：** 板卡电源/封装/晶振/引脚与复用、DMA/cache/中断、任务 WCET 与实际栈高水位、UART 吞吐、LoRa 空口互通/前端电平/输出功率/天线与链路预算、存储满盘/断电与重启、传感器标定/安装方向/温漂/磁场干扰、导航和模型精度、真实发动机数据及飞行资格。本轮没有连接、烧写或触发硬件动作。静态余量和 Host 耗时不能替代这些证据。

## 清理与保留

Underline 已清理本轮 PyInstaller 中间文件 16 个、51,389,317 字节；TreeDiagram 已清理本轮独立 wheel 安装验证副本 113 个、1,531,813 字节，清单和结果在各仓本轮报告。

SilverStar 已清理当前任务清单里、与受保护正式归档成员相同路径/大小/SHA256 的编译副本 **9,145 个、831,475,551 字节**，无跳过。每个路径核对绝对边界及 reparse 状态，每个 ZIP 成员完整读取再计算 SHA；原生 PowerShell 逐文件删除，未递归删除未知目录。实际结果见 [清理执行](delivery/duplicate-build-cleanup.json)；独立后检确认这些文件全部不存在，而保留的 573 个唯一/报告文件共 72,689,122 字节及受保护归档 SHA 全部未变，见 [清理后检](delivery/duplicate-build-cleanup-verification.json)。受保护的 F407/E19 原 epoch 完整工程 ZIP、GUI 证据 ZIP、所有唯一编译物、原始日志/输入和新 current 工程均保留，归档不重新归因到别的源码版本。

同样规则完成本轮旧板型构建副本清理：**13,872 个、2,375,668,814 字节**，无跳过；独立后检保留的2,360个文件/726,476,848字节及两个保护ZIP/清单全部未变。仅涉及明确列出的 candidate-c 至 n 中间 build 与 own F103-c build，不含 O/P/D 当前交付或任何输入，见 [执行](delivery/board-duplicate-cleanup.json)及[后检](delivery/board-duplicate-cleanup-verification.json)。

在最终包逐成员校验与两轮完整打包日志保存后，另清理本轮失败半成品目录 `dist/pf1117` 和两次 PyInstaller build 中间目录，共 **3,329 个、986,808,625 字节**；正式 `dist/pf1117b`、所有原始许可证凭据包和证据保留。路径/文件哈希清单、执行和后检见 [结果](delivery/package-cleanup-result.json)。原 PowerShell 字节汇总对 ordered dictionary 输出null，原始收据保留，后检仅从删除前清单补正字节总数，没有改变实际删除项。SilverStar 本轮合计清理 **26,346 个文件、4,193,952,990 字节**。

原有 SilverStar `docs/evidence/astra_0_1_3_20261027/`、`docs/evidence/cleanup_20261028/`、三个 `work_*_20261006` 清单，以及 Underline 的 `docs/Repository_Showcase_Review_20261016.md` 均保留未跟踪状态。未碰未知旧 `.work`、用户工程/日志/解码包、旧 worktree、旧发布包或不可访问目录。仓库产物大小/类型门禁未扩大例外；大正式包留在 `dist`，Git 保留代码与可审阅文字证据。

## 提交与远端检查

SilverStar 源码已普通推送，远端 [artifact hygiene 检查](https://github.com/aleistercrowleybeast666/SilverStar/actions/runs/43924458667)成功。Underline 当前交付提交为 [dbc0b7e](https://github.com/aleistercrowleybeast666/Underline_RETLDC/commit/dbc0b7edddcceeda13aed2e7dee2f9d36d9964ef)，[远端检查](https://github.com/aleistercrowleybeast666/Underline_RETLDC/actions/runs/43913478358)成功；TreeDiagram 为 [c4b2915](https://github.com/aleistercrowleybeast666/TreeDiagram/commit/c4b2915c9408940a78f88ded2d74655521117636)，[远端检查](https://github.com/aleistercrowleybeast666/TreeDiagram/actions/runs/43913498588)成功。本报告与最终证据随后另作普通提交；实际远端 HEAD 在交付时再次核对。此 CI 只负责仓库产物门禁，不能替代上面的本地固件/GUI测试。
