# f61cbd8 / 5b99438 普通异步 GUI 独立复核

代码：`f61cbd851b8ac32b865deb1a3997058685dfebbd`；最终证据：`5b99438ba4005ea02935e9734307e749e2e758e7`。独立核实 worktree clean，证据提交相对 f61 只有 docs/evidence，没有后续产品代码修改。审查固定 Git 源码、完整增量、最终 report/delivery JSON、receipts/source-snapshot 与实际产物，另进行自己的只读 offscreen Qt 测试。没有执行真实导入/生成/编译/清理、复制 vendor、操作原生桌面/硬件/串口/探针、merge 或 push；没有重新进行被停止的 b66 安全审查。

## 结论

**原 GUI 同步审计阻塞 P2 已闭合；本次普通产品增量未发现新的 P1/P2。可以本地合并，作为明确范围的实验候选供用户进行软件验收。** 这不是正式发布批准，也不是安全/硬件验收。首批 exact F103/C071、逐步 Import → Generate → Ground Build 入口与 Generate All/正式发布 BLOCKED 的说明应继续保留。F407 和未支持配置没有因本次复核获得放行。

同步旧有页面填充仍存在约 0.64 秒的成本，并跑记录超过原 0.75 秒阈值。这一性能限制尚未消除，不能报告成任意负载下整个 GUI 刷新都达标。但它与此前在 GUI 线程重复执行完整 native Plan 和全部文件审计、阻塞 6.75/9.26 秒的 P2 有明确区别；未见这次调度修改新增的同类阻塞。

## 原 P2 的独立复现

沿用之前实际 ug08 F103/C071 合法 compiled 候选与保存模型，独立运行当前 `test_usb_gui_async.py` 的只读部分：**12 passed，4 deselected，47.87 秒**。deselected 的四项会调用实际导入，为避免写作者原缓存没有独立重跑；并未称其通过。本次 fixture 核对两个原输出的 compiler/backend receipt 及 normal/analyzer ELF 在运行前后不变。没有采用生成替身来代替完整 Plan。

| 目标 | 本次同步页面填充 | 完整刷新总时间 | 审计期间 Qt ticks | 后台最大 tick 间隔 | 完整 Plan |
|---|---:|---:|---:|---:|---|
| F103 | 0.646s | 3.057s | 71 | 0.090s | 1 次，非 GUI 线程 |
| C071 | 0.642s | 4.411s | 118 | 0.078s | 1 次，非 GUI 线程 |

后台间隔从同步填充返回后计量，没有把前面的填充成本藏入零时间。真实 GUI completion、原两条质量记录、无 stale 状态、候选 generated 标志均断言通过。原来的 6.750/9.262 秒、timer ticks 为 0 的复现见前轮 `gui-63771a1-review/ordinary-offscreen-refresh.json`；本轮使用相同已完成候选，结果可比较。

命令、固定 test SHA、起止时间、结果与量化数据见 `independent-async.json`，完整日志 `independent-async.log`；可重跑程序 `run_readonly_async.py`。

## 请求归属、取消和关闭

源码检查 `main_window.py` 的 `_UsbGroundRefresh_Request/Start/Invalidate`、`_UsbGroundRequest_Current`、`_Task_Finish`、`_Task_Cancel`、`closeEvent`，以及 `usb_ground_flow.py` 的 `UsbGroundRefresh_Inspect`：

- 每次请求 deep-copy 模型和项目；单 shot QTimer 属于窗口 QObject，合并尚未执行的请求。完整审计进入现有 Task_Run/FunctionWorker，一次结果中的各质量记录共用已读取的 Tools 字节。没有新增持久信任缓存。
- 返回时同时核对 epoch、项目、完整模型以及关闭状态。新请求撤销旧 epoch，并取消旧 refresh worker；旧结果不能填写当前项目。检查保留 pointer 前后身份和既有全部 SDK、native、model、receipt、source/artifact hash 校验。
- 取消清除 pending 并停止 timer；正在运行的 native Plan 本身没有中途取消点，但其前后及逐个 hash/Tools 文件处检查取消，现有实际 Plan 耗时内终止。未证明任意慢磁盘或未来输入上都有固定取消延迟。
- close 时保留窗口直到自有 worker 结束，再关闭；已关闭/销毁窗口不会启动排队 refresh。没有在新实现中发现跨线程 QWidget 调用。
- 实际 artifact action 的完整验证也进入 worker，使用当前请求归属后再展示结果。Clean 的删除仍限于经验证候选 build 输出；本次未执行删除。

自己的上述 12 项中已实际执行 pending 合并、切换为新项目后丢弃旧结果、按钮取消、活动 worker 关闭、QObject 销毁、排队 timer 关闭、artifact 审核非 GUI 线程。另执行 **4 passed / 8.52 秒** 的 `test_late_callbacks_readonly.py`：实际 import request/Qt worker/成功或错误分发，项目切换后旧成功和错误均未覆盖新项目。该补充使用返回值替身避免原缓存导入写入，只证明 callback 归属；不把它称为再次验证实际 CubeMX 导入。作者 ur06 的四项实际 late-import 仍单独在最终 16 项记录中。

legacy 非 USB import 保持原 `_GroundCubeMxImport_Complete` callback API。f61 恢复这一点后的 99 项保留回归实际通过；之前 ugr03 的 98 passed/1 failed 历史未被删去。

## 并跑失败和性能边界

独立读到 ur05 原完整失败：**14 passed / 2 failed**，均失败于同步 `_Project_Refresh` 返回时间 <0.75s，F103 0.977s、C071 0.941s，未进入后台 cadence 断言。ur05 和 ur06 使用同一个 clean f61，test SHA 相同；没有修改代码或阈值换绿。ur06 单独执行 16 passed；本次独立只读复跑也满足原同步阈值和后台 cadence。

25 个其他 UI 文件 Git 对象未改。新增六条 owned timer/worker 初始化后，移除仅这六条的 constructor AST 与原版本相同；既有 widget/layout/style 构造没有改动。`_Project_Display` 原填充路径除移除审计和提交刷新外保持。结合明确测量，这支持“重复完整审计已迁出，而旧页面填充仍随并跑负载变慢”，不支持“所有 legacy view 填充已证明永不阻塞”或“并跑全部性能阈值已通过”。这项遗留性能限制应保留在用户验收说明中，不能用一次 PASS 覆盖失败。

ui/callback/source 边界独立记录见 `scope-audit.json`。

## 真实 Build 按钮与软件证据

当前 fixed `test_usb_gui_flow.py:139–154` 先选择真实 compiler 路径，点击原有 detect button 并断言真实 detector 返回 compiler found，再点击 Generate，等待审核后断言 Ground Build enabled 并 `.click()`。未通过直接 action signal 或伪造 ToolStatus 替代按钮启用。本次只读复核没有重复 ARM 构建；核对的是作者 ua04 的实际按钮、worker、全新 compile receipts、命令和响应记录。

ua04 两款真实 Build 总窗口约 68.406/73.373 秒，有 3288/3610 次 Qt ticks，最大间隔 0.720/0.622 秒；后续 artifact/quality 动作和 stale ELF 拒绝断言均实际通过。ua03 的两个 Build-button 失败来自当时测试未调用工具检测，原记录保留；f61 增加的是测试真实 detect-button 路径，没有使 compiler 未检测也能构建。

最终四组分别是 ua04 12 passed、ur06 16 passed、ugr04 99 passed、ul19 2 pytest tests / 两组各 17 个合法 Host lifecycle scenarios。这些不是一个全仓库或并跑全套 PASS。pytest cache_dir warning 与 Host 上游 warning 按其 scope 保留。

## 归档、来源和产物身份

独立验证 **962 个 manifest 文件哈希、963 个保存的 Git 文件字节全部匹配**；final delivery report/manifest SHA 与实际文件一致。所有 fresh source-snapshot、saved model、backend/compiler/index receipts 对应 code f61，dirty diff 为空，Git 字节和 receipt 来源未发现未说明差异。部分 checkout Python 为 CRLF，而 Git 为 LF；审计保留 raw SHA 并分别证明 normalized 内容相同，未把它冒充原始字节相同。

| fresh 输出 | 实际命令 | 真正 C analyzer 编译 | generated/current 与 archive | recorded artifacts | native 原件 | source snapshot |
|---|---:|---:|---:|---:|---:|---:|
| F103 | 339/339 exit 0 | 54，`-fanalyzer -S` | 127 / 127 全匹配 | 555 全匹配 | 114 全匹配 | 52 模块对应 f61 |
| C071 | 351/351 exit 0 | 56，`-fanalyzer -S` | 273 / 273 全匹配 | 575 全匹配 | 111 全匹配 | 161 模块对应 f61 |

没有 `-fsyntax-only` 被当作 analyzer。两款 normal/analyzer ELF 及全部 recorded artifacts 都对应本次新命令；ELF 与之前相同符合本次没有 firmware generator/C 改动，不是拿旧 binary 冒充新运行。normal/analyzer F103 SHA 均 `fde957fe80fdf038f4c5c6640bc851446e8ef7acb7605258fd94dca87c81240b`；C071 均 `ee90e6871f5f5723982701e8b6783dd2638f4bd76f352f5099d2d38e031028b9`。

每款 architecture、ordinary Host、artifact、原样 Power10 共 8 条 emitted gate 命令 exit 0，完整 log SHA 均与回执相符。ul19 actual generated F103 21 个/C071 19 个输入哈希与 fresh ua04 也全部一致，各 17 场景 exit 0；原 F103 Reset/Disconnect P2 修复没有被撤销。此轮目标 firmware 源未改，因此没有再次重跑已经独立通过的 34 个 Host 场景，仅核实本次鲜生成字节与回执。

完整审计见 `receipt-audit.json`，程序 `audit_receipts.py`。已确认审查结束后 worktree 仍 clean。

## 本地合并和未验收事项

在保留 exact-target/工具/SDK/native profile 前提、逐步候选入口、当前性能限制及明确实验/未实测标识的前提下，**建议允许本地合并供用户验收**。没有依据把关闭这个普通 GUI P2 变成正式发布、通用任意 CubeMX 支持、F407 放行或硬件通过。Flight 默认、UART 的既有路径没有此次 firmware 修改。

formal release 仍 BLOCKED，b66 独立安全审查 NO_PASSED_OUTCOME；manual critical-contract、whole-program stack/WCET、目标 PCD/PMA/IRQ 并发、物理 USB/硬件/飞行验收仍未证明。工具通过只覆盖其实际记录；本次也没有用这些 NOT PROVEN 项自动判断安全或无问题。上述未测边界不是额外要求用户先做硬件才能集成本轮普通软件。
