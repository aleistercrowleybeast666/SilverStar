# 安装标定：离线软件接入与交接（2026-10-19）

Owner：`installation_c_impl_20261019_v1`。本批继续已批准的无硬件实现；证据统一保留在
`.work/dev013_installation_c_impl_20261019_v1/`，不清理历史内容。分支与脏源码摘要、完整命令、
退出码及文件散列见该目录的 `software_closeout.json` 和 `retained_inventory_software.json`。
未连接串口或调试器，未刷写、复位、推送、修改稳定 main；JY901B 调查保持暂停。

## 已接入的软件链路

1. SCG 可选声明插件 `silverstar.installation.capture` 拥有唯一 C 实现。所有预设默认不选；
   仅开发者显式加入项目 base components 时编译。生成器检查 F4、维护通道、唯一 IMU/MAG，
   按真实 catalog 生成端点标签。不新增导航算法选项，不改第四轮 GUI 布局。
2. IMU 从现有单消费者 `SystemImu_NextSampleGet` 成功返回处、校正前旁路复制；MAG 从现有
   源选择器校正前旁路观察，不增设 FIFO 消费者。生产端传入 NULL proof，明确表示原生逐样本、
   原始量定义、epoch 与测量时间语义未证明。没有用到达时间冒充同步测量时间。
3. `SystemInstallationCapture_*` 使用同一 C 状态机处理 CAPS/分页 INFO/BEGIN/FACE/POLL/
   STATUS/DO CANCEL；与现有日志导出共用维护串口，控制命令未写入 SSLOG。完整 INFO 冻结
   IMU/MAG 身份、来源、单位/坐标、校准代次及实际系数；未知启动/时间/父代保持 UNKNOWN/null。
   开机 IMU 校正单独保留，静态六面不声称完成陀螺尺度标定。
4. GSHC 的真实 `MaintenanceOwner` 工作线程与 `FileServiceSerialTransport` 经有界 lease 接入
   后端；默认关闭。会话 ID/RID、迟到回复隔离、断线失效、空闲读取屏障、TF/MAG/控制台排斥，
   以及取消等待消费者释放后的确认均有离线覆盖。串口 I/O 不进入 GUI 线程。
5. 每面按冻结计划依次采集 TRAIN/HOLDOUT，PC 保留原始数据。拟合使用既有后端；导出用
   固定训练解独立计算留出残差，不用留出样本重新选解。激励/歧义不合格时拒绝候选，必要时
   另补倾斜姿态。仍采用未知磁倾角标量约束，未将重力与磁场直接当成同向 Wahba 向量。

## 候选与 TF 边界

`installation_calibration_candidate.py` 实现 SSIC v1 kind 2 完整软件候选；既有 MAG kind 1
不变。32 字节公共头之外保存规范化完整绑定、父代、实际系数、训练解与独立留出报告、原始
归档 SHA-256。禁止 NaN、重复 JSON 键、越界包和绑定不一致；所有候选固定
`hardware_acceptance=NOT_PROVEN`、`apply_allowed=false`、`save_allowed=false`。

`InstallationCandidateStore` 提供 Read/Create immutable/Commit CAS verified 对象接口，
`OfflineTfObjects` 提供目录镜像适配器。新对象独立写入、回读验证，再发布代次；失败验证不覆盖
旧对象。重复保存幂等，父代变化拒绝，损坏新 head 可回退到完整旧代。丢失提交 ACK 为不确定结果，
重启后可能发现完整新代，不承诺“返回失败就必然没提交”。镜像测试覆盖这些故障；不代表 TF/FAT
掉电验证。

MCU 的分块 TF/LoggerTask 提交适配器仍未实现：现有 `PersistentStorage_ObjectWriteAtomic`
上限 512 字节，且缺少通用流式对象读取接口，完整候选可达 16 KiB。本批未扩大该上限、未复用
MAG 槽位或改 TF 所有者区域。真实 UPLOAD/APPLY/SAVE 继续关闭；GUI 也没有新操作入口。

## 真实链接与资源约束

状态对象 1960 字节、串口协调状态 28 字节；模块边界链接合计 1988 字节，功能 cap 仍为
2048 字节。完整固件必须将它们放入现有 `.ccmram_bss.*`，并核对对齐后的整体 CCM 占用；
不能仅用独立夹具推断真实地址。旧 section 拼写导致主 SRAM orphan 的失败 ELF 已保留，
拥有该状态的插件源码与夹具均已修复，不修改 MCU 链接器预算。

最终完整 ELF：CCM 64896/65536（含本功能 1992 字节及末尾对齐），剩余 640；主 SRAM
102292/102400（含既定堆/栈保留），剩余 108。模块边界的 644 字节算术余量未包含完整
链接器末尾的 4 字节对齐，不能用它代替完整 ELF 的 640。Ryu 的内部断言通过局部桥接进入
既有 `SilverStarAssert_Fail`，避免 libc abort/信号/格式化路径；Host 正常与非法移位触发场景
通过。setjmp/longjmp 仅用于 Host 截获终端故障，不进入目标代码，不代表 MCU 恢复。

完整源码图的编译、链接与静态占用，以 `software_closeout.json` 中最终完整 ELF 为准。
严格告警及真实 `-fanalyzer` 覆盖修改的目标 C 路径；第三方 Ryu 的来源、许可证与本地改动单独保留。
生成的 `power10-check` 按原命令执行，没有改阈值、例外或源覆盖；成功仍报告关键契约审查
NOT PROVEN。模块或完整 ELF 中的已知静态调用链不等于完整任务/MSP/ISR 栈证明，未测硬件高水位
或 STM32 WCET。不得将本批称为原始 Power of Ten 合规、完整安全验收或硬件资格通过。

扩大回归在故障桥接前的冻结源码上一次跑完 515 项及 5 个子测试；最终故障桥接另做有界重点
回归、正常/故障触发、严格 ARM 编译/分析与完整链接。两者的确切版本、命令和结果分别保留，
不拼接为“最终源码已执行整套扩大回归”。旧扩大回归超时涉及临时目录及耗时的存储完整性
回归；明确任务内 TEMP/TMP 并记录有界时限后，Python 整组约 147 秒、Host 门禁可重复完成。

## 上硬件前剩余最小批次

1. 补齐全固件控制入口的生命周期 lease。当前 C 资源原语、控制台与 GSHC 排斥已接入，但 AIR/
   内部控制入口尚未全部使用该 lease。禁止据此声称所有入口互斥已经完成。
2. 为具体驱动证明 boot 身份、原生序号连续性、raw 定义、单位坐标、测量时间与不确定度；MAG
   LatestSampleGet 不能自然证明 every-native。当前生产 BEGIN 明确拒绝 `SOURCE_QUALIFICATION`，
   不得通过伪造 proof 解锁，也不通过偷偷降低采样率回避来源问题。
3. TF 所有者实现有界分块对象接口及恢复/读取；验证快照依赖失效、旧代保留、掉电/拔卡后恢复。
   再分别接入验证、应用、保存，保持它们的权限与结果独立，ACK 不等于 READY。
4. 完成整任务/库/间接调用/MSP/ISR 栈与关键契约人工审查后，另获授权用已知良好模块验证采样、
   时间与精度。本批没有恢复 JY901B 硬件调查或暂停的 M9N INT32_MIN 任务。
