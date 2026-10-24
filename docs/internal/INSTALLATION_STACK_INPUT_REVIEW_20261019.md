# 安装采集：编译输入身份审查（2026-10-19，v22）

本次只登记当前开发分支、v6 已编译 F407 Release 配置的确切输入。基准为
`7896c1d09a7f9138c41cdac35beef38347d94b78` 加保留的脏工作树；不是稳定 main。
审查材料为 `.work/dev013_installation_followup_20261019_v1/implementation/` 下的
`callback_inputs_review_v6.json/.diff`、`project_payloads_v6.json`、`ab_ON6`、v6 回归和
`msp_isr_v7/disassembly.txt`。旧 `stack_gate_04` 的退出 1 原样保留。

## 本次登记覆盖什么

42 个当前源码/头文件身份是**存在但尚未登记的版本**，不是缺文件。已逐组阅读完整新增实现或相对于
受保护候选的完整差异，并检查实际 `.d` 输入闭包、链接后调用点与当前拥有者 payload/renderer。
确切路径、原始及规范化哈希、每个翻译单元的依赖顺序和配对哈希保存在
`implementation/msp_boot_v8/input_registration.json`，不能由一次成功构建自动扩充。

此次接纳的是编译输入及固定回调绑定的审查身份，**不是所有函数关键契约验收**。
关键契约、硬件资格、WCET 和整个固件安全接受状态仍为 **NOT PROVEN**。

| 输入（对应清单中的完整路径） | 实质审查、所有权及对调用图的影响 |
|---|---|
| `APP/Src/logger_task.c` | 在现有 Logger 循环直接调用有界候选存储服务。没有新增任务、执行器或动态回调；TF 仍只有 Logger 执行。 |
| `Common/Src/common_format.c` | `__builtin_signbit(double)` 保留负零，修复 MinGW 的 float 宏转换；未更改格式器容量或现有回调。 |
| `persistent_storage.h/.c` | 只增加 SSOB kind 5 的合法枚举边界；原双槽、长度、CRC、代次和重读规则未移除。 |
| `mag_calibration_storage.c` | 启动加载取得 MagWrite 租约，直接调用 Owned 入口，结束后释放；没有第二层租约或新指针表。 |
| `storage_service.c` | 原 FIL/记录缓冲区仍由 Logger 独占。完整 SHA 的八级短文件名由固定十六进制映射构造；64 B 分块、错误 close 保留不确定性、发布后复验、68 B head 与代次 CAS。所有操作为直接调用；不注册 HAL/RTOS 回调。17 个实际 C/FatFs/SSOB 场景已通过，不能当卡介质或断电实测。 |
| `silverstar_flight_cycle.c` | START 排队/处理全生命周期、维护 drain 和配置操作与采集互斥。状态/租约转换在原临界区中；SafeSet 在锁外，失败不留下 READY。原 task entry 和回调表未改。 |
| `project_installation_capture.h` | 新的固定端点标签，仅来自声明式图；不能证明硬件身份/原始帧/测量时间。没有可执行分派。 |
| `project_log_config.c`、`project_log_decoder_profile.c`、`project_metadata.c` | 与当前 v6 ON 配置生成物逐字节核对；记录 MAG 流禁用及其元数据/语义身份差异，未改 SSLOG 格式。仅登记该配置，不把另一配置的已知单个头与它拼接。 |
| `system_installation_calibration_if.h` | 增加完整候选 kind 2 和命名快照坐标常量，标注 unknown 父标识；不意味着运行时应用。 |
| `system_installation_capture_if.h`、`system_installation_store_if.h` | 明确直接类型接口、角色枚举、64 B 工作副本和请求/token/阶段匹配。默认 OFF 为无状态内联桩；没有函数指针成员。真实 typed Begin 的 offline=0 拒绝和 wire APPLY/SAVE 关闭保持。 |
| `capture_internal.h`、`capture_port.h`、`installation_capture.h`、`system_installation_capture.h` | 有界结构与私有状态接口；1960 B 静态采集存储，两个 80 B 预留空间复用。数据指针不是可执行回调；不扩大现有指针例外。 |
| `capture_port.c` | PRIMASK 保存/恢复内的字节/字操作；临界区不调 I/O、不循环等待，不依赖 CCM exclusive 指令。输入指针来自私有确定对象；这不代替全函数故障契约证明。 |
| `installation_capture.c` | 私有静态 CCM 状态、两对槽、单个非阻塞 guard。快照先校验再复制；序号、时间、容量、超时、取消/清理和确切代次释放有普通失败路径。无新增间接调用、递归或分配；生产端点不能伪装合格离线源。完整关键契约审查仍未完成。 |
| `capture_info.c` | 固定有序 JSON 流式输出/哈希，8192 B 总上限和页容量；profile<4/角色配对及字符串 token 验证在快照入口。driver/model 是固定字符串指针表，非函数表。unknown 父系数输出 null。 |
| `capture_primitives.c` | 固定 64 轮 SHA、32 B 数字输出，有限 double 才进入 Ryu；没有 printf/strtod、动态分配或可执行指针。数值格式与 SHA 的既有跨语言金样本保留；不能以文本循环扫描当完整数学证明。 |
| `installation_lease.c` | 直接结果映射和确切 token 延迟释放；Busy/Capacity 保持普通拒绝，非法内部释放进入既有断言路径。 |
| `installation_store.c` | Logger 取工作副本后锁外做 TF I/O，完成检查 request/token/phase/offset；取消不提前释放未确认 I/O，完整 SHA/CRC/信封复验后才 CAS head。最多四次非阻塞完成提交，不新增调度器、回调或分配。JSON 语义/拟合质量仍由 PC 审查，MCU 只承认候选字节。 |
| `system_installation_capture.c` | 单 Serial 所有者的 bounded ASCII dispatcher，191 B 请求、整帧发送。源证明 NULL 立即拒绝；不增第二个 FIFO 读者。真实 BEGIN 继续 SOURCE_QUALIFICATION；wire UPLOAD/APPLY/SAVE 未连接。字符/token 表不可执行。 |
| `system_alignment.h/.c`、`system_calibration.c` | CAL Start/Reset 经 ALIGN 所有者校验、quiesce、失效后交接；后台 reset 不在 IRQ 临界区中。CAL Face/Stop 不发起交接。失败/并发竞争无 CAL 部分发布或陈旧 READY；v6 的 CAL417、ALIGN304、交接故障29 项通过，保留 v4 红例。无动态回调。 |
| `system_mag_calibration.h/.c` | coherently 复制 active/status/bias/matrix；LOAD/APPLY 的同步租约与 SAVE/CLEAR 匹配 request 的异步租约分开，旧完成不释放新请求。10 个实际 MAG 模式通过；未更改目标 MAG 校准质量算法。 |
| `system_inertial.c`、`system_source_selector.c` | 只在原消费点、软件校正前观察；NULL proof 明确拒绝当前真实源，不从 latest/READY 推断原生连续性。不更改设备选择分派表。 |
| `system_console.c` | 安装命令和周期发送在原 Serial 上下文直接执行；独占期间其他操作返回 Busy，没有新增 HAL callback。 |
| `system_log_file.c` | 原 mailbox 增加租约/清理失败状态，保留关闭不确定性；会话结束先关闭/清缓存，再释放，未新增文件执行线程或改传输帧。 |
| `system_log_policy.c` | 配置变更取得 Configuration 租约并失效 frozen 依赖；原配置验证/冻结规则未变。 |
| Ryu 的 `common.h`、`d2s.c`、`d2s_intrinsics.h`、`ryu_assert.h` | 按保留的上游 commit `4c0618b0e44f7ef027ebae05d2cc7812048f7c8f` 和 LOCAL_CHANGES 审查。直接 fail-stop bridge 保留上游前置条件；warning 修正不抑制诊断。无函数指针；只链接 buffered 路径，nm/实际闭包没有 malloc/abort。未链接的便利分配 API 仍保留于第三方清单。 |
| Ryu 的 `d2s_full_table.h`、`digit_table.h`、`ryu.h` | 常量表/声明与上游来源对照；两个上游许可保留，不把第三方变成首方合规对象。数值循环/库栈与时序后果继续单列，未增白名单例外。 |

## 正式机制和不变门槛

v22 只新增上述确切版本、实际依赖图与完整 source+compiler-input 配对，并更新两个注册查询函数与审查版本号。
保留历史 v2–v21 的所有登记、256 B 上下文和最小任务余量、动态帧/递归/未知间接调用拒绝规则、库函数帧处理、
任务根与固定启动/diskio 回调验证。AST 对照必须证明其余内容未改。

在复用的开发验证投影中，用新拥有者脚本运行实际 emitted stack-report；固件 C/头、配置、ELF 均不改。
负例只能放在独立的少量编译输入夹具中：未知源码、未知头、依赖图变化和“单独已知但配对不符”的旧头均须拒绝。
旧失败报告和全部 v6 编译/回归证据仍对应旧脚本；新的通过不能倒填旧记录。

MSP 的逐阶段分析见同日 v8 报告。输入登记通过不将其条件 HAL 回调模型转成全固件证明，也不打开真实采集、
应用/保存、硬件或飞行门禁。
