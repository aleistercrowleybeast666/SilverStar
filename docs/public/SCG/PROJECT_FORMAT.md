# SilverStar Project Format

当前开发产品为 **0.1.3 development**，稳定发布仍为 **0.1.2**。当前原生工程身份为 **14 至 23**，以 `project/model.py` 的格式常量及 `schemas/project.schema.json` 为准。打开、显示或切换工作区不把旧文件机械改成最新格式；早期格式仅沿用已有的明确迁移路径。项目包括 Flight 配置、独立 `ground_target`、唯一 `air_link`、alignment、设备实例、算法实际参数及日志策略。

| 格式 | 扩展身份 |
|---|---|
| 14 | 基础双目标工程 |
| 15 / 16 | 地面无线实例 / 模块 variant |
| 17 | full、standard、compact、minimal 真实固件功能档及其预设 |
| 18 | 类型化 NIS 概率输入 |
| 19 | 原生 USB 引用 |
| 20 | 安装位置与明确基准；v1 结构基准和 v2 导航点分别保留原义 |
| 21 | 磁力计、维护导出等可选资源选择 |
| 22 | 桌面参考 `mission_process` 与原始 IMU 第二安装轴 |
| 23 | 可选 `mission_functions`：共享实例及有界范围绑定 |

详见[Target model](../shared/TARGET_MODEL.md)、[AIR Link](../shared/AIR_LINK.md)与[Device variants](../shared/DEVICE_VARIANTS.md)。当前 GUI 是硬件与通信、飞行流程、检查与生成三个自由切换工作区；状态估计、控制/动作及记录在飞行流程中编辑。

## 共享任务功能与实际消费者

没有 `mission_process` 或 `mission_functions` 的标准工程，只派生只读胶囊/功能展示，不写入这两个字段，也不改变功能档、算法、硬件、参数或生成资格。显式保存功能绑定时使用格式 23；原字段 `strategies`、`algorithm_parameters`、`modes`、`mode_parameters`、日志和 Ground 配置仍是对应消费者的配置权威。

`mission_functions` 为 `{schema_version:1, functions:[...]}`。每项有稳定 `instance_id`、`plugin_id`、分类、一次性/持续方式、开始/停止边界、依赖、输入引用和输出；参数不复制进卡片或每个阶段。阶段改名不更换引用，区间内插入阶段自然覆盖。缺失边界、倒序、重复实例/输出、不可用输入与依赖环作为可定位问题保留；草稿可保存，生成前拒绝。

数值阶段条件的输入由显式合同映射：`altitude_agl_m`、`vertical_velocity_mps` 使用已选择的 estimator 输出；未选择 estimator 时才使用 INS 输出。生产者必须在进入条件取样前可用，不能等待这个条件进入阶段后才启动。检查自等待环、输入缺失和上游范围覆盖；外部 `launch_detected` 等事件不按名称猜测来自估计器。一次参考快照的顺序是条件取样、至多一次阶段转换、停止区间、按依赖启动区间，再返回每个持续实例一次；不执行算法或硬件。

普通边界为 `system_prepare`、`mission_start`、`system_landed`、`lifecycle_end`；它们复用已有准备、已接受 START、LANDED 和收尾合同，不改变初始化。`stage_enter` 是显式阶段进入边界，区间包含开始、不包含停止。同一实例只保存一次。一次性任务是一次请求后等待实际插件完成/失败，不等于调用一次函数或自动显示物理完成。

声明目录为 `contracts/mission_functions_v1.json`。只有与现有生命周期和 canonical 输入/依赖精确一致的 adapter 绑定能生成；任意阶段区间、改变调度依赖和不同输入映射仍缺少固件消费者，明确报告参考编排并拒绝生成。旧 `mission_process_firmware_binding_unavailable` 拒绝保留，不吞掉自定义过程后生成旧行为。Ground-only 生成隔离 Flight 的过程、功能及安装元数据，顶层工程仍保留原草稿。

含 `mission_process` 的工程在“检查与生成”校验阶段即报告 `MISSION_PROCESS_REFERENCE_ONLY` 错误；编辑校验仅给警告，允许保存草稿。该提示不替代渲染器的最终拒绝，不能出现校验显示可生成、渲染时才发现缺少阶段消费者的假象。

日志功能引用原有 `logging_streams`，不创建第二份记录表。Logger 会话仍从启动准备，飞前 native/corrected 默认开关保持，关键记录及落地 drain/flush/finalize 不因普通卡片停止而删除。自定义日志区间尚无固件门控消费者，因此不以可编辑草稿宣称支持板端记录门控。

## 导出身份与参数文件

`.ssmission` v1/v2 保持原义；只有显式功能配置存在时导出 v3，包含 `functions` 和设备引用。`process` 仅在工程实际配置时出现，不因展示默认胶囊而补造。导出摘要包含声明式配置，GSHC/FLP 的共享解析器已支持 v3；配置声明与桌面参考 trace 均不等于板端 Recorded。

具体功能可导入/导出 `.ssparams` 参数 JSON，`.ssparameters` 是相同内容的兼容扩展名。合同为 `contracts/function_parameters_v1.json`：核对选中插件 ID、实现版本、manifest SHA-256、参数 schema、字段、单位、representation 和 float32/int32 类型，预览后事务性应用。它保留实际项目输入精度，通过既有 resolver 得到生成精度；共享参数使用原 `shared_key` 权威同步。未知旧参数的删除必须在预览中可见；只读参数不能通过文件绕过。

参数导入只更新所选参数 owner 及其真正共享参数，不替换硬件或任务流程。保存使用同目录临时文件、原子替换、上一版 `.bak` 和冲突/损坏保护；重复 JSON key、非有限数、超限和不兼容身份拒绝。该文件不是固件可执行代码、MCU 热加载 ABI，也不承诺尚未落实的 TreeDiagram 参数兼容。

默认来源依次为工程已存显式值、用户明确应用的配置/模板、适用插件默认；已有 `legacy_default` 按原契约保留。界面简洁不能调用功能档切换来覆盖用户参数或关闭记录。

## 历史：format 12/13

## Algorithm actual parameters / 算法实际参数

历史实现曾新增独立算法参数页面（硬件连接之前），插件声明实际值、单位和 representation；这不是当前三页导航结构。
Project format 12；`.ssdecoder` / project-semantics 1.2，拒绝 decoder 1.1；
Platform 仍为 0.0.12，Record Catalog 与协议布局不变。
参数清单、生成绑定与 Recorded Configuration / Offline What-if 边界见[参数契约](ALGORITHM_PARAMETERS.md)。
精确验证结果仅见仓库根 VALIDATION.md。


以下核心字段原属 Flight Controller；format 13 起保留其运行时 API 以保证原有 Flight 生成能力，format 14 延续该结构。

## 核心数据
- project identity：name、SilverStar firmware/platform version；
- MCU/Platform lock + `build.target_profile`派生锁；
- Board或Custom CubeMX hardware identity；
- Device instances；
- Strategies；
- Modes及参数；
- capability source overrides；
- three nullable protocol slots；
- logging policy；
- resource assignments；
- development environment；
- generation/readiness fingerprints。

## Calibration
`modes.calibration`合法：`[]`、`["OneFace"]`、`["SixFace"]`、`["OneFace","SixFace"]`。NONE不是GUI mode option，而是始终存在的SystemCalibration运行模式。空数组自动NONE/READY；非空build仍允许运行时选择NONE。

## Protocols
`telemetry/maintenance/logging`分别为协议锁对象或`null`。Device存在不强制启用协议。

## Target lock
`build.target_profile`必须与匹配MCU/Platform manifest完全一致；它是完整性锁，不是用户自由输入。

## Project Semantics
生成的Project Semantics记录physical devices、capability endpoints、initial canonical routes、protocol locks/bindings、algorithms/strategies/modes、logging和hardware identity。Runtime source change通过日志event表达。

## Shared algorithm-parameter invariant (format 12)

No shared map is added. Values remain under `algorithm_parameters[component_id][parameter_id]`; all selected declarations with one `shared_key` must be exactly equal or strict open/validation/generation fails with a shared-parameter mismatch. Reconciliation initializes a newly selected owner from an existing group value, but never repairs an existing conflict. Deselecting an owner prunes only its existing private component map.
