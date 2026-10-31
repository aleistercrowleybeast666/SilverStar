# SilverStar_GSHC 接收与显示架构

AIR字段以 [`AIR_PROTOCOL.md`](AIR_PROTOCOL.md) 为准，GSP以 [`GSP_MIN_PROTOCOL.md`](GSP_MIN_PROTOCOL.md) 为准。

## 1. 数据流
```text
SerialWorker(QThread): open/read/write/close
  ↓ bounded direct enqueue
ProtocolWorker(QThread)
  → GSP parser
  → AIR parser
  → SS-TM session / global sequence / event identity acceptance
  → immutable ProtocolEvent
  → Async JSONL queue (先持久化)
  → bounded UI mailbox
  ↓ GUI timer pull
Controller
  → FlightControllerState
  → EventHistory
  → command/handshake transactions
  ↓ render timer
MainWindow / plots / one OpenGL view
```
SerialWorker不访问Widget/协议；ProtocolWorker不访问Widget；MainWindow不解析wire。

## 2. 有界队列
所有实时容器有明确上限。正式数据在UI合并前进入JSONL；GUI忙时只允许合并中间显示用PREFLIGHT/FLIGHT状态，不能静默丢持久化数据。

## 3. Session/Handshake
Controller是Capability/command/session唯一状态所有者。第一次兼容Capability绑定会话；更新seq在未握手时替换pending Capability ACK。握手成功后迟到Capability只做诊断，不自动清空状态或rollover日志。新飞控会话通过明确断开/重连建立。

上述 Controller 握手规则保留用于历史 AIR M0。SS-TM 的接收语义由后台
`ReceivePipeline` 的 `TelemetrySession` 唯一判定，再通过不可变快照提供给
Controller；UI 不在合并之后重新判定同一帧。日志的物理换算只使用当前已接纳
boot 的合格 CAP。retired boot、重复或过期 CAP 仍归档原始包，不生成新的物理结论；
新 boot 尚无 CAP 时保留 raw 数值并将物理量标未知。

SS-TM 发送序号是全局 16 位序号。接收端使用全局展开位置和 256 帧有限乱序窗口，
事件另按稳定 event_id 去重，CAP/HEALTH 等快照禁止旧值覆盖新值。连续主流中的稀疏
CAP/EVENT 跨半圈与完整回绕不再误丢。若长断线后首个跳变超过半圈且缺少独立发送端
证据，现有协议不能唯一判定回绕次数，接收端保守拒绝，不将其宣称为已解决的长断线重同步。

每个解析帧具有独立 `ingress_ordinal`，不把同一串口 chunk 的共同时间戳当排序键。
UI mailbox 合并时保留边界前的最后显示样本并按 ordinal 排序；原始数据和已接纳的
mission/stage 事实在合并前归档。迟到的首次 START 绑定已有轨迹，不清空早期样本；
迟到阶段事实不会覆盖时间更晚的已收事实。S 在当前 boot 观察到任务开始后保持被动，
不拿任务相对时间与 CAP 的 boot 时间混算后重开上行。

握手完成：匹配`ACK(CAPABILITY_ACK,OK)`或`PREFLIGHT_STATUS.capability_acked=1`恢复。Capability自身seq与PC命令seq严格区分。

## 4. Calibration / Alignment
Capability决定build支持的流程；当前状态由PREFLIGHT_STATUS决定。最终NONE/OneFace/SixFace规则见 [`AIR_CALIBRATION_CONTRACT.md`](AIR_CALIBRATION_CONTRACT.md)。当build含采样procedure时，GSHC可发送`CAL_START(NONE)`选择默认校正；仅0x01时飞控自动NONE。

`FlightControllerState.sampling_calibration_modes()` 只返回采样流程；`calibration_start_modes()` 返回当前可启动事务。Controller 在公共入口、通用入口及每次重试发送前使用 `check_calibration_start()`；无采样 build 的 NONE 返回 `AUTOMATIC_NONE`，不发重复命令。

NONE 必须由真实 `PREFLIGHT_STATUS` 的 mode/state/ready 确认；Calibration 状态事件继续显示状态，但不补造其 ready 标志。CAL_RESET 的丢 ACK 恢复也区分自动 NONE/READY 和等待选择的 NOT_SELECTED/IDLE。两个分支都由快照驱动。

ALIGN_START ACK只表示accepted；最终看alignment state/ready。普通ACK错误/timeout不改变握手状态。

## 5. 诊断
AIR Link Details集中显示Capability RX、PC→GS request、serial writes、GSP ACK、GS TX/RX/CRC、AIR ACK/PREFLIGHT恢复、队列积压、RSSI/SNR、最后AIR/快照年龄。用于区分PC/GSP/空口/飞控运行故障。

## 6. GUI
预飞/飞行/后处理三页可手动切换。左侧OpenGL context只创建一次。飞行首次由START ACK、MISSION_START或FLIGHT_STATE确认时自动切页一次；之后不抢焦点。

## 7. Persistent vs live
JSONL记录整个会话；EventHistory和实时曲线是有界GUI缓存。实时窗口裁剪不影响持久化。

有效 WGS84 最后观测在后台接收线程原子保存至用户数据目录的
`data/recovery-last-wgs84.json`。该文件是寻回显示缓存，不是原始飞行记录或控制输入。
重启加载后明确显示历史来源；缓存只保存 wall-clock 保存时刻与当时样本年龄，
不复用上次进程的 monotonic。wall-clock 回退时年龄显示未知。POSITION/HEALTH
均更新有效链路接收年龄，保留点重发不会更新其测量新鲜度。WGS84 不要求确认 ENU
原点；没有操作者实时位置时只提供坐标、地图和导出，不编造操作者距离/方向。

## 8. Thread safety
长后处理/模拟/数据迁移在独立worker thread；UI线程只更新状态。所有退出/取消有界，不能遗留运行QThread对象。

## Session recovery update (2026-10-01)

The controller now permits automatic local session invalidation on BOOT or confirmed rollback of boot-relative preflight telemetry time. It rebinds a fresh state model, preserves event history, cancels transactions and negotiates Capability again. It never automatically replays business commands. Unknown Capability cannot be acknowledged by a preflight snapshot. Read AIR_PROTOCOL.md for priority, timestamp-domain and stale-packet limitations. SELFTEST_COMPLETE text includes pass/fail; only the preflight snapshot supplies current system readiness and block reason.
