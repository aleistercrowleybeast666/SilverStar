# 普通生命周期 QA — 80db263 / c55bdc3

结论：发现 1 项 P2，F103 正常 Reset/Disconnect 在 endpoint cleanup 返回失败时丢失错误结果；原有普通 24 场景通过不能证明这个组合已闭合。无新 P1。此前 C071 保存项目追溯 P3 已修复并核对。正式 USB、安全审查及硬件验收仍未完成，本轮不建议将 F103 普通生命周期描述为全部闭合。

固定范围：源提交 80db26338bba77950a9b8e9bbc03d8a77e33567b，证据提交 c55bdc3a16514f62c9a92b6a7582a7bbcdf132a3。所有仓库内容均由 git object 精确读取，未读取当前 GUI 工作树。没有改代码、merge/push、烧录/START、串口/探针，没有畸形 USB、alternate-owner 表达式或受阻 b66 安全审查复试。仅将小型已归档 Host C/H 与审查脚本写入独立任务目录并执行普通公开 API 场景。

P2：F103 public Reset/Disconnect 报成功，但 class cleanup 实际失败。

- 实际构建文件：final/STM32F103C8T6/HardwareGenerated/ReviewedNativeControl/Core/Src/usbd_core.c:442–467（USBD_LL_Reset）和 :588–594（USBD_LL_DevDisconnected）。前者 :462–464，后者 :592 调用 class DeInit 后丢弃返回值，最后固定返回 USBD_OK。
- Owning generator 为 apps/SCG/src/silverstar_fccg/generator/native_control.py:39–54 的 F103 ordinary control/bulk composition；当前复制修复 Init/Start/ClrClassConfig/Stop 并修复顶层 DeInit，却仍保留了这两个原生 core 的错误返回丢失行为。它在 838/e176 已存在，本次是在 80db/c55 普通增量 QA 中首次确认，不能称为新引入回归。
- 触发：合法已配置 FS CDC 会话、正常待完成 64-byte TX，然后一次 USBD_LL_CloseEP(IN) 返回 USBD_FAIL；调用标准 USBD_LL_Reset 或 USBD_LL_DevDisconnected。没有非法 setup、伪造 owner 或改设备对象。
- 独立结果：两次 F103 都打印 cleanup_status=0、allocated=1、frees_delta=0、state=1（DEFAULT）、class_retained=1；原 session 失效、写入 BUSY，随后“公共返回必须非 OK”的断言失败，两个进程 exit 3221226505。该退出是 Host 测试断言，不是目标 MCU 恢复/故障证据。class/TX 的保留与写入阻断在断言前通过；问题是调用者收到成功，无法据 status 分辨尚需 cleanup retry。补充场景在这个断言处结束，未把未执行的 F103 后续 retry 计为通过。
- 同一固定实例、相同合法流程及相同 CloseEP 一次失败，在 C071 两次都返回 USBD_FAIL（3）；class 保留、写入阻断、随后 USBD_Stop 清理重试、重新配置和 DeInit 都通过。
- 最小修复：在 owning F103 generator/derivative 的这两个普通 core 路径传播实际 class DeInit 结果，保留原有 reset/disconnect 状态和资源保留路径；不要只补改一次性生成文件，也不要把正常 LL 故障替换为 fatal assertion。新增这两个普通 regression 后，验证 fresh generated 输出以及受影响 Host/ARM/analyzer/gate。无需全平台重构或重启受阻审查。

独立实际运行：

- 使用 c55 归档 host/F103 与 host/C071 的原始 normal.c、真实生成 core/ctlreq/ioreq/class/interface/descriptor/stream C，以及归档 headers、Host LL/Cortex/UID/static-allocation substitutes，fresh GCC 编译。两目标分别执行 complete-zlp、unconfigure、reset、disconnect、stop、deinit、close-retry、deinit-close-retry、init-open、init-prepare、tx-failure、rx-rearm：24/24 场景 exit 0。
- GCC 16.1.0，-std=c11 -O2 -Wall -Wextra -Werror=implicit-function-declaration -Werror=incompatible-pointer-types。F103 编译保留 1 条、C071 3 条 vendor unused-parameter warning，与作者 Host 记录相符；没有声称 Host 零警告。
- 另 fresh 编译补充 Reset/Disconnect + 一次公开 CloseEP failure 两个正常组合：F103 0/2 通过，C071 2/2 通过。仅修改任务目录 harness 增加合法调用和错误返回预期，原 core/class/adapter/header 字节未改，未弱化原断言。
- 本轮没有运行 pytest 22/67 全组，没有重新 ARM 链接或重跑 8 个 gate；没有执行当前新增 GUI 或其他工作树文件。作者 ul14 是 2 个 pytest tests × 12 个 named scenarios，不能说成 24 个独立 pytest tests。

固定归档和构建证据：

- verification 列出 604 项，全部在精确 c55 Git 树存在且 SHA 相符；目录共有 605 Git 文件，多出的一个是 verification 自身。80db 与 c55 的非文档源码 blob 无差异。
- ul14 2 passed/0 skip（15.88 s）、uc09 22 passed/0 skip（170.91 s）、ucr04 67 passed/0 skip（81.89 s），均记录 80db；各有原 pytest cache_dir 配置警告。归档保留 ul07/ul09/ul10 正常 pre-fix failure 与其他 Host fixture/intermediate history，本轮未独立重跑那些历史失败。
- F103 compiler receipt 339 个命令均 exit 0，54 普通 +54 实际 analyzer C 编译；C071 351 命令，56+56。两份 receipt compiler warning 列表为空；记录的 8 项 ucg03 architecture/Host/artifact/PoT exit 0。它们不覆盖本轮发现的错误返回组合，不构成 critical-contract 或全生命周期 PASS。
- 归档内 F103 41 项 generated-content 与112项 retained artifact，C071 44/116 项均匹配对应 compiler receipt SHA（retained artifact 是两个 ELF/map 与 .su）；其余 receipt 所列 vendor/intermediate objects 不在此归档，本轮没有读取 temp 路径来扩大结果。所有604清单项另有完整 Git blob SHA核对。
- F103 21项、C07119项生命周期 Host C/H 输入全部匹配 final compiler receipt 的 generated/original SHA，确实来自最终生成输入；并非另写一个只测试编译的替代 USB 实现。
- 两目标 final Make 的 C_SOURCES 与实际 graph 完全一致，无重复 source 路径，ABI probe 和 _sbrk 链接要求反映在实际构建图。C071编译两项 ReviewedC071Lifecycle class/core derivative，原 companion 源及 narrow patch provenance 保留；C071 Export generator 已用 final ownership graph 生成 Make，包含 lifecycle/HAL/no-heap owner。

C071 追溯 P3 关闭：

app/usb_ground.py:394–396 增加 project_root、runtime_project、runtime_project_sha256、snapshot_root；shared native_compile.py:299–301 保存 runtime/snapshot 字段；updated build index 同时保留 backend receipt SHA。此次 saved_project/SilverStar.ssproject 已在固定归档。归档保存文件的实际字节 SHA 同时匹配 compiler/backend/index，规范化 model SHA 同时匹配两层 receipt，路径彼此一致，backend 的 compile receipt SHA 匹配实际归档字节。此前只能从三个同内容副本猜源路径的问题已消除。

源码版本核对的范围：两份 compiler receipt 记录 80db 与空 dirty diff，内嵌编译引擎、13项既有 generator 源与精确80db匹配；uc09 command另内嵌9项源记录且匹配。完整 source-snapshot.json 未被纳入c55归档，新的c071_lifecycle/native_control完整模块不在这些嵌入清单中；其精确80db文件可读，最终生成 C 输入也已用SHA绑定并独立运行。本轮不宣称完成每个实际Python模块原始工作树字节的独立核对。建议额外保留构建时已经生成的两份 source-snapshot.json，避免以后依赖可变temp目录；这是证据保留边界，不是检测到源码不匹配。

未覆盖与验收边界：

HAL/PCD/PMA/真实IRQ均为Host substitutes；公开 LL_Stop/LL_DeInit 自身失败在原24场景中未注入，LL_Reset EP0 OpenEP失败、suspend/resume、所有IRQ/main并发、真实host-driver行为和物理取消未由本轮证明。普通单FS/单class配置的成功路径与已列出的错误路径有对应结果，不能扩展到任意芯片/配置。完整EP0/异步生命周期、人工critical-contract、whole-program call graph/stack/WCET、物理时序/电源和硬件仍 NOT PROVEN。被平台停止的b66独立review仍 NO PASSED_OUTCOME，本轮没有复试或替它宣布PASS。

GUI接线是后续另一个增量，固定80db仍有报告列出的旧入口和progress/cancellation契约缺口。本轮没有评判正在变化的GUI文件，没有把backend+Host通过称为可用GUI流程。F103 P2修复前，不宜完成普通生命周期闭合验收或据此提前merge。

支持证据：audit.json；independent-host/evidence.json（24项）；independent-public-return/evidence.json（两目标对照）；reviewer-attempts.json。所有setup失败也保留：一次harness缩进插入标记不符、一次审查脚本尝试读取未归档source-snapshot；都发生在准备阶段，没有被计为产品通过或目标故障。

