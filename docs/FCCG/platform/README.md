# SilverStar Platform Documentation

本目录是 **SilverStar 平台/固件规范**，由统一仓库中的 FCCG 维护。当前产品发布身份由根目录 `VERSION` 决定，版本为 0.1.0；以下 0.0.12 文件是合仓前的技术规范快照，协议与硬件身份未随产品版本改变。

- [`SilverStar_0_0_12.md`](SilverStar_0_0_12.md)：合仓前的平台规范快照；
- [`details/`](details/)：接口、协议、状态机、构建和验证细节；
- [`formula/`](formula/)：INS/KF数学公式源文件和PDF；
- [`history/`](history/)：0.0.7~0.0.9历史平台文档，保持历史语义。

FCCG自身的软件架构、插件格式、工程格式、GUI和生成器说明仍位于上一级 `docs/`。平台文档不应再由外部reference firmware人工维护第二份当前版本。

[运行时安全与任务栈](details/RUNTIME_SAFETY.md)规定启动、命令执行上下文和任务栈证明边界。组件包内的文档仅是package-local implementation note，外部reference docs不覆盖本平台规范。

## Algorithm configuration contract

Pure INS/KF6/ESKF15 实际参数、单位、P0/Q/R 转换与 decoder 1.2 边界见[算法参数契约](../ALGORITHM_PARAMETERS.md)。当前质量策略 revision 3、ESKF revision 1 及预飞、时序、日志的跨组件行为见[导航契约](../NAVIGATION_CONTRACT.md)。历史 decoder 按原版本复算。
