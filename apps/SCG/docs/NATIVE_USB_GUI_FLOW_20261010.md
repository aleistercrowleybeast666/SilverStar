# 第一批 USB 普通产品接线与软件验证 — 2026-10-10

最终测试/构建提交 `63771a17e63052c238246dd4fe3fe6394de8ccec`；产品源代码与 `f91f82e4a0b4e83bb583c39b86a3d98f150cccf2` 完全相同，63771a1 仅改变真实 ARM 质量审计测试的有界等待。独立工作树 `D:\python_software\SilverStar\.work\ccdi`，分支 `feature/scg-classic-cdc-contract-20261009`。没有自行 merge/push，日用 HEAD 保持 `56448bd35736221d7885a26704f2f953b0fe5055`。

直接用户回复“允许”后，原 GUI 写入审批已通过；先前两次执行前拒绝已解决。此授权不覆盖 b66 独立 USB 安全审查。该审查仍 `NO_PASSED_OUTCOME`，未重试、未绕过、未标已审。以下均是普通功能、生成、构建和软件证据。

## 已有普通用户入口

原有 Ground Station Hardware 页的 PC 接口选项已有 `USB CDC Virtual Serial`。普通新建项目默认单 E28/SX1281、SX128x AIR 配置：选 USB，然后原有“导入 CubeMX 目录/IOC”按钮读取 exact native source，应用完整后端绑定模型；原有保存/打开保持模型；原有 Ground“生成”按钮进行 candidate Plan/Export；Build 页原有 Ground Build 按钮进行 candidate Build。源码在正常 MainWindow/FccgService 中调用，不依赖 SILVERSTAR_USB_BACKEND_ARM 之类测试开关。

`ue01` 从 `ProjectDraft_Create` 普通默认模型开始，删除 private model/admission 环境，实际操作已有 USB 下拉框、目录导入按钮、保存/重载和生成按钮，两款均成功。它没有另做 ARM 编译；`ug08` 则通过相同正常 MainWindow Build action signal/真实 worker 路径完成两款 normal/analyzer 编译与质量检查。文件选择对话框与 QMessageBox 在 offscreen 测试中被替换，业务 backend/compiler/worker 没有替换。未声称真实桌面鼠标或新建向导像素验收。

生成与编译是已有独立按钮操作，不能把配置、目录选择与两次操作称为一个无需配置的整包按钮。每次生成/Build 使用新的 disjoint sibling `usb-<id>`，模型记录在所选项目，目录和 receipts 从 UI 日志/已有打开目录/VSCode/产物操作可见。native HAL/CMSIS/startup/linker/clock/GPIO/IRQ/PCD/middleware 原件保持所有权，窄范围 derivatives 保留 patches 与原件/派生 hash。不会覆盖原生输入或用户项目 payload。

## 本轮软件可用性限制

| 条件/门禁 | 对已有按钮的具体影响 | 状态 |
|---|---|---|
| exact target/native profile | 仅 F103C8T6/72MHz、C071FBP6/48MHz 的已 pin 完整工程；F407/其他芯片、时钟、变动源集拒绝 | 明确首批范围，未删检查 |
| radio/资源/LED 配置 | 单 `radio0` E28/SX1281、SPI1 与各板固定 NSS/reset/busy/DIO1；无此候选未适配的活动 LED | 不静默改用户配置；不符拒绝 |
| independent SDK IRQ/header 与 C071 companion | 每次 import/Plan 验证 SDK bytes/enums；C071 使用 builtin byte-pinned companion。SDK 位置可通过明确 location env 设置，不能借此改变信任描述 | 缺失或 hash 不符时明确错误，不颁发能力 |
| 工具 | 编译须有配置/探测到的 ARM GCC；normal/analyzer/对象/ELF/IRQ/内存核对均实际运行。Host/PoT 还需对应 Host GCC/PowerShell | Build 不需要 Make；工具缺失阻断相应操作 |
| model/source/artifact identity | 保存模型、snapshot、backend/compiler receipts、所有记录源/产物 hash 必须一致 | 过期 ELF 被实际 GUI 拒绝，重新生成/Build |
| 正式一般生成/Generate All | 独立 candidate Ground 操作可用；正式 general generation guard 保留，Generate All 不把此候选与 Flight 静默组合 | 显示软件候选与 formal release BLOCKED |
| b66 独立安全审查 | 不阻止这条明确候选普通软件工作流；阻止把它报告为已安全审查/正式发布 | NO_PASSED_OUTCOME |
| manual critical-contract、whole-program stack/WCET | 工具通过不构成语义验收、完整栈或 STM32 WCET 证明 | NOT PROVEN，不 relabel PASS |
| PCD/PMA/IRQ 运行/物理 USB | Host 不执行原生 controller/IRQ interleaving；未进行板上行为/全部异步交错证明 | 本轮未测；硬件不是本轮软件完成前提 |

状态与 logs 明确保留 release notice。`static_analysis` 动作检查已有成功 analyzer receipt 和产物，不伪造新的独立 analyzer/review。Clean 仅删除已验证候选的 build 目录并撤销成功 pointer，保留源/日志/receipt。未以内存余量代替栈证明。

## 正常缺陷与超时定位

父 ordinary review 的 F103 P2：`USBD_LL_Reset`/`USBD_LL_DevDisconnected` 丢弃 class DeInit/CloseEP 失败。4926f77 在 owning generator 传播返回并保持原来的失败保留资源路径。ul17 对每款 actual core/class/interface/stream 执行 17 个正常场景（含 Reset/Disconnect 清理失败及重试、suspend/resume/reset/disconnect），共 34 次执行，2 pytest tests，不把 scenario 数写成 pytest 数。LL/PCD、Cortex、UID/allocator accounting 是明确 Host 替身。

ug07 GUI 结果保持为 11 passed/1 failed：C071 artifact quality audit 超过旧通用 10 秒测试 helper 的等待。ug08 产品源代码未变，只将这一真实 ARM 审计等待限定为 120 秒。最终 C071 architecture 6.07s、artifact 10.47s；真实命令退出、quality receipt 写 passed、worker 清空、GUI success 与 BLOCKED 同时断言通过，随后 stale ELF 拒绝断言通过。独立 ugg02 artifact 命令亦 exit 0。这支持正常审计预算不足，未观察卡死；不宣称所有未来工具进程有总超时证明。既有 runner 仍支持普通取消。

前期 ug03 状态文字被通用 completion 覆盖、ug06 资源表 generic gpio 类型分别已修，原断言保留。ug01/02 的 tuple/list 原始 Python 类型比较改用真实 JSON 序列化身份；ug04 测试 collection import 错误记录保留。旧失败不拼接成另一次全套 PASS。

## 最终执行结果

- `ug08`: 12 passed, 0 skipped，source `63771a17e63052c238246dd4fe3fe6394de8ccec`；Ordinary actual GUI import/save/reload/private Plan/Export/Build, result/progress/cancel and exact-target refusal; no hardware or stopped safety review。
- `ue01`: 2 passed, 0 skipped，source `63771a17e63052c238246dd4fe3fe6394de8ccec`；Ordinary new project default plus existing USB combo/import directory/save/reload/generate; no private model or admission environment。
- `ul17`: 2 passed, 0 skipped，source `f91f82e4a0b4e83bb583c39b86a3d98f150cccf2`；Only valid ordinary single-FS CDC enumeration, configured bulk transfers, ZLP, lifecycle cancellation, buffer lifetime and session reconnection through real generated USB sources. Host LL controller substitutes; no malformed USB/owner expressions or blocked independent review.。
- `ugr02`: 99 passed, 0 skipped，source `f91f82e4a0b4e83bb583c39b86a3d98f150cccf2`；Preserved ordinary GUI/target progress/build and native control/clock/radio/ABI/runtime regression; no hardware。
- `STM32F103C8T6`：339 实际命令均 exit 0，normal/analyzer link 成功，firmware/analyzer 零 diagnostics；normal ELF `fde957fe80fdf038f4c5c6640bc851446e8ef7acb7605258fd94dca87c81240b`，analyzer ELF `fde957fe80fdf038f4c5c6640bc851446e8ef7acb7605258fd94dca87c81240b`；完整 source-snapshot SHA256 `e40511fd8c095348b5b13f60ceddedfd38275c519e5ef0c0246db48eaa159aed`。
- `STM32C071FBP6`：351 实际命令均 exit 0，normal/analyzer link 成功，firmware/analyzer 零 diagnostics；normal ELF `ee90e6871f5f5723982701e8b6783dd2638f4bd76f352f5099d2d38e031028b9`，analyzer ELF `ee90e6871f5f5723982701e8b6783dd2638f4bd76f352f5099d2d38e031028b9`；完整 source-snapshot SHA256 `3b3cca957eeb3c72dd773114ad344404bef178ddfb132d18c983d8b2e898ba5c`。

生成的 C071 普通 Host gate 继续使用其既有 endpoint-service mock；独立 ul17 lifecycle tests 编译实际生成的 C071 interface/service/core/class，LL/PCD 控制器仍是 Host 替身。两类证据不互相替代，也不称原生 IRQ 调度验证。

每款八项验证类别为：已有 GUI 流程、独立正常 lifecycle Host、normal ARM、analyzer ARM、生成架构、生成普通 Host、产物/实际对象 CPU 与独立 SDK IRQ/vector、原有 PoT。后四项是每款四条独立生成检查命令，`ugg02` 共八条全 exit 0；没有伪称每款八条 generated gate 命令或全仓库测试通过。所有实际对象和 ELF 的 CPU/ABI 及独立 SDK IRQ enum/vector 核对保留。

布局/控件/样式与原构造器保持：两个 UI 文件仅指定逻辑方法改变，另 24 个 UI 文件相同。相同普通未绑定参考模型经稳定 Qt font/geometry 状态后，Ground 与 Build offscreen1280x820 两张 PNG 像素完全相同；初次两像素字体状态差异证据仍保留。字体环境存在中文缺字，不能声称原生桌面全视觉验收。

现有 pytest unknown `cache_dir` 警告与 Host vendor unused-parameter 警告原样保存，区别于 firmware/analyzer 无诊断门禁。证据 manifest：`evidence/native_usb_gui_flow_20261010/verification.json`。归档包含完整 final source-snapshot、compiler/backend/model/result receipts、实际 commands/logs、两种 ELF/maps/.su、selected generated/derivatives/Tools、actual lifecycle Host fixtures/executable，以及失败/通过历史；未重复复制大 vendor 树，原件 hash/路径和早期 archives 仍作为 provenance。

F407 原候选和原计时报告保留，未新放行。日用仅三个已有 untracked inventory 文件；无 hardware/DAPLink/串口/flash/START、FINAL 修改、push 或 merge。此报告不是新的独立安全审查或正式通用固件交付；普通首批软件工作流完成后交父任务审查。
