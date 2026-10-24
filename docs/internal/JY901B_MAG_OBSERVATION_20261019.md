# JY901B磁输出：现固件有界只读观测

2026-10-19 03:45 UTC；owner `installation_c_impl_20261019_v1`。按用户新增授权检查现固件，未烧录采集候选，未发送传感器配置/解锁/EEPROM命令，未启动任务或执行器测试。

**未观测到有效0x54磁帧。** 四次非原子RAM快照约2.88 s内，JY driver及adapter发布副本的MAG/ACC/GYRO计数均为0，MagTimestampUs=0，MagRaw保持初始化值，valid_frame_count=0、checksum_error_count=0。这不是静止数值变化小导致的误判：有效帧计数本身没有增加，也没有将零填充值当作测量。

已只读匹配板载Flash全部ELF load bytes，SHA绑定现候选 `7056eac7d4de282eebf2f7b1f637ca1b30948e192eb086167121860d763c2f44`。DAP为Horco CMSIS-DAP，USB serial `132765403520`；目标CPUID/0x413 family匹配所选F407配置，观测时core running。没有halt/resume/reset、target memory write、flash或option bytes操作。RAM地址由该ELF的有界DWARF成员解析，只有通过镜像匹配后才读取。

生成资源明确JY instance0映射`PLATFORM_UART_1`、`module_variant=0`（配置为B，未凭此宣称独立识别了实物型号）。该UART initialized=1，rx_bytes=0、tx_bytes=0且不增长；adapter initialized=1、health.error_count=1、effective_config.output_rate_hz=0。软件初始化flag不证明配置命令已发送或生效。目前没有支持“RSW写入已经到达模块”的运行时证据。源中B的磁输出组合为0x0256、S为0x0216，Euler不在组合内；本轮没有混用型号或尝试重写任一mask。

串口COM9最初在受限执行下拒绝打开；获准的独占只读检查后可打开，但SYSTEM/IMU/MAG查询均没有收到应答。MAG STREAM START也未获ACK；随后有界发送一次MAG STREAM STOP清理，仍无ACK。不能将发送字节数当业务完成，最终MCU stream flag/维护及写日志状态均为UNKNOWN。COM9已关闭；SWD会话最终detach成功，未保留探针句柄。没有清除日志或冻结TF业务。

当前失败类别是**模块数据接收/处理路径无有效输入证据，配置发送/生效未证明**。零checksum错误不能证明解析路径已获得有效输入；这不能区分尚未到达配置阶段、DMA/串口输入、波特率/接线/供电、输出设置或供应商型号差异，也不能断言硬件损坏。继续试配需要先确认真实模块型号和实际RX/TX链路，不应盲目重复未知命令。

证据位于[观测摘要](../../.work/dev013_installation_c_impl_20261019_v1/jy_observation_summary.json)、[完整Flash/RAM观测](../../.work/dev013_installation_c_impl_20261019_v1/existing_jy_ram_observation.json)、[串口查询](../../.work/dev013_installation_c_impl_20261019_v1/existing_firmware_serial_observation.json)和[清理结果](../../.work/dev013_installation_c_impl_20261019_v1/serial_stream_cleanup.json)。Flash/RAM读取是有界非原子观测，不建立测量时间同步、标定精度或飞行资格。
