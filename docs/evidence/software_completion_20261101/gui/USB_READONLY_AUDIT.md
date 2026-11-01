# §14 原生 USB 未完成项：只读核对

2026-11-01；核对起点 `8b028f280ba01dce0efc697479ef99ec143f7456`。本记录没有运行 USB 审查、畸形输入、构建或硬件操作，也没有改变 USB 源码或正式放行门禁。它定位下一步工作，不能代替安全验收。

## b66 中止原因的证据边界

`apps/SCG/docs/NATIVE_CLASSIC_CDC_RUNTIME_20261010.md` 原文是“b66 的独立安全审查被平台机制中止，没有审查结果，没有重试”。`NATIVE_USB_FIRST_BATCH_BINDING_20261010.md:39` 又记“须由合法途径处理”。现有被读取的文档、绑定摘要、b66 Git 文档没有该次审查原始拒绝文本、动作、工具回执或中止错误。因此目前只能确认 **NO_PASSED_OUTCOME；具体平台中止原因未知**。不能把它认定为某种安全分类，也不能从一次没有结果的审查推导永久禁止，或直接改成已通过。

两件相邻但不同的历史事件不可混用：

- `apps/SCG/docs/evidence/native_usb_gui_flow_20261010/history/USB_GUI_WIRING_BLOCKED_20261010.md` 明确记录 GUI 写入在执行前遭 approval 拒绝，原因是旧 GUI freeze 与授权来源；随后直接用户授权解决。该文明确说这与 b66 独审是两件事。
- `git show b66f142:apps/SCG/docs/GROUND_USB_OWNER_BOUNDARY_20261009.md` 记较早的一次测试执行因 EDA 范围限制被拒，直接用户授权后同命令获准。这发生在候选等候独审之前，不能当作其后的独审中止原因。

另读到原任务 `C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-formal-validation/pause-ep0-20261009.json`，但它固定较早 `842faf7` 的开发暂停，不是 b66 独审回执。没有改变或重新执行这些历史动作。

## 必须分开的两条软件路径

| 路径 | 当前入口与事实 | 未证明内容 |
| --- | --- | --- |
| 精确目标私有 Ground 候选 | `app/usb_ground.py`、`app/native_ground.py`；F103/C071 首批，F407 独立私有路径。`generator/native_ground.py` 确实组合 `NativeF103Control_Integrate` / `NativeF407Control_Integrate`；`native_control.py`、`ground_usb_control.py` 保留已修 EP0 长度/结果/来源和普通 lifecycle 派生。C071 保留 pinned companion 身份。 | 不能把旧原生 EP0 长度缺陷无条件描述为这些当前精确派生的尚存缺陷；仍缺完整 EP0、所有异步交错、人工 critical contracts 和 whole-program stack 的正式验收。`app/service.py:_NativeFormalGeneration_Reject` 与 `usb_ground.py:C071_LIMITS` 仍阻止正式生成。 |
| 通用 experimental inspect/prepare/build | `app/native_usb.py`、`generator/usb_cdc_integration.py`、`generator/native_usb_graph.py`、`build/native_usb.py`。与上面的精确候选不是同一来源图或证据。 | build receipt 当前明确 `power10: NOT_RUN_BY_THIS_BUILD`、`stack_wcet: NOT_PROVEN`。`USB_CDC_COMPATIBILITY_20261015.md` 保留 F103 7 / F407 10 失败组和 native mixed-owner 诊断；此只读检查没有重跑，不能标为当前新复现或已关闭。 |

## 不依赖实物即可继续的明确工作

| 项目 | 具体源码 / 现有测试入口 | 需要补的证明 |
| --- | --- | --- |
| EP0 请求/继续/状态阶段 | `generator/ground_usb_control.py` 的 `PcUsbControl_*` 模板；`generator/native_control.py`；`test_native_control_normal.py`；b66 Git 文档 `GROUND_F103_F407_EP0_REPAIR_20261009.md` | 已有 GET/SET 长度、回调/LL 失败、复位/重配的有限证据不等于完整 Chapter 9。逐路径审查请求字段、对象容量、data/status continuation、失败后状态和旧 command retirement；对实际生成源保存正常/错误路径反例。原文提及完整 51 项矩阵，但当前检查未取得其完整逐项验收表，应找回该表而非猜计数。 |
| 异步 buffer/session/关闭所有权 | `generator/native_usb_data.py`、`native_usb_indexed.py`、`native_usb_indexed_ll.py`、`usb_cdc_integration.py`；`test_usb_lifecycle_normal.py`、`test_native_usb_data.py`、`test_native_usb_ll.py`、`test_native_usb_indexed_ll.py`、`test_ground_usb_review_boundaries.py`、`test_usb_transport_integration.py` | 对 main 与 USB IRQ 共享状态、pending TX、ZLP、Receive rearm、Stop/DeInit 失败保留、late completion、suspend/reset/reconnect 建立明确顺序/线性化点。Host LL/PCD 替身只能证明对应模型，尚不能证明所有实际 HAL/IRQ 路径。静态穷尽与受控故障模型属于软件工作。 |
| 人工 critical-contract 验收 | 实际源图所选 first-party、mixed-owner 衍生、HAL/USB/库和回调，结合 `Generated/usb_control_manifest.json`、source graph、原件/patch/hash | 为每个 safety-critical 边界记录输入/状态契约、真实失败处理、READY 撤销、并发快照一致性和被调用者结果处理。文本 PoT exit 0 不能代签这一项，不能靠增加无意义断言消除 NOT PROVEN。 |
| whole-program stack | fresh exact candidate 的 ELF/map/disassembly、`.su`、已链接 library 与 callback/vector；现有 `build/native_usb.py` 只收集记录 | 覆盖 main/MSP、完整直接/间接/尾调用、库/动态帧/递归、可能抢占的 ISR 层级与 Cortex exception frame；各预算与上界独立比较。静态软件证明可先做；RAM spare、单函数 `.su` 和局部 frame sum 都不能直接算安全余量。 |
| 通用路径现有门禁失败归因 | `apps/SCG/docs/USB_CDC_COMPATIBILITY_20261015.md` 的 “All 17 remaining groups”、`gate-attribution-final.json` 历史索引 | 先冻结当前图并复现，不移用精确私有候选的 PASS。记录哪些项已由后续派生解决，哪些 native/mixed-owner `USBD_CDC_Setup`、EP0、descriptor walker、配置条件、永久 loop、`sysmem` 仍被编译/扫描；修复归拥有者且不削覆盖。旧 F407 FIFO 原件与后续独立 corrected reference 必须分别标识。 |

当前已有软件范围还包括 `docs/evidence/treediagram_20261101/native-v2.log` 的完整 **31 passed / 586.73 s**（原报告固定的那次源码/构型），以及 `apps/SCG/docs/NATIVE_USB_LIFECYCLE_NORMAL_20261010.md` 和 `NATIVE_USB_GUI_ASYNC_20261010.md` 的历史正常序列、GUI 异步/取消/身份验证。它们没有关闭上表所有义务，不能拼接成一次新的全套通过。

## 真正需要目标环境或硬件的证据

物理 USB 枚举/主机驱动兼容、供电/PHY/时钟精度、插拔和 suspend 电气行为、实际 PMA/FIFO/PCD、IRQ 延迟和目标最坏负载时序、USB 与无线同时工作，仍需相应目标测试。MCU WCET 可以先做静态模型/路径边界，但主机运行时间不能替代目标测量。stack 高水位是补充观测，不能替代软件完整上界。这些硬件项应单列，不能用它们掩盖上表可继续的软件工作。

正式发布依然 BLOCKED。本次没有结论足以放开它；下一轮应先确认实际被中止动作的原始回执与适用授权，然后由合法路径继续明确的软件范围。
