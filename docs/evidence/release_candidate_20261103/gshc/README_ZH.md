# 遥测方向、重连与 UART

Ground、GSHC 和 Flight 使用 SS-TM-S。READY 阶段的 ENTER/EXIT 更新阶段显示。成功 START 回执、任务里程事件或飞行数据可将该次 boot 锁定为下行；迟到的 CAP 或阶段事件不能解除锁定。新连接从被动状态开始，接收线程完全停下后才移交有限的防重放信息和最后绝对位置。接收过的旧 READY、健康状态或旧连接位置不会成为新连接的实况。历史 M0 的只读解析保留。

| 软件检查 | 结果与证据 |
|---|---|
| 修改前的实际失效 | 有效遥测后断开触发冻结对象写入异常，READY 与 CAP 的不同顺序提前封死上行。[断开与顺序](before.log) · [同一批实际编码帧进入 C 和 Python](wire-before.log) |
| 非活动协议及异常外部数据 | 原 M0 帧引发发送，已修复。无效位置、非有限飞行数据及无效健康标志不能抢占当前 boot。[历史输入反例](historical-before.log) · [异常帧反例](invalid-wire-before.log) · [修后同线收发测试](final-wire.log) |
| 控制器及接收路径 | 分别执行 50 项和 243 项回归；含未在 UI 刷新的最后一帧、旧 session、迟到 CAP 和混合阶段顺序。[50 项](after-v1.log) · [243 项](after-v2.log) |
| 串口和文件服务 | 独立 111 项通过，另有 33 项子测试。[运行日志](serial-final.log) |

在 230400 baud、8N1 默认配置下，单个 65 B 遥测帧按 5 Hz 示例占 325 B/s。1200 条 20 Hz 磁力计维护记录占 142730 B，最长 120 B（含 CRLF），行上限 192 B。文件服务逐块校验 1048580 B 数据，2049 块完整还原。双向合计 1408490 个线上字节，在该波特率下的理想串行时间约 61.13 s。读等待为 20 ms，单次读块 4096 B，协议输入队列最多 1024 块。设备调度、真实串口桥和 SD 延时需上板测量。[复验脚本](serial_budget.py) · [计数、读回哈希和时间](serial-budget.log)

从仓库根运行以下命令。pytest 使用一个新的临时目录，避免碰触其他运行的测试文件。

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python -B -m pytest apps/GSHC/tests/test_release_telemetry_direction.py --basetemp=.work/rc-wire-recheck
.\.venv\Scripts\python -B docs/evidence/release_candidate_20261103/gshc/serial_budget.py .work/rc-uart-recheck
```

真实窗口在断开状态下经 Qt offscreen 平台绘制，截图记录逻辑尺寸、像素比和 SHA-256。[中文浅色 125%](qt-125/receipt.json) · [英文深色 150%](qt-150/receipt.json) · [磁力计维护窗](qt-125/mag-calibration.png) · [历史位置与来源入口](qt-150/recovery.png)
