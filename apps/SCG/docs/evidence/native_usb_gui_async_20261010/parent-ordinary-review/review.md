# 63771a1 / bf22bdc 普通 GUI 与 F103 清理修复独立复核

审查产品提交 `63771a17e63052c238246dd4fe3fe6394de8ccec`，最终证据提交 `bf22bdcd56e76687e8be40d5f221cb3c29668ec1`。bf22 相对 637 只有 SCG docs/evidence 修改，产品代码相同。本次是受委派的普通产品只读 QA，没有重启被停止的 b66 独立安全审查，没有 malformed USB/替换 owner 测试、原生桌面控制、硬件/串口/探针、烧录、merge 或 push。仅在本任务目录建立小型 Host/offscreen Qt 上下文。

## 结论与新问题

**发现一个 P2 GUI 响应性问题；没有新 P1。先前 F103 Reset/Disconnect 丢失清理错误的 P2 已在 owning generator 和 fresh output 中修复。** 编译、普通 GUI 最终结果与生命周期功能的记录成立，但“已有 GUI 工作流可响应完成”的验收还应修复以下 P2。

### P2：完整 native Plan/文件审计仍同步运行在 GUI 刷新中

定位：`apps/SCG/src/silverstar_fccg/ui/main_window.py:884`、`:3491`、`:3495`，以及 `app/usb_ground_flow.py:85`、`:174`。

触发：已保存并构建的合法 F103/C071 候选，存在 architecture/artifact 两条质量记录，打开/刷新项目，或者 Build 成功后的 `_UsbGroundOperation_Request` completion 回调（main_window.py:3671）调用 `_Project_Refresh()`。该回调由 `_Task_Finish` / `_TaskOutcome_Dispatch` 在 GUI 线程派发。一次 `_Project_Display` 调用完整 `UsbGroundOutput_Get`，随后 `_TargetQualityResults_Refresh` 再调用一次；每条质量记录又由 `UsbGroundQualityHash_Get` 重跑完整 Output_Get。Output_Get 开头重新生成/审查 native Plan，之后读取并 hash 所有候选源、产物及 native 输入。这些工作都没有在刷新路径上交给 worker。

独立复现：对 **已完成 ug08 的合法输出只读**，使用自己的 FccgService、SettingsStore 和 `QT_QPA_PLATFORM=offscreen`，调用实际 MainWindow `_Project_Refresh()`；设置 20ms Qt 定时器检查事件循环。F103 **6.750 秒**、C071 **9.262 秒**，刷新期间 timer ticks 均为 **0**，返回并处理事件后均恢复一次 tick。没有生成新工程、拷贝 vendor 或执行编译。细分只读计时：单次 Output_Get 为 1.448/2.262 秒，两条质量记录 hash 额外 2.864/4.360 秒；与重复调用源代码相符。该问题随普通候选状态刷新反复出现，期间不能处理输入、进度绘制或取消。不是硬件风险推测，也不是旧测试等待超时的重述。

最小修复：把完整 Plan/源/产物身份检查放入现有 worker，使用不可变模型/指针身份快照；结果返回时校验仍属于当前模型后一次性更新 UI。一次刷新中的多条质量记录共享同一已验证输出/文件清单，不再逐条重跑整个 Plan。保留所有身份、路径与 hash 检查，不能靠删检查、无身份长期缓存或 GUI 内 processEvents 重入来修复。增加实际 Qt timer/输入响应测试；等待时仍可取消，成功后 stale ELF 拒绝应继续成立。

复现程序：`reproduce_refresh.py`；结果：`ordinary-offscreen-refresh.json`、`ordinary-read-timing.json`。offscreen 上下文未运行工具探测，因此其 Build button false **不能用作新的按钮功能缺陷**；本复现只评价实际候选刷新和事件循环。

## F103 原 P2 修复核对

`generator/native_control.py` 对 F103 `USBD_LL_Reset`、`USBD_LL_DevDisconnected` 的 class DeInit 调用替换为捕获结果并返回 OK/BUSY/FAIL。这是 owning generator 修改，未仅修 disposable 输出。fresh ug08 F103 `HardwareGenerated/ReviewedNativeControl/Core/Src/usbd_core.c:464` 与 `:594` 具有相同传播逻辑。

ul17 的 F103 21 个、C071 19 个 actual generated C/header 输入 hash 与 fresh ug08 字节全相同。使用这些 **fresh ug08 源码**在自己目录重新编译既有合法 Host harness，各目标 17 个原场景全部执行成功，共 34 次。包括 reset-close-failure、disconnect-close-failure：失败不返回成功，保留分配/类资源和已失效 session，写入 BUSY，Stop 重试仅释放一次，重新配置使用新 session；也包含正常 TX/ZLP、旧 buffer 生命周期、Rx 重挂载、stop/deinit、初始化失败及 suspend/resume/reset/disconnect。没有追加被停止的安全探测。命令、工具版本、源码 hash、完整 stdout/stderr 见 `independent-lifecycle/evidence.json`，编译日志原样保留。Host 有上游 unused-parameter 警告，不能据此称全部 Host 编译零警告。

LL/PCD、Cortex intrinsics、UID 与 allocator accounting 为显式 Host 替身；目标 HAL/PMA/真实 IRQ 并发未执行。此结果足以关闭原普通清理错误返回问题，不能扩展为完整控制器或异步交错证明。

## 最终证据独立核对

- ug08：637 clean，12 passed，0 skipped；导入/保存/重载/候选 Export、实际 worker Build、取消进度、配置拒绝及旧 ELF 被拒绝。其成功 Build 测试通过 actionRequested signal 而不是物理点击按钮，不能单独证明所有 enablement 状态。所有 6 个回执内嵌源 hash 与固定 Git 对象一致。
- ue01：637 clean，2 passed，0 skipped；真实普通 `ProjectDraft_Create` 默认模型，原 USB 下拉框、import-directory 按钮点击、保存/重载、generate 按钮点击。没有加载私有已绑定模型；独立测试文件 SHA 与 command receipt 一致并保存在 final runners。没有单独 ARM Build。
- ul17：f91 clean，2 pytest tests / 34 合法场景执行；f91 与 637 产品源相同。ugr02 99 passed 是单独保留回归结果；没有与 ug08 拼成一个全仓库套件。
- F103：339/339 实际命令 exit 0；54 个实际 C `-fanalyzer -S` 编译及 analyzer 链接；不是 `-fsyntax-only`。127 generated、555 recorded artifact、114 native input hash 全部匹配当前已完成输出，52 个 source-snapshot 模块对应固定代码。
- C071：351/351 实际命令 exit 0；56 个实际 C analyzer 编译及链接；273 generated、575 recorded artifact、111 native input hash 全部匹配，160 个 source-snapshot 模块对应固定代码。
- 两款保存模型的 canonical model digest、文件 SHA、backend/compiler/index receipts、normal/analyzer ELF hash 均一致。部分 checkout Python 是 CRLF，Git 为 LF；审计保留原 raw SHA，并验证 normalized source 与固定 Git 字节内容相同，没有把这些差异误记为未说明 dirty 修改。
- ugg02：**ug08 的两个新输出**各 architecture、ordinary Host、artifact、原样 Power10 共 8 条命令 exit 0；8 个完整 gate log SHA 都匹配回执。ug07 11 passed/1 failed 历史被保留，不能改称当次全通过。
- final evidence bf22：manifest 内 744 个文件 hash 全匹配，Git 保存的 745 个文件字节全匹配；manifest 不包含其自身。bf22 相对 637 没有非 docs 产品修改。

完整独立记录：`audit-initial.json`、`archive-audit.json`。F103 normal/analyzer ELF SHA 均 `fde957fe80fdf038f4c5c6640bc851446e8ef7acb7605258fd94dca87c81240b`；C071 均 `ee90e6871f5f5723982701e8b6783dd2638f4bd76f352f5099d2d38e031028b9`。

## 实际可用性与验收边界

普通软件入口已接入原 MainWindow/FccgService，首批只接受 exact F103C8T6/72MHz 与 C071FBP6/48MHz、指定已 pin native 工程、固定 SPI1/radio GPIO、单 radio0 E28/SX1281。Build 不需要 Make，但需要 ARM 工具；每次候选操作仍需要可用且字节相符的独立 SDK header，其位置由文档所述环境变量或默认机器路径给出。这是有前提的首批候选软件路径，不是任意 CubeMX 工程的普遍支持。更换配置/工具改变模型身份时旧候选失效，需重新生成；未将严格身份检查当作缺陷。

UI 只改两个既有逻辑文件，24 个其他 UI 文件不变；constructor/layout/style AST 与 baseline 一致。已记录的 Ground/Build 两张 offscreen1280x820、普通未绑定参考模型 settled 图片逐像素相同。此视觉证据不涵盖所有候选状态、实际桌面字体/文件对话框；有中文缺字环境记录。Flight 默认与旧 UART 路径不应从候选分支推定改变，本次差异和保留回归未发现这类新变更。

原始 native HAL/CMSIS/startup/linker/PCD 等仍在导入身份中；C071 byte-pinned companion 有明确所有权与 license/patch provenance。此前 source closure 审查不在本轮被扩大成新的安全审查。当前 formal release 仍 BLOCKED，b66 独立审查 NO_PASSED_OUTCOME。manual critical-contract、whole-program stack/WCET、原生 PCD/PMA/IRQ interleaving 和硬件/飞行验收未证明；Power10 文本检查 exit 0 不能关闭这些事项。F407 未新放行。它们不是本次普通软件 P2 的替代原因，也没有被标为 PASS。

## 最终交付与本地合并建议

已读取 `usb-gui-final-delivery.json`：实际 HEAD 是 bf22，git status 确认 clean；交付 JSON 中的 report 和 manifest SHA 均与实际文件一致，见 `delivery-audit.json`。此前的 745 Git 字节核对已包含最终 receipts/source-snapshot。

现有 Import / Ground Generate / Ground Build 是逐步候选入口，Generate All 与正式发布仍 blocked，这一说明与代码相符，未误导为一般 CubeMX/硬件/正式发布完成。硬件未测与明确实验状态本身不妨碍把候选软件集成本地供用户验收。但**当前仍有已复现的新 P2**，不建议据“无新增 P1/P2、普通 GUI 已完成验收”合并。应先修复并复验事件循环响应，再保留这些候选/未实测门禁进行本地合并。此建议不是批准正式发布，也未执行 merge/push。

C071 10.47 秒 artifact audit 成功支持旧 10 秒总等待不足；它不反驳同期另行复现的同步 GUI 刷新阻塞。提高测试等待预算不能替代事件循环响应性修复。
