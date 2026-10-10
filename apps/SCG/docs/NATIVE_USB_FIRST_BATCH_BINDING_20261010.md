# F103/C071 USB 首批后端绑定阶段｜2026-10-10

**USB 尚未完成，不能合并日用或报告正式开放。** 本阶段完成精确目标分派、C071 原生 PCD/companion 来源绑定和保存重载的 recipe 计划；F103 复用既有私有导入/渲染/ARM 构建。C071 固件 renderer/build 在统一后端仍未接入，这是实现缺口。USB b66 独审无通过结果、完整生命周期/critical-contract/栈/WCET 未验收是另一个发布阻塞，不能混称“只是没上板”。

源码：`efef41f49c451ba38b4b7ca88581d4e89b6ee23d`，父提交 `ed9ff651f0b6d8483378889009811ab572dff109`。开发目录仍为 `D:/python_software/SilverStar/.work/ccdi`，分支 `feature/scg-classic-cdc-contract-20261009`。

## 普通实现

- 新增 service 的 `UsbGroundProject_Import` / `UsbGroundCandidate_Plan` / `UsbGroundCandidate_Export` / `UsbGroundCandidate_Build`。首批只认 F103C8T6/72MHz、C071FBP6/48MHz；F103CB、C071RB、F407 及未知配置均不属于该入口。原 F407 私有 API/测试保留，没有扩其适配。
- 后端固定数据校验自身原始字节 SHA；实际独立 SDK header 的 SHA 与完整 IRQn 表每次核对。项目中的 part/capability/release 字段不构成授权。没有声称哈希是厂商认证或完整物理内存证明。
- C071 使用已知 b66 的固定 native-profile 与 companion-manifest JSON，只核对普通来源字节身份。原生 HAL/CMSIS/startup/linker/clock/GPIO/IRQ/PCD 保留；原生输入是 PCD，不能冒充原生 CDC。companion payload 每次逐文件核对；没有复制或运行其 USB 固件/安全研究到本分支。
- C071 导入返回复制模型，冻结 111 个原生来源文件到工作区缓存；模型往返与重载后再验证源图、资源、绑定及能力字段。模型仅标记 `usb.native_pcd`。recipe 计划明确 `firmware_files_rendered=false`、`cdc_runtime_accepted=false`、`formal_release=false`，结果为 `BlockedFirmwareIntegration`。
- C071 候选 Export/Build 在创建输出前拒绝。正式 Ensure/Plan/Apply/Build（含 `ensure_buildable=false`）和直接 Ground renderer 均保留阻断。现 GUI 冻结，没有新按钮。
- Python wheel 包含四份固定配置数据，逐字节与源码核对；这只证明配置入包，未宣称完整应用可独立部署。

F103 Export 的保存项目目录边界仍沿用此前 API：它无 project_root 参数，不宣称检查了保存项目目录的双向包含；Build 才检查该边界。本阶段不改变此已记录限制。

## 实际执行与证据

| 运行 | 结果与准确范围 |
|---|---|
| ub03 新首批 suite | 21 passed、0 skipped，100.13s；C071 普通绑定/保存重载/拒绝/门禁，F103 统一入口 Import/Export/真实 ARM+analyzer Build，F407 在统一入口拒绝 |
| ub04 保留原生后端 suite | 28 passed、0 skipped，241.12s；原 F103/F407 私有流程与两次真实 ARM+analyzer Build |
| ubr01 单独保留回归 | 11 passed，22.80s；静态导入、模型重载和普通 build tooling 单元范围 |
| ub03 F103 gate | architecture、Host、artifact、原样 emitted PoT 四命令均 exit 0；不是未执行的整仓或完整 USB 安全 PASS |
| Python wheel | 离线无依赖下载构建 exit 0；四份配置数据哈希匹配 |

三次新构建分别是 F103 333、F103 333、F407 387 个命令，全 exit 0、编译 warning 0；实际对象/ELF CPU/FPU/ABI、独立 IRQn/vector、source closure 保留。逐次核对 545/545/635 个记录产物哈希和 model SHA/双 receipt 关联。两个 MCU 新 ELF 分别与此前字节相同，均为新构建，未复制旧 ELF。**本阶段没有 C071 固件构建结果。**

每次 pytest 有一条既有 `Unknown config option: cache_dir` 环境 warning。ub01 保留 1 failed/18 passed：重载测试未沿用其显式短缓存配置；修正测试配置后 ub02 中间版本 19 passed。ub03 才是最终新增 suite。另一次保留回归 shell 准备命令因引号 SyntaxError 未开始测试，改为保存 runner 后执行 ubr01；不计旧失败为 PASS。

测试实际基线是 ed9 的可审计 dirty snapshot，记录新增文件的原始 SHA/文本并与 efef 源提交核对。pyproject 的数据入包设置由随后 wheel 构建验证；不改称在最终 clean 提交上重跑了全部测试/链接。分开的 21、28、11 及 gates 不拼成未执行的全套回归。本阶段新增普通绑定没有独立 QA 通过结论；此前 348/ed9 独审只适用于其原范围。

证据目录 `docs/evidence/native_usb_first_batch_binding_20261010/`，89 个清单项目、90 个 Git 文件（含 verification 自身）。清单 SHA256：`0a92f4dad9ca433d1643ce7dd78056be00970994c1f24a82bee6eb1277977062`。含执行命令/日志、保留失败、源码及配置、两份 C071 保存模型/合同、三次编译 receipt/源快照/ELF/map 和 wheel；没有复制整套 vendor 源。临时完整原生输入/产物路径在 receipts 中可核对。

## 剩余工作与权限边界

1. 普通实现：将 C071 固定 companion 的实际固件 recipe 接入统一 renderer 与共享 ARM/analyzer 编译，保存完整源图/模型/产物回执；F103 共享 EP0 修复也尚未合入这条线。不能只增加白名单或删检查来宣称支持完成。
2. 发布验收：已知 USB 另线 `b66f142f7ab9b5611bd2f9a84a105835e4f77b96` 独审被平台中止，无通过结论；本轮未恢复、换工具或绕过该审查。须由合法途径处理，用户“需要权限时给”不等于解除这条约束。完整 EP0/异步 TX/control/reset/config/deinit/cancel 所有权、人工 critical-contract、库/间接调用/递归、MSP/ISR 栈及 MCU WCET 仍 NOT PROVEN。
3. 硬件：未接探针/串口、未烧录/START，真实 USB/SPI/无线电/IRQ/计时余量与栈高水位均未测；软件实现和验收缺口单独列出。

本阶段无需新增用户权限。未来合并必须在父任务先告知用户实际完成范围后安排，并检查日用工作区保护；当前未合并、未 push。日用仍 `56448bd35736221d7885a26704f2f953b0fe5055`，三个既有未跟踪清单保留。GUI/FINAL/用户文件未改；现有固件模板、插件 payload 与 F407 适配未改。
