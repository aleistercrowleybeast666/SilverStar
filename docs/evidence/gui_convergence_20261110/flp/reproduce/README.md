# 本机真实软件输入复现

本目录保存本轮执行过的脚本原文，不是新建的测试门禁。
脚本按 `.work/<task>/<owner>/` 层级定位仓库，因此先复制到新的小任务目录；
不要在正式证据目录直接运行，不要覆盖原输入或本轮结果。
本轮机器的编译器为 `D:/msys64/ucrt64/bin/gcc.exe`，Python 为仓根 `.venv/Scripts/python.exe`。

示例在仓根执行：

```powershell
$task = '.work/flp-reproduction-20261110/flp'
New-Item -ItemType Directory -Path $task
Copy-Item docs/evidence/gui_convergence_20261110/flp/reproduce/*.py $task
Copy-Item docs/evidence/gui_convergence_20261110/flp/reproduce/producer_sources.json $task
.venv/Scripts/python.exe "$task/prepare_inputs.py"
.venv/Scripts/python.exe "$task/prepare_replay_inputs.py"
.venv/Scripts/python.exe "$task/build_producers.py"
.venv/Scripts/python.exe "$task/build_golden_fixed.py"
```

脚本只用当前 catalog/service/importer/正常校验产生配置和 decoder，
从相同正常生成输出取得源文件/宏/include 后实际 Host 编译；不会把旧 decoder 改名或
覆盖时序配置来冒充新模式。`prepare_inputs.py --resume` 仅用于本轮首次名称 API 错误后的
检查式继续；新复现应从空目录一次执行。

`run_regression.ps1` 是本轮实际命令环境的固定记录，其 `$repo`、`$task`、`$traceRoot`
指向本轮存在的输入。复用新目录时须显式改这些路径，同时供给本轮 SCG owner 生成的
staged/native horizon compile receipts 与 trace；不能拿软件模式不同的旧文件替换。
SF6 的负测试另需在新 inputs/KF6_v6 放置本次 existing 的精确 decoder 副本，
它只用于证明错误 decoder 被拒绝，不是另一次生成证据。

完整套件仍调用原
`docs/evidence/release_candidate_20261103/flp/suite-review/run_flp_suite.py`，
`--max-continuations 0`、单例 150 秒 watchdog 均未改动。
`QT_QPA_FONTDIR=C:/Windows/Fonts` 使用实际系统字体；异常探针不会吞掉 pytest-qt 异常。
生产者完整命令、生成头文件/源哈希与退出码见上级 `producer-*.json`；输入/受测源
哈希见 `full-inputs.json`。这些都是合成 CPU 证据，不是实录或飞行合格证据。
