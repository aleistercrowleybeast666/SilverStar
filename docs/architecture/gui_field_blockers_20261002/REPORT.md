# GUI field blockers — 2026-10-02

本轮完成 SCG/FLP 配置卡点修复。功能代码提交为 `08a113d2cce58070dc1f424b316595005e38eb5d`；全部修改只在 `D:\python_software\SilverStar\.work\GuiFieldBlockers_20261002`，分支 `feature/gui-field-blockers-20261002`。

主工作区初始及完工前均为 `fix/software-reconnect-ground-20261001` / `5c451551c6f55211c06f38fe33d0f06f3349edb6`，`git status --short` 为空。读取了仓库 AGENTS、FCCG 架构/运行时安全和 FLP 架构；未找到仓库额外 `.agents` 规则或可读 `memory_summary.md`。没有修改其他 worktree，没有连接 COM3/DAP、发送硬件命令、烧录、push、tag、Release 或合并。

## 根因与修复

| 项目 | 复现证据 | 最终行为 |
| --- | --- | --- |
| FLP 遮挡 | 基线 1000×700 逻辑窗口：第一行分配 23 px，下拉控件需要 31 px；第二行从 y=57 开始，与控件范围重叠 | 与 SCG 一样一行顶栏；项目标签使用可收缩布局策略，按最终控件宽度省略；`*` 独立保留，完整路径在提示中 |
| Ground 默认空白 | 新草稿 Flight `custom`，Ground `unselected`；板卡框无当前项目 | 新草稿两端均默认自定义 STM32。旧工程解析不自动更改 Ground 选择；Ground 启用仍需要用户显式勾选 |
| UART 空白 | 未选择硬件时只有空项，未解释原因；GS_SS1 选中后有实际 USART1，但只显示 PLATFORM_UART_1 | 使用所选 Ground 的资源 inventory；显示 `USART1 · PLATFORM_UART_1`。无 inventory、无 UART、旧绑定不存在分别提示原因；失效绑定保留并禁选，不伪造资源 |
| 无线选择不一致 | Ground 选择 SX1281 后唯一 `e28_2g4m12sx` 仍空，报 AIR_LINK_NO_RADIO；Flight 直接使用唯一模块 | Ground 与 Flight 同样采用唯一声明模块；多模块仍需显式选择。重选同一无线插件保留模块/接线；不改变 AIR 参数、发射功率或协议，不做多无线自动切换 |
| UART 绑定重开/重复选择 | 板卡声明 USART1；逻辑资源映射、配置序列化与 UI 当前值均可核对 | 已保存绑定重开一致；重复选择相同 PC 接口不清除 custom UART 绑定 |
| 导入/保存按钮 | 新建 Ground 的模式导致流程与 Flight 不一致；保存按钮还会被公用 Boards_Set 后续重置 | 实际完整 F103 CubeMX 工程导入后匹配 MCU、列出 USART1、保存硬件可用；保存后的 Ground 实例出现在已有硬件列表。没有完整快照时不能保存硬件 |
| 新工程内存布局 | 新草稿 build.memory_layout 为 legacy | 只在 ProjectDraft_Create 设置 auto；BuildOptions 与旧字段缺省仍为 legacy。显式 legacy / eskf_window_sram / auto 均保持 |
| 根入口仍 FCCG | 根部同时保留 FCCG/SCG 以及辅助程序，SCG 启动函数仍以 FCCG 命名 | 根部只保留 SCG.py、GSHC.py、FLP.py。SCG 公共名称解析到兼容 apps/FCCG 实现；CLI 描述更新 |

`baseline/capture.json` 和 `final_capture/capture.json` 保留实际控件几何和 inventory 映射。Windows 显示缩放使 1000×700 逻辑窗口的 PNG 为 1250×875 像素；验收使用实际 PNG，未将逻辑尺寸冒充 PNG 尺寸。

## 分隔提交与目录安全方案

| 提交 | 范围 |
| --- | --- |
| a97acbc | 根三入口、兼容 FCCG 启动器、辅助程序迁移及版本/启动测试 |
| 502e527 | SCG Ground 默认、Radio/UART、保存按钮及新草稿 Auto |
| 08a113d | FLP 一行顶栏与布局回归 |
| 后续证据提交 | 本报告、复现脚本、完整日志、截图与哈希；不改功能代码 |

先提出安全方案，再在隔离分支执行：`FCCG.py` → `apps/FCCG/FCCG.py`（调用同目录 main）；`silverstar_version.py` → `tools/silverstar_version.py`（同步 setuptools 动态版本导入）；`freeze_memory_final.py` → `tools/freeze_memory_final.py`（根定位改为 parents[1]）。其余目录不迁移。LICENSE、VERSION、README、AGENTS、pyproject、Git metadata 都保留；未移动用户日志、TEST0–4 或其他用户输入。旧项目 schema、apps/FCCG 包名、配置路径和工程导入方法保持兼容。

实测 `SCG.py --version`、`apps/FCCG/FCCG.py --version` 和 setuptools `read_attr('tools.silverstar_version.__version__')` 均为 0.1.1。原根 `FCCG.py` 文件已搬到兼容入口；外部快捷方式若仍直接指向原根 FCCG.py，需要改为 SCG.py 或新兼容路径。

## 验证结果（不合并成虚构的全套 PASS）

| 执行 | 结果 | 证据 |
| --- | --- | --- |
| 新控件回归 + Ground recovery + release GUI + FLP header/release identity | 17 passed | targeted_tests_r4.log |
| 已有 workflow + F103 generation/resource constraints + auto memory + monorepo baseline | 38 passed, 1 failed | extended_tests.log |
| 最终提交 UART 保存重开 + 根三入口 GUI 启动 + 旧 FCCG 版本入口 | 3 passed | final_focused_tests.log |
| 最终提交 fresh Flight/Ground 生成、ARM Release 编译 | 两目标 exit 0，make -j2 | build_final/summary.json 与两份完整编译日志 |
| 新测试/FLP widget 的 Ruff F 检查、git diff --check | passed | 本轮命令输出；diff 当前无空白错误 |
| 完整 CubeMX 导入/保存/已有实例 + 相同接口保留 USART1 | passed，实际 Qt 像素已查看 | final_capture/import_save.json 与两张截图 |

扩展回归失败项为 `test_current_document_links_resolve`：历史 `docs/FCCG/evidence_flight_safety_batch1_20261001/AGENTS_SNAPSHOT.md` 中 `docs/FCCG/ARCHITECTURE.md` 相对链接失效。只读对比确认该快照与初始 HEAD 字节一致；保留历史证据，没有为了变绿修改它。

完整保留早期失败：`targeted_tests.log` 的临时目录初始化/旧配置样本错误；`targeted_tests_r2.log` 的应用路径约束与不完整 CubeMX 输入；`targeted_tests_r3.log` 的本轮测试安装板卡污染后续列表。测试准备已修正：临时目录位于应用 .work、导入完整 payload、安装目录按测试隔离；已生成的旧测试板卡移至隔离 .work 证据，未删除用户数据。17 项重跑通过，不把先前失败抹去。

生成流程从 SCG 新草稿开始，选择 Flight SS0.5 和 Ground GS_SS1、启用 Ground、选择 SX1281/UART；配置保存后通过 GUI `_Project_Open` 重开，断言 Ground 配置相等；随后 `TargetGeneration_Apply(..., TargetScope.ALL)` 输出到新的 `.work/FieldBuild_20261002_final`。编译命令在两个目标目录分别执行：`D:\msys64\ucrt64\bin\mingw32-make.exe -j2 all CONFIG=Release`。PATH 前置 Arm GNU 14.3 rel1 与 UCRT64。没有执行 flash 目标。

代码版本和 ELF SHA-256 在 `build_final/summary.json`。本轮只是配置/GUI 修改，没有改 firmware payload、RF/Baro/optional GNSS、GSHC START controller 或融合诊断门槛。新草稿 Auto 用于 Flight；Ground 保留其独立原有构建策略。成功链接不证明 MCU 栈、安全门槛、导航准确性或外场/飞行资格。

## 像素与未测边界

已逐张查看：FLP 基线遮挡/修复后正常与窄窗口/长中文工程名/未保存/英文暗色；SCG Ground 初始默认、所选板卡、唯一模块选择、实际 USART1、无 inventory 提示、Auto 构建页、完整导入后保存按钮、保存后的已有硬件实例。图片放在 `baseline/` 和 `final_capture/`。

这些是实际 Windows Qt 窗口的 QWidget.grab 与真实控件/API 驱动（含 QtTest 等待/几何测试），不是原生鼠标点击验收。Computer Use 技能已读取，但本环境没有它要求的 node_repl 工具，未冒充 CUA。没有运行全仓库全部测试；没有自定义 Ground 的全套生成编译矩阵、GSHC START、固件 optional GNSS、硬件通讯或烧录测试。已有自动测试对无 UART 资源分支使用受控模型状态，不代表另一个真实板卡。

## 用户附件的明确阻碍

保留原身份 `libfile_7ee9e9ad6e448191ba15d6be4a723fbd`。依 Library 技能 `skill://plugin_connector_1p_1b8ff8edfc1481918b252c8277e23125/library/SKILL.md` 和其 `references/materialization.md`，使用 prepare_materialize 与本轮从同一源读取的官方传输助手。受限网络首次下载失败，获准联网重试后进入元数据写入，但官方助手调用 Windows Python 不具备的 `os.setxattr`，报 `AttributeError`，最终 PNG 路径不存在，因此未查看用户原始附件。

该材料化规范明确要求："If the helper is unavailable, stop rather than producing a local file without its Library metadata." 本轮没有绕过原身份或把下载临时文件当成已成功读取，也没有重新上传用户输入。原附件像素对照仍待受支持的 Library 本地材料化能力；本报告的复现只依据独立实际 GUI。

功能提交可供父线程审阅和选择集成；若需要先做板测，可独立选取 SCG/FLP 功能提交，目录整理是独立提交。当前不能宣称“全 GUI 没问题”或“全部验收完成”：原附件对照、原生鼠标验收和历史文档链接失败仍明确保留。没有合并主分支。


## 父审核补充后的最新状态

后续修复了扩展回归的文档检查器来源目录问题，冻结快照及 INDEX 哈希不变；重新执行先前扩展集合结果为 **41 passed**，没有剩余该项失败。首次 38 passed / 1 failed 的日志保留作为历史执行记录。详见 PARENT_REVIEW.md 与 extended_tests_r2.log。

父线程已通过官方云端 Library 看过原附件；本机仍没有材料化文件，本人没有声称已看输入原图。依据父线程对原图两行游离项目文字的具体描述，补充并亲眼查看了修复后同 1920×1020 像素窗口、长中文 dirty 名称以及窄窗截图，位于 parent_comparison/。本机材料化失败不再阻碍父线程原图审核；原生鼠标验收仍未做。生产代码仍为 08a113d，后续仅修改测试验证器和证据，未合主工作区。
