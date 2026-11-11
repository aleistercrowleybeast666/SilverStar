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
并已无损压缩纳入 [正式原日志索引](root_regressions/index.json)。每份 gzip 均已读回解压、
按原始完整字节比对；索引记录原路径、原文件与压缩文件 SHA-256。

## 清理后的当前入口与明确命令

在 `c8ec254a8d2ce57db23832dc176c80a2da2a9b95` 上补执行以下明确的 GSHC 八文件批次：

```powershell
$env:PYTHONPATH = "$PWD/apps/GSHC"
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_QPA_FONTDIR = 'C:/Windows/Fonts'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:SILVERSTAR_GSHC_DATA_ROOT = "$PWD/.work/gui-convergence-20261110/gshc-final-v2-data"
.venv/Scripts/python.exe -B -m pytest -q apps/GSHC/tests/test_release_telemetry_direction.py apps/GSHC/tests/test_reconnect_recovery.py apps/GSHC/tests/test_sensor_snapshot.py apps/GSHC/tests/test_navigation_readiness.py apps/GSHC/tests/test_magnetometer_calibration.py apps/GSHC/tests/test_magnetometer_workflow.py apps/GSHC/tests/test_maintenance_serial_profile.py apps/GSHC/tests/test_gui_maintenance_workflow.py --basetemp=.work/gui-convergence-20261110/gshc-final-v2
```

单次 **79 passed / 32.81 s**，runner exit 0、36.80 s，190 个 Python 源输入前后散列一致。
早先80项批次没有独立留存完整参数收据，因此只保留其真实日志，不从数量反推八文件命令，
也不把79与80写成同一批次。当前精确 argv、环境、源码散列与原日志均在上述索引。
这次入口第一次遗漏 GSHC 的 PYTHONPATH，8个模块在 collection 阶段报 import error；
完整失败日志及命令保留。补正确应用路径后从新 basetemp 完整执行，没有改源码或测试门禁。

根目录 `test_monorepo_baseline.py`、`test_desktop_version_inventory.py`、
`test_product_version_metadata.py` 三完整文件单次 **32 passed / 1 failed / 115.79 s**。
失败为历史许可文档本地图片缺失；按同一门禁扫描的全部3处断链已修复，许可正文未变，
该完整文档链接测试再执行 **1 passed / 3.05 s**。原32项未重复执行、不拼成一次33项通过。
具体资源与固定提交来源见 [许可引用修复收据](document-link-repair.json)。

## 交付文档与证据检查（2026-11-12）

文档/收据暂存树的差异格式检查通过，原有产物门禁审查245个变化blob通过；
当前文档链接测试单独执行1 passed / 1.28 s。禁用pytest缓存插件以避免生成缓存，
同时出现既有cache_dir配置的1条warning，完整输出保留；不称零warning或新全套通过。
精确命令、源码HEAD和该次暂存tree见[完整命令收据](root_regressions/final-delivery-checks.json.gz)，
[字节索引](root_regressions/final-delivery-index.json)。随后补充原始失败日志及本收据，
最终提交的产物门禁和远端CI另行核对，不把后续文件冒称包含在这次245项检查中。
