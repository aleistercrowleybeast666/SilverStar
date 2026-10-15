# GSHC RAM 变量监视与摘要接口（0.1.3 开发版）

运行诊断页可从 ELF 导入变量目录，搜索并添加最多 16 个 RAM 标量或固定结构体成员，
以 1/2/5 秒间隔采样，支持暂停与移除。准备状态、估计任务、惯导输出和日志存储各有一行摘要。
缺失字段明确为 UNKNOWN；主机读取超过 3 秒标记 STALE。摘要中的 ready 是观测值，
不授权 START，也不替代 AIR/命令控制器的就绪判定。

## 变量准入

`contracts/swd_watch_v1.json` 定义新的 watch 边界。原有四条固定诊断及 `.ssdiag` 绑定不变。
目录由共享 `silverstar_diagnostics` ELF/DWARF 读取器生成，仅接受文件作用域全局量或
静态量的 `DW_OP_addr`，要求精确匹配链接符号的地址/大小，整个对象位于一个可写分配节及
所选目标的可信 RAM 范围。结构体使用固定偏移，最多 4 层、每层 256 成员、总目录 8192 项。
同名静态变量以编译单元路径区分；来源/名字/成员仍有歧义的条目不可选。

支持整数、布尔、枚举、32/64 位浮点。数组、指针解引用、联合体、位域、函数局部量
（包括函数内 static）、动态位置、优化后缺失位置、表达式和 MMIO 明确拒绝。
没有 DWARF 时只保留固件身份能力，不猜类型。读取 NaN/Inf 返回带状态的字符串，避免非法 JSON 数字。

单次 watch 最多 128 字节；API 的 watch 最短间隔为 1 秒。所有操作共同受会话 64 KiB RAM/状态
读取预算、600 次采样及 600 秒寿命限制。完整 flash 身份核验使用既有独立的最多 2 MiB 扫描预算。
暂停不延长会话寿命。更换选择立即清空显示；旧选择的在途结果不能重新填入 watch 表。
传输失败/取消/预算耗尽触发有界释放，断开后值失效；重新连接需要重新核对 ELF。

## 身份、时间与访问语义

本次连接先核对 ELF 的完整非空内部 flash PT_LOAD 加载内容，再解释 RAM。
匹配是一次非原子读取的证据，不是固件认证。记录 ELF SHA-256、所选目标、探针标识、
变量地址/类型、原始字节、值、主机 UTC/单调时钟接收时间及持续时间。
多个成员不构成原子快照。主机接收年龄与 MCU 采样年龄不同，未知 MCU 年龄始终为 null。

`Swd_ReadWatches` 仅读所选 RAM，不读核状态，不能检测采样期间未观察到的复位或重刷。
已知目标变化后必须断开并重新核验。GUI 及 `Swd_Inspect` 同时保留原有核状态/固定诊断；
其中 DHCSR 读取会消耗 S_RESET_ST/S_RETIRE_ST 粘滞历史位，界面/API 明示此边界。
观察到复位会撤销符号匹配。没有新增 halt/reset/resume、写内存、断点或目标调用能力。
调试传输自身的 DP/AP 选择和读请求不是“总线上零写事务”的承诺。

## 本地 JSON/API

在具备 GSHC 与共享包依赖的仓库环境中运行：

```powershell
python apps/GSHC/swd_cli.py catalog --elf firmware.elf --target STM32F407VET6
python apps/GSHC/swd_cli.py watch --probe '<inventory 的精确标识>' --elf firmware.elf --target STM32F407VET6 --watch '<catalog 的精确 ID>'
python apps/GSHC/swd_cli.py summary --probe '<inventory 的精确标识>' --descriptor firmware.ssdiag
```

`catalog` 完全离线，不枚举或打开探针。`watch`/`summary` 明确请求一次目标读取，使用同一个
`SwdSession` 所有权、匹配、限流、取消及释放实现；不存在监听网络服务。
输出为 `silverstar.swd-snapshot` version 1，保留 result/release、原有 snapshot/diagnostics，
并增加 watches、firmware_sha256、budget、watch_identity（RAM-only）、summary 及时间/访问说明。
`summary` 可重复 `--watch` 添加精确目录 ID，不接受自由地址表达式。

## 验证范围

测试使用实际 ARM 编译器产生的 ELF 和模拟内存，覆盖结构体、同名静态量、枚举、浮点、
缺 DWARF、成员越界、RAM/MMIO 边界、错误选择、短读、复位、限流、预算、取消、暂停超时和 Qt 界面。
已有 ESKF15 实际生成 ELF 可离线读取 2110 项目录，其中 1543 项可用（147 项 binary32）；
这证明该 ELF 的解析结果，不是当前修改的固件构建或上板结果。
本批没有打开串口/探针、烧录、复位或操作执行器。Horco/F407 历史核状态读取证据不等于
本次变量监视上板验收；ST-Link、其他目标和当前 ELF 匹配变量读取仍须硬件验证。

TF 下载同时修正了 Windows 长路径下检查点临时名过长的问题：临时文件仍在同目录，
改用固定短前缀与随机 ID，继续原子替换。设备侧删除、协议、原始日志及 decoder 均未改变。
