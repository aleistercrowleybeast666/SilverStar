# 安装采集运行期生命周期审查（2026-10-19，v9）

范围为当前 F407 开发配置的安装采集链路、固定 UART/SD DMA 回调、候选 TF 事务及离线故障。
复用 v6–v8 的源/依赖清单、已链接回调写入清单、MSP 模型和受保护候选；不重复宣称完成全固件证明。
未触碰公开展示文档、GUI、硬件、烧录、暂停的 M9N INT32_MIN 任务、main/tag 或推送。
默认 OFF、真实 BEGIN 的 SOURCE_QUALIFICATION 拒绝以及 wire APPLY/SAVE 关闭保持。

## 发现并修复的缺陷

原 `SystemInstallationStore_WorkComplete` 在成功提交返回后，先处理晚到的取消/30 s 超时。
真实 C coordinator + FatFs + SSOB + diskio 的两项红例均出现：**head 已是代次 1，状态却为 Cancelled、代次 0、cleanup_complete=1**。
原二进制、命令、退出 1 和完整输出保留在 `implementation/runtime_lifecycle_v9/baseline_cases.json` 及对应 before 日志。

修复只在 owning payload 的 `Modules/InstallationCapture/Src/installation_store.c`：
确认 Commit 返回成功后，按实际返回代次发布 **CandidateOnly**，晚到取消/超时不能覆盖已发生的 head 发布。
其余 Open/Write/Read/Publish 阶段仍允许取消；执行错误仍优先处理，未知 close/commit 仍保留 Store 独占。
没有声称回滚已发布对象，没有应用运行时标定，没有增加 RAM、任务、回调或协议版本。
最终 owning 文件原始 SHA-256：`1f8cb2348d38edfb2fe9c84438ae53679802c2f675585ee8719c03a07170cda0`。

修复后的实际 FatFs 两项绿例都报告 head/status 代次 1、CandidateOnly、cleanup_complete=1。
旧 work 晚到不释放新 Store token、取消时提交不确定继续保留独占也通过；原有 17 项实际存储回归通过。
仓库新增直接执行实际 C coordinator 的阶段回归：五种 I/O action × 取消/超时，另覆盖不确定提交、输入缓冲副本和旧数据。
该小回归显式模拟 I/O 返回值，真实 FatFs/SSOB 证据与之分列。

## HAL 回调生命周期与所有权

| 边界 | 已核查的当前实现 | 适用范围与限制 |
|---|---|---|
| 注册/注销 | `USE_HAL_UART/SD/TIM_REGISTER_CALLBACKS=0`；当前链接映像没有这些运行期注册/注销 API。DMA handle 的固定字段由 HAL 的 RX/TX/error 路径设置，DeInit 成功路径才将字段置 NULL；BUSY 返回保留回调。 | 安装会话不注册或拆卸 HAL 回调，不新增运行期 callback registry。不能外推到宏开启、其他 HAL 版本或未选设备。 |
| 父 handle | Core 的六个 UART、两个 SDIO `__HAL_LINKDMA` 固定写入 hdmarx/hdmatx 及 Parent；IRQ 入口使用这些静态 handle。SD BSP 的 HAL bridge 只接受 `handle == &hsd`。 | 没有短命会话地址放进 DMA Parent；任意损坏指针或未审查重配仍不受证明。 |
| UART RX | `UART_Start_Receive_DMA` 设置 ReceiveCplt、RxHalf、DMAError，abort 先置 NULL。阻塞 AbortReceive 清 RXNE/PE/ERR/IDLE、DMAR，并取消 abort callback；成功才允许原平台 restart。 | 终止安装会话并不停止底层 UART。环形 DMA 缓冲归平台，观察点只复制样本；当前 proof=NULL 拒绝真实源资格。 |
| UART error/abort | UART IRQ 的 DMA 接收错误清 DMAR 后用 Abort_IT；abort IRQ 返回 READY 后才执行对应 error callback。DMA TE 路径有计数上限；FE/DME 及平台重启路径仍依赖 HAL 状态/时钟。 | 可达目标仍是 v7 的保守固定并集；本次不向 checker 添加 HAL 回调例外。HAL 等待的硬件/时钟条件不能只靠主机证明。 |
| UART TX | 原 WriteFrameAsync 在临界区内完整复制到平台 TX ring；DMA 持有该 ring 的线性片段，完成后才 Skip 并启动下一片。 | Serial 栈上的事件行在返回后不被 DMA 借用。enqueue 成功仍不是物理送达证据；旧 SID 帧可能已在底层发送队列。 |
| 停采/取消/超时 | capture 状态先进入 Cancelling；ProducerStopped 与活动 consumer 释放后才 cleanup/release。已取得的 consumer 不被并发回收；重入 guard 失败非阻塞，producer loss 在后续入口失效输出。 | 不是 MCU 恢复协议；当前 Observe/发送是同步复制调用，没有安装会话异步 HAL callback 需要注销。 |
| 旧数据 | 帧的 receive/sample 时间必须属于当前窗口，epoch 必须匹配 frozen source；请求入口检查 SID/RID。训练/留出及新姿态不接纳缓存前窗口样本。 | SourcePush 是内部原生源入口，不携带独立 SID；未来真实 provider 必须保留原测量时间/epoch，不能把旧帧重新盖上新时间。该资格目前关闭。 |
| TF DMA | `sd_diskio.c` 的 512 B bounce scratch 与 static queue 独占；失败后 poison、STA_NOINIT、transfer_active=0，后续 init/read/write 不复用 scratch，晚到 completion 不能解毒。 | 复用既有七类 timeout/wrong-event/start/sync 故障用例与静态检查；不重复跑整个日志/存储长测。poison 需要重启恢复，不擅自执行重启。 |
| TF coordinator | 64 B work 是 guard 内的独立副本；Logger 在 guard 外执行文件操作，完成检查 token/request/action phase/offset。旧 work 不释放新 owner；不确定完成保留租约。 | 只有候选字节与 head 事务，不验证 PC 拟合的物理有效性。已发布不可变 blob 可在取消后留下；不做未经授权的清理。 |

v7 的 24 处已链接 DMA 回调字段赋值和 8 处 Parent 连接全部复用并重新核对源身份。
当前 RX/TX 完成目标为 UART/SD 各自固定 helper，半完成只有 UART，error 为 UART_DMAError/SD_DMAError，
abort 为 UART_DMAAbortOnError/SD_DMARxAbort/SD_DMATxAbort；M1 仅 NULL，当前选中路径不启用 DBM。
HAL 可执行回调字段属于已有第三方受控例外，不把它们抹掉或称为严格原版 Power of Ten。

## 新增离线证据与正式门禁

`runtime_lifecycle_v9/hal_body_host02/` 从当前保存的 HAL/UART/BSP 源中逐字提取 **8 个完整函数体**，
记录源/函数体哈希。Host facade 仅模拟寄存器、tick、DMA disable 卡住和回调计数；编译后执行十二种情形：
正常/半完成、NULL callback、异步 abort 有/无 callback、阻塞 abort 后晚到标志、UART stop 后晚到标志、
UART abort timeout、DMA transfer error、DeInit 成功清理/忙时保留、SD foreign-handle。真实 Host `-fanalyzer -c` 与全部十二项运行通过。
这不代表整份 HAL 被 Host 执行，也不代表 NVIC、DMA 总线或 IRQ 时序验证。
另有 **32 项**实际 C coordinator/UART 平台定向 pytest 通过，其中 14 项是新的阶段/数据所有权回归。
最终源码对应的实际 FatFs DLL 为 `store_host02/store.dll`；两个旧红例、两个晚到/不确定用例及 17 项存储回归均在该最终 DLL 上再次验证。

本次固件只变更上述一个 C 文件。正式栈输入审查 v23 仅登记它的确切版本及对应完整 compiler-input 配对；
依赖图、回调识别、源覆盖、256 B 上下文/最小任务余量、库栈和所有历史登记保持。
它是在红例、实际 FatFs 绿例、目标编译/真实 analyzer 和源码差异审查之后登记，不能由成功构建自动学习。
完整命令、日志、错误/修正尝试、产物哈希及来源放在同一 v9 清单中；旧失败不删除、不倒填。
实际 emitted `make stack-report` 退出 **0**，**91 项**历史绑定/输入拒绝/生成测试通过，四类输入篡改仍全部拒绝。
实际 ARM GCC 严格编译/链接、变更 TU 的 `-O0 -fanalyzer -c`、原样 Power10 和架构门禁均退出 **0**。
168 个目标对象与 v6 对照，只有 `installation_store.o` 改变；无新增/移除 text symbol，八个任务栈预算/余量不变。
主 SRAM 仍为 102292 / 102400 B，CCM 为 64896 / 65536 B；未扩栈或借用保留区。
Flash load sections 为 391592 B，比 v6 增加 8 B；不把既有未变二进制当作本修复的目标编译证据。
最终 ELF SHA-256 为 `3c307ae0143ab4e7152baedcd4ba10cb91c1200be0ace5d50049f8f23e64ff3c`。

## 仍未证明或仍需目标硬件验证

- UART/SD 硬件 abort、FIFO/DMAR/EN 与 NVIC pending 的实际交错，以及错误后恢复的目标时延。
- HAL 部分等待依赖 HAL_GetTick；较高优先级 ISR 中不能假定低优先级 timebase 推进。EN 卡住/停 tick 的完整终止界、DeInit 失败路径及整份第三方代码仍为 **NOT PROVEN**，不以十二个主机情形填平。
- 完整形式化 HAL 生命周期/任意中断交错、目标最小 SP/HWM、WCET、卡拔出/断电/控制器缓存、物理送达。
- 真实传感器 boot 身份、每原生帧、测量时间/不确定度与 raw 定义，以及标定精度、运行时应用/重启载入资格。
- 全固件关键契约与硬件/飞行接受仍为 **NOT PROVEN**；已验证软件范围不会自动开放这些门禁。

没有新增网络或权限阻断。所有临时输出在既有任务内的小型 `runtime_lifecycle_v9/`，不复制仓库/SDK/工具链，不清理历史产物。
