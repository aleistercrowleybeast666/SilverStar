# SilverStar Windows 发布候选 · 2026-11-03

SilverStar 从 `feature/usb-transport-0.1.3-20261013` 的 `8a25f99e7096df94cbf46b83bf4049a55e43a887` 继续。Underline 从 `main` 的 `351ab0b0167eb37bd6312c2bde79181d6225e97f` 建立 `codex/release-candidate-20261103`。TreeDiagram 沿用已有的电机数据交换合同。本次验证使用软件目标、模拟输入和 Windows 桌面，设备端操作留待台架执行。

| Windows 便携包 | 源码与身份 |
|---|---|
| `D:/python_software/SilverStar/dist/rc1103c/SilverStar_0_1_3_RC_20261103_Windows_x64.zip` | [构建提交 `18701020`](https://github.com/aleistercrowleybeast666/SilverStar/commit/187010202685111fa0653b4fa4641e83140d7cfc)。240544021 字节，SHA-256 `54fa9f18761bf67ddb4571b6427b21b2905fe0ba103582b693a41c918faadfed`。 |
| `D:/python_software/Underline_RETLDC/dist/rc_20261103/Underline_RETLDC_RC_20261103_Windows_Portable.zip` | [构建提交 `df6fefd3`](https://github.com/aleistercrowleybeast666/Underline_RETLDC/commit/df6fefd392c1577b9b1301dc488e1d175774badb)。101439751 字节，SHA-256 `14fa32f129353026e7644e60cd34cd5317c90d3ac12241c868b35de01ced277a`。[Underline 最终报告及截图](https://github.com/aleistercrowleybeast666/Underline_RETLDC/blob/a6e5d3b1eab66032c109cedbcd0743c05395c2c9/docs/evidence/rc_20261103/REPORT_ZH.md) |

## 用户入口

将整个 SilverStar Windows 候选包解压。运行 `SCG.exe`，依次完成硬件与通信、任务流程、检查与生成。两端都选择自定义且未导入时，生成区会分别说明缺少什么。选择一个目标可以独立生成，已明确配置的跨端冲突仍需解决。属性窗的“应用”更新当前工程；工程保存和生成各有独立入口。[最短操作说明](../../public/USER_WORKFLOW.md) · [SCG 用户指南](../../public/SCG/USER_GUIDE.md)

运行 `GSHC.exe`，连接地面站 UART 或外部 USB-UART 桥。飞控维护 UART 提供磁力计采集、拟合、应用及保存；持久化结果取自设备状态和读回。任务结束后导出日志、匹配的 `.ssdecoder` 及任务快照，使用 `FLP.exe` 打开日志。[磁力计操作](../../public/GSHC/MAGNETOMETER_CALIBRATION.md) · [FLP 回看](../../public/FLP/APP_README.md)

## 便携包实测

正常运行三个独立的 PyInstaller Analysis、PYZ 和 EXE，再合并公共库。2275 个第一方文件与提交核对，最终 ZIP 的 3423 个成员在另一目录重新解压并逐项验证。依赖清单按实际收集的文件归属到 34 个分发包。NumPy 的 RECORD 自身没有内嵌自身哈希，另行核对唯一归属路径及收集前后字节。[构建收据](packaging/candidate.json) · [解压收据](packaging/unpacked.json) · [许可证文件归属补查](packaging/wheel-record-self.json) · [各次完整构建的日志及清单](packaging/complete-packaging-logs.zip)

在最终解压目录分别启动三套 EXE。SCG 两个未导入目标显示同样的阻塞原因，两个生成按钮均禁用。GSHC 在串口断开的情况下正确禁止采集、应用、保存，并通过普通文件选择器读取 SCG 导出的 `.ssmission`。FLP 以英文深色打开最终 F407 的实际生成日志，显示精确包、40080 条有效记录、0 个 CRC/解码错误，可打开记录参数、单位和键。关闭了本次未保存的测试草稿，三个程序均退出。[三程序身份与截图哈希](packaging/native-gui.json) · [SCG 检查与生成](packaged-gui/final-scg-build.jpg) · [GSHC 任务快照](packaged-gui/final-gshc-declaration.jpg) · [磁校准](packaged-gui/final-gshc-mag.jpg) · [FLP 记录参数](packaged-gui/final-flp-parameters.jpg)

两次实测直接发现交付问题。Windows 初次收集的绝对路径过长，改用较短候选目录。首个能压缩的中间包缺少 GSHC 的 `mission_profile.py`，实际 EXE 无法启动。修复了清单，并让打包入口拒绝移出 PYZ 后没有随包源文件的第一方模块。真实 FLP 的旧概览会错误显示时间范围栏，也已通过页面 owner 修复，修后四种语言/主题组合全部通过。[GSHC 修改前的异常](packaged-gui/gshc-before.txt) · [FLP 修改前](packaged-gui/flp-before-range.jpg) · [修后的概览](packaged-gui/final-flp-overview.jpg) · [四种组合](flp/range-final.log)

## 软件验证

- **SCG**。三页与属性窗共享同一工程模型和 TargetReadiness。工程格式 14–23 用历史写入器产生的样本验证迁移。旧 CDC 输入得到明确的迁移提示，原 CubeMX 文件保持原始字节。飞控和地面站的实际生成、固件检查、内存银行和界面截图详见分项记录。[SCG 证据](scg/README_ZH.md)
- **方向和重连**。真实 Ground C 逻辑与 GSHC 接收器使用相同编码帧验证 READY、CAP、START、飞行数据、迟到事件和旧会话。新增只读历史协议隔离、冻结快照断开及最后绝对坐标来源检查。测量独立覆盖遥测、维护采样和大文件传输。[GSHC 结果](gshc/README_ZH.md)
- **默认 F407 的 Host 实例**。`mingw32-make host-tests` 对实际生成的 F407/KF6/SX1281 工程完整运行，77 个可执行测试、5,509,758 次检查、12 个编译正例、17 个预期编译拒绝、20 个明确不适用项，存储检查 4/4；总退出 0。该日志和后续重新生成的证据分别绑定各自输入。[完整输出](flight-host/f407-kf6.log)
- **FLP**。正常打开日志与 CLI 都按 Descriptor 搜索精确匹配，缺失、歧义或损坏时保留修复入口。35 项解码目录、旋转字、真实生成包、快照和 GUI 回归一次通过。H743 事件样例由生成的包和实际 C 编码器构造；FLP 显示量化后的带符号四元数、更新号和质量。没有快照身份的记录显示“不可用”。[35 项回归](flp/snapshot-final-v2.log) · [H743 事件样例](flp/h743-v6.log)
- **记录值和名称**。FLP 从记录读取参数值，在精确解码包中按完整参数键的哈希和存储类型查找名称与单位。缺名、碰撞或类型不同，显示原始键和类型。另有 11 项回归，包括故意让包声明值与记录不同的例子。[参数字典回归](flp/dictionary-final.log) · [固件日志与快照回看](flp/README_ZH.md)
- **校准、旋转和 GNSS**。600 个模拟方向经 PC 的拟合器生成 84 字节包，实际固件服务执行 RAM 应用、双槽保存和校验。第二个独立进程从槽字节重启读回。默认关闭的 H743 在线旋转在受控时间序列上采用 7 次、应用 560 次。四种 GNSS 各自的飞行默认和显式 Portable 共 8 种实际生成组合通过。安装 F407 Debug 的 SRAM 审阅余量为 380 B，CCMRAM 物理余量为 464 B。[完整门禁与未证明边界](../release_20261103/sensors/REPORT_ZH.md) · [配置指南](../../public/SCG/MAG_ROTATION_AND_GNSS.md)

## 复验用的本地产物

下表对应工作机上的实际文件。各单项报告提供模型、ELF、map、BIN、生成清单和工具输出哈希。检查构建及打开日志即可复验，无需连接实物。

| 产物 | 位置 |
|---|---|
| F407 / SX1281 的生成工程 | `D:/python_software/SilverStar/.work/0.1.3-release-20261103/scg/flight-v2/f407-sx1281/project` |
| 该工程的 Release ELF、map 和 BIN | 上述目录下 `Flight_Controller/build/FCCG/SilverStar_F407/Release` |
| H743 / BMI088_SYNC400 / MMC5983MA 在线旋转 | `D:/python_software/SilverStar/.work/release-20261103/sensors/v7/h743/Flight_Controller/build/FCCG/SilverStar_H743ZI` |
| 最终可直接打开的 F407 Host 记录 | `D:/python_software/SilverStar/.work/0.1.3-release-20261103/root/fatfs-final/valid-input/HOST_GENERATED.sslog`。同目录保留精确包与七个引用快照对象。 |

从 SilverStar 仓库根运行 `.\.venv\Scripts\python.exe SCG.py`、`GSHC.py` 或 `FLP.py` 可启动相应的源码应用。固件生成后在 `Flight_Controller` 运行 `mingw32-make all`、`host-tests`、`architecture-check`、`power10-check`、`static-analysis`、`artifact-check`、`stack-report` 等对应目标，使用门禁日志记录的工具链。[软件构型与命令](scg/README_ZH.md) · [工作目录及所有权](WORKSPACE.md)

## 资格边界

Flight 的严格栈门禁要求所选编译输入、回调、运行库、任务、MSP 和中断嵌套均有对应审阅。历史通过的十个构型有各自的封存身份，不能覆盖本轮变化。即使某一任务计算出的余量为正，整项仍以当前严格检查器退出码为准。Power-of-Ten 文本扫描中的关键语义合同也需单独审阅。[本轮栈输入差异](scg/build/stack-closure-delta.json) · [历史证明范围](../software_completion_20261101/stack/v5/DELIVERY_ZH.md)

普通 F407 / SX1281 的补充诊断具体停在设备任务经 NEO-M9N 进入 `SystemDeviceStartup_Tick` 的回调路径。F407 / SX1278 可算出局部链路预算，完整输入仍被严格门禁拒绝。H743 还需审阅 BMI088_SYNC400 的实际调用绑定、新 EXTI 和拟合/日志路径。后续需针对本次生成图、实际链接对象和间接调用完成逐构型审阅及破坏输入反证，再登记新的完整软件上界。[最终 F407 诊断](flight-host/stack-diagnostic.json) · [H743 对象和调用证据](../release_20261103/sensors/final-v2/h743-Release-call-evidence.json)

**单独留给硬件的项目**包括实际 CH340/串口桥的长时传输与取消、两无线端的实测丢包和时延、TF/SD 掉电与重启读回、GNSS 各型号配置 ACK 及真实设备读回、IMU/磁力计数据就绪边沿与时钟偏差、旋转估计在受扰地磁环境中的表现，以及任务栈水位、中断嵌套和 WCET。Host 队列计数、模拟持久化和静态银行容量分别只支持对应的软件结论。
