# SilverStar 0.0.12 运行时安全

本文是当前平台规则；builtin和reference overlay中的同名说明仅为组件实现备注。实际构建结果、内存数值和测试快照见[根VALIDATION](../../VALIDATION.md)。

## 启动与指示灯

生产启动在创建任务前依次初始化Calibration、Alignment和SystemIndicator。SS0.5的系统灯由Verified Board logical GPIO 6映射到`IMU_CAL_LED`/PA1，低电平点亮。GPIO逻辑编号不能来自CubeMX扫描序号。不存在第二个可分配GNSS灯，不能复用系统灯或mission-action输出。状态与非阻塞完成提示见[System Indicator](SYSTEM_INDICATOR.md)。

## Calibration与Alignment事务

Calibration NONE永久合法。build只选择OneFace/SixFace采样procedure，空选启动/成功Reset自动NONE/Identity/READY；有采样procedure时等待显式事务。真实`Start(NONE)`选择并锁定active IMU、失效旧Alignment并发布单位校正。非法或未编入的mode在状态修改前拒绝。日志启用时Required `CALIBRATION_RESULT`记录实际生效结果。菜单及ACK遵循[共同契约](../../AIR_CALIBRATION_CONTRACT.md)。

Alignment Start保留立即的参数、lifecycle、Calibration ready、build capability、source lock、互斥及后端接受检查；接受后由FlightTask周期调用完整Process。Telemetry/Serial不执行完整Alignment重计算，origin reset使用非等待路径，占用时返回BUSY。接受ACK与最终READY是不同阶段。

## 任务栈与故障诊断

静态任务栈预算来自`APP/Inc/app_task_config.h`。每个Arm GNU C编译生成`.su`；Release和Debug分别执行`stack-report`，结合ELF实际call graph、栈配置和保守context reserve，检查所选静态任务及Idle。报告必须显式反映未知、递归或无法可靠界定的调用，不能把Host测试或源代码字面数值当作目标栈证明。

静态fault record保存fault type、task handle、原始name地址、稳定task ID/name、lifecycle和最后正常stack snapshot的HWM及有效标志。overflow hook不得解引用不可信名称、扫描损坏TCB、分配heap或进行诊断I/O。Idle独立标识，未知任务和不可用HWM明确标记。缓存HWM不是overflow瞬间的新测量；overflow检测、assert和HardFault保持fail-stop。

## 待实机验证

SS0.5持续验证冷启动、灯极性/闪烁、重复AIR及Serial校准/对准/Reset、所有任务HWM与MSP/中断嵌套、active IMU锁定及校准日志快照。多设备真实断流/发送timeout、SD写入/掉电恢复和I2C/PWM电气路径需要独立实测。其他MCU及飞行适用性不能由当前软件结果推断。
