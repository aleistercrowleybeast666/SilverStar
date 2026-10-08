# SCG 存储与最简维护串口修复，2026-10-08

基线为 `e702ffd0fddf2432b22bd4c46fd1a45980d6705d`。用户最终授权仅修复 TF/SD 重复和最简档维护串口重新启用；轻量档维护串口继续可选。未读取、保存或修改用户当前未保存的工程，未关闭其窗口，未访问硬件、烧录或 push。

## 根因及修复边界

- `ui/pages/components.py::DevicesPage.Configuration_Set` 同时渲染 F4 与 F103 的存储插件，两个插件的中文显示名称相同。普通格式 15 工程、切档和反复刷新在隔离测试中只有一个存储实例，但 GUI 显示两个候选。`app/service.py::DeviceSelectionAvailabilities_Get` 此前只检查资源，并未排除另一平台的存储插件。现在按声明的 MCU/MCU-family 依赖筛选未选候选，已选不兼容实例仍保留可见并可删除。
- 存储原本使用复选框，没有逐实例删除按钮；资源不满足时，已勾选项也被禁用，无法取消。现允许取消所选不可用存储，并为每个实际实例提供独立删除按钮。旧工程有两个实例时保留它们，由用户显式删除；不静默修剪输入。
- `ui/main_window.py::_ProjectConfiguration_Change` 此前未拦截存储的第二实例或另一平台的存储添加。F103 reconciliation 又会把 F4 存储替换为 F103 存储，从而可能形成两个同插件实例。现对添加/替换入口检查平台和存储总数，拒绝非法事务；导入仍保留冲突并由生成校验拒绝。
- `project/model.py::_ProjectV9_Migrate` 只辨认 F4 存储，已有正式 F103 存储时仍会注入 F4 存储。隔离迁移用例已复现并修复为识别这两个正式插件；不会改写传入字典。这是迁移函数的边界证据，未认定用户当前工程就是格式 9。
- `project/feature_tiers.py::FeatureTier_Apply / FeatureTier_ErrorsGet` 的既有约定：轻量保留维护协议选择；最简显式关闭维护协议并在生成端禁止启用。`project/protocols.py::ProtocolProfileAvailabilities_Get` 此前仅检查传输/硬件，因此最简 GUI 仍能选回；`_ProtocolProfile_Change` 也能提交冲突。现同步禁用 GUI 候选，并拒绝直接启用入口。`_ProtocolProfiles_Reconcile` 保留导入的档位冲突供人工检查，防止新的 GUI 可用性规则导致加载时静默清除协议。

[推荐配置](SilverStar_Recommended_Configurations.md) 中的“轻量参考组合无维护串口”是那一组配置的选择，不是轻量档硬限制；[档位矩阵](FCCG/platform/details/FEATURE_TIERS_20261006.md) 也明确 Compact 可配置、Minimal 关闭。未更改导航算法、运行协议、日志配置、队列、栈大小、固件 payload、生成模板或任何哈希白名单。使用本次 Python 修复需要用户自行保存必要内容并重启 SCG；既有进程不会自动重载模块。

## 执行证据

[完整命令、失败日志、来源/产物哈希与工具版本清单](evidence/scg_storage_maintenance_20261008/manifest.json) 和 [证据归档](evidence/scg_storage_maintenance_20261008/evidence.zip) 包含全部运行尝试。源码修改通过最终 dirty snapshot 和各文件 SHA-256 绑定；最终提交还包含本说明及证据。

| 检查 | 结果与范围 |
|---|---|
| 修复前失败 | 候选/不可删除/维护候选：5 FAIL、2 PASS；额外添加与逐实例删除：2 FAIL；旧迁移 F103 注入：1 FAIL、1 PASS。保留完整日志 |
| 最终受影响回归 | **101 PASS、3 deselected，exit 0，153.84 s**；实际 Qt 切档、删除/添加、旧工程导入、重复刷新、保存重开、非法配置生成校验与翻译/协议回归 |
| 排除的旧测试 | 三项在原始 e702ffd Python 源码、同插件与目录定位下同因复现：过时 telemetry combo 搜索、格式 9 拒绝信息 regex、旧 Storage payload 路径。基线 3 FAIL / 1 PASS；未改测试期待或产品逻辑来消除这些失败 |
| 早期扩展回归 | 97 PASS / 4 FAIL，exit 1；含上述三项及从 monorepo 根目录执行翻译测试导致的路径失败。后者在 SCG 目录重跑 PASS。前两次基线隔离尝试缺定位数据，不能作为产品失败证据，亦完整保留 |
| GUI 视觉检查 | 独立 offscreen Qt 进程、安装字体、中文存储卡和最简维护控件已检查；未观察用户当前未保存模型 |
| 新生成输出 | 相同 F407/KF6 Delay10 软件配置的 22 个输出在最终修复前后逐字节相同；18 个生成 C/头文件与前一 0.1.2 隔离工程在规范化换行后相同。全部新物化 C/头文件/汇编/linker 输入也完成同样对照 |
| 架构 | 实际新生成 Makefile 的 `architecture-check`：356 checks、0 failures，exit 0 |
| PoT | 原样运行新生成 `power10-check`：6329 checks、111 first-party C files、2761 functions，exit 0；815 非阻塞建议；**critical-contract review NOT PROVEN** |
| ARM Release / 内存 / 产物 | 实际 GCC 编译、链接及 `artifact-check memory-report`，exit 0；Flash 331000/524288 B，main SRAM 112756/131072 B，CCMRAM 46760/65536 B，heap 0。保留历史 SRAM 预算提示；剩余字节不代表安全栈余量 |
| 真实静态分析 | 新工程 `static-analysis`，实际 `-fanalyzer` 编译并链接 StaticAnalysis 输出，exit 0；非 syntax-only |
| Host | 新工程 `host-tests`，exit 0；80 executables、4,446,469 checks、0 failures、11 compile-pass、18 expected rejection、8 not-applicable；后续 storage integrity 完成 |
| 栈门禁 | **FAIL exit 2**，拒绝未知 `Generated/Src/project_metadata.c` 完整源码哈希；未放宽门槛 |
| 全库/所有目标/实际硬件 | NOT RUN；本次 ARM/Host 样本只覆盖 F407/KF6 Delay10；F103 本次覆盖 GUI 平台候选与迁移，未新做 ARM/硬件验证 |

新工程只复用已逐项比对的隔离样本编译缓存，保存旧证据，实际重新编译日志和时间均在归档。最终追加的旧迁移防重检查没有改变该样本的生成字节；最终再次渲染对照后复用本轮 ARM/Host 结果，未拼成未经执行的整套 PASS。

新 Release `.bin` 为 331012 B，SHA-256 `eac468a93aff1a7602e92f5088a2cab597b3275ccda8b45e2c0dc14ba4c3ccc7`，与前一 **0.1.2 隔离软件样本**完全一致。这不是旧 `b2fae22 / mission 000051` 上板固件的再次硬件验证，也不是用户尚未配置的最终外场工程。

## 保留的栈审批阻塞

`project/model.py::_ProductPatchIdentity_Migrate` 把官方工程身份 `0.1.1 / SilverStar_0_1_1` 升级到 `0.1.2 / SilverStar_0_1_2`，这属于之前 e702ffd 的行为。本次用同一个模型精确恢复旧身份再算摘要，得到：

| 项目 | 旧 | 新 |
|---|---|---|
| 配置摘要 | `0xA79E2E92UL` | `0x42A4C1C6UL` |
| `Generated/Src/project_metadata.c` 规范化源码 SHA-256 | `ae4706ff828b966e517972f147eee2d5ca938a144ff437ef3b71d32a9f186181` | `bba3aed1cc73043a10cfd126a7759728a10de53e3769e2563fb209a4b12feadf` |

仅替换旧文件这一个摘要常量即与新文件全部文本相同。新的完整源码哈希仍未授权、未登记。本次未追加 owning checker 或 reference overlay 白名单；若继续闭合该样本栈门禁，需对这一确切文件、差异和哈希单独明确授权。用户改成自己的最终配置后摘要还可能不同，不能用这一个样本的授权覆盖任意新配置。

用户可开始自行配置；合法配置的普通生成路径已验证，但当前不能声称 0.1.2 已完成全部外场门禁。栈 FAIL、三项原有测试失败、PoT 关键合同 NOT PROVEN 及不可用硬件证据均保留。
