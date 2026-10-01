# 0.1.1 GUI 小批次交付

2026-10-01，CHD Windows，父任务要求完成本批后停止新工作。基线为已提交的 `e02cca1c1c4de134c700e5a913dd3d2c563d9f6f`；此前固件与首发策略证据保持冻结。此报告随本地提交保存，不涉及推送、发布、烧录、START 或执行器操作。

## 已实现与实际边界

| 用户项 | 当前实现 |
| --- | --- |
| GSHC 指定旧布局 | 只读核对外部仓库，`8be9fd6^` 确实为 `cbee51e1f259d56a8e9dcdb7c3b236f9b054e4fb`。恢复预飞系统/校准/初对准三列，惯性/GNSS 两列，操作和事件全宽；飞行状态/数据/任务三列，速度 ENU 三图第一行、位置 ENU 三图第二行。保留现有串口、控制器、READY、协议和隐藏磁校准修复。新增导航准备放在事件之后，健康信息保留为可展开详情。为适配较小窗口调整布局空间和图表最小高度，并非逐像素回退整个应用。 |
| 产品 0.1.1 | 根 `VERSION` 控制三应用运行身份、生成固件身份及 decoder 身份。GSHC Windows 资源和安装脚本改读同一根版本。core 插件 ID 固定为既有 `silverstar.core.0_1_0`，插件、协议和 schema 独立版本保持；旧工程固件版本原值不自动改写。安装包本轮未构建。 |
| SCG 标题 | `SilverStar 系统配置与生成` / `SilverStar System Configuration & Generation`，单行，去掉 `(SCG)`；1280×720 中英文宽度检查通过。 |
| 初对准同框 | 选择器在上，固定双矢量或外部姿态参数、草稿提示、确认/取消均属于同一实际“初始对准”组。重绘只清理选择器表单，不销毁参数编辑器。取消保持原模型。 |
| 两硬件页 | 共用板卡选择框和硬件操作结构。Ground“使用已有硬件”根据实际可选且 MCU 可用的板卡启用；取消不变，确认后绑定 Ground 板卡及资源。高级设置移到相应配置页；Ground 构建组移到构建页、状态提示移到遥测配置。共享黄色提示按角色显示。 |
| PCB 保存 | 本地归档和安装分别进入 `Flight_Controller` / `Ground_Station` 分类目录，保存角色元数据；保留旧混合目录扫描。短唯一 payload 根避免不同 PCB 的原公共路径冲突及 Windows 长路径失败，未放宽冲突保护。相同 ID 拒绝覆盖，错误角色拒绝安装。CubeMX 原输入和旧插件不改写。 |
| 检测目标 | 质量检查明确固定为 Flight_Controller，不自动触发整套检查，也未新增 Ground 全质量检查。各目标的构建/清理分别执行。目标顶部按钮明确只看 ELF 是否存在；日志显示 integrity NOT CHECKED，不能解释为完整验收通过。NOT_PROVEN/manual pending 保持。 |

本批无导航算法、传感器运行逻辑或固件安全 payload 改动。冷备/气压计扩展按父任务延期；仍是单实例候选，不把当前暖备/共享 UART 行为声称为冷备完成。

## 已执行快回归

所有运行的完整命令、UTC、环境、基线 HEAD、退出码、完整日志和对应源 diff 在同名 `.json` / `.log` / `.source.diff`。最终源码（含新增文件）见 `source_hashes.csv`，输出见 `generated_hashes.csv`，证据文件见 `artifact_hashes.csv`。不拼接为一个未执行的全套 PASS。`reproduction/` 脚本需复制到仓库 `.work/` 后运行；生成脚本拒绝覆盖已有候选，重现请另选新的独立版本目录。

| 运行 | 实际结果 |
| --- | --- |
| `scg_final` | 15 passed，Windows Qt；本批布局、翻译、旧工程迁移、既有 GUI 工作流。 |
| `pcb_service_final` | 4 passed；补验真正的本地保存入口、Unicode 目录、两角色归档/重载、同 ID 拒绝覆盖、旧混合目录、错误角色、manifest 源文件及硬件清单读取。 |
| `gshc_final` | 4 passed / 30 warnings；两语言 × 1280×720、1536×816，真实代表性传感器值，关键状态/速度/位置/任务以及健康摘要和详情按钮在滚动视口内，六图两行在窗口内。 |
| `gshc_layout` | 21 passed / 137 warnings，较早布局与端口 GUI 回归；不冒称为最后一次布局源码的全套结果。 |
| `identity011_verified` | 1 passed，最后源码下根入口/三应用 0.1.1、独立插件版本、Windows 资源版本对象。 |
| `flp_final` | 5 passed / 3 deselected；身份与新 KF6 decoder 的严格生产打开/回放、错误身份/录制配置负例。输入是合成记录，不是板端日志。 |
| `generate011` | 独立 `.work/SCG_011_KF6_e02cca1_v1` 新生成 Flight_Controller + Ground_Station，156 个结果哈希，exit 0；版本 0.1.1。不覆盖用户最终工程。 |
| `gshc_capture_final`, `scg_capture_bottom` | 原生 Windows Qt 截图，exit 0；不是 offscreen，也没有鼠标驱动手动验收。 |

本轮没有为 0.1.1 输出重新 ARM 编译/Host/-fanalyzer/PoT。此前已提交候选的独立 ARM 两目标、Host、真实分析和检查结果仅属于 [冻结候选报告](../../FCCG/gui_closeout_20261001_v1/CANDIDATE_REPORT.md)，不能归属本轮的新生成文件或新二进制。本批源哈希和生成身份另行记录；没有旧二进制冒充新构建。

## 界面证据与未完成验收

原生截图 `delivered_*` 覆盖两语言、两逻辑尺寸，实际默认 DPR 1.25；另有 DPR 1.5 的 1280×720 采集。1536×816 对应默认缩放下 1920×1020 图像。每张采集的实际窗口、DPR、源哈希及矩形见同名 JSON。`visible=true` 是 Qt 标志，不单独证明没有裁切；上述几何测试另外核对实际视口。

- [GSHC 预飞](delivered_zh_CN_1536x816_scale1_preflight.png)、[GSHC 飞行](delivered_zh_CN_1536x816_scale1_flight.png)、[英文飞行](delivered_en_US_1536x816_scale1_flight.png)。
- [SCG 初始对准同框](scg_native/zh_CN_initial_alignment.png)、[Ground 硬件](scg_native/zh_CN_ground_hardware.png)、[检查范围](scg_native/zh_CN_checks.png)。

用户 Library 原图已能读 OCR，但受文件传输失败影响未获得其原始像素。本批旧版比对依据确切 `cbee51e` 源布局、父任务提供的截图描述和本地 native 采集；不声称已经逐像素核对用户原图。`historical_*1536x816*` 是指定历史 UI 文件加载在当前后端/身份上的隔离比对，不是原版安装包运行。

多窗口 Qt 回归出现已有 OpenGL 1281 / glGetAttribLocation 警告与显示器接口警告，完整保留未抑制。截图中的单窗口 3D 模型可见，但不等于各种显卡或实际遥测的 3D 渲染均已验收。1280×720 六图区域较紧凑，实际操作、缩放和观感留给用户手测。

仍需用户原生手测、实际串口/READY/硬件验证；未构建安装包，未完成完整栈/ISR/WCET、人工关键契约审查或硬件资格。首发磁力计与 TF 校准持久化入口保持禁用；F Prime-inspired 适配不等于 NASA 认证。GUI 小批次交付不代表 FIELD READY。

中间失败均保留：首次重挂编辑器进入动态 QForm 导致控件被清理，已改为独立 VBox 子控件；首次长 PCB payload 根超过 Windows 路径限制，已缩短并重验；FLP 旧标题/旧版本期望改为现有公共身份及根版本；初次跨应用收集和截图设置路径错误属于运行配置，修正后重跑。健康摘要实际裁切先留下失败与截图，再调整空间分配，最终同一可见性要求通过。无静默删失败、放宽安全检查或硬件动作。

暂存区全量 `git diff --cached --check` 对原始 OpenGL 日志的空格+制表缩进报错，完整输出和非零退出码保留在 `git_whitespace_all.log` / `git_whitespace.json`；排除原始日志的源码/文档检查 exit 0。未修改原始诊断格式或把全量结果称为 PASS。

交付后停止新增 Codex 工作，由用户手测，父任务负责后续安排。
