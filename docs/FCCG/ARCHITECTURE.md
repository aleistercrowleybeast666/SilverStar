# SilverStar_FCCG Architecture

## Algorithm actual parameters / 算法实际参数

新增独立算法参数页面（硬件连接之前），插件声明实际值、单位和 representation。
Project format 12；`.ssdecoder` / project-semantics 1.2，拒绝 decoder 1.1；
Platform 仍为 0.0.12，Record Catalog 与协议布局不变。
参数清单、生成绑定与 Recorded Configuration / Offline What-if 边界见[参数契约](ALGORITHM_PARAMETERS.md)。
精确验证结果仅见仓库根 VALIDATION.md。


FCCG 是 SilverStar 平台的中央配置、组件装配、接口冻结与版本权威。插件是声明式数据和源文件payload，固件运行期不加载插件。

## 1. 应用层
```text
PySide6 Devices / Flight Configuration / Algorithm Parameters / Hardware Connection / Build
        ↓
FccgService
        ├─ Project model + validation
        ├─ plugin catalog + safe installer
        ├─ CubeMX/Board hardware resolver
        ├─ capability / protocol / resource resolver
        ├─ SourceGraph + renderers
        └─ guarded build/validation runner
        ↓
WorkspacePolicy + atomic staging
```

## 2. Device / Capability / Canonical Source
Physical Device Instance 与 plugin type 分离。一个物理设备可提供多个 Capability Endpoint；算法声明消费能力，不声明具体型号。只有至少两个物理实例能满足同一能力时，项目才保存显式source override；单一来源由解析器直接确定。官方JY901B、M9N、SX1281支持同插件最多4实例；driver state和资源必须实例隔离。

所有IMU/GNSS实例持续处理并可记录native数据；Canonical IMU在Calibration/Alignment前选择后锁定，GNSS可按基础liveness向后续备用单向切换。AIR只使用一个active telemetry，连续10次真实TX timeout才向后续备用切换，success清零，无备用继续周期有界重试。

## 3. Board / Custom CubeMX / MCU
- MCU不是Devices页选项；Board或导入的`.ioc`提供实际part/family/package/core，匹配MCU/Platform插件。
- Verified Board插件保存固定logical→physical mapping。`.ioc`和generated defines只验证physical alias，CubeMX scan order不得重排`PLATFORM_GPIO_*`等逻辑ID。
- Custom CubeMX由用户在Hardware Connection手动分配资源。
- MCU/Platform插件拥有Target Profile、HAL/CMSIS policy、CPU/FPU、memory、backend和resource-render ABI。

## 4. Protocol slots
Telemetry、Maintenance、Logging是三个独立nullable槽。物理Device存在与协议是否启用相互独立；移除唯一transport会清空依赖协议，恢复Device不会偷偷重启协议。

## 5. Generation ownership
首次选择的组件payload复制进生成工程后归工程所有；普通Generate不覆盖。FCCG只管理`Generated/`、project descriptor、build/editor metadata、`.ssdecoder`等明确表面。SourceGraph是Make/EIDE/VS Code唯一构建真相。

## 6. Safety
路径、插件ZIP、输出目录、staging、atomic replace、dangerous change、Board resource closure、stack report、Power of Ten、static analysis均为显式门禁。当前软件验证不等于硬件/飞行认证。

平台运行时规范见 [`platform/`](platform/)。
