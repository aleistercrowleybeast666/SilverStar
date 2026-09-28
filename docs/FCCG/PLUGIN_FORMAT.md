# Plugin Format

## Algorithm actual parameters / 算法实际参数

新增独立算法参数页面（硬件连接之前），插件声明实际值、单位和 representation。
Project format 12；`.ssdecoder` / project-semantics 1.2，拒绝 decoder 1.1；
Platform 仍为 0.0.12，Record Catalog 与协议布局不变。
参数清单、生成绑定与 Recorded Configuration / Offline What-if 边界见[参数契约](ALGORITHM_PARAMETERS.md)。
精确验证结果仅见仓库根 VALIDATION.md。


插件是严格声明式manifest + payload，不执行安装包脚本。未知核心字段、非法路径、非法类别和ABI不匹配必须失败。

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
