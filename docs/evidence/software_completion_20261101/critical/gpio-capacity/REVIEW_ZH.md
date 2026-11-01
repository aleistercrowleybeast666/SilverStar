# F407 GPIO 状态容量与主栈预留

本项修复没有降低 RAM、CCM 或栈余量门槛，也没有缩减 UART、无线、日志、估计器队列。适用源为 F4 平台 GPIO payload、Flight 配置 renderer 和 STM32F407VET6 linker owner；既有参考输入及用户工程没有被修改。

此前 `PlatformGpioContext s_gpio[PLATFORM_GPIO_COUNT]` 分配 96 个状态，共 1920 字节。实际 SS0.5 完整 GPIO 资源表只有编号 0–8；其余编号在 `PlatformStm32f4Resource_GpioGet` 中本来就返回不存在。F1/H7 已有按生成容量分配的做法。F4 现从同一完整资源表求最高逻辑编号加一，而不是按已选择设备裁剪。空表保留一个不可用哨兵槽；自定义稀疏编号 95 仍分配 96 槽；不能解释的 legacy C 符号保留 96 槽。实际 C 数组、访问前边界和 IRQ 遍历同时使用生成容量，编译期拒绝零或超过平台容量。

真实 Host GCC `-fanalyzer` 用相同回归先编译 Git 基线的 F4 C，再编译修复源码。9 槽用例此前失败，报告 `allocated=96 configured=9 highest_lookup=95`；96 槽此前通过。修复后正常读写、未配置洞、容量边界、负编号、NULL 输出、非匹配 IRQ、连续两次 IRQ 消费及临界区状态恢复均通过。生成侧同时验证完整板卡、移除设备后仍保留所有 GPIO、空表、稀疏高编号、非法编号和 legacy 回退。

`gpio-before-v2` 整次为 **1 failed / 9 passed**，其中生成器已修复、C 明确来自旧 Git 基线；`gpio-after-v2` 整次为 **10 passed / 8.06 s**。不是把两次运行拼接成一次通过。编译命令、源码 SHA-256、编译器版本、完整编译/执行日志、原始源码对象和可执行文件 hash 见 `index.json`。v1 是较早未带完整输入收据的同一现象，保留但不替代 v2。

同时将主 MSP 预留由 1024 增至 2304 字节。依据为独立栈审阅对实际 F407 中全部优先级写入者的 `{0,5,6,15}` 域证明、每层实际最大 handler 路径、完整扩展浮点 exception frame、NMI/HardFault 和 reset/main 路径，保留 256 字节最低余量。最终接受须以最终源码的完整严格 stack-report 为准；本项 Host 测试自身不证明 MCU 栈。

v3 分析构型已重新正常生成并实际 ARM 链接：安装配置 Debug 的 RAM `used_bytes=101980`、`allocated_span=101984`，低于不变的 102400 字节门槛；CCM 65056/65536。此前 v2 同配置 RAM 为 102444，超额 44 字节。新增主栈预留已计入，GPIO 节省 1740 字节。v3 随后还有控制器单位合同变更，故这里只作为资源修复证据，不能冒称最终源码的全部门禁通过。

生成边界只精确登记 `Generated/Src/project_control_research.c` 和 `Generated/control_research.json` 两个拥有者文件。`architecture-after-v1` 的完整 16 项运行通过，包含未知生成文件、构建时新生成器和协议事实不一致仍被拒绝。`ownership-after-v2` 曾因并发 Tools 编辑触发保留来源身份不一致而失败；源冻结后的 `ownership-after-v3` 两项通过，并逐字节验证实际生成 Tools 与 payload owner 一致。没有绕过身份检查。
