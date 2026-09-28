# Current Progress

## Algorithm actual parameters / 算法实际参数

新增独立算法参数页面（硬件连接之前），插件声明实际值、单位和 representation。
Project format 12；`.ssdecoder` / project-semantics 1.2，拒绝 decoder 1.1；
Platform 仍为 0.0.12，Record Catalog 与协议布局不变。
参数清单、生成绑定与 Recorded Configuration / Offline What-if 边界见[参数契约](ALGORITHM_PARAMETERS.md)。
精确验证结果仅见仓库根 VALIDATION.md。


## Logger startup burst closeout

已在LoggerBus统一bootstrap/streaming准入：关键事件、配置和Calibration/Alignment/Initial State
继续记录，普通周期流等启动信息排空并同步后开放。成功开文件立即消费，尚未完成的自检报告不触发
关闭重开。未准入计数、真实overflow/gap和sink错误分别保留；队列容量与协议布局保持不变。
已补默认多流启动/START和有限过载恢复模型；精确结果见根VALIDATION。上一轮修复落盘字节损坏，
本轮处理启动短时队列突发；实卡正常启动仍须证明overflow/gap均为零。

## Storage integrity progress

已完成SS0.5 DMA任意地址缓冲、Logger部分写入不重放、关键记录批次同步、队列/延迟诊断、
真实FatFs与C codec的Host回归及严格离线审计。协议布局没有变化，实测结果见根VALIDATION。
启动queue已满时仍打开writer排空，再补入Required decoder descriptor，避免反复关闭导致停滞。
已提供Target字节读回harness；真实SDIO/card、历史SS0014、两次或两卡正常停止验收仍需实机。

> 当前产品版本：SilverStar 0.1.0。合仓前的精确测试数量、hash、RAM/FLASH和commit见本应用 [历史 VALIDATION](VALIDATION.md)，本文件不复制易漂移的数字。

## 已完成
- FCCG作为平台版本/装配权威；
- 工程格式12；`.ssdecoder`/Project Semantics 1.2；
- 三协议独立nullable；
- Verified Board固定资源映射与closure check；
- STM32CubeMX自定义硬件导入；
- I2C、PWM software-supported，Classic CAN reserved；
- SD/TF独立storage Device；
- 多IMU/GNSS/telemetry实例与最小主备策略；
- Calibration空procedure、动态Capability、NONE/Identity；
- production Indicator Init、Alignment deferred processing、任务stack-report；
- Make/EIDE/VS Code统一SourceGraph；
- Host/architecture/Power-of-Ten/static-analysis/artifact gates。

## 仍需实机
- SS0.5长期运行，任务HWM/MSP、中断嵌套、重复校准/对准/Reset与日志快照验证；第二平台须先完成其独立插件和验证；
- I2C/PWM电气验证；
- 双IMU/双GNSS/双radio真实失效注入；
- 完整飞行日志→FLP联调；
- 飞行/环境验证。

## Future
- 完整Health/Fault Isolation、投票、Multi-EKF；
- RF端到端链路健康/failback；
- 真实H7/G4 Platform插件；
- CAN/FDCAN consumer/router；
- 正式公开发布资产。
