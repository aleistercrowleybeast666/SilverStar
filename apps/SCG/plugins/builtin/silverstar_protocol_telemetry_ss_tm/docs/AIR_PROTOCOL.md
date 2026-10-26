# SilverStar Telemetry 0.1

SS-TM-S：预飞半双工，START 最后响应真实发射完成或有界截止后进入飞控只发、地面只收。SS-TM-H：全程有界半双工。

机器契约以仓库 `contracts/ss_tm_v0_1.json` 为准。公共头 8 字节：版本 0x01、profile/type、little-endian u16 序号、u32 非零 boot_session。序号表示发送帧；事件 ID 表示同一真实事件，重发不更换 ID 和原始时间。boot_session 来自本次启动硬件 RNG，不用于认证，32 位碰撞仍可能发生。

FLIGHT_DATA 56 B；POSITION 28 B；HEALTH 16 B；EVENT 32 B；CAP 24 B；CMD 15 B；ACK 16 B。硬件 CRC 保持，不加应用层 CRC。POSITION 和 HEALTH 独立解码。旧 M0 由独立插件保留，不能按长度猜测新旧布局。

当前工程实现尚在集成验证；硬件 RNG、RF 吞吐、START 双端切换和射频故障恢复均需上板验证。默认 PHY 不变；不能由 Host 模型推断覆盖距离。状态估计器数学实现不属于本协议修改。
