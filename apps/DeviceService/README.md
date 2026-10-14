# SilverStar_DeviceService：只读模拟原型

本应用已迁入 SilverStar monorepo 的 `apps/DeviceService`。迁入来源与原始文件哈希见 [MIGRATION_SOURCE.json](MIGRATION_SOURCE.json)，本轮复验见 [迁入报告](../../docs/evidence/monorepo_import_20261014/REPORT.md)。以下原型范围和历史验证保留；没有新增真实设备连接。

这是可撤回原型：独立 Python API + 单次 CLI，无第三方依赖。
不建立设备连接、不运行后台服务、不新增 GUI。所有响应带 `mock: true` 和
`hardware_access: false`。Python 3.10+ 语法；本机实际测试版本见 [VALIDATION.md](VALIDATION.md)。

## 是否值得独立出来

有用的情况：GSHC、CF33 测试 runner、未来 AI 都需要相同的设备状态、能力和日志读取；
希望统一连接所有权、超时、下载完整性、诊断和权限边界，避免每个调用者各写一套串口逻辑。
独立接口也让无人值守测试不必启动 GUI，且可先用模拟设备验证调用流程。

不值得的情况：只有 GSHC 一个使用者，需求只是偶尔查状态或导出日志；这时在已有会话外加
一个小型只读适配层更省维护成本。独立进程会额外带来生命周期、版本协商、身份校验及
部署成本。现在先验证接口需求，暂不把它定为第四个完整应用，更不先做大 GUI。

## 与现有组件的边界

| 组件 | 应负责 | 独立服务不能接管/重复的部分 |
|---|---|---|
| GSHC 会话 | Controller 是 Capability、命令、握手和会话状态的所有者；串口 worker 持有连接 | 不用 Capability/ACK 推断 READY，不另建并行会话抢串口，不复制握手/自动重放业务命令 |
| TF 日志服务 | 固件 LoggerTask 独占 FatFs；LOGFILE v1 按生命周期提供旧任务日志 | PC 服务不能直接读 TF、绕过固件状态门禁或执行 DELETE；`closed=1` 不保证日志成功收尾 |
| CF33 测试 runner | 编排测试、选择用例、调用有界接口、汇总结果与证据 | 不独占串口实现第二套 transport，不把测试编排器变成设备守护进程；本轮未发现可确认的 runner 集成入口 |
| DeviceService | 向调用者提供窄接口、能力/状态快照、将来统一连接租约与日志下载 | 不是 GUI、固件、协议权威、飞行控制器或机械安全控制器 |
| 未来 AI / MCP | 将已批准的少量 API 映射成工具；读取数据、解释结果、提出建议 | 不提供任意串口帧、任意脚本、Shell、文件路径、通用 `send_command`；数据不是指令 |
| SCG / FLP | SCG 配置/生成；FLP 用精确 decoder + Descriptor 验证后分析 | 下载不改写 SSLOG、不猜 decoder、不把模拟样例当作可解码飞行记录 |

优先集成路线是 **由现有 GSHC 会话拥有连接，服务读它发布的不可变快照**。
若将来需要 GSHC 关闭时运行，再决定是否将连接所有权整体移到单一服务进程；二者不能
同时直接打开同一个物理端口。AI 不能在读失败时自行绕过所有者去开串口。

## 现有代码检查与契约来源

在 `D:\python_software` 检查了顶层目录、AGENTS、SilverStar/GSHC 的相关代码与公开文档。
没有现成 `SilverStar_DeviceService` 顶层目录；找到了可复用的职责和协议来源：

- `SilverStar/apps/GSHC/services/file_service_client.py`：已有 LOGFILE v1 客户端。
- `SilverStar/apps/GSHC/transport/maintenance_backend.py`：现有维护连接。
- `SilverStar/docs/public/GSHC/UPPER_COMPUTER_ARCHITECTURE.md`：会话与线程职责。
- `SilverStar/docs/public/SCG/LOG_FILE_SERVICE_V1.md`：日志服务与导出设计。
- `ArmDesigner/README.md`：现有机械臂程序为离线仿真/设计，不是实机控制后端。

未导入、修改或运行这些项目的硬件代码。邻接项目的 AGENTS 只作为约定参考；新目录规则见
[AGENTS.md](AGENTS.md)。没有给 SilverStar、Android、TreeDiagram 或 UNDERLINE 添加依赖。

`contracts/` 保存共享契约的**逐字节参考快照**，权威仍在 SilverStar 仓库，不创建第二套协议。
父任务提供基线提交 `cb944b7`；读取时工作树已有更新，以下 SHA-256 标识本原型实际使用的字节，
不将它们伪称为该提交的精确内容：

| 参考文件 | SHA-256 |
|---|---|
| [log_file_service_v1.json](contracts/log_file_service_v1.json) | `56ee90b08d1c2f55704d91857d3cbd2840ba64932a5b831244c87aa451e3b2ab` |
| [session_export_v1.schema.json](contracts/session_export_v1.schema.json) | `ed2ce84f55d26ccdc28fc37683e83bdb9a114078f717294e49cd63f4c1d17feb` |
| [session_export_v1.golden.json](contracts/session_export_v1.golden.json) | `d998062d184fd1c8f1d73677faf93ccb55c53cf32c66efc37d943133e702cf9e` |

## 已实现的最小范围

- 两个固定模拟引用：`mock-fc-001`（飞控）、`mock-rig-001`（调试机械）。不会枚举操作系统设备。
- 设备状态、能力、采集状态查询。`connected=false`、`readiness=unknown`，采集保持 mock-idle。
- 飞控的日志目录、元信息、临时下载。能力字段沿用 LOGFILE v1，`delete_supported=0`。
- 每次下载从头取契约 golden 字节、核对总长度/CRC32、计算 SHA-256，再以 `.part` 文件发布临时样例。
- 下载目录使用 `session-export v1`：`manifest.json` 和 `logs/flight.sslog`，无未声明的附加文件。
- 严格操作白名单及参数集合；拒绝未知操作、额外字段、真实端口/USB路径和任意输出路径。
- 有锁的内存租约演示：独占、TTL、代次、冲突和过期旧持有者拒绝。

**日志是共享契约的 `123456789`（9 字节）传输 golden 向量，不是有效 SSLOG 记录。**
即使样例清单写 `SSLOG` / `0.0`，也仅延续共享 golden 的格式声明，不代表字节可供 FLP 使用。
CLI 返回 `valid_sslog_recording=false`，清单的 `source_app.version` 是 `0.0.0-mock`。
这是共享字段/样例包的适配验证，不是 ASCII wire、真实协议互通、日志采集或硬件验收。

`device_ref` 仅是当前模拟实例中的选择键；真正的 `device_id` 和 `boot_id` 始终 `unknown`。
CRC/长度 token 只是变化检测值，不是认证或跨设备、跨启动身份。
不支持断点续传；断开/超时/取消/重启之后必须重新取得能力和元信息，从零开始。

## 使用方法

在本目录运行，不需安装软件包或启动服务：

```powershell
python -B device_service.py devices
python -B device_service.py status mock-fc-001
python -B device_service.py capabilities mock-fc-001
python -B device_service.py collection mock-fc-001
python -B device_service.py logs mock-fc-001
python -B device_service.py metadata mock-fc-001 1
python -B device_service.py download mock-fc-001 1
python -B device_service.py lease-demo
python -B -m unittest discover -s tests -v
```

CLI 成功退出码 0；API 拒绝/失败为 1；非法 CLI 参数为 2。每个 CLI 是新进程，结束即退出。
`download` 唯一的写入是 OS 临时目录下新建 `silverstar-device-service-mock-*` 样例包；
不覆盖既有文件、不接收目标路径、不删除来源。失败返回 `IO_ERROR`，可能留下标为 incomplete
的临时样例目录；不要把部分文件当完整结果。用户检查后可只清理自己刚生成的样例目录。

```python
from device_service import MockDeviceService, DeviceServiceResult

service = MockDeviceService()
reply = service.Request_Execute({"operation": "status", "device_ref": "mock-fc-001"})
assert reply.result == DeviceServiceResult.OK
print(reply.Reply_AsDict())
```

| `Request_Execute` 操作 | 必须参数（除 `operation`） | Python API |
|---|---|---|
| `devices` | 无 | `Device_List()` |
| `status` | `device_ref` | `Device_ReadStatus(device_ref)` |
| `capabilities` | `device_ref` | `Device_ReadCapabilities(device_ref)` |
| `collection` | `device_ref` | `Collection_ReadStatus(device_ref)` |
| `logs` | `device_ref` | `Log_List(device_ref)` |
| `metadata` | `device_ref, file_id` | `Log_ReadMetadata(device_ref, file_id)` |
| `download` | `device_ref, file_id` | `Log_DownloadTemporary(device_ref, file_id)` |
| `lease` | `device_ref` | `Lease_Read(device_ref)` |

这些是本地 API 调用名，不是新 wire 协议。`ServiceReply` 是本地返回包装，内含类型化
`DeviceServiceResult`；公开日志数据保留共享契约字段。没有 HTTP、MCP SDK 或常驻监听。

## 租约概念与局限

`Lease_Acquire/Lease_Release` 仅供同一个 Python 对象内的演示和测试，未放进 AI 操作白名单。
`lease-demo` 展示 GSHC 取得租约、AI 得到 BUSY、GSHC 释放后 AI 取得模拟租约。
租期 1–60 秒，使用单调时钟；新租约有新代次，旧代次不能释放新持有者的租约。
owner 和 generation 不是凭据，不创建持久化访问。

**它不锁真实串口，不协调其他服务实例或进程。** 两次 CLI 的租约不共享。
查询读固定内存快照，所以不要求租约；这不代表未来可以无租约读取真实连接。
真实集成时只能有一个连接所有者，读写请求均须经所有者排队。未来还须定义规范化的物理
资源键、OS/进程级互斥、会话失效、请求取消、过期连接关闭及崩溃恢复。
未知设备身份不能用模拟引用替代；端口重用后旧租约/授权不得沿用。

## 未实现与 AI 安全边界

未实现真实串口/USB、ASCII 编解码及 PENDING/POLL/CANCEL 时序、跨进程所有权、真实采集、
大文件流式下载、断点续传、GSHC/CF33/FLP 集成、GUI、HTTP/MCP、网络监听、凭据或系统服务。
没有创建这些能力的自动探测/回退分支。

`connect/write/delete/flash/move/collection_start/collection_stop` 等均不在请求白名单，
返回 UNSUPPORTED；CLI 也不提供相应命令。源码中没有真实 transport 或通用执行接口。
这只是 API 边界，不是将任意 Python 调用者隔离的安全沙箱。未来 AI 若仍持有 Shell/系统串口
权限，就无法靠这个白名单限制它；正式部署必须在工具权限和操作系统层面限制访问。

设备标签、状态文本、日志内容、导出字段均视为不可信数据；不得作为 Python、Shell、URL、
工具调用或操作授权执行。本轮不解析日志记录，不根据日志内容调用别的功能。
未来读取大日志应有大小/时间上限、来源标注和数据/指令隔离，保留原始证据。

运动接口仅提出后续设计，不提供可调用桩：

1. AI 可提交一个有单位、设备/会话身份、限位和速度约束的“建议/预演”。
2. 人工在独立可信界面审核确切计划、风险和设备身份，签发短期单次授权；修改计划须重新审核。
3. 唯一连接所有者执行前再校验授权、当前状态、硬限位和急停回路；超时/断链进入已验证的安全状态。
4. 硬件急停、硬限位和安全控制器独立于 AI。AI 无权解除急停、旁路限位、扩大权限或伪造人工确认。

实际安全机制和停止行为需要机械/固件方案及实机验证，本原型没有提供任何运动安全保证。

## 下午只需决定的三件事

1. 第一个消费者是谁：先 GSHC 只读快照，还是先 CF33 测试 runner？不要同时扩展所有消费者。
2. 连接谁拥有：优先 GSHC；只有确认需要无 GUI 运行时才抽出独立所有者。
3. 第一阶段是否只保留读状态/下载旧日志：建议是。GUI 暂缓，后续若人需要维护入口，再做小面板。

本轮到此为止，不推进实机或运动。撤回仅需归档这个独立目录；其他应用未引用它。
保留的小型证据及实际验证范围见 [VALIDATION.md](VALIDATION.md)。
