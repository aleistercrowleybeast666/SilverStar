# 磁力计本体校准、安装旋转与 GNSS 动态模型

## 本体校准

在具备维护串口的飞控工程中连接 GSHC 的维护端口，打开磁力计校准。选择实际的磁力计实例与物理 ID，读取当前参数，随后采集覆盖各个方向的原始磁场，单位为 µT。GSHC 在 PC 上计算硬铁偏置和软铁矩阵，按样本数、八个八分区覆盖、条件数与残差决定能否应用。在候选计算过程中切换设备、重新连接或重新采集，都会使旧结果失效。

先应用，再读回。RAM 候选的代际是 0，必须与拟合物理 ID、配置摘要和候选包 CRC 相符。保存后等待维护读回显示已保存、无等待、无失败，并核实非零代际。相同对象重复保存可能复用已经验证过的持久代际。设备重启并成功从存储重新加载时，维护读回才将 `loaded` 标为 1。支持读回扩展的固件在 `MAG i CAL READ` 中提供 `crc`、`cfg` 和 `loaded`。旧设备仍可显示基本状态，缺少这些对应关系时不能确认新写入。保存失败后重新读取当前生效项，再决定是否重试应用。

## 可选实时旋转

SCG 高级硬件属性中的实验性选项默认关闭。启用要求一套 BMI088 的 `bosch_sync_400_hz` 同步配置、两个独立 DRDY 资源、一个 MMC5983MA、维护串口和启用 EVENT 策略的 SSLOG。支持 F4/H7 已实现的 GPIO 边沿时钟。普通 JY901B/POLL、通用磁力计或单一 DRDY 不提供此功能。实际接线、安装和用于 BMI088 同步的引脚必须按所选板核对。[Bosch BMI088 数据手册](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmi088-ds001.pdf)

运行时只估计磁传感器相对于所选 IMU 的三维旋转。设备驱动提供两路已消费中断的连续序号与 MCU 时间、当前实例和配置代际。磁力计提供单次转换触发与读取完成的时间区间。两者配对失败即撤销资格。已保存的硬/软铁校正先还原传感器磁向量。若已有符合依赖关系的固定安装记录，则它提供基础旋转，否则采用默认的共同坐标约定。对可观测的 40 对样本窗口拟合残余旋转，用独立窗口验证。每次步长限制 0.16 rad，候选相对基础的总角度限 45°，两次通过相对 RMS 门限后才能采用。标量磁场异常、时间戳过期、源切换或代际变化会阻止在线校正。位置和杆臂仍由工程填写。

日志使用 MCU 单调微秒。数值采用 Hamilton 四元数 WXYZ。采用的向量变换与 `ADOPTED` 记录由相同的量化值解码。基础和残余合成一次，内参只应用一次。新的采用要求 EVENT 确实入队。日志满时撤销采用，有限延期重试固定回退通知。已入队事件的实际写卡结果仍取决于存储路径。用工程随附的精确 `.ssdecoder` 解释当前五个事件。

| EVENT | 内容 |
|---|---|
| 0x32 BASE | 校正后磁传感器到基础 IMU 坐标的旋转 |
| 0x33 ESTIMATE | 基础参考到所选 IMU 坐标的残余估计 |
| 0x34 ADOPTED | 当前真正选用的完整旋转 |
| 0x35 FIXED | 恢复基础旋转 |
| 0x36 QUALITY | 质量代码、相对 RMS 及样本对数 |

所有事件均以 `arg1` 表示运行更新版本号。四种旋转记录的 `arg0` 以高 2 位记录绝对值最大分量的索引，统一其符号为正，其余三个分量按 WXYZ 剩余顺序分别占低位起 10 位有符号数，量化比例为 511√2。QUALITY 低 8 位依次编码等待、训练、候选、采用、不可观测、扰动、过期、源错误。位 8 至 23 为相对 RMS 乘 10000，65535 表示未知。高 8 位为窗口样本对数。维护命令 `MAG 0 CAL ROTATION` 可查询当前基础、估计、实际选择、版本、质量和日志失败计数。

同步 IRQ 是 CPU 服务时刻，MMC 的时刻是转换区间中的估计。周期、源与连续性检查不证明本体固有延迟、物理误差、磁环境、导航精度或飞行适用性。既有离线安装采集另有自身的启动/时基和取样证明条件。

## GNSS 飞控默认值

| 型号 | 新工程默认 | 接收机设置与核验 |
|---|---|---|
| NEO-M8N | Airborne with <4g | 旧式 UBX-CFG-NAV5 的 dynModel 字段为 8，轮询同一字段核验；此实现不证明 M8 掉电持久层。 |
| NEO-M9N | Airborne with <4g | 原专用启动驱动使用 CFG-NAVSPG-DYNMODEL 并验证读回；保留既有速度、消息与启动设置。 |
| MAX-M10S | Airborne with <4g | 配置键 0x20110021 的 E1 值为 8，读取对应配置层。 |
| NEO-F10N | Airborne with <4g | 同键和值，保留 F10 自身的星座、等待与持久层规则。 |
| 通用 NMEA | 接收、解析 | 只读来源不发送上述 u-blox 命令。 |

SilverStar 的 `SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G` 和接收机 wire 值 8 使用各自枚举。显式 Portable 使用 wire 0，保存和重新打开工程会保留选择。在 GNSS 硬件属性中选择当前实例的 UART/profile。已有启动流程广播一个平台动态模型，多接收机显式设置冲突时，验证会列出实例与各自模式，要求用户先在属性页统一。现有工程在磁盘上保持原始选择。旧工程若未显式保存模式，在新生成端按所选器件默认解析。实体接收机固件型号、启动后值、可写层和断电保持均待连接相应设备核验。Airborne with <4g 属于接收机导航配置，不能代替火箭实际过载或接收机全程可用性验证。

各型号协议参考 [M8 接收机协议](https://content.u-blox.com/sites/default/files/products/documents/u-blox8-M8_ReceiverDescrProtSpec_UBX-13003221.pdf)、[M9 SPG 4.04](https://content.u-blox.com/sites/default/files/u-blox-M9-SPG-4.04_InterfaceDescription_UBX-21022436.pdf)、[M10 SPG 5.10](https://content.u-blox.com/sites/default/files/u-blox-M10-SPG-5.10_InterfaceDescription_UBX-21035062.pdf) 和 [F10 SPG 6.00](https://content.u-blox.com/sites/default/files/documents/u-blox-F10-SPG-6.00_InterfaceDescription_UBX-23002975.pdf)。
