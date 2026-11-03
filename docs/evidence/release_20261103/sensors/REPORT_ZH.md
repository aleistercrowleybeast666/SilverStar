# 2026-11-03 磁力计与 GNSS 软件验收

## 改动与运行

生产代码身份为 `724030c4744886b148a55954bfe0580c575c9bff`。选用原安装捕获插件的固定模式、默认不选择新实验插件的普通模式，以及显式选择 `silverstar.installation.mag_rotation` 的在线模式分开验证。正常操作与五种版本化日志事件见[磁力计与 GNSS 指南](../../../public/SCG/MAG_ROTATION_AND_GNSS.md)。

从 Windows 仓库根目录运行以下命令。构建要求 Host GCC、GNU Arm 14.3、make、PowerShell，Python 环境使用仓库已有依赖。固定安装与 H7 生成用本轮专属目录，`generate.py` 保留原始 CubeMX 输入，验证用 H7 软件夹具另加同步 EXTI2/3 接线。该夹具仅表示一种可生成的板级资源表。

```powershell
.venv/Scripts/python -X utf8 -m pytest apps/SCG/tests/test_release_mag_rotation.py apps/SCG/tests/test_joint_sensor_library.py apps/SCG/tests/test_round4_mmc5983ma.py apps/SCG/tests/test_neo_m9n_startup.py -q
.venv/Scripts/python -X utf8 apps/SCG/tools/validation/mag_calibration_validate.py --tf --serial --supplemental --output .work/dev013_mag_tf_replay/new
.venv/Scripts/python -X utf8 docs/evidence/release_20261103/sensors/generate.py h743 replay-new
```

实际工作目录、阶段和退出码见[结构化结果](final-v2/summary.json)、[默认 F407 命令](frozen-v1/f407-commands.json)、[安装 F407 命令](final-v2/installation-commands.json)、[H743 命令](final-v2/h743-commands.json)和[工作区库存](work-inventory.json)。生成模型、原始门禁输出、fixture 变更哈希及前期失败同目录保留。三个工程中本轮变更且实际选中的 C/头文件按原始字节核对到各自 owner，并核实 Git blob。[源码身份](final-v2/owner-c-identity.json)

## 软件验证

- GSHC 正常磁力计对话框与工作流共 20 项通过，覆盖过期拟合、身份读回、异步存储、失败后重新应用等。旧样机不支持 CRC 时只读兼容。历史未注册的 `MagnetometerCalibrationPage` 只被独立测试引用；发布入口使用校准对话框和独占维护传输。[Qt 结果](mag-ui-v2.log)
- 600 个合成方向经过非对角软铁和硬铁扰动。PC 实际求解器生成 84 字节包，校正服务应用到 RAM，真实双槽持久服务写入、读回并校验。第二个独立进程仅接收原始存储槽字节，重启加载得相同物理 ID 11、代际 1、CRC `CC74E16C` 和校正向量。存储/串口/故障夹具共 49 项通过，GCC analyzer 与 ARM 单元链接均成功。[跨进程结果](pc-persistence-v2.json) | [单元、故障、命令及工具版本](final-v2/calibration-storage.json)
- 数学正/负旋转、单轴不可观测、中断、错误来源、父内参 CRC 及固定安装基准的真实 Host 运行，验证候选四元数的方向、量化后采用值和实际应用一致。对日志满的回退延迟重试，保留原事件时刻。开始时运行时误清除尚未采用的候选，两个真实时序用例失败；修后能在独立留出数据上逐步收敛。H743 生成工程中实际运行的实验入口记录采用 7 次、应用 560 个磁观测。该选择性入口还执行了附带的完整存储/logger 测试。完整的 H7 `make host-tests` 未运行。[前期失败](rotation-v3.log) | [最终专项 8 项](rotation-final-v1.log) | [设备运行时 Host](h743-runtime-host-v7.log)
- 现有固定安装核验和事务消费者单独测试。与 `INSTALL CAPS` 同一个实际 C 编译单元的生产资格代码在合成端口上检验两连续帧、epoch、实例源、物理 ID、时钟新鲜度和立即停止。原生边界允许检查保持过期拒绝；独立应用事务的模拟端口不充当物理机证据。[资格用例](native-qual-v3.json) | [固定安装集成 Host](installation-fixed-host-v7.log)
- 四款接收机均核对了实际生成的飞控头、选中源码和实例配置。M8/M10/F10 另核对生成的每实例配置，M9 沿原生启动驱动。8 个渲染组合分别检查飞行默认与已保存 Portable。第一次直接交换参考板器件被真实资源校验拒绝，原因是原先 M9 串口 921600 不符合其余三款的 115200；后续采用既有一致修改 IOC 和初始化源的独立软件夹具。C 用例覆盖实际 M8 NAV5、现代 UBX 键设置/读回及 M9 专用驱动。多台可配置 GNSS 启动使用一个共同动态模型，互相冲突的显式设置在工程验证中列出并拒绝。通用 NMEA 保持只读。[原始资源拒绝](gnss-render-v1.log) | [8 组生成结果](gnss-render-v2.json) | [包含专用驱动的整组 52 项](host-v7.log)

## ARM、资源与严格栈

三套正式工程的 Release 编译链接、架构检查、原样 Power10 项目文本门禁、固件产物检查、真正 `-fanalyzer` ARM 编译链接全部成功。三套 Debug 编译链接及产物检查全部成功。共执行 27 项目标，21 项退出 0，6 次严格栈门禁退出 2。全固件关键合同审阅仍为 NOT PROVEN。

| 工程 | Release SRAM 已用 / 审核余量 | Debug SRAM 已用 / 审核余量 | CPU RAM |
|---|---:|---:|---|
| 普通 F407 | 101676 / 724 B | 101812 / 588 B | 两构型 CCM 已用 62656 B，余 2880 B |
| F407 固定安装 | 101884 / 516 B | 102020 / 380 B | 两构型 CCM 已用 65072 B，余 464 B |
| H743 在线 | 220988 / 303300 B | 221112 / 303176 B | 两构型 DTCM 已用 8192 B，余 122880 B |

F407 的 SRAM 审核预算是 102400 B，H743 表中使用主 SRAM 物理容量 524288 B。每份 memory-report 内分别记录物理空间、链接占用、保留段及双银行模型。H743 中 392 B 状态和 96 B 中断时刻数组以目标 ELF 符号核对。普通 F407 未链接这两个对象；固定安装 F407 另有 40 B 资格状态。局部余量不能证明安全栈深度或 WCET。

实际 H7 双向量中 EXTI2/3 分别进入对应 IRQ handler、HAL EXTI 和 GPIO 时间提供者。Release 的一条真实设备任务路径经启动分派、磁设备及 MMC adapter，进入 `SystemMagRotation_MagObserve`（局部帧 272 B）与 `MagRotation_Step`（局部帧 208 B）。记录的各函数局部帧不能相加当作最终严格任务上界。F407 默认/安装已变更完整输入；H743 的旧回调绑定审查只识别旧 BMI088 I²C 来源，未覆盖 SYNC400 绑定、新 IRQ 和在线拟合/日志调用。未登记新证明或放宽检查。[H7 Release 符号/路径](final-v2/h743-Release-call-evidence.json) | [H7 Debug 符号/路径](final-v2/h743-Debug-call-evidence.json) | [F407 严格退出](frozen-v1/f407-Release-stack-report.log) | [H743 严格退出](final-v2/h743-Release-stack-report.log)

未证明的部分包括物理 IRQ 延迟/抖动、同步网与线序、实际坐标和场强、运动覆盖、空中磁扰、硬件磁偏置与精度、实机 IMU/磁传感器和 GNSS 配置读回、卡的断电持久性、飞行安全与任务/VECT/MSP/ISR 完整最坏栈。既有离线多传感器捕获仍有单独的完整物理时间/复位证明和资格检查；实际原始采样不自动具备那些证据。在线校正不会永久回写安装参数，位置仅作为配置及日志信息。
