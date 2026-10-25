# SilverStar SCG Architecture

Current application implementation: `apps/SCG`. The Python package and plugin IDs retain FCCG compatibility names. `docs/FCCG` and frozen evidence paths are historical namespaces; their recorded bytes and hashes are preserved.

The current development line is 0.1.3, with product identity read from root `VERSION`. The stable 0.1.2 release and its seven-page UI are historical baselines, not the current workspace structure. Exact accepted project identities are owned by `project/model.py` and `schemas/project.schema.json`.

## 当前配置与版本

现行开发版使用三个自由切换的配置工作区：硬件与通信、飞行流程、检查与生成。工程格式 14–23 保持各自兼容边界；共享功能编排字段 `mission_functions` 使用格式 23，阶段与已有安装扩展保持原身份。仅浏览旧工程不注入新字段或升级格式。产品版本不机械改写独立插件、协议、decoder 或已有用户工程身份。

状态估计、控制/动作、记录和遥测通过同页阶段详情配置，actual values、单位、representation 和 shared_key 仍由既有插件/参数解析层拥有。新 `silverstar.mission-functions/1` 保存唯一功能实例、输入输出引用及显式边界；多阶段仅显示同一实例的开始、持续和停止关系。参数仍保存在 `algorithm_parameters`，不复制到胶囊。

可精确映射到现有生命周期的适配保持原生成行为，包括系统准备、已接受 START 初始化与落地收尾。任意自定义阶段边界仍须明确标为参考编排，在缺少固件消费者时拒绝生成；不能移除旧 `mission_process_firmware_binding_unavailable` 来静默丢掉配置。GSHC/FLP 使用同一版本化声明读取，实际运行状态与原日志不能由桌面配置补造。

详细参数见[参数契约](ALGORITHM_PARAMETERS.md)，界面流程见[应用说明](APP_README.md)。



SCG 是 SilverStar 平台的中央配置、组件装配、接口冻结与版本权威。插件是声明式数据和源文件payload，固件运行期不加载插件。

## 1. 应用层
```text
PySide6 Hardware & Communication / Flight Workflow / Checks & Generation
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
Physical identity is `(vendor, model, chipset)`, independent of transport and
platform implementation. Transport/profile choices of one driver remain variants
within one component. The same physical hardware may have separate platform
implementations only when each has exactly one mandatory MCU/family dependency
whose match rules prove a finite, disjoint set of exact target parts. Exact parts
use the same canonical token function as runtime platform matching, so case and
separators cannot invent separate domains; empty canonical tokens are rejected. Catalog scan
rejects overlapping parts, broad rules and unproven platform domains before
publishing the catalog. Component IDs or renamed physical labels are not proof of
exclusivity; target dependency and source ownership checks still apply.

Physical Device Instance 与 plugin type 分离。一个物理设备可提供多个 Capability Endpoint；算法声明消费能力，不声明具体型号。只有至少两个物理实例能满足同一能力时，项目才保存显式source override；单一来源由解析器直接确定。官方JY901B、M9N、SX1281支持同插件最多4实例；driver state和资源必须实例隔离。

所有IMU/GNSS实例持续处理并可记录native数据；Canonical IMU在Calibration/Alignment前选择后锁定，GNSS可按基础liveness向后续备用单向切换。AIR只使用一个active telemetry，连续10次真实TX timeout才向后续备用切换，success清零，无备用继续周期有界重试。

## 3. Board / Custom CubeMX / MCU
- MCU不是Devices页选项；Board或导入的`.ioc`提供实际part/family/package/core，匹配MCU/Platform插件。
- Verified Board插件保存固定logical→physical mapping。`.ioc`和generated defines只验证physical alias，CubeMX scan order不得重排`PLATFORM_GPIO_*`等逻辑ID。
- Custom CubeMX由用户在Hardware Connection手动分配资源。
- HardwareWorkspacePage 统一挂载 Flight/Ground 两套独立编辑器；板卡和完整 CubeMX 目录导入在首屏，硬件快照、路径、资源和目标构建参数不跨目标混用。Ground 不参与生成时仍保留其完整配置。
- MCU/Platform插件拥有Target Profile、HAL/CMSIS policy、CPU/FPU、memory、backend和resource-render ABI。

## 阶段工作区与运行边界

FlightWorkflowPage 拥有阶段选择和同页协调；MissionProcessPanel 编辑有界顺序条件，FunctionBindingsEditor 编辑共享功能引用和范围。插件能力只来自已安装且版本匹配的显式声明/适配，不因添加卡片而获得新控制律、多个估计器实例或运行时热加载能力。一次性任务的“请求一次”与持续采样直到完成/失败分开；准备任务仍受系统准入，不能伪装成可绕过 READY/FAULT 的普通胶囊。

区间采用开始包含、停止不包含的显式边界。改名保留 ID；插入阶段按边界自然覆盖；倒序、空区间、缺失边界、输出冲突及依赖问题由模型校验报告。跨阶段不重新初始化状态、协方差或历史，不新建任意回调注册体系或 RTOS 任务。函数参数档 `.ssparameters` 只修改明确算法的实际输入，身份、版本、manifest 摘要、单位和表示均须匹配，不替换硬件或任务。

Logger 生命周期与记录功能区间不同：系统准备、必要诊断、START、尾段排空和最终关闭仍沿用现有消费者。当前普通记录策略继续使用 EVERY/DECIMATION/PERIODIC/EVENT/ONE_SHOT 原义；尚无固件消费者的自定义区间只可保存为参考草稿，不能声称已经过滤实际数据。详见[飞前日志](PREFLIGHT_LOGGING.md)。

## 4. Protocol slots
Telemetry、Maintenance、Logging是三个独立nullable槽。物理Device存在与协议是否启用相互独立；移除唯一transport会清空依赖协议，恢复Device不会偷偷重启协议。

## 5. Generation ownership
首次选择的组件payload复制进生成工程后归工程所有；普通Generate不覆盖。SCG只管理`Generated/`、project descriptor、build/editor metadata、`.ssdecoder`等明确表面。SourceGraph是Make/EIDE/VS Code唯一构建真相。

## 6. Safety
路径、插件ZIP、输出目录、staging、atomic replace、dangerous change、Board resource closure、stack report、Power of Ten、static analysis均为显式门禁。当前软件验证不等于硬件/飞行认证。

平台运行时规范见 `platform/`（历史或内部参考，不纳入公共说明的验收依据）。
