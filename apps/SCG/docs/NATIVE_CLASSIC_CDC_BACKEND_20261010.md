# 原生 classic CDC Ground 后端接线交付（2026-10-10）

用户已选择“完整 CubeMX CDC 工程导入的通用后端”，无需再次选择两种 profile 与通用入口。本批建立可扩展的后端 import→facts/项目模型→native renderer→ARM/analyzer→receipt 链路；当前实际支持仍限已验证 F103/F407 配置，其他设备/源码/配置明确拒绝。正式生成继续受保护，GUI 没有接线或改动。

新增源码提交：`348784a35ac164dec2a8b0f2b113d7d4fa55e87b`。父提交是证据基线 `9b9a20be2829dcc5135c648f6dc84b6e9af60316`；既有源码基线 `9f115f087f12868dd8a5384ca0b1e78edace63e0`、更早 CPU/IRQ 修复及其证据均保留。没有修改 firmware generator templates、插件 C payload、原生 vendor 输入或既有 9f/9b 证据文件。

## 本批新增实现

- `FccgService.NativeClassicCdcGroundProject_Import` 对完整原生输入先检查真实 source/config 和当前 Ground radio/protocol/LED 条件，再冻结导入；返回复制的项目模型，原调用方模型保留。Ground 不选择 MCU/Board 后端插件，由原生工程和独立 facts 拥有 CPU/资源/启动/时钟/中断。
- `native_ground_backend` binding 持久化 profile、HCLK、snapshot digest、独立 facts 摘要、SPI/GPIO 角色。实际角色同时写入 Ground `resource_assignments`。现有 `ProjectRoot_Save` 保存配置目录；`ProjectModel_Load` 和新的 service 实例可重载该配置。
- 每次候选 Plan/Export/Build 都重新提供可信 `NativeDeviceFacts` 并检查 snapshot、canonical contract、项目 proof、源图、资源与 facts/profile 一致性。项目中的 metadata、risk checkbox 或 `formal_generation` 字段不能授予放行。
- `NativeClassicCdcGroundCandidate_Plan` 使用真实 renderer 在内存中生成预览；`..._Export` 仅写入新的隔离目录并给出 `RENDERED_NOT_COMPILED` 回执；现存输出和用户编辑不被覆盖。导出后再次检查源快照与模型。
- `NativeClassicCdcGroundCandidate_Build` 要求传入模型与已保存项目完全相同，重新验证可信绑定，调用共享 `build/native_compile.py`，不启动 CLI 子进程。失败输出有明确回执；成功需实际编译状态、候选 scope 和模型 SHA 一致，再核对快照和保存模型没有变化。输出归属 token 防止把未拥有的并发占用目录当作本次失败产物改写。
- 原验证 CLI 变为共享编译引擎的薄入口，保留参数。原 ARM CPP/GAS/实际对象/ELF CPU/FPU/ABI、独立 IRQn/vector、闭包、源 owner、物理区间、warning/analyzer 检查保留。
- 普通 `GenerationPlan_Create/Apply`、`Project_EnsureBuildable`、`Build_Run` 增加明确 native 保护，覆盖 `ensure_buildable=False`；`GroundFiles_Render` 原拒绝保持原样。普通 `ProjectRoot_Save` 只保存配置，允许绑定模型持久化。

旧 `Build_Run(ensure_buildable=False)` 触达 runner 的普通旁路用不执行命令的 runner 复现；新版本直接返回 `error.native_formal_generation_blocked`。这个复现没有执行构建配方、板级代码或硬件操作。

## 验证与版本对应

新增完整后端 suite：**28 passed，0 skipped，233.59s**，包含两个真实 ARM/analyzer 流程。另行旧静态导入/模型重载与构建工具回归 **11 passed**。二者各有 1 个 pytest `cache_dir` 配置 warning，均非编译 warning。没有把两套测试拼为未执行的单一 suite，也没有重跑整套旧 154 项并冒称新版本通过该全套。

| 新 backend 构建 | F103 | F407 |
|---|---:|---:|
| 原生配置 | F103C8T6 / SysTick / 72MHz | F407VET6 / TIM1 / 168MHz / indexed CDC |
| 实际 ARM/analyzer 命令 | 333 | 387 |
| C / startup ASM | 53 / 1 | 62 / 1 |
| compiler warning | 0 | 0 |
| generated 哈希核对 | 114 | 124 |
| artifact 哈希核对 | 545 | 635 |
| 独立 SDK IRQ 枚举 | 52 | 89（含最后无逗号的 FPU_IRQn=81） |
| architecture / Host / artifact / emitted PoT | 全部 exit 0 | 全部 exit 0 |

两个 fresh 输出均从不存在的独立目录开始，经保存/重载后的 bound model 调用后端产生；不是拷贝旧二进制。normal/analyzer ELF 字节分别与先前 14e 相同，支持“只补工程接线，固件行为未增加改动”的边界判断。F103 ELF SHA256 `daf2a00ba8d22023c11a1c39b3ed2194bd64f3f41c7f907c63f76b4505538a4a`；F407 `5a9414e97a5e7f3f02d2e001266145304b711c600c16639e05e7e7a79aa44bf8`。

两种实际构建及 28 项 suite 在基于 9b9a20b 的 auditable dirty snapshot 上执行。每个构建捕获 45 个模块，已逐一核对 raw working SHA、嵌入源码及规范化 Git blobs 与 348784a 一致；后续文档/证据提交不宣称重新构建。原输入与独立 SDK header 再次做哈希和完整 IRQ 枚举核对。

父线程已独立通过 **9f/9b 普通功能范围**，无新 P1/P2；此结论不覆盖新 348784a 后端接线。其证据对象集合为旧 manifest 的 **1338 项**；作者 **1339 blobs** 包含这 1338 项及 verification.json 自身，两者口径不相加。新后端清单独立列出，不能混用旧计数。

第一次新增测试尝试 `nb01` 因 pytest/Python 3.14 在受限 Windows 下创建 mode0700 目录而发生 setup/清理失败，输出还存在日志编码异常；没有功能 PASS。随后采用既有仅测试用的继承 ACL 目录创建插件与 UTF-8 日志，在新目录 `nb02/nb03` 完成；没有修改任何目录权限。中间失败和最终结果均保留。

## 后端使用边界

调用方必须已有明确的单 bare SX1281/M12 Ground 配置（enabled、usb_cdc、无额外 LED/RTOS），并从可信后端 descriptor 提供独立 facts。不能以用户工程自己的 IOC/linker/header 或项目 metadata 自证 facts。示意调用：

```python
imported = service.NativeClassicCdcGroundProject_Import(
    native_input, configured_model, device_facts=trusted_facts,
    spi_resource="SPI1", gpio_resources=(nss, "RADIO_RST", "RADIO_BUSY", "RADIO_DIO1"),
    hclk_hz=reviewed_hclk, risk_acknowledged=True,
)
service.ProjectRoot_Save(imported.model, new_config_root, create_new=True)
loaded = ProjectModel_Load(new_config_root / "SilverStar.ssproject")
plan = service.NativeClassicCdcGroundCandidate_Plan(loaded, device_facts=trusted_facts)
# 可选：导出到新的预览目录，只返回 RENDERED_NOT_COMPILED。
preview = service.NativeClassicCdcGroundCandidate_Export(
    loaded, new_preview_output, device_facts=trusted_facts,
)
built = service.NativeClassicCdcGroundCandidate_Build(
    loaded, new_config_root, new_build_output, device_facts=trusted_facts,
)
# 检查 built.result；CompiledCandidate 仍不是正式生成/发布或硬件资格。
```

快照由同一 backend workspace 的 immutable import cache 管理；切换 workspace 或失去该 cache 会明确拒绝，须显式重新导入并核对事实，而不会回退至 legacy MCU 生成器。build/preview 输出必须新建，build 输出与保存项目、cache 互不包含。既有 native-only static import API 保持兼容。

## 09:00 可引用兼容矩阵及剩余缺口

| 对象 | 本批后端能力 | 正式交付边界 |
|---|---|---|
| F103 私有 | 可信完整导入、绑定/持久化/重载、实际候选 renderer、保存模型到 ARM/analyzer/receipt 的后端流程已执行 | 已知 F103C8T6/SysTick source/config；正式入口仍 BLOCKED；未上板 |
| F407 私有 | 上述流程已执行；复用既有 TIM1/indexed CDC 完整正常 Ground 数据路径 | 已知 F407VET6/TIM1 source/config；正式入口仍 BLOCKED；未上板 |
| C071 另线 | 本批无新实现/构建/集成；保持 b66 精确版本 | 独立安全审查被平台机制中止，无 outcome；不能标已审/放行其依赖 |
| 未知 STM32/不同 source/config | 扩展用后端接线结构已建立；当前没有其适配或构建支持 | 在 profile/真实 source/config 检查处明确拒绝；不能声称大多数 STM32 已支持 |

剩余三类必须区分：

1. **实现/软件验收缺口**：现已完成 backend API 到隔离候选的闭环；正式 Generate/Build 的受控放行与项目 readiness/product 入口尚未开放，GUI 接入本批不做。其他 MCU、不同 native source/config/时钟/USB ABI 和可信 facts provider 覆盖仍未实现。完整 EP0/control/reset/config/deinit/cancel/异步所有权契约、critical-contract、library/indirect-call/recursion 与 MSP/ISR 嵌套栈仍未完成验收。
2. **独审受阻**：b66 的平台中止没有审查结果，没有重试、绕过或集成。父线程的 9f/9b 普通独审不改变该状态，也不能覆盖完整生命周期/栈/WCET。新后端接线亦不冒称已经独立审过。
3. **仅缺硬件证据**：真实 USB 枚举/总线时序、SPI/无线电实交换、IRQ/timer jitter/latency/漏更新余量、WCET 与实际栈高水位未测。用户本轮明确无需硬件，这不是上述软件缺口的统称或要求用户接板的理由。

后续最小顺序：对新精确提交做普通功能复核 → 补必要的软件契约与依法允许的受阻依赖处置 → 证据满足后受控开放已验证 profile 的普通生成 → 再逐个加入其他真实 profile。通用后端目标已确定；需要父线程另行处理的是依赖阻塞与扩展优先级，不再要求用户重新选择项目范围。

所有编译/Host/模型操作都在隔离目录；唯一源码工作树 `D:\python_software\SilverStar\.work\ccdi`。日用 HEAD 保持 `56448bd35736221d7885a26704f2f953b0fe5055`；GUI/FINAL/用户文件未动；无 DAPLink、串口、烧录、START、push 或 merge。没有执行畸形 USB/owner 表达式研究或受阻审查。

精确产物、命令、source-snapshot、模型/事实/IRQ/ELF 哈希与失败记录见 [新后端证据](evidence/native_classic_cdc_backend_20261010/verification.json)；先前 runtime/timer 报告及 9f/9b 清单保持冻结。
