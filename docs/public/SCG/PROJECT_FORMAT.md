# SilverStar Project Format

### 历史地面站串口配置

格式 19 的原生 CDC 引用、旧 `ground_target.pc_interface=usb_cdc` 和带 CDC 生成源的硬件清单仅用于识别旧工程。打开这类工程会提示迁移，保存和生成会报告具体原因。选取地面站硬件属性，在“设备与接口”明确选择 UART 和实际串口资源，核对导入工程或板卡声明的波特率，再应用并保存。尚有 CDC 源时，请在单独位置准备普通 UART CubeMX 工程再导入。取消或 Esc 保留原文件。普通 PC 串口和 CH340 等外置 USB-UART 都通过该 UART 配置。

当前开发产品为 **0.1.3 development**，稳定发布仍为 **0.1.2**。当前工程格式为 **24**，兼容版本化迁移的旧格式，以 `project/model.py` 和 `schemas/project.schema.json` 为准。读取迁移作用于内存模型，原始文件在用户保存前保持不变。项目包括 Flight 配置、独立 `ground_target`、唯一 `air_link`、alignment、设备实例、算法实际参数及日志策略。

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
| 24 | 移除 Ground `enabled` 门控；由显式目标动作决定生成范围 |

详见[Target model](../shared/TARGET_MODEL.md)、[AIR Link](../shared/AIR_LINK.md)与[Device variants](../shared/DEVICE_VARIANTS.md)。当前 GUI 是硬件与通信、飞行流程、检查与生成三个自由切换工作区；状态估计、控制/动作及记录在飞行流程中编辑。

## 共享任务功能与实际消费者

新工程使用原生准备/上升默认流程，普通阶段卡片可以直接打开事务弹窗。没有显式流程的旧工程保留兼容入口；阶段编辑经校验后显式转换，浏览或取消不修改项目。原字段 `strategies`、`algorithm_parameters`、`modes`、`mode_parameters`、日志和 Ground 配置仍是对应消费者的参数权威。

`mission_functions` 为 `{schema_version:1, functions:[...]}`。每项有稳定 `instance_id`、`plugin_id`、分类、一次性/持续方式、开始/停止边界、依赖、输入引用和输出；参数不复制进卡片或每个阶段。阶段改名不更换引用，区间内插入阶段自然覆盖。缺失边界、倒序、重复实例/输出、不可用输入与依赖环作为可定位问题保留；校验失败保留草稿供修正，生成前拒绝。

数值阶段条件由版本化合同映射：高度、垂速使用已选择的导航输出，`acceleration_g` 使用经过校正的规范 IMU 比力模长。生产者必须在条件取样前可用，检查自等待、输入缺失、过期和上游范围覆盖。阶段名称不会产生事件；事件必须有真实生产者。原生调度每步最多转换一个阶段，执行退出/停止、转换、进入/启动的确定顺序。

普通边界为 `system_prepare`、`mission_start`、`system_landed`、`lifecycle_end`；它们复用已有准备、已接受 START、LANDED 和收尾合同，不改变初始化。`stage_enter` 是显式阶段进入边界，区间包含开始、不包含停止。同一实例只保存一次。一次性任务是一次请求后等待实际插件完成/失败，不等于调用一次函数或自动显示物理完成。

声明目录为 `contracts/mission_functions_v1.json` 和 `contracts/mission_process_v2.json`。合法原生阶段、功能区间、输入和依赖生成有界表并由实际固件消费者执行。输入来源修改通过唯一 capability authority 同步依赖功能；缺失插件、非法模式、冲突、环或未支持消费者在生成前拒绝。Ground-only 生成隔离 Flight 的过程、功能及安装元数据，顶层工程仍保留原草稿。

旧桌面参考流程不直接获得原生执行资格；必须显式迁移并通过当前合同与消费者校验。未知参考表达式和未支持事件继续明确拒绝，不能只改 execution 字符串或丢弃流程后生成旧行为。

日志功能引用原有 `logging_streams`。记录和遥测区间接入实际运行门控，支持合同允许的 INS/估计器依赖；无效或过期依赖暂停相应数据流。Logger 会话、关键身份/诊断和必要 drain/flush/finalize 保持各自 owner。默认不配置回收时，不隐式插入燃尽、滑行、开伞或落地停止，记录按配置持续到任务终止。

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
