# SilverStar Project Format

## Algorithm actual parameters / 算法实际参数

新增独立算法参数页面（硬件连接之前），插件声明实际值、单位和 representation。
Project format 12；`.ssdecoder` / project-semantics 1.2，拒绝 decoder 1.1；
Platform 仍为 0.0.12，Record Catalog 与协议布局不变。
参数清单、生成绑定与 Recorded Configuration / Offline What-if 边界见[参数契约](ALGORITHM_PARAMETERS.md)。
精确验证结果仅见仓库根 VALIDATION.md。


当前工程格式：**12**。

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
