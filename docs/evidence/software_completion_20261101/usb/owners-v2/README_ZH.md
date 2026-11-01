# 通用 USB owning 修复：堆 ABI、F407 FIFO、共享描述符遍历

本批继续完成实际软件缺陷，原 CubeMX 输入始终只读，没有硬件动作。
普通 Ground/private 构型与通用 kit 的结果分别记录；不能互相替代。
源码基线为 `e7c42b7c4971fddb02c6d5c60864b50dffaa3f1a`，执行时为可审计 dirty
快照，见 [source-snapshot.json](source-snapshot.json) 和 [OWNED_FILES.txt](OWNED_FILES.txt)。
实际生成源码、完整命令、失败/成功日志与 ELF/map 已保留；不是旧产物换标签。
最终相干源码随后提交为 `e4b909c05c6887d54a977f973a19378970d0aabc`；上述测试的
实际执行身份仍是原 e7 + dirty snapshots，没有倒填执行当时的 HEAD。

## 实际修复与前失败

1. **两板 sysmem**：通用 source graph 原样编入 `Core/Src/sysmem.c`。现在复用现有
   `NativeNoHeap_FilesRender`，只接受原始 SHA `ad20f7b1…df95`，将该唯一编译槽明确
   替换为 `Src/native_no_heap.c`，按 first-party 严格编译并强制链接 `_sbrk`。
   零、正、负与极值请求全部返回 `(void *)-1` / `ENOMEM`。没有删除原输入、隐藏
   其来源或只修改 checker 投影。未知 sysmem 身份拒绝自动替换。
2. **精确 F407 FIFO**：原配置为 RX=128、EP0=64、EP1=128，共 320/320 words，
   没有 EP2，不能再直接添加 16 words。只有完整 LL SHA 等于既有已审
   `native_usb_indexed.LL_SHA` 且 fixed F407 controller/ABI 匹配时，复用其
   128/64/64/16 初始化（272/320，剩余 48 words），检查所有 HAL 结果。
   用户修改过的 LL 仍原样保留；运行时 geometry guard 继续拒绝不足/重叠配置。
   `configuration_derivation.native` 保留原始缺 EP2 事实，`derived` 单独描述新配置。
3. **F407 descriptor walker**：旧 `USBD_GetEpDesc` 依赖未经校验的 `bLength`
   前进。共享 `ground_usb_control.py` owner 现在先由真实 class 静态对象身份获得
   67 字节容量，外来/NULL 指针在读取前拒绝；检查配置头、总长、每记录的正向进展、
   剩余容量和完整 endpoint 长度，扫描完整链后才返回目标，不因提前找到目标而漏掉
   后续坏记录。最多 67 步。FS/HS/other-speed 三个现有 getter 都在所有 endpoint
   验证后才写 packet/interval 字段。失败长度为零并调用既有 Abort 发布软件 STALL；
   返回有效 backing pointer 是因为原生 ctlreq 在检查长度前写 `pbuf[1]`。
   容量 API 只在 indexed F407 头中声明。generic 与 private 合成同一个 owner。

[pre.log](pre.log) 为真实前失败：两板 source graph 都仍选择 sysmem；F407 真正
执行 LL initializer 后 notification 容量检查失败。F103 对应配置与原 EP0 组通过。
descriptor 前失败第一次记录器误对字符串 `.decode`，该测试工具异常原样保留，
不算目标缺陷；随后仅修记录器，在**同一个原可执行文件**上补录全部 10 场景。
见 [descriptor-pre-receipt.json](pre/test_generic_actual_ep0_bounda1/descriptor-pre-receipt.json)。
三个 getter 的正常场景 exit 0；零长度场景 2 秒内不前进，被受控终止；另六场景有
明确旧安全断言失败 stderr。NULL owner/NULL length 的进程未在界限内退出，没有
捕获具体 native exception 指令，不把它们统称为已证明死循环。

## 实际执行范围

| 运行 | 结果 |
| --- | --- |
| 修复后首批 | [post1.log](post1.log)：96 passed、6 capability skips，108.71 s |
| F407 专属头修正及真实 no-heap C | [post2.log](post2.log)：97 passed、6 capability skips，108.16 s |
| 实际产品 graph/不可变输出边界 | [workflow.log](workflow.log)：8 passed、18 deselected，172.78 s；有意选中受影响项，未称整文件通过 |
| 完整通用组选组一次执行 | [full/host-tests.log](full/host-tests.log)：148 passed、6 capability skips，197.90 s |
| F103 ARM normal / 实际 analyzer | 编译、链接、attributes、symbols、vectors、size 全 exit 0 |
| F407 ARM normal / 实际 analyzer | 编译、链接、attributes、symbols、vectors、size 全 exit 0 |
| 原样 Power of Ten | **F103 5 个失败组；F407 9 个失败组；完整 validator exit 1** |

原七个能力 skip 中，F407 第四个 FIFO setter 已存在并执行其故障场景，因此减少为六个。
没有删掉旧边界预期。ARM analyzer 保留两份上游 HAL UART 诊断，不能称完整 SDK
无警告；这是 `-fanalyzer` 实际编译/链接，非 syntax-only。
`_sbrk` 真实保留在两板 ELF。日志中的 `*-sysmem` 编译标签和
`Generated/UsbVendorReview/Core/Src/sysmem.c` 投影名沿用原 input 槽，内容/实际
compiled 路径是已审拒绝 ABI；以 [实际图](full/f407/Generated/usb_transport_source_graph.json)
和命令为准。

| exact generic ELF | normal 与 analyzer SHA-256（两次实际构建相同） | GNU size text/data/bss |
| --- | --- | --- |
| F103 | `52e531b65cbb11793b6002a7926f7fe0f2c6876396964e7813722a6b875d0bcb` | 19152 / 472 / 8152 |
| F407 | `940ee9fdf472e384a16e9ef54e8e52dc8ed0dfca150d28202134e9b04481f0de` | 20904 / 340 / 10944 |

上述是该独立 USB 图的链接段大小，不是任务/ISR/MSP 栈余量证明。

## 完整构建之后的准入收尾（不重新归因旧构建）

新加的 `heap_policy.required_link_symbols` 和 replacement `policy` 需要自身的
严格输入边界，不能仅依赖外层 kit inventory。最后的两个 Python owner 修复：
symbols 必须是实际 list，且只能 `[]` 或恰好 `['_sbrk']`；已声明拒绝 ABI 时必须
保留后者。只有已审 sysmem original/hash、固定派生 path、准确源/头字节和 matching
receipt 才可取得 first-party policy，其他 replacement 保持 vendor。产品构建入口
在调用任何工具之前复用相同 symbols 校验。

[metadata-pre.log](metadata-pre.log) 的两板 16 项畸形 manifest 都曾 **DID NOT RAISE**；
[admission-final.log](admission-final.log) 的 27 项全部通过（192.31 s），包括这 16 项、
合法实际图/原输入保护、正常与故障 FIFO、两个完整 generic 控制包装、真实拒绝 heap ABI。
这个后续组选组不是又一次完整 148 项，不能拼接宣称完整套件在新 Python epoch 重跑。
最终产品 workspace/graph 选择回归 [workflow-final.log](workflow-final.log) 为
**8 passed、18 deselected / 118.05 s**。最后源码身份见
[final-admission-source-snapshot.json](final-admission-source-snapshot.json)，它明确列出
相对完整构建 epoch 的两个输入拒绝 Python owner 与两个测试文件变化。

合法产物等价检查在新独立目录重新导出两板 kit：[admission-equivalence.json](admission-equivalence.json)
证明 F103 33 个、F407 35 个 kit 文件逐字节相同，真实编译源码及 policy、flags、assembly、
linker、required symbols 也与本批已执行 ARM 的输入相同。只新增坏元数据拒绝，没有
把旧二进制换名冒充另一轮 ARM 构建。

精确 private 路径的新实际验证见 [descriptor-v2](../../usb-exact/descriptor-v2/README_ZH.md)：
三板各 normal/analyzer 实际 ARM，12 个 emitted gate 全 exit 0；F103 的 18 正常+
10 故障、F407 的 18 正常+20 故障均通过。其首次 F407 invalid-descriptor 场景失败是
Host 夹具在首次坏 getter 触发预期 STALL 之前尚未置 `allow_control_error`；只将该
场景的许可提前，device/endpoint、零发送、整数组无部分修改断言仍在。原失败保留，
共享生产 descriptor owner 在修正前后字节相同。generic 对同一最终夹具也已实际重跑。

## 未通过项的准确归属

checker SHA 仍为 `a4aca423ec1df7a1ea273f80ddc8c9f0baaac5b9d4bac6481d1386c9a1312fac`，
没有修改例外、阈值或源覆盖。两堆失败组和 F407 描述符非进展循环组已消除；
仍失败的原始完整诊断见 [F103](full/f103-power10.log)、[F407](full/f407-power10.log)。

| 项目 | F103 / F407 组数 | 原因与可行动边界 |
| --- | --- | --- |
| main 服务 / Error_Handler 永久 while | 1 / 1 | 裸机服务循环与终止错误循环保留上游模型；此通用路径不在既有例外中。不能改成另一种循环语法躲扫描，也不能有限运行后返回来保持相同固件行为。需要独立审查及明确的例外授权或真实运行模型设计。 |
| 保留的多模式条件编译 | 3 / 5 | F103：main、core、LL；F407 另有 CDC 与 I/O。它们位于已修改的混合派生文件，不能整文件移到排除范围。后续需显式固定配置/ABI 的 owner 合同和拒绝相反配置证据，不能仅用预处理输出消除诊断。 |
| 长函数 | 1 / 3 | F103 DataIn=70；F407 Setup=62、DataOut=71、DataIn=80 个非注释代码行。均包含本轮/既有合成修改，不冒称完全不属于我们。未为 60 行阈值拆分/压缩；后续需要有独立职责与错误契约依据的实现审查。 |

这些是未闭合的软件门禁，**不归类成硬件待测**，也不声称是永久不能修改的用户输入。
任意标准请求、完整异步交错、整个 USB 闭包 critical contracts 与全程序栈仍未证明。
真正硬件项另为枚举/拔插/挂起/复位压力、真实 FIFO/PMA 取消、PHY/时钟与 IRQ 时序。
有限 Host 与 ARM 通过不会自动解除 formal release 阻断。

## 重放

```powershell
$env:PYTHONPATH='D:/python_software/SilverStar/apps/SCG/src'
$env:PATH='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;' + $env:PATH
.venv/Scripts/python.exe -B apps/SCG/tools/validation/usb_transport_validate.py --integrated --reference D:/Codex_Work/2026-10-08/task/usb-validation --output <新的独立目录>
```

原输入路径、工具版本、命令和 exit 在 [full/commands.json](full/commands.json)；
输入保留确认与四个实际产物身份见 [full/summary.json](full/summary.json)。
每个 source-map 保存原运行路径到去重原始字节的映射；`archive.py.txt` 是一次性
归档工具的原字节快照，运行路径/hash 在 `archive-replay.json`，不是生产入口。
本目录不授权清理原始输入、旧证据或这些留存产物。
