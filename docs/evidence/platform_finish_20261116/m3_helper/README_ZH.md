# M3 补充批：共享 CRT 弱回调证明的原样提取

这是此前 `contracts/` 完成后的新软件批，未改写此前 F407 E28/E19 构建的结论或输入时代。
F103 Ground 的旧 1 KiB MSP 预算不足、M3 初始化数组形状被旧适配器严格拒绝，均由
boards 原始诊断保留。本批只负责共享逻辑提取与只读回调闭包交叉审阅；M3 新适配器、
链接器 MSP、完整 ARM/analyzer/原样 gates 与实际精确病例由板卡 owner 负责。

`stack_runtime.py` 把原 `CrtCallbacks_Resolve` 的弱回调前半段原样提取为
`CrtWeakCallbacks_Resolve(graph)`。原 M4 入口先调用它，再执行完全不变的初始化数组证明。
M3 可以复用 LDR 零指针 / CBZ 到 BX LR / 唯一前驱证明，随后进入自己的精确初始化数组规则。
没有给 M4 matcher 添加 M3 备选形状，没有伪造删减 graph，没有改变 C071 的 CMP/BEQ 规则，
没有改最低余量、case30 索引、目标 C 或任何编译门槛。

[extraction-equivalence.json](extraction-equivalence.json) 逐 AST 核对原弱回调全部语句、
M4 初始化数组尾部和其他所有函数原样相同；只有调用 wrapper 与独立返回增加。
`stack_runtime_before.py.txt` 是实际执行前原始源码字节快照，不是改名绕过检查的正式工具。
新增测试文件仍以 `.py` 正常检查，Ruff 通过。

实际机器夹具来自最终 E19 B Release ELF，保存 ELF、objdump、工具版本和源路径身份。
它保留真实函数行、PC literal、初始化数组与符号表；测试中的 256-byte 临时文件只用于
数组长度上界参数，不伪装为 MCU ELF，也不授予 case 准入。

| 独立执行 | 结果 | 范围 |
|---|---|---|
| 提取前 `test_stack_crt_weak.py -k 'not helper_only'` | 13 passed / 1 deselected，0.51 s | 旧 M4 完整入口正常及 12 个真实边界变异；新 API 测试尚未执行，不把 refactor 本身冒充旧安全缺陷 |
| 提取后 weak / stack_runtime / C071 runtime 三文件 | 32 passed，1.02 s | 同一正常/拒绝期待，以及新 helper 只移除 weak、保留架构 initializer 给其 owner |
| 原完整关键合同组重新执行 | 167 passed，25.88 s | 独立新日志，不回填或拼接到旧 167 项时代 |

拒绝用例覆盖非零/缺失 literal、错误 guard/opcode/寄存器/return、旁路 load/guard、
额外间接 call、错 initializer 步长与非法 Thumb 数组目标。

F103 只读交叉审阅收据见
[f103-callback-cross-review.json](f103-callback-cross-review.json)：唯一 `huart1`（72 bytes）
及 RX/TX DMA（各 68 bytes）由 BSS 初始化，双向 `__HAL_LINKDMA` 与 IRQ 固定对象一致。
实际常量 completion/half/error/abort installer 与保留符号相符；未链接 registration APIs、
异步 Abort APIs 或其他 abort callbacks。UART callback registration 为 0，生成 byte-stream
只访问固定对象，没有第二 handle、替换对象或 callback registry。
Release 有五条 `(caller, PC, ABI-slot)` 绑定行，编译器合并后仅三个不同 PC，未误称五个独立
调用指令。此闭包审阅不是整体语义审计，也没有把旧 1 KiB MSP 失败改成通过。

未执行硬件操作、未 stage/commit/push。全部旧 case 原始字节与其来源保持；真实硬件
时序、WCET、高水位和全固件关键合同语义仍按前批范围保留 NOT PROVEN。
