# SilverStar monorepo architecture

```text
SilverStar
├─ SCG  — declarative Flight and Ground target configuration and code generation
├─ GSHC — AIR M0 ground telemetry, commands, readiness and operator UI
└─ FLP  — immutable SSLOG log opening, exact decoder validation, replay and export
```

`apps/SCG`, `apps/GSHC` and `apps/FLP` retain their existing internal module names. The root launchers locate their applications; they contain no product logic. All use one Python environment and the root `VERSION` for product release identity.

`contracts/navigation_v1.json` is the one machine-readable navigation contract. SCG generation, GSHC navigation documentation and FLP replay share that authority. AIR M0, SSLOG 0.0, `.ssdecoder`, project semantics and navigation revision are separate compatibility identities and remain unchanged by the product release version.

Builtin plugins retain their own implementation versions. New generated firmware derives its product identity through the shared version resolver; existing requests and explicitly supported legacy migrations follow [version management](VERSION_MANAGEMENT.md). Generated firmware is an output in a user-selected project or ignored work area, never a long-term source directory here. User logs and decoder packages are immutable inputs. Application-local implementation details remain owned by each application; explicit cross-component work can update all three.

SCG now places Flight Controller and optional Ground Station firmware in one project. Both share [AIR Link](AIR_LINK.md); Ground remains an opaque AIR packet bridge to GSHC's GSP serial stream. [Target model](TARGET_MODEL.md), [Ground Station](GROUND_STATION.md), and [Device variants](DEVICE_VARIANTS.md) define the second-round boundary. Simulator and device automatic initialization remain future work.

## 飞行配置首批（2026-10-24，已实现）

基线先保存为 `54baba43`，随后实现本节功能。首批沿用已有的固定生命周期和策略编辑器：阶段规则参数仍保存于原生 `.ssproject` 的 `modes` / `mode_parameters`，经现有生成器进入 C 宏；连续 INS/估计任务与阶段规则分开展示。没有新增任意状态图、按状态执行脚本或新的执行器控制。

- **SCG 飞行配置页**：增加任务周期摘要与导出按钮。已提交但尚在事件队列中的编辑先合入，再保存 `.ssmission`；原生工程重开保持同一模型。导出是声明式配置快照，不是设备下载命令。
- **GSHC 后期处理页**：可离线打开 `.ssmission`，显示工程名、摘要和未核对设备的状态；错误或取消保留已有内容。文件读取不改遥测状态、READY、START 或连接权限。
- **FLP 概览页**：从精确打开的 `.ssdecoder` 工程语义 `metadata_declarations.mission_profile` 读取并校验；旧日志明确显示未声明。配置不兼容时拒绝该配置，原始记录仍按其精确 decoder 阅读；不从旁边工程猜测配置。

格式权威为 [mission_profile_v1.json](../../../contracts/mission_profile_v1.json)，[golden 样例](../../../contracts/mission_profile_v1.golden.json)来自 SCG 合成测试工程，未经过飞行调参。通用校验/持久化代码在 `tools/silverstar_mission_profile.py`；版本登记于 `versions.json` 的 `mission.profile`。

| 字段 | 语义 |
|---|---|
| `schema_id` / `schema_version` | `silverstar.mission-profile/1` / 整数 1；与产品版本独立 |
| `project` | 工程名、请求的固件版本、生成器版本及声明的 MCU/板卡 |
| `frame` | ENU；MCU 单调微秒；任务时间从已接受 START 起算，不代表物理起飞检测 |
| `lifecycle` | 固定参考模板及与实际 C enum 对应的 0..8 稳定状态 ID |
| `rules` | 现有策略 owner/版本、选项、启用标志、实际声明的参数、单位、范围、生成符号和比例；首版支持当前多触发策略 0.1.0 的三个选项 |
| `continuous` | INS/估计器/着陆策略身份与日志流配置；尚不包含任意任务频率编辑或完整导航参数包 |
| `qualification` | 固定为设备绑定未验证、未做硬件测试；不能在文件中自行改为通过 |
| `sha256` | 去除此字段后，键排序、紧凑分隔、UTF-8、保留 Unicode 的 JSON SHA-256；不依赖界面语言或机器路径 |

参数是 SCG 声明值；C 的比例转换/存储仍由现有生成器执行。快照随新 decoder 进入其精确语义摘要，但不替代 ELF、`.ssdiag` 或实际固件身份。GSHC 的在线配置摘要协商、完整状态事件扩展、从快照反向应用工程及自定义生命周期留待后续。

读取拒绝未知字段/版本、重复 JSON key、非有限数、错误单位/映射、越界值、错误坐标与摘要；限 1 MiB。保存先校验，同目录临时文件后原子替换；显式覆盖只接受有效旧文件，并保留 `.bak`，失败保留当前好文件。数据不携带可执行脚本。

```powershell
.\.venv\Scripts\python.exe -B tools/export_mission_profile.py apps/SCG/tests/fixtures/radio_handshake.ssproject .work/mission_demo.ssmission
.\.venv\Scripts\python.exe -B tools/silverstar_mission_profile.py .work/mission_demo.ssmission
# 需要覆盖有效旧快照时，导出命令显式加 --replace
```

最终离线回归入口 `tools/verify_navigation_baseline.py` 共 9 组，**744 passed，另 3 subtests passed**。包含三端配置读取、原生工程重开、参数到 C 宏/decoder 的一致性、GUI 导出/取消、中英文/主题，以及实际生成后的六个 Host 调度场景。修正了该场景旧 UART Host 声明和私有测试句柄；未更改固件 UART 校验。完整命令/哈希/JUnit 在 `.work/ss013_20261024_final/`，界面检查图在 `.work/b013_20261024_02/mission_scg.png`、`mission_gshc.png`；未制作安装包或操作硬件。

## 任务周期设计全景（2026-10-24，后续项）

本节保留完整设计方向。首批已实现的固定模板摘要与配置追溯见上节；其余状态可配置性和运行行为尚待后续批次，不以加入主动控制为前提。

“任务周期”需要区分任务流程和执行周期：前者是从启动到飞后回收的生命周期，后者是采样、估计、记录、遥测的调度频率。两者有关联，但不能用一次状态切换隐式改变滤波器的时间步长。

### 分层与配置范围

| 层次 | 职责 | 建议首版配置边界 |
|---|---|---|
| 固件生命周期 | 保留现有 BOOT / SELF_TEST / PREFLIGHT / READY / FLIGHT / RECOVERY / LANDED / POSTFLIGHT / FAULT 及已有准入语义 | 固定稳定 ID；启动、自检、故障、维护锁定等核心约束不开放任意重写 |
| 飞行阶段 | 在既有生命周期内部表达物理阶段 | 从受支持模板选择阶段和检测参数；不直接把所有生命周期枚举改成任意图 |
| 事件检测 | 从带时间、有效性、来源的测量/估计产生候选事件 | 单位、有效性门槛、迟滞、持续时间、缺测策略、优先级和重复事件策略显式配置 |
| 阶段规则 | 处理进入、退出、超时及一次性任务 | 首版只引用已实现且有明确结果合同的行为；请求、接受、完成、失败分别记录 |
| 连续任务 | 采样、估计、健康检查、记录、遥测持续运行 | 独立配置频率与资源预算；阶段只选择经验证的运行档位，不重置估计状态 |
| 动作准入 | 管理命令来源、能力、互锁与执行权限 | 与事件、显示及 ACK 分开；未实现的输出能力不能靠配置获得 |

SCG 可设置“任务流程”和“采样与调度”两个配置区。前者显示阶段、事件条件、行为和数据依赖；后者复用现有采样/时序规划并检查总负载与传感器可用性。状态估计使用真实测量时间和明确的延迟合同，不能拿 GUI 刷新周期、遥测到达时间或配置中的名义周期代替。

### 配置如何到达 GSHC 与 FLP

建议 SCG 项目保存声明式 `mission_profile`，拥有独立的 schema 版本、稳定的阶段/事件/行为 ID、单位、依赖、来源和内容摘要。它是未来字段提案，不是当前可导入格式。生成时编译成有界静态配置，同时把同一配置和摘要纳入工程语义/decoder；不携带可执行脚本。首版采用重新生成固件的静态配置，不先开放运行时任意上传规则。

配置描述预期行为，固件运行记录描述实际行为，两者不能互相替代：

| 消费者 | 配置来源 | 实际状态来源 | 不匹配/旧版本处理 |
|---|---|---|---|
| GSHC | 导入与设备身份匹配的任务配置，核对固件报告的 profile 摘要 | 固件发布的生命周期/阶段快照及事件；带 boot/session、递增序号、单调时间、原因和质量 | 无匹配配置时显示原始 ID/未知；序号缺口明确提示，重连用快照恢复当前状态，不补造漏失事件 |
| FLP | 精确 `.ssdecoder` 的 Descriptor 与工程语义，继续走 LogOpenCoordinator | 原始 SSLOG 中实际记录的状态转换、触发依据、请求与结果 | 旧日志仅展示其原有信息；离线推导归入 Derived/What-if，不能回填为 Recorded |

新增数据需要单独版本化的协议扩展及能力协商；不能在现有 AIR M0 固定帧尾部直接追加字段。Ground 继续转发不解释的 AIR 数据，并验证传输容量；GSHC 的绘图/轮询频率不改变飞控任务周期。记录 schema、任务 profile、算法版本、固件构建身份分别管理，不用一个产品版本号代替全部兼容判断。

START 是否进入任务、开始记录、建立原点或触发其他行为，应逐项沿用和核对现有实现，不能把它重新解释为自动发射或所有动作的一键许可。落地巡回属于 LANDED / POSTFLIGHT 的通信与找回策略，可独立设计定位新鲜度、最后接收位置、低功耗通信、离线地图与声光提示；地面站/移动端不能以连接断开自行认定落地。

### 未来实现的最小顺序

1. 冻结输入/时间/质量、事件和配置身份合同，选一个兼容现有生命周期的只读模板。
2. SCG 校验与生成、配置回读和精确摘要验证；先闭合采样/估计/日志的追溯链路。
3. 固件记录事件与结果，GSHC 展示、FLP 原样重放；再开放有限的阶段行为配置。
4. 验证缺测、乱序/重复事件、重启、重连、未知版本、配置不匹配、取消与失败状态；完成后才讨论更复杂流程。

首批完成固定模板下的配置快照和三端读取；未修改现有状态机。移动端、Underline 和 TreeDiagram 以后消费同一版本化合同，避免各自定义第二套状态权威。
