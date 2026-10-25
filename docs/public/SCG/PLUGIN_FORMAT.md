# Plugin Format

当前 Device manifest 可声明 device_variants：一个真实芯片插件对应接口和运行 profile 的有限 overlay，物理芯片身份由公共 manifest 唯一声明。Radio Device 另声明物理频段、PHY 和模块 variant，详见[Device variants](../shared/DEVICE_VARIANTS.md)与[AIR Link](../shared/AIR_LINK.md)。以下 format 12 描述为历史上下文。

## 当前配置与版本

当前产品为 0.1.3 development，稳定发布仍为 0.1.2。SCG 当前原生格式 14 至 23 保持各自兼容边界，显式共享功能配置使用 23；decoder/project-semantics 容器合同仍沿用既有 1.2，不以 GUI 重构改写旧记录。算法参数在飞行流程的具体功能区编辑，保留 actual values、单位、representation、来源和共享参数约束。产品版本不机械改写独立插件、协议或已有用户工程身份。

详细参数见[参数契约](ALGORITHM_PARAMETERS.md)，界面流程见[应用说明](APP_README.md)。



插件是严格声明式manifest + payload，不执行安装包脚本。未知核心字段、非法路径、非法类别和ABI不匹配必须失败。

## 任务功能目录与后端支持

当前 `contracts/mission_functions_v1.json` 为已有插件提供显式 legacy adapter 声明，结合实际 PluginCatalog 产生用户可选目录。声明包括精确支持版本、一次性/持续方式、单实例限制、输入输出、准备/初始化和停止边界、完成含义、参数修改时机及支持范围。未声明或版本不匹配的插件不会仅凭显示名进入“可调度”目录。

此适配没有改写旧 manifest 或协议锁 SHA-256，也没有新增动态回调、任意脚本或 RTOS 任务。单实例插件仍只有一个实际参数 owner。各阶段引用同一实例和原有 `algorithm_parameters`；参数不会因为区间跨越多个阶段而复制或重复初始化。

已声明的 INS/估计器沿用已接受 START 的初始化事务及现有 LANDED gate；准备、校准/对准、输出服务、日志与遥测各保留原生命周期。校准卡片本身不启用未选择的校准模式。一次性任务必须等待明确的插件完成/失败报告，软件输出完成也不代表物理开伞确认。

任意 `stage_enter` 区间、改变 canonical 输入或依赖调度仅为参考编排，生成前明确拒绝；没有通过删除既有不支持错误来宣称固件已消费。日志自定义区间尚未实现普通流门控，Logger 会话、必需记录和收尾保持原义。当前目录不提供虚构的 PID/LQR 插件或示例增益。

## 功能参数交换

`.ssparams`（兼容 `.ssparameters`）是 `silverstar.function-parameters/1` 的声明式 JSON。导入要求精确 plugin ID/version、manifest SHA-256、`silverstar.algorithm-parameters/1.0`、完整字段、单位、representation 和存储类型；未知/不兼容字段不能静默忽略。内容先校验并预览，再通过原 Value_Resolve 与 shared_key 合同应用到唯一参数 owner，保留未编辑数值精度。仅构建时参数不会因放入功能卡片就成为飞行中可变参数。

`.ssmission` v3 在显式功能配置时保存同一份实例/范围声明，并继续支持旧 v1/v2 消费；`.ssdecoder` 由既有真实生成路径携带配置身份。上述文件都不是 MCU 代码加载格式，也未声明与未来 TreeDiagram 参数协议兼容。

## Types
Core、MCU/Platform、Board、Device、Algorithm、FlightLogic、OS、Protocol、HardwareConfigurationProvider、DevelopmentEnvironment。

## Device category
合法命名空间：`sensor.*`、`link.*`、`storage.*`、`actuator.*`、`indicator.*`。`sensor.imu`和`sensor.gnss`进入Primary Sensors，其余合法`sensor.*`进入Other Sensors；未知顶层namespace拒绝。

## Instance policy
`plugin_max`控制同plugin最大实例，`class_max`控制类别总实例。重复同型号还要求`same_plugin_multiple=true`和`multi_instance_ready=true`。多实例驱动必须context-safe并使用instance-aware resource binding。

## MCU/Platform
声明part/family匹配、Target Profile、CPU/FPU、memory、HAL/CMSIS source policy、backend maturity、resource binding ABI和CubeMX兼容范围。Target不是GUI用户项。

## Board
Verified Board保存固定logical→physical mapping、兼容MCU、`.ioc` snapshot、roles/provenance。普通Generate不按CubeMX scan order重排logical ID。

## Protocol
每个Protocol插件只拥有一个category：telemetry/maintenance/logging。Project槽可为null。Profile声明transport selection：single或显式ordered failover等。AIR M0的多radio候选不改变wire。

## Security
ZIP traversal、绝对路径、symlink、special file、case collision、超限文件、managed-path claim均拒绝。所有C symbol/path/token做严格校验。

## Shared algorithm parameters

An algorithm parameter may declare `shared_key`, matching `^[a-z][a-z0-9_.-]*$`. All catalog declarations for a key must have identical type, default, unit, representation, bounds, precision, and step; IDs and generated symbols may differ. Selected owners are displayed by `selection.ui_order`, then component ID, with owners lacking `selection` last. This is declarative FCCG configuration linkage, not an algorithm dispatch rule.

## Sensor Recommendation != Algorithm Constraint

A Device may publish `metadata.sensor_recommendations`, an array of objects with
`parameter_id`, finite numeric `value`, `unit`, `representation`, `source`, and
localized `description`. Example: JY901B `baro_std_m=1.5`, unit `m`, representation
`sigma`. This is advisory display/initialization/fallback data. It cannot overwrite
saved algorithm values, clamp them, reject a shared parameter group, or masquerade
as native per-sample variance. UI pairs a matching parameter ID/unit/representation
with the advisory label; its editor retains the algorithm's own legal bounds.

Algorithm `minimum`/`maximum` and `Value_Resolve` remain hard numeric domains. Actual
chip/protocol limits, C representability, necessary numerical invariants, static
history capacity and reviewed MCU budgets remain hard constraints with explicit
errors. A recommended sigma/rate/range/quality threshold is not a hardware guarantee.
If no native variance exists, mark it unavailable rather than synthesizing sigma²
from a recommendation. Real receiver hAcc/vAcc/sAcc uncertainty remains native data.

Builtin audit: JY901B barometer 5 m was an empirical recommendation previously
misrepresented as per-sample variance; it is now 1.5 m advisory and variance is
unavailable. The old KF setter's 1.5 m clamp is removed. JY901B process-acceleration
sigma and NEO-M9N recommended GNSS sigma floors already feed only descriptor/fallback
paths when no explicit algorithm override exists; they are now also visible advisory
metadata. Receiver-reported hAcc/vAcc/sAcc and the algorithm's configured dynamic
GNSS floor policy are retained. Actual transport rates, sensor ranges, qualification,
quality gates and existing GNSS recovery thresholds are unchanged.
