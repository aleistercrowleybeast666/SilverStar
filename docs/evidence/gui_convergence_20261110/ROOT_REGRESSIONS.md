# 主负责人软件回归

运行目录为 SilverStar 根，Python 使用 `.venv/Scripts/python.exe`，GCC 从
`D:/msys64/ucrt64/bin` 解析，Qt 软件测试采用 `QT_QPA_PLATFORM=offscreen` 与
`QT_QPA_FONTDIR=C:/Windows/Fonts`。原生 GUI 范围另见 [GUI_NATIVE.md](GUI_NATIVE.md)。

- ESKF Host 夹具原先缺实际任务流程实现，链接报 `LoggingActiveGet` 未定义；补入拥有者的
  `system_mission_process.c` 与生成的 `project_mission_process.c`，没有替换成假返回函数。
  `pytest apps/SCG/tests/test_kf6_horizon_backend.py apps/SCG/tests/test_eskf15_horizon_backend.py -q`
  在新 `horizon-traces-final` basetemp 单次执行 **56 passed，202.10 s**。
  该组主要为明确的 staged mode2/30 ms 覆盖，个别 origin-fault 可执行文件用mode1；
  不把整组宣称为原生mode0/mode1配置。
- [原生输入生成脚本](prepare_native_horizon.py)通过正常服务创建JY901S、无气压计、无着陆判定的
  软件限定工程，mode2/300 ms不靠编译宏覆盖。设置
  `SILVERSTAR_HORIZON_NATIVE_CONFIGURATION=1` 及两生成工程环境变量后，同两文件
  `-k 'O2 and normal'` 单次 **2 passed，54 deselected，29.50 s**。
  [输入身份](native_horizon_inputs.json)明确工程及用途。之前JY901B速率证据不足、BMP280缺I2C
  两次被正常校验拒绝，不算通过或硬件证明。
- GSHC 方向、重连、传感器快照、导航准备、磁力计与维护串口/GUI相关八文件单次
  **80 passed，39.23 s**。不是GSHC全套，也没有串口硬件操作。
- [新run消费脚本](consume_new_run.py)对本轮TreeDiagram文件执行真实Preview/Apply与正常生成，
  普通INS/KF6及显式10 ms PID研究分别验证。实际GCC `-O2 -Wall -Wextra -Werror -pedantic
  -fanalyzer` 编译并运行，两组exit0；PID与TreeDiagram C核心结果容差2e-7。
  [命令](integration/commands.json)、[结果](integration/results.json)、
  [范围](integration/scope.json)保留精确来源及参数。普通工程实际mode1；控制研究仍
  `deployable=false`，没有执行器电气驱动。

首次整批horizon运行曾为便携版启动门禁协调资源而主动中止；记录为中止，不与后续片段拼接。
上面56与2均为各自从新basetemp执行到结束的独立批次。完整日志保留在本任务
`root/horizon-traces-final.log`、`root/native-horizon-traces.log`、`root/gshc-regression.log`，
将在任务收尾归档索引记录散列和恢复位置。
