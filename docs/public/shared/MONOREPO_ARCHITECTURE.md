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

基线先保存为 `54baba43`，随后实现本节功能，配置快照基础保存为 `c5a73382`。首批沿用已有的固定生命周期和策略语义：阶段规则参数仍保存于原生 `.ssproject` 的 `modes` / `mode_parameters`，经现有生成器进入 C 宏；连续 INS/估计任务与阶段规则分开展示。没有新增任意状态图、按状态执行脚本或新的执行器控制。

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

配置快照基础的离线回归入口 `tools/verify_navigation_baseline.py` 共 9 组，**744 passed，另 3 subtests passed**。包含三端配置读取、原生工程重开、参数到 C 宏/decoder 的一致性、GUI 导出/取消、中英文/主题，以及实际生成后的六个 Host 调度场景。修正了该场景旧 UART Host 声明和私有测试句柄；未更改固件 UART 校验。完整命令/哈希/JUnit 在 `.work/ss013_20261024_final/`，界面检查图在 `.work/b013_20261024_02/mission_scg.png`、`mission_gshc.png`；未制作安装包或操作硬件。

### 任务阶段胶囊与执行记录（2026-10-24）

当前胶囊表示**任务阶段**。可创建无控任务参考模板，在任意阶段前插入自定义阶段、调整顺序、修改名称和删除；稳定 `stage_id` 不依赖显示名或列表位置。胶囊内编辑名称，详情弹窗设置进入条件、持续确认、动作类型和设备实例引用。已有固件的三个部署触发条件恢复普通参数控件，不再作为任务阶段胶囊。

参考模板默认覆盖就绪、任务开始、动力上升、滑行、开伞请求、下降、落地，共七阶段，不默认加入预开伞和找回。开伞请求直接等待明确的越顶确认；用户仍可手动插入这些阶段，旧工程中的自定义阶段不自动删除。START 与实际起飞默认分开；可显式选择合并，模板将上升阶段条件改为已接受 START。自定义阶段不重写 BOOT、自检、READY、故障和维护互锁。当前只支持有界的顺序阶段（最多 32 个），每阶段一个进入条件；AND/OR 组合条件、分支、并发和循环尚未实现，不执行用户脚本或表达式。

本批实现范围是**桌面编排、持久化、校验和参考解释执行**。原生工程格式 22 保存 `mission_process`；未使用此字段的旧工程不自动升级。含流程的 `.ssmission` 使用 v2，携带实际阶段、设备引用和完整摘要；v1 仍可读取并保持原义。规范入口为 `contracts/mission_process_v1.json`、`mission_profile_v2.json` 和共享 `tools/silverstar_mission_process.py`。

解释器每个严格递增采样时刻最多进入一个阶段；缺测、无效输入或超限采样间隔会打断连续确认。事件由明确的输入生产者提供；解释器不会因阶段名称或 GUI 参数而捏造起飞、燃尽、越顶或开伞结果。动作只记录为 `simulated_action_request`，不会向设备发送指令，更不会自动标成执行完成。

**新增阶段尚未绑定固件执行。** 保存、重开、导出和参考回放可用，但带自定义流程的 C 生成明确报 `mission_process_firmware_binding_unavailable`，防止表面配置成功而固件仍执行旧流程。原有工程的固件生成保持原路径。删除自定义流程会显式恢复原固件配置；本批未声称完整无控任务已能在板端按新流程执行。

#### GSHC 与 FLP 如何知道过程

配置和实际过程分开：配置描述预期阶段，运行事件描述实际发生了什么。

| 消费者 | 本批可用 | 固件接入时的要求 |
|---|---|---|
| GSHC | 离线打开 `.ssmission` 显示阶段；可读取摘要匹配的 `.ssmissiontrace` 桌面参考记录，不改变实时状态、READY 或命令权限 | 设备主动报告匹配的 profile 摘要、boot/session、状态快照和递增事件序号；阶段 ID 在该 profile 中解析。配置不匹配、缺帧和未知 ID 明确显示，不按 GUI 时间推演状态 |
| FLP | 从精确 `.ssdecoder` 读取流程声明；可打开同一摘要的桌面参考 trace，并明确标为非板端 Recorded | 新 SSLOG 阶段记录通过既有 LogOpenCoordinator 精确解析，记录切换原因、时间、有效性以及动作请求/接受/完成/失败。旧日志未记录的阶段保持缺失；推导结果只能是 Derived |
| Ground | 当前无线转发合同不变 | 新事件采用独立版本消息/记录和能力协商；核对载荷上限及带宽，不能直接在 AIR M0 固定帧后追加字段 |

后续应先把有界阶段解释器接到现有 FlightLogic owner：事件检测产生候选事件，阶段层决定阶段切换和动作请求，原动作服务继续拥有准入与执行。准备阶段可以等待或记录，但不能绕过原生命周期许可。一次性动作必须区分请求、被接受、输出完成和物理结果；GPIO 脉冲完成不等于确认降落伞已展开。连续 INS/估计、采样、记录和遥测不随阶段任意重置。

完整无控任务的下一步验收是：同一配置在 Host 与生成固件中解释一致，缺测/重复/乱序/超时/重启/故障路径闭合；事件进入 SSLOG 与版本化遥测；GSHC 展示实际快照，FLP 原样回放。H7 板级时序、资源、电气输出与实际飞行仍按硬件清单补测。

#### 三页工作区与共享功能（2026-10-25，已实现）

现行主导航是“硬件与通信、飞行流程、检查与生成”。第一页同时显示 Flight/Ground 的板卡选择和完整 CubeMX 导入，两端资源独立，空地链路使用唯一权威配置。第二页左侧为阶段胶囊、右侧为四组同页详情；小窗口上下排列，进入条件细项和参数默认折叠。第三页提供双目标命令和可定位的问题列表，后台生成、构建与取消继续使用真实进度。旧七页控件作为唯一编辑器适配层挂载，不再作为主导航。

没有自定义流程的标准工程只派生展示模型。显式 `mission_functions` 使用原生格式 23，`.ssmission` v3 携带同一绑定；参数仍只保存在原 `algorithm_parameters`/shared_key 权威中。功能区间使用稳定 stage_id，开始包含、停止不包含；删除边界保留缺失引用并报告，绝不自动改绑。共享参考运行器按同一采样快照处理停止、启动、运行，一次性任务等待明确完成/失败；它不是新增的板端调度器。

状态估计与控制应分层。惯导传播和估计器状态连续运行，阶段切换不隐式复位；阶段只选择具备切换合同的配置档。更换不同维数的估计器、修改状态定义或仅构建时参数，必须有明确的初始化/状态迁移规则，不能因 GUI 允许选择就声称支持运行中切换。控制档描述启用时段、目标和已有执行器能力；开伞等一次性事件动作与连续闭环控制分开，仍经过原动作准入及生命周期互锁。

当前 GSHC 通过手动导入 SCG 的 `.ssmission` 获得离线声明，入口明确为“导出任务配置给 GSHC”，摘要默认折叠。后续可由固件报告配置摘要、固件身份、会话与实际阶段 ID，GSHC 再匹配本地配置。任务列展示的计划配置与实时过程各有来源和时间，不能按地面端计时自动推进。FLP 继续以精确 decoder 和原始记录为准。本次没有实现运行中算法切换、任意阶段固件调度或新 AIR/SSLOG 协议。

精确匹配既有系统生命周期的适配能等价生成；自定义流程与新阶段边界会在生成校验中明确拒绝，编辑校验允许参考草稿保存。记录/遥测范围保持实际系统生命周期并只读展示，记录内容和抽取仍在唯一“任务记录”卡编辑，既不停止采样/估计，也不绕过落地排空收尾。`.ssparams` 参数档核对实际插件版本、manifest 摘要、参数 schema、单位和类型，预览后只修改 canonical 参数，不导入可执行代码。标准生成样例、GUI 与实际 ARM 构建见[本次证据](VERSIONS_AND_EVIDENCE.md)。

#### 设备页分工

飞控设备页拥有实体及能力；硬件页统一分配 GPIO/PWM 等通道；任务阶段通过稳定实例 ID 引用设备。卡片建议显示名称、输出类型、用途、通道和可用性，详情弹窗编辑真实已实现参数。“开伞”是用途，GPIO/PWM 是实现类型。当前已有 GPIO 逻辑设备和平台 PWM，独立舵机设备的参数、生成与执行链路仍需实现，不以占位入口代替。

参考 Altus Metrum 的公开手册：其核心飞行状态由固件跟踪，输出通道可配置条件，多个已启用条件共同约束该通道。SilverStar 的可插入阶段是本项目扩展，不宣称 AltOS 本身提供任意生命周期编辑器。[Altus Metrum 官方手册](https://altusmetrum.org/AltOS/doc/altusmetrum.html)

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
