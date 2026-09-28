# System Indicator
> **0.0.12增量**：生产启动流程必须在任务创建前调用`SystemIndicator_Init()`。SS0.5系统指示灯固定为Verified Board logical GPIO 6→`IMU_CAL_LED`，低电平点亮；该映射不得由CubeMX inventory序号覆盖。

SilverStar 0.0.12把本地指示灯拆为System角色与直接物理接口两层。System层只使用`SYSTEM/GNSS/SAFETY`逻辑角色和`OFF/ON/BLINK_SLOW/BLINK_FAST`模式；`SystemIndicatorDevice_Set()`只负责channel和逻辑电平，不理解Calibration、GNSS或Safety语义。所选`FlightLogic/Indicator/GpioStatus`实现通过`PROJECT_RESOURCE_SYSTEM_INDICATOR`和Platform GPIO落实极性；当前Target的channel 0映射PA1且低电平点亮。当前仅`SYSTEM_INDICATOR_SYSTEM_ENABLE=1`，GNSS和SAFETY均为0；不存在的channel保持unsupported。

## SYSTEM基础模式

- OFF：Calibration尚未选择、IDLE或FAILED；含采样procedure的build成功RESET后回到此等待状态。无采样procedure的build成功RESET后自动NONE/READY，因此按READY规则显示。
- BLINK_FAST：Calibration正在WAIT_FACE/COLLECTING/CHECKING，100 ms亮/100 ms灭。
- BLINK_SLOW：Calibration READY但还未达到Calibration READY + Alignment READY + System READY，500 ms亮/500 ms灭。
- ON：Calibration READY + Alignment READY + System READY；进入FLIGHT/RECOVERY/LANDED/POSTFLIGHT后保持ON。

AIR Capability ACK、AIR LOCK/UNLOCK和command policy不参与板载SYSTEM灯基础状态。

## 非阻塞阶段完成提示

SystemIndicator提供短时transient override；它只保存`mode + expiry timestamp`，由现有周期`SystemIndicator_Process()`解析，不使用`HAL_Delay`、`osDelay`或busy wait。当前确认时间由`SYSTEM_INDICATOR_EVENT_CONFIRM_US=500000`配置。

以下成功事件将SYSTEM灯临时强制常亮500 ms，然后自动恢复当时的基础模式：

- SIX_FACE任意一面最终PASSED；
- ONE_FACE/NONE或SIX_FACE整体Calibration进入READY；
- 一次`ALIGN START`对应的Alignment进入READY。

失败不编码额外闪码，原因由维护Console、AIR状态事件、`PREFLIGHT_STATUS`和日志表达。最后一面六面校准可能同时触发face PASSED和Calibration READY，两者只刷新同一个500 ms常亮窗口，不产生阻塞。Alignment完成后若System本身已READY，500 ms结束后基础模式仍为常亮。

Alignment 在 START 前进入 `STALE` 时，Calibration 仍为 READY、Alignment ready 变为0，因此 SYSTEM 灯自然回到既有 `BLINK_SLOW`。不增加新的闪码，不触发500 ms成功 transient，也不访问GPIO业务细节。新的 `ALIGN START` 真正再次进入 READY 后，才按既有规则产生500 ms成功提示。START成功后基础模式为ON，guard已停止，正常飞行动作不改变该模式。

## 扩展

当前宏：

```text
SYSTEM_INDICATOR_SYSTEM_ENABLE = 1
SYSTEM_INDICATOR_GNSS_ENABLE   = 0
SYSTEM_INDICATOR_SAFETY_ENABLE = 0
```

GNSS角色的通用System语义已经实现：没有GNSS设备、未初始化、离线或没有有效样本时为OFF；在线且样本有效但`position_usable=0`时为BLINK_SLOW；`position_usable!=0`时为ON。判断读取统一GNSS健康和样本，不单独使用`fix_type`。默认关闭时不读取GNSS接口，也不访问不存在的Board channel。

启用新物理灯需要选择声明式Indicator Device，并在Hardware Connection满足独占GPIO Output、极性和安全启动约束。当前SilverStar 0.5没有第二个LED GPIO，GNSS角色不得复用P_CONTROL火工/任务功率输出。SAFETY语义留给未来独立安全/火工状态机；未启用角色不得访问不存在的GPIO，也不得引入运行期回调注册。
