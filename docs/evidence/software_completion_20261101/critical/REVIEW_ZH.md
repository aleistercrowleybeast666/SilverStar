# 任务状态发布与错误传播：限定合同复核

本记录对应 `system_mission_process.c`、`system_mission_process_runtime.c`
及固定控制器窗口接口。基线为 `8b028f280ba01dce0efc697479ef99ec143f7456`。
实际编译源码及 SHA 在 [compiler-inputs/index.json](compiler-inputs/index.json)；
不是对整个固件、任意配置、所有 Power of Ten 规则或硬件安全的认证。

## 实际缺陷及修复证据

| 合同 | 修复前实际失败 | 修复与正常/故障证据 |
|---|---|---|
| 事件读取不能在配置读取失败时部分改写调用者 | `config-error` 失败 | 先检查配置结果，再进入发布；调用者哨兵保持不变 |
| 损坏的阶段计数不能用于数组索引或返回活动许可 | `event-count`、`active-count`、`navigation-count` 失败 | 同一 IRQ 临界区先检查计数、布尔状态及合法 ready 位，再读取/发布；真实断言故障记录和终止路径被 Host 捕获 |
| 终止状态、事件顺序和时间不能彼此矛盾 | `active-terminated`、`event-future`、`event-order` 失败 | 检查终止时间等于最后处理时间、所读历史及相邻项严格递增且不晚于最后时间；不扫描未使用的整个历史 |
| ready 位和已启动标志必须属于真实状态域 | `ready-mask`、`mission-flag` 失败 | 存储状态损坏进入既有 fail-stop；外部非法输入仍返回 Invalid |
| 终止配置失败仍必须终止，且不能返回成功 | `termination-config-error` 失败 | 发布安全停止，同时返回 Invalid，交给运行时进入 FAULT |
| 阶段动作/日志读取异常不能当作“无更多事件” | `events-invalid`、`log-events-invalid` 失败 | Unavailable 才是普通排空；其他异常立即传播并停止该轮发布 |
| 动作失败不能继续记录成功；日志参数/内部错误不能无声重试 | `action-error`、`log-bad-param` 失败 | 动作错误立即 FAULT 并返回；日志仅 FULL/BUSY/BAD_STATE 保留当前游标作有界重试，其他错误进入 FAULT |
| 控制器窗口必须区分未启用、等待、运行、停止、配置异常 | 新接口正常及损坏状态测试 | 固定 owner 4、停止优先、同锁读取；依赖失效不能伪装为尚未开始，实际输入/依赖撤销由控制器 adapter 负责 |

`mission-before-v3.log` 为 **9 failed / 1 passed**；
`termination-before.log` 为 **1 failed / 12 deselected**；
`runtime-before-v2.log` 为 **4 failed / 6 passed / 8 deselected**。
这些是相同安全期待下旧实现的实际执行失败，不是手工推测。

最终本组 [mission-combined-after-v2.log](mission-combined-after-v2.log)
为 **31 passed，65.05 秒，退出 0**：13 个状态/窗口用例和 18 个真实生成/native
用例在一次命令中执行。两组合同夹具实际使用 GCC `-O2 -Wall -Wextra -Werror
-pedantic -fanalyzer` 编译和链接；并非 syntax-only。唯一 pytest 配置警告来自
关闭 cacheprovider 后已有 `cache_dir` 选项，不是 C 编译/分析警告。

```powershell
& .venv\Scripts\python.exe -m pytest apps/SCG/tests/test_mission_critical_contracts.py apps/SCG/tests/test_mission_process_native.py -q -s -p no:cacheprovider --basetemp=.work/0.1.3-software-completion-20261101/critical/post-combined-v2
```

重放应使用新的任务输出目录。原输出和日志保持为本次证据。

## 并发、失败路径及证明边界

阶段 Step/Transition/Terminate 的写入者是既有 FlightTask；它不从 ISR 调用。
跨任务活动/停止/事件读取使用已有 `PlatformCritical_Enter/Exit`，状态验证与读取
处在同一个临界区。64 位 `last_us` 的写入移入原状态发布锁，避免读者看见撕裂值。
加速/导航条件保持 FlightTask 私有历史，正常来源过期走普通 Waiting/Invalid 路径。
配置 getter 来自静态生成的有界数组；外部配置先经生成器合法性校验，Host 仍注入
getter 失败以检查运行时处理，不能依赖“当前 getter 不会失败”来丢弃返回值。

内部断言先于危险索引和输出写入。夹具调用实际 `silverstar_assert.c` 并检查模块、
原因、故障记录、锁状态和调用者哨兵；仅在 Host 用 setjmp/longjmp 截获最终 trap。
目标固件没有加入该机制，测试结果不表示 MCU 能从损坏状态恢复。
正常有界日志重试不增加游标、不重复已成功动作；发生异常的本轮不再发布后续成功记录。

早期环境/夹具/并发生成失败均保留：缺 basetemp 父目录、Host volatile 夹具编译错误、
夹具拼接 NameError、生成期间另一个 owner 更新源码引发精确 payload 身份拒绝。
`mission-after-v1` 和 `mission-runtime-after-v1` 不是通过的整组结果；最终执行前明确
冻结 owning payload 后才生成，未放宽来源检查。

上述表格闭合的是列出的软件合同。Power10 文本扫描器仍须输出
**critical-contract review NOT PROVEN**，因为它不能从文本证明全程序合同、
指针/回调语义、WCET 或全路径栈。最终生成 Power10、ARM、资源及完整栈结果由本任务
总报告对应构型单独记录；不能用这 31 项 Host 测试替代。
