# 生成固件日志的精确回看

## F407 存储链

输入为正常 SCG 生成的 F407 / SX1281 / KF6 工程。使用该工程生成的 Host 编译命令、LoggerBus、LoggerTask、LogSink、存储适配器和 FatFs，将模拟测量写到 Host 的内存卡模型。测试夹具最后通过 FatFs 接口导出实际文件，原始负例单独保留。

默认压力夹具的校准记录是全零标记。FLP 以 `calibration_result_not_ready` 拒绝；仅修正校准而让后续 IMU 记录保持无效，FLP 同样拒绝。加入有效校准后，只要日志里没有任务快照身份，原始日志虽可打开，快照仍显示不可用。这三个行为均保留在正常打开路径中。[压力日志拒绝](firmware-writer.stderr) · [不一致的纠正记录](firmware-valid-v4.stderr) · [实现与编译入口](export_test_volume.py)

正例在模拟任务事件之前调用从生成的 FlightTask 原样提取的身份构造函数；它读取 LoggerTask 对已提交快照的诊断。校准记录和快照读取相同的 Host 校准提供者。日志、对象格式、序列化和 FLP 校验均使用正常实现，所有原始门禁保持原样。这个场景验证数据来源及格式，没有运行实机导航或完整飞行调度。[Host 输入与卷导出](export_test_volume.c) · [独立核实脚本](verify_writer.py)

`flight-v1` 的正例含 40080 条记录，`inspect` 自动找到精确解码包。七个 SSOB 文件验证成功，快照含 12 个设备、4 项算法、42 个参数及校准代次 1。解码包 SHA-256 为 `9455696a43494c863d508c1c2d3fa576bc394f5c117092883f8001a69d520297`。[核实值、设备、参数和源文件 SHA-256](firmware-snapshot.json)

同一日志从真实 Qt 主窗口正常打开，进入“记录的任务配置”并逐项查看八个只读标签页。截图取自 125% 缩放的中文界面。参数显示名和单位只接受精确解码包的唯一同类型匹配；表中保留了记录值及原始键。[主窗口](final-125/overview.png) · [参数](final-125/recorded-5.png) · [校准](final-125/recorded-6.png) · [来源身份](final-125/recorded-7.png) · [尺寸和哈希](final-125/receipt.json)

**最终冻结工程 `flight-v2` 已独立复验**。其完整 Host 门禁和存储 4/4 均退出 0。重新编译 Host 写盘夹具，正常 CLI 自动打开 `HOST_GENERATED.sslog`，核实七份快照来源，42 个参数均有唯一的同类型名称匹配。SSLOG SHA-256 为 `942358074e96ccaaefb1921c75d19f5f83d7ba24b0c76b448fcb3b5d1f16ce68`，精确包 SHA-256 为 `2895ad3f1c9d8c7933567e7632776aa1b996c9d2f526622f07a752cd019cd305`。日志、包和所有导出的槽文件在 CLI 打开前后哈希相同。[最终完整 Host](../flight-host/f407-final.log) · [生成的写盘夹具及哈希](fatfs-final.log) · [最终快照收据](firmware-final-snapshot.json)

## H743 旋转事件和普通打开

用正常生成的 H743 解码包和实际 C 编码器构造一个短 SSLOG。FLP 自动匹配 Descriptor，并按清单声明解释带符号的 Hamilton 四元数和窗口质量。未知事件或未知编码保留原字；无有效任务快照时不会填入当前工程值。日志和解码包在打开前后逐字节 SHA-256 一致。[构造和核实脚本](generated_pair.py) · [v7 生成包实际输出](h743-v7.log)

初始问题、修后的 69 项回归及最终 35 项专项都可独立复查。首次运行最终专项时系统 pytest 临时目录拒绝写入；改用新的任务专属目录后，35 项全部通过。[修改前](before.log) · [69 项](after.log) · [临时目录错误](snapshot-final.log) · [35 项](snapshot-final-v2.log)

## 全套测试的比较范围

完整 FLP 测试同时包含历史离线算法、模拟数据集和长运行导出测试。已从基线独立复现的七例及短路径对照另行记录。[基线对照](baseline-review/README_ZH.md)
