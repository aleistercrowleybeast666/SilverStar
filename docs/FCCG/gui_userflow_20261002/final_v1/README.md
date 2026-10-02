# GUI / user-flow 软件切片验收（2026-10-02）

本轮必要修复已完成，最终代码提交 `17bc6ce8351773bd036f4f52b93b2e4bf0acde16`。四个全新单端工程与两个全新双端工程完成应用入口验收；最终原生门禁是一轮实际执行的 **14/14**，不是拼接历史通过项。关键契约人工审查仍 **NOT_PROVEN**。

当前分支 `fix/software-reconnect-ground-20261001`；main 保持 `d410f4a7254f0433e91a22adb237b2944939fd99`。所有生成/截图都在本轮 `.work/GUI_UserFlow_20261002_v1` 或 FCCG 自有隔离测试目录。用户 TEST_0–4、桌面、其他网站任务、ToDesk 和加速器未修改；本轮没有 COM 枚举/连接、DAP/SWD、复位、烧录或硬件控制。父线程独立获得的硬件证据不算本轮验收证据。

## 逐项结果

“通过”均指下表明确的软件范围。离屏 Qt 使用真实事件循环和应用入口；未执行实际 Windows 鼠标验收，也未模拟 MCU 资格验证。

| 项 | 结果 | 实际证据 / 限制 |
|---|---|---|
| 中文单行标题、0.1.1 | 通过 | 最新 28 张逐页截图显示 `SilverStar 系统配置与生成`，没有 `(SCG)`；英文保留 SCG。 |
| 传感器名称、IMU 在 GNSS 前、磁力计隐藏 | 通过 | FCCG GUI 名称测试及最新 Devices 截图。 |
| 重力/方向矢量与外部姿态配置、连续操作 | 通过（Qt） | alignment 分组、弹出框往返、原子确认/保存重开及忙碌双击测试；没有为阈值重排函数。实际 Windows 弹出框体验未验证。 |
| KF6 默认、首屏日志可用、ALIGN_RESULT 必需记录 | 通过 | 新工程默认和日志 UI 测试；四条真实新工程入口均检查 KF6 默认。 |
| Ground 无线合入遥测、UART、启用/CRC 边框 | 通过（Qt） | 新浅深主题滚动截图，UART=`PLATFORM_UART_1`、230400；实际 F103 已有板卡与完整 IOC 生成/编译。引脚仅来自板卡/导入清单。 |
| Flight/Ground 已有板卡、导入、保存流程与提示 | 通过（软件） | 既有硬件选择取消/提交、共同页面、PCB 分类/旧路径、保存分类/重开测试；平台事实从清单匹配，黄色说明可见。保存硬件按钮按现有/自定义适用性启用。未新增任意板卡兼容承诺。 |
| 新工程立即创建三目录 | 通过 | 四条 `_NewProject_Show` 均验证 Flight_Controller / Ground_Station / Log；向向导注入文本，随后走真实应用入口。 |
| 仅 Flight 不受未启用 Ground 阻挡 | 通过 | 两个全新 Flight 单端生成成功，Ground 没有 Makefile。 |
| PoT 硬失败红色、建议通过信息色、系统日志与导出 | 通过（展示/防陈旧） | 返回 0 但 critical FAIL 仍红色的负例；PASS 保持信息/人工待审。最新弹窗回放的是实际新工程原生输出，CSV 含函数、完整路径、文件和行号；变更源码后导出被拒绝。合成测试只证明 GUI 合约。 |
| cbee51e 历史 GSHC 布局 | 通过（离屏对照） | 读取精确 `cbee51e1f259d56a8e9dcdb7c3b236f9b054e4fb` 的 main_window 模块，以当前共享依赖运行；历史/当前共 12 张截图及几何数据。状态区按内容高度布置，减少图表被空白挤压。双方 GL 隐藏、未创建 controller/transport；不声称完整历史应用或桌面 3D 已验证。 |
| FLP 当前/未保存标题 | 通过（2 个定向测试） | `flp_titles.log/xml`，本轮未新增打开日志/解码退路。 |
| 英文侧栏、深色文本 | 通过（Qt） | 宽度按本地化标签自适应且有上限；最新中英浅深截图与主题重绘测试。 |
| F407/F103 已有板卡与完整自定义 IOC 四路径 | 通过 | 全新配置→保存重开→单端生成→ARM 编译链接→架构→原样 PoT；两 Flight 另跑 memory/stack 报告。自定义 IOC 是真实仓库板卡完整导入夹具，不是未知 PCB 硬件证明。输入文件哈希未变。 |
| 两个新双端工程、再次生成保留用户文件 | 通过（生成范围） | `Dual_Final_v2` 已有板卡/完整 IOC 各一；真实 `generate_all` 两次，两个 Makefile、保存重开一致，双方 UserNotes 与 Log 夹具哈希不变。双端工程未额外 ARM 编译；四条单端编译是其明确编译范围。 |
| Baro GUI / 运行时边界 | 保留边界 | 本轮未集成新 Baro 运行时。旧来源 255/UNKNOWN 与冷备未证明状态不能据 GUI 消除；独立 Baro 提交由父线程审查，本轮不归因于这些输出。 |

## 本轮提交与关键函数

| 提交 | 改动 / 亲读入口 |
|---|---|
| `2b74e295655da4e6297f58fddb6c4fb528792ca3` | `MainWindow._Build_Create/Language_Apply`，`BuildPage.QualityResults_Set`；侧栏自适应、主题语义色；忙碌测试补已有 SF6 条目，幂等断言未削弱。 |
| `ede4fbcccd8300152bf076d318c8583552d67fa4` | GSHC `MainWindow._build_flight_page`，`TouchScroll_Wrap`、`_ContentSizedScrollArea.sizeHint/resizeEvent`；状态内容高度与图表空间。 |
| `4a05a20fdb171cc7a0f9ab4b18f33e6b1adb568a` | `_GroundBoard_Reconcile`、`MainWindow._TargetPages_Refresh`；恢复 Ground 板卡事实、平台匹配与 SysTick 展示，保留错误映射拒绝。 |
| `078c3c8d78ffbebcf5b3e980662bf180551539fb` | `MainWindow._SystemLog_Show/_Power10Report_Export`；单实例非模态日志、当前哈希验证 CSV、陈旧导出拒绝。弹窗内容是打开时快照，不承诺实时流刷新。 |
| `17bc6ce8351773bd036f4f52b93b2e4bf0acde16` | 所属 core 的 `check_architecture.ps1` 与 `SourceGraph_Resolve`；按明确自定义快照切换 Core/FATFS/IOC 路径，有 Board 时继续扫描；导入 `.mk` 同样受禁通配约束；EIDE 显式排除 importer 原本已排除的 sysmem/freertos。Make 源图、PoT 模板与九条其他规则/例外不放宽。 |

## 实际测试范围

分别记录，不能合称一次完整全套：FCCG 52 passed / 4 Windows 用例 deselected（源码 `078c3c8`）；GSHC 9 passed（`ede4fbc` 后，之后 GSHC 源未修改）；FLP 2 passed（之后 FLP 未修改）；自定义架构 5 passed（17bc 提交前对应功能内容）；最终 `17bc6ce` 新生成的原生一轮 14/14。52 项未因只修改源图/架构模板而重复。

四个明确未执行的 Windows 用例：alignment popup 的 `[windows]`、`test_windows_first_show_has_final_page_and_style_state`、`test_native_windows_first_paint_and_non_alignment_popup`、`test_root_launcher_windows_first_paint`。本轮没有悄然变成 skipped/pass。

| 新路径 | ARM artifact-check | architecture-check | power10-check | memory / stack |
|---|---|---|---|---|
| flight_existing | 0 | 0 | 0；人工 NOT_PROVEN | 0 |
| ground_existing | 0 | 0 | 0；人工 NOT_PROVEN | 未要求 / 未执行 |
| flight_ioc | 0 | 0 | 0；人工 NOT_PROVEN | 0 |
| ground_ioc | 0 | 0 | 0；人工 NOT_PROVEN | 未要求 / 未执行 |

命令、cwd、source commit、退出码、完整输出及输出 SHA 在 `workflow_gates_final.json` 和归档中的 `Runs/final_*`；准确工具版本在 manifest。驱动 `workflow_final.py`、`dual_final_v2.py`、`run_workflow_gates_final.py`、截图脚本均附原文。最终 emitted Power10 与 architecture 文件也保存；未只补丁生成副本。本輪未重跑 Host 或 GCC analyzer，既有 Single 24/24 与 Auto 32/32 只保留原日期/版本/范围，不归因于本轮提交。资源余量不是全路径栈界限、WCET 或 MCU 时序证明。

## 失败及夹具限制保留

第一次原生一轮是 **13/14**，完整 logs/json 保留；自定义 F407 架构失败先暴露硬编码 Board/Core/FATFS/IOC，随后正常导入回归再暴露 EIDE 多选 sysmem.c。修复前 4/4 失败、下一轮 1 failed/3 passed、最终 5 passed 均保留，负例仍要求具体诊断。

Workflow v1 字段夹具错误；v2 自有长等待停止；v3 timed faulthandler 与 Python access violation 同期；v4 QTest 忙轮询等待 600s 超时；v5/v6/v7 缺完整 Drivers/startup/linker 输入被拒；v8 直接 tuple/list 比较失败，canonical JSON 一致。v9 真实 Qt 事件循环完成四路径，最终轮从 17bc 新生成。前两轮抓图仅 processEvents 未排完延迟布局，保留异常截图路径，最终正式截图使用 QEventLoop/QTimer。Dual v1 设置路径被 workspace policy 拒绝，修正自有 settings 路径后 Dual v2 两条通过。第一轮归档误读 Ground target 的配置位置而中止，`evidence.zip` 保留为不完整归档，**唯一正式归档为 `evidence_final.zip`**。

这里没有将 Python access violation 或超时当作成功；未运行 async.exe 来产生本轮证据，也未关闭不可归属的错误窗口。新驱动设置本进程 `SetErrorMode(3)`，原生子进程有超时与自有 PID 树清理，非零/超时输出保留；没有改全局 WER。一次恢复 ASCII/no-BOM 的操作被自动审批拒绝，随后只读证明 HEAD 原版纯 ASCII、BOM 为本轮误加；证据充分后的恢复获批，本轮最终原生门禁使用恢复后的已提交模板。

## 交付、保留与未证明

`evidence_final.zip` SHA256 `114e15fb07fa2b6ee84c204fd53b0f670201dd396aa8906c3c769006cef45a58`，7,016,712 bytes，包含当前截图/CSV、所有保存的运行/失败日志、复现脚本、四个配置/文件哈希与二个双端记录、准确历史布局来源 hash、最终 emitted gate 文件。`workflow_artifacts_final.json` 是新输出 ELF/BIN/HEX/MAP 等哈希，不能与 frozen Delay10 混用。

`preservation.json` 重新核对冻结 Single 的 ZIP/ELF/BIN/HEX/MAP 全部未变；Auto 八个工程的归档内 C/H/S/LD（522 或 528 个/工程）逐文件与冻结目录一致。此范围不同于原先“609 个全部来源文件”，这里没有声称其余扩展名本轮也逐文件检查。main 未变。原始冻结 Delay10 硬件候选及 Auto 生成目录均未写。

硬件超时、无线迟到 ACK/Capability、GNSS 无接收、完整关键契约审查、真实 Windows 桌面鼠标/3D、STM32 栈余量/WCET、飞行精度与资格验证均仍未由此切片证明。父线程正在处理真实无线原始包，后续由其证据决定修复；本轮没有增加无线超时或集成未审 Baro。
