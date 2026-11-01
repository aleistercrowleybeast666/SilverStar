# 通用 CDC kit：限定 EP0 修复与仍然失败的门禁

> 后续状态：本页保留第一阶段 134 项验证与 6/11 组门禁失败的原义。追加的描述符、无堆 owner、精确 FIFO 派生和元数据准入结果见 [owners-v2](owners-v2/README_ZH.md)；新完整通用组选组为 148 passed / 6 skips，严格规则仍有 F103 5 / F407 9 组失败。

此目录记录 `UsbTransport_Export(..., integrate=True)` 的独立通用 kit，**不是**普通
Ground 私有候选源图。普通 F103/F407/C071 的结果见相邻 `usb-exact/`，不能互相替代。
原 CubeMX 输入只读保留；没有访问 USB 设备、串口、调试器或执行烧录。

## 修复与真实执行

通用生成器现在通过同一个 `NativeControl_Integrate` 复用精确原生 owner 的有界 EP0
策略，不维护第二套控制请求实现。保留原 bulk、session、retirement、原生时钟/PMA/FIFO
所有权，只合成 class Setup/RxReady、core EP0 分支、I/O helper 与 Control trampoline。
原始到最终的 patch/hash 随 kit 一起输出，新增 policy 编译进实际源图并进入严格扫描。

- GET 的回调固定接收 7 字节容量，发送量为 `min(wLength, 7)`；SET 要求真实收到恰好
  7 字节，控制 RX 缓冲仍可承受实际 64 字节 EP0 包。未知/坏请求保持普通错误路径。
- 初始、继续、状态阶段的 LL 错误都撤销命令并将 EP0 标为 STALL。迟到回调不得继续
  LL 操作或恢复成功；新合法 Setup 才开始新的控制事务。NULL/外来 owner 在解引用前拒绝。
- 非空用户 `CDC_Control_FS` 拒绝自动合成，输入字典保持原字节；不覆盖用户策略。

| 实际执行 | 结果与范围 |
|---|---|
| 原通用完整选组 | `generic-before-v1/host-tests.log`：132 passed、7 capability skips，261.61 s |
| 通用 EP0 修复前 | `generic-ep0-before-v1.log`：两板实际长度边界均失败；旧 kit 没有 policy，所以另外 20 个 policy 场景记录 exit 2、未执行，不能冒充实际故障注入 |
| 通用 EP0 修复后 | `generic-ep0-after-v1.log`：2 passed，91.67 s；两板各正常/边界及 10 故障，共 24 个场景实际运行成功 |
| 修复后完整选组 | `generic-after-v1/host-tests.log`：134 passed、原 7 capability skips，305.46 s；一次完整执行，无拼接 |
| 用户回调所有权新增负例 | `generic-user-owner-v1.log`：2 passed、88 deselected，27.15 s；晚于完整选组新增，单独报告 |
| 编译宏别名准入补齐 | `generic-alias-before-v1.log` 两板 DID NOT RAISE；补接既有 build-owner 检查后，`generic-alias-after-v1.log` 4 passed、88 deselected，9.97 s，包含非空回调和编译宏别名 |
| F103/F407 normal 与 analyzer | 四次实际 ARM 编译/链接、attributes、symbols、vectors、size 均 exit 0；不是 syntax-only |

Host 使用完整实际生成的 class/core/I/O/policy/transport/port。LL 和 retirement hardware
port 是 Host 模型；retirement 的真实生成实现另有完整 register/failure 选组。
EP0 前后日志保留旧 harness 的 BOS 重复定义警告；最终完整选组移除了重复的命令行定义，
没有改源头或抑制诊断。上游 F103 `USBD_CtlError` 的 unused parameter Host 警告仍保留。
两板 ARM analyzer 都保留上游 HAL UART 的诊断，不能称整个原生闭包无警告。

最后的编译宏准入修复不改变合法输出：[admission-revision.json](admission-revision.json)
逐字节核对 F103 17 个、F407 19 个生成文件与实际 ARM/analyzer 候选完全相同。该项
拒绝坏输入，不借前一次执行宣称新 Python 入参路径已跑完整组选组；新拒绝路径由独立
前失败/后通过复核。原始 C、flags、ELF 对应关系没有变化。

## 仍未通过：软件项，不归类为硬件待测

完整 validator 的最后退出码仍是 **1**。未改变 checker
`a4aca423ec1df7a1ea273f80ddc8c9f0baaac5b9d4bac6481d1386c9a1312fac`，也未扩大例外。

- F103 原样 Power10 为 **6 个失败组**；F407 为 **11 个失败组**。包括原生 main/fault
  永久循环不属于该通用路径既有例外、混合派生源中的条件编译、超过 60 行的原生
  core/class 函数，以及 source graph 中仍有 `sysmem.c`。完整原始诊断分别在
  `generic-after-v1/f103-power10.log` 和 `f407-power10.log`。修复前为 7/10 组；新 I/O
  派生源的条件编译也完整纳入扫描，不能用总数相同掩盖范围变化。
- 本次不通过压缩/拆分函数、隐藏派生源、删除诊断、调整阈值或新增永久循环例外使其变绿。
  generic 源图仍按原覆盖规则拒绝；其失败不影响另外记录的 Flight 配置门禁含义。
- 原生 F407 参考未显式分配 CDC notification EP2 TX FIFO；能力报告保留该事实，运行时
  geometry guard 会拒绝不足/重叠配置。kit 不静默重写用户拥有的 FIFO 初始化。
- 任意标准请求、完整异步生命周期、完整 critical-contract 手工验收和该独立 USB 图的
  全程序栈仍未闭合；有限 EP0 场景成功不升级为整体正式准入。

真正的硬件待测为枚举、拔插/挂起/复位压力、真实 PMA/FIFO 取消及 IRQ/时序；与上述
软件失败分开。`formal release` 准入仍阻断，没有执行硬件动作。

## 重放与证据

```powershell
.venv\Scripts\python.exe apps/SCG/tools/validation/usb_transport_validate.py --integrated --reference D:/Codex_Work/2026-10-08/task/usb-validation --output .work/0.1.3-software-completion-replay/usb
```

必须使用新输出目录；上述 reference 是本次已有的两份精确原生输入，不是任意 MCU。
`commands.json` 保存完整工具命令/退出码，`source-snapshot.json` 保存执行时 owning 源字节，
`summary.json` 保存 actual ELF 和链接库 SHA。`source-objects/` 去重保留实际派生源码，
各 `source-map.json` 指向对应对象；原许可证在 `native-licenses/`。`inventory.json`
记录从测试目录提取的每个证据文件与 hash。没有把同名旧二进制当作新构建。
